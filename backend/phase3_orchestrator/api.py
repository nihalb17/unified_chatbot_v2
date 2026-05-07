"""
Phase 3 — Orchestrator Agent: FastAPI Server (port 8002)

Single endpoint: POST /api/chat
- Accepts { message, history, session_id }
- Returns  { text, links, type, session_id }

Session state is maintained in-memory keyed by session_id.
A new session_id is assigned on first call; the client must echo
it back on every subsequent call to maintain conversation state.
"""

import os
import uuid
import asyncio
import httpx
import requests
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from graph import run_orchestrator
from meetings_log import load_log, search_appointments, find_by_code
from google_workspace_mcp import get_workspace_mcp
from stores import _session_message_log, _session_store
from availability_policy import load_policy, policy_to_dict, save_policy

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

app = FastAPI(title="Phase 3 — Orchestrator Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================================== #
# Request / Response Models                                           #
# ================================================================== #

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    session_id: str | None = None


class SendBookingDetailsRequest(BaseModel):
    booking_code: str
    email: str


# ================================================================== #
# Endpoints                                                            #
# ================================================================== #

@app.get("/")
def root():
    """Root endpoint for Render health checks and service info."""
    return {
        "message": "Phase 3 — Orchestrator Agent API is running.",
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health",
            "status": "/api/system/status"
        }
    }

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for the user portal.
    Runs one turn of the Orchestrator Agent and returns the reply.
    """
    # Resolve or create session (accept client-provided id for voice + chat parity)
    session_id = request.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    if session_id not in _session_store:
        _session_store[session_id] = None  # Will be initialised inside run_orchestrator

    session_state = _session_store.get(session_id)

    # Convert Pydantic ChatMessage objects to plain dicts
    history_dicts = [{"role": m.role, "content": m.content} for m in request.history]

    # Run one turn
    response, updated_session = run_orchestrator(
        user_input=request.message,
        conversation_history=history_dicts,
        session_state=session_state,
    )

    # Persist session for next turn
    _session_store[session_id] = updated_session

    # Keep server log aligned with client history for voice WebSocket turns
    _session_message_log[session_id] = history_dicts + [
        {"role": "user", "content": request.message},
        {"role": "assistant", "content": response.get("text") or ""},
    ]

    return {**response, "session_id": session_id}


@app.websocket("/voice/ws")
async def voice_websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket parameter must be typed as WebSocket or FastAPI rejects the handshake (403)."""
    from phase5_voice.ws_handler import handle_voice_websocket

    await handle_voice_websocket(websocket)


@app.get("/api/health")
def health():
    """Basic health check."""
    return {"status": "ok", "service": "phase3-orchestrator", "port": 8002}


# ================================================================== #
# System Status & Refresh Proxy (For Auto-Pilot Loader)              #
# Background polling approach: avoids blocking on cold-starting        #
# Render services (which can take 30-60s to wake up).                 #
# ================================================================== #

from urllib.parse import urlparse

def _base_from_url(full_url: str, fallback: str) -> str:
    """Strip path/query from a full URL, leaving only scheme + host."""
    try:
        p = urlparse(full_url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return fallback

PHASE1_BASE = _base_from_url(
    os.getenv("REVIEW_AGENT_URL", ""),
    os.getenv("PHASE1_URL", "http://127.0.0.1:8000"),
).rstrip("/")

PHASE2_BASE = _base_from_url(
    os.getenv("FAQ_AGENT_URL", ""),
    os.getenv("PHASE2_URL", "http://127.0.0.1:8001"),
).rstrip("/")

print(f"[SystemProxy] Phase1 base: {PHASE1_BASE}")
print(f"[SystemProxy] Phase2 base: {PHASE2_BASE}")

# In-memory session tracking — resets on every backend boot
_initial_refresh_triggered = False
_definitions_refresh_triggered = False

# In-memory cache — updated every 20s by the background loop
_status_cache: dict = {
    "cache_initialized": False,
    "has_data": False,
    "is_running": False,
    "phase1_ready": False,
    "phase1_running": False,
    "factsheets_ready": False,
    "factsheets_running": False,
    "definitions_ready": False,
    "definitions_running": False,
}

async def _fetch_phase1_status(client: httpx.AsyncClient) -> dict:
    """Async check of Phase 1 (Reviews)."""
    result = {"phase1_ready": False, "phase1_running": False}
    try:
        r = await client.get(f"{PHASE1_BASE}/api/reviews/themes")
        if r.status_code == 200:
            themes = r.json().get("themes", [])
            result["phase1_ready"] = len(themes) > 0
    except Exception as e:
        print(f"[SystemStatus] Phase 1 themes error: {type(e).__name__}")
    try:
        rs = await client.get(f"{PHASE1_BASE}/api/reviews/status")
        if rs.status_code == 200:
            result["phase1_running"] = bool(rs.json().get("running"))
    except Exception as e:
        print(f"[SystemStatus] Phase 1 status error: {type(e).__name__}")
    return result

async def _fetch_phase2_status(client: httpx.AsyncClient) -> dict:
    """Async check of Phase 2 (Factsheets + Definitions)."""
    result = {
        "factsheets_ready": False, "factsheets_running": False,
        "definitions_ready": False, "definitions_running": False,
    }
    try:
        r = await client.get(f"{PHASE2_BASE}/api/faqs/status")
        if r.status_code == 200:
            data = r.json()
            fs = data.get("factsheets", {})
            df = data.get("definitions", {})
            result["factsheets_ready"] = bool(fs.get("last_refreshed"))
            result["factsheets_running"] = bool(fs.get("running"))
            result["definitions_ready"] = bool(df.get("last_refreshed"))
            result["definitions_running"] = bool(df.get("running"))
        else:
            print(f"[SystemStatus] Phase 2 returned HTTP {r.status_code}")
    except Exception as e:
        print(f"[SystemStatus] Phase 2 error: {type(e).__name__}")
    return result

async def _update_status_cache():
    """Poll both phases concurrently and update the in-memory cache."""
    global _status_cache
    # 90s timeout: enough for a cold Render instance to wake up
    async with httpx.AsyncClient(timeout=90.0) as client:
        p1, p2 = await asyncio.gather(
            _fetch_phase1_status(client),
            _fetch_phase2_status(client),
        )
    merged = {**p1, **p2}
    merged["is_running"] = (
        merged["phase1_running"]
        or merged["factsheets_running"]
        or merged["definitions_running"]
    )
    
    # If the pipelines are already running, we consider the refresh "triggered" for this session
    global _initial_refresh_triggered, _definitions_refresh_triggered
    if merged["is_running"]:
        _initial_refresh_triggered = True
    if merged["definitions_running"]:
        _definitions_refresh_triggered = True

    merged["has_data"] = (
        merged["phase1_ready"]
        and merged["factsheets_ready"]
        and merged["definitions_ready"]
        and _initial_refresh_triggered
        and _definitions_refresh_triggered  # Ensure full sequence completion
    )
    merged["cache_initialized"] = True  # Mark that at least one real check has completed
    _status_cache = merged
    print(f"[SystemStatus] Cache updated: {merged}")

async def _background_status_loop():
    """Continuously refresh the status cache every 20 seconds."""
    while True:
        try:
            await _update_status_cache()
        except Exception as e:
            print(f"[SystemStatus] Background loop error: {e}")
        await asyncio.sleep(20)

@app.on_event("startup")
async def start_background_status_loop():
    """Launch the background status polling loop on app startup."""
    asyncio.create_task(_background_status_loop())
    print("[SystemStatus] Background polling loop started.")

@app.get("/api/system/status")
def get_system_status():
    """Returns the cached system status — always responds instantly."""
    return _status_cache

@app.post("/api/system/refresh")
async def system_refresh():
    """Triggers Phase 1 and Phase 2 Factsheets concurrently."""
    global _initial_refresh_triggered, _definitions_refresh_triggered
    _initial_refresh_triggered = True
    _definitions_refresh_triggered = False # Reset for the new sequence
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        results = await asyncio.gather(
            client.post(f"{PHASE1_BASE}/api/reviews/refresh"),
            client.post(f"{PHASE2_BASE}/api/faqs/factsheets/refresh"),
            return_exceptions=True,
        )
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            label = "Phase 1" if i == 0 else "Phase 2 Factsheets"
            print(f"[SystemRefresh] {label} trigger error: {type(r).__name__}")
        else:
            label = "Phase 1" if i == 0 else "Phase 2 Factsheets"
            print(f"[SystemRefresh] {label} triggered: HTTP {r.status_code}")
    # Force an immediate cache refresh after triggering
    asyncio.create_task(_update_status_cache())
    return {"status": "refreshing"}

@app.post("/api/system/refresh/definitions")
async def system_refresh_definitions():
    """Triggers Phase 2 Definitions."""
    global _initial_refresh_triggered
    _initial_refresh_triggered = True
    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            r = await client.post(f"{PHASE2_BASE}/api/faqs/definitions/refresh")
            print(f"[SystemRefresh] Definitions triggered: HTTP {r.status_code}")
        except Exception as e:
            print(f"[SystemRefresh] Definitions trigger error: {type(e).__name__}")
    asyncio.create_task(_update_status_cache())
    return {"status": "refreshing_definitions"}


# ================================================================== #
# Phase 4 — Appointments API (for internal dashboard)                #
# ================================================================== #

@app.get("/api/appointments")
def get_appointments():
    """Return all booked appointments from the meetings log."""
    appointments = load_log()
    return {"appointments": appointments, "count": len(appointments)}


@app.get("/api/appointments/search")
def search_appointments_endpoint(q: str = ""):
    """Search appointments by booking code or topic.

    Query params:
        q: Search string (partial match on booking code or topic)
    """
    if not q.strip():
        return {"appointments": [], "count": 0}
    results = search_appointments(q)
    return {"appointments": results, "count": len(results)}


@app.post("/api/send-booking-details")
def send_booking_details(request: SendBookingDetailsRequest):
    """Send booking confirmation details to the user's email.

    This is a user-initiated, optional action triggered by the
    "Send me the booking details" button after a successful booking.
    Single-shot: can only be called once per booking code.
    """
    entry = find_by_code(request.booking_code)
    if not entry:
        return {"success": False, "error": "Booking not found"}

    try:
        mcp = get_workspace_mcp()
        result = mcp.send_user_booking_email(
            recipient=request.email,
            topic=entry.get("topic", ""),
            booking_code=request.booking_code,
            date_str=entry.get("date") or "",
            time_str=entry.get("time") or "",
        )
        return {"success": True, "recipient": result["recipient"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ================================================================== #
# Slot Configuration API (internal dashboard "Meeting Slot Configuration") #
# ================================================================== #


class SlotConfigPayload(BaseModel):
    work_start: str
    work_end: str
    lunch_start: str = ""
    lunch_end: str = ""
    gap_mins: int = 0
    # Monday = 0 … Sunday = 6 (datetime.weekday). Required so a missing field
    # cannot silently fall back to Mon–Fri and wipe Sat/Sun from disk.
    work_weekdays: list[int]
    holidays: list[str] = []


@app.get("/api/admin/slot-config")
def get_slot_config():
    """Return the current meeting slot configuration."""
    return policy_to_dict(load_policy())


@app.put("/api/admin/slot-config")
def update_slot_config(payload: SlotConfigPayload):
    """Validate and persist the meeting slot configuration.

    Returns 400 with a precise reason when validation fails so the dashboard
    can show it to the user instead of silently saving a broken config.
    """
    try:
        # Explicit dict so persistence never depends on model_dump edge cases.
        data = {
            "work_start": payload.work_start,
            "work_end": payload.work_end,
            "lunch_start": (payload.lunch_start or "").strip(),
            "lunch_end": (payload.lunch_end or "").strip(),
            "gap_mins": int(payload.gap_mins),
            "work_weekdays": [int(x) for x in payload.work_weekdays],
            "holidays": list(payload.holidays),
        }
        saved = save_policy(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return policy_to_dict(saved)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
