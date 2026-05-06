"""
Phase 3 — Orchestrator Agent: Graph Nodes

Each function implements one focused node in the LangGraph.
All nodes take OrchestratorState and return an updated OrchestratorState.
LLM calls use GROQ_API_KEY_ORCHESTRATOR (optional GROQ_API_KEY_ORCHESTRATOR_FALLBACK
on rate limits). FAQ calls use HTTP to port 8001; the FAQ service uses
GROQ_API_KEY_FAQ_AGENT plus optional GROQ_API_KEY_FAQ_AGENT_FALLBACK.
Themes are loaded from the shared KB JSON on disk.
"""

import os
import re
import json
from typing import Optional
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import groq

from google_workspace_mcp import get_workspace_mcp
from meetings_log import code_exists as _booking_code_exists

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

# ------------------------------------------------------------------ #
# Shared LLM helpers                                                   #
# ------------------------------------------------------------------ #

# Primary model: openai/gpt-oss-120b on Groq production tier.
# - 500 t/s vs 280 t/s for llama-3.3-70b-versatile (~1.8x faster)
# - 120B params + reasoning, generally stronger than llama-3.3-70b
# - Cheaper input ($0.15 vs $0.59) and output ($0.60 vs $0.79) per 1M tokens
# Model and API-key fallbacks kick in when Groq returns rate limits.
_MODEL = "openai/gpt-oss-120b"
_FAQ_API_URL = os.getenv("FAQ_AGENT_URL", "http://127.0.0.1:8001/api/chat")
_REVIEW_API_URL = os.getenv("REVIEW_AGENT_URL", "http://127.0.0.1:8000/api/reviews/themes")
_THEMES_KB_PATH = os.path.join(os.path.dirname(__file__), "../data/themes_kb.json")


def _is_groq_rate_limit_exc(exc: BaseException) -> bool:
    """True when Groq signals throttling (string match + common SDK shapes)."""
    s = str(exc).lower()
    if "rate_limit" in s or "429" in s or "too many requests" in s:
        return True
    code = getattr(exc, "status_code", None)
    if code == 429:
        return True
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    return False


def _orchestrator_groq_keys() -> list[str]:
    keys: list[str] = []
    for env_name in ("GROQ_API_KEY_ORCHESTRATOR", "GROQ_API_KEY_ORCHESTRATOR_FALLBACK"):
        v = (os.getenv(env_name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys


def _model_fallback_chain(model: str) -> list[str]:
    models_to_try = [model]
    if model == "openai/gpt-oss-120b":
        models_to_try.append("llama-3.3-70b-versatile")
    elif model == "llama-3.3-70b-versatile":
        models_to_try.append("llama-3.1-70b-versatile")
    if "llama-3.1-8b-instant" not in models_to_try:
        models_to_try.append("llama-3.1-8b-instant")
    return models_to_try


def _llm_json(prompt: str, model: str = _MODEL) -> dict | None:
    """Call LLM, parse and return JSON. Returns None on any failure.
    Tries backup Groq API key after exhausting model fallbacks on rate limits.
    """
    keys = _orchestrator_groq_keys()
    if not keys:
        print("[Orchestrator][LLM JSON] No GROQ_API_KEY_ORCHESTRATOR configured.")
        return None
    models_to_try = _model_fallback_chain(model)
    last_error: BaseException | None = None
    for api_key in keys:
        client = groq.Groq(api_key=api_key)
        for m in models_to_try:
            try:
                response = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=m,
                    temperature=0,
                )
                text = response.choices[0].message.content.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception as e:
                last_error = e
                if _is_groq_rate_limit_exc(e):
                    print(f"[Orchestrator][LLM JSON] Rate limit on {m}, trying next...")
                    continue
                print(f"[Orchestrator][LLM JSON] Failed on {m}: {e}")
                break
    if last_error:
        print(f"[Orchestrator][LLM JSON] All keys/models failed. Last error: {last_error}")
    return None


def _llm_text(prompt: str, temperature: float = 0.3, model: str = _MODEL) -> str:
    """Call LLM and return plain text. Returns empty string on failure.
    Tries backup Groq API key after exhausting model fallbacks on rate limits.
    """
    keys = _orchestrator_groq_keys()
    if not keys:
        print("[Orchestrator][LLM text] No GROQ_API_KEY_ORCHESTRATOR configured.")
        return ""
    models_to_try = _model_fallback_chain(model)
    last_error: BaseException | None = None
    for api_key in keys:
        client = groq.Groq(api_key=api_key)
        for m in models_to_try:
            try:
                response = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=m,
                    temperature=temperature,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                if _is_groq_rate_limit_exc(e):
                    print(f"[Orchestrator][LLM text] Rate limit on {m}, trying next...")
                    continue
                print(f"[Orchestrator][LLM text] Failed on {m}: {e}")
                break
    if last_error:
        print(f"[Orchestrator][LLM text] All keys/models failed. Last error: {last_error}")
    return ""


def _load_themes() -> list:
    """Load the Themes KB via HTTP from Phase 1. Returns empty list on failure."""
    try:
        response = requests.get(_REVIEW_API_URL, timeout=10)
        if response.status_code == 200:
            return response.json().get("themes", [])
    except Exception as e:
        print(f"[Orchestrator][Themes] HTTP Load failed: {e}. Falling back to local file.")
    
    # Fallback to local disk for local development testing
    try:
        if os.path.exists(_THEMES_KB_PATH):
            with open(_THEMES_KB_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("themes", [])
    except Exception as e:
        print(f"[Orchestrator][Themes] Local Load failed: {e}")
    
    return []


def _history_tail(state: dict, n: int = 6) -> list:
    return state.get("conversation_history", [])[-n:]


# ------------------------------------------------------------------ #
# Affirmative / negative reply detection                              #
# Used to intercept short "yes" / "no" replies after the bot offered  #
# to book a call (pending_booking_offer flag). Deterministic so we    #
# don't burn an LLM call on the most common affirmation pattern.      #
# ------------------------------------------------------------------ #

_AFFIRMATIVE_EXACT = {
    "yes", "yep", "yeah", "yup", "y", "sure", "ok", "okay", "kk", "alright",
    "absolutely", "definitely", "please", "fine", "cool", "great", "good",
    "yes please", "please do", "yes please do", "go ahead", "do it", "book it",
    "sounds good", "that works", "yes do it", "yes book it", "let's do it",
    "lets do it", "let's do this", "lets do this", "yes do", "ok do it",
    "okay do it", "ok please", "okay please", "yeah do it", "yeah book it",
}

_NEGATIVE_EXACT = {
    "no", "nope", "nah", "n", "no thanks", "no thank you",
    "not now", "not really", "never mind", "nevermind",
    "skip", "cancel", "no need", "i'm good", "im good",
    "no don't", "no dont", "no please don't", "no don't book",
}

_AFFIRMATIVE_LEADERS = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay"}
_NEGATIVE_LEADERS = {"no", "nope", "nah"}


def _normalize_short(text: str) -> str:
    if not text:
        return ""
    return text.lower().strip().rstrip(".!?,;").strip()


def _is_affirmative(text: str) -> bool:
    """True for short affirmations like 'yes', 'sure', 'yes please'."""
    t = _normalize_short(text)
    if not t:
        return False
    if t in _AFFIRMATIVE_EXACT:
        return True
    words = t.split()
    if len(words) <= 4 and words[0] in _AFFIRMATIVE_LEADERS and "?" not in text:
        return True
    return False


def _is_negative(text: str) -> bool:
    """True for short negative replies like 'no', 'no thanks', 'never mind'."""
    t = _normalize_short(text)
    if not t:
        return False
    if t in _NEGATIVE_EXACT:
        return True
    words = t.split()
    if len(words) <= 4 and words[0] in _NEGATIVE_LEADERS and "?" not in text:
        return True
    return False


# Paths where the assistant is actively collecting booking fields and the
# user's next message must stay on the booking pillar. Without this guard,
# short replies that double as finance terms ("KYC", "SIP", "ELSS") are
# misclassified as FAQ by the intent LLM and hit the FAQ agent by mistake.
_BOOKING_COLLECTION_PATHS = frozenset({
    "booking_need_topic",
    "escalation_need_topic",
    "theme_miss_need_topic",
    "booking_have_topic",
    "booking_need_both",
    "escalation_have_topic",
    "theme_miss_have_topic",
    "booking_need_date",
    "booking_need_time",
    "slot_rejected",
})


def _in_active_booking_collection(state: dict, in_flight: dict) -> bool:
    """True when the user is mid booking-collection (topic / date / time).

    Requires either a persisted active_path from the last assistant turn
    *or* last_intent == 'booking' as a fallback when active_path was not
    saved. This intentionally does NOT fire on a cold session where all
    three booking fields are empty but the user has not started booking
    yet (e.g. 'Hello' or 'What is the NAV?'), because active_path is not
    a collection path and last_intent is not booking.
    """
    if state.get("chat_closed"):
        return False

    missing_any = (
        not in_flight.get("topic")
        or not in_flight.get("date")
        or not in_flight.get("time")
    )
    if not missing_any:
        return False

    ap = state.get("active_path") or ""
    if ap in _BOOKING_COLLECTION_PATHS:
        return True

    if state.get("last_intent") == "booking":
        return True

    return False


# ================================================================== #
# NODE 1 — detect_escalation                                          #
# Runs first on every turn. Sets escalation_triggered.               #
# ================================================================== #

def detect_escalation_node(state: dict) -> dict:
    """Detect if the user wants a human advisor or is dissatisfied."""
    user_input = state["user_input"]

    # Fast rule-based pass to avoid an LLM call for obvious cases
    escalation_phrases = [
        "talk to someone", "speak to a human", "talk to human",
        "speak to someone", "want to talk", "talk to an advisor",
        "speak to advisor", "book a call", "schedule a call",
        "connect me", "human agent", "real person", "not helpful",
        "this isn't helping", "this is not helpful", "i give up",
        "can i talk", "can i speak", "want to speak",
        "not understanding", "not satisfied", "don't understand",
        "doesn't make sense", "not making sense", "still confused",
        "would like to discuss", "want to discuss", "discuss with",
        "discuss more", "need more help", "need help with",
    ]
    if any(ph in user_input.lower() for ph in escalation_phrases):
        state["escalation_triggered"] = True
        return state

    # LLM pass for subtle signals
    prompt = f"""You are checking whether a user message signals dissatisfaction or a desire to speak to a human advisor.

User message: "{user_input}"

Recent conversation:
{json.dumps(_history_tail(state, 4), indent=2)}

Respond ONLY with a JSON object — no explanation:
{{
  "escalation_triggered": true or false
}}

Trigger ONLY when:
- User EXPLICITLY asks to speak to / book a call with a human, advisor, or agent
  (e.g. "I want to talk to someone", "book a call", "connect me to an agent")
- User expresses clear frustration WITH the assistant's answer
  (e.g. "this isn't helpful", "you're not understanding me", "I give up")
- User has asked the same question multiple times in a row (repetition = confusion)

Do NOT trigger for:
- Normal factual questions about mutual funds
- General expressions of concern about their investments"""

    result = _llm_json(prompt)
    state["escalation_triggered"] = bool(result.get("escalation_triggered")) if result else False
    return state


# ================================================================== #
# NODE 2 — detect_intent                                              #
# Classifies intent and extracts scheme / concept entities.           #
# ================================================================== #

def detect_intent_node(state: dict) -> dict:
    """Detect intent and extract key entities from the user message."""
    user_input = state["user_input"]
    in_flight = state.get("in_flight_booking", {})
    last_intent = state.get("last_intent")

    # ── Phase 4: awaiting confirmation interception ──
    # If we asked the user to confirm a booking, their next message should
    # be interpreted as a confirmation response — NOT as a new intent.
    if state.get("active_path") == "awaiting_confirmation":
        state["last_intent"] = "confirmation_pending"
        return state

    # ── Phase 4: awaiting slot acceptance interception ──
    # If we suggested an alternative slot, the user's next message is
    # their acceptance or rejection of that alternative.
    if state.get("active_path") == "awaiting_slot_acceptance":
        state["last_intent"] = "slot_acceptance_pending"
        return state

    # ── Pending-booking-offer interception ──
    # If the bot's previous reply ended with "Would you like me to book a
    # call with an advisor?" (e.g. after FAQ refusal, theme match, or an
    # investment-adjacent question), a bare "yes" / "sure" must route
    # straight into booking — otherwise the LLM re-routes it into the
    # same pillar and the user sees the same offer again.
    if state.get("pending_booking_offer"):
        # Always clear the flag; we handle this turn explicitly.
        state["pending_booking_offer"] = False
        if _is_affirmative(user_input):
            state["last_intent"] = "booking"
            # escalation_triggered makes collect_booking_topic auto-generate
            # the topic from conversation history rather than re-asking.
            state["escalation_triggered"] = True
            return state
        if _is_negative(user_input):
            state["last_intent"] = "other"
            # generate_response_node "other" branch will compose a friendly
            # "no problem, anything else?" reply via the LLM.
            return state
        # Anything else: the user changed subject — fall through to normal
        # intent detection.

    missing_booking_fields = (
        not in_flight.get("topic") or not in_flight.get("date") or not in_flight.get("time")
    )

    # Lock routing to booking while we are collecting topic / date / time,
    # so answers like "KYC" are not sent to the FAQ agent. Gated by
    # active_path (and last_intent fallback) — see _in_active_booking_collection.
    if missing_booking_fields and _in_active_booking_collection(state, in_flight):
        state["last_intent"] = "booking"
        return state

    # ── Phase 4: booking signal check (improves first-turn recognition) ──
    booking_keywords = ["book", "schedule", "appointment", "call", "advisor", "meeting"]
    user_lower = user_input.lower()
    if any(k in user_lower for k in booking_keywords) and not last_intent:
        state["last_intent"] = "booking"
        return state

    prompt = f"""You are the intent detector for a mutual fund investor assistant.

User message: "{user_input}"

Recent conversation (last 6 turns):
{json.dumps(_history_tail(state), indent=2)}

Previous turn intent: {last_intent or "none"}
Booking in progress: topic={in_flight.get("topic")}, date={in_flight.get("date")}, time={in_flight.get("time")}

Detect the intent. Choose ONE of:
- "faq"     — user asks about a mutual fund's data (NAV, expense ratio, exit load, alpha, beta, fund manager, SIP, AUM, lock-in, etc.) or wants to understand a mutual fund concept, or mentions a transaction they performed (e.g. "I placed a redemption order", "I started a SIP") without expressing a problem
- "theme"   — user explicitly describes a PROBLEM or COMPLAINT about the Groww app/service (e.g. "my order is stuck", "app crashed during trading", "can't withdraw money"). Simply mentioning a transaction or action is NOT a theme — there must be a clear negative experience or error
- "booking" — user wants to book/schedule a call with a human advisor, OR is continuing an in-progress booking by providing a topic/date/time they were asked for
- "cancel_or_reschedule" — user wants to cancel or reschedule an existing appointment (e.g. "cancel my appointment", "reschedule my call", "I want to change my booking")
- "other"   — greeting, thanks, or completely unrelated

Also extract (set to null if not present):
- scheme_name: full mutual fund scheme name (e.g. "Axis Bluechip Fund", "SBI Small Cap Fund")
- concept: mutual fund term (e.g. "exit load", "expense ratio", "NAV", "alpha")

Note: If previous_turn_intent was "booking" and the user is supplying a date, time, or topic, use intent "booking".

Respond ONLY with JSON:
{{
  "intent": "faq" | "theme" | "booking" | "cancel_or_reschedule" | "other",
  "scheme_name": "string or null",
  "concept": "string or null"
}}"""

    # Use the default primary (gpt-oss-120b). Intent classification is the
    # most consequential routing decision in the graph — a wrong intent can
    # send the user to the wrong pillar entirely. The cost of getting it
    # right is well worth the small extra latency vs llama-3.1-8b-instant.
    result = _llm_json(prompt)
    if result:
        state["last_intent"] = result.get("intent", "other")
        if result.get("scheme_name"):
            state["current_scheme"] = result["scheme_name"]
        if result.get("concept"):
            state["current_concept"] = result["concept"]
    else:
        state["last_intent"] = "other"

    return state


# ================================================================== #
# NODE 3 — check_theme                                                #
# Fuzzy-matches user complaint against the Themes KB.                 #
# ================================================================== #

def check_theme_node(state: dict) -> dict:
    """Match user complaint against the loaded Themes Knowledge Base.

    Also performs a lightweight escalation check: if the user's message
    contains escalation signals AND matches a theme, escalation wins
    so the user gets routed to booking instead of a theme response.
    """
    themes = _load_themes()
    user_input = state["user_input"]

    # Lightweight escalation signal check (reuses the same phrase list
    # as detect_escalation_node).  If the user is asking for a human,
    # escalation should win even if their message also matches a theme.
    _ESCALATION_PHRASES = [
        "talk to someone", "speak to a human", "talk to human",
        "speak to someone", "want to talk", "talk to an advisor",
        "speak to advisor", "book a call", "schedule a call",
        "connect me", "human agent", "real person", "not helpful",
        "this isn't helping", "this is not helpful", "i give up",
        "can i talk", "can i speak", "want to speak",
        "not understanding", "not satisfied", "don't understand",
        "doesn't make sense", "not making sense", "still confused",
        "would like to discuss", "want to discuss", "discuss with",
        "discuss more", "need more help", "need help with",
    ]
    escalation_detected = any(ph in user_input.lower() for ph in _ESCALATION_PHRASES)

    if not themes:
        state["theme_match"] = None
        state["active_path"] = "theme_miss"
        if escalation_detected:
            state["escalation_triggered"] = True
        return state

    # Build a concise summary for the LLM — include more example quotes for better matching
    themes_summary = [
        {
            "name": t["theme_name"],
            "description": t.get("short_description", ""),
            "examples": [q.get("text", "")[:120] for q in t.get("representative_quotes", [])[:2]],
        }
        for t in themes
    ]

    prompt = f"""You are matching a user complaint to a list of known issues tracked by our team.

User message: "{state['user_input']}"

Known themes:
{json.dumps(themes_summary, indent=2)}

Does the user's complaint match one of these known themes?
Rules:
- Match only if the user's specific problem clearly falls within a theme's scope
  (e.g. "app keeps crashing" matches "App Crashes"; "can't reach support" matches "Customer Support";
   "withdrawal is stuck" matches "Withdrawal Issues")
- Do NOT match just because the topic is loosely related — the user must be describing an actual
  problem that fits the theme's description and examples
- A user simply mentioning a transaction (e.g. "I placed a redemption order") is NOT a complaint —
  only match if they describe something going WRONG
- Return the EXACT theme name as it appears in the list
- If the complaint doesn't clearly fit any theme, return matched=false

Respond ONLY with JSON:
{{
  "matched": true or false,
  "theme_name": "exact theme name or null"
}}"""

    result = _llm_json(prompt)

    if result and result.get("matched") and result.get("theme_name"):
        matched_name = result["theme_name"]
        full_theme = next((t for t in themes if t["theme_name"] == matched_name), None)
        if full_theme:
            state["theme_match"] = full_theme
            # Escalation wins over theme match - user explicitly wants a human
            if escalation_detected:
                state["escalation_triggered"] = True
                state["active_path"] = "theme_match_escalation"
            else:
                state["active_path"] = "theme_match"
            return state

    state["theme_match"] = None
    state["active_path"] = "theme_miss"
    if escalation_detected:
        state["escalation_triggered"] = True
    return state


# ================================================================== #
# NODE 4 — rewrite_query                                              #
# Rewrites the user query to be fully self-contained.                 #
# ================================================================== #

def rewrite_query_node(state: dict) -> dict:
    """Rewrite vague user query into a self-contained question for the FAQ agent."""
    user_input = state["user_input"]
    scheme = state.get("current_scheme")
    concept = state.get("current_concept")

    prompt = f"""You are rewriting a user's question to make it fully self-contained.

Original question: "{user_input}"

Context:
- Scheme in scope: {scheme or "none"}
- Concept in scope: {concept or "none"}

Recent conversation:
{json.dumps(_history_tail(state), indent=2)}

Rules:
1. Replace pronouns ("it", "its", "that fund", "this") with the actual scheme or concept name
2. The rewritten question must be understandable without any prior context
3. Keep it concise and natural — don't over-explain
4. If the question is already self-contained, return it unchanged

Return ONLY the rewritten question as plain text (no JSON, no quotes)."""

    rewritten = _llm_text(prompt, temperature=0)
    if rewritten:
        state["rewritten_query_for_faq"] = rewritten.strip().strip('"').strip("'")
    else:
        state["rewritten_query_for_faq"] = user_input

    return state


# ================================================================== #
# NODE 5 — call_faq_agent                                             #
# Calls the Phase 2 FAQ agent via HTTP.                               #
# ================================================================== #

def call_faq_agent_node(state: dict) -> dict:
    """Call the Phase 2 FAQ agent and store the structured response."""
    query = state.get("rewritten_query_for_faq") or state["user_input"]
    history = state.get("conversation_history", [])

    try:
        response = requests.post(
            _FAQ_API_URL,
            json={"message": query, "history": history},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            state["faq_response"] = data
            faq_type = data.get("type", "answer")
            if faq_type == "clarify":
                state["active_path"] = "faq_clarify"
            elif faq_type == "refuse":
                state["active_path"] = "faq_refused"
            else:
                state["active_path"] = "faq_answered"
        else:
            raise ValueError(f"FAQ API returned HTTP {response.status_code}")
    except Exception as e:
        print(f"[Orchestrator][call_faq_agent] Failed: {e}")
        state["faq_response"] = {
            "type": "error",
            "text": "I'm having trouble accessing my knowledge base right now.",
            "links": [],
        }
        state["active_path"] = "faq_error"

    return state


# ================================================================== #
# NODE 6 — collect_booking_topic                                      #
# Extracts or auto-generates the booking topic.                       #
# ================================================================== #

def collect_booking_topic_node(state: dict) -> dict:
    """Extract, auto-generate, or ask for the booking topic."""
    in_flight = state.get("in_flight_booking", {})

    # If topic already collected in a previous turn, pass through
    if in_flight.get("topic"):
        return state

    user_input = state["user_input"]
    escalation = state.get("escalation_triggered", False)
    is_theme_miss = (state.get("last_intent") == "theme" and not state.get("theme_match"))
    is_faq_refused = (
        state.get("faq_response", {}).get("type") in ("refuse", "error")
        if state.get("faq_response") else False
    )

    is_theme_match = state.get("theme_match") is not None
    # Auto-generate from context for escalation / theme_miss / faq_refused / theme_match
    auto_generate = escalation or is_theme_miss or is_faq_refused or is_theme_match

    prompt = f"""You are extracting or generating a brief booking topic (1–3 words) for a call with a mutual fund advisor.

User message: "{user_input}"

Context:
- Scheme discussed: {state.get("current_scheme") or "none"}
- Concept discussed: {state.get("current_concept") or "none"}
- Theme matched: {state.get("theme_match", {}).get("theme_name") if state.get("theme_match") else "none"}
- FAQ refused: {is_faq_refused}
- Auto-generate from context: {auto_generate}

Recent conversation (last 8 turns):
{json.dumps(_history_tail(state, 8), indent=2)}

Task:
- If "auto_generate" is true: derive a 1–3 word topic from the conversation context
  (e.g. "Exit Load", "App Crash", "SIP Processing", "Fund Performance")
- If user explicitly stated a topic in their message: extract and condense to 1–3 words
- If neither applies: return null (we'll ask the user)

CRITICAL: NEVER use words like "appointment", "call", "booking", or weekdays/dates as the topic. If the user hasn't provided a specific subject (like "KYC", "Redemption", etc.), return null.

Respond ONLY with JSON:
{{
  "topic": "1–3 word topic string, or null",
  "needs_to_ask": true or false
}}"""

    result = _llm_json(prompt)
    topic = result.get("topic") if result else None

    # FILTER: Don't use generic action words, dates, or filler-only phrases
    # as the booking topic. Rejects: "Monday", "appointment", "next week",
    # "appointment on Monday", "call about it", "the meeting".
    DATE_WORDS = {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "today", "tomorrow", "tonight", "morning", "afternoon", "evening",
        "next", "this", "coming", "week", "weekend", "month", "day",
        "am", "pm",
    }
    GENERIC_WORDS = {
        "appointment", "booking", "book", "call", "advisor", "meeting",
        "help", "support", "someone", "talk", "schedule", "session",
        "discuss", "discussion", "chat", "conversation",
        "the", "a", "an", "about", "on", "at", "with", "for", "to", "in",
        "it", "that", "this",
    }
    FILLER_TOKENS = DATE_WORDS | GENERIC_WORDS

    def _strip_filler_prefix(s: str) -> str:
        """Strip leading filler so 'appointment on Monday about taxes' -> 'taxes'."""
        words = s.lower().split()
        # Drop leading filler tokens
        while words and words[0] in FILLER_TOKENS:
            words.pop(0)
        return " ".join(words)

    if topic:
        # Strip surrounding punctuation/quotes the LLM sometimes wraps.
        candidate = topic.strip().strip('"').strip("'").strip()
        candidate_lower = candidate.lower()
        tokens = candidate_lower.split()

        if not tokens:
            topic = None
        else:
            # Reject if every token is filler (date or generic).
            if all(tok in FILLER_TOKENS for tok in tokens):
                topic = None
            else:
                # Try to recover a real topic by stripping leading filler.
                stripped = _strip_filler_prefix(candidate_lower)
                if stripped and not all(tok in FILLER_TOKENS for tok in stripped.split()):
                    # Re-title-case using the original casing where possible.
                    topic = stripped
                else:
                    topic = None

    needs_ask = result.get("needs_to_ask", True) if result else True

    if topic and not needs_ask:
        in_flight["topic"] = topic
        state["in_flight_booking"] = in_flight
        # Choose active_path variant based on booking source
        if escalation:
            state["active_path"] = "escalation_have_topic"
        elif is_theme_miss:
            state["active_path"] = "theme_miss_have_topic"
        else:
            state["active_path"] = "booking_have_topic"
    else:
        # Need to ask for topic
        if escalation:
            state["active_path"] = "escalation_need_topic"
        elif is_theme_miss:
            state["active_path"] = "theme_miss_need_topic"
        else:
            state["active_path"] = "booking_need_topic"

    return state


def _infer_relative_booking_date(
    user_input: str,
    today_str: str,
    tomorrow_str: str,
    day_after_str: str,
) -> str | None:
    """Map user-literal relative day words to IST calendar dates.

    Used only when the LLM left ``date`` empty. Keeps booking collection
    robust for short replies like "Tomorrow" or common typos ("tiomorrow").
    """
    if not user_input or not str(user_input).strip():
        return None
    text = user_input.lower()

    def _rejects_tomorrow_phrase(t: str) -> bool:
        if re.search(r"\bnot\s+(?:the\s+)?day\s+after\s+tomorrow\b", t):
            return True
        if re.search(r"\bnot\s+(?:tomorrow|tiomorrow)\b", t):
            return True
        if re.search(r"\bexcept\s+tomorrow\b", t):
            return True
        if re.search(r"\bother\s+than\s+tomorrow\b", t):
            return True
        if re.search(r"\banything\s+but\s+tomorrow\b", t):
            return True
        if re.search(r"\btomorrow\s+won'?t\b", t):
            return True
        if re.search(r"\btomorrow\s+(doesn'?t|does not)\s+work\b", t):
            return True
        return False

    if re.search(r"\b(?:the\s+)?day\s+after\s+tomorrow\b", text):
        if not _rejects_tomorrow_phrase(text):
            return day_after_str

    if re.search(r"\b(?:tomorrow|tiomorrow)\b", text) and not _rejects_tomorrow_phrase(text):
        return tomorrow_str

    if re.search(r"\b(?:today|tonight|this\s+evening|this\s+afternoon)\b", text):
        if re.search(r"\bnot\s+today\b", text) or re.search(r"\bnot\s+tonight\b", text):
            return None
        return today_str

    return None


# ================================================================== #
# NODE 7 — collect_booking_datetime                                   #
# Extracts date + time from conversation.                             #
# ================================================================== #

def collect_booking_datetime_node(state: dict) -> dict:
    """Parse date and time for the booking from conversation (IST-aware)."""
    in_flight = state.get("in_flight_booking", {})

    # Already have both — skip
    if in_flight.get("date") and in_flight.get("time"):
        state["active_path"] = "booking_complete"
        return state

    # ------------------------------------------------------------------ #
    # Anchor all date calculations to IST (Asia/Kolkata, UTC+5:30).       #
    # Pre-compute every reference term so the LLM uses exact dates.       #
    # ------------------------------------------------------------------ #
    try:
        from zoneinfo import ZoneInfo
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = datetime.now()  # graceful fallback

    today_str     = now_ist.strftime("%Y-%m-%d")
    today_weekday = now_ist.strftime("%A")
    tomorrow      = now_ist + timedelta(days=1)
    day_after     = now_ist + timedelta(days=2)
    tomorrow_str  = tomorrow.strftime("%Y-%m-%d")
    day_after_str = day_after.strftime("%Y-%m-%d")

    # "Coming / next <Weekday>" — always the strictly next occurrence (≥ 1 day ahead)
    _WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    coming: dict[str, str] = {}
    for idx, name in enumerate(_WEEKDAYS):
        days_ahead = idx - now_ist.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        coming[name] = (now_ist + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Generate a small reference calendar for the next 30 days
    calendar_lines = []
    for i in range(45): # Provide 45 days of context
        d = now_ist + timedelta(days=i)
        calendar_lines.append(f"  {d.strftime('%d %b (%A)')}: {d.strftime('%Y-%m-%d')}")
    calendar_ref = "\n".join(calendar_lines)

    prompt = f"""Extract a booking date and time STRICTLY from the user's CURRENT message.
Current Date: {today_str} ({today_weekday}), all times in IST.

=== UPCOMING WEEKDAYS (use ONLY to resolve weekday names the user explicitly says) ===
Monday    -> {coming.get('Monday')}
Tuesday   -> {coming.get('Tuesday')}
Wednesday -> {coming.get('Wednesday')}
Thursday  -> {coming.get('Thursday')}
Friday    -> {coming.get('Friday')}
Saturday  -> {coming.get('Saturday')}
Sunday    -> {coming.get('Sunday')}

(Full reference calendar for ordinals only:)
{calendar_ref}

=== CURRENT USER MESSAGE (the ONLY source of truth) ===
"{state['user_input']}"

=== Conversation history (CONTEXT ONLY — do NOT extract dates/times from here) ===
{json.dumps(_history_tail(state), indent=2)}

=== EXTRACTION RULES ===
1. Only extract what the user literally wrote in their CURRENT message above.
2. A leading "no", "nope", or "not" does NOT block extraction. The user is
   often correcting a previous bot suggestion and providing new values in the
   same sentence. Read past the negation and grab the date/time the user is
   PROPOSING (see examples below).
3. If the current message does not mention a date, return date=null. The
   system has its own memory for previously confirmed values; do not guess.
4. Do not invent dates from history or from bot suggestions. Never pick an
   "upcoming Monday" or other weekday unless the user named that weekday in
   the CURRENT message. When the user literally says relative day words in
   the CURRENT message, you MUST return the exact calendar date:
   "today"/"tonight"/"this afternoon"/"this evening" -> {today_str};
   "tomorrow" -> {tomorrow_str};
   "day after tomorrow" (or "the day after tomorrow") -> {day_after_str}.
5. NEVER carry over values the BOT suggested. Bot suggestions are not
   user-stated and must not be returned here.
6. Resolve weekdays using the table above.
7. Resolve ordinals (e.g. "3rd May" -> "2026-05-03").
8. Normalize time to 24h format (e.g. "4:30 pm" -> "16:30").

=== EXAMPLES ===
User: "yes"                              -> {{"date": null, "time": null}}
User: "ok"                               -> {{"date": null, "time": null}}
User: "Tomorrow"                         -> {{"date": "{tomorrow_str}", "time": null}}
User: "tomorrow at 3pm"                  -> {{"date": "{tomorrow_str}", "time": "15:00"}}
User: "no, book on Tuesday at 4:30 pm"   -> {{"date": "{coming.get('Tuesday')}", "time": "16:30"}}
User: "not that time, how about 5pm"     -> {{"date": null, "time": "17:00"}}
User: "no Wednesday"                     -> {{"date": "{coming.get('Wednesday')}", "time": null}}
User: "actually Friday morning"          -> {{"date": "{coming.get('Friday')}", "time": null}}
User: "let's pick exit load topic"       -> {{"date": null, "time": null}}

Respond ONLY with JSON:
{{
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM or null"
}}"""

    # Use the larger model — extraction needs to handle negations and
    # correction phrasing reliably. The 8b model was dropping both fields
    # whenever the user input started with "no".
    result = _llm_json(prompt)
    print(f"[Orchestrator][extract] User: '{state['user_input']}' -> Extracted: {result}")

    if result:
        date_val = result.get("date")
        time_val = result.get("time")

        # Validation Fallback: If LLM returned a weekday name despite instructions
        if date_val and date_val.title() in coming:
            date_val = coming[date_val.title()]

        if date_val:
            in_flight["date"] = date_val
        if time_val:
            in_flight["time"] = time_val

    if not in_flight.get("date"):
        inferred = _infer_relative_booking_date(
            state.get("user_input") or "",
            today_str,
            tomorrow_str,
            day_after_str,
        )
        if inferred:
            in_flight["date"] = inferred

    state["in_flight_booking"] = in_flight

    # ── Resolve the next active_path based on what's still missing ──
    has_topic = bool(in_flight.get("topic"))
    has_date = bool(in_flight.get("date"))
    has_time = bool(in_flight.get("time"))
    source_path = state.get("active_path") or ""

    # Topic gating: a booking must always have a topic before we proceed
    # to slot check / confirmation. If topic is missing, force a *_need_topic
    # active_path (preserving the source variant if collect_booking_topic_node
    # already chose one).
    if not has_topic:
        if source_path in ("escalation_need_topic", "theme_miss_need_topic", "booking_need_topic"):
            pass  # keep source-specific need-topic message
        else:
            state["active_path"] = "booking_need_topic"
        return state

    # Topic present — decide based on date/time gaps.
    if has_date and has_time:
        state["active_path"] = "booking_complete"
    elif not has_date and not has_time:
        # Only keep the source-specific "have_topic" copy when nothing else
        # is known yet — this ensures the special escalation / theme-miss
        # messaging runs exactly once on the turn topic is first acquired.
        if source_path in ("escalation_have_topic", "theme_miss_have_topic", "booking_have_topic"):
            pass
        else:
            state["active_path"] = "booking_need_both"
    elif not has_date:
        state["active_path"] = "booking_need_date"
    else:
        state["active_path"] = "booking_need_time"

    return state


# ================================================================== #
# NODE 8 — emit_booking_request                                       #
# Packages the final booking request once all fields are collected.   #
# ================================================================== #

def emit_booking_request_node(state: dict) -> dict:
    """Package the completed booking fields into a structured request.

    In Phase 4, this no longer generates a confirmation message.
    Instead, it sets the booking_request and routes to slot checking.
    """
    in_flight = state.get("in_flight_booking", {})

    state["booking_request"] = {
        "topic": in_flight.get("topic", "General inquiry"),
        "date": in_flight.get("date"),
        "time": in_flight.get("time"),
        "user_info": {},
    }

    # Don't clear in_flight yet — we still need it for slot checking
    state["active_path"] = "booking_complete"
    return state


# ================================================================== #
# PHASE 4 NODES                                                       #
# ================================================================== #


def check_slot_availability_node(state: dict) -> dict:
    """Check the requested slot against the meeting policy AND Google Calendar.

    Order of checks:
      1. Policy (holidays, working hours, lunch, gap) — cheap, deterministic.
      2. Calendar overlap — only if policy allowed it.
    Either failure produces ``active_path = "slot_unavailable"`` with a
    human-readable ``reason`` and a policy-aware ``suggested_alternative``
    so the suggestion is guaranteed to satisfy the same rules.
    """
    from availability_policy import load_policy, next_compliant_slot, validate_slot

    in_flight = state.get("in_flight_booking", {})
    date_val = in_flight.get("date")
    time_val = in_flight.get("time")

    if not date_val or not time_val:
        state["active_path"] = "slot_available"  # no date/time to check, proceed
        return state

    try:
        start_ist = datetime.strptime(f"{date_val} {time_val}", "%Y-%m-%d %H:%M")
        end_ist = start_ist + timedelta(minutes=30)
    except Exception as e:
        print(f"[Orchestrator][slot_check] Failed to parse date/time '{date_val} {time_val}': {e}")
        state["slot_check_result"] = {
            "available": False,
            "reason": "Invalid date or time format.",
        }
        state["active_path"] = "slot_unavailable"
        return state

    policy = load_policy()

    # ── Step 1: policy check (no API call) ──
    ok, reason = validate_slot(start_ist, end_ist, busy=(), policy=policy)
    if not ok:
        suggestion = _suggest_with_policy(start_ist, policy)
        state["slot_check_result"] = {
            "available": False,
            "reason": reason,
            "suggested_alternative": _serialize_suggestion(suggestion),
        }
        state["active_path"] = "slot_unavailable"
        return state

    # ── Step 2: calendar check (overlap with existing events, gap-aware) ──
    try:
        mcp = get_workspace_mcp()
        busy = mcp.list_busy_intervals(
            start_ist - timedelta(minutes=max(policy.gap_mins, 30)),
            end_ist + timedelta(minutes=max(policy.gap_mins, 30)),
        )
    except Exception as e:
        print(f"[Orchestrator][slot_check] MCP error: {e}")
        state["slot_check_result"] = {
            "available": False,
            "reason": "Could not reach the calendar to confirm the slot.",
        }
        state["active_path"] = "slot_unavailable"
        return state

    ok, reason = validate_slot(start_ist, end_ist, busy=busy, policy=policy)
    if ok:
        state["slot_check_result"] = {"available": True, "reason": ""}
        state["active_path"] = "slot_available"
        return state

    suggestion = _suggest_with_policy(start_ist, policy)
    state["slot_check_result"] = {
        "available": False,
        "reason": reason,
        "suggested_alternative": _serialize_suggestion(suggestion),
    }
    state["active_path"] = "slot_unavailable"
    return state


def _suggest_with_policy(after_ist: datetime, policy) -> Optional[dict]:
    """Find the next slot that satisfies policy + calendar.

    Pulls one window of busy events (14 days) and lets ``next_compliant_slot``
    enforce all rules so suggestion and validation cannot drift apart.
    """
    from availability_policy import next_compliant_slot

    try:
        mcp = get_workspace_mcp()
        busy = mcp.list_busy_intervals(after_ist, after_ist + timedelta(days=14))
    except Exception as e:
        print(f"[Orchestrator][slot_check] Could not list busy intervals: {e}")
        busy = []
    return next_compliant_slot(after_ist + timedelta(minutes=30), busy=busy, policy=policy)


def _serialize_suggestion(suggestion: Optional[dict]) -> Optional[dict]:
    if not suggestion:
        return None
    return {
        "start_ist": suggestion["start_ist"].strftime("%Y-%m-%d %H:%M"),
        "end_ist": suggestion["end_ist"].strftime("%Y-%m-%d %H:%M"),
    }


def suggest_alternative_slot_node(state: dict) -> dict:
    """Suggest an alternative slot when the requested one is unavailable.

    Tells the user the specific reason (holiday, working hours, lunch, gap,
    or calendar conflict) and offers the next policy-compliant slot. Updates
    ``in_flight_booking`` so if the user accepts, the correct slot is used.
    """
    slot_result = state.get("slot_check_result", {})
    alternative = slot_result.get("suggested_alternative")
    reason = (slot_result.get("reason") or "").strip()

    prefix = reason if reason else "That time is not available."
    if not prefix.endswith("."):
        prefix += "."

    if alternative:
        alt_start = alternative["start_ist"]
        try:
            dt = datetime.strptime(alt_start, "%Y-%m-%d %H:%M")
            formatted = dt.strftime("%A, %d %B %Y at %I:%M %p IST")
            in_flight = state.get("in_flight_booking", {})
            in_flight["date"] = dt.strftime("%Y-%m-%d")
            in_flight["time"] = dt.strftime("%H:%M")
            state["in_flight_booking"] = in_flight
        except Exception:
            formatted = alt_start
        # Keep policy/calendar reasons user-friendly, but always surface the concrete next slot.
        state["response_to_user"] = (
            f"{prefix} Here is the next available slot I can offer you: {formatted}. "
            "Would that work for you?"
        )
    else:
        state["response_to_user"] = (
            f"{prefix} I could not find another opening that fits our calendar in the next "
            "couple of weeks. Would you like to try a different date or time?"
        )

    state["response_type"] = "booking_collecting"
    state["active_path"] = "awaiting_slot_acceptance"
    return state


def request_final_confirmation_node(state: dict) -> dict:
    """Ask the user for final confirmation before booking."""
    in_flight = state.get("in_flight_booking", {})
    topic = in_flight.get("topic", "your query")
    date_val = in_flight.get("date", "")
    time_val = in_flight.get("time", "")

    # Format date with weekday
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.strptime(date_val, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        date_formatted = dt.strftime("%A, %d %B %Y")
    except Exception:
        date_formatted = date_val

    state["response_to_user"] = (
        f"Got it. To confirm: a 30 minute call about '{topic}' "
        f"on {date_formatted} at {time_val} IST. Should I book this?"
    )
    state["response_type"] = "booking_collecting"
    state["active_path"] = "awaiting_confirmation"
    return state


def detect_confirmation_response_node(state: dict) -> dict:
    """Interpret the user's response to the final confirmation prompt."""
    user_input = state["user_input"]
    in_flight = state.get("in_flight_booking", {})

    # Pre-compute IST reference data so the LLM can resolve weekdays and
    # ordinals correctly (and never invent a default).
    try:
        from zoneinfo import ZoneInfo
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = datetime.now()
    today_str = now_ist.strftime("%Y-%m-%d")
    today_weekday = now_ist.strftime("%A")
    _WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    coming: dict[str, str] = {}
    for idx, name in enumerate(_WEEKDAYS):
        days_ahead = idx - now_ist.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        coming[name] = (now_ist + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    prompt = f"""You are interpreting a user's response to a booking confirmation prompt.

Current date: {today_str} ({today_weekday}), all times in IST.
The user was asked: "Should I book this?"
for a 30 minute call about '{in_flight.get("topic", "your query")}'
on {in_flight.get("date") or "<no date set>"} at {in_flight.get("time") or "<no time set>"}.

User's response: "{user_input}"

Classify the response as exactly ONE of:
- "confirmed" — user says yes, confirms, agrees (e.g. "yes", "book it", "go ahead", "sure", "confirm")
- "change_slot" — user wants a different date/time but still wants to book (e.g. "no, can we do Wednesday instead", "not that time", "how about 5pm", "no book on Tuesday at 4:30")
- "change_topic" — user wants to change the topic (e.g. "actually I want to discuss something else")
- "exit" — user wants to cancel/exit the booking entirely (e.g. "never mind", "cancel", "forget it", "no thanks")
- "ambiguous" — unclear response, neither clearly yes nor no (e.g. "hmm", "wait")

Date/time extraction rules — read carefully:
- Only extract new_date / new_time if the user literally wrote them in THEIR CURRENT response above.
- A leading "no" does NOT block extraction — "no, Tuesday 4:30 pm" still yields date=next Tuesday and time=16:30.
- NEVER inherit, guess, or default to a date the bot suggested.
- Resolve weekdays using upcoming dates: Monday->{coming['Monday']}, Tuesday->{coming['Tuesday']}, Wednesday->{coming['Wednesday']}, Thursday->{coming['Thursday']}, Friday->{coming['Friday']}, Saturday->{coming['Saturday']}, Sunday->{coming['Sunday']}.
- Normalize time to 24h (e.g. "4:30 pm" -> "16:30").
- If the user did not state a new date/time, return null for that field.

Respond ONLY with JSON:
{{
  "response": "confirmed" | "change_slot" | "change_topic" | "exit" | "ambiguous",
  "new_date": "YYYY-MM-DD or null",
  "new_time": "HH:MM or null"
}}"""

    result = _llm_json(prompt)
    response_type = result.get("response", "ambiguous") if result else "ambiguous"
    state["confirmation_response"] = response_type

    # If user provided a new date/time, update in_flight
    if response_type == "change_slot" and result:
        if result.get("new_date"):
            in_flight["date"] = result["new_date"]
        if result.get("new_time"):
            in_flight["time"] = result["new_time"]
        state["in_flight_booking"] = in_flight

    # Map to active_path
    path_map = {
        "confirmed": "confirmation_confirmed",
        "change_slot": "confirmation_change_slot",
        "change_topic": "confirmation_change_topic",
        "exit": "confirmation_exit",
        "ambiguous": "confirmation_ambiguous",
    }
    state["active_path"] = path_map.get(response_type, "confirmation_ambiguous")
    return state


def generate_booking_code_node(state: dict) -> dict:
    """Generate a unique 4-digit booking code."""
    mcp = get_workspace_mcp()

    for _ in range(10):  # Max 10 attempts to avoid collision
        code = mcp.generate_booking_code()
        if not _booking_code_exists(code):
            state["booking_code"] = code
            return state

    # Extremely unlikely fallback
    state["booking_code"] = mcp.generate_booking_code()
    return state


def execute_booking_node(state: dict) -> dict:
    """Execute the four booking side effects sequentially."""
    from meetings_log import append_entry as _append_meeting_log

    in_flight = state.get("in_flight_booking", {})
    booking_code = state.get("booking_code", "")
    topic = in_flight.get("topic", "General inquiry")
    date_val = in_flight.get("date", "")
    time_val = in_flight.get("time", "")

    artifacts = {
        "calendar_event_id": None,
        "calendar_event_link": None,
        "broker_email_sent": False,
        "google_doc_id": None,
        "google_doc_url": None,
        "dashboard_log_id": None,
    }

    mcp = get_workspace_mcp()

    # Construct IST datetimes
    try:
        from zoneinfo import ZoneInfo
        ist_tz = ZoneInfo("Asia/Kolkata")
        start_ist = datetime.strptime(f"{date_val} {time_val}", "%Y-%m-%d %H:%M").replace(tzinfo=ist_tz).replace(tzinfo=None)
        end_ist = start_ist + timedelta(minutes=30)
        meeting_time_str = f"{date_val} at {time_val} IST"
    except Exception as e:
        print(f"[Orchestrator][execute_booking] Datetime parse failed: {e}")
        state["booking_artifacts"] = artifacts
        state["active_path"] = "booking_execution_failed"
        return state

    # Step 1: Create calendar event
    try:
        cal_result = mcp.create_calendar_event(topic, start_ist, end_ist, booking_code)
        artifacts["calendar_event_id"] = cal_result["event_id"]
        artifacts["calendar_event_link"] = cal_result.get("event_link")
    except Exception as e:
        print(f"[Orchestrator][execute_booking] Calendar event failed: {e}")
        state["booking_artifacts"] = artifacts
        state["active_path"] = "booking_execution_failed"
        return state  # Calendar is critical — abort if it fails

    # Step 2: Create Google Doc
    doc_link = None
    try:
        doc_result = mcp.create_meeting_notes_doc(topic, booking_code, meeting_time_str)
        artifacts["google_doc_id"] = doc_result["doc_id"]
        artifacts["google_doc_url"] = doc_result["doc_link"]
        doc_link = doc_result["doc_link"]
    except Exception as e:
        print(f"[Orchestrator][execute_booking] Google Doc failed: {e}")
        # Non-critical — continue

    # Step 2b: Attach doc to calendar event
    if doc_link and artifacts["calendar_event_id"]:
        try:
            mcp.update_calendar_event_with_doc(artifacts["calendar_event_id"], doc_link)
        except Exception as e:
            print(f"[Orchestrator][execute_booking] Doc attachment failed: {e}")

    # Step 3: Send broker email
    try:
        mcp.send_booking_email(
            topic=topic,
            booking_code=booking_code,
            meeting_time=meeting_time_str,
            doc_link=doc_link,
            event_link=artifacts.get("calendar_event_link"),
        )
        artifacts["broker_email_sent"] = True
    except Exception as e:
        print(f"[Orchestrator][execute_booking] Broker email failed: {e}")
        # Non-critical — continue

    # Step 4: Append to meetings log
    try:
        _append_meeting_log({
            "booking_code": booking_code,
            "topic": topic,
            "date": date_val,
            "time": time_val,
            "broker_email": os.getenv("MF_DISTRIBUTOR_EMAIL", ""),
            "doc_link": doc_link,
            "doc_id": artifacts.get("google_doc_id"),
            "calendar_event_id": artifacts.get("calendar_event_id"),
            "calendar_event_link": artifacts.get("calendar_event_link"),
            "status": "scheduled",
        })
        artifacts["dashboard_log_id"] = booking_code
    except Exception as e:
        print(f"[Orchestrator][execute_booking] Dashboard log failed: {e}")
        # Non-critical — continue

    state["booking_artifacts"] = artifacts
    state["active_path"] = "booking_executed"
    return state


def close_chat_node(state: dict) -> dict:
    """Compose the closing message and mark chat as closed."""
    booking_code = state.get("booking_code", "")
    in_flight = state.get("in_flight_booking", {})
    topic = in_flight.get("topic", "your query")
    date_val = in_flight.get("date", "")
    time_val = in_flight.get("time", "")

    # Format date with weekday
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.strptime(date_val, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        date_formatted = dt.strftime("%A, %d %B %Y")
    except Exception:
        date_formatted = date_val

    state["response_to_user"] = (
        f"Booked! Your booking code is **#{booking_code}**. "
        f"The advisor will reach out for a 30 minute call about '{topic}' "
        f"on {date_formatted} at {time_val} IST."
    )
    state["response_type"] = "booking"
    state["chat_closed"] = True

    # Clear in_flight now that booking is complete
    state["in_flight_booking"] = {"topic": None, "date": None, "time": None}

    return state


def classify_out_of_scope_node(state: dict) -> dict:
    """Classify an 'other' intent as investment-adjacent or unrelated."""
    user_input = state["user_input"]

    prompt = f"""You are classifying a user message for a mutual fund investor assistant.

User message: "{user_input}"

Recent conversation:
{json.dumps(_history_tail(state, 4), indent=2)}

Classify this message as exactly ONE of:
- "investment_adjacent" — the question is about mutual funds, investments, financial planning, or related to the user's financial situation, but not answerable from factsheet data or known themes. Examples: "Is now a good time to invest?", "How do I plan for retirement?", "What's a good asset allocation?"
- "unrelated" — the question has nothing to do with mutual funds, investments, or finance. Examples: "What's the IPL score?", "Tell me a joke", "What's the weather?"

Respond ONLY with JSON:
{{"category": "investment_adjacent" | "unrelated"}}"""

    result = _llm_json(prompt)
    category = result.get("category", "unrelated") if result else "unrelated"
    state["out_of_scope_category"] = category

    if category == "investment_adjacent":
        state["active_path"] = "out_of_scope_investment"
    else:
        state["active_path"] = "out_of_scope_unrelated"

    return state


def detect_slot_acceptance_node(state: dict) -> dict:
    """Interpret the user's response to an alternative slot suggestion.

    Routes:
    - accepted  → request_final_confirmation (with the updated in_flight_booking)
    - rejected  → ask the user for a different date/time
    """
    user_input = state["user_input"]
    in_flight = state.get("in_flight_booking", {})

    prompt = f"""You are interpreting a user's response to a suggested alternative appointment slot.

The user was told: "The slot is not available at that time. The next available slot is [alternative]. Would that work?"
for a 30 minute call about '{in_flight.get("topic", "your query")}'.

User's response: "{user_input}"

Classify the response as exactly ONE of:
- "accepted" — user agrees to the alternative slot (e.g. "yes", "sure", "that works", "ok", "sounds good", "yes it would work")
- "rejected" — user wants a different time or doesn't want the alternative (e.g. "no", "different time", "not that one", "how about 3pm")

Respond ONLY with JSON:
{{"response": "accepted" | "rejected"}}"""

    result = _llm_json(prompt)
    response_type = result.get("response", "rejected") if result else "rejected"

    if response_type == "accepted":
        state["active_path"] = "slot_accepted"
    else:
        state["active_path"] = "slot_rejected"

    return state


# ================================================================== #
# NODE 9 — generate_response                                          #
# Composes the final user-facing reply based on active_path.         #
# ================================================================== #

def generate_response_node(state: dict) -> dict:
    """Compose the final natural-language reply for the user."""
    in_flight = state.get("in_flight_booking", {})
    # Use `or` so that None (set but empty) also falls back to "other"
    active_path = state.get("active_path") or "other"
    state["response_links"] = []

    # ---- FAQ paths -------------------------------------------- #

    if active_path == "faq_answered":
        faq = state.get("faq_response", {})
        state["response_to_user"] = faq.get("text", "Here's what I found.")
        state["response_links"] = faq.get("links", [])
        state["response_type"] = "answer"

    elif active_path == "faq_clarify":
        faq = state.get("faq_response", {})
        state["response_to_user"] = faq.get("text", "Could you please clarify your question?")
        state["response_type"] = "clarify"

    elif active_path in ("faq_refused", "faq_error"):
        faq = state.get("faq_response", {})
        base = faq.get("text", "I don't have information on that.")
        state["response_to_user"] = (
            base + " Would you like me to book a call with an advisor who can help?"
        )
        state["response_type"] = "refuse"

    # ---- Theme paths ------------------------------------------- #

    elif active_path == "theme_match":
        theme = state.get("theme_match", {})
        prompt = f"""You are a helpful Groww (mutual fund / financial app) support assistant.

A user's message matches a theme we already track. Themes can be problems, feedback, or suggestions, not only bugs.

Theme: {theme.get("theme_name", "this area")}
Description: {theme.get("short_description", "")}
Actionable item: {theme.get("actionable_item", "")}

Write a SHORT response (max 2 sentences, under 45 words) that:
1. Acknowledges that this is feedback we have been hearing from users and that we will work to improve (do not call it only a "bug" or "known issue" unless the description is clearly a defect)
2. Offers to book an advisor call if they would like to discuss further

Be concise and direct. Do NOT say "I completely understand" or "I apologize". Do not say "I am an AI"."""
        text = _llm_text(prompt)
        state["response_to_user"] = text or (
            f"Users have been giving us similar feedback on {theme.get('theme_name', 'this')}, and we are working to improve. "
            "If you want, I can book a call with an advisor for you."
        )
        state["response_type"] = "theme"

    # ---- Booking collection paths ------------------------------ #

    elif active_path in ("booking_need_topic", "escalation_need_topic"):
        date_val = in_flight.get("date")
        time_val = in_flight.get("time")
        prefix = "I'd be happy to book a call with an advisor for you. "
        if date_val and time_val:
            prefix += f"I've noted {date_val} at {time_val} IST. "
        elif date_val:
            prefix += f"I've noted {date_val}. "
        elif time_val:
            prefix += f"I've noted {time_val}. "
        state["response_to_user"] = prefix + "What topic would you like to discuss?"
        state["response_type"] = "booking_collecting"

    elif active_path == "theme_miss_need_topic":
        date_val = in_flight.get("date")
        time_val = in_flight.get("time")
        prefix = (
            "I don't have a specific update on that issue right now. "
            "I can connect you with an advisor who can look into it. "
        )
        if date_val and time_val:
            prefix += f"I've noted {date_val} at {time_val} IST. "
        elif date_val:
            prefix += f"I've noted {date_val}. "
        elif time_val:
            prefix += f"I've noted {time_val}. "
        state["response_to_user"] = prefix + "What topic should I note for the call?"
        state["response_type"] = "booking_collecting"

    elif active_path in ("booking_have_topic", "booking_need_both"):
        topic_raw = in_flight.get("topic")
        topic_display = topic_raw.title() if topic_raw else "the call"
        state["response_to_user"] = (
            f"Got it, I'll book a call about '{topic_display}'. "
            "What date and time works best for you?"
        )
        state["response_type"] = "booking_collecting"

    elif active_path == "escalation_have_topic":
        topic_raw = in_flight.get("topic")
        topic_display = topic_raw.title() if topic_raw else "the call"
        date_val = in_flight.get("date")
        time_val = in_flight.get("time")
        
        msg = f"I'm sorry I couldn't fully help with that. I'd like to connect you with an advisor who can discuss '{topic_display}' in more detail. "
        if date_val and time_val:
            msg += f"Should I schedule this for {date_val} at {time_val} IST?"
        elif date_val:
            msg += f"I see you mentioned {date_val}. What time works best?"
        elif time_val:
            msg += f"I see you mentioned {time_val}. What date works best?"
        else:
            msg += "What date and time works best for you?"
            
        state["response_to_user"] = msg
        state["response_type"] = "booking_collecting"

    elif active_path == "theme_miss_have_topic":
        topic_raw = in_flight.get("topic")
        topic_display = topic_raw.title() if topic_raw else "the call"
        date_val = in_flight.get("date")
        time_val = in_flight.get("time")
        
        msg = f"I don't have a specific update on that issue right now, but I can connect you with an advisor. I've noted '{topic_display}' as the topic. "
        if date_val and time_val:
            msg += f"Should I schedule this for {date_val} at {time_val} IST?"
        elif date_val:
            msg += f"I see you mentioned {date_val}. What time works best?"
        elif time_val:
            msg += f"I see you mentioned {time_val}. What date works best?"
        else:
            msg += "What date and time works best for you?"
            
        state["response_to_user"] = msg
        state["response_type"] = "booking_collecting"

    elif active_path == "booking_need_date":
        topic_raw = in_flight.get("topic")
        topic_display = topic_raw.title() if topic_raw else "the call"
        time_val = in_flight.get("time")
        if time_val:
            state["response_to_user"] = f"Got it, I'll book a call about '{topic_display}' at {time_val}. What date works best for you?"
        else:
            state["response_to_user"] = f"I'd be happy to book a call about '{topic_display}' for you. What date and time works best for you?"
        state["response_type"] = "booking_collecting"

    elif active_path == "booking_need_time":
        topic_raw = in_flight.get("topic")
        topic_display = topic_raw.title() if topic_raw else "the call"
        date_str = in_flight.get("date")
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=ZoneInfo("Asia/Kolkata")
            )
            date_formatted = dt.strftime("%A, %d %B %Y")
        except Exception:
            date_formatted = date_str or "the chosen date"
        state["response_to_user"] = (
            f"Got it, I'll book a call about '{topic_display}' for {date_formatted}. "
            "What time works best?"
        )
        state["response_type"] = "booking_collecting"

    elif active_path == "booking_confirmed":
        booking = state.get("booking_request", {})
        date_val = booking.get("date", "")
        time_val = booking.get("time", "")
        topic = booking.get("topic", "your query")
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(date_val, "%Y-%m-%d").replace(
                tzinfo=ZoneInfo("Asia/Kolkata")
            )
            date_formatted = dt.strftime("%A, %d %B %Y")  # e.g. "Thursday, 08 May 2026"
        except Exception:
            date_formatted = date_val
        state["response_to_user"] = (
            f"Your call has been scheduled! Topic: '{topic}', "
            f"on {date_formatted} at {time_val} IST. "
            "An advisor will reach out to confirm the appointment."
        )
        state["response_type"] = "booking"

    # ---- Phase 4: Slot & Confirmation paths ------------------ #

    elif active_path in ("slot_unavailable", "awaiting_slot_acceptance"):
        # suggest_alternative_slot_node already composed response_to_user
        if not state.get("response_to_user"):
            state["response_to_user"] = "The slot is not available at that time. Would you like to try a different time?"
        state["response_type"] = state.get("response_type") or "booking_collecting"

    elif active_path == "slot_rejected":
        # User rejected the alternative — ask for a different date/time
        state["response_to_user"] = (
            "No problem. What date and time would you prefer?"
        )
        state["response_type"] = "booking_collecting"

    elif active_path == "awaiting_confirmation":
        # request_final_confirmation_node already composed response_to_user
        if not state.get("response_to_user"):
            in_flight = state.get("in_flight_booking", {})
            state["response_to_user"] = (
                f"To confirm: a 30 minute call about '{in_flight.get('topic', 'your query')}'. "
                "Should I book this?"
            )
        state["response_type"] = state.get("response_type") or "booking_collecting"

    elif active_path == "confirmation_exit":
        state["response_to_user"] = (
            "No problem! If you'd like to book a call later, just let me know. "
            "Is there anything else I can help with?"
        )
        state["response_type"] = "answer"
        # Clear booking state
        state["in_flight_booking"] = {"topic": None, "date": None, "time": None}

    elif active_path == "confirmation_ambiguous":
        in_flight = state.get("in_flight_booking", {})
        topic = in_flight.get("topic", "your query")
        date_val = in_flight.get("date", "")
        time_val = in_flight.get("time", "")
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(date_val, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            date_formatted = dt.strftime("%A, %d %B %Y")
        except Exception:
            date_formatted = date_val
        state["response_to_user"] = (
            f"I didn't catch that. Could you confirm: should I book a 30 minute call "
            f"about '{topic}' on {date_formatted} at {time_val} IST?"
        )
        state["response_type"] = "booking_collecting"
        state["active_path"] = "awaiting_confirmation"  # stay in confirmation mode

    elif active_path == "booking_executed":
        # close_chat_node already composed response_to_user
        if not state.get("response_to_user"):
            state["response_to_user"] = "Your appointment has been booked!"
        state["response_type"] = state.get("response_type") or "booking"

    elif active_path == "booking_execution_failed":
        state["response_to_user"] = (
            "I'm sorry, something went wrong while booking your appointment. "
            "Please try again later or contact support directly."
        )
        state["response_type"] = "error"

    # ---- Phase 4: Out-of-scope paths -------------------------- #

    elif active_path == "out_of_scope_investment":
        # Route to booking — this path goes to collect_booking_topic,
        # not generate_response. But handle it as a safety net.
        state["response_to_user"] = (
            "That's a great question for an advisor. "
            "I can book a call for you to discuss this in detail. "
            "What topic should I note down?"
        )
        state["response_type"] = "booking_collecting"

    elif active_path == "out_of_scope_unrelated":
        state["response_to_user"] = (
            "I'm a mutual fund assistant — I can help with fund data, known app issues, "
            "or booking a call with an advisor. "
            "How can I help you today?"
        )
        state["response_type"] = "answer"

    # ---- Phase 4: Cancel/Reschedule --------------------------- #

    elif active_path == "cancel_or_reschedule":
        state["response_to_user"] = (
            "I understand you'd like to cancel or reschedule. "
            "Currently, this needs to be handled by your advisor directly. "
            "You can also check your email for the booking confirmation with the advisor's contact details. "
            "Is there anything else I can help with?"
        )
        state["response_type"] = "answer"

    # ---- Other / General --------------------------------------- #

    elif active_path == "other":
        prompt = f"""You are a helpful Groww investor assistant (mutual funds & financial app).

User message: "{state['user_input']}"

Recent conversation:
{json.dumps(_history_tail(state, 4), indent=2)}

Respond helpfully and briefly. You can help with:
- Mutual fund factsheet questions (NAV, expense ratio, exit load, alpha, beta, etc.)
- Known app issues
- Booking calls with advisors

If the user is greeting or saying thanks, respond warmly and briefly."""
        text = _llm_text(prompt)
        state["response_to_user"] = text or "How can I help you today?"
        state["response_type"] = "answer"

    else:
        state["response_to_user"] = "Something went wrong. Please try again."
        state["response_type"] = "error"

    # ── Pending-booking-offer flag ──
    # Set True when the response we just composed ends with an offer to
    # book a call (FAQ refusal, theme match, investment-adjacent question).
    # detect_intent_node uses this on the next turn to intercept short
    # affirmative / negative replies and route them correctly.
    state["pending_booking_offer"] = active_path in (
        "faq_refused",
        "faq_error",
        "theme_match",
        "out_of_scope_investment",
    )

    return state
