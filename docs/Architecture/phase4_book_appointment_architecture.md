# Phase 4 — Book Appointment: Sub-Architecture

> Detailed architecture for the Book Appointment subsystem (Phase 4 of the Investor Ops & Intelligence Suite). This subsystem completes the booking flow that the orchestrator started in Phase 3 — extending the graph with slot availability checking, final user confirmation, booking code generation, and execution of all booking side effects (calendar event, broker email, meeting notes Doc, dashboard log). There is no separate booking agent; all booking-related work is handled by the orchestrator itself.

---

## Purpose

This subsystem is responsible for two things:

1. **Validating and confirming** the booking inputs (topic, date, time) collected in Phase 3 — checking calendar availability, suggesting alternatives when needed, and getting final user confirmation before committing.
2. **Executing the booking** once confirmed — generating a unique 4-digit booking code, creating four linked artifacts (calendar event, broker email, meeting notes Doc, dashboard log entry), and surfacing a closing confirmation to the user.

The subsystem operates as an extension of the orchestrator's LangGraph workflow. New nodes are added after the existing `collect_booking_datetime` node. The shared state gains additional fields for booking execution tracking. The user-orchestrator conversation continues to be a natural cycle: START → node chain → END, then START again on the next user turn with updated state.

---

## System Overview

The system extends the orchestrator's directed graph with six new stages, all running within the orchestrator — no separate booking agent exists.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Book Appointment (Phase 4 Extension)                     │
│                                                                              │
│  AFTER EXISTING collect_booking_datetime (all fields present)                │
│                                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────────┐ │
│  │  Stage 1     │──▶│  Stage 2     │──▶│  Stage 3                        │ │
│  │  Slot Check  │   │  Handle      │   │  Final                          │ │
│  │  (MCP read)  │   │  Unavailable │   │  Confirmation                   │ │
│  └──────────────┘   └──────────────┘   └──────────────────────────────────┘ │
│                                                                              │
│  ┌──────────────┐   ┌──────────────────────────────────────────────────┐    │
│  │  Stage 4     │──▶│  Stage 5 (four sequential side effects via MCP) │    │
│  │  Booking     │   │  Calendar → Email → Doc → Dashboard Log         │    │
│  │  Code Gen    │   └──────────────────────────────────────────────────┘    │
│  └──────────────┘                                                            │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 6 — Confirm to user + close chat (with optional "Send me    │    │
│  │  the booking details" button)                                        │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ALSO: classify_out_of_scope node for out-of-scope intent handling          │
│  ALSO: cancellation/reschedule detection in detect_intent                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Principle: Orchestrator Handles Conversation AND Booking, Tools Handle Side Effects

The orchestrator owns:
- Slot availability checking (delegated to a deterministic tool via MCP calendar reads).
- Suggesting alternative slots when the requested slot is unavailable.
- Final confirmation prompting and interpreting the user's confirmation response.
- Distinguishing "no, but" (change slot/topic) from "no, stop" (exit booking).
- Generating the booking code.
- Composing the user-facing closing message.

The orchestrator does NOT own:
- Calendar event creation — delegated to an MCP tool.
- Email sending — delegated to an MCP tool.
- Google Doc creation — delegated to an MCP tool.
- Dashboard log writes — delegated to a deterministic write function.

All four side effects share the booking code as a common linking identifier. The orchestrator orchestrates them in sequence; it does not execute them itself.

---

## Inputs and Outputs

### Per-Turn Inputs

| Aspect | Description |
|---|---|
| **Trigger** | All three booking fields (topic, date, time) have been collected in the prior phase, or the user provides a new date/time during the slot negotiation loop. |
| **Inputs** | The collected `in_flight_booking` fields from state, plus the user's current message (for confirmation responses and slot negotiation). |

### Per-Turn Outputs

| Output Type | Description |
|---|---|
| **Booking confirmed** | A closing message with a 4-digit booking code, topic, date, and time. The chat session ends. |
| **Booking declined by user** | The user said no during final confirmation — nothing is booked. The orchestrator gracefully exits the booking flow. |
| **Slot unavailable, alternative offered** | The requested slot was taken or conflicting; the orchestrator suggests the next available slot and waits for the user's response. |
| **Clarification prompt** | The user's confirmation response was ambiguous; the orchestrator asks whether they want to try a different time or skip the booking. |

---

## The 4-Digit Booking Code

The booking code is the **single linking identifier** across all four artifacts. It appears in:

- The user's confirmation message.
- The calendar event title.
- The email to the organization broker (subject and body).
- The Google Doc title.
- The internal dashboard's meetings log entry.

This means anyone in the system — user, broker, ops team — can reference one code and find the corresponding meeting consistently across all surfaces.

The code is generated at booking time, after the user has confirmed but before any side effects are executed, so the same code is available to all four MCP operations.

---

## Six Stages

### Stage 1 — Slot Availability Check

Once topic, date, and time are collected, the orchestrator runs a **calendar slot check**. This is a deterministic operation that:

- Reads the calendar via MCP to see if there is a **conflicting event** at the requested slot.
- Returns one of:
  - **Available** — no conflicting event in the calendar at that slot.
  - **Unavailable** — there is a conflicting event. The next available 30-minute slot is computed and returned as a suggestion.

Slots are **always 30 minutes**. There is no flexibility on duration in this phase.

In this phase there are **no working-hours, lunch-break, or holiday checks**. The only constraint is "is the calendar free at that time." Working hours, lunch, and holidays may be added in a future phase if needed; the design should leave room for them but not implement them now.

The next-available-slot logic is rule-based: scan forward from the requested time in 30-minute increments, return the first slot the calendar shows as free. This is plain code, not an LLM call.

### Stage 2 — Handle Unavailable Slots

If the slot is unavailable:

- The orchestrator tells the user the requested slot has a conflicting event already in the calendar.
- The orchestrator suggests the next available 30-minute alternative.
- If the user accepts the alternative, the flow continues with the alternative slot.
- If the user proposes a different time, the flow loops back to Stage 1 with the new time.
- The user can also say "never mind" or "let me think about it" — the orchestrator gracefully exits the booking flow without creating any artifacts.

### Stage 3 — Final Confirmation

If the slot is available, the orchestrator asks the user for **final confirmation** before proceeding. The confirmation message includes the topic, date, and time as captured.

Example:
> *"Got it. To confirm: a 30-minute call about 'Exit load query' on May 15 at 3:00 PM. Should I book this?"*

The user response is interpreted into one of these cases:

| User Response | Action |
|---|---|
| **Yes / confirmed** | Proceed to Stage 4 (booking code generation). |
| **No, but different time** | User rejects *this* slot but still wants to book. The orchestrator captures the new date/time and loops back to Stage 1. |
| **No, never mind / cancel** | User exits the flow entirely. The orchestrator gracefully ends the booking without creating any artifacts. |
| **Wants to change the topic** | Orchestrator updates the topic and loops back to Stage 3 for re-confirmation. |

The key distinction the orchestrator must make is **"no, but"** vs. **"no, stop"**. A bare "no" without further detail should prompt the orchestrator to ask: *"No problem — would you like to try a different time, or skip the booking?"* rather than assuming exit. The flow is forgiving — the user can change their mind multiple times before either confirming or explicitly exiting.

### Stage 4 — Generate Booking Code

Once the user confirms, the orchestrator generates a **4-digit booking code**. The code is unique within the system and serves as the linking identifier across all four artifacts created in the next stage.

The code generation logic should:
- Produce a 4-digit numeric code.
- Avoid collisions with existing bookings (check against the meetings log).
- Be human-readable (no leading zeros if avoidable, or accept leading zeros if uniqueness requires it).

### Stage 5 — Execute Booking (Four Sequential Side Effects via MCP)

The orchestrator now executes the booking by performing four operations. All four happen via MCP. They share the booking code as a common identifier.

**1. Create calendar event**
- Title includes the booking code and the topic (e.g., `[#4729] Exit load query`).
- Date, time, and duration set per the confirmed slot.
- Created in the organization's calendar via MCP.

**2. Email the organization broker**
- Sent via MCP.
- Subject and body include the booking code, topic, date, time, and any context from the conversation that would help the broker prepare for the meeting.
- Recipient is the configured organization broker email.

**3. Create Google Doc for meeting notes**
- Created via MCP.
- The Doc's title includes the booking code (e.g., `Meeting Notes - #4729 - Exit load query - May 15`).
- Contains a basic template with sections like agenda, discussion points, action items, ready for the broker to fill during/after the meeting.
- The Doc is also attached to the calendar event so it's accessible from the event itself.

**4. Log to internal dashboard's meetings store**
- An entry is appended to the meetings log used by the internal dashboard.
- Entry includes: booking code, topic, date, time, broker assigned, Google Doc link, calendar event reference, status (initially "scheduled"), and creation timestamp.
- This is the source of truth that the dashboard's Scheduled Appointments menu reads from.

The four execute nodes run in sequence. They could run in parallel for speed, but sequential execution makes failure handling simpler in this phase. If parallel execution is needed later for performance, the graph can be restructured.

If any of the four operations fails, the orchestrator should attempt graceful recovery (retry once, then surface the failure to the user with the booking code so the operation can be completed manually). Partial-success states are surfaced clearly — e.g., "calendar event created but email failed" should be visible in logs, not silently swallowed.

### Stage 6 — Confirm to User and Close the Chat

Once the booking is executed, the orchestrator surfaces the final confirmation to the user in a message that **closes the chat session**. The user cannot continue interacting in the same session after a booking is completed — the session ends with the booking confirmation.

The closing message includes:

- The booking code, prominently displayed.
- The topic, date, and time of the booking.
- A note that an advisor will be in touch.
- An **optional action button**: *"Send me the booking details"*.

Example closing message:
> *"Booked! Your booking code is **#4729**. The advisor will reach out for a 30-minute call about 'Exit load query' on May 15 at 3:00 PM."*
>
> *[Send me the booking details]*

### The "Send me the booking details" Optional Flow

This is an explicit user-initiated action, not automatic. When the user clicks the button in the chat closing message:

- A small popup or inline form appears asking for the user's email address.
- The user types their email and clicks "Send".
- The system sends a separate email to that user-provided address with the booking details (booking code, topic, date, time, and a brief note).

Important properties of this email:

- **Separate from the broker email.** The broker received their own notification email in Stage 5. This email is to the *user* and contains the same booking details framed for the user (not as a meeting brief for an advisor).
- **User-initiated and optional.** If the user doesn't click the button, no email is sent to them. The system never auto-emails the user.
- **Sent via MCP** like all other email operations.
- **Single-shot.** After the user submits, the popup closes and the user cannot send the booking details to a second email address from the chat session.

If the user chooses not to click the button, the chat ends with just the in-chat confirmation. The user can always reference the booking code if they need to contact the advisor or the system later.

---

## No Cancellation, No Rescheduling

The orchestrator **does not support** cancellation or rescheduling of existing bookings. This is an intentional simplification.

- If a user wants to cancel: the orchestrator informs them they can simply not show up — no-shows are acceptable. No system-level cancellation flow exists.
- If a user wants to reschedule: the orchestrator instructs them to book a new appointment. The old booking remains as-is in the system. The user notes the new booking code, and the broker handles any cleanup of the old slot manually if needed.

The orchestrator should detect cancellation/reschedule intent and respond gracefully:

> *"We don't support cancelling existing bookings — you can simply not attend if you can't make it. If you'd like to book a different time instead, I can set up a new appointment for you."*

This keeps the booking flow strictly forward-only and avoids the complexity of state transitions on existing bookings.

---

## Out-of-Scope Handling (The "Else" Branch)

The orchestrator routes user inputs into one of three primary pillars: theme check, FAQ pipeline, or booking. Anything else falls into a catch-all that this phase handles correctly.

There are **two distinct out-of-scope categories**, and they require different responses.

### Category A — Investment-Related but Not in Any Pillar

Questions that are about mutual funds, investments, or financial planning, but don't match any active theme and aren't answerable from the factsheet knowledge base. Examples:

- *"Is now a good time to invest in equity funds?"*
- *"How do I plan for retirement?"*
- *"What's a good asset allocation for someone in their 30s?"*

These questions are **legitimate** but beyond what the system can answer. The orchestrator should:

- Acknowledge the question briefly.
- Suggest scheduling a call with an advisor who can help.
- Offer to start the booking flow.

Example response:
> *"That's a great question, but it's not something I can answer well — it depends on your specific situation. Would you like to schedule a call with an advisor to discuss it?"*

If the user agrees, the orchestrator enters the booking flow with topic auto-generated from the question.

### Category B — Out-of-Scope (Random or Unrelated Questions)

Questions that have nothing to do with mutual funds, investments, or the user's relationship with Groww. Examples:

- *"What's the latest IPL score?"*
- *"Who won the Oscar this year?"*
- *"Tell me a joke."*
- *"What's the weather in Mumbai?"*

These questions are **not appropriate to escalate to a booking** — booking an advisor call about the IPL score is absurd. The orchestrator should:

- Politely decline.
- Briefly state that this isn't something it can help with.
- Optionally redirect to what it *can* help with.

Example response:
> *"I can't help with that. I'm here to answer questions about your investments, help with mutual fund queries, or schedule a call with an advisor."*

The key distinction the orchestrator must make is **investment-related vs. genuinely unrelated**. The first category gets a "let me set up a call" response. The second gets a "this isn't something I can help with" response.

This classification happens during intent detection. The orchestrator's intent detection node should recognize these two categories explicitly and route accordingly.

---

## Conversation Memory and Booking State

The orchestrator maintains a shared state object that persists across turns. This phase extends the state from Phase 3 with additional booking execution fields.

### Extended State Schema

```
{
  // --- Existing fields from Phase 3 ---
  conversation_history: list,
  user_input: string,
  current_scheme: string | null,
  current_concept: string | null,
  last_intent: string | null,         // "faq" | "theme" | "booking" | "other"
  in_flight_booking: {
    topic: string | null,
    date: string | null,
    time: string | null,
  },
  rewritten_query_for_faq: string | null,
  faq_response: object | null,
  theme_match: object | null,
  response_to_user: string | null,

  // --- New fields for Phase 4 ---
  slot_check_result: object | null,        // { available: bool, conflicting_event_summary, suggested_alternative }
  booking_confirmed_by_user: bool | null,  // result of final confirmation
  booking_code: string | null,             // 4-digit code, generated after confirmation
  booking_artifacts: {                     // tracks side effect completion
    calendar_event_id: string | null,
    broker_email_sent: bool,
    google_doc_id: string | null,
    google_doc_url: string | null,
    dashboard_log_id: string | null,
  },
  user_details_email_sent_to: string | null,  // populated only if user clicks "Send me details"
  out_of_scope_category: "investment_adjacent" | "unrelated" | null,
}
```

### Booking State Transitions

| State | Trigger | Next State |
|---|---|---|
| All booking fields collected | — | Slot check requested |
| Slot available | MCP calendar read returns no conflict | Awaiting final confirmation |
| Slot unavailable | MCP calendar read returns conflict | Offering alternative |
| User accepts alternative | User says yes to suggested slot | Awaiting final confirmation |
| User proposes new time | User provides different date/time | Slot check requested (loop) |
| User confirms booking | User says yes | Booking code generated |
| User changes slot at confirmation | "No, but [different time]" | Slot check requested (loop) |
| User changes topic at confirmation | "Can we change the topic?" | Topic updated, re-confirm |
| User exits booking | "Never mind" / "Cancel" | Booking flow exited, no artifacts |
| Booking code generated | Deterministic code creation | Executing side effects |
| All four side effects complete | Calendar + email + doc + log done | Chat closed with confirmation |

---

## LangGraph Implementation

This phase extends the orchestrator's graph from Phase 3. The shared state and most nodes carry over; new nodes and edges are added for the booking execution.

### Graph Nodes

Each node does one focused thing.

| Node | Type | Description |
|---|---|---|
| **`check_slot_availability`** | Deterministic (MCP read) | Reads the calendar via MCP for the requested 30-minute window. Returns available if no conflicting event exists, unavailable otherwise. Updates `slot_check_result` in state. |
| **`suggest_alternative_slot`** | Deterministic (MCP read) | Scans forward from the requested time in 30-minute increments via MCP calendar reads. Returns the first slot with no conflicting event. |
| **`request_final_confirmation`** | LLM call | Composes the confirmation prompt to surface to the user. Waits for user input on the next turn. |
| **`detect_confirmation_response`** | LLM call or rule-based | Interprets the user's response to the confirmation prompt. Returns one of: `confirmed`, `change_slot` (with the new slot extracted), `change_topic`, `exit`, or `ambiguous`. |
| **`generate_booking_code`** | Deterministic | Generates a unique 4-digit code, checking against existing logs to avoid collisions. Updates `booking_code` in state. |
| **`execute_calendar_create`** | MCP tool call | Creates the calendar event with the booking code in the title. Updates `booking_artifacts.calendar_event_id`. |
| **`execute_broker_email`** | MCP tool call | Sends the email to the broker with the booking code in the subject and body. Updates `booking_artifacts.broker_email_sent`. |
| **`execute_doc_create`** | MCP tool call | Creates the Google Doc with the booking code in the title. Attaches the Doc to the calendar event. Updates `booking_artifacts.google_doc_id` and `booking_artifacts.google_doc_url`. |
| **`execute_dashboard_log`** | Deterministic write | Appends a row to the meetings log used by the internal dashboard. Updates `booking_artifacts.dashboard_log_id`. |
| **`close_chat_with_confirmation`** | Deterministic | Composes the chat-closing message with the booking code, topic, date, and time. Surfaces the optional "Send me the booking details" action to the user. Marks the chat session as closed for further interaction. |
| **`send_user_details_email`** | MCP tool call (user-initiated) | Triggered only when the user clicks "Send me the booking details" and submits an email address. Sends a separate email (distinct from the broker email) with the booking details framed for the user. Updates `user_details_email_sent_to` in state. |
| **`classify_out_of_scope`** | LLM call | When intent doesn't match theme, FAQ, or booking, this node classifies whether the question is investment-adjacent or genuinely unrelated. Sets `out_of_scope_category` in state. |

---

### Graph Edges and Routing

```
AFTER the existing "collect_booking_topic → collect_booking_datetime" chain,
when all booking fields are present:

  collect_booking_datetime
    ↓
  check_slot_availability
    ├─→ (available)   → request_final_confirmation
    └─→ (unavailable) → suggest_alternative_slot → generate_response (offers alternative)
                          ↓ (user accepts alternative)
                        check_slot_availability (loop back with new slot)

  request_final_confirmation
    ↓ (user responds on next turn)
  detect_confirmation_response
    ├─→ (confirmed)    → generate_booking_code
    ├─→ (change_slot)  → check_slot_availability (with the new slot)
    ├─→ (change_topic) → collect_booking_topic (then back through datetime/check/confirm)
    ├─→ (exit)         → generate_response (graceful exit, no artifacts)
    └─→ (ambiguous)    → generate_response (asks: try different time or skip booking?)

  generate_booking_code
    ↓
  execute_calendar_create
    ↓
  execute_broker_email
    ↓
  execute_doc_create
    ↓
  execute_dashboard_log
    ↓
  close_chat_with_confirmation     // closing message + "Send me details" button
    ↓
  END (chat session closed)

  // Optional user-initiated branch, separate from the main flow
  user clicks "Send me the booking details"
    ↓
  send_user_details_email
    ↓
  popup closes

For out-of-scope handling, intent detection routes to:

  detect_intent
    └─→ (intent = other) → classify_out_of_scope
                              ├─→ (investment_adjacent) → collect_booking_topic
                              └─→ (unrelated)           → generate_response (politely decline)

For cancellation/reschedule detection:

  detect_intent
    └─→ (intent = cancel_or_reschedule) → generate_response
        (explains no cancel/reschedule support, offers new booking)
```

---

### Key Routing Rules

| Rule | Description |
|---|---|
| **Slot check before confirmation** | The orchestrator always checks slot availability before asking for final confirmation. The user never confirms a slot that hasn't been verified as free. |
| **"No, but" vs. "No, stop"** | A bare "no" during confirmation is treated as ambiguous — the orchestrator asks the user to clarify rather than assuming exit. Only explicit exit signals end the booking flow. |
| **Topic change loops back to re-confirmation** | If the user changes the topic at the confirmation stage, the orchestrator loops back to Stage 3 (final confirmation) with the updated topic — it does NOT go back to slot checking (the slot is still available). |
| **Booking code before side effects** | The booking code is generated after confirmation but before any MCP operations, ensuring all four artifacts share the same code. |
| **Sequential side effects** | The four execute nodes run in sequence, not parallel. This simplifies failure handling — if a later operation fails, earlier ones remain and the user is informed with the booking code for manual recovery. |
| **Chat closes after booking** | After `close_chat_with_confirmation`, the session ends. The user cannot continue chatting. The only remaining interaction is the optional "Send me the booking details" button. |
| **No cancellation or rescheduling** | Cancellation and rescheduling intents are detected by `detect_intent` and routed directly to `generate_response` with a graceful decline message. No state changes, no side effects. |

---

## Worked Examples

### Example 1 — The Smooth Booking Case

> **User:** *"I want to talk to someone about my SIP."*
> **Orchestrator:** (Phase 3 collects topic = "SIP query", date = "May 15", time = "3:00 PM")

| Step | Action |
|---|---|
| **1. check_slot_availability** | Calendar read via MCP — no conflict at May 15, 3:00 PM. |
| **2. request_final_confirmation** | *"Got it. To confirm: a 30-minute call about 'SIP query' on May 15 at 3:00 PM. Should I book this?"* |
| **3. User says yes** | `detect_confirmation_response` returns `confirmed`. |
| **4. generate_booking_code** | Code = 4729 (no collision in meetings log). |
| **5. execute_calendar_create** | Event `[#4729] SIP query` created. |
| **6. execute_broker_email** | Email sent to broker with code #4729. |
| **7. execute_doc_create** | Doc `Meeting Notes - #4729 - SIP query - May 15` created and attached to event. |
| **8. execute_dashboard_log** | Row appended to meetings log. |
| **9. close_chat_with_confirmation** | *"Booked! Your booking code is **#4729**. The advisor will reach out for a 30-minute call about 'SIP query' on May 15 at 3:00 PM."* |

---

### Example 2 — The Slot Unavailable Case

> **User:** *"Book me for May 14 at 2:00 PM."*

| Step | Action |
|---|---|
| **1. check_slot_availability** | Calendar read — conflicting event found at May 14, 2:00 PM. |
| **2. suggest_alternative_slot** | Next free slot: May 14, 2:30 PM. |
| **3. generate_response** | *"The slot is not available at that time. The next available slot is May 14 at 2:30 PM. Would that work?"* |
| **4. User accepts** | Flow continues to `request_final_confirmation` with the 2:30 PM slot. |
| **5. User confirms** | Booking proceeds through Stages 4–6 as normal. |

---

### Example 3 — The "No, But" Confirmation Case

> **User confirms slot, then reconsiders:**

| Step | Action |
|---|---|
| **1. request_final_confirmation** | *"Got it. To confirm: a 30-minute call about 'Exit load query' on May 15 at 3:00 PM. Should I book this?"* |
| **2. User says:** *"No, I'm not free Tuesday — can we do Wednesday at 6 PM?"* |
| **3. detect_confirmation_response** | Returns `change_slot` with new date = May 16, time = 6:00 PM. |
| **4. check_slot_availability** | Checks May 16 at 6:00 PM — available. |
| **5. request_final_confirmation** | *"To confirm: a 30-minute call about 'Exit load query' on May 16 at 6:00 PM. Should I book this?"* |
| **6. User says yes** | Booking proceeds through Stages 4–6 as normal. |

---

### Example 4 — The Out-of-Scope (Investment-Adjacent) Case

> **User:** *"Is now a good time to invest in equity funds?"*

| Step | Action |
|---|---|
| **1. detect_intent** | Intent = `other` (not theme, not FAQ, not booking). |
| **2. classify_out_of_scope** | Category = `investment_adjacent`. |
| **3. generate_response** | *"That's a great question, but it's not something I can answer well — it depends on your specific situation. Would you like to schedule a call with an advisor to discuss it?"* |
| **4. User agrees** | `detect_escalation` triggers, enters booking flow with topic auto-generated = "Equity fund investment". |

---

### Example 5 — The Out-of-Scope (Unrelated) Case

> **User:** *"What's the latest IPL score?"*

| Step | Action |
|---|---|
| **1. detect_intent** | Intent = `other`. |
| **2. classify_out_of_scope** | Category = `unrelated`. |
| **3. generate_response** | *"I can't help with that. I'm here to answer questions about your investments, help with mutual fund queries, or schedule a call with an advisor."* |

---

### Example 6 — The Cancellation/Reschedule Intent Case

> **User:** *"I want to cancel my appointment #4729."*

| Step | Action |
|---|---|
| **1. detect_intent** | Intent = `cancel_or_reschedule`. |
| **2. generate_response** | *"We don't support cancelling existing bookings — you can simply not attend if you can't make it. If you'd like to book a different time instead, I can set up a new appointment for you."* |

---

## End-to-end System Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  PHASE 3 CARRY-OVER:                                                         │
│  detect_escalation ──▶ detect_intent ──▶ collect_booking_topic              │
│       ──▶ collect_booking_datetime (all fields present)                      │
│                                                                              │
│  PHASE 4 EXTENSION:                                                          │
│                                                                              │
│  check_slot_availability                                                     │
│  ├── available ──▶ request_final_confirmation                                │
│  └── unavailable ──▶ suggest_alternative_slot ──▶ generate_response         │
│                         (user accepts) ──▶ check_slot_availability (loop)   │
│                                                                              │
│  request_final_confirmation                                                  │
│       ↓ (user responds)                                                      │
│  detect_confirmation_response                                                │
│  ├── confirmed ──▶ generate_booking_code                                    │
│  ├── change_slot ──▶ check_slot_availability (with new slot)                │
│  ├── change_topic ──▶ collect_booking_topic (then re-confirm)               │
│  ├── exit ──▶ generate_response (graceful exit)                             │
│  └── ambiguous ──▶ generate_response (clarify: new time or skip?)           │
│                                                                              │
│  generate_booking_code                                                       │
│       ↓                                                                      │
│  execute_calendar_create ──▶ execute_broker_email ──▶ execute_doc_create    │
│       ──▶ execute_dashboard_log ──▶ close_chat_with_confirmation ──▶ END    │
│                                                                              │
│  (Optional, user-initiated)                                                  │
│  user clicks "Send me the booking details" ──▶ send_user_details_email     │
│                                                                              │
│  OUT-OF-SCOPE HANDLING:                                                      │
│  detect_intent (intent = other) ──▶ classify_out_of_scope                   │
│  ├── investment_adjacent ──▶ collect_booking_topic                          │
│  └── unrelated ──▶ generate_response (politely decline)                     │
│                                                                              │
│  CANCEL/RESCHEDULE DETECTION:                                                │
│  detect_intent (intent = cancel_or_reschedule) ──▶ generate_response       │
│       (explains no support, offers new booking)                              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Internal Dashboard: Scheduled Appointments Menu

The dashboard surface for booked meetings has two views.

### List View (Default)

A tabular list of all booked meetings, sorted by date (upcoming first, past below). Each row shows:

- Booking code
- Topic
- Date and time
- Link to the Google Doc (clickable, opens the meeting notes)
- Link to the calendar event (optional, clickable)

A **search bar** at the top of the list view supports searching by:

- **Booking code** — exact or partial match on the 4-digit code.
- **Topic** — keyword search over the topic field.

Search filters down the list in place. Search is the only filter mechanism for this phase — no separate date-range filters are needed since search by code or topic covers the typical lookup use cases.

### Calendar View

A calendar layout showing all bookings as events on their respective dates and times. Each calendar entry shows:

- Booking code
- Topic
- Time slot

Clicking on a calendar entry opens a detail panel with the same information as a list-view row, including the Google Doc link.

The dashboard reads from the meetings log written to in Stage 5. The log is the source of truth — the dashboard does not separately query the calendar via MCP. This keeps the dashboard fast and avoids depending on real-time MCP availability for read operations.

---

## Failure Handling

| Scenario | Behaviour |
|---|---|
| **Calendar read failure during slot check** | The orchestrator informs the user that calendar lookup failed and asks them to try again later. No artifacts are created. |
| **Slot becomes unavailable between check and execute** | Between the user's confirmation and the actual calendar event creation, the slot might get taken by another booking. The `execute_calendar_create` node should detect this conflict, abort the booking before any other artifacts are created, and inform the user. |
| **One MCP operation fails during Stage 5** | Retry once. If retry fails, surface the failure to the user with the booking code so manual recovery is possible. Other artifacts that succeeded should remain (don't try to roll them back automatically — manual cleanup is safer than half-rollback). |
| **Booking code collision** | Extremely unlikely with 4 digits if the system has fewer than several thousand bookings. The generation function checks for collisions and retries with a fresh code if one is found. After 5 retries, log an error. |
| **MCP tools unavailable** | The orchestrator informs the user that booking is temporarily unavailable and apologizes. State is preserved so the user can retry. |
| **LLM error at any node** | Return a graceful failure message to the user ("Something went wrong, please try again") and preserve conversation state so the next turn can recover. |
| **Ambiguous confirmation response** | The orchestrator asks the user to clarify whether they want to try a different time or skip the booking, rather than guessing. |
| **Booking collection stall** | If the user cannot or will not provide a date or time after several turns, gracefully exit the booking flow rather than looping indefinitely. |
| **User initiates "Send details" but email fails** | Surface the failure in the popup, offer a retry, but do not block the closed chat session. The booking itself is unaffected. |

---

## Configuration

All values below are configurable (config file or environment variables), not hardcoded:

| Parameter | Description |
|---|---|
| Organization broker email | The recipient of every booking email. |
| Calendar identifier | Which calendar the events are written to via MCP. |
| Google Doc template | Template for meeting notes document creation. |
| Default meeting duration | 30 minutes (configurable but fixed at 30 in this phase). |
| Booking code format | 4-digit numeric code (range adjustable). |
| Booking code collision retry limit | Maximum retries on code collision (default: 5). |
| Booking field collection turn limit | Max turns the orchestrator waits for a missing booking field before exiting the booking flow. |
| LLM model | LLM used for the orchestrator's reasoning nodes (Groq). |
| Escalation trigger phrases | Phrases or model thresholds that cause `detect_escalation` to fire. |
| Themes knowledge base location | Path or endpoint for the Themes KB used by `check_theme`. |
| FAQ agent invocation interface | How `call_faq_agent` reaches the FAQ agent. |
| MCP tool endpoints | URLs/identifiers for calendar, email, and Doc MCP operations. |

---

## Downstream Consumers

| Consumer | What it reads | Phase |
|---|---|---|
| **User Portal (Frontend)** | Receives every `response_to_user` reply and renders it in the chat interface. Also renders the "Send me the booking details" button. | Phase 3/4 |
| **Booking Pipeline** | Receives the structured booking request emitted by `close_chat_with_confirmation`. | Phase 4 |
| **Internal Dashboard** | Reads the meetings log (booking code, topic, date, time, Google Doc link, status). Provides the Scheduled Appointments list and calendar views. | Phase 4/8 |
| **Organization Broker** | Receives the broker email with booking code, topic, and meeting context. | Phase 4 |
| **FAQ Agent** | Receives rewritten, self-contained queries from `call_faq_agent` and returns structured responses. | Phase 2 |
| **Themes Knowledge Base** | Queried by `check_theme` for each complaint-type intent. | Phase 1 |

---

## Dependencies on the Broader Product

This subsystem depends on:

- The **Orchestrator Agent** (Phase 3) — this is an extension of the orchestrator's graph, not a standalone service.
- The **Themes knowledge base** (Phase 1) — read by `check_theme`.
- The **FAQ agent** (Phase 2) — called by `call_faq_agent`.
- **MCP tools** — calendar (read and create), email (send), Google Docs (create and attach) — these are external integrations, not part of this project.

It writes to:

- The **meetings log** — the source of truth for the internal dashboard's Scheduled Appointments menu.
- The **organization's calendar** — via MCP.
- The **broker's email** — via MCP.
- The **Google Doc for meeting notes** — via MCP.

It is the only component in the system that talks directly to the user — all other agents and tools communicate through the orchestrator.

> The orchestrator is the **user-facing layer**. Downstream agents (FAQ agent) and tools (MCP calendar, email, Docs) are internal specialists that receive clean inputs and return structured outputs. They do not interact with the user directly.

---

## Out of Scope for This Phase

These items are deferred to subsequent phases:

| Item | Deferred to |
|---|---|
| **Voice mode** (Sarvam STT/TTS) for the booking flow | Phase 5 — text-only in this phase. |
| **Multi-language support** for booking conversations | Future phase. |
| **Working hours, lunch breaks, and holidays** | Future phase — the slot check only verifies "no conflicting calendar event" in this phase. |
| **Employee handbook upload and parsing** | Future phase. |
| **Cancellation and rescheduling flows** | Explicitly not supported, ever (per design). |
| **Booking modifications after creation** | Once a booking is logged, only manual broker-side edits are possible. |
| **Parallel execution of side effects** | Currently sequential for simpler failure handling; can be restructured for performance later. |
