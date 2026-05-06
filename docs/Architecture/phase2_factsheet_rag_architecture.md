# Phase 2 — Factsheet RAG System (FAQ Agent): Sub-Architecture

> Detailed architecture for the Factsheet RAG System (Phase 2 of the Investor Ops & Intelligence Suite). This subsystem powers the FAQ agent — maintaining a factsheet knowledge base built from scraped Groww pages, and answering investor questions at runtime by retrieving relevant content and generating sourced replies that may combine scheme-specific data with concept definitions.

---

## Purpose

This subsystem is responsible for two things:

1. Maintaining a **factsheet knowledge base** built from two scraped sources — Groww factsheet pages (one per scheme) and separate pages containing definitions of common mutual fund terms.
2. Answering investor questions at runtime by retrieving the relevant content and generating a **sourced reply** that may combine scheme-specific data with concept definitions in a single answer.

The subsystem has two flows: an **offline indexing flow** (run on demand from the Internal Dashboard) and an **online retrieval flow** (run every time the FAQ agent is called).

---

## System Overview

The system operates across two distinct flows — one offline, one online — sharing a single vector store.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Factsheet RAG System                                     │
│                                                                              │
│  OFFLINE INDEXING FLOW                                                       │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────────────┐  │
│  │  Stage 1   │──▶│  Stage 2   │──▶│  Stage 3   │──▶│     Stage 4        │  │
│  │   Fetch    │   │ Structure  │   │  Embed &   │   │ Persist Indexing   │  │
│  │  Content   │   │  & Chunk   │   │   Index    │   │    Metadata        │  │
│  └────────────┘   └────────────┘   └────────────┘   └────────────────────┘  │
│                                                                              │
│  ONLINE RETRIEVAL FLOW                                                       │
│  ┌────────────┐   ┌────────────┐   ┌──────────────────────────────────────┐  │
│  │  Stage 1   │──▶│  Stage 2   │──▶│          Stage 3                    │  │
│  │   Query    │   │  Decide    │   │   Return to Caller                  │  │
│  │ Understand │   │  Path      │   │   (Answer / Clarify / Refuse)       │  │
│  └────────────┘   └────────────┘   └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Two URL Lists, One Pipeline

The Internal Dashboard manages two separate URL lists, both feeding the same indexing pipeline:

| URL List | Description | Refresh Cadence |
|---|---|---|
| **Factsheet URLs** | One URL per mutual fund scheme. Each URL points to the Groww factsheet page for that scheme. | Frequent — data like NAV changes often. |
| **Definitions URLs** | One URL per mutual fund term (exit load, expense ratio, NAV, SIP, SWP, AUM, lock-in, etc.). Each definition has its own dedicated link. | Rare — definitions change infrequently. |

Keeping them as separate lists lets the ops team manage the cadence of each independently and add/remove individual definitions without affecting factsheet scraping. Internally, both feed the same indexing pipeline and end up in the same vector store, just tagged differently via `kind` metadata.

The dashboard exposes **two independent refresh buttons** — one for "Refresh factsheets" and one for "Refresh definitions" — so each set can be refreshed on its own cadence without forcing a re-scrape of the other.

### Refresh Button — Dual Purpose

Each refresh button performs **two jobs in a single action**:

| Job | Description |
|---|---|
| **1. Re-scrape existing URLs** | Fetches the latest data from every URL currently in the list (e.g., updated NAV, changed expense ratio). This keeps the knowledge base current. |
| **2. Sync URL list changes** | If the ops team has added, removed, or changed any URLs in the list since the last refresh, pressing refresh applies those changes to the knowledge base. |

This means the ops team's workflow is always the same — edit the URL list if needed, then press refresh:

| URL List Change | Effect on Knowledge Base After Refresh |
|---|---|
| **URL added** (new scheme or new definition) | **Every URL in the list is scraped** — both the newly added URL and all existing URLs. The new URL's data enters the knowledge base and all existing data is refreshed with the latest values. Coverage **grows** and existing data stays current. |
| **URL removed** (scheme or definition dropped) | The remaining URLs are all re-scraped. The removed URL's data is purged from the knowledge base during the atomic replace. Coverage **shrinks**. |
| **URL changed** (pointing to a different page) | All URLs are re-scraped. The old data is replaced with data from the new URL. |
| **No URL changes** (just a data refresh) | All existing URLs are re-scraped to pick up the latest values (NAV, fund size, etc.). |

> **Key point**: Refresh always scrapes **every URL in the current list** — there is no distinction between "new" and "existing" URLs at scrape time. Whether you added a URL, removed one, or changed nothing, pressing refresh runs the full pipeline against the entire list. This is a **full rebuild**, not a differential update.

**Worked example:**

> The factsheet list has 5 URLs. Last refresh was at 12:00 PM. At 12:35 PM, the ops team adds a 6th URL (e.g., HDFC Mid-Cap). At 12:37 PM, they press "Refresh factsheets".
>
> **Result**: The pipeline scrapes all 6 URLs — the 5 existing schemes get their latest data (updated NAV, fund size, etc.) AND the newly added HDFC Mid-Cap scheme is scraped for the first time. The knowledge base now covers 6 schemes, all with data as of 12:37 PM.

> **Implementation note**: This works naturally because Stage 3 (Embed & Index) performs an **atomic replace** — the entire index is rebuilt from the current URL list. URLs that no longer exist in the list simply produce no chunks, so their data disappears from the new index. New URLs produce new chunks that appear in the new index. There is no separate "add" or "delete" operation — every refresh is a full rebuild from the current list.

---

## Factsheet Fields Extracted

Only the following 14 fields are extracted from each factsheet page. Everything else is ignored.

| # | Field |
|---|---|
| 1 | Lock-in |
| 2 | NAV |
| 3 | Minimum SIP |
| 4 | Fund Size |
| 5 | Expense Ratio |
| 6 | Alpha |
| 7 | Beta |
| 8 | Sharpe |
| 9 | Sortino |
| 10 | P/E Ratio |
| 11 | P/B Ratio |
| 12 | Exit Load |
| 13 | Stamp Duty |
| 14 | Fund Management |

> The scraper treats anything outside this list as out-of-scope — it is not the job of this subsystem to capture the entire factsheet page.

---

## Inputs and Outputs

### Offline Indexing Flow

| Aspect | Description |
|---|---|
| **Trigger** | Manual invocation from the Internal Dashboard. Two independent refresh buttons: one for factsheets, one for definitions. Either can also be run on a schedule (GitHub Actions — Phase 6). |
| **Inputs** | The configured factsheet URL list, the configured definitions URL list (one URL per term), or both — depending on which refresh was triggered. |
| **Outputs** | An updated factsheet knowledge base (vector store), plus indexing metadata (timestamp, URL count, per-URL success/failure) surfaced on the dashboard separately for each list. |

### Online Retrieval Flow

| Aspect | Description |
|---|---|
| **Inputs** | The user's question, plus any conversation context provided by the calling agent (such as which scheme has already been mentioned earlier in the chat). |
| **Outputs** | One of three responses: (A) a sourced answer combining factsheet data with definitions, (B) a clarifying question if the input is too vague, or (C) an honest "I don't know" if the relevant scheme or definition isn't in the knowledge base. |

---

## Offline Indexing Flow

### Stage 1 — Fetch Content

Two parallel fetchers run, one per URL list type.

```
                    ┌───────────────────────────┐
                    │     Stage 1: Fetch         │
                    └───────────┬───────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼                               ▼
    ┌───────────────────┐           ┌───────────────────┐
    │  Factsheet        │           │  Definitions      │
    │  Fetcher          │           │  Fetcher           │
    │                   │           │                    │
    │  One URL per      │           │  One URL per       │
    │  mutual fund      │           │  MF term           │
    │  scheme           │           │                    │
    │                   │           │  Yields exactly    │
    │  Extracts 14      │           │  one definition    │
    │  specified fields │           │  record per URL    │
    └────────┬──────────┘           └────────┬──────────┘
             │                               │
             └───────────┬───────────────────┘
                         ▼
              Raw factsheet records
              + raw definition records
```

#### Factsheet Fetcher

| Aspect | Details |
|---|---|
| **Input** | Factsheet URL list from the dashboard. |
| **Per-URL action** | Fetch the page, extract only the 14 specified fields. |
| **Scheme identification** | The scheme name is identified from the page and attached as metadata. |
| **Field detection** | Should be robust to small layout variations on the page. |
| **Failure handling** | If a URL fails to scrape, log the failure and continue. A partial index is better than no index. |

#### Definitions Fetcher

| Aspect | Details |
|---|---|
| **Input** | Definitions URL list from the dashboard (one URL per term). |
| **Per-URL action** | Fetch the page and extract the definition text for the term that URL covers. |
| **Term identification** | The term name is known from the URL configuration in the dashboard, not inferred from the page. |
| **Output** | Each URL yields exactly one definition record. |

---

### Stage 2 — Structure and Chunk

All fetched content is structured into retrievable chunks with rich metadata.

```
Raw factsheet records + raw definition records (Stage 1 output)
        │
        ├──▶ Per-field chunking (factsheets)
        │
        ├──▶ Per-definition chunking (definitions)
        │
        ▼
  Structured chunks with metadata, ready for embedding
```

#### Factsheet Chunk Schema

Each factsheet field for each scheme becomes its own retrievable chunk. Per-field chunking ensures retrieval can be precise — most queries target a specific field for a specific scheme.

| Chunk Field | Example | Description |
|---|---|---|
| `value` | `"1% if redeemed within 1 year, 0% after"` | The field value extracted from the factsheet. |
| `scheme_name` | `"Axis Bluechip"` | Name of the mutual fund scheme. |
| `field` | `"Exit Load"` | Which of the 14 factsheet fields this chunk represents. |
| `source_url` | `"https://groww.in/mutual-funds/..."` | The URL the data was scraped from. |
| `scraped_at` | `"2025-03-15T10:30:00Z"` | Timestamp of when this data was scraped. |
| `kind` | `"factsheet_field"` | Distinguishes factsheet chunks from definition chunks in the vector store. |

> **Why per-field chunking?** Most queries are about a specific field for a specific scheme (e.g., "What's the exit load on Axis Bluechip?"). Keeping fields separate lets the retriever target exactly what's needed without pulling the entire factsheet.

#### Definition Chunk Schema

Each definition becomes one chunk.

| Chunk Field | Example | Description |
|---|---|---|
| `text` | `"Exit load is a fee charged by..."` | The full definition text. |
| `term` | `"exit load"` | The mutual fund term this definition covers. |
| `source_url` | `"https://groww.in/p/exit-load"` | The URL the definition was scraped from. |
| `scraped_at` | `"2025-03-15T10:30:00Z"` | Timestamp of when this definition was scraped. |
| `kind` | `"definition"` | Distinguishes definition chunks from factsheet chunks in the vector store. |

---

### Stage 3 — Embed and Index

```
Structured chunks (Stage 2 output)
        │
        ▼
  Generate embeddings for every chunk
        │
        ▼
  Write all chunks to vector store
  (factsheet fields + definitions together,
   distinguished by `kind` metadata)
        │
        ▼
  Atomic replace — old index stays live
  until new one is fully written, then swap
```

| Aspect | Details |
|---|---|
| **Embedding** | Generate vector embeddings for every chunk (both factsheet fields and definitions). |
| **Storage** | All chunks are written to the **same vector store**, distinguished only by their `kind` metadata (`factsheet_field` vs `definition`). |
| **Atomicity** | The previous index stays live until the new one is fully written, then the swap happens. Readers never see a half-updated state. |
| **Full rebuild** | Every refresh rebuilds the index from the **current URL list**. This is what makes the refresh button dual-purpose — added URLs produce new chunks, removed URLs produce no chunks (so their data is purged), and existing URLs get fresh data. No separate add/delete logic is needed. |

---

### Stage 4 — Persist Indexing Metadata

Update dashboard-visible metadata so the ops team has full visibility into the indexing state. This includes **per-URL status indicators** so the dashboard can show exactly which URLs were successfully scraped and which failed in each refresh run.

#### Run-level Metadata

| Metadata Field | Description |
|---|---|
| **Refresh timestamp** | When the last indexing run completed (e.g., `30 Apr 2025 · 10:50 AM`). |
| **Total schemes processed** | Number of factsheet URLs successfully scraped out of total configured. |
| **Total definitions processed** | Number of definition URLs successfully scraped out of total configured. |

#### Per-URL Status Record

For every URL in both lists, the pipeline persists a status record:

| Field | Type | Description |
|---|---|---|
| `url` | string | The factsheet or definition URL. |
| `label` | string | Scheme name (for factsheets) or term name (for definitions). |
| `status` | enum | `success` or `failed`. |
| `scraped_at` | datetime | Timestamp of the scrape attempt. |
| `failure_reason` | string (nullable) | If failed — the reason (e.g., `"HTTP 404"`, `"timeout"`, `"parse error"`). Null if successful. |

#### Dashboard Indicator — Per-URL Tick / Cross

The Internal Dashboard renders every URL with a visual **✅ / ❌** indicator against the refresh timestamp, so the ops team can see at a glance which URLs were updated and which were not.

**Example — after a factsheet refresh at `30 Apr 2025 · 10:50 AM`:**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Factsheet Knowledge Base                                          │
│  Last refreshed: 30 Apr 2025 · 10:50 AM                           │
│                                                                     │
│  ✅  Axis Bluechip Fund         groww.in/mutual-funds/axis-blue... │
│  ✅  SBI Small Cap Fund         groww.in/mutual-funds/sbi-smal...  │
│  ✅  ICICI Prudential Value     groww.in/mutual-funds/icici-pr...  │
│  ❌  Parag Parikh Flexi Cap     groww.in/mutual-funds/parag-pa...  │
│      └── Reason: HTTP 504 — Gateway timeout                       │
│  ✅  Mirae Asset Large Cap      groww.in/mutual-funds/mirae-as...  │
│                                                                     │
│  4 / 5 URLs updated successfully                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Definitions Knowledge Base                                        │
│  Last refreshed: 28 Apr 2025 · 02:15 PM                           │
│                                                                     │
│  ✅  Exit Load                  groww.in/p/exit-load               │
│  ✅  Expense Ratio              groww.in/p/expense-ratio           │
│  ✅  NAV                        groww.in/p/nav                     │
│  ✅  SIP                        groww.in/p/sip                     │
│  ✅  AUM                        groww.in/p/aum                     │
│                                                                     │
│  5 / 5 URLs updated successfully                                   │
└─────────────────────────────────────────────────────────────────────┘
```

> **Key behaviour**: The tick/cross indicators always reflect the **most recent refresh run** for that URL list. If a factsheet refresh is triggered but not a definitions refresh, the factsheet indicators update while the definitions indicators remain unchanged (showing their own last refresh timestamp).

---

## Online Retrieval Flow

This runs every time the FAQ agent is invoked by the Orchestrator (Phase 3, Lane 2). **Latency matters** — the user is waiting.

### Stage 1 — Query Understanding

The FAQ agent inspects the user's question to determine three things:

| Determination | Description | Example |
|---|---|---|
| **What is the user asking about?** | A specific factsheet field, a concept (definition), or a synthesis question that needs both. | "What's the NAV?" → factsheet field. "What is exit load?" → concept. "Why was this exit load deducted?" → synthesis. |
| **Which scheme is in scope?** | Stated explicitly in the question, or inferable from conversation context passed by the caller. | "What's the NAV of Axis Bluechip?" → explicit. Prior conversation mentioned Axis Bluechip → inferred. |
| **Which fields/definitions are needed?** | A question mentioning "exit load" needs both the exit load field for the scheme AND the definition of exit load. | "What is the expense ratio of SBI Small Cap?" → needs `Expense Ratio` field + definition of `expense ratio`. |

```
User question + conversation context
        │
        ▼
  FAQ Agent — query understanding
        │
        ├── What type of question? (factsheet / concept / synthesis)
        ├── Which scheme? (explicit / inferred / unknown)
        └── Which fields + definitions needed?
        │
        ▼
  Structured query intent
```

---

### Stage 2 — Decide: Ask, Retrieve, or Refuse

The agent picks one of three paths based on what it determined in Stage 1.

```
                        ┌──────────────────────────────────────────────┐
                        │         FAQ Agent — Decision Gate             │
                        └──────┬──────────────┬──────────────┬─────────┘
                               │              │              │
                    ┌──────────▼──┐   ┌───────▼──────┐  ┌───▼──────────────┐
                    │  Path A     │   │  Path B      │  │  Path C          │
                    │ Clarifying  │   │ Retrieve &   │  │ Honest           │
                    │ Question    │   │ Answer       │  │ Refusal          │
                    └─────────────┘   └──────────────┘  └──────────────────┘
```

#### Path A — Ask a Clarifying Question (the question is too vague)

The agent should **ask back, not guess**, when:

- A factsheet-specific question doesn't identify a scheme and the conversation context doesn't either ("What's the NAV?" with no scheme mentioned anywhere).
- The question references multiple possible interpretations ("Why am I being charged extra?" — could be exit load, expense ratio, stamp duty).
- The user mentions a concept in passing without clearly asking about it.

The agent returns a clarifying question to the orchestrator, which relays it to the user.

| Trigger | Example Clarifying Question |
|---|---|
| No scheme identified | *"Which fund are you asking about?"* |
| Ambiguous field | *"Are you asking about the exit load, the expense ratio, or the stamp duty?"* |

> **Rules**: The agent does NOT silently default to a guess. It also does NOT use a generic "Could you clarify?" — the question must be **specific** about what information it needs.

#### Path B — Retrieve and Answer (the question is answerable)

The agent runs retrieval against the knowledge base. Retrieval is **metadata-aware**:

| Retrieval Strategy | Description |
|---|---|
| **Scheme filtering** | If a scheme is in scope, prefer chunks where `scheme_name` matches. |
| **Field filtering** | If a specific factsheet field is in scope, prefer chunks where `field` matches. |
| **Definition pull** | If a concept is in scope, also pull the matching definition chunk where `kind = "definition"` and `term` matches. |
| **Synthesis queries** | For synthesis questions (e.g., "Why was this exit load deducted?"), the retriever pulls both the relevant factsheet field for the scheme AND the relevant definition in one pass. |

**Answer generation rules:**

- Be grounded **only** in the retrieved chunks.
- Cite the source clearly — the factsheet section and the definition source.
- Combine factsheet data and definitions **naturally** when both are retrieved (don't list them as two separate paragraphs unless the question explicitly asks for both).

#### Path C — Honestly Refuse (the answer isn't in the knowledge base)

The agent **must refuse rather than invent** when:

- The scheme the user is asking about isn't in the factsheet knowledge base (no chunks with that `scheme_name`).
- The concept the user is asking about isn't in the definitions knowledge base (no chunks with that `term`).
- Retrieval returns chunks but their similarity to the query is below the confidence threshold.

**Refusal rules:**

| Rule | Description |
|---|---|
| **Honest and concise** | Simply state that it does not have information on the requested scheme or term. |
| **No hallucination** | Never invent or fabricate a partial answer. |
| **No scope disclosure** | Never list the schemes or terms the agent does cover — no "I can answer about X, Y, Z instead." This avoids leaking the configured scope to the user. |
| **No external hints** | Never hint at sources, links, or fallback resources. |

Example refusals:
- *"I don't have information on that fund."*
- *"I don't have a definition for that term."*

> The refusal is returned to the calling agent. The caller may then decide whether to offer an escalation path (e.g., booking a call with an advisor) — but that escalation decision is not the FAQ agent's job.

---

### Stage 3 — Return to Caller

The FAQ agent returns one of three response types to the Orchestrator:

| Response Type | Content |
|---|---|
| **Answer** (Path B) | Sourced answer with citations and a confidence signal. |
| **Clarifying Question** (Path A) | A specific question about what information is missing. |
| **Honest Refusal** (Path C) | A concise statement that the information is not available. |

The Orchestrator decides what to do with each response.

---

## Worked Examples

### Example 1 — The Synthesis Case

> **User:** "Why was ₹47 deducted as exit load from my Axis Bluechip redemption?"

| Step | Action |
|---|---|
| **1. Query understanding** | Scheme = Axis Bluechip, fields needed = Exit Load, concept needed = definition of exit load. |
| **2. Retrieval** | Pulls the Exit Load chunk for Axis Bluechip ("1% if redeemed within 1 year, 0% after") AND the definition of exit load. |
| **3. Generation** | LLM combines both into a single explanation — *"Axis Bluechip charges a 1% exit load on redemptions within the first year of investment. Exit load is a fee that mutual funds charge to discourage early withdrawals — it goes back into the fund. Based on the rule, your ₹47 charge corresponds to roughly ₹4,700 redeemed within the lock-in window."* |
| **4. Citations** | Axis Bluechip factsheet (Exit Load field) + definitions source (exit load entry). |

> This is the answer pattern that makes the agent feel useful instead of robotic.

---

### Example 2 — The Clarification Case

> **User:** "Why is my fund losing money?"

| Step | Action |
|---|---|
| **1. Query understanding** | Too vague — no specific field mentioned, "losing money" could mean NAV decline, expense ratio drag, exit load, stamp duty, market movement. |
| **2. Decision** | The agent does not retrieve. It asks back: *"A few things can affect your fund's value — recent market movement, the expense ratio, or charges like exit load or stamp duty. Which fund are you asking about, and is there a specific charge or change you noticed?"* |
| **3. After clarification** | The agent runs the normal retrieval flow with the clarified inputs. |

---

### Example 3 — The Honest Refusal Case

> **User:** "What's the alpha of HDFC Top 100?"

| Step | Action |
|---|---|
| **1. Query understanding** | Scheme = HDFC Top 100, field = Alpha. |
| **2. Retrieval** | No chunks match `scheme_name = "HDFC Top 100"` because that scheme's URL isn't in the configured factsheet list. |
| **3. Refusal** | *"I don't have information on that fund."* — no scope disclosure, no alternatives offered. |

---

## End-to-end System Summary

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  OFFLINE INDEXING FLOW                                                           │
│                                                                                  │
│  STAGE 1: Fetch Content                                                          │
│  Factsheet fetcher ──┐                                                           │
│                      ├──▶ Raw factsheet records + raw definition records          │
│  Definitions fetcher─┘                                                           │
│                                                                                  │
│  STAGE 2: Structure & Chunk                                                      │
│  Factsheet records ──▶ Per-field chunks with metadata (kind = factsheet_field)   │
│  Definition records ──▶ Per-definition chunks with metadata (kind = definition)  │
│                                                                                  │
│  STAGE 3: Embed & Index                                                          │
│  All chunks ──▶ Generate embeddings ──▶ Atomic write to vector store             │
│                                                                                  │
│  STAGE 4: Persist Metadata                                                       │
│  Timestamp + per-URL ✅/❌ status + failure reasons ──▶ Dashboard                │
│                                                                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ONLINE RETRIEVAL FLOW                                                           │
│                                                                                  │
│  STAGE 1: Query Understanding                                                    │
│  User question + context ──▶ Determine type, scheme, fields/definitions needed   │
│                                                                                  │
│  STAGE 2: Decide Path                                                            │
│  ├── Path A: Too vague ──▶ Clarifying question                                  │
│  ├── Path B: Answerable ──▶ Metadata-aware retrieval ──▶ Sourced answer         │
│  └── Path C: Not in KB ──▶ Honest refusal                                       │
│                                                                                  │
│  STAGE 3: Return to Caller                                                       │
│  Answer / Clarifying question / Refusal ──▶ Orchestrator (Phase 3)              │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Handling

| Scenario | Behaviour |
|---|---|
| **Individual URL fails during scraping** | Logged per URL. Dashboard surfaces the failure. Indexing continues with the URLs that worked. A partial index is better than no index. |
| **Empty retrieval at runtime** | Handled as Path C (honest refusal). Never silently defaulted to a guess. Never disclose the contents of the knowledge base when refusing. |
| **LLM generation errors** | The agent returns a graceful failure message to the caller. One retry is acceptable; beyond that, escalate. |
| **Stale data risk** | Every chunk carries a `scraped_at` timestamp. If a retrieved chunk is older than a configurable threshold, the answer should optionally include a soft caveat ("Based on factsheet data from [date]") so the user knows the answer may not reflect the latest values. |
| **Atomicity** | Readers (FAQ Agent, Dashboard) see either the old index or the new index — never a half-updated state. The previous index stays live until the new one is fully written, then the swap happens. |

---

## Configuration

All values below are configurable (config file or environment variables), not hardcoded:

| Parameter | Description |
|---|---|
| Factsheet URL list | Managed via the Internal Dashboard. Adding/removing a URL adds/removes that fund from FAQ Agent coverage. |
| Definitions URL list | Managed via the Internal Dashboard. One URL per mutual fund term. |
| Factsheet fields to extract | The 14 fields listed above. |
| Embedding model | Model used to generate vector embeddings for all chunks. |
| Vector store backend | The vector database used for chunk storage and retrieval. |
| Chunks per query | Number of chunks to retrieve per user query. |
| Similarity threshold | Score below which the agent refuses (Path C) rather than answering. |
| Stale-data caveat threshold | Age after which a retrieved chunk triggers a soft "data from [date]" caveat. |

---

## Downstream Consumers

| Consumer | What it reads | Phase |
|---|---|---|
| **Orchestrator Agent** | Invokes the FAQ Agent at query time when it detects a factsheet/fund question (Lane 2). | Phase 3 |
| **Internal Dashboard** | Reads indexing metadata (timestamp, scheme count, failures). Manages factsheet and definitions URL lists. Provides refresh buttons. | Phase 8 |
| **GitHub Actions Scheduler** | Invokes the offline indexing flow on a cron schedule. | Phase 6 |

---

## Dependencies on the Broader Product

This subsystem reads from two pieces of dashboard-managed configuration (factsheet URL list, definitions URL list) and writes to one piece of dashboard-visible state (indexing metadata). It is invoked at runtime by the Orchestrator Agent (Phase 3) that handles user-facing questions via Lane 2. It does not interact directly with the user, with calendars, or with the booking flow.

> The FAQ agent is an **internal agent** — it receives queries from and returns answers to the Orchestrator. The user never interacts with it directly.
