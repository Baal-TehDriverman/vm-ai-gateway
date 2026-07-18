#!/home/tehlappy/🜏 Lilith/_shared/gateway/venv/bin/python3
"""
🜏 Lilith Gateway Server — FastAPI
GUI access to all apps, VMs, and system status
Serves: http://localhost:8080
"""
import json, os, subprocess, shutil, asyncio, signal, sys
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import time

sys.path.insert(0, str(Path(__file__).parent / "venv" / "lib" / "python3.14" / "site-packages"))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import uvicorn

GATEWAY = Path(__file__).parent.resolve()

# ─── LLM Proxy Config ───
OLLAMA_URL = "http://localhost:11434"
llm_client: httpx.AsyncClient | None = None

STATIC = GATEWAY / "static"
APPS_JSON = GATEWAY / "apps.json"
VMS_JSON = GATEWAY / "vms.json"

# ─── App State ───
connected_websockets = set()

# ─── Cache Helpers ───
# Cache storage
_apps_cache = None
_apps_cache_time = 0
_vms_cache = None
_vms_cache_time = 0
_models_cache = None
_models_cache_time = 0

CACHE_TTL = 30  # seconds
MODELS_CACHE_TTL = 60  # seconds

def load_json(path):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return {}

async def get_apps_cached():
    global _apps_cache, _apps_cache_time
    now = time.time()
    if _apps_cache is None or (now - _apps_cache_time) > CACHE_TTL:
        scan_apps = GATEWAY / "scan_apps.py"
        if scan_apps.exists():
            subprocess.run([sys.executable, str(scan_apps)], capture_output=True, timeout=30)
        _apps_cache = load_json(APPS_JSON)
        _apps_cache_time = now
    return _apps_cache

async def get_vms_cached():
    global _vms_cache, _vms_cache_time
    now = time.time()
    if _vms_cache is None or (now - _vms_cache_time) > CACHE_TTL:
        scan_vms = GATEWAY / "scan_vms.py"
        if scan_vms.exists():
            subprocess.run([sys.executable, str(scan_vms)], capture_output=True, timeout=30)
        _vms_cache = load_json(VMS_JSON)
        _vms_cache_time = now
    return _vms_cache

async def get_models_cached():
    global _models_cache, _models_cache_time, llm_client
    now = time.time()
    if _models_cache is not None and (now - _models_cache_time) < MODELS_CACHE_TTL:
        return _models_cache
    
    if llm_client:
        try:
            resp = await llm_client.get("/v1/models", timeout=5.0)
            if resp.status_code == 200:
                _models_cache = resp.json()
                _models_cache_time = now
                return _models_cache
        except:
            pass
    return {"data": []}

def invalidate_apps_cache():
    global _apps_cache, _apps_cache_time
    _apps_cache = None
    _apps_cache_time = 0

def invalidate_vms_cache():
    global _vms_cache, _vms_cache_time
    _vms_cache = None
    _vms_cache_time = 0

def refresh_inventory():
    """Force refresh of both inventories"""
    invalidate_apps_cache()
    invalidate_vms_cache()
    # Trigger async refresh
    scan_apps = GATEWAY / "scan_apps.py"
    scan_vms = GATEWAY / "scan_vms.py"
    if scan_apps.exists():
        subprocess.run([sys.executable, str(scan_apps)], capture_output=True, timeout=30)
    if scan_vms.exists():
        subprocess.run([sys.executable, str(scan_vms)], capture_output=True, timeout=30)

def get_system_status():
    status_file = GATEWAY.parent / "dashboard" / "status.json"
    if status_file.exists():
        try: return json.loads(status_file.read_text())
        except: pass
    return {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client
    llm_client = httpx.AsyncClient(base_url=OLLAMA_URL, timeout=120.0)
    # Don't refresh inventory on startup - lazy load instead
    yield
    connected_websockets.clear()
    if llm_client:
        await llm_client.aclose()
        llm_client = None

app = FastAPI(title="🜏 Lilith Gateway", version="2.0.0", lifespan=lifespan)

# ─── LLM Proxy Routes ───

@app.api_route("/v1/chat/completions", methods=["POST"])
async def llm_chat(request: Request):
    """Proxy to local Ollama OpenAI-compatible endpoint."""
    if not llm_client:
        raise HTTPException(503, "LLM proxy not initialized")
    body = await request.json()
    headers = {"Content-Type": "application/json"}
    if "x-api-key" in request.headers:
        headers["x-api-key"] = request.headers["x-api-key"]
    try:
        resp = await llm_client.post("/v1/chat/completions", json=body, headers=headers)
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        raise HTTPException(504, "LLM backend timeout")
    except Exception as e:
        raise HTTPException(502, f"LLM proxy error: {e}")

@app.api_route("/v1/models", methods=["GET"])
async def llm_models():
    """List models from local Ollama (cached)."""
    return await get_models_cached()

# ─── Health Check Routes ───

@app.get("/health")
async def health_check():
    """Basic health check - returns 200 if service is running"""
    return {"status": "healthy", "service": "lilith-gateway", "version": "2.0.0"}

@app.get("/health/ready")
async def readiness_check():
    """Readiness check - verifies dependencies are available"""
    checks = {
        "gateway": "ok",
        "virsh": "ok" if shutil.which("virsh") else "missing",
        "ollama": "unknown",
    }
    
    # Check Ollama connectivity
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            checks["ollama"] = "ok" if resp.status_code == 200 else "error"
    except:
        checks["ollama"] = "unreachable"
    
    # Overall readiness
    ready = all(v in ("ok", "unknown") for v in checks.values())
    status_code = 200 if ready else 503
    
    return JSONResponse(
        content={"ready": ready, "checks": checks, "timestamp": datetime.now().isoformat()},
        status_code=status_code
    )

@app.get("/health/live")
async def liveness_check():
    """Liveness check - returns 200 if process is alive"""
    return {"alive": True, "service": "lilith-gateway", "timestamp": datetime.now().isoformat()}

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
    data = await get_apps_cached()
    return data

@app.get("/api/apps/search/{query}")
async def search_apps(query: str):
    data = await get_apps_cached()
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
    data = await get_vms_cached()
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

# ─── Cache Management ───

@app.post("/api/cache/invalidate")
async def invalidate_cache(cache_type: str = "all"):
    """Manually invalidate caches"""
    if cache_type in ("all", "apps"):
        invalidate_apps_cache()
    if cache_type in ("all", "vms"):
        invalidate_vms_cache()
    if cache_type in ("all", "models"):
        global _models_cache, _models_cache_time
        _models_cache = None
        _models_cache_time = 0
    return {"status": "invalidated", "cache_type": cache_type}

# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    heartbeat_task = None
    
    async def heartbeat():
        """Send periodic ping to keep connection alive"""
        try:
            while True:
                await asyncio.sleep(30)
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_json({"type": "ping", "timestamp": datetime.now().isoformat()})
                else:
                    break
        except:
            pass

    try:
        # Start heartbeat
        heartbeat_task = asyncio.create_task(heartbeat())
        
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            elif data == "pong":
                # Heartbeat response from client
                pass
            elif data == "refresh":
                refresh_inventory()
                apps = await get_apps_cached()
                vms = await get_vms_cached()
                await websocket.send_json({"type": "inventory", "apps": apps.get("count", 0), "vms": vms.get("count", 0)})
    except WebSocketDisconnect:
        pass
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
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
    endpoints = {}
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for m in route.methods:
                if m in ("GET", "POST", "PUT", "DELETE", "WS"):
                    key = f"{m} {route.path}"
                    endpoints[key] = route.path
    return {"endpoints": endpoints, "count": len(endpoints)}

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
    sys.argv = ["gateway_server.py", "run"]; uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")

if __name__ == "__main__":
    main()