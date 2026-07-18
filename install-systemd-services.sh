#!/bin/bash
# install-systemd-services.sh
# Install and enable systemd services for Lilith Gateway and Windows Port Console
# Run with: sudo ./install-systemd-services.sh

set -euo pipefail

GATEWAY_SERVICE="/home/tehlappy/vm-ai-gateway/lilith-gateway/lilith-gateway.service"
CONSOLE_SERVICE="/home/tehlappy/vm-ai-gateway/windows-port-console/windows-port-console.service"

SYSTEMD_DIR="/etc/systemd/system"

echo "=== Installing systemd services ==="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Copy service files
echo "Copying service files to $SYSTEMD_DIR..."
cp "$GATEWAY_SERVICE" "$SYSTEMD_DIR/lilith-gateway.service"
cp "$CONSOLE_SERVICE" "$SYSTEMD_DIR/windows-port-console.service"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable services
echo "Enabling services for auto-start on boot..."
systemctl enable lilith-gateway.service
systemctl enable windows-port-console.service

echo ""
echo "=== Installation complete ==="
echo ""
echo "To start services now:"
echo "  sudo systemctl start lilith-gateway"
echo "  sudo systemctl start windows-port-console"
echo ""
echo "To check status:"
echo "  sudo systemctl status lilith-gateway"
echo "  sudo systemctl status windows-port-console"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u lilith-gateway -f"
echo "  sudo journalctl -u windows-port-console -f"
echo ""
echo "Services will auto-start on next boot."