"""Run one orchestrator turn for voice; updates shared session + message log."""

from graph import run_orchestrator
from stores import _session_message_log, _session_store


def run_voice_chat_turn(session_id: str, user_text: str) -> dict:
    """
    Same core logic as POST /api/chat: one run_orchestrator turn.
    Returns API-shaped dict: text, links, type, chat_closed, booking_code.
    """
    if session_id not in _session_store:
        _session_store[session_id] = None

    history = list(_session_message_log.get(session_id, []))
    session_state = _session_store.get(session_id)

    response, updated_session = run_orchestrator(
        user_input=user_text.strip(),
        conversation_history=history,
        session_state=session_state,
    )
    _session_store[session_id] = updated_session

    reply = response.get("text") or ""
    _session_message_log[session_id] = history + [
        {"role": "user", "content": user_text.strip()},
        {"role": "assistant", "content": reply},
    ]
    return response


def resolve_voice_response(response: dict) -> tuple[str, bool, dict | None]:
    """Map orchestrator response to (spoken_reply, call_ended, call_ended_payload)."""
    reply = response.get("text") or ""
    if response.get("chat_closed"):
        payload = {
            "action": "book",
            "headline": "Session ended",
            "message": reply,
            "booking_code": response.get("booking_code"),
            "scheduled_display": None,
            "banner_text": reply,
        }
        return reply, True, payload
    return reply, False, None
