"""
Phase 4 — Meetings Log Store

Local JSON file store for booked appointments.
This is the source of truth for the internal dashboard's
Scheduled Appointments menu.

All dates/times are stored in IST as the user provided them.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

logger = logging.getLogger(__name__)

# Default path relative to project root
_DEFAULT_LOG_PATH = os.path.join(os.path.dirname(__file__), "../data/meetings_log.json")


def _get_log_path() -> str:
    """Resolve the meetings log file path from env or default."""
    env_path = os.getenv("MEETINGS_LOG_PATH", "")
    if env_path and os.path.isabs(env_path):
        return env_path
    # Relative path — resolve from project root
    project_root = os.path.join(os.path.dirname(__file__), "../..")
    return os.path.join(project_root, env_path or "backend/data/meetings_log.json")


def load_log() -> List[Dict[str, Any]]:
    """Load the full meetings log from disk.

    Returns an empty list if the file doesn't exist or is invalid.
    """
    path = _get_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load meetings log: {e}")
        return []


def _save_log(entries: List[Dict[str, Any]]) -> None:
    """Atomically write the full log to disk (write to temp, then rename)."""
    path = _get_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Atomic write: write to temp file in same dir, then rename
    dir_name = os.path.dirname(path)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        # On Windows, need to remove dest first if it exists
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp_path, path)
    except Exception as e:
        logger.error(f"Failed to save meetings log: {e}")
        # Clean up temp file if rename failed
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def append_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Append a new entry to the meetings log.

    Args:
        entry: Dict with booking details.

    Returns:
        The updated full log list.
    """
    entries = load_log()

    # Ensure created_at is set
    if "created_at" not in entry:
        entry["created_at"] = datetime.now().isoformat()

    entries.append(entry)
    _save_log(entries)
    logger.info(f"Appended booking #{entry.get('booking_code')} to meetings log")
    return entries


def find_by_code(booking_code: str) -> Optional[Dict[str, Any]]:
    """Find an entry by its 4-digit booking code.

    Returns the entry dict or None.
    """
    for entry in load_log():
        if entry.get("booking_code") == booking_code:
            return entry
    return None


def code_exists(booking_code: str) -> bool:
    """Check if a booking code already exists in the log."""
    return find_by_code(booking_code) is not None


def search_appointments(query: str) -> List[Dict[str, Any]]:
    """Search appointments by booking code or topic.

    Args:
        query: Search string (partial match on booking code or topic).

    Returns:
        List of matching entries.
    """
    query_lower = query.lower()
    results = []
    for entry in load_log():
        code = entry.get("booking_code", "").lower()
        topic = entry.get("topic", "").lower()
        if query_lower in code or query_lower in topic:
            results.append(entry)
    return results
