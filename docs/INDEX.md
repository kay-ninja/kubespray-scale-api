# Kubespray API-Based Autoscaling - Complete Package

This package contains everything you need to implement API-based autoscaling for your Kubespray cluster.

## 📦 Package Contents

### Core Components

1. **kubespray_scale_api.py** - Main API server
   - Flask-based REST API
   - Handles node registration
   - Runs Ansible playbooks in background
   - Tracks job status
   - Verifies nodes with kubectl
   - Rotating file logs (10MB per file, 5 backups)

2. **requirements.txt** - Python dependencies
   - Flask==3.0.0
   - PyYAML==6.0.1

3. **kubespray-api.service** - Systemd service file
   - Auto-start on boot
   - Automatic restart on failure
   - Proper logging configuration

4. **cloudinit-autoscale-simple.yml.tmpl** - New simplified cloud-init template
   - ~150 lines (vs 400+ in original)
   - Sets up networking and SSH only
   - Calls API to register node
   - Monitors registration status
   - Template variables: `${bastion_ip}`, `${gateway_ip}`

### Documentation

4. **INSTALL.md** - Complete installation guide
   - Automated installation script
   - Manual installation steps
   - Service management
   - Troubleshooting
   - Security considerations

5. **README.md** - API Documentation
   - Installation instructions
   - API endpoints reference
   - Usage examples
   - Logging documentation
   - Troubleshooting guide

6. **QUICKSTART.md** - Step-by-step setup guide
   - Complete deployment walkthrough
   - Example workflows
   - Architecture diagrams
   - Best practices

7. **COMPARISON.md** - Old vs New approach
   - Feature comparison
   - Benefits analysis
   - Migration guide
   - Architecture comparison

8. **LOGGING.md** - Logging documentation
   - Log locations and rotation
   - Multiple ways to view logs
   - API log endpoint usage
   - Debugging techniques

### Installation & Tools

9. **install.sh** - Automated installation script
   - One-command installation
   - Checks prerequisites
   - Installs and configures everything
   - Sets up systemd service

10. **uninstall.sh** - Uninstallation script
    - Clean removal of all components
    - Optional file cleanup
    - Service removal

11. **kubespray-api.service** - Systemd service file
    - Production-ready configuration
    - Auto-restart on failure
    - Proper logging setup

### Examples & Tools

12. **terraform_example.tf** - Terraform configuration example
    - Shows how to use the cloud-init template
    - Includes bastion_ip variable passing
    - Node creation example
    - Status checking outputs

13. **add_node.sh** - Helper script for manual node addition
    - Interactive script to add nodes
    - Monitors registration progress
    - Shows final status

14. **view_logs.sh** - Log viewing helper script
    - View recent logs via API
    - Follow logs in real-time
    - Filter for errors/warnings
    - Multiple display options

## 🚀 Quick Start (2 Minutes)

### 1. Deploy API on Bastion (Automated)
```bash
# On bastion server (91.99.14.172)
chmod +x install.sh
sudo ./install.sh
```

The installation script will:
- ✅ Install dependencies
- ✅ Create directories
- ✅ Set up systemd service
- ✅ Start the API

**Or install manually:**
```bash
sudo mkdir -p /opt/kubespray-api /var/log/kubespray-api
sudo cp kubespray_scale_api.py requirements.txt /opt/kubespray-api/
sudo cp kubespray-api.service /etc/systemd/system/
sudo pip3 install -r /opt/kubespray-api/requirements.txt
sudo systemctl enable --now kubespray-api
```

### 2. Update Terraform
```hcl
# Use the new cloud-init template
data "template_file" "worker_cloudinit" {
  template = file("cloudinit-autoscale-simple.yml.tmpl")
  vars = {
    bastion_ip = "91.99.14.172"
    gateway_ip = "10.10.10.1"
  }
}
```

### 3. Deploy Nodes
```bash
terraform apply
```

That's it! Nodes will auto-register and join the cluster.

## 📊 How It Works

```
New Node → Cloud-init → API Call → Inventory Update → Ansible → Node Joins
```

**Old way (400+ lines):**
- Node installs everything itself
- Runs kubeadm join directly
- Hope it works

**New way (~150 lines):**
- Node sets up basics
- Calls API: "I'm worker-4 at 10.10.10.24"
- Kubespray handles the rest
- Guaranteed consistency

## 📁 File Usage Guide

| File | Where to Use | Purpose |
|------|--------------|---------|
| `install.sh` | Bastion server | Automated installation (recommended) |
| `kubespray_scale_api.py` | Bastion server | API server that orchestrates node addition |
| `requirements.txt` | Bastion server | Install Python dependencies |
| `kubespray-api.service` | Bastion server | Systemd service configuration |
| `cloudinit-autoscale-simple.yml.tmpl` | Terraform | Template for new nodes |
| `terraform_example.tf` | Terraform project | Reference configuration |
| `add_node.sh` | Anywhere | Manual node addition tool |
| `view_logs.sh` | Anywhere | View API logs easily |
| `uninstall.sh` | Bastion server | Clean uninstallation |
| `INSTALL.md` | Read first | Complete installation guide |
| `README.md` | Reference | API documentation |
| `QUICKSTART.md` | Follow along | Setup guide |
| `LOGGING.md` | Reference | Logging documentation |
| `COMPARISON.md` | Read | Understand benefits |

## 🔧 Key Features

✅ **Simple** - Minimal cloud-init configuration
✅ **Reliable** - Uses proven Kubespray playbooks
✅ **Trackable** - Full job status and history via API
✅ **Automated** - Zero manual intervention needed
✅ **Consistent** - Same setup as manual node addition
✅ **Debuggable** - Centralized logging on bastion

## 📋 API Endpoints

- `POST /add-node` - Register a new worker
- `GET /status` - Check registration status
- `GET /jobs` - List all jobs
- `GET /health` - API health check

## 🛠️ Common Tasks

### Add a node manually:
```bash
curl -X POST http://91.99.14.172:5000/add-node \
  -H "Content-Type: application/json" \
  -d '{"hostname": "worker-4", "ip": "10.10.10.24"}'
```

### Check status:
```bash
curl "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24"
```

### Use helper script:
```bash
./add_node.sh worker-4 10.10.10.24
```

## 📖 Next Steps

1. **Read**: Start with `QUICKSTART.md`
2. **Deploy**: Follow the setup instructions
3. **Test**: Add one node manually first
4. **Automate**: Update Terraform to use new template
5. **Scale**: Let it handle your autoscaling

## 🔐 Security Notes

**Current Implementation:**
- No authentication (development/testing)
- HTTP only
- Suitable for private networks

**For Production:**
- Add API authentication
- Use HTTPS/TLS
- Implement rate limiting
- Add firewall rules

## 💡 Benefits Over Original

| Aspect | Original | New API-Based |
|--------|----------|---------------|
| Cloud-init lines | 400+ | ~150 |
| Complexity | High | Low |
| Maintenance | Hard | Easy |
| Debugging | Difficult | Centralized |
| Reliability | Variable | High |
| Visibility | Limited | Full API |

## 🆘 Support

**API not working?**
```bash
systemctl status kubespray-api
journalctl -fu kubespray-api
```

**Node not registering?**
```bash
ssh root@<node-ip>
journalctl -u cluster-registration.service
```

**Need help?**
- Check `README.md` for detailed API docs
- See `QUICKSTART.md` for troubleshooting
- Review `COMPARISON.md` for architecture details

## 📝 Summary

This package transforms your Kubespray autoscaling from a complex, brittle cloud-init process into a simple, reliable API-based system. The new approach:

- **Simplifies** node provisioning to a single API call
- **Centralizes** all scaling logic on the bastion
- **Leverages** Kubespray's proven playbooks
- **Provides** full visibility and tracking
- **Reduces** maintenance burden significantly

Your genius idea to use the API instead of complex cloud-init was spot on! 🎯

---

**Ready to get started?** → Read `QUICKSTART.md`

**Want to understand the architecture?** → Read `COMPARISON.md`

**Need API reference?** → Read `README.md`

**Quick test?** → Use `add_node.sh`
