#!/usr/bin/env python3
"""
🜏 Lilith Gateway Server — FastAPI (Android/Termux Compatible)
Lightweight version for edge nodes (OnePlus 6T/8T) - Pydantic v1 compatible
Serves: http://0.0.0.0:8080
"""
import json, os, subprocess, asyncio, signal, sys
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import time
import logging
import logging.handlers
import uuid

GATEWAY = Path(__file__).parent.resolve()

# ─── Structured Logging Setup ───
LOG_DIR = GATEWAY / "logs"
LOG_DIR.mkdir(exist_ok=True)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        request_id = getattr(record, 'request_id', None)
        if request_id:
            log_obj["request_id"] = request_id
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    json_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gateway.json.log",
        maxBytes=10_000_000,
        backupCount=5
    )
    json_handler.setFormatter(JSONFormatter())
    logger.addHandler(json_handler)
    
    human_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "gateway.log",
        maxBytes=10_000_000,
        backupCount=5
    )
    human_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    ))
    logger.addHandler(human_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(message)s'
    ))
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# ─── LLM Proxy Config ───
OLLAMA_URL = "http://localhost:11434"
llm_client = None

STATIC = GATEWAY / "static"
APPS_JSON = GATEWAY / "apps.json"
VMS_JSON = GATEWAY / "vms.json"

# ─── App State ───
connected_websockets = set()

# ─── Cache Helpers ───
_apps_cache = None
_apps_cache_time = 0
_vms_cache = None
_vms_cache_time = 0
_models_cache = None
_models_cache_time = 0

CACHE_TTL = 30
MODELS_CACHE_TTL = 60

def load_json(path):
    if path.exists():
        try: return json.loads(path.read_text())
        except: pass
    return {}

async def get_apps_cached():
    global _apps_cache, _apps_cache_time
    now = time.time()
    if _apps_cache is None or (now - _apps_cache_time) > CACHE_TTL:
        # Skip scan on Android
        _apps_cache = load_json(APPS_JSON)
        if not _apps_cache:
            _apps_cache = {"apps": [], "count": 0, "generated": datetime.now().isoformat()}
        _apps_cache_time = now
    return _apps_cache

async def get_vms_cached():
    global _vms_cache, _vms_cache_time
    now = time.time()
    if _vms_cache is None or (now - _vms_cache_time) > CACHE_TTL:
        # Skip VM scan on Android
        _vms_cache = load_json(VMS_JSON)
        if not _vms_cache:
            _vms_cache = {"vms": [], "count": 0, "virsh_available": False, "generated": datetime.now().isoformat()}
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

@asynccontextmanager
async def lifespan(app):
    global llm_client
    import httpx
    llm_client = httpx.AsyncClient(base_url=OLLAMA_URL, timeout=120.0)
    yield
    connected_websockets.clear()
    if llm_client:
        await llm_client.aclose()
        llm_client = None

# ─── FastAPI App ───
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import uvicorn

app = FastAPI(title="🜏 Lilith Gateway (Edge)", version="2.0.0-edge", lifespan=lifespan)

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
    return {"status": "healthy", "service": "lilith-gateway-edge", "version": "2.0.0-edge", "platform": "android-termux"}

@app.get("/health/ready")
async def readiness_check():
    checks = {
        "gateway": "ok",
        "ollama": "unknown",
    }
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            checks["ollama"] = "ok" if resp.status_code == 200 else "error"
    except:
        checks["ollama"] = "unreachable"
    
    ready = all(v in ("ok", "unknown") for v in checks.values())
    status_code = 200 if ready else 503
    
    return JSONResponse(
        content={"ready": ready, "checks": checks, "timestamp": datetime.now().isoformat()},
        status_code=status_code
    )

@app.get("/health/live")
async def liveness_check():
    return {"alive": True, "service": "lilith-gateway-edge", "timestamp": datetime.now().isoformat()}

# ─── API Routes ───
@app.get("/api/status")
async def api_status():
    status = {
        "timestamp": datetime.now().isoformat(),
        "gateway_version": "2.0.0-edge",
        "platform": "android-termux",
        "device": "OnePlus 6T/8T HyperDroid",
    }
    try:
        load = os.getloadavg()
        status["cpu_load"] = f"{load[0]:.1f} / {load[1]:.1f} / {load[2]:.1f}"
    except:
        pass
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                if "MemTotal" in line: mem["total"] = int(line.split()[1]) // 1024
                if "MemAvailable" in line: mem["avail"] = int(line.split()[1]) // 1024
            if mem.get("total"):
                used = mem["total"] - mem.get("avail", 0)
                status["memory_used"] = f"{used}MB / {mem['total']}MB"
    except:
        pass
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

@app.get("/api/vms")
async def list_vms():
    data = await get_vms_cached()
    return data

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
        heartbeat_task = asyncio.create_task(heartbeat())
        
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            elif data == "refresh":
                invalidate_apps_cache()
                invalidate_vms_cache()
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
    return HTMLResponse("""
    <html><head><title>🜏 Lilith Gateway (Edge)</title></head>
    <body style="font-family: monospace; background: #0a0a0a; color: #00ff00; padding: 20px;">
    <h1>🜏 Lilith Gateway — Edge Node</h1>
    <p>Running on OnePlus 6T/8T HyperDroid</p>
    <ul>
    <li><a href="/health" style="color: #00ff88;">/health</a> — Health check</li>
    <li><a href="/health/ready" style="color: #00ff88;">/health/ready</a> — Readiness</li>
    <li><a href="/api/status" style="color: #00ff88;">/api/status</a> — System status</li>
    <li><a href="/api/apps" style="color: #00ff88;">/api/apps</a> — App inventory</li>
    <li><a href="/api/vms" style="color: #00ff88;">/api/vms</a> — VM inventory</li>
    <li><a href="/v1/models" style="color: #00ff88;">/v1/models</a> — List Ollama models</li>
    </ul>
    <p>WebSocket: <code>ws://localhost:8080/ws</code></p>
    </body></html>
    """)

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
    print("🜏 Lilith Gateway Server (Edge) — http://0.0.0.0:8080")
    print("  Dashboard → /")
    print("  API       → /api/status")
    print("  Apps      → /api/apps")
    print("  VMs       → /api/vms")
    print("  LLM Proxy → /v1/chat/completions")
    print("  Models    → /v1/models")
    print("  Docs      → /api/docs")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")

if __name__ == "__main__":
    main()