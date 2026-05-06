# Sub-Architecture: Mutual Fund FAQ

## Purpose

This subsystem powers the **FAQ agent**, which is invoked when an investor asks a factsheet-related question.

It is responsible for two things:

1. Maintaining a **factsheet knowledge base** built from two scraped sources — Groww factsheet pages (one per scheme) and a separate page containing definitions of common mutual fund terms.
2. Answering investor questions at runtime by retrieving the relevant content and generating a sourced reply that may combine **scheme-specific data with concept definitions** in a single answer.

The subsystem has two flows: an **offline indexing flow** (run on demand from the internal dashboard) and an **online retrieval flow** (run every time the FAQ agent is called).

---

## Two URL lists, one pipeline

The dashboard manages two separate URL lists, both feeding the same indexing pipeline:

1. **Factsheet URLs** — one URL per mutual fund scheme. Re-scraped frequently (data like NAV changes often).
2. **Definitions URLs** — **one URL per term**. Each definition (exit load, expense ratio, NAV, SIP, SWP, AUM, lock-in, etc.) has its own dedicated link in the list. Re-scraped rarely (definitions change rarely).

Keeping them as separate lists in the dashboard lets the ops team manage the cadence of each independently and add/remove individual definitions without affecting others. Internally, both feed the same indexing pipeline and end up in the same vector store, just tagged differently.

The dashboard exposes **two independent refresh buttons** — one for "Refresh factsheets" and one for "Refresh definitions" — so the ops team can refresh each set on its own cadence without forcing a re-scrape of the other.

---

## What gets scraped from each factsheet

Only the following fields are extracted from each factsheet page. Everything else is ignored.

- Lock-in
- NAV
- Minimum SIP
- Fund Size
- Expense Ratio
- Alpha
- Beta
- Sharpe
- Sortino
- P/E Ratio
- P/B Ratio
- Exit Load
- Stamp Duty
- Fund Management

These fields form the structured record per scheme. The scraper should treat anything outside this list as out-of-scope — it is not the job of this subsystem to capture the entire factsheet page.

## What gets scraped from definitions URLs

The full text of each definition for the mutual fund terms covered by the page. Each definition becomes its own retrievable unit in the knowledge base.

---

## Inputs and outputs

### Offline indexing flow
- **Trigger** — manual invocation from the internal dashboard. There are **two independent refresh buttons**: one for factsheets and one for definitions. Each button only re-scrapes and re-indexes the URL list it corresponds to. Either can also be run on a schedule.
- **Inputs** — the configured factsheet URL list, the configured definitions URL list (one URL per term), or both depending on which refresh was triggered.
- **Outputs** — an updated factsheet knowledge base, plus indexing metadata (timestamp, URL count, per-URL success/failure) surfaced on the dashboard separately for each list.

### Online retrieval flow
- **Inputs** — the user's question, plus any conversation context provided by the calling agent (such as which scheme has already been mentioned earlier in the chat).
- **Outputs** — one of three possible responses:
  1. A **sourced answer** that may combine factsheet data with definitions.
  2. A **clarifying question** if the input is too vague to answer confidently.
  3. An **honest "I don't know"** if the relevant scheme or definition isn't in the knowledge base.

---

## Offline indexing flow

### Stage 1 — Fetch content

Two parallel fetchers run, one per URL list type.

**Factsheet fetcher**
- For each factsheet URL, fetch the page.
- Extract only the 14 specified fields. Field detection should be robust to small layout variations on the page.
- Identify the scheme name from the page so it can be attached as metadata.
- If a URL fails to scrape, log the failure and continue. A partial index is better than no index.

**Definitions fetcher**
- For each definition URL (one URL per term), fetch the page.
- Extract the definition text for the term that URL covers.
- Each URL yields exactly one definition record. The term name is known from the URL configuration in the dashboard, not inferred from the page.

### Stage 2 — Structure and chunk

**Factsheet records**
Each factsheet field for each scheme becomes its own retrievable chunk, so retrieval can be precise. A chunk for "Axis Bluechip · Exit Load" carries:
- The field value (e.g., "1% if redeemed within 1 year, 0% after").
- Metadata: `scheme_name`, `field` (e.g., "Exit Load"), `source_url`, `scraped_at`, `kind = "factsheet_field"`.

This per-field chunking matters because most queries are about a specific field for a specific scheme. Keeping fields separate lets the retriever target exactly what's needed.

**Definition records**
Each definition becomes one chunk:
- The definition text.
- Metadata: `term` (e.g., "exit load"), `source_url`, `scraped_at`, `kind = "definition"`.

### Stage 3 — Embed and index

- Generate embeddings for every chunk.
- Write all chunks (factsheet fields + definitions) to the same vector store, distinguished only by their `kind` metadata.
- This is an **atomic replace** — the previous index stays live until the new one is fully written, then the swap happens. Readers never see a half-updated state.

### Stage 4 — Persist indexing metadata

Update dashboard-visible metadata: timestamp, total schemes processed, total definitions processed, list of any URLs that failed and why.

---

## Online retrieval flow

This runs every time the FAQ agent is invoked. Latency matters — the user is waiting.

### Stage 1 — Query understanding

The FAQ agent inspects the user's question to determine:

- **What is the user asking about?** A specific factsheet field (e.g., "what's the NAV"), a concept (e.g., "what is exit load"), or a synthesis question that needs both (e.g., "why was this exit load deducted from my fund").
- **Which scheme, if any, is in scope?** Stated explicitly in the question, or inferable from the conversation context passed in by the caller.
- **Which fields and/or definitions are likely needed?** A question mentioning "exit load" needs the exit load field for the scheme AND the definition of exit load. A question about "expense ratio" needs both, similarly.

### Stage 2 — Decide whether to ask, retrieve, or refuse

The agent picks one of three paths based on what it determined in Stage 1.

#### Path A — Ask a clarifying question (the question is too vague)

The agent should ask back, not guess, when:
- A factsheet-specific question doesn't identify a scheme and the conversation context doesn't either ("What's the NAV?" with no scheme mentioned anywhere).
- The question references multiple possible interpretations (e.g., "Why am I being charged extra?" — could be exit load, expense ratio, stamp duty).
- The user mentions a concept in passing without clearly asking about it.

The agent returns a clarifying question to the orchestrator, which relays it to the user. Examples:
- *"Which fund are you asking about?"*
- *"Are you asking about the exit load, the expense ratio, or the stamp duty?"*

The agent does NOT silently default to a guess. It also does NOT use a generic "Could you clarify?" — the question should be specific about what information it needs.

#### Path B — Retrieve and answer (the question is answerable)

The agent runs retrieval against the knowledge base. Retrieval is metadata-aware:
- If a scheme is in scope, prefer chunks where `scheme_name` matches.
- If a specific factsheet field is in scope, prefer chunks where `field` matches.
- If a concept is in scope, also pull the matching definition chunk where `kind = "definition"` and `term` matches.

For synthesis questions ("why was this exit load deducted?"), the retriever pulls both the relevant factsheet field for the scheme AND the relevant definition in one pass. The LLM is then prompted to weave both into a single answer that explains the rule (definition) AND applies it to the user's specific scheme (factsheet field).

The generated answer must:
- Be grounded only in the retrieved chunks.
- Cite the source clearly — the factsheet section and the definition source.
- Combine factsheet data and definitions naturally when both are retrieved (don't list them as two separate paragraphs unless the question explicitly asks for both).

#### Path C — Honestly refuse (the answer isn't in the knowledge base)

The agent must refuse rather than invent when:
- The scheme the user is asking about isn't in the factsheet knowledge base (no chunks with that `scheme_name`).
- The concept the user is asking about isn't in the definitions knowledge base (no chunks with that `term`).
- Retrieval returns chunks but their similarity to the query is below the confidence threshold.

The refusal must be honest and concise. The agent simply states that it does not have information on the requested scheme or term.

The refusal must NOT:
- Invent or hallucinate a partial answer.
- List the schemes or terms the agent does cover. The agent should never disclose what is in the knowledge base when refusing — no "I can answer about X, Y, Z instead." This avoids leaking the configured scope to the user and keeps refusals clean.
- Hint at sources, links, or fallback resources.

Example refusals:
- *"I don't have information on that fund."*
- *"I don't have a definition for that term."*

The refusal is returned to the calling agent. The caller may then decide whether to offer an escalation path (e.g., booking a call with an advisor) — but that escalation decision is not the FAQ agent's job.

### Stage 3 — Return to caller

The FAQ agent returns one of:
- An answer (Path B), with citations and a confidence signal.
- A clarifying question (Path A).
- An honest refusal (Path C).

The caller decides what to do with each.

---

## Worked example — the synthesis case

> **User:** "Why was ₹47 deducted as exit load from my Axis Bluechip redemption?"

1. Query understanding: scheme = Axis Bluechip, fields needed = Exit Load, concept needed = definition of exit load.
2. Retrieval: pulls the Exit Load chunk for Axis Bluechip ("1% if redeemed within 1 year, 0% after") AND the definition of exit load.
3. Generation: LLM combines both into a single explanation — *"Axis Bluechip charges a 1% exit load on redemptions within the first year of investment. Exit load is a fee that mutual funds charge to discourage early withdrawals — it goes back into the fund. Based on the rule, your ₹47 charge corresponds to roughly ₹4,700 redeemed within the lock-in window."*
4. Citations: Axis Bluechip factsheet (Exit Load field) + definitions source (exit load entry).

This is the answer pattern that makes the agent feel useful instead of robotic.

---

## Worked example — the clarification case

> **User:** "Why is my fund losing money?"

1. Query understanding: too vague — no specific field mentioned, "losing money" could mean NAV decline, expense ratio drag, exit load, stamp duty, market movement.
2. The agent does not retrieve. It asks back: *"A few things can affect your fund's value — recent market movement, the expense ratio, or charges like exit load or stamp duty. Which fund are you asking about, and is there a specific charge or change you noticed?"*
3. After the user clarifies, the agent runs the normal retrieval flow with the clarified inputs.

---

## Worked example — the honest refusal case

> **User:** "What's the alpha of HDFC Top 100?"

1. Query understanding: scheme = HDFC Top 100, field = Alpha.
2. Retrieval: no chunks match `scheme_name = "HDFC Top 100"` because that scheme's URL isn't in the configured factsheet list.
3. The agent refuses honestly without disclosing what it does cover: *"I don't have information on that fund."*

---

## Failure handling

- **Scraping failures** during indexing — logged per URL, dashboard surfaces them, indexing continues with the URLs that worked.
- **Empty retrieval** at runtime — handled as Path C (honest refusal). Never silently defaulted to a guess. Never disclose the contents of the knowledge base when refusing.
- **LLM generation errors** — the agent returns a graceful failure message to the caller. One retry is acceptable; beyond that, escalate.
- **Stale data risk** — every chunk carries a `scraped_at` timestamp. If a retrieved chunk is older than a configurable threshold, the answer should optionally include a soft caveat ("Based on factsheet data from \[date]") so the user knows the answer may not reflect the latest values.

---

## Configuration

Values that should live as configuration, not hardcoded:

- The factsheet URL list (managed via the dashboard).
- The definitions URL list (managed via the dashboard).
- The 14 factsheet fields to extract.
- Embedding model.
- Vector store backend.
- Number of chunks to retrieve per query.
- Similarity threshold below which the agent refuses (Path C).
- Threshold for stale-data caveats.

---

## Dependencies on the broader product

This subsystem reads from two pieces of dashboard-managed configuration (factsheet URL list, definitions URL list) and writes to one piece of dashboard-visible state (indexing metadata). It is invoked at runtime by the calling agent that handles user-facing questions. It does not interact directly with the user, with calendars, or with the booking flow.
