# Installation Guide

Complete installation guide for the Kubespray Scale API.

## Prerequisites

- ✅ Existing Kubespray cluster deployed
- ✅ Bastion server with access to all nodes
- ✅ Root access to bastion server
- ✅ Python 3.6+ installed
- ✅ kubectl configured on bastion

## Method 1: Automated Installation (Recommended)

### Download Files

Transfer these files to your bastion server:
- `kubespray_scale_api.py`
- `requirements.txt`
- `kubespray-api.service`
- `install.sh`

### Run Installation Script

```bash
# Make install script executable
chmod +x install.sh

# Run installation
sudo ./install.sh
```

The script will:
1. ✅ Check prerequisites
2. ✅ Create directories (`/opt/kubespray-api`, `/var/log/kubespray-api`)
3. ✅ Install Python dependencies
4. ✅ Copy API files
5. ✅ Install systemd service
6. ✅ Start the service

### Verify Installation

```bash
# Check service status
systemctl status kubespray-api

# Test API
curl http://localhost:5000/health

# View logs
journalctl -fu kubespray-api
```

## Method 2: Manual Installation

### Step 1: Create Directories

```bash
sudo mkdir -p /opt/kubespray-api
sudo mkdir -p /var/log/kubespray-api
```

### Step 2: Copy Files

```bash
# Copy API files
sudo cp kubespray_scale_api.py /opt/kubespray-api/
sudo cp requirements.txt /opt/kubespray-api/

# Make executable
sudo chmod +x /opt/kubespray-api/kubespray_scale_api.py
```

### Step 3: Update Configuration

Edit the API script if your Kubespray path is different:

```bash
sudo nano /opt/kubespray-api/kubespray_scale_api.py
```

Update these lines if needed:
```python
KUBESPRAY_DIR = "/root/tf-k8s-cluster-1/kubespray"  # Your path here
```

### Step 4: Install Dependencies

```bash
cd /opt/kubespray-api
sudo pip3 install -r requirements.txt
```

### Step 5: Install Systemd Service

```bash
# Copy service file
sudo cp kubespray-api.service /etc/systemd/system/

# Or create it manually
sudo cat > /etc/systemd/system/kubespray-api.service <<'EOF'
[Unit]
Description=Kubespray Scale API Server
Documentation=https://github.com/your-repo/kubespray-scale-api
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/kubespray-api
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /opt/kubespray-api/kubespray_scale_api.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kubespray-api
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload
```

### Step 6: Start Service

```bash
# Enable service to start on boot
sudo systemctl enable kubespray-api

# Start the service
sudo systemctl start kubespray-api

# Check status
sudo systemctl status kubespray-api
```

### Step 7: Verify Installation

```bash
# Test health endpoint
curl http://localhost:5000/health

# Should return: {"status": "healthy"}

# Check logs
sudo tail -f /var/log/kubespray-api/kubespray-api.log

# Or via journalctl
sudo journalctl -fu kubespray-api
```

## Post-Installation

### Configure Firewall (if needed)

```bash
# Allow API port (if using ufw)
sudo ufw allow 5000/tcp

# Or for firewalld
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

### Test from Remote Machine

```bash
# From another machine
curl http://YOUR_BASTION_IP:5000/health
```

### Copy Helper Scripts

```bash
# Copy helper scripts to a convenient location
sudo cp view_logs.sh /usr/local/bin/kubespray-logs
sudo cp add_node.sh /usr/local/bin/kubespray-add-node

# Make executable
sudo chmod +x /usr/local/bin/kubespray-logs
sudo chmod +x /usr/local/bin/kubespray-add-node

# Now you can use them from anywhere
kubespray-logs
kubespray-add-node worker-5 10.10.10.25
```

## Service Management

### Start/Stop/Restart

```bash
# Start
sudo systemctl start kubespray-api

# Stop
sudo systemctl stop kubespray-api

# Restart
sudo systemctl restart kubespray-api

# Reload (after config changes)
sudo systemctl reload kubespray-api
```

### View Status

```bash
# Service status
sudo systemctl status kubespray-api

# Is it running?
sudo systemctl is-active kubespray-api

# Is it enabled?
sudo systemctl is-enabled kubespray-api
```

### View Logs

```bash
# Follow service logs (systemd journal)
sudo journalctl -fu kubespray-api

# Recent logs
sudo journalctl -u kubespray-api --since "10 minutes ago"

# Application logs (rotating file)
sudo tail -f /var/log/kubespray-api/kubespray-api.log

# Via API
curl http://localhost:5000/logs | jq -r '.logs'

# Using helper script
./view_logs.sh
```

### Auto-start on Boot

```bash
# Enable
sudo systemctl enable kubespray-api

# Disable
sudo systemctl disable kubespray-api
```

## Updating the API

### Update to New Version

```bash
# Stop service
sudo systemctl stop kubespray-api

# Backup current version
sudo cp /opt/kubespray-api/kubespray_scale_api.py /opt/kubespray-api/kubespray_scale_api.py.backup

# Copy new version
sudo cp kubespray_scale_api.py /opt/kubespray-api/

# Update dependencies if needed
cd /opt/kubespray-api
sudo pip3 install -r requirements.txt --upgrade

# Restart service
sudo systemctl start kubespray-api

# Verify
sudo systemctl status kubespray-api
```

### Rollback

```bash
# Stop service
sudo systemctl stop kubespray-api

# Restore backup
sudo cp /opt/kubespray-api/kubespray_scale_api.py.backup /opt/kubespray-api/kubespray_scale_api.py

# Restart
sudo systemctl start kubespray-api
```

## Troubleshooting

### Service Won't Start

```bash
# Check for errors
sudo journalctl -u kubespray-api -n 50

# Check file permissions
ls -la /opt/kubespray-api/

# Check Python dependencies
pip3 list | grep -E "Flask|PyYAML"

# Verify Kubespray path exists
ls -la /root/tf-k8s-cluster-1/kubespray/
```

### Port Already in Use

```bash
# Check what's using port 5000
sudo lsof -i :5000

# Or
sudo netstat -tulpn | grep :5000

# Change port in kubespray_scale_api.py if needed
sudo nano /opt/kubespray-api/kubespray_scale_api.py
# Change: app.run(host='0.0.0.0', port=5000, debug=False)
```

### Permission Errors

```bash
# Ensure log directory is writable
sudo chmod 755 /var/log/kubespray-api

# Ensure API files are readable
sudo chmod 644 /opt/kubespray-api/kubespray_scale_api.py
sudo chmod 644 /opt/kubespray-api/requirements.txt
```

### API Not Accessible Remotely

```bash
# Check if listening on all interfaces
sudo netstat -tulpn | grep :5000
# Should show 0.0.0.0:5000

# Check firewall
sudo iptables -L -n | grep 5000
# Or
sudo ufw status | grep 5000

# Test locally first
curl http://localhost:5000/health

# Then test from remote
curl http://BASTION_IP:5000/health
```

## Uninstallation

### Automated Uninstall

```bash
chmod +x uninstall.sh
sudo ./uninstall.sh
```

### Manual Uninstall

```bash
# Stop and disable service
sudo systemctl stop kubespray-api
sudo systemctl disable kubespray-api

# Remove service file
sudo rm /etc/systemd/system/kubespray-api.service
sudo systemctl daemon-reload

# Remove files
sudo rm -rf /opt/kubespray-api
sudo rm -rf /var/log/kubespray-api

# Remove Python packages (optional)
sudo pip3 uninstall Flask PyYAML
```

## File Locations Reference

| Item | Location |
|------|----------|
| API Script | `/opt/kubespray-api/kubespray_scale_api.py` |
| Dependencies | `/opt/kubespray-api/requirements.txt` |
| Service File | `/etc/systemd/system/kubespray-api.service` |
| Main Log | `/var/log/kubespray-api/kubespray-api.log` |
| Rotated Logs | `/var/log/kubespray-api/kubespray-api.log.[1-5]` |
| Kubespray Dir | `/root/tf-k8s-cluster-1/kubespray` (configurable) |

## Security Considerations

### For Production:

1. **Add Authentication**
   - Implement API key authentication
   - Use OAuth or JWT tokens

2. **Use HTTPS**
   - Run behind nginx/apache with TLS
   - Use Let's Encrypt certificates

3. **Restrict Access**
   - Firewall rules to specific IPs
   - VPN or private network only

4. **Run as Non-Root** (optional)
   ```bash
   # Create dedicated user
   sudo useradd -r -s /bin/false kubespray-api
   
   # Update service file
   User=kubespray-api
   Group=kubespray-api
   
   # Fix permissions
   sudo chown -R kubespray-api:kubespray-api /opt/kubespray-api
   sudo chown -R kubespray-api:kubespray-api /var/log/kubespray-api
   ```

5. **Rate Limiting**
   - Implement rate limiting for API endpoints
   - Use nginx rate limiting if behind proxy

## Next Steps

After installation:

1. ✅ Test the API: `curl http://localhost:5000/health`
2. ✅ Add a test node: `./add_node.sh worker-test 10.10.10.100`
3. ✅ Check logs: `./view_logs.sh`
4. ✅ Update Terraform to use the new cloud-init template
5. ✅ Set up monitoring/alerting
6. ✅ Implement authentication for production

## Support

- Installation issues: Check `journalctl -u kubespray-api`
- API errors: Check `/var/log/kubespray-api/kubespray-api.log`
- Ansible errors: Use `verbose=true` parameter in status endpoint
- General help: See [README.md](README.md) and [QUICKSTART.md](QUICKSTART.md)
