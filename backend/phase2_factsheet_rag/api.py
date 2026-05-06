"""
Phase 2 — Factsheet RAG API Server

FastAPI server (port 8001) for managing factsheet & definition URLs
and triggering the offline indexing pipeline.
"""

import os
import json
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pipeline import run_indexing, load_json, save_json, FACTSHEET_URLS_FILE, DEFINITION_URLS_FILE, METADATA_FILE
from scraper import extract_scheme_name_from_url
from agent import run_faq_agent

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

app = FastAPI(title="Phase 2 — Factsheet RAG API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory status tracking
pipeline_status = {
    "factsheets": {"running": False, "progress": []},
    "definitions": {"running": False, "progress": []},
}


# ===== Request/Response Models =====

class FactsheetUrlEntry(BaseModel):
    url: str
    name: str | None = None

class DefinitionUrlEntry(BaseModel):
    url: str
    term: str

class UrlListUpdate(BaseModel):
    urls: list[dict]

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ===== Name Extraction =====

@app.get("/api/faqs/extract-name")
def extract_name(url: str):
    """Extract scheme name from a Groww factsheet URL."""
    name = extract_scheme_name_from_url(url)
    return {"name": name}


# ===== Factsheet URL Management =====

@app.get("/api/faqs/factsheets")
def get_factsheet_urls():
    """Get the factsheet URL list with per-URL status."""
    config = load_json(FACTSHEET_URLS_FILE)
    metadata = load_json(METADATA_FILE)
    return {
        "urls": config.get("urls", []),
        "indexing": metadata.get("factsheets", {"last_refreshed": None, "url_statuses": []}),
    }


@app.post("/api/faqs/factsheets")
def save_factsheet_urls(data: UrlListUpdate):
    """Save the factsheet URL list."""
    save_json(FACTSHEET_URLS_FILE, {"urls": data.urls})
    return {"message": "Factsheet URLs saved.", "count": len(data.urls)}


@app.post("/api/faqs/factsheets/add")
def add_factsheet_url(entry: FactsheetUrlEntry):
    """Add a single factsheet URL. Auto-extracts name from URL if not provided."""
    config = load_json(FACTSHEET_URLS_FILE)
    urls = config.get("urls", [])
    
    # Check for duplicates
    if any(u["url"] == entry.url for u in urls):
        raise HTTPException(status_code=400, detail="URL already exists.")
    
    name = entry.name or extract_scheme_name_from_url(entry.url)
    urls.append({"url": entry.url, "name": name})
    save_json(FACTSHEET_URLS_FILE, {"urls": urls})
    return {"message": "URL added.", "name": name, "urls": urls}


@app.delete("/api/faqs/factsheets")
def delete_factsheet_url(url: str):
    """Remove a factsheet URL."""
    config = load_json(FACTSHEET_URLS_FILE)
    urls = config.get("urls", [])
    urls = [u for u in urls if u["url"] != url]
    save_json(FACTSHEET_URLS_FILE, {"urls": urls})
    return {"message": "URL removed.", "urls": urls}


# ===== Definition URL Management =====

@app.get("/api/faqs/definitions")
def get_definition_urls():
    """Get the definitions URL list with per-URL status."""
    config = load_json(DEFINITION_URLS_FILE)
    metadata = load_json(METADATA_FILE)
    return {
        "urls": config.get("urls", []),
        "indexing": metadata.get("definitions", {"last_refreshed": None, "url_statuses": []}),
    }


@app.post("/api/faqs/definitions/add")
def add_definition_url(entry: DefinitionUrlEntry):
    """Add a single definition URL with its term name."""
    config = load_json(DEFINITION_URLS_FILE)
    urls = config.get("urls", [])
    
    if any(u["url"] == entry.url for u in urls):
        raise HTTPException(status_code=400, detail="URL already exists.")
    
    urls.append({"url": entry.url, "term": entry.term})
    save_json(DEFINITION_URLS_FILE, {"urls": urls})
    return {"message": "Definition URL added.", "urls": urls}


@app.delete("/api/faqs/definitions")
def delete_definition_url(url: str):
    """Remove a definition URL."""
    config = load_json(DEFINITION_URLS_FILE)
    urls = config.get("urls", [])
    urls = [u for u in urls if u["url"] != url]
    save_json(DEFINITION_URLS_FILE, {"urls": urls})
    return {"message": "URL removed.", "urls": urls}


# ===== Refresh (Indexing Pipeline) =====

@app.post("/api/faqs/factsheets/refresh")
def refresh_factsheets(background_tasks: BackgroundTasks):
    """Trigger factsheet indexing pipeline in the background."""
    if pipeline_status["factsheets"]["running"]:
        return {"message": "Factsheet pipeline is already running."}
    
    pipeline_status["factsheets"]["running"] = True
    pipeline_status["factsheets"]["progress"] = []
    
    def run():
        def on_progress(url, label, status, reason):
            pipeline_status["factsheets"]["progress"].append({
                "url": url, "label": label, "status": status, "failure_reason": reason
            })
        
        try:
            run_indexing("factsheets", progress_callback=on_progress)
        except Exception as e:
            print(f"Factsheet pipeline failed: {e}")
            pipeline_status["factsheets"]["progress"].append({
                "url": "", "label": "Pipeline Error", "status": "failed", "failure_reason": str(e)
            })
        finally:
            pipeline_status["factsheets"]["running"] = False
    
    background_tasks.add_task(run)
    return {"message": "Factsheet pipeline started."}


@app.post("/api/faqs/definitions/refresh")
def refresh_definitions(background_tasks: BackgroundTasks):
    """Trigger definitions indexing pipeline in the background."""
    if pipeline_status["definitions"]["running"]:
        return {"message": "Definitions pipeline is already running."}
    
    pipeline_status["definitions"]["running"] = True
    pipeline_status["definitions"]["progress"] = []
    
    def run():
        def on_progress(url, label, status, reason):
            pipeline_status["definitions"]["progress"].append({
                "url": url, "label": label, "status": status, "failure_reason": reason
            })
        
        try:
            run_indexing("definitions", progress_callback=on_progress)
        except Exception as e:
            print(f"Definitions pipeline failed: {e}")
            pipeline_status["definitions"]["progress"].append({
                "url": "", "label": "Pipeline Error", "status": "failed", "failure_reason": str(e)
            })
        finally:
            pipeline_status["definitions"]["running"] = False
    
    background_tasks.add_task(run)
    return {"message": "Definitions pipeline started."}


@app.get("/api/faqs/status")
def get_pipeline_status():
    """Returns the current pipeline status for both factsheets and definitions."""
    metadata = load_json(METADATA_FILE)
    return {
        "factsheets": {
            "running": pipeline_status["factsheets"]["running"],
            "progress": pipeline_status["factsheets"]["progress"],
            "last_refreshed": metadata.get("factsheets", {}).get("last_refreshed"),
            "url_statuses": metadata.get("factsheets", {}).get("url_statuses", []),
        },
        "definitions": {
            "running": pipeline_status["definitions"]["running"],
            "progress": pipeline_status["definitions"]["progress"],
            "last_refreshed": metadata.get("definitions", {}).get("last_refreshed"),
            "url_statuses": metadata.get("definitions", {}).get("url_statuses", []),
        },
    }


# ===== Online Retrieval Flow (Chat) =====

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    """
    Handles user chat messages for the FAQ agent.
    Executes the online retrieval flow.
    """
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]
    response = run_faq_agent(request.message, history_dicts)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
