"""
Phase 2 — Indexing Pipeline

Orchestrates the full offline indexing flow:
  Stage 1: Fetch content (scrape factsheets + definitions)
  Stage 2: Structure and chunk
  Stage 3: Embed and index into ChromaDB
  Stage 4: Persist indexing metadata (per-URL status)
"""

import os
import json
from datetime import datetime, timezone
from scraper import scrape_factsheet, scrape_definition
from embedder import embed_and_index

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
FACTSHEET_URLS_FILE = os.path.join(CONFIG_DIR, "factsheet_urls.json")
DEFINITION_URLS_FILE = os.path.join(CONFIG_DIR, "definition_urls.json")
METADATA_FILE = os.path.join(CONFIG_DIR, "indexing_metadata.json")


def load_json(path: str) -> dict:
    """Load a JSON config file."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict):
    """Save data to a JSON config file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_indexing(url_type: str, api_key: str = None, progress_callback=None):
    """
    Run the offline indexing pipeline.
    
    Args:
        url_type: "factsheets", "definitions", or "both"
        api_key: Optional Gemini API key (now ignored, using local embeddings)
        progress_callback: Optional callback(url, label, status, reason) for real-time updates
    """
    print(f"\n{'='*60}")
    print(f"  Phase 2 Indexing Pipeline — {url_type.upper()}")
    print(f"{'='*60}")
    
    metadata = load_json(METADATA_FILE)
    factsheet_records = []
    definition_records = []
    factsheet_statuses = metadata.get("factsheets", {}).get("url_statuses", [])
    definition_statuses = metadata.get("definitions", {}).get("url_statuses", [])
    
    # ===== STAGE 1: Fetch content =====
    print("\n[Stage 1/4] Fetching content...")
    
    if url_type in ("factsheets", "both"):
        fs_config = load_json(FACTSHEET_URLS_FILE)
        fs_urls = fs_config.get("urls", [])
        factsheet_statuses = []
        
        for entry in fs_urls:
            url = entry["url"]
            label = entry.get("name", url)
            
            record = scrape_factsheet(url)
            factsheet_records.append(record)
            
            status_entry = {
                "url": url,
                "label": label,
                "status": "success" if record else "failed",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "failure_reason": None if record else "Failed to scrape or parse page",
                "fields_extracted": len(record["fields"]) if record else 0,
            }
            factsheet_statuses.append(status_entry)
            
            if progress_callback:
                progress_callback(url, label, status_entry["status"], status_entry["failure_reason"])
        
        print(f"  Factsheets: {sum(1 for r in factsheet_records if r)} / {len(fs_urls)} successful")
    
    if url_type in ("definitions", "both"):
        def_config = load_json(DEFINITION_URLS_FILE)
        def_urls = def_config.get("urls", [])
        definition_statuses = []
        
        for entry in def_urls:
            url = entry["url"]
            term = entry["term"]
            
            record = scrape_definition(url, term)
            definition_records.append(record)
            
            status_entry = {
                "url": url,
                "label": term,
                "status": "success" if record else "failed",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "failure_reason": None if record else "Failed to scrape or parse definition",
            }
            definition_statuses.append(status_entry)
            
            if progress_callback:
                progress_callback(url, term, status_entry["status"], status_entry["failure_reason"])
        
        print(f"  Definitions: {sum(1 for r in definition_records if r)} / {len(def_urls)} successful")
    
    # ===== STAGE 2 & 3: Structure, chunk, embed, index =====
    print("\n[Stage 2-3/4] Structuring, embedding, and indexing...")
    
    # Filter out None records for embedding
    valid_fs = [r for r in factsheet_records if r is not None]
    valid_def = [r for r in definition_records if r is not None]
    
    if valid_fs or valid_def:
        embed_and_index(valid_fs, valid_def, api_key, url_type)
    else:
        print("  No valid records to index.")
    
    # ===== STAGE 4: Persist indexing metadata =====
    print("\n[Stage 4/4] Persisting indexing metadata...")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if url_type in ("factsheets", "both"):
        metadata["factsheets"] = {
            "last_refreshed": now,
            "url_statuses": factsheet_statuses,
        }
    
    if url_type in ("definitions", "both"):
        metadata["definitions"] = {
            "last_refreshed": now,
            "url_statuses": definition_statuses,
        }
    
    save_json(METADATA_FILE, metadata)
    
    print(f"\n{'='*60}")
    print(f"  Pipeline completed at {now}")
    print(f"{'='*60}\n")
if __name__ == "__main__":
    run_indexing("both")
