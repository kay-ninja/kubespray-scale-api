#!/usr/bin/env python3
"""
Enhanced Kubespray Scale API Server with Dynamic Inventory
Manages adding worker nodes to a Kubernetes cluster deployed via Kubespray
Automatically generates and maintains dynamic inventory from Hetzner API
"""

from flask import Flask, request, jsonify
import subprocess
import threading
import yaml
import json
import os
import time
from datetime import datetime
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from queue import Queue
import hcloud

app = Flask(__name__)

# Configuration
KUBESPRAY_DIR = "/root/tf-k8s-cluster-1/kubespray"
INVENTORY_FILE = f"{KUBESPRAY_DIR}/inventory/mycluster/hosts.yaml"
VENV_ANSIBLE = f"{KUBESPRAY_DIR}/.venv/bin/ansible-playbook"
SCALE_PLAYBOOK = f"{KUBESPRAY_DIR}/scale.yml"
LOG_FILE = "/var/log/kubespray-api/kubespray-api.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Hetzner configuration
HCLOUD_TOKEN = os.environ.get('HCLOUD_TOKEN')
HCLOUD_NETWORK_ID = int(os.environ.get('HCLOUD_NETWORK', 0))
AUTOSCALER_LABEL = 'hcloud/node-group=apps'  # Label for autoscaled nodes

# Job tracking
jobs = {}
job_lock = threading.Lock()

# Ansible job queue for serializing playbook runs
ansible_queue = Queue()
queue_lock = threading.Lock()

# Inventory update lock to prevent concurrent modifications
inventory_lock = threading.Lock()

# Setup logging with rotating file handler
log_dir = os.path.dirname(LOG_FILE)
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatters
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

# File handler with rotation
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(detailed_formatter)

# Console handler for stdout
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(detailed_formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Also configure Flask's logger
flask_logger = logging.getLogger('werkzeug')
flask_logger.addHandler(file_handler)
flask_logger.addHandler(console_handler)


class JobStatus:
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HetznerInventoryManager:
    """Manages dynamic inventory from Hetzner"""
    
    def __init__(self, token, network_id):
        self.client = hcloud.Client(token=token)
        self.network_id = network_id
        self.logger = logger
    
    def get_autoscaled_servers(self):
        """Get all servers with autoscaler label"""
        try:
            # Get all servers with the autoscaler label
            servers_list = self.client.servers.get_all(label_selector=AUTOSCALER_LABEL)
            self.logger.info(f"Found {len(servers_list)} autoscaled servers from Hetzner")
            return servers_list
        except Exception as e:
            self.logger.error(f"Failed to get servers from Hetzner: {e}")
            return []
    
    def get_server_ip(self, server):
        """Extract private IP from server"""
        try:
            # The Hetzner API uses 'private_net' not 'private_networks'
            private_nets = getattr(server, 'private_net', None)
            
            if private_nets and self.network_id:
                # Find the private network matching our network ID
                for net in private_nets:
                    if hasattr(net, 'network') and net.network.id == self.network_id:
                        return net.ip
            
            # Fallback to first private network
            if private_nets and len(private_nets) > 0:
                return private_nets[0].ip
            
            # Last resort: public IPv4
            if hasattr(server, 'public_net') and server.public_net and hasattr(server.public_net, 'ipv4') and server.public_net.ipv4:
                self.logger.warning(f"Using public IP for {server.name} as no private IP found")
                return server.public_net.ipv4.ip
            
            self.logger.warning(f"Could not find IP for server {server.name}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting IP for {server.name}: {e}")
            return None
    
    def generate_dynamic_inventory(self, static_hosts=None):
        """Generate inventory with dynamic autoscaled nodes"""
        if static_hosts is None:
            static_hosts = self._load_static_hosts()
        
        inventory = {
            'all': {
                'hosts': static_hosts.copy(),
                'children': {
                    'kube_control_plane': {'hosts': {}},
                    'kube_node': {'hosts': {}},
                    'etcd': {'hosts': {}},
                    'k8s_cluster': {'children': {'kube_control_plane': None, 'kube_node': None}},
                    'calico_rr': {'hosts': {}},
                },
                'vars': {'ansible_shell_executable': '/bin/bash'}
            }
        }
        
        # Add static groups
        if 'kube_control_plane' in static_hosts or 'master' in str(static_hosts):
            masters = [h for h in static_hosts.keys() if h.startswith('master-')]
            inventory['all']['children']['kube_control_plane']['hosts'] = {m: None for m in masters}
            inventory['all']['children']['etcd']['hosts'] = {m: None for m in masters}
        
        workers = [h for h in static_hosts.keys() if h.startswith('worker-')]
        inventory['all']['children']['kube_node']['hosts'] = {w: None for w in workers}
        
        # Add dynamic autoscaled nodes
        servers = self.get_autoscaled_servers()
        for server in servers:
            ip = self.get_server_ip(server)
            if not ip:
                self.logger.warning(f"Skipping server {server.name}: no IP found")
                continue
            
            inventory['all']['hosts'][server.name] = {
                'ansible_host': ip,
                'ip': ip,
                'access_ip': ip,
                'ansible_user': 'root',
                'ansible_shell_executable': '/bin/bash'
            }
            inventory['all']['children']['kube_node']['hosts'][server.name] = None
            self.logger.info(f"Added {server.name} ({ip}) to inventory")
        
        return inventory
    
    def _load_static_hosts(self):
        """Load static hosts from current inventory"""
        try:
            with open(INVENTORY_FILE, 'r') as f:
                current = yaml.safe_load(f)
            
            static_hosts = {}
            current_hosts = current.get('all', {}).get('hosts', {})
            
            # Keep only non-apps hosts (masters, workers, bastion)
            exclude_prefixes = ('apps-',)
            for hostname, hostdata in current_hosts.items():
                if not any(hostname.startswith(p) for p in exclude_prefixes):
                    static_hosts[hostname] = hostdata
            
            return static_hosts
        except Exception as e:
            self.logger.error(f"Failed to load static hosts: {e}")
            return {}
    
    def sync_inventory(self):
        """Sync inventory file with current Hetzner state"""
        with inventory_lock:
            try:
                static_hosts = self._load_static_hosts()
                new_inventory = self.generate_dynamic_inventory(static_hosts)
                
                # Write updated inventory
                with open(INVENTORY_FILE, 'w') as f:
                    yaml.dump(new_inventory, f, default_flow_style=False, sort_keys=False)
                
                self.logger.info(f"Synced inventory: {len(new_inventory['all']['hosts'])} total hosts, "
                               f"{len([h for h in new_inventory['all']['hosts'] if h.startswith('apps-')])} autoscaled")
                return True
            except Exception as e:
                self.logger.error(f"Failed to sync inventory: {e}")
                return False


def backup_inventory():
    """Create a backup of the inventory file"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{INVENTORY_FILE}.backup.{timestamp}"
        
        with open(INVENTORY_FILE, 'r') as f:
            content = f.read()
        
        with open(backup_file, 'w') as f:
            f.write(content)
        
        logger.info(f"Created inventory backup: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Failed to backup inventory: {str(e)}")
        return None


def remove_from_inventory(hostname):
    """Remove a node from the Kubespray inventory file"""
    with inventory_lock:
        try:
            backup_inventory()
            
            with open(INVENTORY_FILE, 'r') as f:
                inventory = yaml.safe_load(f)
            
            # Check if node exists
            if hostname not in inventory['all']['hosts']:
                logger.warning(f"Node {hostname} not found in inventory")
                return False
            
            # Check if it's a master node (safety check)
            if 'kube_control_plane' in inventory['all']['children']:
                if 'hosts' in inventory['all']['children']['kube_control_plane']:
                    if hostname in inventory['all']['children']['kube_control_plane']['hosts']:
                        logger.error(f"Cannot remove master node {hostname}")
                        return False
            
            # Remove from hosts
            del inventory['all']['hosts'][hostname]
            logger.info(f"Removed {hostname} from hosts")
            
            # Remove from kube_node group
            if 'kube_node' in inventory['all']['children']:
                if 'hosts' in inventory['all']['children']['kube_node']:
                    if hostname in inventory['all']['children']['kube_node']['hosts']:
                        del inventory['all']['children']['kube_node']['hosts'][hostname]
                        logger.info(f"Removed {hostname} from kube_node group")
            
            # Write back to file
            with open(INVENTORY_FILE, 'w') as f:
                yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Successfully removed {hostname} from inventory")
            return True
        except Exception as e:
            logger.error(f"Failed to remove from inventory: {str(e)}")
            return False


def run_ansible_playbook(hostname):
    """Run Kubespray scale playbook for a specific node"""
    try:
        # First, sync inventory from Hetzner
        if HCLOUD_TOKEN and HCLOUD_NETWORK_ID:
            manager = HetznerInventoryManager(HCLOUD_TOKEN, HCLOUD_NETWORK_ID)
            manager.sync_inventory()
        
        cmd = [
            VENV_ANSIBLE,
            '-i', INVENTORY_FILE,
            SCALE_PLAYBOOK,
            f'--limit={hostname}',
            '-e', 'ansible_shell_executable=/bin/bash',
            '-vvv'
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"DEBUG: ANSIBLE_SHELL_EXECUTABLE = /bin/bash")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully provisioned node {hostname}")
            return True, "Node provisioned successfully"
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Failed to provision {hostname}: {error_msg}")
            return False, error_msg
    except subprocess.TimeoutExpired:
        logger.error(f"Ansible playbook timed out for {hostname}")
        return False, "Playbook execution timed out"
    except Exception as e:
        logger.error(f"Error running playbook for {hostname}: {str(e)}")
        return False, str(e)


def ansible_worker():
    """Background worker that processes Ansible jobs from the queue"""
    while True:
        try:
            job = ansible_queue.get(block=True)
            
            if job is None:  # Poison pill to stop worker
                break
            
            job_id, hostname, ip = job
            
            with job_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = JobStatus.RUNNING
                    jobs[job_id]['message'] = 'Running Ansible playbook'
            
            success, message = run_ansible_playbook(hostname)
            
            with job_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = JobStatus.COMPLETED if success else JobStatus.FAILED
                    jobs[job_id]['message'] = message
                    jobs[job_id]['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"Ansible worker completed job {job_id}. Queue size: {ansible_queue.qsize()}")
        except Exception as e:
            logger.error(f"Error in ansible worker: {str(e)}")


def periodic_inventory_sync():
    """Background worker that syncs inventory from Hetzner every 10 minutes"""
    if not HCLOUD_TOKEN or not HCLOUD_NETWORK_ID:
        logger.info("Hetzner integration not configured, skipping periodic sync")
        return
    
    logger.info("Starting periodic inventory sync (every 10 minutes)")
    
    while True:
        try:
            time.sleep(600)  # Wait 10 minutes between syncs
            
            logger.info("Starting periodic inventory sync from Hetzner...")
            manager = HetznerInventoryManager(HCLOUD_TOKEN, HCLOUD_NETWORK_ID)
            success = manager.sync_inventory()
            
            if success:
                logger.info("Periodic inventory sync completed successfully")
            else:
                logger.warning("Periodic inventory sync failed")
        except Exception as e:
            logger.error(f"Error in periodic inventory sync: {str(e)}")


# Start Ansible worker thread
worker_thread = threading.Thread(target=ansible_worker, daemon=True)
worker_thread.start()

# Start periodic inventory sync thread
sync_thread = threading.Thread(target=periodic_inventory_sync, daemon=True)
sync_thread.start()


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200


@app.route('/add-node', methods=['POST'])
def add_node():
    """Add a new node to the cluster"""
    try:
        data = request.get_json()
        hostname = data.get('hostname')
        ip = data.get('ip')
        
        if not hostname or not ip:
            return jsonify({'error': 'Missing hostname or ip'}), 400
        
        job_id = f"{hostname}_{ip}"
        
        with job_lock:
            # Check if job already exists
            if job_id in jobs:
                existing = jobs[job_id]
                if existing['status'] in [JobStatus.RUNNING, JobStatus.QUEUED]:
                    return jsonify({
                        'status': 'okay',
                        'message': f'Job already in progress for {hostname}',
                        'job_id': job_id,
                        'queue_position': ansible_queue.qsize()
                    }), 409
            
            # Create new job
            jobs[job_id] = {
                'status': JobStatus.QUEUED,
                'hostname': hostname,
                'ip': ip,
                'created_at': datetime.now().isoformat(),
                'message': 'Waiting for Ansible to process'
            }
        
        # Queue the Ansible job
        ansible_queue.put((job_id, hostname, ip))
        
        queue_position = ansible_queue.qsize()
        logger.info(f"Queued job {job_id} to add node {hostname} ({ip}). Queue position: {queue_position}")
        
        return jsonify({
            'status': 'okay',
            'message': f'Node {hostname} ({ip}) queued for addition',
            'job_id': job_id,
            'queue_position': queue_position
        }), 202
    except Exception as e:
        logger.error(f"Error in /add-node: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def status():
    """Get status of a node addition job"""
    try:
        hostname = request.args.get('hostname')
        ip = request.args.get('ip')
        
        if not hostname or not ip:
            return jsonify({'error': 'Missing hostname or ip'}), 400
        
        job_id = f"{hostname}_{ip}"
        
        with job_lock:
            if job_id not in jobs:
                return jsonify({
                    'status': 'unknown',
                    'message': f'No job found for {hostname}',
                    'job_id': job_id
                }), 404
            
            job = jobs[job_id]
            return jsonify({
                'job_id': job_id,
                'status': job['status'],
                'message': job.get('message', ''),
                'created_at': job['created_at'],
                'completed_at': job.get('completed_at')
            }), 200
    except Exception as e:
        logger.error(f"Error in /status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/remove-node', methods=['DELETE'])
def remove_node():
    """Remove a node from inventory"""
    try:
        hostname = request.args.get('hostname')
        skip_k8s = request.args.get('skip_k8s', 'false').lower() == 'true'
        
        if not hostname:
            return jsonify({'error': 'Missing hostname'}), 400
        
        # Remove from inventory
        success = remove_from_inventory(hostname)
        
        if success:
            logger.info(f"Successfully removed {hostname} from inventory")
            return jsonify({
                'status': 'okay',
                'message': f'Node {hostname} removed from inventory'
            }), 200
        else:
            return jsonify({
                'error': f'Failed to remove {hostname}'
            }), 500
    except Exception as e:
        logger.error(f"Error in /remove-node: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/sync-inventory', methods=['POST'])
def sync_inventory():
    """Manually trigger inventory sync from Hetzner"""
    try:
        if not HCLOUD_TOKEN or not HCLOUD_NETWORK_ID:
            return jsonify({'error': 'Hetzner integration not configured'}), 400
        
        manager = HetznerInventoryManager(HCLOUD_TOKEN, HCLOUD_NETWORK_ID)
        success = manager.sync_inventory()
        
        if success:
            return jsonify({
                'status': 'okay',
                'message': 'Inventory synced with Hetzner'
            }), 200
        else:
            return jsonify({'error': 'Failed to sync inventory'}), 500
    except Exception as e:
        logger.error(f"Error in /sync-inventory: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/inventory', methods=['GET'])
def get_inventory():
    """Get current inventory"""
    try:
        with open(INVENTORY_FILE, 'r') as f:
            inventory = yaml.safe_load(f)
        
        # Count nodes by group
        stats = {
            'total_hosts': len(inventory.get('all', {}).get('hosts', {})),
            'autoscaled_nodes': len([h for h in inventory.get('all', {}).get('hosts', {}) if h.startswith('apps-')]),
            'static_nodes': len([h for h in inventory.get('all', {}).get('hosts', {}) if not h.startswith('apps-')]),
        }
        
        return jsonify({
            'status': 'okay',
            'stats': stats,
            'inventory': inventory
        }), 200
    except Exception as e:
        logger.error(f"Error in /inventory: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting Kubespray Scale API with Dynamic Inventory")
    logger.info(f"Inventory file: {INVENTORY_FILE}")
    logger.info(f"Hetzner integration: {'enabled' if HCLOUD_TOKEN else 'disabled'}")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
