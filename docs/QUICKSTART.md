# Quick Start: Kubespray API-Based Autoscaling

This guide walks you through setting up automated node scaling for your Kubespray cluster using the API-based approach.

## Prerequisites

- ✅ Existing Kubespray cluster deployed
- ✅ Bastion server with access to all nodes
- ✅ Terraform configured for Hetzner Cloud
- ✅ Python 3.6+ on bastion server
- ✅ kubectl configured on bastion

## Setup (One-Time)

### 1. Deploy the Scaling API on Bastion

```bash
# SSH to your bastion server
ssh root@91.99.14.172

# Create directory for the API
mkdir -p /opt/kubespray-api
cd /opt/kubespray-api

# Download the files (or copy them)
# - kubespray_scale_api.py
# - requirements.txt

# Install dependencies
pip3 install -r requirements.txt

# Update paths in kubespray_scale_api.py if needed
# Default: KUBESPRAY_DIR = "/root/tf-k8s-cluster-1/kubespray"

# Test the API
python3 kubespray_scale_api.py
```

You should see:
```
Starting Kubespray Scale API Server...
Kubespray directory: /root/tf-k8s-cluster-1/kubespray
Inventory file: /root/tf-k8s-cluster-1/kubespray/inventory/mycluster/hosts.yaml
 * Running on http://0.0.0.0:5000
```

Press Ctrl+C and run it as a service:

```bash
# Create systemd service
cat > /etc/systemd/system/kubespray-api.service <<'EOF'
[Unit]
Description=Kubespray Scale API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/kubespray-api
ExecStart=/usr/bin/python3 /opt/kubespray-api/kubespray_scale_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable kubespray-api
systemctl start kubespray-api

# Check status
systemctl status kubespray-api

# View logs
journalctl -fu kubespray-api
```

### 2. Verify API is Running

```bash
# From bastion or any machine that can reach it
curl http://91.99.14.172:5000/health
```

Expected response:
```json
{"status": "healthy"}
```

### 3. Update Terraform Configuration

Create or update your Terraform files:

**variables.tf**
```hcl
variable "bastion_ip" {
  description = "IP of bastion running the API"
  default     = "91.99.14.172"
}

variable "gateway_ip" {
  description = "Gateway IP for private network"
  default     = "10.10.10.1"
}
```

**workers.tf**
```hcl
data "template_file" "worker_cloudinit" {
  template = file("${path.module}/cloudinit-autoscale-simple.yml.tmpl")
  
  vars = {
    bastion_ip = var.bastion_ip
    gateway_ip = var.gateway_ip
  }
}

resource "hcloud_server" "worker" {
  count       = var.worker_count
  name        = "worker-${count.index + 4}"
  image       = "ubuntu-22.04"
  server_type = "cx21"
  
  user_data = data.template_file.worker_cloudinit.rendered
  
  network {
    network_id = hcloud_network.main.id
    ip         = "10.10.10.${count.index + 24}"
  }
}
```

## Usage

### Add a Single Node Manually

```bash
# Method 1: Direct API call
curl -X POST http://91.99.14.172:5000/add-node \
  -H "Content-Type: application/json" \
  -d '{"hostname": "worker-5", "ip": "10.10.10.25"}'

# Method 2: Using the helper script
./add_node.sh worker-5 10.10.10.25
```

### Add Nodes via Terraform

```bash
# Create new workers
terraform apply -var="worker_count=2"

# Terraform will:
# 1. Create servers with cloud-init
# 2. Servers auto-register with API
# 3. Kubespray adds them to cluster
```

### Check Status

```bash
# Single node
curl "http://91.99.14.172:5000/status?hostname=worker-5&ip=10.10.10.25"

# All jobs
curl http://91.99.14.172:5000/jobs | jq

# Pretty format
curl "http://91.99.14.172:5000/status?hostname=worker-5&ip=10.10.10.25" | jq
```

### Monitor in Real-Time

```bash
# Watch API logs
journalctl -fu kubespray-api

# Watch a specific node registration
watch -n 5 'curl -s "http://91.99.14.172:5000/status?hostname=worker-5&ip=10.10.10.25" | jq'
```

## Example Workflow

### Scenario: Scale from 3 to 5 workers

1. **Update Terraform:**
   ```bash
   # In terraform.tfvars or as variable
   worker_count = 5  # Was 3, now 5
   ```

2. **Apply Changes:**
   ```bash
   terraform plan
   terraform apply
   ```

3. **Monitor Progress:**
   ```bash
   # New servers will be created with IPs:
   # - worker-4: 10.10.10.24
   # - worker-5: 10.10.10.25
   
   # Check their registration
   for i in 4 5; do
     echo "=== worker-$i ==="
     curl -s "http://91.99.14.172:5000/status?hostname=worker-$i&ip=10.10.10.2$i" | jq -r '.status,.message'
   done
   ```

4. **Verify Cluster:**
   ```bash
   kubectl get nodes
   ```
   
   You should see:
   ```
   NAME       STATUS   ROLES           AGE
   master-1   Ready    control-plane   10d
   master-2   Ready    control-plane   10d
   master-3   Ready    control-plane   10d
   worker-1   Ready    <none>          10d
   worker-2   Ready    <none>          10d
   worker-3   Ready    <none>          10d
   worker-4   Ready    <none>          5m    ← New!
   worker-5   Ready    <none>          5m    ← New!
   ```

## Understanding the Flow

```
┌─────────────┐
│   Terraform │
│   applies   │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ Hetzner creates VM  │
│ with cloud-init     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ Cloud-init:                     │
│ 1. Setup network                │
│ 2. Configure SSH                │
│ 3. Call API to register         │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ API receives registration:      │
│ POST /add-node                  │
│ {                               │
│   "hostname": "worker-4",       │
│   "ip": "10.10.10.24"          │
│ }                               │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ API:                            │
│ 1. Updates inventory.yaml       │
│ 2. Runs Ansible in background   │
│    ansible-playbook scale.yml \ │
│      --limit=worker-4           │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ Kubespray:                      │
│ 1. Installs containerd          │
│ 2. Installs kubelet/kubeadm     │
│ 3. Configures networking        │
│ 4. Joins cluster                │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ API verifies with kubectl       │
│ Updates job status: completed   │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────┐
│ ✅ Node is Ready!   │
└─────────────────────┘
```

## Troubleshooting

### Node Not Registering

**Check cloud-init on the node:**
```bash
ssh root@10.10.10.24
journalctl -u cluster-registration.service
```

**Check connectivity:**
```bash
# From the new node
curl http://91.99.14.172:5000/health
```

### Registration Stuck

**Check API logs:**
```bash
journalctl -fu kubespray-api
```

**Check Ansible progress:**
```bash
# The API logs will show the ansible-playbook command
# You can run it manually to see full output
cd /root/tf-k8s-cluster-1/kubespray
.venv/bin/ansible-playbook -i inventory/mycluster/hosts.yaml scale.yml --limit=worker-4 -vvv
```

### Node Not Joining Cluster

**Check job status:**
```bash
curl "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24" | jq
```

**SSH to bastion and check:**
```bash
kubectl get nodes
kubectl get node worker-4 -o yaml
```

## Best Practices

1. **Start Small:** Test with one node before scaling to many
2. **Monitor Logs:** Keep an eye on API logs during scaling
3. **Use Terraform:** Let Terraform handle the infrastructure
4. **Status Checks:** Always verify node status before considering it done
5. **Backup Inventory:** The API modifies inventory.yaml, keep backups

## Security Considerations

⚠️ **For Production:**

1. **Add Authentication:**
   - API currently has no auth
   - Add API keys or OAuth

2. **Use HTTPS:**
   - Run API behind nginx with TLS
   - Use Let's Encrypt certificates

3. **Firewall:**
   - Restrict API access to trusted networks
   - Only allow specific IPs

4. **Audit Logs:**
   - Log all API requests
   - Monitor for unusual activity

## Next Steps

- [ ] Deploy API to bastion
- [ ] Test with single node manually
- [ ] Update Terraform to use new cloud-init
- [ ] Test autoscaling with Terraform
- [ ] Add monitoring/alerting
- [ ] Implement authentication (production)
- [ ] Set up HTTPS (production)

## Resources

- API Documentation: `README.md`
- Comparison: `COMPARISON.md`
- Example Scripts: `add_node.sh`
- Terraform Example: `terraform_example.tf`

## Support

**Check API Health:**
```bash
curl http://91.99.14.172:5000/health
```

**View All Jobs:**
```bash
curl http://91.99.14.172:5000/jobs | jq
```

**Get Job Details:**
```bash
curl "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24" | jq
```

That's it! You now have a simple, reliable autoscaling system for your Kubespray cluster. 🚀
