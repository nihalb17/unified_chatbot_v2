# Sub-Architecture: Orchestrator Agent

## Purpose

This subsystem is the **user-facing layer** of the unified product. Every user query enters through here, and every reply to the user goes out from here. The other agents and tools in the system never talk to the user directly.

The orchestrator's job in this phase is **intent detection and pillar routing**. It figures out what the user wants and forwards the query to the right downstream pillar:

- **Theme check** — if the user describes a problem, check whether it matches a known theme.
- **FAQ pipeline** — if the user asks a factsheet-related question, hand off to the FAQ agent.
- **Booking pipeline** — if the user wants to schedule an appointment with an advisor, collect the necessary details (date, time, topic) and prepare a booking request.

The actual booking execution (calendar slot check, calendar write, MCP actions) is **out of scope for this phase**. In this phase the orchestrator only collects the booking inputs and produces a structured booking request. The booking pipeline will be wired up in the next phase.

---

## Key principle: orchestrator handles conversation, specialists handle specialty

The orchestrator owns:
- Conversation memory across turns.
- Intent detection.
- Reference resolution (e.g., "what about its expense ratio?" → resolve "its" to the scheme discussed earlier).
- Query rewriting (turning vague follow-ups into self-contained questions before calling the FAQ agent).
- Dissatisfaction detection and the escalation rule.
- Topic generation when escalating mid-conversation.
- Producing user-facing replies in natural language.

The orchestrator does NOT own:
- Knowledge of factsheet contents (that's the FAQ agent's job).
- Knowledge of mutual fund definitions (that's also the FAQ agent's job).
- Booking execution logic (deferred to the next phase).

This separation matters because it keeps each component focused, and it means the FAQ agent can stay as a stateless specialist that always receives clean, fully-specified questions.

---

## Inputs and outputs

### Inputs
- The user's current message (text).
- The conversation history so far.

### Outputs (one of)
- A natural-language reply to the user.
- A structured booking request (when the booking flow has gathered all required details). Format:
  ```
  {
    topic: string (1-3 words),
    date: string (ISO format),
    time: string (HH:MM),
    user_info: { ... whatever context is available ... }
  }
  ```
  In this phase, the orchestrator simply produces this structured request and surfaces a confirmation message to the user. Forwarding it to the booking pipeline is the next phase's responsibility.

---

## Three pillars the orchestrator routes between

### Pillar 1: Theme check
Triggered when the user describes a complaint or issue rather than asking a factual question.

Behavior:
- Look up the user's described issue against the Themes knowledge base.
- If it matches an active theme, respond with a "this is a known issue, fix is being worked on" message.
- If it doesn't match a theme, fall through to the booking flow (since the user has a problem the system doesn't have a known answer for).

### Pillar 2: FAQ pipeline
Triggered when the user asks a factsheet-related question (NAV, expense ratio, exit load, fund manager, etc.) or asks about a mutual fund concept.

Behavior:
- Resolve any vague references in the question using conversation history.
- Construct a clean, self-contained query for the FAQ agent.
- Call the FAQ agent.
- The FAQ agent returns one of three structured responses:
  - **answer** — orchestrator relays it to the user.
  - **needs_clarification** — orchestrator asks the user the clarifying question (possibly rephrased to match conversation tone).
  - **no_info** — orchestrator informs the user the system doesn't have that information, and may offer to escalate to booking.

### Pillar 3: Booking pipeline (this phase: collect-only)
Triggered when the user explicitly wants to talk to a human, schedule a call, or when the orchestrator escalates from another pillar.

Behavior in this phase:
- Collect three required fields through conversation: **topic**, **date**, **time**.
- For the topic:
  - If the user volunteers it, use it (condensed to 1-3 words).
  - If the user doesn't mention it, ask them.
  - If escalating from another pillar (FAQ or theme check), auto-generate the topic from conversation context — do NOT ask the user again.
- For date and time, ask the user if not already specified.
- Once all three are gathered, produce the structured booking request and confirm with the user that a booking will be scheduled. The actual execution is deferred to the next phase.

---

## The escalation rule

At any point in any pillar, if the user signals dissatisfaction OR explicitly asks for a human, the orchestrator must redirect to the booking pillar.

Triggers for escalation:
- User says things like "I'm not understanding," "this isn't helpful," "can I talk to someone," "I want to speak to a human."
- User repeatedly rephrases the same question (signal of confusion).
- The FAQ agent returns `no_info` and the user follows up indicating they still want help.
- The theme check returns "known issue" but the user pushes back wanting more direct assistance.

When escalation fires:
- The orchestrator immediately auto-generates a 1-3 word topic from conversation context. It does NOT ask "what's your topic?" since the conversation history already reveals it.
- The orchestrator then asks for date and time (if not already known).
- Once date and time are collected, produces the structured booking request as in Pillar 3.

Example:
> User in FAQ pillar: *"What's the exit load on my ELSS fund?"*
> FAQ agent answers, but user replies: *"This isn't helping, I want to talk to someone."*
> Orchestrator generates topic = "Exit load query" → asks for date and time → produces booking request.

---

## Conversation memory and reference resolution

The orchestrator maintains conversation state that persists across turns. This state includes:
- Full conversation history.
- The most recently mentioned scheme (if any).
- The most recently discussed concept (if any).
- The current intent / active pillar.
- Any partially-collected booking fields (e.g., topic already known, waiting for date and time).

Before calling the FAQ agent, the orchestrator uses this state to **rewrite vague queries into self-contained ones**. Examples:

| User says | State has | Rewritten query for FAQ agent |
|---|---|---|
| "What's the NAV?" | scheme = Axis ELSS | "What is the NAV of Axis ELSS?" |
| "What about its expense ratio?" | scheme = SBI Gold | "What is the expense ratio of SBI Gold?" |
| "What does that mean?" | last concept = exit load | "What does exit load mean?" |
| "What about HDFC Top 100?" | scheme = SBI Gold | New scheme; query becomes "Tell me about HDFC Top 100" (scheme switch detected) |

Rewriting is the orchestrator's job, not the FAQ agent's. The FAQ agent always receives complete questions and never has to guess at references.

---

## LangGraph implementation

The orchestrator is implemented using **LangGraph**, which models the workflow as a graph of nodes connected by edges, with shared state passed between them.

### Why LangGraph
- The architecture is naturally a stateful graph with conditional routing — exactly what LangGraph is built for.
- Conversation memory lives in the graph's state object, accessible to every node.
- Conditional edges handle pillar routing cleanly without nested if-statements.
- Loops are first-class — the user-orchestrator conversation is a natural cycle.
- Future human-in-the-loop pauses (e.g., the slot confirmation gate in the next phase) integrate cleanly.

### Shared state
Every node reads from and writes to a shared state object. The state contains at minimum:

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

### Graph nodes

The graph has the following nodes. Each does one focused thing.

**`detect_intent`** (LLM call)
- Reads conversation history and current user input.
- Detects intent: factsheet question, problem/complaint, booking request, escalation signal, or other.
- Updates `last_intent` in state.
- Also updates `current_scheme` and `current_concept` if the user mentioned them.

**`check_theme`** (deterministic lookup)
- Looks up the user's described issue against the Themes knowledge base.
- If a match is found, sets `theme_match` in state.

**`rewrite_query`** (LLM call or rule-based)
- Takes the user's raw question + state (conversation history, current_scheme, current_concept).
- Produces a self-contained query suitable for the FAQ agent.
- Stores it in `rewritten_query_for_faq`.

**`call_faq_agent`** (wraps the existing FAQ agent)
- Reads `rewritten_query_for_faq` from state.
- Calls the existing FAQ agent (which is treated as a black box — its internals are unchanged).
- Stores the FAQ agent's structured response in `faq_response`.

**`collect_booking_topic`** (LLM call or rule-based)
- If user volunteered a topic, extract and condense to 1-3 words.
- If escalating from FAQ or theme check, auto-generate topic from conversation context.
- If still missing and not escalating, prompt the user.
- Updates `in_flight_booking.topic`.

**`collect_booking_datetime`** (LLM call or rule-based)
- Parses date and time from user input ("tomorrow at 3 PM" → structured datetime).
- If missing, prompts the user.
- Updates `in_flight_booking.date` and `in_flight_booking.time`.

**`detect_escalation`** (LLM call or rule-based)
- Inspects user input for dissatisfaction signals.
- If escalation triggered, sets `last_intent = "booking"` and routes downstream.

**`generate_response`** (LLM call)
- Composes the final user-facing reply based on whichever pillar produced the result (theme match message, FAQ answer, clarification request, booking confirmation, etc.).
- Stores in `response_to_user`.

**`emit_booking_request`** (deterministic)
- When all three booking fields are present, packages them into the structured booking request output.
- In this phase, simply confirms with the user that a booking will be scheduled. In the next phase, this node will hand off to the booking pipeline.

### Graph edges and routing

```
START
  ↓
detect_escalation                  // checks before everything else
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
  ├─→ (status = answer)            → generate_response
  ├─→ (status = needs_clarification) → generate_response (relays clarification question)
  └─→ (status = no_info)           → generate_response (informs + may offer escalation)

collect_booking_topic
  ↓
collect_booking_datetime
  ├─→ (all booking fields present) → emit_booking_request → generate_response
  └─→ (still missing fields)       → generate_response (asks for missing info)

generate_response
  ↓
END (waits for next user turn, then START again with updated state)
```

### Key routing rules expressed in the graph

- **Escalation always wins.** The `detect_escalation` node runs first on every turn. If escalation is triggered, the user is routed straight into the booking flow regardless of whatever pillar they were in.
- **Theme miss = booking.** If the user describes a problem and it doesn't match any active theme, the orchestrator interprets this as "the system doesn't have a known answer, so let's get them to a human" and routes to booking.
- **FAQ no_info does NOT auto-escalate.** When the FAQ agent returns no_info, the orchestrator informs the user and may offer to book a call — but doesn't force it. The user has to express that they want help (which would trigger escalation on the next turn).
- **Booking collection is a multi-turn process.** The graph cycles through `collect_booking_topic` → `collect_booking_datetime` across multiple user turns until all three fields are present.

---

## Integration with the existing FAQ agent

The FAQ agent already exists. It is **not modified** in this phase.

The orchestrator wraps it in a single node (`call_faq_agent`) that:
- Sends the rewritten, self-contained query to the FAQ agent.
- Receives the FAQ agent's structured response.
- Packages it into shared state for the next graph node to use.

The FAQ agent does not know it is being called from a LangGraph context. Its internal implementation, prompts, and knowledge bases are untouched.

If the FAQ agent's current interface needs minor adjustments (e.g., to expose a single function that takes query + context and returns a structured response with a clear status), those small interface adjustments may be necessary — but no rewrite of its retrieval, RAG pipeline, or response generation logic is needed.

---

## Out of scope for this phase

These items are deferred to subsequent phases and the orchestrator should not attempt to handle them yet:

- **Calendar slot checking.** When a booking is requested in this phase, the orchestrator collects topic/date/time and produces a structured booking request. It does not check whether the slot is actually available.
- **Calendar writes and MCP actions.** No external calls to email, calendar, sheets, or docs in this phase.
- **Slot confirmation gate.** The "is this slot OK to book?" approval step happens after slot checking exists. In this phase, the orchestrator simply confirms with the user that the booking details have been captured.
- **Voice mode (Sarvam STT/TTS).** Text-only in this phase.

The orchestrator's graph should be designed so that adding these capabilities in the next phase is a matter of extending the graph (adding new nodes for slot check and execute booking, with a confirmation pause between them) rather than restructuring existing logic.

---

## Configuration

Values that should live as configuration, not hardcoded:

- LLM choice for the orchestrator (Groq).
- Themes knowledge base location.
- The existing FAQ agent's invocation interface (function call, HTTP endpoint, etc.).
- Escalation trigger phrases or model thresholds.

---

## Failure handling

- **LLM errors at any node** — return a graceful failure message to the user ("Something went wrong, please try again") and preserve conversation state so the next turn can recover.
- **FAQ agent unavailable** — the orchestrator informs the user it can't answer factsheet questions right now and offers to book a call instead.
- **Ambiguous intent** — the orchestrator asks a clarifying question rather than guessing and routing wrongly.
- **Booking field collection stalls** — if the user can't or won't provide a date or time after a few turns, the orchestrator should gracefully exit the booking flow rather than looping indefinitely.
