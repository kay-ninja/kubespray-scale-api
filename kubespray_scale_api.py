#!/usr/bin/env python3
"""
Kubespray Scale API Server
Manages adding worker nodes to a Kubernetes cluster deployed via Kubespray
"""

from flask import Flask, request, jsonify
import subprocess
import threading
import yaml
import os
import time
from datetime import datetime
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from queue import Queue

app = Flask(__name__)

# Configuration
KUBESPRAY_DIR = "/root/tf-k8s-cluster-1/kubespray"
INVENTORY_FILE = f"{KUBESPRAY_DIR}/inventory/mycluster/hosts.yaml"
VENV_ANSIBLE = f"{KUBESPRAY_DIR}/.venv/bin/ansible-playbook"
SCALE_PLAYBOOK = f"{KUBESPRAY_DIR}/scale.yml"
LOG_FILE = "/var/log/kubespray-api/kubespray-api.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

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
simple_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
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
console_handler.setFormatter(simple_formatter)

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
            # Backup first
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


def drain_and_delete_node(hostname):
    """Drain and delete node from Kubernetes cluster"""
    try:
        # Check if node exists in cluster
        result = subprocess.run(
            ['kubectl', 'get', 'node', hostname],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.warning(f"Node {hostname} not found in Kubernetes cluster")
            return {'exists': False, 'drained': False, 'deleted': False}
        
        # Drain the node
        logger.info(f"Draining node {hostname}")
        drain_result = subprocess.run(
            ['kubectl', 'drain', hostname, '--ignore-daemonsets', '--delete-emptydir-data', '--force', '--timeout=120s'],
            capture_output=True,
            text=True,
            timeout=180
        )
        
        drained = drain_result.returncode == 0
        if not drained:
            logger.warning(f"Failed to drain node {hostname}: {drain_result.stderr}")
        
        # Delete the node
        logger.info(f"Deleting node {hostname} from cluster")
        delete_result = subprocess.run(
            ['kubectl', 'delete', 'node', hostname],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        deleted = delete_result.returncode == 0
        if deleted:
            logger.info(f"Successfully deleted node {hostname} from cluster")
        else:
            logger.error(f"Failed to delete node {hostname}: {delete_result.stderr}")
        
        return {
            'exists': True,
            'drained': drained,
            'deleted': deleted,
            'drain_output': drain_result.stdout,
            'delete_output': delete_result.stdout
        }
    
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout while draining/deleting node {hostname}")
        return {'exists': True, 'drained': False, 'deleted': False, 'error': 'Timeout'}
    except Exception as e:
        logger.error(f"Failed to drain/delete node: {str(e)}")
        return {'exists': True, 'drained': False, 'deleted': False, 'error': str(e)}


def update_inventory(hostname, ip):
    """
    Update the Kubespray inventory file with the new node.
    MUST be called with inventory_lock held or within a context that serializes access.
    """
    with inventory_lock:
        try:
            # Backup first
            backup_inventory()
            
            with open(INVENTORY_FILE, 'r') as f:
                inventory = yaml.safe_load(f)
            
            if 'vars' not in inventory['all']:
                inventory['all']['vars'] = {}
            inventory['all']['vars']['ansible_shell_executable'] = '/bin/bash'

            # Check if host already exists
            if hostname in inventory['all']['hosts']:
                logger.warning(f"Host {hostname} already exists in inventory, updating...")
            
            # Add the new host
            inventory['all']['hosts'][hostname] = {
                'ansible_host': ip,
                'ip': ip,
                'access_ip': ip,
                'ansible_user': 'root',
                'ansible_shell_executable': '/bin/bash'  # ADD THIS LINE
            }
            
            # Add to kube_node group
            if 'kube_node' not in inventory['all']['children']:
                inventory['all']['children']['kube_node'] = {'hosts': {}}
            
            # Ensure kube_node is a dict (handle null/None values)
            if not isinstance(inventory['all']['children']['kube_node'], dict):
                inventory['all']['children']['kube_node'] = {'hosts': {}}
            
            # Ensure hosts exists and is a dict
            if 'hosts' not in inventory['all']['children']['kube_node'] or \
               not isinstance(inventory['all']['children']['kube_node']['hosts'], dict):
                inventory['all']['children']['kube_node']['hosts'] = {}
            
            inventory['all']['children']['kube_node']['hosts'][hostname] = None
            
            # Write back to file
            with open(INVENTORY_FILE, 'w') as f:
                yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Successfully updated inventory with {hostname} ({ip})")
            return True
        except Exception as e:
            logger.error(f"Failed to update inventory: {str(e)}")
            return False


def ansible_worker():
    """
    Worker thread that processes Ansible jobs from the queue sequentially.
    This ensures only one Ansible playbook runs at a time, preventing:
    - Race conditions in inventory updates
    - Concurrent SSH connections to the same nodes
    - Resource contention
    """
    logger.info("Ansible worker thread started")
    
    while True:
        # Get job from queue (blocks until job available)
        job_data = ansible_queue.get()
        
        if job_data is None:  # Poison pill to stop worker
            logger.info("Ansible worker thread stopping")
            break
        
        job_id, hostname, ip = job_data
        
        with job_lock:
            if job_id in jobs:
                jobs[job_id]['status'] = JobStatus.RUNNING
                jobs[job_id]['message'] = 'Updating inventory and running Ansible playbook'
        
        logger.info(f"Ansible worker processing job {job_id} for node {hostname} ({ip})")
        
        try:
            # Run the ansible playbook (which now updates inventory first)
            run_ansible_playbook(hostname, ip, job_id)
        except Exception as e:
            logger.error(f"Ansible worker caught exception for job {job_id}: {str(e)}")
            with job_lock:
                if job_id in jobs:
                    jobs[job_id]['status'] = JobStatus.FAILED
                    jobs[job_id]['message'] = f'Worker exception: {str(e)}'
                    jobs[job_id]['completed_at'] = datetime.now().isoformat()
        finally:
            # Mark task as done
            ansible_queue.task_done()
            
            # Log queue status
            with queue_lock:
                queue_size = ansible_queue.qsize()
                logger.info(f"Ansible worker completed job {job_id}. Queue size: {queue_size}")


def run_ansible_playbook(hostname, ip, job_id):
    """
    Run the Ansible scale playbook in the background.
    NOW UPDATES INVENTORY RIGHT BEFORE RUNNING PLAYBOOK.
    """
    with job_lock:
        jobs[job_id]['status'] = JobStatus.RUNNING
        jobs[job_id]['started_at'] = datetime.now().isoformat()
        jobs[job_id]['message'] = 'Updating inventory'
    
    try:
        # CRITICAL: Update inventory here, right before running playbook
        # This ensures nodes are added one at a time, only when ready
        logger.info(f"Updating inventory for {hostname} ({ip})")
        if not update_inventory(hostname, ip):
            with job_lock:
                jobs[job_id]['status'] = JobStatus.FAILED
                jobs[job_id]['message'] = 'Failed to update inventory file'
                jobs[job_id]['completed_at'] = datetime.now().isoformat()
            logger.error(f"Failed to update inventory for {hostname}")
            return
        
        # Small delay to ensure inventory file is written
        time.sleep(30)
        
        with job_lock:
            jobs[job_id]['message'] = 'Running Ansible playbook'
        
        # Run ansible playbook
        cmd = [
            VENV_ANSIBLE,
            '-i', INVENTORY_FILE,
            SCALE_PLAYBOOK,
            f'--limit={hostname}',
            '-e', 'ansible_shell_executable=/bin/bash',
            '-vvv'
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        env = os.environ.copy()
        env['ANSIBLE_CONFIG'] = '/root/.ansible.cfg'
        env['ANSIBLE_REMOTE_TMP'] = '/tmp/.ansible-tmp'
        env['ANSIBLE_SHELL_EXECUTABLE'] = '/bin/bash'
        env['VIRTUAL_ENV'] = f'{KUBESPRAY_DIR}/.venv'
        logger.info(f"DEBUG: ANSIBLE_SHELL_EXECUTABLE = {env.get('ANSIBLE_SHELL_EXECUTABLE')}")

        
        result = subprocess.run(
            cmd,
            cwd=KUBESPRAY_DIR,
            env=env, # THIS LINE IS CRITICAL
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )
        
        with job_lock:
            jobs[job_id]['ansible_stdout'] = result.stdout
            jobs[job_id]['ansible_stderr'] = result.stderr
            jobs[job_id]['ansible_returncode'] = result.returncode
        
        if result.returncode == 0:
            # Verify node joined the cluster
            time.sleep(10)  # Wait a bit for node to fully register
            node_status = check_node_status(hostname)
            
            with job_lock:
                jobs[job_id]['status'] = JobStatus.COMPLETED
                jobs[job_id]['node_status'] = node_status
                jobs[job_id]['message'] = f"Worker node {hostname} has successfully joined the cluster"
                jobs[job_id]['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"Successfully added node {hostname}")
        else:
            with job_lock:
                jobs[job_id]['status'] = JobStatus.FAILED
                jobs[job_id]['message'] = f"Ansible playbook failed with return code {result.returncode}"
                jobs[job_id]['completed_at'] = datetime.now().isoformat()
            
            logger.error(f"Failed to add node {hostname}: {result.stderr}")
    
    except subprocess.TimeoutExpired:
        with job_lock:
            jobs[job_id]['status'] = JobStatus.FAILED
            jobs[job_id]['message'] = "Ansible playbook execution timed out"
            jobs[job_id]['completed_at'] = datetime.now().isoformat()
        logger.error(f"Timeout while adding node {hostname}")
    
    except Exception as e:
        with job_lock:
            jobs[job_id]['status'] = JobStatus.FAILED
            jobs[job_id]['message'] = f"Error: {str(e)}"
            jobs[job_id]['completed_at'] = datetime.now().isoformat()
        logger.error(f"Exception while adding node {hostname}: {str(e)}")


def check_node_status(hostname):
    """Check if node has joined the cluster using kubectl"""
    try:
        result = subprocess.run(
            ['kubectl', 'get', 'node', hostname, '-o', 'json'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            import json
            node_data = json.loads(result.stdout)
            conditions = node_data.get('status', {}).get('conditions', [])
            
            for condition in conditions:
                if condition.get('type') == 'Ready':
                    return {
                        'exists': True,
                        'ready': condition.get('status') == 'True',
                        'status': condition.get('status'),
                        'reason': condition.get('reason', '')
                    }
            
            return {'exists': True, 'ready': False, 'status': 'Unknown'}
        else:
            return {'exists': False, 'ready': False, 'status': 'Not Found'}
    
    except Exception as e:
        logger.error(f"Failed to check node status: {str(e)}")
        return {'exists': False, 'ready': False, 'error': str(e)}


@app.route('/add-node', methods=['POST'])
def add_node():
    """
    Add a new worker node to the cluster.
    MODIFIED: No longer updates inventory immediately - worker thread does it.
    """
    data = request.get_json()
    
    if not data or 'hostname' not in data or 'ip' not in data:
        return jsonify({'error': 'Both hostname and ip parameters are required'}), 400
    
    hostname = data['hostname']
    ip = data['ip']
    
    # Create job ID
    job_id = f"{hostname}_{ip}"
    
    # Check if job already exists
    with job_lock:
        if job_id in jobs and jobs[job_id]['status'] in [JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RUNNING]:
            return jsonify({
                'status': 'error',
                'message': f'Job for {hostname} ({ip}) is already in progress',
                'job_id': job_id
            }), 409
    
    # Create job entry - DO NOT update inventory yet
    with job_lock:
        jobs[job_id] = {
            'hostname': hostname,
            'ip': ip,
            'status': JobStatus.QUEUED,
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'message': 'Job queued for processing'
        }
    
    # Add job to queue for serial processing
    # The worker thread will update inventory and run Ansible
    ansible_queue.put((job_id, hostname, ip))
    
    with queue_lock:
        queue_size = ansible_queue.qsize()
        queue_position = queue_size
    
    logger.info(f"Queued job {job_id} to add node {hostname} ({ip}). Queue position: {queue_position}")
    
    return jsonify({
        'status': 'okay',
        'message': f'Node {hostname} ({ip}) queued for addition',
        'job_id': job_id,
        'queue_position': queue_position
    }), 202


@app.route('/remove-node', methods=['DELETE'])
def remove_node():
    """Remove a node from the cluster and inventory"""
    hostname = request.args.get('hostname')
    ip = request.args.get('ip')
    skip_k8s = request.args.get('skip_k8s', 'false').lower() == 'true'
    
    if not hostname:
        return jsonify({'error': 'hostname parameter is required'}), 400
    
    logger.info(f"Received request to remove node {hostname} ({ip})")
    
    # Create job ID for tracking
    job_id = f"remove_{hostname}_{ip or 'unknown'}"
    
    with job_lock:
        jobs[job_id] = {
            'hostname': hostname,
            'ip': ip,
            'operation': 'remove',
            'status': JobStatus.RUNNING,
            'created_at': datetime.now().isoformat(),
            'started_at': datetime.now().isoformat(),
            'message': 'Removing node'
        }
    
    result = {
        'hostname': hostname,
        'ip': ip,
        'kubernetes': {},
        'inventory': False
    }
    
    # Step 1: Remove from Kubernetes (unless skipped)
    if not skip_k8s:
        logger.info(f"Draining and deleting node {hostname} from Kubernetes")
        k8s_result = drain_and_delete_node(hostname)
        result['kubernetes'] = k8s_result
        
        if not k8s_result.get('deleted', False) and k8s_result.get('exists', True):
            logger.warning(f"Failed to delete node {hostname} from Kubernetes, but continuing with inventory removal")
    else:
        logger.info(f"Skipping Kubernetes removal for {hostname}")
        result['kubernetes'] = {'skipped': True}
    
    # Step 2: Remove from inventory
    logger.info(f"Removing node {hostname} from inventory")
    inventory_removed = remove_from_inventory(hostname)
    result['inventory'] = inventory_removed
    
    # Update job status
    with job_lock:
        if inventory_removed:
            jobs[job_id]['status'] = JobStatus.COMPLETED
            jobs[job_id]['message'] = f"Successfully removed node {hostname}"
        else:
            jobs[job_id]['status'] = JobStatus.FAILED
            jobs[job_id]['message'] = f"Failed to remove node {hostname} from inventory"
        
        jobs[job_id]['completed_at'] = datetime.now().isoformat()
        jobs[job_id]['result'] = result
    
    # Determine response
    if inventory_removed:
        logger.info(f"Successfully removed node {hostname}")
        return jsonify({
            'status': 'success',
            'message': f'Node {hostname} removed',
            'job_id': job_id,
            'result': result
        }), 200
    else:
        logger.error(f"Failed to remove node {hostname}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to remove node {hostname}',
            'job_id': job_id,
            'result': result
        }), 500


@app.route('/status', methods=['GET'])
def get_status():
    """Get the status of a node addition job"""
    hostname = request.args.get('hostname')
    ip = request.args.get('ip')
    verbose = request.args.get('verbose', 'false').lower() == 'true'
    
    if not hostname or not ip:
        return jsonify({'error': 'Both hostname and ip parameters are required'}), 400
    
    job_id = f"{hostname}_{ip}"
    
    with job_lock:
        if job_id not in jobs:
            return jsonify({
                'status': 'not_found',
                'message': f'No job found for {hostname} ({ip})'
            }), 404
        
        job_info = jobs[job_id].copy()
    
    # Build response
    response = {
        'job_id': job_id,
        'hostname': job_info['hostname'],
        'ip': job_info['ip'],
        'status': job_info['status'],
        'created_at': job_info['created_at'],
        'started_at': job_info.get('started_at'),
        'completed_at': job_info.get('completed_at'),
        'message': job_info.get('message', ''),
        'node_status': job_info.get('node_status', {})
    }
    
    if job_info.get('ansible_returncode') is not None:
        response['ansible_returncode'] = job_info['ansible_returncode']
    
    # Include ansible logs if verbose=true or if job failed
    if verbose or job_info['status'] == JobStatus.FAILED:
        if job_info.get('ansible_stdout'):
            response['ansible_stdout'] = job_info['ansible_stdout']
        if job_info.get('ansible_stderr'):
            response['ansible_stderr'] = job_info['ansible_stderr']
    
    return jsonify(response), 200


@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs"""
    with job_lock:
        job_list = []
        for job_id, job_info in jobs.items():
            job_list.append({
                'job_id': job_id,
                'hostname': job_info['hostname'],
                'ip': job_info['ip'],
                'status': job_info['status'],
                'created_at': job_info['created_at'],
                'message': job_info.get('message', '')
            })
    
    return jsonify({'jobs': job_list}), 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


@app.route('/logs', methods=['GET'])
def get_logs():
    """Get recent log entries"""
    lines = request.args.get('lines', '100')
    try:
        lines = int(lines)
        if lines < 1 or lines > 10000:
            lines = 100
    except ValueError:
        lines = 100
    
    try:
        if not os.path.exists(LOG_FILE):
            return jsonify({'error': 'Log file not found'}), 404
        
        # Read last N lines from log file
        with open(LOG_FILE, 'r') as f:
            log_lines = f.readlines()
            recent_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
        
        return jsonify({
            'log_file': LOG_FILE,
            'total_lines': len(log_lines),
            'returned_lines': len(recent_lines),
            'logs': ''.join(recent_lines)
        }), 200
    except Exception as e:
        logger.error(f"Failed to read logs: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/queue', methods=['GET'])
def queue_status():
    """Get the current status of the Ansible job queue"""
    with queue_lock:
        queue_size = ansible_queue.qsize()
    
    # Get queued jobs
    queued_jobs = []
    with job_lock:
        for job_id, job_info in jobs.items():
            if job_info['status'] == JobStatus.QUEUED:
                queued_jobs.append({
                    'job_id': job_id,
                    'hostname': job_info['hostname'],
                    'ip': job_info['ip'],
                    'created_at': job_info['created_at'],
                    'message': job_info.get('message', '')
                })
    
    # Sort by creation time (oldest first)
    queued_jobs.sort(key=lambda x: x['created_at'])
    
    return jsonify({
        'queue_size': queue_size,
        'queued_jobs': len(queued_jobs),
        'jobs': queued_jobs
    }), 200


# Start the Ansible worker thread
worker_thread = threading.Thread(target=ansible_worker, daemon=True, name="AnsibleWorker")
worker_thread.start()
logger.info("Started Ansible worker thread for job queue processing")


if __name__ == '__main__':
    # Verify configuration
    if not os.path.exists(KUBESPRAY_DIR):
        logger.error(f"Kubespray directory not found: {KUBESPRAY_DIR}")
        exit(1)
    
    if not os.path.exists(INVENTORY_FILE):
        logger.error(f"Inventory file not found: {INVENTORY_FILE}")
        exit(1)
    
    if not os.path.exists(VENV_ANSIBLE):
        logger.error(f"Ansible venv not found: {VENV_ANSIBLE}")
        exit(1)
    
    if not os.path.exists(SCALE_PLAYBOOK):
        logger.error(f"Scale playbook not found: {SCALE_PLAYBOOK}")
        exit(1)
    
    logger.info("="*60)
    logger.info("Starting Kubespray Scale API Server...")
    logger.info(f"Kubespray directory: {KUBESPRAY_DIR}")
    logger.info(f"Inventory file: {INVENTORY_FILE}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Log rotation: {LOG_MAX_BYTES/1024/1024}MB per file, {LOG_BACKUP_COUNT} backups")
    logger.info("="*60)
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)