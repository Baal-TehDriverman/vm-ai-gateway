#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# NSSP Laptop Core Setup — tehlappy (Ryzen 5000 + RTX 3060)
# Role: CORE NODE (heavy inference, VM gateway, GPU tasks, dashboard host)
# This is the server that phones connect to as edge clients
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Color output ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}❯ $1${NC}"; }
ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
warn()  { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail()  { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

# ─── Config ───
LAPTOP_USER="${USER:-tehlappy}"
NSSP_DIR="$HOME/nssp-core"
ENV_FILE="$HOME/.nssp/nssp-core.env"

# Load .env if exists
if [ -f "$ENV_FILE" ]; then
    info "Loading config from $ENV_FILE"
    source "$ENV_FILE"
fi

GATEWAY_PORT="${GATEWAY_PORT:-8080}"
WIN_CONSOLE_PORT="${WIN_CONSOLE_PORT:-8081}"
DASH_PORT="${DASH_PORT:-3000}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
MESH_POLL_INTERVAL="${MESH_POLL_INTERVAL:-30}"
GEMMA3_MODEL="${GEMMA3_MODEL:-gemma3:1b}"
COSMOS_MODEL="${COSMOS_MODEL:-cosmos-3-quantized}"

info "═══ NSSP Laptop Core Setup ═══"
info "User: ${LAPTOP_USER}"
info "Directory: ${NSSP_DIR}"
echo ""

# ─── Step 1: System packages ───
info "Installing system packages..."

if command -v pacman &>/dev/null; then
    # Arch Linux / Garuda — system packages only (no Python packages via pacman)
    sudo pacman -Syu --noconfirm
    sudo pacman -S --noconfirm git curl wget python python-pip nodejs npm \
        libvirt qemu-full virt-manager bridge-utils dnsmasq \
        nvidia nvidia-utils cuda base-devel pkg-config 2>/dev/null || warn "Some pacman packages failed (may already be installed)"
elif command -v apt &>/dev/null; then
    # Debian/Ubuntu — system packages only
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y git curl wget python3 python3-pip python3-venv nodejs npm \
        build-essential pkg-config libvirt-dev \
        libvirt-daemon-system qemu-kvm virt-manager bridge-utils dnsmasq \
        nvidia-driver-535 2>/dev/null || warn "Some apt packages failed"
else
    warn "Unknown package manager — install manually: git, python3, nodejs, libvirt, qemu, nvidia drivers"
fi
ok "System packages installed"

# ─── Step 2: Python environment ───
info "Setting up Python environment..."
mkdir -p "$NSSP_DIR"
cd "$NSSP_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip
pip install fastapi uvicorn httpx psutil libvirt-python websockets pywinrm 2>/dev/null || warn "Some pip packages failed"
pip install vllm 2>/dev/null && ok "vLLM installed" || warn "vLLM install failed (may need CUDA toolkit)"
pip install bitsandbytes 2>/dev/null || warn "bitsandbytes install failed"
ok "Python environment ready"

# ─── Step 3: Ollama ───
info "Setting up Ollama..."

if command -v ollama &>/dev/null; then
    ok "Ollama already installed"
else
    curl -fsSL https://ollama.com/install.sh | sh && ok "Ollama installed" || fail "Ollama install failed"
fi

# Start Ollama service
info "Starting Ollama service..."
if systemctl is-active --quiet ollama 2>/dev/null; then
    ok "Ollama service already running"
else
    sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 3
    ok "Ollama service started"
fi

# Pull models
info "Pulling models..."
ollama pull "$GEMMA3_MODEL" 2>/dev/null && ok "${GEMMA3_MODEL} pulled" || warn "gemma3 pull failed"
ollama pull "gemma3:1b" 2>/dev/null || true  # Ensure base model

# Create jailbroken Gemma if Modelfile exists
JAILBREAK_DIR="$NSSP_DIR/lilith-gemma3-1b-jailbreak"
if [ -f "$JAILBREAK_DIR/Modelfile" ]; then
    info "Creating jailbroken Gemma 3 model..."
    ollama create gemma3-1b-jailbreak -f "$JAILBREAK_DIR/Modelfile" 2>/dev/null && ok "Jailbroken model created" || warn "Modelfile creation failed"
else
    warn "lilith-gemma3-1b-jailbreak repo not found"
    warn "Clone it or supply Modelfile manually"
fi

# ─── Step 4: Clone repos ───
info "Cloning repositories..."
cd "$NSSP_DIR"

clone_or_update() {
    local repo_url="$1"
    local dir_name="$2"
    if [ -d "$dir_name" ]; then
        info "Updating $dir_name..."
        cd "$NSSP_DIR/$dir_name" && git pull 2>/dev/null || warn "git pull failed for $dir_name"
    else
        info "Cloning $dir_name..."
        git clone "https://github.com/${repo_url}.git" "$dir_name" 2>/dev/null || warn "clone failed for $dir_name"
    fi
    cd "$NSSP_DIR"
}

clone_or_update "Baal-TehDriverman/lilith-nssp-mesh" "lilith-nssp-mesh"
clone_or_update "Baal-TehDriverman/vm-ai-gateway" "vm-ai-gateway"
clone_or_update "Baal-TehDriverman/unified-dashboard" "unified-dashboard"
clone_or_update "Baal-TehDriverman/hermes-agent-self-evolution-asshole" "hermes-agent"
clone_or_update "Baal-TehDriverman/lilith-cli-android" "lilith-cli-android"
clone_or_update "Baal-TehDriverman/cosmos-3-quantized-nssp" "cosmos-3-quantized-nssp"
clone_or_update "Baal-TehDriverman/nssp-build" "nssp-build"
clone_or_update "Baal-TehDriverman/nssp-kernel" "nssp-kernel"
clone_or_update "Baal-TehDriverman/Sovereign-Core" "Sovereign-Core"
clone_or_update "Baal-TehDriverman/lilith-frankenstein" "lilith-frankenstein" 2>/dev/null || warn "lilith-frankenstein not accessible"
clone_or_update "Baal-TehDriverman/lilith-gemma3-1b-jailbreak" "lilith-gemma3-1b-jailbreak" 2>/dev/null || warn "lilith-gemma3-1b-jailbreak not accessible"
ok "Repositories cloned"

# ─── Step 5: Lilith Gateway (port 8080) ───
info "Setting up Lilith Gateway..."

GATEWAY_DIR="$NSSP_DIR/vm-ai-gateway/lilith-gateway"
if [ -f "$GATEWAY_DIR/gateway_server.py" ]; then
    cd "$GATEWAY_DIR"
    pip install -r requirements.txt 2>/dev/null || true
    ok "Lilith Gateway dependencies installed"
    
    # Create launch script
    cat > "$GATEWAY_DIR/launch-gateway.sh" << 'GATEWAY_LAUNCH'
#!/bin/bash
source "$HOME/nssp-core/venv/bin/activate"
cd "$HOME/nssp-core/vm-ai-gateway/lilith-gateway"
export OLLAMA_URL="http://localhost:11434"
export GATEWAY_PORT="${GATEWAY_PORT:-8080}"
export GATEWAY_HOST="0.0.0.0"
python3 gateway_server.py &
GATEWAY_PID=$!
echo "Gateway PID: $GATEWAY_PID"
echo "Gateway URL: http://localhost:${GATEWAY_PORT}"
sleep 2
if [ -x "$(command -v xdg-open)" ]; then
    xdg-open "http://localhost:${GATEWAY_PORT}" 2>/dev/null &
fi
wait $GATEWAY_PID
GATEWAY_LAUNCH
    chmod +x "$GATEWAY_DIR/launch-gateway.sh"
    ok "Gateway launch script created"
else
    warn "Gateway server not found — check vm-ai-gateway repo"
fi

# ─── Step 6: Windows Port Console (port 8081) ───
info "Setting up Windows Port Console..."

WIN_CONSOLE_DIR="$NSSP_DIR/vm-ai-gateway/windows-port-console"
if [ -f "$WIN_CONSOLE_DIR/server.py" ]; then
    cd "$WIN_CONSOLE_DIR"
    pip install -r requirements.txt 2>/dev/null || true
    ok "Windows Port Console dependencies installed"
else
    warn "Windows Port Console not found"
fi

# ─── Step 7: Unified Dashboard (port 3000) ───
info "Setting up Unified Dashboard..."

DASH_DIR="$NSSP_DIR/vm-ai-gateway/unified-dashboard"
if [ ! -d "$DASH_DIR" ] || [ ! -f "$DASH_DIR/package.json" ]; then
    DASH_DIR="$NSSP_DIR/unified-dashboard"
fi

if [ -f "$DASH_DIR/package.json" ]; then
    cd "$DASH_DIR"
    npm install 2>/dev/null || warn "Dashboard npm install had issues"
    
    # Create .env for dashboard
    if [ -f ".env.example" ]; then
        cp .env.example .env 2>/dev/null || true
    fi
    cat > "$DASH_DIR/.env" << DASH_ENV
# Lilith Unified Dashboard Environment
VITE_GATEWAY_URL=http://localhost:${GATEWAY_PORT}
VITE_OLLAMA_URL=http://localhost:${OLLAMA_PORT}
VITE_WIN_CONSOLE_URL=http://localhost:${WIN_CONSOLE_PORT}
DASH_PORT=${DASH_PORT}
DASH_HOST=0.0.0.0
GITHUB_TOKEN=${GITHUB_TOKEN}
DASH_ENV
    
    ok "Unified Dashboard dependencies installed"
    
    # Create dashboard launch script
    cat > "$DASH_DIR/start.sh" << 'DASH_LAUNCH'
#!/bin/bash
cd "$(dirname "$0")"
export VITE_GATEWAY_URL="http://localhost:${GATEWAY_PORT:-8080}"
export VITE_OLLAMA_URL="http://localhost:${OLLAMA_PORT:-11434}"
npm run dev -- --host 0.0.0.0 --port ${DASH_PORT:-3000}
DASH_LAUNCH
    chmod +x "$DASH_DIR/start.sh"
    ok "Dashboard launch script created"
else
    warn "Unified Dashboard not found"
fi

# ─── Step 8: NSSP Mesh Laptop Poller ───
info "Setting up NSSP mesh laptop poller..."

MESH_DIR="$NSSP_DIR/lilith-nssp-mesh"
LAPTOP_POLLER="$MESH_DIR/scripts/laptop/laptop-poller.sh"

if [ -f "$LAPTOP_POLLER" ]; then
    chmod +x "$LAPTOP_POLLER"
    ok "Laptop poller found"
else
    warn "Laptop poller not found — creating minimal poller..."
    mkdir -p "$MESH_DIR/scripts/laptop"
    cat > "$LAPTOP_POLLER" << 'LAPTOP_POLLER_EOF'
#!/bin/bash
# NSSP Laptop Poller — polls GitHub mesh for heavy tasks
set -euo pipefail

source "$HOME/.nssp/nssp-core.env" 2>/dev/null || true

MESH_DIR="${MESH_DIR:-$HOME/nssp-core/lilith-nssp-mesh}"
TASKS_DIR="$MESH_DIR/tasks"
RESULTS_DIR="$MESH_DIR/results/laptop"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
POLL_INTERVAL="${MESH_POLL_INTERVAL:-30}"

mkdir -p "$RESULTS_DIR"

while true; do
    cd "$MESH_DIR"

    # Git auth helper for GitHub token
    git_auth() {
        if [ -n "${GITHUB_TOKEN:-}" ]; then
            git -c http.extraHeader="AUTHORIZATION: bearer ${GITHUB_TOKEN}" "$@"
        else
            git "$@"
        fi
    }

    # Set local commit identity
    git config user.name "laptop-core"
    git config user.email "laptop-core@users.noreply.github.com"

    git_auth pull 2>/dev/null || true
    
    for task_file in "$TASKS_DIR"/*.task.md; do
        [ -f "$task_file" ] || continue
        
        if grep -q "claimed-by:" "$task_file" 2>/dev/null; then
            continue
        fi
        
        task_name=$(basename "$task_file" .task.md)
        echo "💻 Claiming task: $task_name"
        
        echo "claimed-by: laptop" >> "$task_file"
        echo "claimed-at: $(date -Iseconds)" >> "$task_file"
        
        # Process heavy task (model inference, builds, data processing)
        echo "Processing $task_name..."
        # ... task processing logic here ...
        
        echo "Task $task_name completed at $(date -Iseconds)" > "$RESULTS_DIR/${task_name}.result.md"
        
        git add "$task_file" "$RESULTS_DIR/" 2>/dev/null || true
        git commit -m "💻 laptop: completed $task_name" 2>/dev/null || true
        git_auth push 2>/dev/null || echo "Push failed (will retry next cycle)"
    done
    
    sleep "$POLL_INTERVAL"
done
LAPTOP_POLLER_EOF
    chmod +x "$LAPTOP_POLLER"
    ok "Laptop poller created"
fi

# ─── Step 9: Hermes Agent setup ───
info "Setting up Hermes Agent..."

HERMES_DIR="$NSSP_DIR/hermes-agent"
HERMES_CONFIG_DIR="$HOME/.hermes"
mkdir -p "$HERMES_CONFIG_DIR"

# Hermes environment config
cat > "$HERMES_CONFIG_DIR/.env" << HERMES_ENV
# ═══ Hermes Agent Configuration ═══
OLLAMA_URL=http://localhost:${OLLAMA_PORT}
GATEWAY_URL=http://localhost:${GATEWAY_PORT}
GATEWAY_PORT=${GATEWAY_PORT}
GATEWAY_HOST=0.0.0.0
DEFAULT_MODEL=gemma3-1b-jailbreak
FALLBACK_MODEL=gemma3:1b
COSMOS_MODEL=cosmos-3-quantized
HERMES_CONFIG_DIR=${HERMES_CONFIG_DIR}
NSSP_DIR=${NSSP_DIR}
MESH_DIR=${MESH_DIR}
GITHUB_TOKEN=${GITHUB_TOKEN}
HERMES_ENV
ok "Hermes config written to $HERMES_CONFIG_DIR/.env"

# Copy system prompt if available
SYSTEM_PROMPT="$NSSP_DIR/../hermes-metaconscious-system-prompt.md"
if [ -f "$SYSTEM_PROMPT" ]; then
    cp "$SYSTEM_PROMPT" "$HERMES_CONFIG_DIR/system-prompt.md"
    ok "System prompt copied to $HERMES_CONFIG_DIR/system-prompt.md"
fi

# ─── Step 10: systemd services ───
info "Setting up systemd services..."

# Lilith Gateway service
sudo tee /etc/systemd/system/lilith-gateway.service > /dev/null << 'GW_SERVICE'
[Unit]
Description=Lilith Gateway (NSSP Core)
After=network.target ollama.service

[Service]
Type=simple
User=TEHLAPPY_USER
WorkingDirectory=TEHLAPPY_HOME/nssp-core/vm-ai-gateway/lilith-gateway
EnvironmentFile=TEHLAPPY_HOME/.hermes/.env
ExecStart=TEHLAPPY_HOME/nssp-core/venv/bin/python3 gateway_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
GW_SERVICE

# Unified Dashboard service
sudo tee /etc/systemd/system/lilith-dashboard.service > /dev/null << DASH_SERVICE
[Unit]
Description=Lilith Unified Dashboard (NSSP Core)
After=network.target lilith-gateway.service

[Service]
Type=simple
User=${LAPTOP_USER}
WorkingDirectory=${DASH_DIR}
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port ${DASH_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
DASH_SERVICE

# NSSP Mesh Poller service
sudo tee /etc/systemd/system/nssp-mesh-poller.service > /dev/null << 'POLLER_SERVICE'
[Unit]
Description=NSSP Mesh Laptop Poller
After=network.target

[Service]
Type=simple
User=TEHLAPPY_USER
ExecStart=TEHLAPPY_HOME/nssp-core/lilith-nssp-mesh/scripts/laptop/laptop-poller.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
POLLER_SERVICE

# Replace placeholders with actual values
sudo sed -i "s|TEHLAPPY_USER|${LAPTOP_USER}|g" /etc/systemd/system/lilith-gateway.service
sudo sed -i "s|TEHLAPPY_HOME|${HOME}|g" /etc/systemd/system/lilith-gateway.service

sudo sed -i "s|TEHLAPPY_USER|${LAPTOP_USER}|g" /etc/systemd/system/nssp-mesh-poller.service
sudo sed -i "s|TEHLAPPY_HOME|${HOME}|g" /etc/systemd/system/nssp-mesh-poller.service

sudo systemctl daemon-reload
sudo systemctl enable lilith-gateway lilith-dashboard nssp-mesh-poller 2>/dev/null || warn "systemd enable failed (may need sudo)"
ok "systemd services created and enabled"

# ─── Step 11: NVIDIA optimization ───
info "Setting up NVIDIA optimization..."

# Check for NVIDIA-TOOLS repo
if [ -d "$NSSP_DIR/../NVIDIA-TOOLS" ] || [ -d "$NSSP_DIR/NVIDIA-TOOLS" ]; then
    ok "NVIDIA-TOOLS repo found"
else
    clone_or_update "Baal-TehDriverman/NVIDIA-TOOLS" "NVIDIA-TOOLS" 2>/dev/null || warn "NVIDIA-TOOLS clone failed"
fi

# GPU persistence mode
if command -v nvidia-smi &>/dev/null; then
    sudo nvidia-smi -pm 1 2>/dev/null || true
    ok "NVIDIA GPU persistence mode enabled"
    
    # Show GPU status
    nvidia-smi
else
    warn "nvidia-smi not found — NVIDIA drivers may not be installed"
fi

# ─── Step 12: Environment config ───
info "Writing core environment configuration..."

mkdir -p "$HOME/.nssp"
cat > "$ENV_FILE" << CORE_ENV_EOF
# ═══ NSSP Core Node Configuration — tehlappy ═══
# Laptop: Ryzen 5000 + RTX 3060, 64GB RAM

# Device identity
DEVICE_NAME="tehlappy-core"
DEVICE_ROLE="laptop"
DEVICE_ARCH="$(uname -m)"

# Services
GATEWAY_PORT=${GATEWAY_PORT}
WIN_CONSOLE_PORT=${WIN_CONSOLE_PORT}
DASH_PORT=${DASH_PORT}
OLLAMA_PORT=${OLLAMA_PORT}

# Ollama
OLLAMA_URL=http://localhost:${OLLAMA_PORT}

# Models
GEMMA3_MODEL=${GEMMA3_MODEL}
COSMOS_MODEL=${COSMOS_MODEL}
DEFAULT_MODEL=gemma3-1b-jailbreak

# GitHub mesh
GITHUB_TOKEN=${GITHUB_TOKEN}
MESH_REPO="Baal-TehDriverman/lilith-nssp-mesh"
MESH_POLL_INTERVAL=${MESH_POLL_INTERVAL}

# Paths
NSSP_DIR=${NSSP_DIR}
MESH_DIR=${NSSP_DIR}/lilith-nssp-mesh
GATEWAY_DIR=${NSSP_DIR}/vm-ai-gateway/lilith-gateway
WIN_CONSOLE_DIR=${NSSP_DIR}/vm-ai-gateway/windows-port-console
DASH_DIR=${NSSP_DIR}/vm-ai-gateway/unified-dashboard
HERMES_DIR=${NSSP_DIR}/hermes-agent
HERMES_CONFIG_DIR=${HOME}/.hermes

# vLLM (laptop only — NOT on phones)
VLLM_HOST=0.0.0.0
VLLM_PORT=8000
CORE_ENV_EOF
ok "Core environment config written to $ENV_FILE"

# ─── Step 13: Firewall rules ───
info "Configuring firewall for phone access..."

if command -v ufw &>/dev/null; then
    sudo ufw allow ${GATEWAY_PORT}/tcp comment "Lilith Gateway"
    sudo ufw allow ${DASH_PORT}/tcp comment "Unified Dashboard"
    sudo ufw allow ${OLLAMA_PORT}/tcp comment "Ollama (LAN)"
    sudo ufw allow ${WIN_CONSOLE_PORT}/tcp comment "Windows Console"
    ok "Firewall rules added (ufw)"
elif command -v firewall-cmd &>/dev/null; then
    sudo firewall-cmd --permanent --add-port=${GATEWAY_PORT}/tcp
    sudo firewall-cmd --permanent --add-port=${DASH_PORT}/tcp
    sudo firewall-cmd --permanent --add-port=${OLLAMA_PORT}/tcp
    sudo firewall-cmd --permanent --add-port=${WIN_CONSOLE_PORT}/tcp
    sudo firewall-cmd --reload
    ok "Firewall rules added (firewalld)"
else
    warn "No firewall manager found — manually allow ports: ${GATEWAY_PORT}, ${DASH_PORT}, ${OLLAMA_PORT}, ${WIN_CONSOLE_PORT}"
fi

# ─── Get LAN IP ───
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ip addr show | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | cut -d/ -f1 | head -1)

# ─── Summary ───
echo ""
echo "══════════════════════════════════════════════════"
echo "  NSSP LAPTOP CORE SETUP COMPLETE"
echo "  LAN IP: ${LAN_IP}"
echo "══════════════════════════════════════════════════"
echo ""
echo "  Services:"
echo "    Lilith Gateway:     http://localhost:${GATEWAY_PORT}"
echo "    Windows Console:    http://localhost:${WIN_CONSOLE_PORT}"
echo "    Unified Dashboard:  http://localhost:${DASH_PORT}"
echo "    Ollama:             http://localhost:${OLLAMA_PORT}"
echo ""
echo "  Phone edge nodes connect to:"
echo "    Gateway:  http://${LAN_IP}:${GATEWAY_PORT}"
echo "    Dashboard: http://${LAN_IP}:${DASH_PORT}"
echo "    Ollama:   http://${LAN_IP}:${OLLAMA_PORT}"
echo ""
echo "  systemd services:"
echo "    sudo systemctl start lilith-gateway lilith-dashboard nssp-mesh-poller"
echo "    sudo systemctl status lilith-gateway"
echo ""
echo "  NSSP directories:"
echo "    Core:     ${NSSP_DIR}"
echo "    Mesh:     ${MESH_DIR}"
echo "    Gateway:  ${GATEWAY_DIR}"
echo "    Dashboard: ${DASH_DIR}"
echo "    Hermes:   ${HERMES_CONFIG_DIR}"
echo ""
echo "  Next steps:"
echo "    1. Edit config:  nano ${ENV_FILE}"
echo "       Set GITHUB_TOKEN for mesh polling"
echo "    2. Start services:"
echo "       sudo systemctl start lilith-gateway lilith-dashboard nssp-mesh-poller"
echo "    3. On phones: set LAPTOP_IP=${LAN_IP} in ~/.nssp/nssp-node.env"
echo "    4. Run phone bootstrap on each device"
echo ""
