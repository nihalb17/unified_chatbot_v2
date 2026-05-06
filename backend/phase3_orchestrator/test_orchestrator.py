"""
Phase 3 — Orchestrator Agent: Basic Test Cases

These are integration tests that call run_orchestrator() directly.
They make real LLM calls (Groq) so they require:
  1. GROQ_API_KEY_ORCHESTRATOR set in .env
  2. Phase 2 FAQ agent running on port 8001 (for FAQ path tests)

Run from the phase3_orchestrator directory:
    python test_orchestrator.py

Each test prints a pass/fail verdict plus the actual bot response for inspection.
"""

import os
import sys

# Allow imports from this directory
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from graph import run_orchestrator

# ------------------------------------------------------------------ #
# Test helpers                                                         #
# ------------------------------------------------------------------ #

_PASS = 0
_FAIL = 0


def _assert(condition: bool, test_name: str, detail: str = ""):
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  [PASS] {test_name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {test_name}" + (f" — {detail}" if detail else ""))


def _run(user_input: str, history: list = None, session: dict = None):
    """Shortcut to run one turn and print the response."""
    resp, updated_session = run_orchestrator(
        user_input=user_input,
        conversation_history=history or [],
        session_state=session,
    )
    print(f"    Bot ({resp['type']}): {resp['text'][:120]}{'...' if len(resp['text']) > 120 else ''}")
    return resp, updated_session


# ================================================================== #
# TEST 1 — FAQ Path: direct factsheet question                        #
# ================================================================== #

def test_faq_direct():
    print("\n[TEST 1] FAQ path — direct factsheet question")
    resp, _ = _run("What is the NAV of Axis Bluechip Fund?")
    # Should route to FAQ agent; type is answer, refuse, or clarify (not booking/theme/error)
    _assert(
        resp["type"] in ("answer", "refuse", "clarify"),
        "Response type is FAQ-related",
        f"got type='{resp['type']}'",
    )
    _assert(
        len(resp["text"]) > 10,
        "Response has non-empty text",
    )


# ================================================================== #
# TEST 2 — FAQ Path: reference resolution (follow-up question)        #
# ================================================================== #

def test_faq_reference_resolution():
    print("\n[TEST 2] FAQ path — reference resolution follow-up")

    # Turn 1: establish scheme
    history = []
    resp1, session = _run("What is the exit load on Axis Bluechip Fund?", history)
    history += [
        {"role": "user", "content": "What is the exit load on Axis Bluechip Fund?"},
        {"role": "assistant", "content": resp1["text"]},
    ]

    # Turn 2: vague follow-up — "it" should resolve to Axis Bluechip
    resp2, _ = _run("What about its expense ratio?", history, session)
    _assert(
        resp2["type"] in ("answer", "refuse", "clarify"),
        "Follow-up routed to FAQ agent",
        f"got type='{resp2['type']}'",
    )
    # The rewritten query or the FAQ response should mention 'expense ratio'
    _assert(
        "expense ratio" in resp2["text"].lower() or resp2["type"] in ("refuse", "clarify"),
        "Concept 'expense ratio' in response or handled",
    )


# ================================================================== #
# TEST 3 — Theme Path: known app issue                                #
# ================================================================== #

def test_theme_known_issue():
    print("\n[TEST 3] Theme path — known app issue (App Crashes)")
    resp, _ = _run("The Groww app keeps crashing every time I open it on my phone.")
    _assert(
        resp["type"] in ("theme", "booking_collecting", "booking"),
        "Routed to theme or booking path",
        f"got type='{resp['type']}'",
    )
    _assert(
        len(resp["text"]) > 10,
        "Response has non-empty text",
    )


# ================================================================== #
# TEST 4 — Escalation Path: user explicitly asks for human            #
# ================================================================== #

def test_escalation():
    print("\n[TEST 4] Escalation path — user asks to speak to an advisor")
    resp, session = _run("I want to speak to a human advisor please.")
    _assert(
        resp["type"] in ("booking_collecting", "booking"),
        "Routed to booking collection",
        f"got type='{resp['type']}'",
    )
    # Bot should ask for topic or date/time
    text_lower = resp["text"].lower()
    _assert(
        any(kw in text_lower for kw in ["topic", "date", "time", "book", "call", "schedule"]),
        "Response mentions booking-related terms",
        f"text='{resp['text'][:80]}'",
    )


# ================================================================== #
# TEST 5 — Multi-turn Booking Flow                                    #
# ================================================================== #

def test_booking_multiturn():
    print("\n[TEST 5] Multi-turn booking flow")

    history = []

    # Turn 1: explicit booking request
    resp1, session = _run("I'd like to book a call with an advisor.", history)
    history += [
        {"role": "user", "content": "I'd like to book a call with an advisor."},
        {"role": "assistant", "content": resp1["text"]},
    ]
    _assert(
        resp1["type"] in ("booking_collecting", "booking"),
        "Turn 1: routed to booking",
        f"got type='{resp1['type']}'",
    )

    # Turn 2: provide topic
    resp2, session = _run("I want to discuss exit load charges.", history, session)
    history += [
        {"role": "user", "content": "I want to discuss exit load charges."},
        {"role": "assistant", "content": resp2["text"]},
    ]
    _assert(
        resp2["type"] in ("booking_collecting", "booking"),
        "Turn 2: still in booking flow",
        f"got type='{resp2['type']}'",
    )

    # Turn 3: provide date and time
    resp3, session = _run("Tomorrow at 3 PM.", history, session)
    history += [
        {"role": "user", "content": "Tomorrow at 3 PM."},
        {"role": "assistant", "content": resp3["text"]},
    ]
    _assert(
        resp3["type"] in ("booking", "booking_collecting"),
        "Turn 3: booking advancing",
        f"got type='{resp3['type']}'",
    )

    # If booking is confirmed, check the response mentions the topic
    if resp3["type"] == "booking":
        _assert(
            "exit load" in resp3["text"].lower() or "call" in resp3["text"].lower(),
            "Booking confirmation references topic or call",
            f"text='{resp3['text'][:80]}'",
        )


# ================================================================== #
# TEST 6 — Escalation During FAQ Flow (mid-conversation)             #
# ================================================================== #

def test_escalation_during_faq():
    print("\n[TEST 6] Escalation during FAQ flow")

    history = []

    # Turn 1: FAQ question
    resp1, session = _run("What is the alpha of Mirae Asset Large Cap Fund?", history)
    history += [
        {"role": "user", "content": "What is the alpha of Mirae Asset Large Cap Fund?"},
        {"role": "assistant", "content": resp1["text"]},
    ]

    # Turn 2: escalation
    resp2, session = _run("This isn't helpful at all. I want to talk to someone.", history, session)
    _assert(
        resp2["type"] in ("booking_collecting", "booking"),
        "Turn 2: escalation routes to booking",
        f"got type='{resp2['type']}'",
    )


# ================================================================== #
# TEST 7 — General / Other Intent                                     #
# ================================================================== #

def test_general_greeting():
    print("\n[TEST 7] General greeting")
    resp, _ = _run("Hello! How are you?")
    _assert(
        resp["type"] in ("answer", "other"),
        "Greeting handled gracefully",
        f"got type='{resp['type']}'",
    )
    _assert(len(resp["text"]) > 5, "Response not empty")


# ================================================================== #
# TEST 8 — Offer-then-yes: smooth transfer to booking                 #
# ================================================================== #
# Reproduces the bug where the bot offers to book a call and the user #
# replies "yes", but the orchestrator forgets the offer and re-routes #
# the answer back through FAQ, looping the same refusal.              #
#                                                                     #
# We simulate the just-offered state directly via session_state so    #
# Phase 2 doesn't need to be running for this test.                   #
# ================================================================== #

def test_offer_then_yes():
    print("\n[TEST 8] Offer-then-yes — smooth transfer to booking")

    history = [
        {"role": "user", "content": "What is the NAV of Bandhan Small Cap Fund?"},
        {"role": "assistant", "content": "The NAV of Bandhan Small Cap Fund is Rs.52.16."},
        {"role": "user", "content": "Can I invest in it?"},
        {
            "role": "assistant",
            "content": (
                "I don't have information on that. "
                "Would you like me to book a call with an advisor who can help?"
            ),
        },
    ]
    session_after_offer = {
        "last_intent": "faq",
        "current_scheme": "Bandhan Small Cap Fund",
        "current_concept": None,
        "in_flight_booking": {"topic": None, "date": None, "time": None},
        "active_path": "faq_refused",
        "pending_booking_offer": True,
    }

    resp, updated_session = _run("yes", history, session_after_offer)
    _assert(
        resp["type"] in ("booking_collecting", "booking"),
        "Affirmative reply transfers into booking flow",
        f"got type='{resp['type']}'",
    )
    text_lower = resp["text"].lower()
    _assert(
        any(kw in text_lower for kw in ["date", "time", "when", "schedule"]),
        "Response asks for date/time (topic auto-generated, not re-asked)",
        f"text='{resp['text'][:120]}'",
    )
    _assert(
        "i don't have information" not in text_lower
        and "would you like me to book" not in text_lower,
        "No looping of the original refusal+offer",
        f"text='{resp['text'][:120]}'",
    )
    _assert(
        not updated_session.get("pending_booking_offer"),
        "pending_booking_offer flag is cleared after handling",
    )


# ================================================================== #
# TEST 9 — "Monday" must not become the topic                          #
# ================================================================== #
# When the user says "I want to book an appointment on Monday", the   #
# orchestrator must NOT treat "Monday" (a date) or "appointment" (a   #
# generic word) as the booking topic. It must ask for a real topic    #
# AND acknowledge the date so it doesn't ask for it again later.      #
# ================================================================== #

def test_monday_as_topic():
    print("\n[TEST 9] 'Monday' must not be used as the booking topic")

    resp, updated_session = _run("I want to book an appointment on Monday")
    _assert(
        resp["type"] in ("booking_collecting", "booking"),
        "Routed into booking flow",
        f"got type='{resp['type']}'",
    )

    in_flight = updated_session.get("in_flight_booking", {})
    topic = (in_flight.get("topic") or "").lower()
    _assert(
        "monday" not in topic and "appointment" not in topic,
        "'Monday' / 'appointment' rejected as topic",
        f"got topic='{in_flight.get('topic')}'",
    )

    text_lower = resp["text"].lower()
    _assert(
        "topic" in text_lower or "discuss" in text_lower or "subject" in text_lower,
        "Bot asks for the topic",
        f"text='{resp['text'][:120]}'",
    )


# ================================================================== #
# TEST 10 — Topic gating: never proceed without a topic               #
# ================================================================== #
# If the user gives date+time but no topic, the orchestrator must     #
# stop and ask for a topic, not silently book with "General inquiry". #
# ================================================================== #

def test_topic_gating():
    print("\n[TEST 10] Topic gating — never proceed without a topic")

    resp, updated_session = _run("Book a call on Monday at 4pm")
    _assert(
        resp["type"] in ("booking_collecting", "booking"),
        "Routed into booking flow",
        f"got type='{resp['type']}'",
    )

    in_flight = updated_session.get("in_flight_booking", {})
    _assert(
        not in_flight.get("topic")
        or in_flight.get("topic", "").lower()
        not in ("monday", "appointment", "call", "the call"),
        "Topic is empty or at least not a date/generic word",
        f"got topic='{in_flight.get('topic')}'",
    )

    text_lower = resp["text"].lower()
    _assert(
        "topic" in text_lower or "discuss" in text_lower or "subject" in text_lower,
        "Bot asks for the topic before confirming the booking",
        f"text='{resp['text'][:120]}'",
    )
    _assert(
        "should i book" not in text_lower and "to confirm" not in text_lower,
        "No final confirmation prompt without a topic",
        f"text='{resp['text'][:120]}'",
    )


# ================================================================== #
# TEST 11 — "Yes" must not auto-pick a date the user never said       #
# ================================================================== #
# Reproduces: the bot offers a booking, user replies "yes", and the   #
# datetime extractor hallucinates "Monday" out of the reference       #
# calendar. After the fix, in_flight.date must remain None.           #
# ================================================================== #

def test_yes_does_not_pick_a_date():
    print("\n[TEST 11] 'Yes' to a booking offer must not auto-pick a date")

    history = [
        {"role": "user", "content": "What is the NAV of Axis Liquid Fund?"},
        {"role": "assistant", "content": "The NAV of Axis Liquid Fund is Rs.3085.84."},
        {"role": "user", "content": "Can I invest in it?"},
        {
            "role": "assistant",
            "content": (
                "I don't have information on that. "
                "Would you like me to book a call with an advisor who can help?"
            ),
        },
    ]
    session_after_offer = {
        "last_intent": "faq",
        "current_scheme": "Axis Liquid Fund",
        "current_concept": None,
        "in_flight_booking": {"topic": None, "date": None, "time": None},
        "active_path": "faq_refused",
        "pending_booking_offer": True,
    }

    resp, updated_session = _run("yes", history, session_after_offer)
    in_flight = updated_session.get("in_flight_booking", {})
    _assert(
        in_flight.get("date") is None,
        "in_flight.date stays None when user only said 'yes'",
        f"got date='{in_flight.get('date')}'",
    )
    _assert(
        in_flight.get("time") is None,
        "in_flight.time stays None when user only said 'yes'",
        f"got time='{in_flight.get('time')}'",
    )
    text_lower = resp["text"].lower()
    _assert(
        "date" in text_lower or "when" in text_lower or "time" in text_lower,
        "Bot asks for date/time rather than confirming a hallucinated slot",
        f"text='{resp['text'][:120]}'",
    )
    _assert(
        "monday" not in text_lower and "to confirm" not in text_lower,
        "Bot does not surface a phantom 'Monday' or jump to confirmation",
        f"text='{resp['text'][:120]}'",
    )


# ================================================================== #
# TEST 12 — User correction must override the prior date              #
# ================================================================== #
# Reproduces: bot has tentatively set date=Monday (from a prior turn  #
# or even a hallucination). User says "no, book on Tuesday at 4:30    #
# pm". The new date+time must REPLACE Monday — not be ignored because #
# of the leading "no".                                                #
# ================================================================== #

def test_correction_overrides_prior_date():
    print("\n[TEST 12] User correction overrides a previously held date")

    # Compute the next Monday and Tuesday in IST so the test is calendar-stable.
    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo as _ZI
        now_ist = _dt.now(_ZI("Asia/Kolkata"))
    except Exception:
        now_ist = _dt.now()
    days_to_mon = (0 - now_ist.weekday()) % 7 or 7
    days_to_tue = (1 - now_ist.weekday()) % 7 or 7
    next_monday = (now_ist + _td(days=days_to_mon)).strftime("%Y-%m-%d")
    next_tuesday = (now_ist + _td(days=days_to_tue)).strftime("%Y-%m-%d")

    history = [
        {"role": "user", "content": "I'd like to book a call with an advisor."},
        {"role": "assistant", "content": "Sure, what topic?"},
        {"role": "user", "content": "Investments"},
        {
            "role": "assistant",
            "content": (
                f"Got it, I'll book a call about 'Investments' for {next_monday}. "
                "What time works best?"
            ),
        },
    ]
    session = {
        "last_intent": "booking",
        "current_scheme": None,
        "current_concept": None,
        "in_flight_booking": {
            "topic": "Investments",
            "date": next_monday,
            "time": None,
        },
        "active_path": "booking_need_time",
        "pending_booking_offer": False,
    }

    resp, updated_session = _run("no book on Tuesday 4:30 pm", history, session)
    in_flight = updated_session.get("in_flight_booking", {})
    _assert(
        in_flight.get("date") == next_tuesday,
        f"in_flight.date overridden to next Tuesday ({next_tuesday})",
        f"got date='{in_flight.get('date')}'",
    )
    _assert(
        in_flight.get("time") == "16:30",
        "in_flight.time set to 16:30",
        f"got time='{in_flight.get('time')}'",
    )


# ================================================================== #
# TEST 13 — find_next_available_slot honors business hours            #
# ================================================================== #
# Pure unit test of the slot search. Stubs the Google Calendar list   #
# call so it doesn't hit the network. Asserts the returned slot is    #
# inside Mon-Fri 09:00-18:00 IST and after the requested time.        #
# ================================================================== #

def test_find_next_available_slot_business_hours():
    print("\n[TEST 13] find_next_available_slot — business hours + skip weekends")

    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo as _ZI
        now_ist = _dt.now(_ZI("Asia/Kolkata"))
    except Exception:
        now_ist = _dt.now()

    # Pick a target on next Saturday at 11:00 IST (a weekend afternoon).
    days_to_sat = (5 - now_ist.weekday()) % 7 or 7
    saturday_11 = (now_ist + _td(days=days_to_sat)).replace(
        hour=11, minute=0, second=0, microsecond=0, tzinfo=None
    )

    from google_workspace_mcp import GoogleWorkspaceMCP

    mcp = GoogleWorkspaceMCP.__new__(GoogleWorkspaceMCP)
    mcp.calendar_service = type("S", (), {})()
    mcp.calendar_id = "primary"

    class _Stub:
        def list(self_inner, **kwargs):
            class _Req:
                def execute(_self_req):
                    return {"items": []}
            return _Req()
    mcp.calendar_service.events = lambda: _Stub()

    slot = mcp.find_next_available_slot(saturday_11)
    _assert(slot is not None, "Returns a slot when calendar is empty")
    if slot:
        s = slot["start_ist"]
        _assert(s.weekday() < 5, "Suggested slot is on a weekday", f"got weekday={s.weekday()}")
        _assert(9 <= s.hour < 18, "Suggested slot is inside 09:00-18:00 IST", f"got hour={s.hour}")
        _assert(s >= saturday_11, "Suggested slot is forward of the requested time")


# ================================================================== #
# TEST 14 — Policy gate in check_slot_availability_node              #
# ================================================================== #
# Two slim integration tests that drive the node directly. They stub  #
# the MCP and the policy so we never hit Google Calendar nor read     #
# slot_config.json. Together with test_availability_policy.py they    #
# cover: rule semantics (unit) + node wiring (integration).           #
# ================================================================== #


def _next_weekday(target_weekday: int) -> str:
    """Return the next YYYY-MM-DD that falls on target_weekday (0=Mon)."""
    from datetime import datetime as _dt, timedelta as _td

    today = _dt.now().date()
    delta = (target_weekday - today.weekday()) % 7 or 7
    return (today + _td(days=delta)).strftime("%Y-%m-%d")


def test_check_slot_node_blocks_holiday():
    print("\n[TEST 14a] check_slot_availability_node — blocks holiday")

    from unittest import mock
    import availability_policy as ap
    from nodes import check_slot_availability_node

    next_tue = _next_weekday(1)  # weekday inside working hours
    policy = ap._coerce_policy(
        {
            "work_start": "09:00",
            "work_end": "18:00",
            "lunch_start": "13:00",
            "lunch_end": "14:00",
            "gap_mins": 0,
            "holidays": [next_tue],
        }
    )

    state = {"in_flight_booking": {"date": next_tue, "time": "11:00"}}
    with mock.patch("availability_policy.load_policy", return_value=policy), mock.patch(
        "nodes._suggest_with_policy", return_value=None
    ):
        result_state = check_slot_availability_node(state)

    _assert(
        result_state["active_path"] == "slot_unavailable",
        "Holiday booking is rejected",
        f"got active_path={result_state['active_path']}",
    )
    reason = result_state["slot_check_result"].get("reason", "")
    _assert(
        "holiday" in reason.lower(),
        "Reason mentions holiday so the chatbot can show it to the user",
        f"got reason={reason!r}",
    )


def test_check_slot_node_blocks_lunch():
    print("\n[TEST 14b] check_slot_availability_node — blocks lunch overlap")

    from unittest import mock
    import availability_policy as ap
    from nodes import check_slot_availability_node

    next_tue = _next_weekday(1)
    policy = ap._coerce_policy(
        {
            "work_start": "09:00",
            "work_end": "18:00",
            "lunch_start": "13:00",
            "lunch_end": "14:00",
            "gap_mins": 0,
            "holidays": [],
        }
    )

    # 12:45-13:15 overlaps lunch [13:00, 14:00).
    state = {"in_flight_booking": {"date": next_tue, "time": "12:45"}}
    with mock.patch("availability_policy.load_policy", return_value=policy), mock.patch(
        "nodes._suggest_with_policy", return_value=None
    ):
        result_state = check_slot_availability_node(state)

    _assert(
        result_state["active_path"] == "slot_unavailable",
        "Lunch-overlapping slot is rejected",
        f"got active_path={result_state['active_path']}",
    )
    reason = result_state["slot_check_result"].get("reason", "")
    _assert(
        "lunch" in reason.lower(),
        "Reason mentions lunch",
        f"got reason={reason!r}",
    )


# ================================================================== #
# TEST 15 — Relative day words (tomorrow) deterministic fallback        #
# ================================================================== #
# Pure unit test: no LLM. Guards regression for theme-miss booking      #
# where the model returned date=null for "Tomorrow" or "tiomorrow".     #
# ================================================================== #


def test_relative_booking_date_inference_unit():
    print("\n[TEST 15] Relative booking date inference (unit)")

    from nodes import _infer_relative_booking_date

    t0, t1, t2 = "2026-05-01", "2026-05-02", "2026-05-03"
    _assert(
        _infer_relative_booking_date("Tomorrow", t0, t1, t2) == t1,
        "Tomorrow maps to tomorrow_str",
    )
    _assert(
        _infer_relative_booking_date("tiomorrow 5.30 pm", t0, t1, t2) == t1,
        "tiomorrow typo maps to tomorrow_str",
    )
    _assert(
        _infer_relative_booking_date("not tomorrow, Tuesday", t0, t1, t2) is None,
        "not tomorrow does not force a date",
    )
    _assert(
        _infer_relative_booking_date("the day after tomorrow", t0, t1, t2) == t2,
        "day after tomorrow maps correctly",
    )
    _assert(
        _infer_relative_booking_date("today at 4pm", t0, t1, t2) == t0,
        "today maps to today_str",
    )


# ================================================================== #
# TEST 14 — "KYC" after topic prompt must stay in booking pillar      #
# ================================================================== #
# Reproduces: user books for Monday, bot asks topic, user replies    #
# "KYC". Without a guard, intent LLM classifies KYC as FAQ and hits     #
# Phase 2, surfacing "knowledge base" errors instead of asking time.    #
# ================================================================== #

def test_kyc_during_booking_collection():
    print("\n[TEST 14] 'KYC' after topic prompt stays in booking flow")

    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo as _ZI
        now_ist = _dt.now(_ZI("Asia/Kolkata"))
    except Exception:
        now_ist = _dt.now()
    days_to_mon = (0 - now_ist.weekday()) % 7 or 7
    next_monday = (now_ist + _td(days=days_to_mon)).strftime("%Y-%m-%d")

    history = [
        {"role": "user", "content": "I want to book an appointment on Monday"},
        {
            "role": "assistant",
            "content": (
                f"I'd be happy to book a call with an advisor for you. "
                f"I've noted {next_monday}. What topic would you like to discuss?"
            ),
        },
    ]
    session = {
        "last_intent": "booking",
        "current_scheme": None,
        "current_concept": None,
        "in_flight_booking": {"topic": None, "date": next_monday, "time": None},
        "active_path": "booking_need_topic",
        "pending_booking_offer": False,
        "chat_closed": False,
    }

    resp, updated = _run("KYC", history, session)
    text_lower = resp["text"].lower()
    _assert(
        resp["type"] == "booking_collecting",
        "Response type is booking_collecting (not FAQ/refuse)",
        f"got type='{resp['type']}'",
    )
    _assert(
        "knowledge base" not in text_lower,
        "Did not hit FAQ / knowledge-base error path",
        f"text='{resp['text'][:120]}'",
    )
    _assert(
        "time" in text_lower or "when" in text_lower,
        "Bot asks for time (topic + date already known)",
        f"text='{resp['text'][:120]}'",
    )
    inf = updated.get("in_flight_booking", {})
    _assert(
        (inf.get("topic") or "").lower() == "kyc",
        "Topic stored as KYC",
        f"got topic='{inf.get('topic')}'",
    )


# ================================================================== #
# Run all tests                                                        #
# ================================================================== #

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3 Orchestrator — Integration Tests")
    print("=" * 60)
    print("Note: These tests make real LLM calls. Each test may take 5–15 seconds.")
    print("Requires: GROQ_API_KEY_ORCHESTRATOR in .env")
    print("Requires: Phase 2 FAQ agent on port 8001 (for FAQ tests)")
    print()

    test_faq_direct()
    test_faq_reference_resolution()
    test_theme_known_issue()
    test_escalation()
    test_booking_multiturn()
    test_escalation_during_faq()
    test_general_greeting()
    test_offer_then_yes()
    test_monday_as_topic()
    test_topic_gating()
    test_yes_does_not_pick_a_date()
    test_correction_overrides_prior_date()
    test_find_next_available_slot_business_hours()
    test_relative_booking_date_inference_unit()
    test_kyc_during_booking_collection()
    test_check_slot_node_blocks_holiday()
    test_check_slot_node_blocks_lunch()

    print()
    print("=" * 60)
    print(f"Results: {_PASS} passed, {_FAIL} failed out of {_PASS + _FAIL} assertions")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)
