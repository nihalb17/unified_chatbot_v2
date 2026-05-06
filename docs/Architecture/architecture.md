# Investor Ops & Intelligence Suite — Phase-wise Architecture

> This document describes the system architecture of the Investor Ops & Intelligence Suite, broken down into eight implementation phases. Each phase builds on the previous one, progressively assembling the full multi-agent product. Two dedicated frontend modules — **User Chat** and **Internal Dashboard** — are scaffolded as their own phases and then incrementally updated alongside each backend phase to enable manual testing at every stage.

---

## High-level Architecture Diagram

![Multi-agent architecture](./multi_agent_architecture_lanes_v4.svg)

---

## Phase Overview

| Phase | Title | Type |
|---|---|---|
| **Phase 1** | Review Intelligence Pipeline | Backend |
| **Phase 2** | Factsheet RAG System | Backend |
| **Phase 3** | Orchestrator Agent — Intent Detection | Backend |
| **Phase 4** | Booking Pipeline | Backend |
| **Phase 5** | Voice Integration | Backend |
| **Phase 6** | GitHub Actions Scheduler | DevOps |
| **Phase 7** | User Chat Frontend | Frontend |
| **Phase 8** | Internal Dashboard Frontend | Frontend |

> **Frontend development model**: Phases 7 and 8 establish the base scaffolding for the two frontend modules. With each backend phase (1–6), the relevant frontend modifications in both modules are made simultaneously so that every backend capability can be tested manually end-to-end as it lands.

---

## Phase 1 — Review Intelligence Pipeline (Theme Analysis)

### Objective

Build the offline data pipeline that collects Groww app reviews, generates themes, tags sentiment, and classifies every review into a theme — producing a structured Themes knowledge base.

### Components

| Component | LLM | Description |
|---|---|---|
| **Review Scraper** | — | Fetches user reviews from the Google Play Store and Apple App Store for the Groww app. |
| **Theme Generation** | **Groq** | Analyses the scraped reviews and generates a set of actionable themes (e.g., "Login Issues", "Nominee Updates", "Exit Load Confusion"). |
| **Sentiment Tagging** | **Groq** | Tags each review with a sentiment label (positive, negative, neutral). |
| **Review Classification** | **Gemini** | Segregates each review into one of the generated themes by classifying them against the theme definitions produced by Groq. |
| **Themes Knowledge Base** | — | Structured output — theme name, review count, representative quotes (2–3 per theme), and one actionable item per theme. |

### Data Flow

```
Play Store / App Store
        │
        ▼
  Review Scraper
        │
        ▼
  Theme Generation (Groq) ──▶ List of themes
        │
        ▼
  Sentiment Tagging (Groq) ──▶ Each review gets a sentiment label
        │
        ▼
  Review Classification (Gemini) ──▶ Each review mapped to a theme
        │
        ▼
  Themes Knowledge Base (JSON / structured store)
```

### Key Design Decisions

- **Groq** handles theme generation and sentiment tagging — tasks that benefit from fast inference.
- **Gemini** handles review-to-theme classification — a task requiring deeper reasoning to accurately segregate reviews.
- The pipeline is **batch / on-demand** — triggered manually by the ops team from the Internal Dashboard, or automatically via the GitHub Actions Scheduler (Phase 6).
- Output feeds two downstream consumers: the **Orchestrator Agent** (Phase 3) and the **Internal Dashboard** (Phase 8).

### Concurrent Frontend Work

- **Internal Dashboard (Phase 8)**: Themes section wired up — displays generated themes, representative reviews, sentiment breakdown, and actionable items.

---

## Phase 2 — Factsheet RAG System (FAQ Agent)

### Objective

Build a retrieval-augmented generation (RAG) system that answers investor questions about mutual fund schemes by grounding responses in scraped Groww factsheet data.

### Components

| Component | LLM | Description |
|---|---|---|
| **Factsheet Scraper** | — | Scrapes Groww factsheet URLs (one per mutual fund scheme) configured by the ops team. |
| **Embedding Store** | — | Builds vector embeddings from scraped factsheet content for similarity-based retrieval. |
| **MF Definitions KB** | — | A curated set of definitions for common mutual fund terms — exit load, expense ratio, NAV, SIP, etc. |
| **FAQ Agent** | **Gemini** | Receives a user question, retrieves relevant factsheet chunks via RAG, and returns a **sourced answer** citing the factsheet section. |

### Data Flow

```
Groww Factsheet URLs (configured via dashboard)
        │
        ▼
  Factsheet Scraper
        │
        ▼
  Embedding Store ──┐
                    ├──▶ FAQ Agent (Gemini) ──▶ Sourced Answer
  MF Definitions ───┘
```

### Knowledge Bases

1. **Groww Factsheet Data** — scraped content, re-built on demand when the ops team triggers a refresh.
2. **Exit Load / Expense Ratio Definitions** — static reference data so the agent can explain meaning, not just retrieve numbers.

### Key Design Decisions

- Every answer must **cite its source** (factsheet section).
- The factsheet URL list is managed via the Internal Dashboard (Phase 8), so adding or removing a fund is an ops-level action.
- The embedding store is rebuilt when the ops team triggers a knowledge base refresh.

### Concurrent Frontend Work

- **User Chat (Phase 7)**: Chat interface can now send FAQ questions and display sourced answers inline.
- **Internal Dashboard (Phase 8)**: Data source management section — ops team can add/remove factsheet URLs and trigger a RAG refresh.

---

## Phase 3 — Orchestrator Agent (Intent Detection)

### Objective

Build the central Orchestrator Agent that serves as the single entry point for all user queries. This phase **integrates with both Phase 1 and Phase 2** — the Orchestrator consults the Themes KB (Phase 1 output) for known-issue detection and routes FAQ queries to the FAQ Agent (Phase 2) for RAG-based answers. It detects intent and routes the query to the correct downstream lane.

### Components

| Component | LLM | Description |
|---|---|---|
| **Orchestrator Agent** | **Groq** | Detects user intent, maintains conversation context, and routes to the appropriate lane. |
| **Themes KB Lookup** | — | First-pass check against the Themes KB (Phase 1 output) before any downstream routing. |
| **FAQ Agent Integration** | — | Routes factsheet/fund questions to the FAQ Agent built in Phase 2 and relays sourced answers back to the user. |

### Integration Points

| Upstream Phase | What is Integrated | How |
|---|---|---|
| **Phase 1 — Review Intelligence** | Themes Knowledge Base | Orchestrator reads the Themes KB at query time. If the user's query matches a known theme, the Orchestrator replies directly (Lane 1) without calling any downstream agent. |
| **Phase 2 — Factsheet RAG** | FAQ Agent | When the Orchestrator detects a factsheet/fund question (Lane 2), it forwards the query to the FAQ Agent, receives a sourced answer, and relays it to the user. |

### Three-lane Routing

```
                        ┌──────────────────────────────────────────────┐
                        │            Orchestrator Agent (Groq)         │
                        │    Detects intent · Consults Themes KB       │
                        └──────┬──────────────┬──────────────┬─────────┘
                               │              │              │
                    ┌──────────▼──┐   ┌───────▼──────┐  ┌───▼──────────────┐
                    │  Lane 1     │   │  Lane 2      │  │  Lane 3          │
                    │ Known Theme │   │ FAQ Intent   │  │ Booking Intent   │
                    │ Direct reply│   │ → FAQ Agent  │  │ → Booking Agent  │
                    └─────────────┘   └──────────────┘  └──────────────────┘
```

#### Lane 1 — Known Theme (early exit)
- Orchestrator matches the query against the Themes KB.
- If match found → replies directly with a "known issue, fix is on the way" message.
- **No downstream agent is called.**

#### Lane 2 — FAQ Intent
- Query is a factsheet / fund question.
- Orchestrator routes to the **FAQ Agent** (Phase 2).
- FAQ Agent retrieves relevant chunks, generates a sourced answer, and returns it to the Orchestrator.

#### Lane 3 — Booking Intent
- User wants to talk to a human or schedule a call.
- Orchestrator collects **date**, **time**, and **topic** (1–3 words), then routes to the **Booking Agent** (Phase 4).

### Escalation Rule

At **any point** during Lane 1 or Lane 2, if the user expresses dissatisfaction or asks for a human:

1. Orchestrator detects the signal.
2. Orchestrator collects date and time from the user.
3. Orchestrator **auto-generates the topic** from the prior conversation context (1–3 words).
4. Orchestrator redirects to Lane 3 (Booking Agent — Phase 4).

> **Example**: User asks about exit load (Lane 2) → FAQ Agent answers → User says "this isn't helpful, can I talk to someone?" → Orchestrator auto-generates topic `"Exit load query"` → asks for date/time → routes to Booking Agent.

### Key Design Decisions

- Phase 3 is the **integration layer** — it wires together the outputs of Phase 1 (Themes KB) and Phase 2 (FAQ Agent) into a single orchestrated flow.
- The Orchestrator is the **only** agent that communicates with the user — all other agents are internal.
- Conversation context is maintained by the Orchestrator so it can summarize prior discussion during an escalation.
- Lane 3 routing is handled here, but the **execution** of the booking flow is in Phase 4.
- Both Phase 1 and Phase 2 must be complete before Phase 3 can function end-to-end.

### Concurrent Frontend Work

- **User Chat (Phase 7)**: Full orchestration loop — user messages now go through the Orchestrator, which routes to Lane 1/2 and returns responses. Lane 3 shows a "booking coming soon" placeholder until Phase 4 is complete.

---

## Phase 4 — Booking Pipeline

### Objective

Build the Booking Agent and its two sub-agents (Slot Check, Implementation) that handle the complete appointment scheduling flow — from availability verification to booking execution via MCP.

### Agents

| Agent | LLM | Role |
|---|---|---|
| **Booking Agent** | **Gemini** | Coordinates the booking flow — receives date, time, topic from the Orchestrator and delegates to sub-agents. |
| **Slot Check Agent** | **Gemini** | Verifies whether the requested slot is available using the Holidays KB and Google Calendar (via MCP). |
| **Implementation Agent** | **Groq** | Executes the four booking actions — all via MCP. |

### Booking Flow

```
Orchestrator (Lane 3)
        │
        │  date, time, topic
        ▼
  Booking Agent (Gemini)
        │
        ├── Step 1 ──▶ Slot Check Agent (Gemini)
        │                 ├── Holidays KB (CSV)
        │                 └── Google Calendar (MCP) ──▶ "free" / "unavailable"
        │
        └── Step 2 (if free) ──▶ Implementation Agent (Groq)
                                    ├── Email notification (MCP)
                                    ├── Calendar event (MCP)
                                    ├── Sheet log (MCP)
                                    └── Meeting notes doc (MCP)
        │
        ▼
  Confirmation → Orchestrator → User
```

### Implementation Agent — Four MCP Actions

| # | Action | External Service |
|---|---|---|
| 1 | **Email notification** | Sends email to the organization about the new meeting. |
| 2 | **Calendar event** | Creates the event on Google Calendar. |
| 3 | **Sheet log** | Appends a row to the master Google Sheet (meeting log). |
| 4 | **Meeting notes doc** | Generates a Google Doc for meeting notes and attaches it to the calendar event. |

### Knowledge Bases

| Knowledge Base | Used By | Source |
|---|---|---|
| Holidays CSV | Slot Check Agent | Managed via Internal Dashboard (Phase 8) |
| Google Calendar | Slot Check Agent | Live read via MCP |

### Key Design Decisions

- Booking **only proceeds** to the Implementation Agent if the Slot Check Agent reports the slot is free.
- All four Implementation Agent actions use **MCP** (Model Context Protocol) to interact with external Google services.
- The master Google Sheet serves as the single source of truth for the Meetings section in the Internal Dashboard.

### Concurrent Frontend Work

- **User Chat (Phase 7)**: Lane 3 is now fully functional — booking widget appears inline, user can pick slots and see confirmation.
- **Internal Dashboard (Phase 8)**: Meetings section wired up — displays master meeting log. Holidays CSV management added to data source section.

---

## Phase 5 — Voice Integration

### Objective

Add voice interaction capabilities to the User Chat app using **Sarvam** for both speech-to-text (STT) and text-to-speech (TTS), enabling fully spoken conversations with the assistant.

### Components

| Component | Technology | Description |
|---|---|---|
| **Speech-to-Text** | **Sarvam STT** | Converts the user's spoken input into text, which is then fed to the Orchestrator as a normal text query. |
| **Text-to-Speech** | **Sarvam TTS** | Converts the Orchestrator's text reply into audio, which is played back to the user. |
| **Voice Mode Toggle** | — | UI control in the chat window to enable/disable voice mode. |

### Voice Mode Behaviour

- When enabled, the user can **speak instead of typing** — Sarvam STT transcribes and submits the text.
- The assistant's reply is **spoken back** — Sarvam TTS renders the response as audio.
- The full conversation **transcript remains visible** in the chat window.
- Voice mode works across **all three lanes** — known-theme replies, FAQ answers, and the booking flow.

### Key Design Decisions

- Voice is an **overlay** on the existing text-based flow — the Orchestrator receives text regardless of input mode.
- No agent or routing logic changes — voice is purely a frontend/integration concern.
- The transcript always stays visible so the user has a written record of the conversation.

### Concurrent Frontend Work

- **User Chat (Phase 7)**: Voice mode toggle added. Mic input, audio playback, and visual indicators for recording/speaking states.

---

## Phase 6 — GitHub Actions Scheduler

### Objective

Automate the periodic execution of the Review Intelligence Pipeline (Phase 1) and Factsheet RAG refresh (Phase 2) using GitHub Actions, removing the need for manual triggers for routine refreshes.

### Components

| Component | Description |
|---|---|
| **Scheduled Workflow** | A GitHub Actions workflow that runs on a configurable cron schedule (e.g., weekly). |
| **Review Intelligence Job** | Re-fetches reviews from both app stores → runs theme generation (Groq) → sentiment tagging (Groq) → review classification (Gemini) → updates the Themes KB. |
| **Factsheet RAG Job** | Re-scrapes all configured factsheet URLs → re-builds embeddings → updates the FAQ Agent's knowledge base. |

### Key Design Decisions

- The scheduler runs both jobs by default but supports running them **independently**.
- Manual trigger (`workflow_dispatch`) is also supported for ad-hoc runs outside the regular cadence.
- The same pipeline code from Phases 1 and 2 is reused — the scheduler simply invokes it on a timer.
- The Internal Dashboard's manual refresh button (Phase 8) continues to work alongside the automated schedule.

### Concurrent Frontend Work

- **Internal Dashboard (Phase 8)**: Status indicators showing the last automated refresh timestamp and next scheduled run.

---

## Phase 7 — User Chat Frontend

### Objective

Build the investor-facing assistant — a single chat-style interface that connects to the multi-agent backend. This phase establishes the base scaffolding; subsequent backend phases incrementally add functionality.

### Core Scaffold

| Component | Description |
|---|---|
| **Chat Window** | Single-screen, continuous conversation UI. All interactions happen inline — no page navigation. |
| **Message Thread** | Renders user messages and assistant replies in a threaded view. |
| **Input Bar** | Text input with send button. Voice toggle added in Phase 5. |
| **Booking Widget** | Inline slot picker that appears during the booking flow (functional after Phase 4). |

### Incremental Updates by Backend Phase

| Backend Phase | Frontend Update |
|---|---|
| Phase 2 (Factsheet RAG) | Chat can send FAQ questions and display sourced answers inline. |
| Phase 3 (Orchestrator) | Full orchestration loop — messages routed through the Orchestrator, Lane 1/2 responses rendered. |
| Phase 4 (Booking Pipeline) | Lane 3 fully functional — booking widget, slot selection, and confirmation inline. |
| Phase 5 (Voice Integration) | Voice mode toggle, mic input, audio playback, recording/speaking visual indicators. |

### Information Hidden from the User

The user never sees:
- Theme analytics, theme names, or theme counts.
- Agent names or internal routing decisions.
- MCP tool calls, calendar internals, or sheet logs.
- Any internal product machinery.

> The user interacts with a **single friendly assistant** — the multi-agent backend is completely invisible.

---

## Phase 8 — Internal Dashboard Frontend

### Objective

Build the internal-facing dashboard for Groww's product and operations team. Provides visibility into review themes, booked meetings, and control over the system's data sources. This phase establishes the base scaffolding; subsequent backend phases incrementally add functionality.

### Core Scaffold

#### 1. Themes Section

| Element | Description |
|---|---|
| **Theme List** | Top themes from the review intelligence pipeline (Phase 1). |
| **Representative Reviews** | 2–3 verbatim quotes per theme from Play Store / App Store reviews. |
| **Sentiment Breakdown** | Sentiment distribution per theme. |
| **Actionable Item** | One recommended next step per theme (e.g., "Add nominee-update FAQ to help center"). |

#### 2. Meetings Section

| Element | Description |
|---|---|
| **Master Meeting Log** | Every meeting booked through the system — sourced from the master Google Sheet written by the Implementation Agent. |
| **Row Data** | Caller name, date & time, topic, assigned advisor, status (pending / completed / cancelled). |
| **Live Sync** | Dashboard reads from the same Google Sheet the Implementation Agent writes to — stays in sync automatically. |

#### 3. Data Source Management

| Data Source | Description | Impact on Agents |
|---|---|---|
| **Mutual Fund Factsheet Links** | Managed list of Groww URLs for factsheet scraping. | Adding/removing a URL adds/removes that fund from the FAQ Agent's coverage. |
| **Holidays CSV** | Organization holidays uploaded/edited by the ops team. | Slot Check Agent reads this when verifying availability. |

#### 4. Knowledge Base Refresh

A manual trigger for the ops team to bring the system up to date:

| Refresh Target | What Happens |
|---|---|
| **Review Intelligence** | Re-fetches reviews → re-runs theme generation (Groq), sentiment tagging (Groq), and review classification (Gemini) → updates the Themes KB. |
| **Factsheet RAG** | Re-scrapes all configured factsheet URLs → re-builds embeddings → updates the FAQ Agent's knowledge base. |

- Can be triggered for **both sources together** or **independently**.
- Works alongside the automated GitHub Actions Scheduler (Phase 6).

### Incremental Updates by Backend Phase

| Backend Phase | Frontend Update |
|---|---|
| Phase 1 (Review Intelligence) | Themes section wired up — themes, reviews, sentiment, actionable items displayed. |
| Phase 2 (Factsheet RAG) | Data source management — factsheet URL list and RAG refresh trigger. |
| Phase 4 (Booking Pipeline) | Meetings section wired up — master log displayed. Holidays CSV management added. |
| Phase 6 (GitHub Actions) | Scheduler status indicators — last refresh timestamp, next scheduled run. |

---

## End-to-end Data Flow (All Phases)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: Review Intelligence                                                  │
│  Play Store + App Store → Scraper → Theme Gen (Groq) → Sentiment (Groq)        │
│  → Review Classification (Gemini) → Themes KB                                  │
└─────────────────────────────────────────┬──────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────┐
│  PHASE 2: Factsheet RAG                                                        │
│  Factsheet URLs → Scraper → Embeddings → FAQ Agent (Gemini)                    │
└─────────────────────────────────────────┬──────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────┐
│  PHASE 3: Orchestrator Agent (Intent Detection)                                │
│                                                                                │
│  Orchestrator (Groq)                                                           │
│   ├── Lane 1: Themes KB match → Direct reply                                  │
│   ├── Lane 2: FAQ intent → FAQ Agent (Gemini) → Sourced answer                │
│   └── Lane 3: Booking intent → routes to Phase 4                              │
└─────────────────────────────────────────┬──────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────┐
│  PHASE 4: Booking Pipeline                                                     │
│  Booking Agent (Gemini)                                                        │
│   ├── Slot Check Agent (Gemini) → Holidays KB + Calendar (MCP)                │
│   └── Implementation Agent (Groq) → Email, Calendar, Sheet, Doc (MCP)         │
└─────────────────────────────────────────┬──────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼──────────────────────────────────────┐
│  PHASE 5: Voice Integration                                                    │
│  Sarvam STT (speech → text) · Sarvam TTS (text → speech)                      │
└────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: GitHub Actions Scheduler                                             │
│  Cron-based automation for Phase 1 + Phase 2 refreshes                         │
└────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: User Chat Frontend                                                   │
│  Chat UI ←→ Orchestrator · Booking widget · Voice toggle                       │
└────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 8: Internal Dashboard Frontend                                          │
│  Themes Section · Meetings Log · Data Source Mgmt · KB Refresh · Scheduler     │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology & LLM Summary

| Component | Technology |
|---|---|
| Theme Generation | **Groq** |
| Sentiment Tagging | **Groq** |
| Review Classification | **Gemini** |
| FAQ Agent | **Gemini** |
| Orchestrator Agent | **Groq** |
| Booking Agent | **Gemini** |
| Slot Check Agent | **Gemini** |
| Implementation Agent | **Groq** |
| Voice STT | **Sarvam** |
| Voice TTS | **Sarvam** |
| Automated Scheduling | **GitHub Actions** |
| External Service Access | **MCP** (Model Context Protocol) — Calendar, Email, Sheets, Docs |
| Knowledge Bases | Themes KB, Factsheet embeddings, MF Definitions, Holidays CSV |
