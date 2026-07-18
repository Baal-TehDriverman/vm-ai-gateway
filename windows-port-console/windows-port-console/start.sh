#!/usr/bin/env bash
# Start the Windows Port Console Dashboard
# Usage: ./start.sh          # start in background
#        ./start.sh --open   # start and open browser
#        ./start.sh --stop   # stop the server

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/server.log"
PORT=8081

# Create shared directory if needed
mkdir -p "$HOME/Desktop/cross-compile"

stop_server() {
    echo "Stopping Windows Port Console..."
    pkill -f "server.py" 2>/dev/null || true
    sleep 1
    if pgrep -f "server.py" >/dev/null 2>&1; then
        echo "Force stopping..."
        pkill -9 -f "server.py" 2>/dev/null || true
    fi
    echo "Stopped."
    exit 0
}

start_server() {
    echo "Starting Windows Port Console..."
    echo "  Dashboard: http://localhost:$PORT"
    echo "  Log: $LOG"
    echo ""

    # Start with daemon-like persistence
    cd "$DIR"
    nohup "$DIR/venv/bin/python3" -u server.py > "$LOG" 2>&1 &
    PID=$!
    disown "$PID" 2>/dev/null || true

    # Wait and check
    sleep 3
    if kill -0 "$PID" 2>/dev/null; then
        echo "✅ Server running (PID: $PID)"
        echo "   Open: http://localhost:$PORT"
        return 0
    else
        echo "❌ Server failed to start. Check log: $LOG"
        tail -5 "$LOG"
        return 1
    fi
}

case "${1:-start}" in
    start|--start)
        start_server
        ;;
    stop|--stop|-k)
        stop_server
        ;;
    restart|--restart)
        stop_server
        sleep 1
        start_server
        ;;
    --open)
        start_server
        if command -v xdg-open &>/dev/null; then
            xdg-open "http://localhost:$PORT"
        elif command -v open &>/dev/null; then
            open "http://localhost:$PORT"
        fi
        ;;
    status|--status)
        if pgrep -f "server.py" >/dev/null 2>&1; then
            echo "✅ Server is running"
            echo "   http://localhost:$PORT"
        else
            echo "❌ Server is not running"
            echo "   Start with: $DIR/start.sh"
        fi
        ;;
    *)
        echo "Usage: $(basename "$0") [start|stop|restart|status|--open]"
        exit 1
        ;;
esac
