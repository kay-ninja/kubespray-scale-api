# Kubespray Scale API Server

A Flask-based REST API server to manage scaling Kubernetes clusters deployed with Kubespray.

## Features

- Add worker nodes to your cluster via REST API
- Automatic inventory file updates
- Background Ansible playbook execution
- Job status tracking
- Node verification using kubectl
- **Rotating file logs** - Automatic log rotation (10MB per file, 5 backups)
- **Log API endpoint** - Retrieve logs via REST API
- **Detailed error tracking** - Full Ansible output captured for debugging

## Installation

1. Install dependencies:
```bash
pip3 install -r requirements.txt
```

2. Make the script executable:
```bash
chmod +x kubespray_scale_api.py
```

3. Update the configuration in the script if your paths differ:
```python
KUBESPRAY_DIR = "/root/tf-k8s-cluster-1/kubespray"
INVENTORY_FILE = f"{KUBESPRAY_DIR}/inventory/mycluster/hosts.yaml"
```

## Running the Server

```bash
python3 kubespray_scale_api.py
```

Or run it in the background:
```bash
nohup python3 kubespray_scale_api.py > kubespray_api.log 2>&1 &
```

The server runs on `http://0.0.0.0:5000`

## API Endpoints

### 1. Add a New Worker Node

**POST** `/add-node`

Add a new worker node to the cluster.

**Request:**
```bash
curl -X POST http://localhost:5000/add-node \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "worker-4",
    "ip": "10.10.10.24"
  }'
```

**Response:**
```json
{
  "status": "okay",
  "message": "Started adding node worker-4 (10.10.10.24)",
  "job_id": "worker-4_10.10.10.24"
}
```

### 2. Remove a Node

**DELETE** `/remove-node?hostname=<hostname>&ip=<ip>&skip_k8s=<true|false>`

Remove a node from the cluster and inventory.

**Parameters:**
- `hostname` (required): Node hostname to remove
- `ip` (optional): Node IP for tracking
- `skip_k8s` (optional): Skip Kubernetes removal, only update inventory (default: false)

**Request:**
```bash
# Full removal (drain, delete from k8s, remove from inventory)
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&ip=10.10.10.24"

# Only remove from inventory (node already deleted from k8s)
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&skip_k8s=true"
```

**Response:**
```json
{
  "status": "success",
  "message": "Node worker-4 removed",
  "job_id": "remove_worker-4_10.10.10.24",
  "result": {
    "hostname": "worker-4",
    "ip": "10.10.10.24",
    "kubernetes": {
      "exists": true,
      "drained": true,
      "deleted": true
    },
    "inventory": true
  }
}
```

**Safety Features:**
- Cannot remove master/control plane nodes
- Automatically backs up inventory before removal
- Drains node before deletion to safely migrate pods
- Returns detailed status of each operation

### 3. Check Job Status

**GET** `/status?hostname=<hostname>&ip=<ip>`

Check the status of a node addition job.

**Request:**
```bash
curl "http://localhost:5000/status?hostname=worker-4&ip=10.10.10.24"
```

**Response (Running):**
```json
{
  "job_id": "worker-4_10.10.10.24",
  "hostname": "worker-4",
  "ip": "10.10.10.24",
  "status": "running",
  "created_at": "2025-10-05T10:30:00",
  "started_at": "2025-10-05T10:30:05",
  "completed_at": null,
  "message": "Job queued",
  "node_status": {}
}
```

**Response (Completed):**
```json
{
  "job_id": "worker-4_10.10.10.24",
  "hostname": "worker-4",
  "ip": "10.10.10.24",
  "status": "completed",
  "created_at": "2025-10-05T10:30:00",
  "started_at": "2025-10-05T10:30:05",
  "completed_at": "2025-10-05T10:35:30",
  "message": "Worker node worker-4 has successfully joined the cluster",
  "node_status": {
    "exists": true,
    "ready": true,
    "status": "True",
    "reason": ""
  },
  "ansible_returncode": 0
}
```

### 3. List All Jobs

**GET** `/jobs`

List all node addition jobs.

**Request:**
```bash
curl http://localhost:5000/jobs
```

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "worker-4_10.10.10.24",
      "hostname": "worker-4",
      "ip": "10.10.10.24",
      "status": "completed",
      "created_at": "2025-10-05T10:30:00",
      "message": "Worker node worker-4 has successfully joined the cluster"
    }
  ]
}
```

### 4. Health Check

**GET** `/health`

Check if the API server is running.

**Request:**
```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy"
}
```

### 5. Get Logs

**GET** `/logs?lines=<number>`

Retrieve recent log entries from the API server.

**Request:**
```bash
# Get last 100 lines (default)
curl http://localhost:5000/logs

# Get last 500 lines
curl http://localhost:5000/logs?lines=500

# Pretty format
curl -s http://localhost:5000/logs | jq -r '.logs'
```

**Response:**
```json
{
  "log_file": "/var/log/kubespray-api/kubespray-api.log",
  "total_lines": 1234,
  "returned_lines": 100,
  "logs": "2025-10-05 11:00:00 - INFO - Starting API...\n..."
}
```

## Logging

The API uses rotating file logs:

**Log location:** `/var/log/kubespray-api/kubespray-api.log`

**View logs:**
```bash
# Direct access (on bastion)
tail -f /var/log/kubespray-api/kubespray-api.log

# Via API (from anywhere)
curl -s "http://localhost:5000/logs?lines=200" | jq -r '.logs'

# Using helper script
./view_logs.sh         # Last 100 lines
./view_logs.sh 500     # Last 500 lines  
./view_logs.sh -f      # Follow logs
./view_logs.sh -e      # Show only errors
```

**Log rotation:**
- Max file size: 10MB
- Backup count: 5 files
- Total storage: ~50MB

See [LOGGING.md](LOGGING.md) for detailed logging documentation.

## Job Status Values

- `pending` - Job is queued but not yet started
- `running` - Ansible playbook is currently executing
- `completed` - Node successfully added and verified in cluster
- `failed` - Job failed (check message for details)

## Example Workflow

1. Add a new node:
```bash
curl -X POST http://localhost:5000/add-node \
  -H "Content-Type: application/json" \
  -d '{"hostname": "worker-4", "ip": "10.10.10.24"}'
```

2. Check status periodically:
```bash
# Check every 30 seconds
while true; do
  curl "http://localhost:5000/status?hostname=worker-4&ip=10.10.10.24"
  sleep 30
done
```

3. Remove a node when scaling down:
```bash
# Full removal (drain + delete from k8s + remove from inventory)
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&ip=10.10.10.24"
```

4. Or use helper scripts:
```bash
# Add a node
./add_node.sh worker-4 10.10.10.24

# Remove a node
./remove_node.sh worker-4 10.10.10.24
```

## Autoscaler Integration

For autoscaler integration, call the API when scaling:

**Scale Up:**
```bash
# 1. Create server with cloud-init (automated)
hcloud server create --name worker-5 --user-data-from-file cloud-init.yaml

# 2. Node automatically registers via cloud-init
# 3. API adds to inventory and runs Ansible
# 4. Node joins cluster
```

**Scale Down:**
```bash
# 1. Remove from cluster and inventory
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-5"

# 2. Destroy server
hcloud server delete worker-5
```

## Prerequisites

- Kubespray cluster already deployed
- kubectl configured and accessible
- SSH access to new nodes from the bastion/control plane
- Python 3.6+
- Flask and PyYAML installed

## Troubleshooting

### Check API Logs

```bash
# View recent logs via API
curl -s "http://localhost:5000/logs?lines=200" | jq -r '.logs'

# View logs on bastion
tail -f /var/log/kubespray-api/kubespray-api.log

# Search for errors
curl -s "http://localhost:5000/logs?lines=500" | jq -r '.logs' | grep ERROR

# Or on bastion
grep ERROR /var/log/kubespray-api/kubespray-api.log
```

### Get Full Job Details (Including Ansible Logs)

```bash
# Failed jobs automatically include ansible output
curl -s "http://localhost:5000/status?hostname=worker-4&ip=10.10.10.24" | jq

# Force verbose output
curl -s "http://localhost:5000/status?hostname=worker-4&ip=10.10.10.24&verbose=true" | jq

# Extract just the ansible errors
curl -s "http://localhost:5000/status?hostname=worker-4&ip=10.10.10.24&verbose=true" | jq -r '.ansible_stderr'
```

### Common Issues

- Check the log output: `./view_logs.sh -e` (shows only errors)
- Verify paths in the script match your setup
- Ensure the API server has permissions to modify the inventory file
- Make sure kubectl is in the PATH and configured correctly

## Security Notes

This is a basic implementation. For production use, consider adding:
- Authentication/Authorization
- HTTPS/TLS
- Input validation and sanitization
- Rate limiting
- Persistent job storage (database)
