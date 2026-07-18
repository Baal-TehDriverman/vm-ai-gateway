#!/bin/bash
# Launch the Lilith Gateway web server (venv-aware)
GATEWAY_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$GATEWAY_DIR" || exit 1

VENV_PYTHON="$GATEWAY_DIR/venv/bin/python3"

# Check if already running
if pgrep -f "uvicorn.*gateway_server" > /dev/null; then
    echo "Gateway already running"
    xdg-open "http://localhost:8080" 2>/dev/null || true
    exit 0
fi

# Generate fresh scans
"$VENV_PYTHON" "$GATEWAY_DIR/scan_apps.py" 2>/dev/null || true
"$VENV_PYTHON" "$GATEWAY_DIR/scan_vms.py" 2>/dev/null || true

# Launch server
nohup "$VENV_PYTHON" -m uvicorn gateway_server:app --host 0.0.0.0 --port 8080 > "$GATEWAY_DIR/gateway.log" 2>&1 &
GATEWAY_PID=$!
disown $GATEWAY_PID
sleep 1
echo "Lilith Gateway started (PID $GATEWAY_PID) at http://localhost:8080"
