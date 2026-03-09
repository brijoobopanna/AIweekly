"""
Tracks the last successful run timestamp and processed URLs to enable
incremental weekly processing — only content from the past 7 days is
considered, and URLs already included in a previous report are skipped.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

_STATE_FILE = Path(config.output_dir) / ".state.json"
_WINDOW_DAYS = 7
_MAX_PROCESSED_HISTORY = 1000  # Cap to prevent unbounded growth


def get_window() -> tuple[datetime, datetime]:
    """
    Returns (window_start, window_end) as UTC-aware datetimes.
    window_end   = now
    window_start = now - 7 days (fixed rolling window)
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=_WINDOW_DAYS)
    return window_start, now


def get_processed_urls() -> set[str]:
    """Return the set of URLs already included in a previous report."""
    return set(_load().get("processed_urls", []))


def save_run(newly_processed: list[str]) -> None:
    """
    Persist the current run timestamp and merge newly processed URLs
    into the history. Trims history to _MAX_PROCESSED_HISTORY entries.
    """
    state = _load()
    existing = list(state.get("processed_urls", []))
    combined = existing + [u for u in newly_processed if u not in set(existing)]
    # Keep the most recent entries if we exceed the cap
    state["processed_urls"] = combined[-_MAX_PROCESSED_HISTORY:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save(state)
    logger.info(
        "State saved. Last run recorded. %d URL(s) in history.",
        len(state["processed_urls"]),
    )


def get_last_run() -> datetime | None:
    """Return the timestamp of the last successful run, or None."""
    raw = _load().get("last_run")
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
