# Investor Ops & Intelligence Suite: Implementation Reference

This document is for **engineers and operators** who need ports, modules, env vars, and how the code is laid out. For a **plain-language overview of what the product does and how the phases fit together**, read [Architecture.md](Architecture.md) first.

Sub-architecture notes in [Architecture/phase2_factsheet_rag_architecture.md](Architecture/phase2_factsheet_rag_architecture.md), [Architecture/phase3_orchestrator_architecture.md](Architecture/phase3_orchestrator_architecture.md), and [Architecture/phase4_book_appointment_architecture.md](Architecture/phase4_book_appointment_architecture.md) go deeper on RAG, the orchestrator graph, and booking.

---

## 1. Repository layout

| Area | Path | Role |
|------|------|------|
| Phase 1 API | `backend/phase1_review_intelligence/` | Review scrape, themes KB build, REST for themes + refresh |
| Phase 2 API | `backend/phase2_factsheet_rag/` | Factsheet or definition URL lists, indexing pipeline, FAQ agent HTTP API |
| Phase 3 API | `backend/phase3_orchestrator/` | LangGraph orchestrator, booking execution, voice WebSocket, appointments + slot admin API |
| Shared data | `backend/data/` | e.g. `themes_kb.json`, `meetings_log.json` (paths configurable via env) |
| User-facing UI | `frontend/user_portal/` | Vite + React 19 chat (text + voice client) |
| Internal UI | `frontend/internal_dashboard/` | Next.js 16 dashboard (themes, FAQs, appointments, slot policy) |
| Environment | `.env` (from `.env.sample`) | API keys, Google OAuth, Sarvam, paths |

---

## 2. Runtime topology

The backend is **three FastAPI processes**, not a single monolith:

| Service | Default port | Entry | Responsibility |
|---------|--------------|--------|----------------|
| Phase 1 | **8000** | `phase1_review_intelligence/api.py` | `GET /api/reviews/themes`, `POST /api/reviews/refresh`, status |
| Phase 2 | **8001** | `phase2_factsheet_rag/api.py` | FAQ URL CRUD, `POST` refresh for factsheets or definitions, `POST /api/chat` (FAQ agent) |
| Phase 3 | **8002** | `phase3_orchestrator/api.py` | `POST /api/chat` (orchestrator), `WebSocket /voice/ws`, appointments + slot config |

**Integration contract:** the orchestrator calls the FAQ service over HTTP (`FAQ_AGENT_URL`, default `http://127.0.0.1:8001/api/chat`). The user portal talks to **8002** for chat and voice; the internal dashboard calls **8000**, **8001**, and **8002** for its sections.

**Session model:** orchestrator conversation graph state is kept **in memory** per `session_id` (`phase3_orchestrator/stores.py`). Clients must echo `session_id` on each turn (including voice) for continuity.

---

## 3. Phase 1: Review intelligence (implemented)

**Pipeline** (`pipeline.py`): fetch reviews, cleanse (minimum word count), stratified sample for themes, theme generation, classify and tag **all** retained reviews, aggregate, write KB.

**Data sources:** Play Store and App Store (`scraper.py`), configured via `PLAYSTORE_APP_ID`, `APPSTORE_APP_ID`, `APP_STORE_REGION`.

**LLMs:**

- **Theme generation:** Groq, model `llama-3.3-70b-versatile` (`analyzer.generate_themes`).
- **Classification + sentiment together:** Google **Gemini 2.5 Flash** over REST, batched (e.g. 50 reviews per batch), parallel workers, **rotating** `GEMINI_API_KEY_PHASE1_CLASS_*` keys (`analyzer.classify_and_tag`). This is **one** JSON response per review: theme + sentiment. It is **not** separate Groq sentiment and separate Gemini classification steps as in the older phase overview in [Architecture/architecture.md](Architecture/architecture.md).

**Output:** JSON knowledge base at `backend/data/themes_kb.json` (API reads this path relative to Phase 1).

**API surface:** themes read, refresh trigger with background task, in-memory `running` or `last_run` status.

---

## 4. Phase 2: Factsheet RAG (implemented)

**Offline indexing** (`pipeline.py`):

1. Scrape factsheets and or definition pages (`scraper.py`).
2. Chunk: one chunk per **factsheet field** per scheme plus one chunk per **definition** (`embedder.build_chunks`).
3. **Embed with Gemini API** using model **text-embedding-004** (768-dim) with **4-key rotation** to handle rate limits and save RAM for cloud deployment (`embedder.py`).
4. Index in **ChromaDB** persistent store under `backend/phase2_factsheet_rag/chroma_db/`.
5. Persist per-URL indexing metadata in `backend/phase2_factsheet_rag/config/indexing_metadata.json`.

**URL configuration:** separate JSON lists: `config/factsheet_urls.json` and `config/definition_urls.json`. Refresh can target factsheets only, definitions only, or both (API on 8001).

**Online FAQ agent** (`agent.py`): **Groq** `llama-3.3-70b-versatile` for query understanding and answer synthesis, with **primary + fallback** keys (`GROQ_API_KEY_FAQ_AGENT`, `GROQ_API_KEY_FAQ_AGENT_FALLBACK`). Retrieval uses `retriever.py` against Chroma. The codebase path does **not** call Gemini for the FAQ agent (`.env.sample` still lists `GEMINI_API_KEY_FAQ_AGENT` for optional or legacy use; `agent.py` has no Gemini usage).

**Response shape:** structured dict with `type` (`answer` / `clarify` / `refuse`), `text`, optional `links` for citations.

---

## 5. Phase 3: Orchestrator (implemented)

**Framework:** **LangGraph** `StateGraph` compiled in `graph.py`. Entry point for tests and API: `run_orchestrator()` in the same module.

**LLM:** **Groq** with primary model **`openai/gpt-oss-120b`**, fallback chain to `llama-3.3-70b-versatile`, then `llama-3.1-70b-versatile`, then `llama-3.1-8b-instant`, and a **second API key** after model fallbacks (`GROQ_API_KEY_ORCHESTRATOR`, `GROQ_API_KEY_ORCHESTRATOR_FALLBACK`). Helpers: `_llm_json`, `_llm_text` in `nodes.py`.

**Themes:** loaded from `backend/data/themes_kb.json` (`_THEMES_KB_PATH` in `nodes.py`).

**Pillars (conceptual):** intent detection and routing implement **theme match**, **FAQ** (HTTP to 8001), **booking**, **cancel or reschedule**, **confirmation pending** handling, and **out-of-scope** classification (`classify_out_of_scope_node`). The graph structure and edge conditions are documented inline at the top of `graph.py`.

**FAQ integration:** `call_faq_agent_node` uses `requests` to `FAQ_AGENT_URL`.

**Escalation:** dissatisfaction and human handoff are handled inside the graph (booking collection, topic from context), consistent with the phase 3 sub-architecture doc.

---

## 6. Phase 4: Booking (implemented inside orchestrator)

The older eight-phase narrative described separate Booking, Slot Check, and Implementation **agents**. **In code there are no separate booking agents.** Booking is a **branch of the same LangGraph**: slot check, alternative suggestions, final confirmation parsing, booking code generation, execution, and close message (`nodes.py`).

**Slot availability and policy:** rules live in **`availability_policy.py`**, loaded from `backend/phase3_orchestrator/config/slot_config.json` (defaults if missing): work hours, lunch window, weekday mask, gap between meetings, and **holidays** as dated entries. The internal dashboard loads and saves this via **`GET/PUT /api/admin/slot-config`** on port **8002**.

**Calendar check:** uses **Google Calendar API** through the workspace client (read busy or free for slot logic in `nodes.py`).

**Booking execution** (`execute_booking_node`): sequential steps:

1. Create **Google Calendar** event (critical; failure aborts execution path).
2. Create **Google Doc** for meeting notes; optionally attach link to event.
3. Send **Gmail** to broker (`MF_DISTRIBUTOR_EMAIL`).
4. Append row to **local meetings log** via `meetings_log.append_entry` (not a Google Sheet as the system of record).

**Meetings source of truth:** **`MEETINGS_LOG_PATH`** (default `backend/data/meetings_log.json`). **`GET /api/appointments`** on 8002 serves this file for the internal dashboard.

**Booking code:** generated in `google_workspace_mcp.py` with collision check against existing log entries.

**User email:** optional `POST /api/send-booking-details` sends confirmation to the user’s email using the workspace client.

---

## 7. Google Workspace integration (implemented)

The module `backend/phase3_orchestrator/google_workspace_mcp.py` defines **`GoogleWorkspaceMCP`**. Despite the name, integration is **direct Google APIs** via **`google.oauth2.credentials.Credentials`** (refresh token) and **`googleapiclient`**, not the Model Context Protocol. Env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`, `GOOGLE_DOCS_FOLDER_ID`, etc.

**Implemented surfaces:** Calendar (events, attachment updates), Gmail (broker and user messages), Docs, Drive as needed by those flows. **Sheets** are not part of the booking persistence path in `execute_booking_node`.

---

## 8. Phase 5: Voice (implemented)

**Location:** `backend/phase3_orchestrator/phase5_voice/` (Sarvam STT or TTS, WebSocket handler, voice turn assembly).

**Wire-up:** FastAPI **`WebSocket /voice/ws`** on **8002** delegates to `handle_voice_websocket` in `api.py`. Audio expectations and model IDs follow `.env.sample` (`SARVAM_*`, `AUDIO_*`).

**Behavior:** streaming STT and TTS; orchestrator still consumes **text**; transcript alignment uses `stores._session_message_log` for parity with REST chat.

---

## 9. Phase 6: GitHub Actions scheduler (implemented)

**Workflows** (repo root `.github/workflows/`):

| Workflow | Schedule | Triggered endpoint |
|----------|----------|-------------------|
| `schedule-review-intelligence.yml` | Weekly (default: Sunday 03:15 UTC) | `POST {PHASE1}/api/reviews/refresh` |
| `schedule-factsheet-rag.yml` | Daily (default: 04:05 UTC) | `POST {PHASE2}/api/faqs/factsheets/refresh` |

Both also support **`workflow_dispatch`** for manual runs from the Actions tab. They mirror the internal dashboard: **no extra backend code paths**, only HTTP `POST` to the deployed FastAPI services (e.g. Render).

**Repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `SCHEDULER_PHASE1_URL` | Base URL for Phase 1 only (e.g. `https://…onrender.com`), no path |
| `SCHEDULER_PHASE2_URL` | Base URL for Phase 2 only |

Cron expressions are in the YAML files; change them there if you need different times. Definitions refresh is **not** scheduled (factsheets only).

**Local testing (same HTTP contract as CI):**

- **One-shot:** with Phase 1 on 8000 and Phase 2 on 8001, from repo root:
  - PowerShell: `.\scripts\test-scheduler-local.ps1 -Once`
  - Bash (Git Bash or WSL): `bash scripts/test-scheduler-local.sh --once`
- **Loop every N seconds** (e.g. 300): omit `-Once` / omit `--once`, or set `-IntervalSeconds` / `--interval`.
- **After deploy:** use **Run workflow** on each workflow in GitHub Actions (no need to wait for cron).
- **Note:** GitHub `schedule` can be delayed a few minutes; it does not support sub-minute cadence. For rapid iteration, prefer `workflow_dispatch` or the scripts above against `http://127.0.0.1:8000` and `:8001`.

---

## 10. Frontends (implemented)

| App | Stack | Backend dependencies |
|-----|-------|----------------------|
| **user_portal** | Vite, React 19 | Orchestrator **8002** (`/api/chat`, `/voice/ws`) |
| **internal_dashboard** | Next.js 16, React 19, Tailwind 4 | **8000** themes or refresh, **8001** FAQ URLs and indexing, **8002** appointments and slot config |

Exact API base URLs are configured in each app’s environment or config (not repeated here).

---

## 11. Technology summary (as implemented)

| Concern | Implementation |
|---------|----------------|
| Phase 1 themes | Groq Llama 3.3 70B |
| Phase 1 classify + sentiment | Gemini 2.5 Flash (batched REST) |
| Embeddings | Gemini API `text-embedding-004` (with key rotation) |
| Vector DB | ChromaDB persistent |
| FAQ answer path | Groq Llama 3.3 70B + retrieval |
| Orchestrator | LangGraph + Groq `openai/gpt-oss-120b` with fallbacks |
| Booking side effects | Google Calendar, Docs, Gmail; local JSON log |
| Voice | Sarvam (WebSocket on 8002) |
| HTTP servers | FastAPI + uvicorn (three ports) |

---

## 12. Divergences from [Architecture/architecture.md](Architecture/architecture.md) (quick reference)

1. **Services:** three FastAPI apps on **8000 / 8001 / 8002**, with FAQ invoked over **HTTP** from the orchestrator.
2. **Phase 1:** sentiment is **not** a separate Groq step; it is **combined with theme classification in Gemini**.
3. **Phase 2:** embeddings are **local**, not API-based; FAQ runtime is **Groq-heavy**, not Gemini-first.
4. **Phase 3–4:** **no** separate booking or slot-check **agents**; **LangGraph nodes** + **`GoogleWorkspaceMCP`** client.
5. **MCP:** external automation is **not** MCP; it is **OAuth + googleapiclient**.
6. **Meetings log:** **JSON file** on disk, not a master Google Sheet written by an “Implementation Agent”.
7. **Holidays or hours:** **`slot_config.json`** API on 8002, not only a CSV upload flow.
8. **Phase 6:** GitHub Actions workflows under `.github/workflows/` trigger Phase 1 and Phase 2 refresh endpoints on a schedule; see §9.
9. **Orchestrator model:** **`openai/gpt-oss-120b`** on Groq, not a small Llama-only stack as implied by some older tables.

For graph-level detail, prefer the comments in `backend/phase3_orchestrator/graph.py` and the sub-docs linked at the top of this file.
