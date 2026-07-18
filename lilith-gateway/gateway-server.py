#!/home/tehlappy/🜏 Lilith/_shared/gateway/venv/bin/python3
"""
🜏 Lilith Gateway Server — FastAPI
GUI access to all apps, VMs, and system status
Serves: http://localhost:8080
"""
import json, os, subprocess, shutil, asyncio, signal, sys
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).parent / "venv" / "lib" / "python3.14" / "site-packages"))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

GATEWAY = Path(__file__).parent.resolve()
STATIC = GATEWAY / "static"
APPS_JSON = GATEWAY / "apps.json"
VMS_JSON = GATEWAY / "vms.json"

# ─── App State ───
connected_websockets = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_inventory()
    yield
    connected_websockets.clear()

app = FastAPI(title="🜏 Lilith Gateway", version="2.0.0", lifespan=lifespan)

# ─── Helpers ───

def refresh_inventory():
    scan_apps = GATEWAY / "scan_apps.py"
    scan_vms = GATEWAY / "scan_vms.py"
    if scan_apps.exists():
        subprocess.run([sys.executable, str(scan_apps)], capture_output=True, timeout=30)
    if scan_vms.exists():
        subprocess.run([sys.executable, str(scan_vms)], capture_output=True, timeout=30)

def load_json(path):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return {}

def get_system_status():
    status_file = GATEWAY.parent / "dashboard" / "status.json"
    if status_file.exists():
        try: return json.loads(status_file.read_text())
        except: pass
    return {}

# ─── API Routes ───

@app.get("/api/status")
async def api_status():
    status = get_system_status()
    try:
        load = os.getloadavg()
        status["cpu_load"] = f"{load[0]:.1f} / {load[1]:.1f} / {load[2]:.1f}"
    except: pass
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                if "MemTotal" in line: mem["total"] = int(line.split()[1]) // 1024
                if "MemAvailable" in line: mem["avail"] = int(line.split()[1]) // 1024
            if mem.get("total"):
                used = mem["total"] - mem.get("avail", 0)
                status["memory_used"] = f"{used}MB / {mem['total']}MB"
    except: pass
    status["timestamp"] = datetime.now().isoformat()
    status["gateway_version"] = "2.0.0"
    status["vms_available"] = shutil.which("virsh") is not None
    return status

@app.get("/api/apps")
async def list_apps():
    data = load_json(APPS_JSON)
    return data

@app.get("/api/apps/search/{query}")
async def search_apps(query: str):
    data = load_json(APPS_JSON)
    query = query.lower()
    results = [a for a in data.get("apps", []) if query in a.get("name", "").lower()]
    return {"apps": results, "count": len(results), "query": query}

@app.post("/api/apps/launch/{app_name}")
async def launch_app(app_name: str):
    data = load_json(APPS_JSON)
    for app in data.get("apps", []):
        if app["name"].lower() == app_name.lower():
            exec_cmd = app["exec"]
            terminal = app.get("terminal", False)
            try:
                if terminal:
                    subprocess.Popen(["konsole", "-e", "bash", "-c", exec_cmd])
                else:
                    subprocess.Popen(exec_cmd, shell=True, start_new_session=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"status": "launched", "name": app["name"], "exec": exec_cmd}
            except Exception as e:
                raise HTTPException(500, f"Failed to launch: {e}")
    raise HTTPException(404, f"Application '{app_name}' not found")

@app.get("/api/vms")
async def list_vms():
    data = load_json(VMS_JSON)
    try:
        result = subprocess.run(["virsh", "list", "--all"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            for vm in data.get("vms", []):
                for line in result.stdout.split("\n")[2:]:
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 3 and parts[1] == vm["name"]:
                        vm["state"] = parts[2]
                        break
    except: pass
    return data

@app.post("/api/vms/{action}/{vm_name}")
async def vm_action(action: str, vm_name: str):
    valid_actions = {"start", "shutdown", "reset", "destroy", "reboot"}
    if action not in valid_actions:
        raise HTTPException(400, f"Invalid action: {action}")
    try:
        result = subprocess.run(
            ["virsh", action, vm_name],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return {"status": "success", "action": action, "vm": vm_name}
        else:
            raise HTTPException(500, f"virsh error: {result.stderr.strip()}")
    except FileNotFoundError:
        raise HTTPException(500, "virsh not found — install libvirt")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "VM operation timed out")

@app.post("/api/vms/console/{vm_name}")
async def vm_console(vm_name: str):
    if not shutil.which("virt-viewer"):
        raise HTTPException(500, "virt-viewer not installed")
    try:
        subprocess.Popen(["virt-viewer", "-c", "qemu:///system", vm_name], start_new_session=True)
        return {"status": "opened", "vm": vm_name}
    except Exception as e:
        raise HTTPException(500, f"Failed to open console: {e}")

@app.post("/api/vms/manager")
async def open_vm_manager():
    if not shutil.which("virt-manager"):
        raise HTTPException(500, "virt-manager not installed")
    try:
        subprocess.Popen(["virt-manager"], start_new_session=True)
        return {"status": "opened"}
    except Exception as e:
        raise HTTPException(500, f"Failed to launch virt-manager: {e}")

@app.get("/api/categories")
async def list_categories():
    data = load_json(APPS_JSON)
    cats = {}
    for app in data.get("apps", []):
        for cat in app.get("categories", []):
            if cat:
                cats[cat] = cats.get(cat, 0) + 1
    return {"categories": dict(sorted(cats.items())), "total_apps": data.get("count", 0)}

# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            elif data == "refresh":
                refresh_inventory()
                apps = load_json(APPS_JSON)
                vms = load_json(VMS_JSON)
                await websocket.send_json({"type": "inventory", "apps": apps.get("count", 0), "vms": vms.get("count", 0)})
    except WebSocketDisconnect:
        pass
    finally:
        connected_websockets.discard(websocket)

# ─── Frontend ───

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    index_html = STATIC / "index.html"
    if index_html.exists():
        return HTMLResponse(index_html.read_text())
    return HTMLResponse("<h1>🜏 Lilith Gateway</h1><p>Dashboard frontend not found. Run bootstrap.</p>")

@app.get("/api/docs")
async def api_docs():
    return {
        "endpoints": {
            "GET /api/status": "System status + live metrics",
            "GET /api/apps": "List all installed GUI applications (184 scanned)",
            "GET /api/apps/search/{query}": "Search applications",
            "POST /api/apps/launch/{name}": "Launch an application",
            "GET /api/vms": "List all virtual machines",
            "POST /api/vms/{action}/{name}": "VM control: start/shutdown/reboot",
            "POST /api/vms/console/{name}": "Open SPICE/VNC console",
            "POST /api/vms/manager": "Launch virt-manager",
            "GET /api/categories": "App categories with counts",
            "WS /ws": "WebSocket for live updates",
            "GET /": "Dashboard frontend",
        }
    }

# ─── Static files ───
os.makedirs(STATIC, exist_ok=True)

# ─── Main ───
def main():
    print("🜏 Lilith Gateway Server — http://localhost:8080")
    print("  Dashboard → /")
    print("  API       → /api/status")
    print("  Apps      → /api/apps")
    print("  VMs       → /api/vms")
    print("  Docs      → /api/docs")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")

if __name__ == "__main__":
    main()
