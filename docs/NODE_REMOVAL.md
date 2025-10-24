# Node Removal Feature

The API now supports removing nodes from the cluster, completing the full lifecycle management for autoscaling.

## What It Does

The removal endpoint performs three operations:

1. **Drains the node** - Safely evicts pods to other nodes
2. **Deletes from Kubernetes** - Removes node from cluster
3. **Updates inventory** - Removes from Kubespray inventory file

All operations include safety checks and automatic inventory backup.

## API Endpoint

**DELETE** `/remove-node`

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| hostname | Yes | - | Node hostname to remove |
| ip | No | - | Node IP for tracking |
| skip_k8s | No | false | Skip Kubernetes operations, only update inventory |

### Examples

**Full removal (recommended):**
```bash
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&ip=10.10.10.24"
```

**Inventory only (node already gone):**
```bash
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&skip_k8s=true"
```

### Response

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
      "deleted": true,
      "drain_output": "...",
      "delete_output": "..."
    },
    "inventory": true
  }
}
```

## Helper Script

Use `remove_node.sh` for interactive removal:

```bash
# Full removal
./remove_node.sh worker-4 10.10.10.24

# Skip Kubernetes (only update inventory)
./remove_node.sh worker-4 10.10.10.24 true
```

The script includes:
- Confirmation prompt
- Progress display
- Result summary
- Verification commands

## Safety Features

### Master Node Protection

Cannot remove nodes in the `kube_control_plane` group:

```python
if hostname in inventory['all']['children']['kube_control_plane']['hosts']:
    return error  # Cannot remove master
```

### Automatic Backup

Inventory is backed up before every modification:

```
/root/tf-k8s-cluster-1/kubespray/inventory/mycluster/hosts.yaml.backup.20251005_120000
```

Backups are timestamped and never overwritten.

### Graceful Drain

Nodes are drained with safe defaults:
- Ignores DaemonSets
- Deletes emptyDir data
- Forces eviction if needed
- 120 second timeout

## Autoscaler Integration

### Scale Down Workflow

When your autoscaler decides to remove a node:

```bash
# 1. Call API to remove from cluster
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-5"

# 2. Wait for confirmation (or check job status)
curl "http://localhost:5000/status?hostname=worker-5"

# 3. Destroy the server
hcloud server delete worker-5
```

### Handling Already-Deleted Nodes

If a node is already destroyed (e.g., spot instance terminated):

```bash
# Use skip_k8s to only clean up inventory
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-5&skip_k8s=true"
```

Or manually delete from Kubernetes first:

```bash
kubectl delete node worker-5
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-5&skip_k8s=true"
```

## Error Handling

### Node Not in Inventory

```json
{
  "status": "success",
  "message": "Node worker-5 removed",
  "result": {
    "inventory": false  // Node wasn't in inventory
  }
}
```

### Node Not in Kubernetes

```json
{
  "result": {
    "kubernetes": {
      "exists": false,
      "drained": false,
      "deleted": false
    },
    "inventory": true
  }
}
```

### Drain Failed

```json
{
  "result": {
    "kubernetes": {
      "exists": true,
      "drained": false,  // Drain failed
      "deleted": true,   // But deletion succeeded
      "drain_output": "error: cannot delete Pods with local storage..."
    }
  }
}
```

The API continues with deletion even if drain fails, which is correct behavior for force-removal scenarios.

## Verification

After removal, verify:

```bash
# Check Kubernetes
kubectl get nodes | grep worker-4
# Should return nothing

# Check inventory
cat ~/tf-k8s-cluster-1/kubespray/inventory/mycluster/hosts.yaml | grep worker-4
# Should return nothing

# Check backup exists
ls -la ~/tf-k8s-cluster-1/kubespray/inventory/mycluster/hosts.yaml.backup.*
# Should show timestamped backups
```

## Troubleshooting

### Node Won't Drain

If pods refuse to evict:

```bash
# Check what's blocking
kubectl describe node worker-4

# Force delete the node (skip drain)
kubectl delete node worker-4 --force --grace-period=0

# Then clean up inventory
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-4&skip_k8s=true"
```

### Inventory Not Updated

Check API logs:

```bash
tail -f /var/log/kubespray-api/kubespray-api.log | grep remove
```

Common issues:
- File permissions on inventory file
- YAML parsing errors
- Node name mismatch

### Master Node Removal Blocked

This is intentional. Master nodes should not be removed via this API. Use proper cluster upgrade/downgrade procedures.

## Best Practices

1. **Always use the API for removal** - Don't manually edit inventory
2. **Check status before destroying server** - Ensure removal completed
3. **Keep backups** - Inventory backups are automatic but verify they exist
4. **Use skip_k8s only when necessary** - Full removal is safer
5. **Monitor drain operations** - Some pods may take time to evict

## Complete Lifecycle Example

```bash
# Add a node
curl -X POST http://localhost:5000/add-node \
  -H "Content-Type: application/json" \
  -d '{"hostname": "worker-5", "ip": "10.10.10.25"}'

# Wait for it to join
watch kubectl get nodes

# Use the node for workloads
# ...

# Remove when scaling down
curl -X DELETE "http://localhost:5000/remove-node?hostname=worker-5&ip=10.10.10.25"

# Verify removal
kubectl get node worker-5
# Error: nodes "worker-5" not found

# Destroy server
hcloud server delete worker-5
```

This completes the full node lifecycle management through the API.
