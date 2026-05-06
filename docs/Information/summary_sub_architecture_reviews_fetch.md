# Sub-Architecture: App Reviews Fetch & Theme Classification

## Purpose

This subsystem is responsible for keeping the **Themes knowledge base** up to date. It is invoked whenever the ops team triggers a "Refresh review intelligence" action from the internal dashboard.

It performs four jobs end-to-end:

1. Fetches the latest Groww app reviews from both the **Google Play Store** and the **Apple App Store**, scoped to the **last 10 weeks**.
2. Takes a sizable sample of those reviews and discovers themes from them (theme generation).
3. Classifies every fetched review into one of the discovered themes (theme classification).
4. Writes the resulting themes — along with counts, sentiment, and representative quotes — to the Themes knowledge base that the orchestrator agent and the internal dashboard both read from.

---

## Inputs

- **Trigger** — manual invocation from the internal dashboard (refresh button), or an optional scheduled run.
- **Time window** — fixed at the **last 10 weeks** (rolling). Reviews older than 10 weeks are ignored.
- **App identifiers** — the Groww app ID on the Play Store and the Groww app ID on the App Store. These are configuration values, not user input.
- **Region** — India (`in`) for both stores, since Groww serves Indian investors.

## Outputs

- **Themes knowledge base** — refreshed with the latest themes derived from the new review batch.
- For each theme, the following is persisted:
  - Theme name (1–3 words, human-readable)
  - Sentiment tag (negative / mixed / positive)
  - Total mention count
  - Per-source mention count (Play Store vs App Store)
  - 2–3 representative review quotes (verbatim)
  - One actionable item recommended for the ops team
- **Refresh metadata** — timestamp of last refresh, total reviews processed, source breakdown.

---

## Pipeline stages

The subsystem runs as a sequential pipeline. Each stage produces input for the next.

### Stage 1 — Fetch reviews

Two parallel fetchers run, one per source. Each returns a list of review records normalized to a shared schema before being merged.

**Play Store fetcher**
- Pulls reviews for the Groww app from the Indian Play Store.
- Filters to reviews posted in the last 10 weeks.
- Sorted newest-first to avoid pulling more than necessary.

**App Store fetcher**
- Pulls reviews for the Groww app from the Indian App Store.
- Filters to reviews posted in the last 10 weeks.
- Apple's review API returns reviews in batches; the fetcher paginates until it hits the 10-week boundary.

**Normalized review schema**
Every fetched review (regardless of source) is mapped to:
- `review_id` — unique identifier within its source
- `source` — `playstore` or `appstore`
- `date` — when the review was posted
- `rating` — 1 to 5
- `title` — review title (may be empty for Play Store)
- `content` — the review body text
- `user_handle` — display name if available

**Output of Stage 1** — a single combined list of normalized reviews from both sources, deduplicated, dated within the 10-week window.

---

### Stage 2 — Sample for theme discovery

Theme discovery does not need every review — it needs a representative sample. Running clustering on every review is expensive and noisy.

**Sampling strategy**
- Take a sizable sample (target: a few hundred reviews) from the combined corpus.
- Stratify the sample so it reflects the source mix (e.g., if Play Store contributes 80% of total reviews, the sample is roughly 80% Play Store / 20% App Store).
- Bias the sample slightly toward lower-rated reviews (1, 2, 3 stars) since these are richer in actionable themes than 5-star praise.
- Drop reviews shorter than a meaningful threshold (e.g., under 5 words) — they don't carry theme signal.

**Output of Stage 2** — a sampled subset of reviews used purely for theme generation in Stage 3.

---

### Stage 3 — Theme generation

Discover the themes that exist in the sampled reviews. The output is a list of theme labels and short descriptions, not yet attached to any specific review.

**What "theme" means here**
- A theme is a recurring user concern, complaint, or topic mentioned across multiple reviews.
- Themes should be expressible in 1–3 words (e.g., "Login Issues", "Nominee Updates", "Exit Load Confusion", "Withdrawal Delays").
- Aim for roughly 5 to 10 themes per refresh cycle. Too few loses nuance; too many makes the dashboard cluttered.

**Approach**
- Pass the sampled reviews to an LLM with a prompt asking it to identify recurring themes.
- The LLM returns a structured list: `{ theme_name, short_description, example_phrases }`.
- A deduplication step merges near-duplicate themes (e.g., "Login Problem" and "Login Issue" become one).

**Output of Stage 3** — a finalized list of 5–10 themes, each with a name, description, and example phrases that capture what belongs in this theme.

---

### Stage 4 — Theme classification

Classify every review in the full corpus (not just the sample) into exactly one theme. Reviews that don't fit any theme go into a catch-all `other` bucket.

**Approach**
- For each review, send the review content + the list of themes (from Stage 3) to the classifier LLM.
- The LLM returns the assigned theme name and a sentiment tag for that specific review.
- Reviews that are too vague or don't map to any theme get classified as `other`.

**Per-review output**
- `theme` — assigned theme name
- `sentiment` — negative / neutral / positive
- `confidence` — optional, for downstream filtering of low-confidence assignments

**Performance note** — classifying every review one-by-one is slow. Batching (e.g., 10 reviews per LLM call with structured output) is the recommended optimization.

**Output of Stage 4** — every fetched review now carries a `theme` and `sentiment` tag.

---

### Stage 5 — Aggregate and persist

Roll up the classified reviews into the final Themes knowledge base format.

**For each theme, compute:**
- Total mention count.
- Mention count per source (Play Store vs App Store).
- Dominant sentiment (the sentiment label that appears most often within this theme).
- Top 2–3 representative quotes — pick reviews whose content is clear, concise, and capture the theme well. Prefer reviews that have at least one upvote/helpfulness signal where available, otherwise pick the longest non-trivial reviews.
- One actionable item — generated by the LLM given the theme and its representative quotes. This is the recommendation the ops team sees on the dashboard. Examples: "Investigate biometric login failures on latest Android build", "Add nominee-update FAQ at top of help center."

**Persistence**
- Write the aggregated themes to the Themes knowledge base used by the orchestrator agent.
- Write the same data (with the per-review breakdown preserved) to the data store backing the internal dashboard's Themes section.
- Update the refresh metadata: timestamp, total reviews processed, source breakdown.

---

## Failure handling

- If one source fails (e.g., Play Store fetch succeeds but App Store fetch fails), the pipeline should continue with the source that worked, log the failure, and surface a warning on the internal dashboard. A partial refresh is better than no refresh.
- If the entire fetch stage fails, the existing Themes knowledge base is left untouched. The system never replaces good data with empty data.
- Theme classification failures on individual reviews (e.g., LLM timeout) result in those reviews being assigned to `other`. They do not block the rest of the pipeline.
- A refresh run is atomic from the consumer's perspective — readers (the orchestrator and the dashboard) see either the old themes or the new themes, never a half-updated state.

---

## Configuration

The following values are configuration, not hardcoded:

- Play Store app ID for Groww
- App Store app ID for Groww
- Region code (`in`)
- Time window (default 10 weeks)
- Theme count target (default 5–10)
- Sample size for theme discovery
- LLM choice for theme generation and classification

These can live in a config file or environment variables.

---

## Where this subsystem fits in the larger product

This pipeline produces the data that powers two surfaces:

- The **orchestrator agent** uses the Themes knowledge base to decide whether an incoming user query matches a known issue (Lane 1 — known theme reply).
- The **internal dashboard** displays the themes with counts, representative reviews, and actionable items in its Themes section.

The pipeline is not invoked at user-query time. It is invoked on demand by the ops team via the dashboard, or on a schedule. The orchestrator and dashboard simply read the latest persisted themes — they never trigger the pipeline themselves.
