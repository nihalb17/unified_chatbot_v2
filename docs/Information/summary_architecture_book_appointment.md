# Sub-Architecture: Book Appointment

## Purpose

This subsystem completes the booking flow that the orchestrator phase started. In the previous phase, the orchestrator only collected booking inputs (topic, date, time) and stopped there. In this phase, the orchestrator extends to actually checking calendar availability, suggesting alternatives if needed, getting final user confirmation, and executing the booking with all its side effects.

There is **no separate booking agent**. All booking-related work is handled by the orchestrator itself, calling deterministic tools where appropriate.

The execution of every booking results in four artifacts: a calendar event, an email to the organization broker, a Google Doc for meeting notes, and a log entry in the internal dashboard. All four share a common 4-digit booking code that links them together.

---

## Inputs and outputs

### Inputs (from the orchestrator's prior collection step)
- **Topic** — 1-3 word summary of what the meeting is about.
- **Date** — desired meeting date.
- **Time** — desired meeting time.
- Conversation context.

### Outputs (one of)
- **Booking confirmed** — a 4-digit booking code surfaced to the user, plus a confirmation message that includes the code, the topic, date, and time.
- **Booking declined by user** — the user said no during final confirmation, so nothing is booked.
- **Slot unavailable, alternative offered** — the requested slot was taken or out of working hours; orchestrator suggests the next available slot and waits for the user's response.

---

## End-to-end flow

The flow has six stages, all happening within the orchestrator's graph (no separate booking agent involved).

### Stage 1 — Slot availability check

Once topic, date, and time are collected, the orchestrator runs a **calendar slot check**. This is a deterministic operation that:

- Reads the calendar via MCP to see if there is a **conflicting event** at the requested slot.
- Returns one of:
  - **Available** — no conflicting event in the calendar at that slot.
  - **Unavailable** — there is a conflicting event. The next available 30-minute slot is computed and returned as a suggestion.

Slots are **always 30 minutes**. There is no flexibility on duration in this phase.

In this phase there are **no working-hours, lunch-break, or holiday checks**. The only constraint is "is the calendar free at that time." Working hours, lunch, and holidays may be added in a future phase if needed; the design should leave room for them but not implement them now. There is also no employee handbook option in this phase.

The next-available-slot logic is rule-based: scan forward from the requested time in 30-minute increments, return the first slot the calendar shows as free. This is plain code, not an LLM call.

### Stage 2 — Handle unavailable slots

If the slot is unavailable:

- The orchestrator tells the user the requested slot has a conflicting event already in the calendar.
- The orchestrator suggests the next available 30-minute alternative.
- If the user accepts the alternative, the flow continues with the alternative slot.
- If the user proposes a different time, the flow loops back to Stage 1 with the new time.
- The user can also say "never mind" or "let me think about it" — the orchestrator gracefully exits the booking flow without creating any artifacts.

### Stage 3 — Final confirmation

If the slot is available, the orchestrator asks the user for **final confirmation** before proceeding. The confirmation message includes the topic, date, and time as captured.

Example:
> *"Got it. To confirm: a 30-minute call about 'Exit load query' on May 15 at 3:00 PM. Should I book this?"*

The user response is interpreted into one of these cases:

- **Yes / confirmed** → proceed to Stage 4 (booking code generation).
- **No, but here's a different time** → the user is rejecting *this* slot but still wants to book. Example: *"No, I'm not free Tuesday — can we do Wednesday at 6 PM?"* The orchestrator captures the new date/time and loops back to Stage 1 to check the new slot. This includes asking for re-confirmation once the new slot is confirmed available.
- **No, never mind / cancel the booking** → the user is exiting the flow entirely. The orchestrator gracefully ends the booking without creating any artifacts.
- **Wants to change the topic** → the orchestrator updates the topic and loops back to Stage 3 for confirmation of the updated booking.

The key distinction the orchestrator must make is **"no, but"** vs. **"no, stop"**. A bare "no" without further detail should prompt the orchestrator to ask: *"No problem — would you like to try a different time, or skip the booking?"* rather than assuming exit. The flow is forgiving — the user can change their mind multiple times before either confirming or explicitly exiting.

### Stage 4 — Generate booking code

Once the user confirms, the orchestrator generates a **4-digit booking code**. The code is unique within the system and serves as the linking identifier across all four artifacts created in the next stage.

The code generation logic should:
- Produce a 4-digit numeric code.
- Avoid collisions with existing bookings (check against the meetings log).
- Be human-readable (no leading zeros if avoidable, or accept leading zeros if uniqueness requires it).

### Stage 5 — Execute booking (four parallel side effects via MCP)

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

If any of the four operations fails, the orchestrator should attempt graceful recovery (retry once, then surface the failure to the user with the booking code so the operation can be completed manually). Partial-success states are surfaced clearly — e.g., "calendar event created but email failed" should be visible in logs, not silently swallowed.

### Stage 6 — Confirm to user and close the chat

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

### The "Send me the booking details" optional flow

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

## The 4-digit booking code

The booking code is the **single linking identifier** across all four artifacts. It appears in:

- The user's confirmation message.
- The calendar event title.
- The email to the organization broker (subject and body).
- The Google Doc title.
- The internal dashboard's meetings log entry.

This means anyone in the system — user, broker, ops team — can reference one code and find the corresponding meeting consistently across all surfaces.

The code is generated at booking time, after the user has confirmed but before any side effects are executed, so the same code is available to all four MCP operations.

---

## No cancellation, no rescheduling

The orchestrator **does not support** cancellation or rescheduling of existing bookings. This is an intentional simplification.

- If a user wants to cancel: the orchestrator informs them they can simply not show up — no-shows are acceptable. No system-level cancellation flow exists.
- If a user wants to reschedule: the orchestrator instructs them to book a new appointment. The old booking remains as-is in the system. The user notes the new booking code, and the broker handles any cleanup of the old slot manually if needed.

The orchestrator should detect cancellation/reschedule intent and respond gracefully:

> *"We don't support cancelling existing bookings — you can simply not attend if you can't make it. If you'd like to book a different time instead, I can set up a new appointment for you."*

This keeps the booking flow strictly forward-only and avoids the complexity of state transitions on existing bookings.

---

## Out-of-scope handling (the "else" branch)

The orchestrator routes user inputs into one of three primary pillars: theme check, FAQ pipeline, or booking. Anything else falls into a catch-all that this phase needs to handle correctly.

There are **two distinct out-of-scope categories**, and they require different responses.

### Category A — Investment-related but not in any pillar

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

### Category B — Out-of-scope (random or unrelated questions)

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

## Updates to the LangGraph implementation

This phase extends the orchestrator's graph from the previous phase. The shared state and most nodes carry over; new nodes and edges are added for the booking execution.

### State additions

The state object gains these fields:

```
{
  ...existing fields...
  
  // Booking execution state
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
  
  // Optional user-initiated send-details flow
  user_details_email_sent_to: string | null,  // populated only if user clicks "Send me details"
  
  // Out-of-scope handling
  out_of_scope_category: "investment_adjacent" | "unrelated" | null,
}
```

### New nodes

**`check_slot_availability`** (deterministic)
- Reads the calendar via MCP for the requested 30-minute window.
- Returns available if no conflicting event exists, unavailable otherwise.
- Updates `slot_check_result` in state.

**`suggest_alternative_slot`** (deterministic)
- Scans forward from the requested time in 30-minute increments via MCP calendar reads.
- Returns the first slot with no conflicting event.

**`request_final_confirmation`** (LLM call)
- Composes the confirmation prompt to surface to the user.
- Waits for user input on the next turn.

**`detect_confirmation_response`** (LLM call or rule-based)
- Interprets the user's response to the confirmation prompt.
- Returns one of: `confirmed`, `change_slot` (with the new slot extracted from the response), `change_topic`, `exit`, or `ambiguous`.
- The orchestrator routes accordingly. An ambiguous response prompts the orchestrator to ask whether the user wants to try a different time or skip the booking.

**`generate_booking_code`** (deterministic)
- Generates a unique 4-digit code, checking against existing logs to avoid collisions.
- Updates `booking_code` in state.

**`execute_calendar_create`** (MCP tool call)
- Creates the calendar event with the booking code in the title.
- Updates `booking_artifacts.calendar_event_id`.

**`execute_broker_email`** (MCP tool call)
- Sends the email to the broker with the booking code in the subject and body.
- Updates `booking_artifacts.broker_email_sent`.

**`execute_doc_create`** (MCP tool call)
- Creates the Google Doc with the booking code in the title.
- Attaches the Doc to the calendar event.
- Updates `booking_artifacts.google_doc_id` and `booking_artifacts.google_doc_url`.

**`execute_dashboard_log`** (deterministic write)
- Appends a row to the meetings log used by the internal dashboard.
- Updates `booking_artifacts.dashboard_log_id`.

**`close_chat_with_confirmation`** (deterministic)
- Composes the chat-closing message with the booking code, topic, date, and time.
- Surfaces the optional "Send me the booking details" action to the user.
- Marks the chat session as closed for further interaction.

**`send_user_details_email`** (MCP tool call, user-initiated)
- Triggered only when the user clicks "Send me the booking details" and submits an email address.
- Sends a separate email (distinct from the broker email) with the booking details framed for the user.
- Updates `user_details_email_sent_to` in state.

**`classify_out_of_scope`** (LLM call)
- When intent doesn't match theme, FAQ, or booking, this node classifies whether the question is investment-adjacent or genuinely unrelated.
- Sets `out_of_scope_category` in state.

### Updated routing

The graph extends with these flows:

```
After the existing "collect_booking_topic → collect_booking_datetime" chain,
when all booking fields are present:

  collect_booking_datetime
    ↓
  check_slot_availability
    ├─→ (available) → request_final_confirmation
    └─→ (unavailable) → suggest_alternative_slot → generate_response (offers alternative)
                            ↓ (user accepts alternative)
                          check_slot_availability (loop back with new slot)

  request_final_confirmation
    ↓ (user responds on next turn)
  detect_confirmation_response
    ├─→ (confirmed)        → generate_booking_code
    ├─→ (change_slot)      → check_slot_availability (with the new slot)
    ├─→ (change_topic)     → collect_booking_topic (then back through datetime/check/confirm)
    ├─→ (exit)             → generate_response (graceful exit, no artifacts)
    └─→ (ambiguous)        → generate_response (asks: try different time or skip booking?)

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
```

The four execute nodes run in sequence. They could run in parallel for speed, but sequential execution makes failure handling simpler in this phase. If parallel execution is needed later for performance, the graph can be restructured.

The "change_slot" path in `detect_confirmation_response` is important for UX — a "no" from the user does not necessarily mean the user wants to exit. The user might be saying "no to *this* slot but yes to a different one." The orchestrator must distinguish between these cases and only treat an explicit exit signal as the end of the flow.

### Reschedule and cancel detection

The intent detection node should explicitly recognize cancellation and rescheduling intents and route them to `generate_response` with a message explaining that the system doesn't support these flows. No state changes, no side effects.

---

## Internal dashboard: Scheduled Appointments menu

The dashboard surface for booked meetings has two views.

### List view (default)

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

### Calendar view

A calendar layout showing all bookings as events on their respective dates and times. Each calendar entry shows:

- Booking code
- Topic
- Time slot

Clicking on a calendar entry opens a detail panel with the same information as a list-view row, including the Google Doc link.

The dashboard reads from the meetings log written to in Stage 5. The log is the source of truth — the dashboard does not separately query the calendar via MCP. This keeps the dashboard fast and avoids depending on real-time MCP availability for read operations.

---

## Failure handling

- **Calendar read failure during slot check** — the orchestrator informs the user that calendar lookup failed and asks them to try again later. No artifacts are created.
- **Slot becomes unavailable between check and execute** — between the user's confirmation and the actual calendar event creation, the slot might get taken by another booking. The `execute_calendar_create` node should detect this conflict, abort the booking before any other artifacts are created, and inform the user.
- **One MCP operation fails during execution (Stage 5)** — retry once. If retry fails, surface the failure to the user with the booking code so manual recovery is possible. Other artifacts that succeeded should remain (don't try to roll them back automatically — manual cleanup is safer than half-rollback).
- **Booking code collision** — extremely unlikely with 4 digits if the system has fewer than several thousand bookings. The generation function checks for collisions and retries with a fresh code if one is found. After 5 retries, log an error.
- **MCP tools unavailable** — the orchestrator informs the user that booking is temporarily unavailable and apologizes. State is preserved so the user can retry.

---

## Out of scope for this phase

These items are deferred to subsequent phases:

- **Voice mode** (Sarvam STT/TTS) for the booking flow. Text-only in this phase.
- **Multi-language support** for booking conversations.
- **Working hours, lunch breaks, and holidays** — the slot check only verifies "no conflicting calendar event" in this phase. Time-of-day and day-of-week constraints can be added in a future phase if needed.
- **Employee handbook upload and parsing** — not part of this phase. The handbook upload flow described elsewhere in the project documentation is for future phases.
- **Cancellation and rescheduling flows** — explicitly not supported, ever (per design).
- **Booking modifications after creation** — once a booking is logged, only manual broker-side edits are possible.

---

## Configuration

Values that should live as configuration:

- Organization broker email address (the recipient of every booking email).
- Calendar identifier (which calendar the events are written to via MCP).
- Google Doc template for meeting notes.
- Default meeting duration (e.g., 30 minutes).
- Booking code format (4 digits, but the format/range can be adjusted).
