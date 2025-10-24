#!/bin/bash
# Uninstallation script for Kubespray Scale API

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

confirm() {
    read -p "Are you sure you want to uninstall Kubespray Scale API? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Uninstallation cancelled"
        exit 0
    fi
}

stop_service() {
    if systemctl is-active --quiet kubespray-api; then
        print_info "Stopping kubespray-api service..."
        systemctl stop kubespray-api
    fi
    
    if systemctl is-enabled --quiet kubespray-api; then
        print_info "Disabling kubespray-api service..."
        systemctl disable kubespray-api
    fi
}

remove_service() {
    if [ -f "$SERVICE_FILE" ]; then
        print_info "Removing systemd service file..."
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        print_info "Removed: $SERVICE_FILE"
    fi
}

remove_files() {
    print_warn "This will remove the following:"
    echo "  - $INSTALL_DIR (API files)"
    echo "  - $LOG_DIR (log files)"
    echo
    
    read -p "Do you want to remove these directories? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -d "$INSTALL_DIR" ]; then
            print_info "Removing: $INSTALL_DIR"
            rm -rf "$INSTALL_DIR"
        fi
        
        if [ -d "$LOG_DIR" ]; then
            print_info "Removing: $LOG_DIR"
            rm -rf "$LOG_DIR"
        fi
        print_info "Files removed"
    else
        print_info "Keeping installation files"
    fi
}

remove_dependencies() {
    read -p "Do you want to remove Python dependencies? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Removing Python packages..."
        pip3 uninstall -y Flask PyYAML 2>/dev/null || true
        print_info "Dependencies removed"
    else
        print_info "Keeping Python dependencies"
    fi
}

show_status() {
    echo
    print_info "Uninstallation complete!"
    echo
    
    if [ -d "$INSTALL_DIR" ] || [ -d "$LOG_DIR" ] || [ -f "$SERVICE_FILE" ]; then
        print_warn "Some files may still remain:"
        [ -d "$INSTALL_DIR" ] && echo "  - $INSTALL_DIR"
        [ -d "$LOG_DIR" ] && echo "  - $LOG_DIR"
        [ -f "$SERVICE_FILE" ] && echo "  - $SERVICE_FILE"
    else
        print_info "All components removed successfully"
    fi
}

# Main uninstallation
main() {
    echo "=========================================="
    echo "  Kubespray Scale API Uninstallation"
    echo "=========================================="
    echo
    
    check_root
    confirm
    stop_service
    remove_service
    remove_files
    remove_dependencies
    show_status
}

# Run uninstallation
main
