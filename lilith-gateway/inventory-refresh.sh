#!/bin/bash
GATEWAY_DIR="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/python3 "$GATEWAY_DIR/scan_apps.py" 2>/dev/null
/usr/bin/python3 "$GATEWAY_DIR/scan_vms.py" 2>/dev/null
echo "Inventory refreshed at $(date)"
