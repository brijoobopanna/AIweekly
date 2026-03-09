"""
Local article cache — persists processed Article objects to disk so that
re-running the pipeline on the same day does not re-spend tokens on articles
that have already been filtered, rewritten, and approved.

Cache is stored in output/.article_cache.json.
Each entry is keyed by the original fetch URL and contains the full Article
dataclass serialised as a dict.

Cache never expires automatically; entries are only evicted when the
output directory is cleared or when explicitly removed.
"""
import json
import logging
from dataclasses import asdict
from pathlib import Path

from config import config
from processor.models import Article

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(config.output_dir) / ".article_cache.json"


def get(url: str) -> Article | None:
    """Return a cached Article for the given URL, or None if not cached."""
    store = _load()
    entry = store.get(url)
    if entry is None:
        return None
    try:
        return Article(**entry)
    except (TypeError, KeyError) as exc:
        logger.warning("Corrupt cache entry for %s (%s) — ignoring", url, exc)
        return None


def put(url: str, article: Article) -> None:
    """Persist an Article to the cache under the given URL key."""
    store = _load()
    store[url] = asdict(article)
    _save(store)


def stats() -> tuple[int, list[str]]:
    """Return (count, list_of_cached_urls)."""
    store = _load()
    return len(store), list(store.keys())


def _load() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read article cache (%s) — starting fresh", exc)
    return {}


def _save(store: dict) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
