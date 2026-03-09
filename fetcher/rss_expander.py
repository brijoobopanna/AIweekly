"""
Expands a blog / newsletter homepage (or explicit feed URL) into a list
of individual article URLs published within the given date window.

Supports both RSS 2.0 and Atom 1.0 feed formats.

Feed discovery order:
  1. The URL itself (if it already is a feed)
  2. {url}/feed
  3. {url}/rss
  4. {url}/atom.xml
  5. {url}/feed.xml
  6. {url}/rss.xml

Returns [] if no feed is found or no items fall within the window.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIWeeklyBot/1.0)"}

_FEED_SUFFIXES = ["", "/feed", "/rss", "/atom.xml", "/feed.xml", "/rss.xml"]

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Regex to sniff whether response body looks like an XML feed
_FEED_SNIFF_RE = re.compile(
    r"<(rss|feed|channel)\b", re.IGNORECASE
)


def is_feed_url(url: str) -> bool:
    """
    Return True for URLs that look like feed homepages rather than
    specific article pages. Heuristic: the path is empty or very shallow.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return True
    # Explicit feed path suffixes
    feed_endings = ("/feed", "/rss", "/atom", "/feed.xml", "/rss.xml", "/atom.xml")
    return path.endswith(feed_endings)


def expand_feed(
    url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[str, str]]:
    """
    Returns a list of (article_url, published_date_iso_str) tuples for
    articles published within [window_start, window_end].
    Returns [] on failure or when no items fall in the window.
    """
    items = expand_feed_with_meta(url, window_start, window_end)
    return [(item["url"], item["date"]) for item in items]


def expand_feed_with_meta(
    url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """
    Returns a list of dicts with keys: url, date, title, summary.
    Returns [] on failure or when no items fall in the window.
    """
    feed_text, feed_url = _discover_feed(url)
    if not feed_text:
        logger.warning("No RSS/Atom feed found for: %s", url)
        return []

    results = _parse_feed_with_meta(feed_text, window_start, window_end)
    logger.info("Feed %s: %d article(s) in window", feed_url, len(results))
    return results


def _discover_feed(base_url: str) -> tuple[str | None, str | None]:
    """
    Try common feed URL patterns. Return (feed_text, feed_url) for the
    first URL that responds with recognisable XML feed content.
    """
    # Normalise base: strip trailing slash
    base = base_url.rstrip("/")

    for suffix in _FEED_SUFFIXES:
        candidate = base + suffix
        try:
            resp = requests.get(candidate, headers=_HEADERS, timeout=20)
            if resp.status_code == 200 and _FEED_SNIFF_RE.search(resp.text[:500]):
                logger.debug("Feed found at: %s", candidate)
                return resp.text, candidate
        except Exception:
            continue
    return None, None


def _parse_feed(xml_text: str, window_start: datetime, window_end: datetime) -> list[tuple[str, str]]:
    items = _parse_feed_with_meta(xml_text, window_start, window_end)
    return [(item["url"], item["date"]) for item in items]


def _parse_feed_with_meta(xml_text: str, window_start: datetime, window_end: datetime) -> list[dict]:
    """
    Parse either an RSS 2.0 or Atom 1.0 feed and return items within
    the date window as dicts with url, date, title, summary.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("Failed to parse feed XML: %s", exc)
        return []

    tag = root.tag.lower()

    if "rss" in tag or root.find("channel") is not None:
        return _parse_rss2(root, window_start, window_end)
    elif "feed" in tag:
        return _parse_atom(root, window_start, window_end)
    else:
        logger.warning("Unrecognised feed root element: %s", root.tag)
        return []


def _parse_rss2(root: ET.Element, window_start: datetime, window_end: datetime) -> list[dict]:
    """Parse RSS 2.0 <channel><item> structure."""
    results = []
    channel = root.find("channel") or root
    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        pub_date_str = item.findtext("pubDate", "").strip()
        title = item.findtext("title", "").strip()
        summary = item.findtext("description", "").strip()[:300]
        if not link:
            continue
        pub_dt = _parse_rss_date(pub_date_str)
        if pub_dt and window_start <= pub_dt <= window_end:
            results.append({"url": link, "date": pub_dt.strftime("%Y-%m-%d"), "title": title, "summary": summary})
        elif pub_dt is None:
            results.append({"url": link, "date": "", "title": title, "summary": summary})
    return results


def _parse_atom(root: ET.Element, window_start: datetime, window_end: datetime) -> list[dict]:
    """Parse Atom 1.0 <feed><entry> structure."""
    results = []
    ns_match = re.match(r"\{([^}]+)\}", root.tag)
    ns = ns_match.group(1) if ns_match else ""
    ns_prefix = f"{{{ns}}}" if ns else ""

    for entry in root.findall(f"{ns_prefix}entry"):
        link_el = entry.find(f"{ns_prefix}link")
        if link_el is None:
            continue
        link = link_el.get("href") or link_el.text or ""
        link = link.strip()
        if not link:
            continue

        title_el = entry.find(f"{ns_prefix}title")
        title = (title_el.text or "").strip() if title_el is not None else ""

        summary_el = entry.find(f"{ns_prefix}summary") or entry.find(f"{ns_prefix}content")
        summary = (summary_el.text or "").strip()[:300] if summary_el is not None else ""

        published_el = (
            entry.find(f"{ns_prefix}published")
            or entry.find(f"{ns_prefix}updated")
        )
        pub_str = (published_el.text or "").strip() if published_el is not None else ""
        pub_dt = _parse_iso_date(pub_str)

        if pub_dt and window_start <= pub_dt <= window_end:
            results.append({"url": link, "date": pub_dt.strftime("%Y-%m-%d"), "title": title, "summary": summary})
        elif pub_dt is None:
            results.append({"url": link, "date": "", "title": title, "summary": summary})
    return results


def _parse_rss_date(date_str: str) -> datetime | None:
    """Parse RFC 2822 date string used in RSS 2.0 pubDate fields."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_iso_date(date_str: str) -> datetime | None:
    """Parse ISO 8601 date string used in Atom feeds."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
