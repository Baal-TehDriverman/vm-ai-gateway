#!/usr/bin/env python3
"""
🜏 Lilith Gateway Server — aiohttp (Android/Termux Compatible)
Lightweight version for edge nodes (OnePlus 6T/8T)
Serves: http://0.0.0.0:8080
"""
import json, os, asyncio, sys
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import time
import logging
import logging.handlers
import uuid

from aiohttp import web, ClientSession, WSMsgType, ClientTimeout
from aiohttp_cors import setup as cors_setup, ResourceOptions

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
        _apps_cache = load_json(APPS_JSON)
        if not _apps_cache:
            _apps_cache = {"apps": [], "count": 0, "generated": datetime.now().isoformat()}
        _apps_cache_time = now
    return _apps_cache

async def get_vms_cached():
    global _vms_cache, _vms_cache_time
    now = time.time()
    if _vms_cache is None or (now - _vms_cache_time) > CACHE_TTL:
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
            async with llm_client.get("/v1/models", timeout=ClientTimeout(total=5.0)) as resp:
                if resp.status == 200:
                    _models_cache = await resp.json()
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

# ─── WebSocket Handler ───
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    connected_websockets.add(ws)
    logger.info(f"WebSocket connected. Total: {len(connected_websockets)}")
    
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(30)
                if not ws.closed:
                    await ws.send_json({"type": "ping", "timestamp": datetime.now().isoformat()})
                else:
                    break
        except:
            pass
    
    heartbeat_task = asyncio.create_task(heartbeat())
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                elif msg.data == "refresh":
                    invalidate_apps_cache()
                    invalidate_vms_cache()
                    apps = await get_apps_cached()
                    vms = await get_vms_cached()
                    await ws.send_json({"type": "inventory", "apps": apps.get("count", 0), "vms": vms.get("count", 0)})
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"WebSocket exception: {e}")
    finally:
        heartbeat_task.cancel()
        connected_websockets.discard(ws)
        logger.info(f"WebSocket disconnected. Total: {len(connected_websockets)}")
    
    return ws

# ─── HTTP Handlers ───
async def health_check(request):
    return web.json_response({"status": "healthy", "service": "lilith-gateway-edge", "version": "2.0.0-edge", "platform": "android-termux"})

async def readiness_check(request):
    checks = {"gateway": "ok", "ollama": "unknown"}
    
    try:
        async with ClientSession(timeout=ClientTimeout(total=2.0)) as client:
            async with client.get(f"{OLLAMA_URL}/api/tags") as resp:
                checks["ollama"] = "ok" if resp.status == 200 else "error"
    except:
        checks["ollama"] = "unreachable"
    
    ready = all(v in ("ok", "unknown") for v in checks.values())
    status_code = 200 if ready else 503
    
    return web.json_response({"ready": ready, "checks": checks, "timestamp": datetime.now().isoformat()}, status=status_code)

async def liveness_check(request):
    return web.json_response({"alive": True, "service": "lilith-gateway-edge", "timestamp": datetime.now().isoformat()})

async def api_status(request):
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
    return web.json_response(status)

async def list_apps(request):
    data = await get_apps_cached()
    return web.json_response(data)

async def search_apps(request):
    query = request.match_info.get('query', '').lower()
    data = await get_apps_cached()
    results = [a for a in data.get("apps", []) if query in a.get("name", "").lower()]
    return web.json_response({"apps": results, "count": len(results), "query": query})

async def list_vms(request):
    data = await get_vms_cached()
    return web.json_response(data)

async def invalidate_cache(request):
    data = await request.json()
    cache_type = data.get("cache_type", "all")
    if cache_type in ("all", "apps"):
        invalidate_apps_cache()
    if cache_type in ("all", "vms"):
        invalidate_vms_cache()
    if cache_type in ("all", "models"):
        global _models_cache, _models_cache_time
        _models_cache = None
        _models_cache_time = 0
    return web.json_response({"status": "invalidated", "cache_type": cache_type})

async def llm_chat(request):
    """Proxy to local Ollama OpenAI-compatible endpoint."""
    if not llm_client:
        return web.json_response({"error": "LLM proxy not initialized"}, status=503)
    
    try:
        body = await request.json()
        headers = {"Content-Type": "application/json"}
        if "x-api-key" in request.headers:
            headers["x-api-key"] = request.headers["x-api-key"]
        
        async with llm_client.post(f"{OLLAMA_URL}/v1/chat/completions", json=body, headers=headers) as resp:
            response_data = await resp.json()
            return web.json_response(response_data, status=resp.status)
    except asyncio.TimeoutError:
        return web.json_response({"error": "LLM backend timeout"}, status=504)
    except Exception as e:
        return web.json_response({"error": f"LLM proxy error: {e}"}, status=502)

async def llm_models(request):
    """List models from local Ollama (cached)."""
    return web.json_response(await get_models_cached())

async def dashboard(request):
    index_html = STATIC / "index.html"
    if index_html.exists():
        return web.Response(text=index_html.read_text(), content_type='text/html')
    return web.Response(text="""
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
    """, content_type='text/html')

async def api_docs(request):
    endpoints = {
        "GET /health": "/health",
        "GET /health/ready": "/health/ready",
        "GET /health/live": "/health/live",
        "GET /api/status": "/api/status",
        "GET /api/apps": "/api/apps",
        "GET /api/apps/search/{query}": "/api/apps/search/{query}",
        "GET /api/vms": "/api/vms",
        "POST /api/cache/invalidate": "/api/cache/invalidate",
        "GET /v1/models": "/v1/models",
        "POST /v1/chat/completions": "/v1/chat/completions",
        "GET /ws": "/ws",
        "GET /": "/",
        "GET /api/docs": "/api/docs",
    }
    return web.json_response({"endpoints": endpoints, "count": len(endpoints)})

# ─── App Setup ───
async def init_app():
    global llm_client
    llm_client = ClientSession(base_url=OLLAMA_URL, timeout=ClientTimeout(total=120.0))
    
    app = web.Application()
    
    # CORS
    cors = cors_setup(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Routes
    app.router.add_get('/health', health_check)
    app.router.add_get('/health/ready', readiness_check)
    app.router.add_get('/health/live', liveness_check)
    app.router.add_get('/api/status', api_status)
    app.router.add_get('/api/apps', list_apps)
    app.router.add_get('/api/apps/search/{query}', search_apps)
    app.router.add_get('/api/vms', list_vms)
    app.router.add_post('/api/cache/invalidate', invalidate_cache)
    app.router.add_post('/v1/chat/completions', llm_chat)
    app.router.add_get('/v1/models', llm_models)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/', dashboard)
    app.router.add_get('/api/docs', api_docs)

    # Abyssal Assets edge integration (NSSP mesh app)
    try:
        from abyssal_nssp_edge import register_abyssal_routes
        register_abyssal_routes(app)
        print("🜏 Abyssal Assets edge routes mounted (/api/abyssal/*)")
    except Exception as e:
        print(f"⚠ Abyssal edge routes NOT mounted: {e}")
    
    # Static files
    if STATIC.exists():
        app.router.add_static('/static/', STATIC)
    
    return app

async def cleanup_app(app):
    global llm_client
    if llm_client:
        await llm_client.close()
        llm_client = None

# ─── Main ───
async def main():
    app = await init_app()
    
    # Add cleanup
    app.on_cleanup.append(cleanup_app)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    print("🜏 Lilith Gateway Server (Edge) — http://0.0.0.0:8080")
    print("  Dashboard → /")
    print("  API       → /api/status")
    print("  Apps      → /api/apps")
    print("  VMs       → /api/vms")
    print("  LLM Proxy → /v1/chat/completions")
    print("  Models    → /v1/models")
    print("  Docs      → /api/docs")
    print("  WebSocket → /ws")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())