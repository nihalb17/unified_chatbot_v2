"""
Shared in-memory stores for HTTP chat and voice WebSocket.

_session_store: orchestrator persistence (LangGraph session fields)
_session_message_log: full [{role, content}, ...] for run_orchestrator history
"""

# { session_id: orchestrator session dict | None }
_session_store: dict = {}

# { session_id: [ {"role": "user"|"assistant", "content": str}, ... ] }
_session_message_log: dict[str, list[dict]] = {}
