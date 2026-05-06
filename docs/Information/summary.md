# Investor Ops & Intelligence Suite — Project Summary

## What this project is

A unified product built for **Groww** that helps the company serve mutual fund investors better while giving the internal product and operations team visibility into what users are struggling with.

The product has two surfaces:

1. **User-facing app** — an investor-facing assistant where users can ask questions about their mutual funds and book appointments with mutual fund distributors. Users can interact with this assistant via text chat or voice.

2. **Internal dashboard** — for Groww's product and operations team. Surfaces what investors are complaining about in app reviews, lists all meetings booked through the system, and lets the team manage the underlying data sources (factsheet links, organization holidays, etc.).

Both surfaces share the same multi-agent backend.

---

## Background context — three foundational capabilities

This product brings together three capabilities that form the foundation of the system. They are not separate apps in the final delivery — they are subsystems within this one unified product.

### 1. Factsheet question-answering (RAG)
A retrieval-augmented system that answers investor questions about specific mutual fund schemes. The knowledge base is built by scraping Groww factsheet URLs (one per scheme). Investors can ask things like *"What is the NAV of my Axis ELSS fund?"* or *"What's the expense ratio?"* and get sourced answers. The system also has supporting definitions for common mutual-fund concepts like exit load and expense ratio so it can explain meaning, not just retrieve numbers.

### 2. Review intelligence (theme analysis)
A pipeline that pulls Groww reviews from both the Google Play Store and the Apple App Store, clusters them into themes (e.g., "Login Issues", "Nominee Updates", "Exit Load Confusion"), classifies each review into a theme, and tags sentiment. The output is a snapshot showing what investors are complaining about, with counts and representative quotes per theme. This output feeds two things in the unified product:
- The **orchestrator agent** consults it to detect known issues at query time.
- The **internal dashboard** displays it so the ops team can act on patterns.

### 3. Voice/chat appointment scheduling
A conversational booking flow that lets investors schedule a call with a mutual fund distributor. It checks calendar availability, books the slot, and notifies the relevant parties. The voice experience is powered by **Sarvam** for both speech-to-text (STT) and text-to-speech (TTS), so the user can have a fully spoken conversation with the assistant if they prefer that over typing.

---

## Multi-agent backend

Five agents work together. The user always interacts with the orchestrator agent through the user-facing app — the other four agents are internal and never communicate with the user directly.

### Orchestrator agent (Groq)
The user's only entry point. Every query comes in through here, every reply goes out through here.

**Responsibilities:**
- Detect user intent and route the query to the right downstream agent.
- Maintain conversation context (so it can summarize what the user was asking about during an escalation — see below).
- Consult the **Themes knowledge base** before doing anything else: if the query matches an active known issue, reply directly with a "this is a known issue, fix is on the way" message and skip downstream agents entirely.

**Routes the query into one of three lanes:**
- **Lane 1 — Known theme**: Query matches an active theme. Orchestrator replies directly. Done.
- **Lane 2 — FAQ intent**: Factsheet/fund question. Routes to FAQ agent.
- **Lane 3 — Booking intent**: User wants to talk to a human or schedule a call. Routes to Booking agent.

**Knowledge base:** Themes KB, fed by the review intelligence pipeline.

### FAQ agent (Gemini)
Answers factsheet-related questions via RAG.

**Knowledge bases:**
- Groww factsheet data (scraped from URLs configured in the internal dashboard).
- Definitions of common mutual fund terms (exit load, expense ratio, NAV, SIP, etc.).

Returns sourced answers — every reply cites the factsheet section it came from.

### Booking agent (Gemini)
Coordinates the booking flow. Doesn't do the work itself — it delegates to two sub-agents.

**Flow:**
1. Receives the booking request with date, time, and topic.
2. Calls the Slot Check agent to verify availability.
3. If the slot is free, calls the Implementation agent to execute the booking.
4. Returns confirmation back up to the orchestrator, which replies to the user.

### Slot Check agent (Gemini)
Verifies whether a requested slot is available.

**Knowledge base:** Holidays list — a CSV of organization holidays, maintained via the internal dashboard.

**External access (via MCP):** Reads the live calendar to check for existing bookings.

Returns either "slot free" or "slot unavailable" (with a suggested alternative if possible).

### Implementation agent (Groq)
Executes the actual booking. All four of its actions happen via MCP:

1. **Email** — notifies the organization that a new meeting has been created.
2. **Calendar event** — writes the event to the calendar.
3. **Sheet log** — appends a row to the master meetings Google Sheet, which logs every booking made through the system.
4. **Meeting notes doc** — generates a Google Doc to be used as the meeting notes for that event, and attaches it to the calendar event.

---

## Critical orchestrator rule — escalation to booking

At any point in any flow (Lane 1 known theme reply, or Lane 2 FAQ answer), if the user signals dissatisfaction OR explicitly asks for a human, the orchestrator must redirect them to the booking flow (Lane 3).

Before handing off to the Booking agent, the orchestrator collects three pieces of information:

- **Date** of the appointment
- **Time** of the appointment
- **Topic** of the appointment (1–3 words)

### How the topic is obtained

- **If the user volunteers it** — use it as-is (condensed to 1–3 words if needed).
- **If the user doesn't mention it** — ask them directly.
- **If the redirect happens mid-conversation from Lane 1 or Lane 2** — the orchestrator must auto-generate a 1–3 word topic from the conversation context. It does NOT need to ask the user again. The orchestrator already knows what the user was asking about; it should summarize that into a short topic and pass it to the Booking agent.

### Example

> User in FAQ lane: *"What's the exit load on my ELSS fund?"*
> FAQ agent answers, but user replies: *"This isn't helpful, can I talk to someone?"*
> Orchestrator detects dissatisfaction → asks for date and time → auto-generates topic `"Exit load query"` from the prior conversation → routes the booking request with all three details to the Booking agent.

---

## User-facing app

A single chat-style assistant interface. One screen, one continuous conversation. Three things can happen inside it:

1. **User asks a question** → answered inline (factsheet answer or known-theme reply).
2. **User wants to book a call** → booking widget appears inline in the chat with available slots; user picks one and confirms.
3. **User is unsatisfied with an answer** → assistant offers "talk to an advisor" path; if accepted, transitions smoothly into the booking flow without making the user navigate anywhere.

### Voice mode
The chat window has a voice mode toggle. When enabled:
- The user can speak instead of typing — Sarvam STT converts speech to text and feeds it to the orchestrator.
- The assistant's reply is spoken back to the user — Sarvam TTS converts the text response into audio.
- The full conversation continues to be displayed as text in the chat window so the user has a transcript.
- Voice mode works for all three lanes — known-theme replies, FAQ answers, and the booking flow can all be conducted entirely by voice.

### What stays hidden from the user
- Theme analytics, theme names, theme counts.
- Agent names, internal routing decisions.
- MCP tool calls, calendar internals, sheet logs.
- Anything resembling internal product machinery.

The user just sees a friendly assistant.

---

## Internal dashboard

Built for Groww's product and operations team. Distinct from the user-facing app — different audience, different purpose, never shown to investors.

### Themes section
- Lists the top themes from the review analysis pipeline (e.g., "Nominee Updates", "Login Issues").
- For each theme, the dashboard shows:
  - **2–3 actual representative reviews** — verbatim quotes pulled from the Play Store and App Store.
  - **One actionable item** — a recommended next step for the team (e.g., "Investigate biometric login on latest Android build", "Add nominee-update FAQ to top of help center").

This is the operational intelligence layer. Visible only on the internal dashboard.

### Meetings section
A master log of every meeting booked through the system. Each row shows caller name, date and time, topic, assigned advisor, and status (pending, completed, cancelled). This is sourced from the master Google Sheet that the Implementation agent writes to — so the dashboard view stays in sync with the source of truth automatically.

### Data source management
Two configurable inputs that the ops team controls. Changes here flow through to the agents in production.

1. **Mutual fund factsheet links** — a managed list of Groww URLs that get scraped to build the FAQ agent's knowledge base. Adding a new fund means adding its factsheet URL here. Removing a fund removes it from the agent's coverage.
2. **Slot Check knowledge base** — an editable CSV of organization holidays. Ops uploads or updates this CSV as company holidays change throughout the year. The Slot Check agent reads from this file when verifying slot availability.

### Knowledge base refresh
The dashboard provides a manual refresh control that the ops team can trigger whenever they want to bring the system's knowledge up to date. When triggered, this action does two things:

1. **Refreshes the review intelligence** — re-fetches the latest Groww reviews from both the Google Play Store and the Apple App Store, re-runs the theme clustering and classification pipeline on the new data, and updates the Themes knowledge base used by the orchestrator agent. The Themes section of the dashboard then reflects the latest themes, counts, and representative reviews.
2. **Refreshes the factsheet RAG database** — re-scrapes every URL in the configured Mutual fund factsheet links list, re-builds the embeddings, and updates the FAQ agent's knowledge base so it answers based on the latest factsheet data.

The refresh can be run for both sources together or for either one independently. The ops team typically triggers this on a regular cadence (e.g., weekly) or after notable events (a new fund being added to coverage, or a spike in negative reviews after an app release).

These management features are internal-only.

---

## Summary of the user journey

1. Investor opens the Groww assistant (user-facing app).
2. Investor either types or speaks (voice mode) a question.
3. Orchestrator decides what to do:
   - If it's a known issue → orchestrator replies directly.
   - If it's a factsheet question → FAQ agent answers with a sourced reply.
   - If it's a booking request → orchestrator collects date, time, topic, and hands to the Booking agent, which checks the slot and executes the booking.
4. If the investor is unsatisfied at any point or asks for a human, the orchestrator gracefully transitions to the booking flow, auto-generating the topic from context.
5. Meanwhile, the ops team at Groww watches the internal dashboard to see what investors are complaining about, what meetings have been booked, and to keep factsheet links and holidays up to date.
