"""
Phase 3 — Orchestrator Agent: Shared State Schema

Every LangGraph node reads from and writes to a single OrchestratorState object.
State is initialized fresh each turn from the session store, then passed through
the graph and persisted back to the session store for the next turn.
"""

from typing import TypedDict, Optional, List


class OrchestratorState(TypedDict):
    # ------------------------------------------------------------------ #
    # Core Turn Inputs                                                     #
    # ------------------------------------------------------------------ #
    user_input: str
    conversation_history: List[dict]  # [{role: str, content: str}, ...]

    # ------------------------------------------------------------------ #
    # Intent & Entity Detection                                            #
    # ------------------------------------------------------------------ #
    last_intent: Optional[str]       # "faq" | "theme" | "booking" | "other"
    current_scheme: Optional[str]    # Most recently identified MF scheme name
    current_concept: Optional[str]   # Most recently discussed MF concept/term
    escalation_triggered: bool       # True if user wants to talk to a human

    # ------------------------------------------------------------------ #
    # Theme Pillar (Pillar 1)                                              #
    # ------------------------------------------------------------------ #
    theme_match: Optional[dict]      # Full matched theme object from KB, or None

    # ------------------------------------------------------------------ #
    # FAQ Pillar (Pillar 2)                                                #
    # ------------------------------------------------------------------ #
    rewritten_query_for_faq: Optional[str]
    faq_response: Optional[dict]     # {type: str, text: str, links: list}

    # ------------------------------------------------------------------ #
    # Booking Pillar (Pillar 3)                                            #
    # ------------------------------------------------------------------ #
    in_flight_booking: dict          # {topic: str|None, date: str|None, time: str|None}
    booking_request: Optional[dict]  # Final structured request once all fields collected

    # ------------------------------------------------------------------ #
    # Phase 4 — Booking Execution                                          #
    # ------------------------------------------------------------------ #
    slot_check_result: Optional[dict]       # {available, conflicting_events, suggested_alternative}
    booking_confirmed_by_user: Optional[bool]
    booking_code: Optional[str]              # 4-digit code generated after confirmation
    booking_artifacts: dict                  # Tracks side-effect completion:
                                             # {calendar_event_id, broker_email_sent,
                                             #  google_doc_id, google_doc_url, dashboard_log_id}
    out_of_scope_category: Optional[str]     # "investment_adjacent" | "unrelated"
    chat_closed: bool                        # True after booking is complete

    # ------------------------------------------------------------------ #
    # Confirmation response (detected on next turn)                        #
    # ------------------------------------------------------------------ #
    confirmation_response: Optional[str]     # "confirmed"|"change_slot"|"change_topic"|"exit"|"ambiguous"

    # ------------------------------------------------------------------ #
    # Pending booking offer (set when last reply offered to book a call)  #
    # Used to intercept short affirmative/negative replies on next turn   #
    # so they don't get re-routed back through FAQ / theme / out-of-scope #
    # and produce the same "shall I book?" message twice.                 #
    # ------------------------------------------------------------------ #
    pending_booking_offer: Optional[bool]

    # ------------------------------------------------------------------ #
    # Response (output of generate_response node)                          #
    # ------------------------------------------------------------------ #
    response_to_user: Optional[str]
    response_links: List[dict]
    response_type: str  # "answer"|"clarify"|"refuse"|"theme"|"booking"|"booking_collecting"|"error"

    # ------------------------------------------------------------------ #
    # Routing Signal                                                       #
    # ------------------------------------------------------------------ #
    active_path: Optional[str]
    # Possible values:
    #   faq_answered, faq_clarify, faq_refused, faq_error
    #   theme_match
    #   theme_miss_need_topic, theme_miss_have_topic
    #   booking_need_topic, booking_have_topic
    #   escalation_need_topic, escalation_have_topic
    #   booking_need_both, booking_need_date, booking_need_time
    #   booking_complete, booking_confirmed
    #   slot_available, slot_unavailable
    #   awaiting_confirmation
    #   confirmation_confirmed, confirmation_change_slot,
    #   confirmation_change_topic, confirmation_exit, confirmation_ambiguous
    #   booking_executed, booking_execution_failed
    #   out_of_scope_investment, out_of_scope_unrelated
    #   cancel_or_reschedule
    #   other, error
