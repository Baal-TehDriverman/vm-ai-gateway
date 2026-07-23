#!/bin/bash
# launch-standalone.sh — One-click launcher for Lilith Unified Dashboard
# Builds (if needed), starts server, opens Firefox.
# Part of https://github.com/Baal-TehDriverman/vm-ai-gateway

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# ─── Config ───
PORT="${PORT:-3000}"
APP_NAME="🜏 Lilith Unified Dashboard"

# ─── Ensure .env ───
if [ ! -f .env ]; then
  [ -f .env.example ] && cp .env.example .env
  echo "[✓] Created .env from .env.example"
fi

# ─── Install deps if missing ───
if [ ! -d node_modules ]; then
  echo "[...] Installing dependencies..."
  npm install || exit 1
  echo "[✓] Dependencies installed"
fi

# ─── Build if needed ───
if [ ! -f dist/index.html ]; then
  echo "[...] Building production bundle..."
  npm run build || exit 1
  echo "[✓] Build complete"
fi

# ─── Kill existing instance on port ───
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "[...] Stopping existing instance on :$PORT..."
  kill $(lsof -ti tcp:"$PORT") 2>/dev/null
  sleep 1
fi

# ─── Start production server ───
export NODE_ENV=production
nohup node dist/server.cjs > "$PROJECT_DIR/dashboard.log" 2>&1 &
APP_PID=$!
disown $APP_PID
echo "[✓] $APP_NAME started (PID $APP_PID) at http://localhost:$PORT"

# ─── Wait for port then open browser ───
for i in $(seq 1 15); do
  if curl -s -o /dev/null -m 1 "http://localhost:$PORT/"; then
    break
  fi
  sleep 1
done

# Open in browser
if command -v firefox >/dev/null 2>&1; then
  firefox "http://localhost:$PORT/" 2>/dev/null &
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$PORT/" 2>/dev/null &
fi
echo "[✓] Dashboard opened in browser"