#!/bin/bash
# Installation script for Kubespray Scale API

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/kubespray-api"
LOG_DIR="/var/log/kubespray-api"
SERVICE_FILE="/etc/systemd/system/kubespray-api.service"
KUBESPRAY_DIR="/root/tf-k8s-cluster-1/kubespray"

# Functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "Please run as root"
        exit 1
    fi
}

check_kubespray() {
    if [ ! -d "$KUBESPRAY_DIR" ]; then
        print_error "Kubespray directory not found: $KUBESPRAY_DIR"
        print_warn "Please update KUBESPRAY_DIR in this script or in kubespray_scale_api.py"
        exit 1
    fi
    
    if [ ! -f "$KUBESPRAY_DIR/scale.yml" ]; then
        print_error "scale.yml not found in Kubespray directory"
        exit 1
    fi
    
    print_info "Found Kubespray at: $KUBESPRAY_DIR"
}

install_dependencies() {
    print_info "Installing Python dependencies..."
    
    if ! command -v pip3 &> /dev/null; then
        print_info "Installing pip3..."
        apt-get update
        apt-get install -y python3-pip
    fi
    
    pip3 install -r "$INSTALL_DIR/requirements.txt"
}

create_directories() {
    print_info "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$LOG_DIR"
    
    print_info "Created: $INSTALL_DIR"
    print_info "Created: $LOG_DIR"
}

copy_files() {
    print_info "Copying API files..."
    
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    
    if [ -f "$SCRIPT_DIR/kubespray_scale_api.py" ]; then
        cp "$SCRIPT_DIR/kubespray_scale_api.py" "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/kubespray_scale_api.py"
        print_info "Copied: kubespray_scale_api.py"
    else
        print_error "kubespray_scale_api.py not found in current directory"
        exit 1
    fi
    
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
        print_info "Copied: requirements.txt"
    else
        print_error "requirements.txt not found in current directory"
        exit 1
    fi
}

install_service() {
    print_info "Installing systemd service..."
    
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    
    if [ -f "$SCRIPT_DIR/kubespray-api.service" ]; then
        cp "$SCRIPT_DIR/kubespray-api.service" "$SERVICE_FILE"
        print_info "Copied: $SERVICE_FILE"
    else
        print_warn "kubespray-api.service not found, creating it..."
        cat > "$SERVICE_FILE" <<'EOF'
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
    fi
    
    systemctl daemon-reload
    print_info "Systemd daemon reloaded"
}

start_service() {
    print_info "Enabling and starting kubespray-api service..."
    
    systemctl enable kubespray-api
    systemctl start kubespray-api
    
    sleep 2
    
    if systemctl is-active --quiet kubespray-api; then
        print_info "Service started successfully!"
    else
        print_error "Service failed to start. Check logs with: journalctl -u kubespray-api -n 50"
        exit 1
    fi
}

show_status() {
    echo
    print_info "Installation complete!"
    echo
    echo "Service status:"
    systemctl status kubespray-api --no-pager -l
    echo
    echo "Commands:"
    echo "  Start:   systemctl start kubespray-api"
    echo "  Stop:    systemctl stop kubespray-api"
    echo "  Restart: systemctl restart kubespray-api"
    echo "  Status:  systemctl status kubespray-api"
    echo "  Logs:    journalctl -fu kubespray-api"
    echo "  API Log: tail -f $LOG_DIR/kubespray-api.log"
    echo
    echo "API Endpoints:"
    echo "  Health:  curl http://localhost:5000/health"
    echo "  Logs:    curl http://localhost:5000/logs"
    echo "  Jobs:    curl http://localhost:5000/jobs"
    echo
    print_info "API is running on http://0.0.0.0:5000"
}

# Main installation
main() {
    echo "======================================"
    echo "  Kubespray Scale API Installation"
    echo "======================================"
    echo
    
    check_root
    check_kubespray
    create_directories
    copy_files
    install_dependencies
    install_service
    start_service
    show_status
}

# Run installation
main
