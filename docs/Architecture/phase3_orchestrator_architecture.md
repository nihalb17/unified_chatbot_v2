# Phase 3 — Orchestrator Agent: Sub-Architecture

> Detailed architecture for the Orchestrator Agent (Phase 3 of the Investor Ops & Intelligence Suite). This subsystem is the user-facing layer of the unified product — every user query enters through here, and every reply to the user goes out from here. It handles intent detection, pillar routing, conversation memory, and reference resolution before delegating to downstream specialists.

---

## Purpose

This subsystem is responsible for two things:

1. Maintaining **conversation state** across turns — tracking the active scheme, discussed concepts, partial booking fields, and current intent — so downstream agents always receive clean, fully-specified inputs.
2. Routing each user query to the correct pillar — **Theme Check**, **FAQ Pipeline**, or **Booking Pipeline** — and composing a coherent user-facing reply from whatever that pillar returns.

The subsystem operates as a stateful LangGraph workflow. Every node reads from and writes to a shared state object. Conditional edges implement the routing logic without nested if-statements. The user-orchestrator conversation is a natural cycle: START → node chain → END, then START again on the next user turn with updated state.

---

## System Overview

The system is a directed graph of focused nodes connected by conditional edges, all sharing a single state object.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Orchestrator Agent                                  │
│                                                                              │
│  EVERY TURN                                                                  │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐  │
│  │  detect_         │──▶│  detect_intent   │──▶│  Pillar Router           │  │
│  │  escalation      │   │                  │   │  (theme / faq / booking) │  │
│  └──────────────────┘   └──────────────────┘   └──────────────────────────┘  │
│                                                                              │
│  THREE PILLARS                                                               │
│  ┌──────────────┐   ┌──────────────────────────┐   ┌──────────────────────┐ │
│  │  Pillar 1    │   │       Pillar 2            │   │      Pillar 3        │ │
│  │  Theme Check │   │   FAQ Pipeline            │   │  Booking Pipeline   │ │
│  │              │   │   rewrite → call →        │   │  collect topic,     │ │
│  │  KB lookup   │   │   generate                │   │  date, time         │ │
│  └──────────────┘   └──────────────────────────┘   └──────────────────────┘ │
│                                                                              │
│  ALWAYS LAST                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │  generate_response  ──▶  END (await next user turn)                     │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Principle: Orchestrator Handles Conversation, Specialists Handle Specialty

The orchestrator owns:
- Conversation memory across turns.
- Intent detection.
- Reference resolution (e.g., "what about its expense ratio?" → resolve "its" to the scheme discussed earlier).
- Query rewriting (turning vague follow-ups into self-contained questions before calling the FAQ agent).
- Dissatisfaction detection and the escalation rule.
- Topic generation when escalating mid-conversation.
- Producing user-facing replies in natural language.

The orchestrator does NOT own:
- Knowledge of factsheet contents (that is the FAQ agent's job).
- Knowledge of mutual fund definitions (that is also the FAQ agent's job).
- Booking execution logic (deferred to the next phase).

---

## Inputs and Outputs

### Per-Turn Inputs

| Aspect | Description |
|---|---|
| **Trigger** | A new message from the user. |
| **Inputs** | The user's current message (text) and the conversation history so far. |

### Per-Turn Outputs

| Output Type | Description |
|---|---|
| **Natural-language reply** | A response to surface directly to the user — an FAQ answer, a theme match message, a clarifying question, or a booking confirmation. |
| **Structured booking request** | Emitted once all three booking fields are collected. Format: `{ topic, date (ISO), time (HH:MM), user_info }`. In this phase the orchestrator produces this request and confirms with the user; forwarding to the booking pipeline is the next phase's responsibility. |

---

## Three Pillars

### Pillar 1 — Theme Check

Triggered when the user describes a complaint or problem rather than asking a factual question.

| Step | Description |
|---|---|
| **1. KB lookup** | The user's described issue is looked up against the Themes knowledge base. |
| **2a. Match found** | Respond with a "this is a known issue, a fix is being worked on" message. |
| **2b. No match** | Fall through to the Booking Pipeline — the user has a problem the system has no known answer for, so routing to a human is appropriate. |

### Pillar 2 — FAQ Pipeline

Triggered when the user asks a factsheet-related question (NAV, expense ratio, exit load, fund manager, etc.) or asks about a mutual fund concept.

| Step | Description |
|---|---|
| **1. Reference resolution** | Resolve any vague references using conversation history (e.g., "its" → most recently mentioned scheme). |
| **2. Query rewriting** | Construct a clean, self-contained query for the FAQ agent. |
| **3. Call FAQ agent** | The FAQ agent is called with the rewritten query and returns a structured response. |
| **4a. Status = answer** | Orchestrator relays the answer to the user. |
| **4b. Status = needs_clarification** | Orchestrator asks the user the clarifying question (possibly rephrased to match conversation tone). |
| **4c. Status = no_info** | Orchestrator informs the user the system doesn't have that information and may offer to escalate to booking. |

### Pillar 3 — Booking Pipeline (this phase: collect-only)

Triggered when the user explicitly wants to speak to a human, or when the orchestrator escalates from another pillar.

| Step | Description |
|---|---|
| **1. Collect topic** | If the user volunteered it, extract and condense to 1-3 words. If escalating from another pillar, auto-generate the topic from conversation context (do NOT ask the user). If still missing, prompt the user. |
| **2. Collect date + time** | Parse from user input. If missing, prompt the user. |
| **3. Emit booking request** | Once all three fields are present, package them into the structured request and confirm with the user. |

> **Key point**: When escalating from another pillar (FAQ or theme check), the topic is always auto-generated from conversation context. The orchestrator never asks the user "what's your topic?" in an escalation scenario — the conversation history already reveals it.

---

## The Escalation Rule

At any point in any pillar, if the user signals dissatisfaction or explicitly asks for a human, the orchestrator immediately redirects to the Booking Pipeline. Escalation always wins — it is evaluated before intent detection on every turn.

### Escalation Triggers

| Trigger | Example |
|---|---|
| **Explicit human request** | "I want to speak to a human", "can I talk to someone" |
| **Dissatisfaction signal** | "I'm not understanding", "this isn't helpful" |
| **Repeated rephrasing** | User asks the same question multiple times — signal of confusion |
| **FAQ no_info + follow-up** | FAQ returns no_info and user follows up indicating they still want help |
| **Theme match push-back** | System reports a known issue but the user pushes back wanting direct assistance |

### When Escalation Fires

| Step | Description |
|---|---|
| **1. Auto-generate topic** | Topic is generated from conversation context immediately. The orchestrator does NOT ask "what's your topic?". |
| **2. Collect date + time** | Asks the user for date and time if not already known from the conversation. |
| **3. Produce booking request** | Once date and time are collected, emits the structured booking request. |

**Worked example:**
> User in FAQ pillar: *"What's the exit load on my ELSS fund?"*
> FAQ agent answers, but user replies: *"This isn't helping, I want to talk to someone."*
> Orchestrator generates topic = "Exit load query" → asks for date and time → produces booking request.

---

## Conversation Memory and Reference Resolution

The orchestrator maintains a shared state object that persists across turns. Before calling the FAQ agent, it uses this state to rewrite vague queries into self-contained ones.

### Shared State Schema

```
{
  conversation_history: list,        // all turns so far
  user_input: string,                // current user message
  current_scheme: string | null,     // most recently mentioned scheme
  current_concept: string | null,    // most recently discussed concept
  last_intent: string | null,        // "faq" | "theme" | "booking" | "other"
  in_flight_booking: {               // partially-collected booking fields
    topic: string | null,
    date: string | null,
    time: string | null,
  },
  rewritten_query_for_faq: string | null,   // self-contained query for FAQ agent
  faq_response: object | null,              // structured FAQ agent response
  theme_match: object | null,               // matched theme if any
  response_to_user: string | null,          // final reply to surface to user
}
```

### Query Rewriting Examples

| User says | State has | Rewritten query for FAQ agent |
|---|---|---|
| "What's the NAV?" | scheme = Axis ELSS | "What is the NAV of Axis ELSS?" |
| "What about its expense ratio?" | scheme = SBI Gold | "What is the expense ratio of SBI Gold?" |
| "What does that mean?" | last concept = exit load | "What does exit load mean?" |
| "What about HDFC Top 100?" | scheme = SBI Gold | New scheme; query becomes "Tell me about HDFC Top 100" (scheme switch detected) |

> Rewriting is the orchestrator's job, not the FAQ agent's. The FAQ agent always receives complete questions and never has to guess at references.

---

## LangGraph Implementation

### Graph Nodes

Each node does one focused thing.

| Node | Type | Description |
|---|---|---|
| **`detect_escalation`** | LLM call or rule-based | Inspects user input for dissatisfaction signals. If escalation triggered, sets `last_intent = "booking"` and routes downstream. Runs first on every turn. |
| **`detect_intent`** | LLM call | Reads conversation history and current user input. Detects intent: factsheet question, problem/complaint, booking request, escalation signal, or other. Updates `last_intent`, `current_scheme`, and `current_concept`. |
| **`check_theme`** | Deterministic lookup | Looks up the user's described issue against the Themes knowledge base. If a match is found, sets `theme_match` in state. |
| **`rewrite_query`** | LLM call or rule-based | Takes the user's raw question plus state (conversation history, current_scheme, current_concept). Produces a self-contained query for the FAQ agent. Stores it in `rewritten_query_for_faq`. |
| **`call_faq_agent`** | Wraps existing FAQ agent | Reads `rewritten_query_for_faq` from state. Calls the FAQ agent (treated as a black box). Stores the structured response in `faq_response`. |
| **`collect_booking_topic`** | LLM call or rule-based | Extracts and condenses topic from user input, auto-generates from context if escalating, or prompts the user. Updates `in_flight_booking.topic`. |
| **`collect_booking_datetime`** | LLM call or rule-based | Parses date and time from user input. If missing, prompts the user. Updates `in_flight_booking.date` and `in_flight_booking.time`. |
| **`emit_booking_request`** | Deterministic | When all three booking fields are present, packages them into the structured booking request output and confirms with the user. |
| **`generate_response`** | LLM call | Composes the final user-facing reply from whichever pillar produced the result. Stores in `response_to_user`. |

---

### Graph Edges and Routing

```
START
  ↓
detect_escalation
  ├─→ (if escalation triggered) → collect_booking_topic
  └─→ (otherwise) → detect_intent

detect_intent
  ├─→ (intent = theme)        → check_theme
  ├─→ (intent = faq)          → rewrite_query → call_faq_agent → generate_response
  ├─→ (intent = booking)      → collect_booking_topic
  └─→ (intent = other)        → generate_response

check_theme
  ├─→ (theme matched)         → generate_response
  └─→ (no match)              → collect_booking_topic   // fall through to booking

call_faq_agent
  ├─→ (status = answer)              → generate_response
  ├─→ (status = needs_clarification) → generate_response (relays clarification question)
  └─→ (status = no_info)             → generate_response (informs + may offer escalation)

collect_booking_topic
  ↓
collect_booking_datetime
  ├─→ (all booking fields present) → emit_booking_request → generate_response
  └─→ (still missing fields)       → generate_response (asks for missing info)

generate_response
  ↓
END (waits for next user turn, then START again with updated state)
```

### Key Routing Rules

| Rule | Description |
|---|---|
| **Escalation always wins** | `detect_escalation` runs first on every turn. If escalation is triggered, the user is routed straight into the booking flow regardless of whatever pillar they were in. |
| **Theme miss = booking** | If the user describes a problem and it doesn't match any active theme, the orchestrator routes to the booking pipeline — the system has no known answer, so getting them to a human is appropriate. |
| **FAQ no_info does not auto-escalate** | When the FAQ agent returns no_info, the orchestrator informs the user and may offer to book a call — but doesn't force it. The user must express that they want help (triggering escalation on the next turn). |
| **Booking collection is multi-turn** | The graph cycles through `collect_booking_topic` → `collect_booking_datetime` across multiple user turns until all three fields are present. |

---

## Worked Examples

### Example 1 — The Reference Resolution Case

> **User turn 1:** "What's the exit load on Axis Bluechip?"
> **User turn 2:** "And what does that mean exactly?"

| Step | Action |
|---|---|
| **1. Turn 1 — intent** | intent = faq, scheme = Axis Bluechip, concept = exit load. |
| **2. Turn 1 — rewrite** | Query is already self-contained: "What is the exit load of Axis Bluechip?" |
| **3. Turn 1 — FAQ** | Returns the exit load value and a definition. |
| **4. Turn 2 — intent** | intent = faq, `current_concept` = exit load (from state). |
| **5. Turn 2 — rewrite** | "What does that mean?" → "What does exit load mean?" |
| **6. Turn 2 — FAQ** | Returns the definition of exit load. Orchestrator relays it to the user. |

---

### Example 2 — The Escalation Case

> **User:** *"What's the alpha of Mirae Asset?"* → FAQ answers.
> **User:** *"I still don't get it. Can I talk to someone?"*

| Step | Action |
|---|---|
| **1. detect_escalation** | "Can I talk to someone" is an escalation trigger. |
| **2. collect_booking_topic** | Conversation context reveals "Mirae Asset / alpha". Topic auto-generated: "Alpha query". |
| **3. collect_booking_datetime** | "When would you like to schedule the call?" |
| **4. emit_booking_request** | `{ topic: "Alpha query", date: "...", time: "...", user_info: {} }` confirmed with user. |

---

### Example 3 — The Theme Miss → Booking Fallthrough Case

> **User:** "My SIP didn't process yesterday."

| Step | Action |
|---|---|
| **1. detect_intent** | intent = theme (problem/complaint). |
| **2. check_theme** | No matching theme found in the knowledge base. |
| **3. collect_booking_topic** | Routes to booking. Topic extracted from context: "SIP processing". |
| **4. collect_booking_datetime** | Asks the user for a preferred date and time. |
| **5. emit_booking_request** | Structured request produced once date and time are provided. |

---

## End-to-end System Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  EVERY TURN                                                                  │
│                                                                              │
│  detect_escalation ──▶ (if triggered) ─────────────────────────────────┐    │
│                   └──▶ (otherwise) ──▶ detect_intent                   │    │
│                                                                         │    │
│  detect_intent                                                          │    │
│  ├── intent = theme   ──▶ check_theme                                   │    │
│  │     ├── match       ──▶ generate_response                            │    │
│  │     └── no match    ──▶ collect_booking_topic ◀───────────────────┐  │    │
│  │                                                                    │  │    │
│  ├── intent = faq     ──▶ rewrite_query ──▶ call_faq_agent            │  │    │
│  │     ├── answer            ──▶ generate_response                    │  │    │
│  │     ├── needs_clarification──▶ generate_response                   │  │    │
│  │     └── no_info           ──▶ generate_response                    │  │    │
│  │                                                                    │  │    │
│  ├── intent = booking  ──────────────────────────────────────────────▶┘  │    │
│  └── intent = other   ──▶ generate_response                           │  │    │
│                                                                        │  │    │
│  collect_booking_topic ──▶ collect_booking_datetime ◀──────────────────┘  │    │
│  ├── all fields present ──▶ emit_booking_request ──▶ generate_response    │    │
│  └── missing fields     ──▶ generate_response (ask for missing info) ◀────┘    │
│                                                                              │
│  generate_response ──▶ END (await next user turn)                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Handling

| Scenario | Behaviour |
|---|---|
| **LLM error at any node** | Return a graceful failure message to the user ("Something went wrong, please try again") and preserve conversation state so the next turn can recover. |
| **FAQ agent unavailable** | Inform the user that factsheet questions can't be answered right now and offer to book a call with an advisor instead. |
| **Ambiguous intent** | Ask a clarifying question rather than guessing and routing incorrectly. |
| **Booking collection stall** | If the user cannot or will not provide a date or time after several turns, gracefully exit the booking flow rather than looping indefinitely. |
| **Theme knowledge base unreachable** | Log the failure, skip the theme check, and fall through to the booking pipeline as if no match was found. |

---

## Configuration

All values below are configurable (config file or environment variables), not hardcoded:

| Parameter | Description |
|---|---|
| LLM model | LLM used for the orchestrator's reasoning nodes (Groq). |
| Themes knowledge base location | Path or endpoint for the Themes KB used by `check_theme`. |
| FAQ agent invocation interface | How `call_faq_agent` reaches the FAQ agent (function call or HTTP endpoint). |
| Escalation trigger phrases | Phrases or model thresholds that cause `detect_escalation` to fire. |
| Booking field collection turn limit | Max turns the orchestrator waits for a missing booking field before exiting the booking flow. |

---

## Downstream Consumers

| Consumer | What it reads | Phase |
|---|---|---|
| **User Portal (Frontend)** | Receives every `response_to_user` reply and renders it in the chat interface. | Phase 3 |
| **Booking Pipeline** | Receives the structured booking request emitted by `emit_booking_request`. | Phase 4 |
| **FAQ Agent** | Receives rewritten, self-contained queries from `call_faq_agent` and returns structured responses. | Phase 2 |
| **Themes Knowledge Base** | Queried by `check_theme` for each complaint-type intent. | Phase 1 |

---

## Dependencies on the Broader Product

This subsystem reads from the Themes knowledge base (Phase 1) and the FAQ agent (Phase 2). It writes structured booking requests to the Booking Pipeline (Phase 4). It is the only component in the system that talks directly to the user — all other agents and tools communicate through the orchestrator.

> The orchestrator is the **user-facing layer**. Downstream agents (FAQ agent, booking pipeline) are internal specialists that receive clean inputs and return structured outputs. They do not interact with the user directly.

---

## Out of Scope for This Phase

These items are deferred to subsequent phases:

| Item | Deferred to |
|---|---|
| **Calendar slot checking** | Phase 4 — the orchestrator collects topic/date/time but does not verify availability. |
| **Calendar writes and MCP actions** | Phase 4 — no external calls to email, calendar, sheets, or docs in this phase. |
| **Slot confirmation gate** | Phase 4 — the approval step ("is this slot OK?") is added when slot checking exists. |
| **Voice mode (Sarvam STT/TTS)** | Phase 5 — text-only in this phase. |

> The orchestrator's graph should be designed so that adding these capabilities is a matter of extending it (adding new nodes for slot check and booking execution) rather than restructuring existing logic.
