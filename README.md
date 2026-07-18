# VM AI Gateway & Dashboards

Public repository for the **Lilith Gateway** (port 8080) and **Windows Port Console** (port 8081) — dual-dashboard AI gateway system for Cyberpunk 2077 MSN Integration mod deployment and sovereign AI operations.

## Overview

| Dashboard | Port | Purpose |
|-----------|------|---------|
| **🜏 Lilith Gateway** | 8080 | Central control plane — apps, VMs, system status, LLM proxy |
| **🖥️ Windows Port Console** | 8081 | Windows 11 VM management, cross-compile dashboard, WinRM/PowerShell bridge |

## Lilith Gateway (port 8080)

**Location:** `/home/tehlappy/🜏 Lilith/_shared/gateway/`

**Features:**
- **System Dashboard** — CPU, memory, disk, load averages
- **App Launcher** — Scan, search, and launch `.desktop` applications
- **VM Manager** — Libvirt/QEMU VM control (start/stop/console/screenshot)
- **LLM Proxy** — OpenAI-compatible `/v1/chat/completions` proxy to local Ollama
- **WebSocket** — Real-time status updates
- **Static Frontend** — Single-page dashboard at `/`

**Key Endpoints:**
- `GET /api/status` — System status
- `GET /api/apps` — Installed applications
- `GET /api/vms` — VM inventory with live state
- `POST /api/vms/{action}/{vm_name}` — VM control (start/shutdown/reboot/destroy)
- `POST /v1/chat/completions` — LLM proxy (Ollama)
- `GET /v1/models` — List local models
- `WS /ws` — WebSocket for live updates

**Desktop Launchers:**
- `lilith-gateway.desktop` — Start server + open browser
- `lilith-gateway-web.desktop` — Open existing server in browser

## Windows Port Console (port 8081)

**Location:** `/home/tehlappy/Desktop/windows-port-console/`

**Features:**
- **VM Dashboard** — Create, start (headless/GUI), stop, power off, screenshot
- **Code Editor** — Browser-based editor with syntax highlighting
- **Terminal** — WebSocket terminal to VM via WinRM
- **File Browser** — Cross-platform file sync (`~/Desktop/cross-compile/`)
- **WinRM/PowerShell Bridge** — Execute PowerShell commands remotely
- **AI Assistant** — Integrated LLM chat for porting assistance

**Key Endpoints:**
- `GET /api/vm/status` — VM state + ISO info
- `POST /api/vm/start` — Start VM (headless or GUI)
- `POST /api/vm/stop` — Graceful or forced stop
- `POST /api/vm/screenshot` — Live screenshot
- `POST /api/vm/create` — Provision new Windows 11 VM
- `POST /api/winrm/execute` — Run PowerShell via WinRM
- `WS /ws` — Interactive terminal + code editor sync

**Desktop Launcher:**
- `windows11-qemu.desktop` / `windows11-spice.desktop` — VM launch shortcuts

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Lilith Gateway (8080)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Apps      │  │    VMs      │  │   System    │             │
│  │  Scanner    │  │  Manager    │  │   Status    │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          ▼                                     │
│              ┌─────────────────────┐                            │
│              │   LLM Proxy         │                            │
│              │   (Ollama / 11434)  │                            │
│              └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Windows Port Console (8081)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  VM Manager │  │ WinRM/Power │  │  Code Editor│             │
│  │  (libvirt)  │  │   Shell     │  │  (Monaco)   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          ▼                                     │
│              ┌─────────────────────┐                            │
│              │  Windows 11 VM      │                            │
│              │  (QEMU/KVM, SPICE)  │                            │
│              └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Lilith Gateway
```bash
cd /home/tehlappy/🜏\ Lilith/_shared/gateway
./launch-gateway.sh
# Opens http://localhost:8080
```

### Windows Port Console
```bash
cd /home/tehlappy/Desktop/windows-port-console
source venv/bin/activate
python3 server.py
# Opens http://localhost:8081
```

## Integration with MSN Cyberpunk Mod

Both dashboards integrate with the **MSN Integration** mod deployment pipeline:

- **Gateway API** (`/api/status`) exposes mod repo status (dirty/clean, branch, commit)
- **Deployment scripts** (`deploy_all_mods.sh`) trigger verification via Gateway
- **CET console** commands verified through Gateway status endpoint
- **Desktop launchers** provide one-click access to full deployment workflow

### Deployment Verification via Gateway
```bash
curl -s http://localhost:8080/api/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
for r in d.get('repositories', []):
    if any(k in r['name'].lower() for k in ['msn', 'gtc', 'cyberpunk']):
        print(f\"  {r['name']}: {r['status']} ({r['branch']}) dirty={r['dirty_files']}\")
"
```

## Repository Structure

```
vm-ai-gateway/
├── lilith-gateway/              # Lilith Gateway (port 8080)
│   ├── gateway_server.py        # FastAPI server
│   ├── gateway-server.py        # Legacy/alternate entry
│   ├── scan_apps.py             # .desktop scanner
│   ├── scan_vms.py              # libvirt VM scanner
│   ├── vm_helper.sh             # VM helper scripts
│   ├── inventory-refresh.sh     # Refresh apps/VMs
│   ├── launch-gateway.sh        # Startup script
│   ├── llm_providers.py         # LLM provider abstraction
│   ├── apps.json                # Cached app inventory
│   ├── vms.json                 # Cached VM inventory
│   ├── static/                  # Frontend assets
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   └── templates/               # Jinja2 templates
└── windows-port-console/        # Windows Port Console (port 8081)
    ├── server.py                # FastAPI server
    ├── vm_manager.py            # libvirt VM operations
    ├── winrm_client.py          # WinRM/PowerShell client
    ├── requirements.txt
    ├── start.sh
    ├── static/
    │   ├── index.html
    │   ├── app.js
    │   └── style.css
    └── venv/                    # Python virtualenv
```

## Dependencies

### Lilith Gateway
- Python 3.10+
- FastAPI, Uvicorn
- httpx (LLM proxy)
- psutil (system stats)
- libvirt-python (VM management)

### Windows Port Console
- Python 3.10+
- FastAPI, Uvicorn
- libvirt-python
- pywinrm (WinRM client)
- websockets

## Configuration

### Gateway Config
Environment variables in `~/.hermes/.env`:
```bash
OLLAMA_URL=http://localhost:11434
GATEWAY_PORT=8080
GATEWAY_HOST=0.0.0.0
```

### Windows Port Console
Edit `server.py` constants:
```python
VM_NAME = "Windows11"
ISO_PATH = Path.home() / "ISOs" / "Win11_24H2.iso"
SHARED_DIR = Path.home() / "Desktop" / "cross-compile"
WINRM_PORT = 5985
```

## Security Notes

- **Local-only by default** — Both servers bind to `0.0.0.0` but expect LAN/localhost use
- **No auth on LLM proxy** — Add `x-api-key` header validation if exposed
- **WinRM credentials** — Passed per-request; not stored
- **WebSocket** — No auth; restrict to trusted networks

## Related Repositories

| Repo | Purpose |
|------|---------|
| `msn-integration` | Cyberpunk 2077 MSN Integration mod (205+ REDscripts) |
| `gtc-mod-staging` | GTC mod stack staging & validation |
| `lilith-frankenstein` | Unified Lilith sovereign AI framework |
| `Sovereign-Core` | 10 Sephirothic agents + council bus |
| `convergence-crucible` | Alchemical conflict resolution engine |

## License

MIT — Part of the Lilith Systems sovereign AI framework.