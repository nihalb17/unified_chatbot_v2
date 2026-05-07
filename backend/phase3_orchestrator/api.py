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
# ================================================================== #

# Derive base service URLs from the existing Render env vars so we
# don't need to add new variables to the Render dashboard.
# REVIEW_AGENT_URL  e.g. https://groww-phase1-reviews.onrender.com/api/reviews/themes
# FAQ_AGENT_URL     e.g. https://groww-phase2-rag.onrender.com/api/chat
def _base_from_url(full_url: str, fallback: str) -> str:
    """Strip path/query from a full URL, leaving only scheme + host."""
    try:
        from urllib.parse import urlparse
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

@app.get("/api/system/status")
def get_system_status():
    """Pings Phase 1 and Phase 2 to determine if data exists and if pipelines are running."""
    status = {
        "has_data": False,
        "is_running": False,
        "phase1_ready": False,
        "phase1_running": False,
        "factsheets_ready": False,
        "factsheets_running": False,
        "definitions_ready": False,
        "definitions_running": False,
    }
    
    # Check Phase 1 (Reviews)
    try:
        r1 = requests.get(f"{PHASE1_BASE}/api/reviews/themes", timeout=8)
        if r1.status_code == 200:
            themes = r1.json().get("themes", [])
            status["phase1_ready"] = len(themes) > 0
            
        r1_status = requests.get(f"{PHASE1_BASE}/api/reviews/status", timeout=8)
        if r1_status.status_code == 200:
            if r1_status.json().get("running"):
                status["is_running"] = True
                status["phase1_running"] = True
    except Exception as e:
        print(f"[SystemStatus] Phase 1 check error: {e}")

    # Check Phase 2 (Factsheets & Definitions)
    try:
        r2 = requests.get(f"{PHASE2_BASE}/api/faqs/status", timeout=8)
        if r2.status_code == 200:
            data = r2.json()
            fs = data.get("factsheets", {})
            df = data.get("definitions", {})
            
            status["factsheets_ready"] = bool(fs.get("last_refreshed"))
            status["definitions_ready"] = bool(df.get("last_refreshed"))
                
            if fs.get("running"):
                status["is_running"] = True
                status["factsheets_running"] = True
                
            if df.get("running"):
                status["is_running"] = True
                status["definitions_running"] = True
        else:
            print(f"[SystemStatus] Phase 2 returned HTTP {r2.status_code}")
    except Exception as e:
        print(f"[SystemStatus] Phase 2 check error: {e}")

    # has_data is only true when ALL three pipelines have produced data
    status["has_data"] = (
        status["phase1_ready"]
        and status["factsheets_ready"]
        and status["definitions_ready"]
    )
        
    return status

@app.post("/api/system/refresh")
def system_refresh():
    """Triggers Phase 1 and Phase 2 Factsheets (Definitions triggered sequentially later)."""
    # Trigger Phase 1
    try:
        requests.post(f"{PHASE1_BASE}/api/reviews/refresh", timeout=8)
    except Exception as e:
        print(f"[SystemRefresh] Phase 1 trigger error: {e}")
        
    # Trigger Phase 2 Factsheets
    try:
        requests.post(f"{PHASE2_BASE}/api/faqs/factsheets/refresh", timeout=8)
    except Exception as e:
        print(f"[SystemRefresh] Phase 2 Factsheets trigger error: {e}")
        
    return {"status": "refreshing"}

@app.post("/api/system/refresh/definitions")
def system_refresh_definitions():
    """Triggers Phase 2 Definitions sequentially."""
    try:
        requests.post(f"{PHASE2_BASE}/api/faqs/definitions/refresh", timeout=8)
    except Exception as e:
        print(f"[SystemRefresh] Phase 2 Definitions trigger error: {e}")
        
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
