# Investor Ops & Intelligence Suite: Architecture (Plain Language)

This document explains **what the system is for**, **how the major pieces fit together**, and **what each phase means**, without file paths or code details. If you need ports, folders, and APIs, open [Implementation.md](Implementation.md).

---

## What is this product?

Two audiences use one connected platform:

1. **Investors** talk to a **single friendly assistant** in a chat app. They can type or use voice. They do not see internal tools, agent names, or spreadsheets.
2. **Groww’s internal team** uses a **dashboard** to see themes from app reviews, manage which fund pages power answers, configure when calls can be booked, and see scheduled appointments.

Behind the scenes, several specialized capabilities work together. The investor always interacts with **one** assistant that routes questions to the right capability.

---

## Big picture: how a question flows

1. The investor sends a message (text or transcribed speech).
2. A **central coordinator** reads the message and recent conversation. It decides what kind of help is needed.
3. Depending on the decision, it may:
   - answer from **known themes** (recurring issues from reviews),
   - send the question to a **fund factsheet helper** that looks up official data and cites sources,
   - start or continue **booking a call** with a human,
   - or politely handle topics that are out of scope.
4. The reply goes back to the investor in the same chat (and as voice if they use voice mode).

The internal dashboard does **not** replace this flow. It **feeds** the system (reviews pipeline, URL lists, office hours and holidays) and **reads** results (themes, appointments).

---

## Phase 1: Review intelligence

**Goal:** Turn raw app store reviews into **organized themes** the assistant can recognize.

**In simple terms:**

- Reviews are collected from the **Play Store** and **App Store**.
- An AI groups them into themes (for example login friction, nominee updates, confusion about charges).
- Each review gets a **theme** and a **sentiment** (positive, neutral, or negative).
- The team sees summaries in the dashboard: what people complain about, sample quotes, and suggested follow-ups.

**Why it matters:** When an investor describes a problem that matches a known theme, the assistant can respond with a clear, consistent message (for example that the issue is known and being addressed) without guessing.

---

## Phase 2: Factsheet knowledge (RAG)

**Goal:** Answer **factual** questions about mutual funds using **real fund pages** and **definitions** of terms, not generic chat guesses.

**In simple terms:**

- The team maintains lists of **factsheet links** (one fund per link) and **definition links** (plain-language explanations of terms like exit load or NAV).
- The system **refreshes** those pages on demand: it reads the pages, breaks them into searchable pieces, and stores them in a **search index** (like a smart library).
- When an investor asks a fund question, a **FAQ helper** searches that library, pulls the relevant bits, and writes an answer that **points to the source** (which page or section the information came from).

**Why it matters:** Answers stay grounded in Groww’s own published data. The assistant can say “here is what the factsheet states” instead of inventing numbers.

**Note:** Factsheets and definitions can be **refreshed on different schedules**. Definitions change rarely; NAVs and fund stats change often.

---

## Phase 3: Orchestrator (the coordinator)

**Goal:** One **front door** for every investor message.

**In simple terms:**

- The orchestrator **understands intent**: is this a complaint that matches a theme, a fund fact question, a request to speak to someone, frustration after an answer, or something unrelated?
- It **remembers context** across turns (which fund you were discussing, what you asked before) so follow-ups like “what about its expense ratio?” still make sense.
- It **hands off** fund questions to the factsheet helper and brings the answer back as part of a natural reply.
- If the user is **unhappy** or **asks for a human**, it can switch into **booking mode** and carry the topic from the conversation so the user does not have to repeat everything.

**Why it matters:** The investor experiences one assistant. Routing and memory stay invisible.

---

## Phase 4: Booking a call

**Goal:** Let the investor **schedule a short call** with the right context, and let the team **see it on the calendar** and in the dashboard.

**In simple terms:**

- The coordinator collects **topic**, **date**, and **time** (and can infer a short topic from context when the user escalates from another flow).
- It checks **rules the team configures**: working days, working hours, lunch break, holidays, and gaps between meetings.
- It checks the **real calendar** to see if the slot is free. If not, it can suggest alternatives.
- It asks for a **clear yes** before committing.
- After confirmation it:
  - creates a **calendar event**,
  - creates a **meeting notes document** and links it to the event where possible,
  - emails the **broker or distributor** with the details,
  - stores a row in an **appointments log** the dashboard reads,
  - gives the user a **booking code** and optional **email with details**.

**Why it matters:** Booking is reliable and traceable: everyone sees the same slot rules, and confirmations are not only a chat message.

---

## Phase 5: Voice

**Goal:** Same assistant, but **spoken** input and output.

**In simple terms:**

- Speech is turned into text, sent through the **same** coordinator and helpers, then the reply is turned back into speech.
- The **written transcript** still appears in the chat so nothing is lost.

**Why it matters:** Accessibility and convenience without maintaining two different product logics.

---

## Phase 6: Automation (scheduler)

**Original idea:** Run review processing and factsheet refreshes on a **schedule** (for example weekly) using GitHub Actions, in addition to manual refresh from the dashboard.

**Today:** GitHub Actions workflows (see `docs/Implementation.md` §9) call the same refresh endpoints as the dashboard on a **weekly** (review intelligence) and **daily** (factsheet-only) cadence, plus manual **workflow_dispatch**. Dashboard and API triggers remain unchanged.

---

## Phase 7: User chat (investor app)

**Goal:** The **only** surface investors need.

**In simple terms:**

- One conversation thread, booking steps **inline** when needed, optional **voice** mode.
- No exposure of internal analytics, theme names as engineering artifacts, or routing jargon.

---

## Phase 8: Internal dashboard

**Goal:** **Operate and observe** the system.

**In simple terms, the team can:**

- See **themes** from Phase 1 (quotes, sentiment, suggested actions).
- Manage **factsheet and definition URLs** and trigger **knowledge refreshes** from Phase 2.
- Configure **when calls can be booked** (hours, lunch, holidays, weekdays).
- See **scheduled appointments** and search by code or topic.

---

## End-to-end story (all phases together)

```text
App reviews  ──▶  Themes knowledge  ──┐
                                      ├──▶  Coordinator  ◀──  Investor chat & voice
Fund pages   ──▶  Searchable FAQ     ──┘         │
                                                  ▼
                                         Booking: rules + calendar
                                                  │
                                                  ▼
                                         Calendar, email, notes doc, appointment log
                                                  │
                                                  ▼
                                         Internal dashboard (read & control)
```

---

## Where to go next

- **Technical build and repo layout:** [Implementation.md](Implementation.md)
- **Older phase diagram and detailed phase notes:** [Architecture/architecture.md](Architecture/architecture.md) and the `phase*.md` files in the same folder
