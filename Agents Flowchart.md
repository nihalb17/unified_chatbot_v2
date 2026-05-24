# Multi-Agent Interactions & Flowchart

This document details the multi-agent architecture, state transitions, and inter-service communications of the **Investor Ops & Intelligence Suite**.

The system operates as a **decoupled multi-service ecosystem** powered by a central **LangGraph Orchestrator (Phase 3)**, a **Review Intelligence Pipeline (Phase 1)**, a **Semantic Factsheet RAG Agent (Phase 2)**, a **Voice Streaming Agent (Phase 5)**, and a **Google Workspace Integration Layer**.

---

## High-Level System Architecture

```mermaid
graph TD
    %% ─── Frontend ───
    UserPortal["🖥 User Portal\nReact / Vite · Port 5173"]
    AdminDash["🛠 Internal Dashboard\nNext.js 15 · Port 3000"]

    %% ─── Orchestrator ───
    Phase3["⚙️ Phase 3: Orchestrator Agent\nFastAPI · Port 8002"]
    LangGraph["🔀 LangGraph State Engine\n(detect_intent → generate_response)"]
    Phase5["🎙 Phase 5: Voice Agent\nSarvam AI WebSocket"]

    %% ─── Microservices ───
    Phase1["📊 Phase 1: Review Intelligence\nFastAPI · Port 8000"]
    Phase2["🗂 Phase 2: Factsheet RAG Agent\nFastAPI · Port 8001"]

    %% ─── Data Stores ───
    ThemesKB[("📄 themes_kb.json\nSynthesized Review Themes")]
    MeetingsLog[("📅 meetings_log.json\nAppointment Log")]
    ChromaDB[("🔷 ChromaDB\nVector Store")]
    FactsheetURLs[("🔗 factsheet_urls.json\nDefinition URLs")]

    %% ─── External LLM Providers ───
    Groq["🤖 Groq LLM\ngpt-oss-120b / llama-3.3-70b"]
    Gemini["✨ Google Gemini\nembedding-001"]

    %% ─── External APIs ───
    PlayStore["▶️ Google Play Store\nRSS Reviews API"]
    AppStore["🍎 Apple App Store\nRSS Reviews API"]
    GCalendar["📆 Google Calendar API\nOAuth2"]
    GDocs["📝 Google Docs API\nOAuth2"]
    Gmail["📧 Google Gmail\nOAuth2"]
    SarvamSTT["🎤 Sarvam AI STT\nsaaras:v3"]
    SarvamTTS["🔊 Sarvam AI TTS\nbulbul:v3"]

    %% ─── Frontend Connections ───
    UserPortal -->|"HTTP POST /api/chat"| Phase3
    UserPortal -->|"WebSocket /voice/ws"| Phase5
    AdminDash -->|"HTTP Polling & CRUD"| Phase1
    AdminDash -->|"HTTP Polling & Indexing"| Phase2
    AdminDash -->|"GET /api/system/status"| Phase3

    %% ─── Orchestrator Internal ───
    Phase3 --- LangGraph
    Phase3 --- Phase5

    %% ─── Orchestrator → Microservices ───
    LangGraph -->|"GET /api/reviews/themes"| Phase1
    LangGraph -->|"POST /api/chat"| Phase2
    LangGraph -->|"Slot Check & Event Create"| GCalendar
    LangGraph -->|"Meeting Notes Template"| GDocs
    LangGraph -->|"Booking Confirmation"| Gmail

    %% ─── Phase 1 Internal ───
    Phase1 -->|"Scrapes Reviews"| PlayStore
    Phase1 -->|"Scrapes Reviews"| AppStore
    Phase1 -->|"Theme Synthesis"| Groq
    Phase1 -->|"Writes Themes"| ThemesKB

    %% ─── Phase 2 Internal ───
    Phase2 -->|"Embeds Factsheets"| Gemini
    Phase2 -->|"Store / Retrieve Vectors"| ChromaDB
    Phase2 -->|"Query Understanding & Generation"| Groq
    Phase2 --- FactsheetURLs

    %% ─── Orchestrator LLM & Storage ───
    LangGraph -->|"Intent / Response Generation"| Groq
    LangGraph -->|"Writes Bookings"| MeetingsLog

    %% ─── Voice Pipeline ───
    Phase5 -->|"Audio → Text"| SarvamSTT
    Phase5 -->|"Text → Audio"| SarvamTTS
    Phase5 -->|"Processed Text Turn"| LangGraph
```

---

## LangGraph Orchestrator: Agent State Machine

The **Orchestrator Agent** manages the conversational state using a structured **LangGraph StateGraph**. Every user message starts at `detect_intent` and flows through conditional edges depending on intent, active dialogue flags, and conversation history.

```mermaid
flowchart TD
    START([📨 User Message Received]) --> detect_intent{🔀 detect_intent_node\nClassify Intent}

    %% ─── Intent Routing ───
    detect_intent -->|"intent = 'theme'"| check_theme[🔍 check_theme_node\nMatch Against themes_kb.json]
    detect_intent -->|"intent = 'faq'"| detect_escalation[😤 detect_escalation_node\nSentiment & Frustration Check]
    detect_intent -->|"intent = 'booking'"| collect_booking_topic[📋 collect_booking_topic_node\nExtract Meeting Topic]
    detect_intent -->|"intent = 'confirmation_pending'"| detect_confirmation[✅ detect_confirmation_response_node\nParse User Confirmation]
    detect_intent -->|"intent = 'slot_acceptance_pending'"| detect_slot_accept[🕐 detect_slot_acceptance_node\nParse Slot Acceptance]
    detect_intent -->|"intent = 'cancel_or_reschedule'"| generate_response[💬 generate_response_node]
    detect_intent -->|"intent = 'other'"| classify_out_of_scope[❓ classify_out_of_scope_node\nInvestment-Adjacent or Unrelated?]

    %% ─── Theme Branch ───
    check_theme -->|"Route: Matched Issue"| generate_response
    check_theme -->|"Route: Matched + Human Requested"| collect_booking_topic
    check_theme -->|"Route: Theme Miss"| detect_escalation

    %% ─── FAQ & Escalation Branch ───
    detect_escalation -->|"Escalated"| collect_booking_topic
    detect_escalation -->|"No Escalation"| rewrite_query[✏️ rewrite_query_node\nResolve Pronouns via History]
    rewrite_query --> call_faq[🗂 call_faq_agent_node\nHTTP POST → Phase 2 Port 8001]
    call_faq --> generate_response

    %% ─── Out-of-Scope Branch ───
    classify_out_of_scope -->|"Investment-Adjacent"| collect_booking_topic
    classify_out_of_scope -->|"Unrelated"| generate_response

    %% ─── Booking Pipeline ───
    collect_booking_topic --> collect_datetime[🗓 collect_booking_datetime_node\nExtract Date & Time]
    collect_datetime -->|"Incomplete Parameters"| generate_response
    collect_datetime -->|"Parameters Complete"| emit_booking[📤 emit_booking_request_node]
    emit_booking --> check_slot[📆 check_slot_availability_node\nQuery Google Calendar]
    check_slot -->|"Slot Available"| request_confirm[❓ request_final_confirmation_node\nAsk User to Confirm]
    check_slot -->|"Slot Unavailable"| suggest_alt[🔄 suggest_alternative_slot_node\nPropose Next Available Slot]
    request_confirm --> generate_response
    suggest_alt --> generate_response

    %% ─── Slot Acceptance ───
    detect_slot_accept -->|"Accepted Alternate"| request_confirm
    detect_slot_accept -->|"Rejected / Custom Slot"| generate_response

    %% ─── Confirmation Processing ───
    detect_confirmation -->|"Confirmed"| gen_booking_code[🔑 generate_booking_code_node\nCreate 4-Digit Code]
    detect_confirmation -->|"Change Slot"| check_slot
    detect_confirmation -->|"Change Topic"| collect_booking_topic
    detect_confirmation -->|"Exit / Cancel / Ambiguous"| generate_response

    %% ─── Booking Execution ───
    gen_booking_code --> execute_booking[🏁 execute_booking_node\nCalendar Event + Google Doc + Email]
    execute_booking --> close_chat[🔒 close_chat_node\nSet chat_closed = True]
    close_chat --> generate_response

    generate_response --> END([📤 Response Sent to User])
```

---

## Phase 2: Factsheet RAG Agent — Internal Pipeline

When `call_faq_agent_node` in the Orchestrator fires, it sends a request to Phase 2's `/api/chat` endpoint, which internally runs a **3-stage retrieval-augmented generation pipeline**.

```mermaid
flowchart TD
    IN([📥 FAQ Request from Orchestrator\nPOST /api/chat]) --> stage1

    subgraph stage1["Stage 1: Query Understanding (Groq)"]
        S1A["Detect vagueness in query"]
        S1B{"Is query\nvague?"}
        S1A --> S1B
        S1B -->|"Yes"| S1C["Return clarifying question"]
        S1B -->|"No"| S1D["Extract scheme name / concept"]
    end

    stage1 --> stage2

    subgraph stage2["Stage 2: Context Retrieval (ChromaDB + Gemini)"]
        S2A["Embed query via Gemini embedding-001"]
        S2B["Semantic search ChromaDB\ncollection: factsheet_kb"]
        S2C{"Relevant\nchunks found?"}
        S2A --> S2B --> S2C
        S2C -->|"No match"| S2D["Return refuse signal"]
        S2C -->|"Matched"| S2E["Filter + rank top chunks"]
    end

    stage2 --> stage3

    subgraph stage3["Stage 3: Grounded Generation (Groq llama-3.3-70b)"]
        S3A["Inject factsheet chunks as context"]
        S3B["LLM generates grounded answer"]
        S3C{"Answer\ngrounded?"}
        S3A --> S3B --> S3C
        S3C -->|"Data absent"| S3D["Return refuse signal\n(no hallucination)"]
        S3C -->|"Grounded answer"| S3E["Return answer + source links"]
    end

    S1C --> OUT
    S2D --> OUT
    S3D --> OUT_REFUSE
    S3E --> OUT

    OUT([✅ FAQ Response to Orchestrator\ntype: answer / clarify])
    OUT_REFUSE([🔴 Refuse Signal to Orchestrator\ntype: refuse → triggers booking offer])
```

---

## Phase 1: Review Intelligence Pipeline

Phase 1 runs as an **async background task** triggered via `POST /api/reviews/refresh`. The output (`themes_kb.json`) feeds directly into the Orchestrator's `check_theme_node`.

```mermaid
flowchart TD
    TRIGGER(["🔁 Trigger: POST /api/reviews/refresh\n(Dashboard or Orchestrator)"]) --> scrape

    subgraph scrape["Scraping (scraper.py)"]
        SC1["Fetch Google Play Store\nRSS reviews for com.nextbillion.groww"]
        SC2["Fetch Apple App Store\nRSS reviews for App ID 1404871703 (IN)"]
    end

    scrape --> preprocess["Deduplicate & clean reviews"]

    preprocess --> llm_analysis

    subgraph llm_analysis["Theme Synthesis (Groq)"]
        L1["Batch reviews per category\n(crash, payment, login, performance...)"]
        L2["LLM: Extract themes + severity + frequency"]
        L3["LLM: Sentiment classification per review"]
        L1 --> L2 --> L3
    end

    llm_analysis --> write["Write synthesized themes\n→ themes_kb.json"]
    write --> DONE(["✅ Phase 1 Complete\nThemes KB ready for Orchestrator"])
```

---

## Phase 5: Voice Agent Interaction

The Voice Agent wraps the same LangGraph turn logic in a **half-duplex WebSocket stream**. Each turn: audio in, text processing via Orchestrator, audio out.

```mermaid
sequenceDiagram
    actor User
    participant VP as User Portal\n(WebSocket Client)
    participant WS as Phase 5 WebSocket Handler\n(/voice/ws)
    participant STT as Sarvam AI STT\n(saaras:v3)
    participant Orch as LangGraph Orchestrator
    participant TTS as Sarvam AI TTS\n(bulbul:v3)

    User->>VP: Speaks into microphone
    VP->>WS: Stream audio chunks (binary)
    WS->>STT: Forward audio stream
    STT-->>WS: Transcript text
    WS->>Orch: POST /api/chat {message, history, session_id}
    Orch-->>WS: {text, type, chat_closed}
    WS->>TTS: Send response text
    TTS-->>WS: Stream audio (ritu voice, en-IN)
    WS-->>VP: Stream audio back to browser
    VP-->>User: Plays synthesized voice response
```

---

## Cross-Service Interaction Map

Summary of every HTTP call crossing service boundaries:

| Caller | Direction | Target | Endpoint | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| LangGraph (Phase 3) | → | Phase 1 (8000) | `GET /api/reviews/themes` | Load theme KB for intent routing |
| LangGraph (Phase 3) | → | Phase 1 (8000) | `GET /api/reviews/status` | Check scraping pipeline status |
| LangGraph (Phase 3) | → | Phase 1 (8000) | `POST /api/reviews/refresh` | Trigger review re-scrape |
| LangGraph (Phase 3) | → | Phase 2 (8001) | `POST /api/chat` | Run FAQ retrieval (call_faq_agent) |
| LangGraph (Phase 3) | → | Phase 2 (8001) | `GET /api/faqs/status` | Check indexing status |
| LangGraph (Phase 3) | → | Phase 2 (8001) | `POST /api/faqs/factsheets/refresh` | Trigger factsheet re-index |
| LangGraph (Phase 3) | → | Phase 2 (8001) | `POST /api/faqs/definitions/refresh` | Trigger definitions re-index |
| LangGraph (Phase 3) | → | Google Calendar | OAuth2 REST | Check slot availability / create event |
| LangGraph (Phase 3) | → | Google Docs | OAuth2 REST | Create meeting notes document |
| LangGraph (Phase 3) | → | Google Gmail | OAuth2 REST | Send booking confirmation email |
| Dashboard (Port 3000) | → | Phase 1 (8000) | `GET /api/reviews/themes` | Display Review Pulse page |
| Dashboard (Port 3000) | → | Phase 2 (8001) | `GET/POST /api/faqs/*` | Manage factsheet/definition URLs |
| Dashboard (Port 3000) | → | Phase 3 (8002) | `GET /api/system/status` | Auto-refresh readiness indicator |
| Dashboard (Port 3000) | → | Phase 3 (8002) | `GET /api/appointments` | Display booking log |
| User Portal (Port 5173) | → | Phase 3 (8002) | `POST /api/chat` | Chat turns |
| User Portal (Port 5173) | → | Phase 3 (8002) | `WS /voice/ws` | Voice streaming |

---

## Session State Persistence

The multi-agent network is stateless at the REST/WebSocket layer. Continuity across turns is maintained by serializing `OrchestratorState` on every message exchange.

| Session Variable | Type | Purpose |
| :--- | :--- | :--- |
| `last_intent` | `String` | Tracks the conversational track of the previous turn for interception logic |
| `current_scheme` | `String / Null` | Persists the mutual fund scheme under discussion for pronoun resolution |
| `current_concept` | `String / Null` | Persists the glossary term or concept in scope |
| `in_flight_booking` | `Dict` | Captures booking values: `{"topic": str, "date": str, "time": str}` |
| `active_path` | `String` | Tracks deep sub-states: `awaiting_confirmation`, `slot_available`, `slot_rejected` |
| `pending_booking_offer` | `Boolean` | If `true`, short affirmations route directly to the booking pipeline |
| `escalation_triggered` | `Boolean` | Bypasses FAQ logic and forces booking pipeline entry (resets each turn) |
| `faq_response` | `Dict / Null` | Holds the Phase 2 response for `generate_response_node` to consume |
| `booking_code` | `String / Null` | The 4-digit booking reference once generated |
| `chat_closed` | `Boolean` | Signals the frontend to disable input after a successful booking |
