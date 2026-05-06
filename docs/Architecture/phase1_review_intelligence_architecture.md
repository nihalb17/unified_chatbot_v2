# Phase 1 — Review Intelligence Pipeline: Sub-Architecture

> Detailed architecture for the Review Intelligence Pipeline (Phase 1 of the Investor Ops & Intelligence Suite). This pipeline fetches Groww app reviews from both app stores, discovers themes, classifies every review into a theme, tags sentiment, and produces the Themes knowledge base consumed by the Orchestrator Agent (Phase 3) and the Internal Dashboard (Phase 8).

---

## App Store Links

| Store | URL |
|---|---|
| **Apple App Store** | https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703 |
| **Google Play Store** | https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN |

---

## Pipeline Overview

The pipeline runs as **five sequential stages**. Each stage produces the input for the next. The entire pipeline is invoked on demand (dashboard refresh button) or on a schedule (GitHub Actions — Phase 6).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Review Intelligence Pipeline                              │
│                                                                              │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────┐ │
│  │  Stage 1   │──▶│  Stage 2   │──▶│  Stage 3   │──▶│  Stage 4   │──▶│ S5 │ │
│  │   Fetch    │   │  Sample    │   │  Theme Gen │   │  Classify  │   │Agg │ │
│  │  Reviews   │   │  Reviews   │   │  (Groq)    │   │  (Gemini)  │   │    │ │
│  └────────────┘   └────────────┘   └────────────┘   └────────────┘   └────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Inputs

| Input | Description |
|---|---|
| **Trigger** | Manual invocation from the Internal Dashboard (refresh button), or automated run via GitHub Actions Scheduler (Phase 6). |
| **Time window** | Rolling **last 10 weeks**. Reviews older than 10 weeks are excluded. |
| **Play Store app ID** | `com.nextbillion.groww` |
| **App Store app ID** | `1404871703` |
| **Region** | India (`in`) — Groww serves Indian investors. |

## Outputs

| Output | Description |
|---|---|
| **Themes Knowledge Base** | Refreshed set of themes with counts, sentiment, representative quotes, and actionable items. |
| **Refresh Metadata** | Timestamp of last refresh, total reviews processed, source breakdown (Play Store vs App Store). |

---

## Stage 1 — Fetch Reviews

### Objective

Pull the latest Groww app reviews from both app stores, normalize them to a shared schema, and merge into a single corpus.

### Architecture

Two **parallel fetchers** run simultaneously — one per source. Both write to the same normalized schema before being merged.

```
                    ┌───────────────────────┐
                    │     Stage 1: Fetch     │
                    └───────────┬───────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼                               ▼
    ┌───────────────────┐           ┌───────────────────┐
    │  Play Store       │           │  App Store         │
    │  Fetcher          │           │  Fetcher           │
    │                   │           │                    │
    │  App ID:          │           │  App ID:           │
    │  com.nextbillion  │           │  1404871703         │
    │  .groww           │           │                    │
    │                   │           │  Paginates until   │
    │  Sorted newest-   │           │  10-week boundary  │
    │  first            │           │                    │
    └────────┬──────────┘           └────────┬──────────┘
             │                               │
             └───────────┬───────────────────┘
                         ▼
              ┌─────────────────────┐
              │  Normalize + Merge  │
              │  + Deduplicate      │
              └─────────────────────┘
                         │
                         ▼
              Combined review corpus
              (last 10 weeks)
```

### Normalized Review Schema

Every fetched review (regardless of source) is mapped to:

| Field | Type | Description |
|---|---|---|
| `review_id` | string | Unique identifier within its source. |
| `source` | enum | `playstore` or `appstore`. |
| `date` | datetime | When the review was posted. |
| `rating` | int (1–5) | Star rating. |
| `title` | string | Review title (may be empty for Play Store reviews). |
| `content` | string | The review body text. |

> **PII Policy**: User names, display handles, and any other personally identifiable information (PII) are **never collected or stored**. The fetchers intentionally skip user identity fields from both app stores. Only the review content itself is retained.

### Source-specific Behaviour

| Behaviour | Play Store | App Store |
|---|---|---|
| **Sorting** | Newest-first to minimize over-fetching. | Batch pagination until the 10-week boundary is hit. |
| **Filtering** | Reviews within the last 10 weeks only. | Reviews within the last 10 weeks only. |
| **Region** | India (`in`) via `hl=en_IN`. | India (`in`). |

### Output

A single combined list of normalized reviews from both sources, deduplicated, all dated within the 10-week window.

---

## Stage 2 — Sample for Theme Discovery

### Objective

Select a representative subset of the fetched reviews for theme generation. Running theme discovery on the entire corpus is expensive and noisy — a stratified sample is sufficient.

### Sampling Strategy

| Strategy | Details |
|---|---|
| **Target sample size** | A few hundred reviews (configurable). |
| **Stratification** | Reflects the source mix — e.g., if Play Store contributes 80% of total reviews, the sample is ~80% Play Store / ~20% App Store. |
| **Rating bias** | Slightly over-samples lower-rated reviews (1, 2, 3 stars) since these carry richer, more actionable theme signal than 5-star praise. |
| **Minimum length** | Reviews shorter than 5 words are dropped — they don't carry meaningful theme signal. |

### Data Flow

```
Combined review corpus (Stage 1 output)
        │
        ▼
  Apply source stratification
        │
        ▼
  Bias toward low-rated reviews (1–3 stars)
        │
        ▼
  Drop reviews < 5 words
        │
        ▼
  Sampled review subset (~few hundred reviews)
```

### Output

A sampled subset of reviews used **exclusively** for theme generation in Stage 3. The full corpus is still preserved for Stage 4 classification.

---

## Stage 3 — Theme Generation (Groq)

### Objective

Discover the recurring themes present in the sampled reviews. The output is a structured list of theme labels and descriptions — not yet attached to any specific review.

### What "Theme" Means

- A theme is a **recurring user concern, complaint, or topic** mentioned across multiple reviews.
- Themes should be expressible in **1–3 words** (e.g., "Login Issues", "Nominee Updates", "Exit Load Confusion", "Withdrawal Delays").
- Target: **5–10 themes** per refresh cycle. Too few loses nuance; too many clutters the dashboard.

### LLM: Groq

| Aspect | Details |
|---|---|
| **LLM** | **Groq** — chosen for fast inference on the theme discovery task. |
| **Input** | The sampled review subset from Stage 2. |
| **Prompt** | Asks the LLM to identify recurring themes across the reviews. |
| **Output format** | Structured list: `{ theme_name, short_description, example_phrases }` per theme. |

### Post-processing

- **Deduplication**: Near-duplicate themes (e.g., "Login Problem" and "Login Issue") are merged into a single theme.
- **Validation**: Ensure 5–10 themes are produced. If too many, merge the most similar. If too few, lower the grouping threshold and re-run.

### Data Flow

```
Sampled reviews (Stage 2 output)
        │
        ▼
  Groq LLM — "identify recurring themes"
        │
        ▼
  Raw theme list: [{ theme_name, description, example_phrases }, ...]
        │
        ▼
  Deduplication + validation
        │
        ▼
  Finalized theme list (5–10 themes)
```

### Output

A finalized list of 5–10 themes, each with:

| Field | Description |
|---|---|
| `theme_name` | 1–3 word label (e.g., "Login Issues"). |
| `short_description` | One-sentence description of what this theme covers. |
| `example_phrases` | 2–3 example phrases that capture what belongs in this theme. |

---

## Stage 4 — Theme Classification + Sentiment Tagging (Gemini + Groq)

### Objective

Classify **every review** in the full corpus (not just the sample) into exactly one theme, and tag each review with a sentiment label. Reviews that don't fit any theme go into a catch-all `other` bucket.

### Two-step Classification

This stage combines two operations per review:

| Operation | LLM | Description |
|---|---|---|
| **Theme Classification** | **Gemini** | Assigns each review to one of the themes from Stage 3. Gemini is chosen for deeper reasoning accuracy in mapping reviews to the correct theme. |
| **Sentiment Tagging** | **Groq** | Tags each review as `negative`, `neutral`, or `positive`. Groq is chosen for fast inference on this simpler tagging task. |

### Classification Approach

- For each review, send the review content + the full list of themes (from Stage 3) to **Gemini**.
- Gemini returns the assigned `theme_name`.
- Reviews that are too vague or don't map to any theme → classified as `other`.

### Sentiment Tagging Approach

- Each review's content is sent to **Groq** for sentiment classification.
- Groq returns one of: `negative`, `neutral`, `positive`.

### Batching Optimization

Classifying every review one-by-one is slow. **Batching** is the recommended approach:
- Send **10 reviews per LLM call** with structured output.
- Reduces total LLM calls significantly and keeps latency manageable.

### Per-review Output Schema

| Field | Type | Description |
|---|---|---|
| `theme` | string | Assigned theme name (or `other`). |
| `sentiment` | enum | `negative` / `neutral` / `positive`. |
| `confidence` | float (optional) | Classification confidence score, for downstream filtering of low-confidence assignments. |

### Data Flow

```
Full review corpus (Stage 1 output) + Theme list (Stage 3 output)
        │
        ├──▶ Gemini — classify each review into a theme (batched)
        │
        ├──▶ Groq — tag sentiment per review (batched)
        │
        ▼
  Every review now carries: { theme, sentiment, confidence }
```

### Output

The complete review corpus with every review tagged with a `theme` and `sentiment` label.

---

## Stage 5 — Aggregate and Persist

### Objective

Roll up the classified reviews into the final Themes knowledge base format and persist it for downstream consumers.

### Aggregation Per Theme

For each discovered theme, compute:

| Metric | Description |
|---|---|
| **Total mention count** | Number of reviews classified into this theme. |
| **Per-source count** | Breakdown by Play Store vs App Store. |
| **Dominant sentiment** | The sentiment label that appears most often within this theme (negative / neutral / positive). |
| **Representative quotes** | Top 2–3 reviews whose content is clear, concise, and captures the theme well. Preference: reviews with upvotes/helpfulness signal if available, otherwise the longest non-trivial reviews. |
| **Actionable item** | One recommended next step generated by the LLM, given the theme and its representative quotes (e.g., "Investigate biometric login failures on latest Android build"). |

### Theme Knowledge Base Schema

```json
{
  "refresh_metadata": {
    "timestamp": "2025-03-15T10:30:00Z",
    "total_reviews_processed": 1247,
    "source_breakdown": {
      "playstore": 985,
      "appstore": 262
    }
  },
  "themes": [
    {
      "theme_name": "Login Issues",
      "short_description": "Users unable to log in, biometric failures, OTP not received",
      "sentiment": "negative",
      "total_mentions": 187,
      "playstore_mentions": 152,
      "appstore_mentions": 35,
      "representative_quotes": [
        "App keeps crashing when I try to log in with fingerprint...",
        "OTP never arrives, been trying for 3 days now..."
      ],
      "actionable_item": "Investigate biometric login failures on latest Android build"
    }
  ]
}
```

### Persistence Targets

| Target | Description |
|---|---|
| **Themes KB** (for Orchestrator Agent) | The orchestrator reads this at query time to check if an incoming query matches a known theme (Lane 1 — direct reply). |
| **Dashboard data store** (for Internal Dashboard) | The same theme data plus the per-review breakdown, so the dashboard can display themes, quotes, sentiment, and actionable items. |
| **Refresh metadata** | Timestamp, total reviews processed, source breakdown — displayed on the Internal Dashboard for ops visibility. |

### Data Flow

```
Classified reviews (Stage 4 output) + Theme list (Stage 3 output)
        │
        ▼
  Aggregate: counts, sentiment, quotes per theme
        │
        ▼
  Generate actionable items (LLM)
        │
        ▼
  ┌─────────────────────────────┐
  │    Themes Knowledge Base    │ ──▶ Orchestrator Agent (Phase 3, Lane 1)
  │    + Dashboard data store   │ ──▶ Internal Dashboard (Phase 8, Themes section)
  │    + Refresh metadata       │ ──▶ Internal Dashboard (Phase 8, status indicator)
  └─────────────────────────────┘
```

### Atomicity

- Consumers (Orchestrator, Dashboard) see either the **old themes** or the **new themes** — never a half-updated state.
- The write is atomic from the reader's perspective.

---

## End-to-end Pipeline Summary

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  STAGE 1: Fetch Reviews                                                          │
│  Play Store fetcher ──┐                                                          │
│                       ├──▶ Normalize + Merge + Deduplicate ──▶ Full corpus       │
│  App Store fetcher  ──┘                                                          │
│                                                                                  │
│  STAGE 2: Sample                                                                 │
│  Full corpus ──▶ Stratified sampling (bias low-rated, drop short) ──▶ Sample     │
│                                                                                  │
│  STAGE 3: Theme Generation (Groq)                                                │
│  Sample ──▶ Groq LLM ──▶ Deduplicate ──▶ 5–10 themes                            │
│                                                                                  │
│  STAGE 4: Classify + Tag (Gemini + Groq)                                         │
│  Full corpus + Themes ──▶ Gemini (classify) + Groq (sentiment) ──▶ Tagged corpus │
│                                                                                  │
│  STAGE 5: Aggregate + Persist                                                    │
│  Tagged corpus ──▶ Counts, quotes, actionable items ──▶ Themes KB + Dashboard    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Handling

| Scenario | Behaviour |
|---|---|
| **One source fails** (e.g., Play Store succeeds, App Store fails) | Pipeline continues with the working source. Logs the failure. Surfaces a warning on the Internal Dashboard. A partial refresh is better than no refresh. |
| **Entire fetch stage fails** | Existing Themes KB is left untouched. The system never replaces good data with empty data. |
| **Individual review classification fails** (e.g., LLM timeout) | That review is assigned to `other`. Does not block the rest of the pipeline. |
| **Atomicity** | Readers (Orchestrator, Dashboard) see either old themes or new themes — never a half-updated state. |

---

## Configuration

All values below are configurable (config file or environment variables), not hardcoded:

| Parameter | Default | Description |
|---|---|---|
| Play Store app ID | `com.nextbillion.groww` | Groww's Play Store package name. |
| App Store app ID | `1404871703` | Groww's App Store numeric ID. |
| Region code | `in` | Target region for review fetching. |
| Time window | 10 weeks | Rolling window — reviews older than this are excluded. |
| Theme count target | 5–10 | Desired number of output themes. |
| Sample size | ~few hundred | Number of reviews sampled for theme discovery. |
| Theme Generation LLM | **Groq** | LLM used for discovering themes from the sample. |
| Sentiment Tagging LLM | **Groq** | LLM used for tagging review sentiment. |
| Review Classification LLM | **Gemini** | LLM used for classifying reviews into themes. |
| Batch size (classification) | 10 | Reviews per LLM call during classification. |

---

## Downstream Consumers

| Consumer | What it reads | Phase |
|---|---|---|
| **Orchestrator Agent** | Themes KB — checks if an incoming query matches a known theme (Lane 1 early exit). | Phase 3 |
| **Internal Dashboard** | Themes + per-review breakdown + refresh metadata — displayed in the Themes section. | Phase 8 |
| **GitHub Actions Scheduler** | Invokes this pipeline on a cron schedule. | Phase 6 |

> This pipeline is **not** invoked at user-query time. It runs on demand or on a schedule. The Orchestrator and Dashboard simply read the latest persisted themes.
