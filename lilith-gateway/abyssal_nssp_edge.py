#!/usr/bin/env python3
"""abyssal_nssp_edge.py — Abyssal Assets edge integration for the NSSP mesh.

Bridges the Abyssal Assets game/MSN onto the OnePlus 8T/6T edge via:
  1. NSSP mesh registration     -> POST {coordinator}/edge/register (node=abyssal)
  2. Lilith Gateway routes      -> /api/abyssal/status, /api/abyssal/nessie
  3. OPEX durable bridge        -> payloads queued + flushed to core on wake

Mount with:
    from abyssal_nssp_edge import register_abyssal_routes
    register_abyssal_routes(app)   # app: aiohttp.web.Application
"""
import aiohttp
from aiohttp import web
import json, os, time, hashlib

ABYSSAL = {
    "app": "abyssal-assets",
    "name": "Abyssal Assets — The Loch Exchange + MSN",
    "version": "1.0.0-edge",
    "source_repo": "Baal-TehDriverman/AbyssalAssetsstandalone",
    "lane": "abyssal",
    "cerebellum": "gemma3-1b-jailbreak",
    "sephira": "DAAT",
    "status": "armed",
}

COORDINATOR = os.environ.get("NSSP_COORDINATOR_URL", "http://192.168.1.20:8001")
NODE_ID = os.environ.get("NSSP_NODE_ID", "oneplus-8t-kebab")

# ---------------------------------------------------------------------------
# OPEX bridge — durable at-least-once payload queue shared with the mesh
# ---------------------------------------------------------------------------
_OPEX_Q = os.path.expanduser(os.environ.get("OPEX_QUEUE_DIR", "~/opex_queue"))


def enqueue(payload: dict) -> str:
    os.makedirs(_OPEX_Q, exist_ok=True)
    pid = hashlib.sha256(f"{time.time()}{json.dumps(payload)}".encode()).hexdigest()
    with open(os.path.join(_OPEX_Q, f"{pid}.json"), "w") as f:
        json.dump({"id": pid, "ts": int(time.time()), "data": payload,
                   "status": "pending", "attempts": 0}, f)
    return pid


async def _register_with_coordinator():
    """Best-effort registration; never raises (mesh may be asleep)."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            r = await s.post(f"{COORDINATOR}/edge/register", json={
                "node_id": f"{NODE_ID}--abyssal",
                "device": "OnePlus 8T (edge)",
                "models": ["gemma3-12b-jailbreak", "abyssal-core"],
                "apps": ["abyssal-assets"],
            })
            if r.status < 300:
                try:
                    return await r.json()
                except Exception:
                    return {"status": f"registered-{r.status}"}
    except Exception as e:
        return {"status": "coordinator-unreachable", "detail": str(e)}


async def abyssal_status(_req):
    reg = await _register_with_coordinator()
    return web.json_response({
        **ABYSSAL,
        "mesh": reg,
        "queue_pending": len([f for f in os.listdir(_OPEX_Q)
                              if f.endswith(".json")]) if os.path.isdir(_OPEX_Q) else 0,
        "ts": int(time.time()),
    })


async def abyssal_nessie(_req):
    # Nessie friendship crossover detail (mirrors MSN agent_nssp.py NESSIE_STATE)
    state_file = os.path.expanduser(
        "~/AbyssalAssetsstandalone/agents/runtime/nssp/nessie_friendship.json")
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return web.json_response(json.load(f))
        except Exception:
            pass
    return web.json_response({"tier": 0, "friendship": 0, "location": "Night City",
                               "note": "Nessie state files live on the laptop core"})


async def abyssal_dispatch(req):
    """Dispatch a command payload to the core (e.g. a Living Sin GM action)."""
    try:
        body = await req.json()
    except Exception:
        body = {"kind": "dispatch", "ts": int(time.time())}
    # any payload content is honored by the OPEX bridge
    if isinstance(body, dict) and "kind" not in body:
        body["kind"] = "dispatch"
    body.setdefault("app", "abyssal-assets")
    body["ts"] = int(time.time())
    pid = enqueue(body)
    return web.json_response({"dispatch": "queued", "payload_id": pid,
                               "to": COORDINATOR})


async def abyssal_dream(_req):
    """Kairos-dream: expiry a speculative crossover plan via the local cerebellum."""
    # neuro: queue a 'dream' payload for the core to ingest when it wakes
    pid = enqueue({"kind": "kairos-dream", "app": "abyssal-assets",
                   "spec": "CrossOver: Abyssal hat market <> Nessie Night City sighting",
                   "ts": int(time.time())})
    return web.json_response({"dream": "sealed", "payload_id": pid})


def register_abyssal_routes(app: web.Application):
    """Mount Abyssal edge endpoints onto the Lilith aiohttp app."""
    app.router.add_get("/api/abyssal/status", abyssal_status)
    app.router.add_get("/api/abyssal/nessie", abyssal_nessie)
    app.router.add_post("/api/abyssal/dispatch", abyssal_dispatch)
    return app


if __name__ == "__main__":
    # standalone smoke test
    import sys
    print(json.dumps({**ABYSSAL, "coordinator": COORDINATOR,
                      "route_suffix": "/api/abyssal/*"}, indent=2))