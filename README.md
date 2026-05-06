# Investor Ops & Intelligence Suite

An advanced AI-powered platform designed to optimize investor operations, analyze user feedback, and provide intelligent customer support through conversational agents.

## 🏗 Architecture Overview

The project is structured into 5 decoupled microservices (3 backends and 2 frontends):

### Backend Services
- **Phase 1: Review Intelligence Pipeline** (`/backend/phase1_review_intelligence`)
  - A sophisticated data pipeline that scrapes app store reviews (Play Store/App Store).
  - Uses AI to cleanse data, discover emerging themes, and classify reviews with sentiment analysis.
  - Implements smart API key rotation, concurrent processing, and rate-limit handling using Groq and Gemini models.
- **Phase 2: Factsheet RAG System** (`/backend/phase2_factsheet_rag`)
  - A Retrieval-Augmented Generation (RAG) system for mutual fund factsheets.
  - Scrapes financial data and definitions, embeds them using Gemini, and stores them in ChromaDB.
  - Features an AI agent capable of accurately answering complex financial queries with exact source citations.
- **Phase 3: Orchestrator Agent** (`/backend/phase3_orchestrator`)
  - The central routing hub for user interactions.
  - Intelligently categorizes user intents (e.g., General Chat, Factsheet Inquiry, Calendar Booking).
  - Routes domain-specific questions to the Factsheet RAG system and handles conversational flows seamlessly.

### Frontend Applications
- **Internal Dashboard** (`/frontend/internal_dashboard`)
  - Built with Next.js & Tailwind CSS.
  - Provides administrators with real-time insights into Review Intelligence (themes, actionable items).
  - Allows manual triggering and monitoring of the background indexing pipelines (Review & RAG).
- **User Portal** (`/frontend/user_portal`)
  - Built with Vite & React.
  - A sleek chat interface for end-users to interact with the Orchestrator agent.
  - **Integrated Voice Agent:** Supports seamless voice interactions, allowing users to speak their queries naturally and receive spoken responses for a hands-free conversational experience.

## 💡 Business Value & Platform Synergy

To understand the full value of the suite, here is how the internal tools and user-facing applications connect to create a seamless operational ecosystem:

### 1. The Customer Support & Appointment Loop
- **User Portal (End-User):** An investor uses the chat interface to inquire about mutual funds. The Orchestrator agent answers Factsheet queries via the RAG system. If the user requests a human consultation, the Orchestrator detects the booking intent, extracts the required details, and securely schedules a meeting.
- **Internal Dashboard (Ops Team):** Operations managers instantly see these newly scheduled meetings on their calendar interface. Furthermore, admins can actively configure available time slots, block out dates, and manage capacity, ensuring the chatbot only offers valid, real-time availability to the users.

### 2. The Product Feedback Loop (Review Intelligence)
- **Data Intake:** The background pipeline automatically scrapes thousands of raw App Store and Play Store reviews.
- **Internal Dashboard:** Product managers use the "Review Pulse" dashboard to monitor AI-discovered themes (e.g., "App Crashes", "Hidden Charges"). The system goes a step further by translating these themes into prioritized *Actionable Items*.
- **Business Impact:** Instead of manually reading reviews, the team gets an immediate, data-driven backlog of what to fix or build next, directly tied to user sentiment.

### 3. The Knowledge Management Loop
- **Internal Dashboard (Admin):** Administrators can trigger complete knowledge base re-indexing (refreshing mutual fund factsheets or FAQs) with a single click. They can monitor the real-time progress of the Gemini embedding generation via live polling.
- **User Portal (End-User):** As soon as the Ops team successfully indexes new financial documents via the dashboard, the changes are instantly propagated. The Orchestrator chatbot immediately begins answering user queries using the newly updated, highly accurate knowledge base.

## 🛠 Tech Stack
- **Backend:** Python, FastAPI, Uvicorn, LangChain, ChromaDB
- **Frontend:** Next.js, React, Vite, Tailwind CSS
- **AI Models:** Groq (LLaMA-3), Google Gemini (Embeddings & Generation)
- **Scraping:** Google Play Scraper, App Store Scraper, BeautifulSoup

## 🚀 Getting Started

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- Valid API Keys for Groq and Google Gemini

### 1. Environment Setup
Create a `.env` file in the root directory based on `.env.sample`:
```bash
cp .env.sample .env
```
Populate the `.env` file with your respective API keys. The system utilizes multiple keys across phases to handle rate limits efficiently.

### 2. Install Dependencies
**Backend Services:**
Navigate to each backend phase and install the Python dependencies:
*(Assuming a virtual environment or global install)*
```bash
cd backend/phase1_review_intelligence
pip install -r requirements.txt
# Repeat for phase 2 and phase 3
```

**Frontend Services:**
Navigate to both frontend directories and install the NPM packages:
```bash
cd frontend/internal_dashboard
npm install
cd ../user_portal
npm install
```

### 3. Running the Suite
You need to run all 5 services concurrently. Open separate terminal instances for each:

**Phase 1 Backend (Port 8000)**
```bash
cd backend/phase1_review_intelligence
python api.py
```

**Phase 2 Backend (Port 8001)**
```bash
cd backend/phase2_factsheet_rag
python api.py
```

**Phase 3 Backend (Port 8002)**
```bash
cd backend/phase3_orchestrator
python api.py
```

**Internal Dashboard (Port 3000)**
```bash
cd frontend/internal_dashboard
npm run dev
```

**User Portal (Port 5173)**
```bash
cd frontend/user_portal
npm run dev
```
