"""
Phase 3 — Orchestrator Agent: LangGraph Construction

Builds and compiles the StateGraph. Exports run_orchestrator() which
is the single entry point for the API and test suite.

Graph structure (Phase 4 extended):
  detect_intent  (entry point)
    ├─ (theme)   ──▶ check_theme
    │               ├─ (match)           ──▶ generate_response
    │               ├─ (match+escalation) ──▶ collect_booking_topic
    │               └─ (no_match)        ──▶ detect_escalation
    │                                       ├─ (escalation) ──▶ collect_booking_topic
    │                                       └─ (no)         ──▶ collect_booking_topic
    ├─ (faq)     ──▶ detect_escalation
    │               ├─ (escalation) ──▶ collect_booking_topic
    │               └─ (no)         ──▶ rewrite_query ──▶ call_faq_agent ──▶ generate_response
    ├─ (booking) ──▶ collect_booking_topic
    ├─ (cancel_or_reschedule) ──▶ generate_response
    ├─ (confirmation_pending) ──▶ detect_confirmation_response
    └─ (other)   ──▶ classify_out_of_scope
                       ├─ (investment_adjacent) ──▶ collect_booking_topic
                       └─ (unrelated)          ──▶ generate_response

  collect_booking_topic
    ├─ (need topic)  ──▶ generate_response
    └─ (have topic)  ──▶ collect_booking_datetime
                          ├─ (complete)   ──▶ emit_booking_request
                          └─ (incomplete) ──▶ generate_response

  emit_booking_request ──▶ check_slot_availability
    ├─ (available)   ──▶ request_final_confirmation ──▶ generate_response
    └─ (unavailable) ──▶ suggest_alternative_slot   ──▶ generate_response

  detect_confirmation_response
    ├─ (confirmed)    ──▶ generate_booking_code ──▶ execute_booking
    │                     ──▶ close_chat ──▶ generate_response
    ├─ (change_slot)  ──▶ check_slot_availability
    ├─ (change_topic) ──▶ collect_booking_topic
    ├─ (exit)         ──▶ generate_response
    └─ (ambiguous)    ──▶ generate_response

  generate_response ──▶ END
"""

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from state import OrchestratorState
from nodes import (
    detect_escalation_node,
    detect_intent_node,
    check_theme_node,
    rewrite_query_node,
    call_faq_agent_node,
    collect_booking_topic_node,
    collect_booking_datetime_node,
    emit_booking_request_node,
    generate_response_node,
    # Phase 4 nodes
    check_slot_availability_node,
    suggest_alternative_slot_node,
    request_final_confirmation_node,
    detect_confirmation_response_node,
    generate_booking_code_node,
    execute_booking_node,
    close_chat_node,
    classify_out_of_scope_node,
    detect_slot_acceptance_node,
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))


# ================================================================== #
# Routing / Conditional Edge Functions                                #
# ================================================================== #

def _route_after_escalation(state: OrchestratorState) -> str:
    """Route after detect_escalation (reached from theme-miss or faq paths).
    - Escalation triggered → booking
    - No escalation + faq intent → continue to FAQ pipeline
    - No escalation + theme miss → booking (theme miss always leads to booking)
    """
    if state.get("escalation_triggered"):
        return "booking"
    if state.get("last_intent") == "faq":
        return "faq"
    return "booking"  # theme miss or other → booking


def _route_after_intent(state: OrchestratorState) -> str:
    intent = state.get("last_intent", "other")
    if intent == "theme":
        return "theme"
    if intent == "faq":
        return "faq"
    if intent == "booking":
        return "booking"
    if intent == "confirmation_pending":
        return "confirmation_pending"
    if intent == "slot_acceptance_pending":
        return "slot_acceptance_pending"
    if intent == "cancel_or_reschedule":
        return "cancel_or_reschedule"
    return "other"


def _route_after_slot_acceptance(state: OrchestratorState) -> str:
    """After detect_slot_acceptance: accepted → confirm, rejected → ask again."""
    ap = state.get("active_path")
    if ap == "slot_accepted":
        return "accepted"
    return "rejected"


def _route_after_theme(state: OrchestratorState) -> str:
    """After check_theme: route based on match result and escalation signals.
    - theme_match_escalation: user matched a theme but also wants a human → booking
    - match: theme matched, no escalation → respond with theme info
    - check_escalation: no theme match → check escalation before booking
    """
    ap = state.get("active_path")
    if ap == "theme_match_escalation":
        return "escalation"
    if state.get("theme_match"):
        return "match"
    return "check_escalation"


def _route_after_topic(state: OrchestratorState) -> str:
    """After collect_booking_topic: ask user for topic or proceed to datetime."""
    ap = state.get("active_path", "")
    if ap in ("booking_need_topic", "theme_miss_need_topic", "escalation_need_topic"):
        return "ask"
    return "proceed"


def _route_after_datetime(state: OrchestratorState) -> str:
    return "complete" if state.get("active_path") == "booking_complete" else "incomplete"


def _route_after_slot_check(state: OrchestratorState) -> str:
    """After check_slot_availability: available → confirm, unavailable → suggest alternative."""
    if state.get("active_path") == "slot_available":
        return "available"
    return "unavailable"


def _route_after_confirmation(state: OrchestratorState) -> str:
    """After detect_confirmation_response: route based on user's response."""
    ap = state.get("active_path", "")
    if ap == "confirmation_confirmed":
        return "confirmed"
    if ap == "confirmation_change_slot":
        return "change_slot"
    if ap == "confirmation_change_topic":
        return "change_topic"
    if ap == "confirmation_exit":
        return "exit"
    return "ambiguous"  # confirmation_ambiguous


def _route_after_classify_out_of_scope(state: OrchestratorState) -> str:
    """After classify_out_of_scope: investment_adjacent → booking, unrelated → respond."""
    if state.get("active_path") == "out_of_scope_investment":
        return "investment_adjacent"
    return "unrelated"


# ================================================================== #
# Graph Construction                                                   #
# ================================================================== #

def _build_graph() -> StateGraph:
    builder = StateGraph(OrchestratorState)

    # Register all nodes
    builder.add_node("detect_escalation", detect_escalation_node)
    builder.add_node("detect_intent", detect_intent_node)
    builder.add_node("check_theme", check_theme_node)
    builder.add_node("rewrite_query", rewrite_query_node)
    builder.add_node("call_faq_agent", call_faq_agent_node)
    builder.add_node("collect_booking_topic", collect_booking_topic_node)
    builder.add_node("collect_booking_datetime", collect_booking_datetime_node)
    builder.add_node("emit_booking_request", emit_booking_request_node)
    builder.add_node("generate_response", generate_response_node)

    # Phase 4 nodes
    builder.add_node("check_slot_availability", check_slot_availability_node)
    builder.add_node("suggest_alternative_slot", suggest_alternative_slot_node)
    builder.add_node("request_final_confirmation", request_final_confirmation_node)
    builder.add_node("detect_confirmation_response", detect_confirmation_response_node)
    builder.add_node("generate_booking_code", generate_booking_code_node)
    builder.add_node("execute_booking", execute_booking_node)
    builder.add_node("close_chat", close_chat_node)
    builder.add_node("classify_out_of_scope", classify_out_of_scope_node)
    builder.add_node("detect_slot_acceptance", detect_slot_acceptance_node)

    # Entry point — detect_intent first so theme check runs before escalation
    builder.set_entry_point("detect_intent")

    # ── detect_intent → pillar routing ──
    builder.add_conditional_edges(
        "detect_intent",
        _route_after_intent,
        {
            "theme": "check_theme",
            "faq": "detect_escalation",
            "booking": "collect_booking_topic",
            "confirmation_pending": "detect_confirmation_response",
            "slot_acceptance_pending": "detect_slot_acceptance",
            "cancel_or_reschedule": "generate_response",
            "other": "classify_out_of_scope",
        },
    )

    # ── classify_out_of_scope ──
    builder.add_conditional_edges(
        "classify_out_of_scope",
        _route_after_classify_out_of_scope,
        {
            "investment_adjacent": "collect_booking_topic",
            "unrelated": "generate_response",
        },
    )

    # ── check_theme ──
    builder.add_conditional_edges(
        "check_theme",
        _route_after_theme,
        {
            "match": "generate_response",
            "escalation": "collect_booking_topic",
            "check_escalation": "detect_escalation",
        },
    )

    # ── detect_escalation (reached from theme-miss or faq paths) ──
    builder.add_conditional_edges(
        "detect_escalation",
        _route_after_escalation,
        {
            "booking": "collect_booking_topic",
            "faq": "rewrite_query",
        },
    )

    # FAQ pipeline: linear chain
    builder.add_edge("rewrite_query", "call_faq_agent")
    builder.add_edge("call_faq_agent", "generate_response")

    # Booking pipeline — topic & datetime collection
    # We always run datetime collection even if topic is missing, 
    # to ensure we capture all info in the first turn.
    builder.add_edge("collect_booking_topic", "collect_booking_datetime")

    builder.add_conditional_edges(
        "collect_booking_datetime",
        _route_after_datetime,
        {"complete": "emit_booking_request", "incomplete": "generate_response"},
    )

    # ── Phase 4: Slot checking & confirmation ──
    # emit_booking_request now goes to slot checking instead of generate_response
    builder.add_edge("emit_booking_request", "check_slot_availability")

    builder.add_conditional_edges(
        "check_slot_availability",
        _route_after_slot_check,
        {
            "available": "request_final_confirmation",
            "unavailable": "suggest_alternative_slot",
        },
    )

    builder.add_edge("suggest_alternative_slot", "generate_response")
    builder.add_edge("request_final_confirmation", "generate_response")

    # ── detect_slot_acceptance ──
    builder.add_conditional_edges(
        "detect_slot_acceptance",
        _route_after_slot_acceptance,
        {
            "accepted": "request_final_confirmation",
            "rejected": "generate_response",
        },
    )

    # ── Phase 4: Confirmation response ──
    builder.add_conditional_edges(
        "detect_confirmation_response",
        _route_after_confirmation,
        {
            "confirmed": "generate_booking_code",
            "change_slot": "check_slot_availability",
            "change_topic": "collect_booking_topic",
            "exit": "generate_response",
            "ambiguous": "generate_response",
        },
    )

    # Booking execution pipeline
    builder.add_edge("generate_booking_code", "execute_booking")
    builder.add_edge("execute_booking", "close_chat")
    builder.add_edge("close_chat", "generate_response")

    # All paths converge at generate_response → END
    builder.add_edge("generate_response", END)

    return builder.compile()


# Compile once at import time (singleton)
_orchestrator_graph = _build_graph()


# ================================================================== #
# Public Entry Point                                                   #
# ================================================================== #

def run_orchestrator(
    user_input: str,
    conversation_history: list,
    session_state: dict | None = None,
) -> tuple[dict, dict]:
    """
    Run one turn of the Orchestrator Agent.

    Args:
        user_input:           The user's latest message.
        conversation_history: Full list of {role, content} dicts (all prior turns).
        session_state:        Persisted fields from the previous turn (or None for first turn).

    Returns:
        (response_dict, updated_session_state)
        response_dict has keys: text, links, type
    """
    if session_state is None:
        session_state = {}

    # Restore persistent fields from session
    initial_state: OrchestratorState = {
        # Turn inputs
        "user_input": user_input,
        "conversation_history": conversation_history,

        # Restored from session (persist across turns)
        "last_intent": session_state.get("last_intent"),
        "current_scheme": session_state.get("current_scheme"),
        "current_concept": session_state.get("current_concept"),
        "in_flight_booking": session_state.get(
            "in_flight_booking", {"topic": None, "date": None, "time": None}
        ),

        # Phase 4: persisted state
        "active_path": session_state.get("active_path"),
        "slot_check_result": session_state.get("slot_check_result"),
        "booking_code": session_state.get("booking_code"),
        "booking_artifacts": session_state.get("booking_artifacts", {}),
        "out_of_scope_category": session_state.get("out_of_scope_category"),
        "chat_closed": session_state.get("chat_closed", False),
        "confirmation_response": session_state.get("confirmation_response"),
        "theme_match": session_state.get("theme_match"),
        "pending_booking_offer": session_state.get("pending_booking_offer", False),

        # Reset each turn
        "escalation_triggered": False,
        "rewritten_query_for_faq": None,
        "faq_response": None,
        "booking_request": None,
        "booking_confirmed_by_user": None,
        "response_to_user": None,
        "response_links": [],
        "response_type": "answer",
    }

    try:
        result = _orchestrator_graph.invoke(initial_state)
    except Exception as e:
        print(f"[Orchestrator][graph] Execution failed: {e}")
        return (
            {"text": "Something went wrong. Please try again.", "links": [], "type": "error"},
            session_state,
        )

    # Build the API response
    response = {
        "text": result.get("response_to_user") or "How can I help you?",
        "links": result.get("response_links", []),
        "type": result.get("response_type", "answer"),
        "chat_closed": result.get("chat_closed", False),
        "booking_code": result.get("booking_code"),
    }

    # Persist fields needed for the next turn
    updated_session = {
        "last_intent": result.get("last_intent"),
        "current_scheme": result.get("current_scheme"),
        "current_concept": result.get("current_concept"),
        "in_flight_booking": result.get(
            "in_flight_booking", {"topic": None, "date": None, "time": None}
        ),
        # Phase 4: persist across turns for multi-turn booking flow
        "active_path": result.get("active_path"),
        "slot_check_result": result.get("slot_check_result"),
        "booking_code": result.get("booking_code"),
        "booking_artifacts": result.get("booking_artifacts", {}),
        "out_of_scope_category": result.get("out_of_scope_category"),
        "chat_closed": result.get("chat_closed", False),
        "confirmation_response": result.get("confirmation_response"),
        "theme_match": result.get("theme_match"),
        "pending_booking_offer": result.get("pending_booking_offer", False),
    }

    return response, updated_session
