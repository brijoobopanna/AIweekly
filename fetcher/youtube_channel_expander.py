"""
Expands a YouTube channel URL into a list of individual video URLs
published within the given date window, using YouTube's public RSS feed
(no API key required).

Flow:
  channel URL  →  scrape page for channel ID
               →  fetch RSS feed (export.arxiv.org equivalent for YouTube)
               →  filter entries by published date
               →  return [(video_url, published_date_iso), ...]
"""
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIWeeklyBot/1.0)"}
_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

_CHANNEL_URL_PATTERNS = [
    r"youtube\.com/@[\w.-]+(?:/videos)?/?$",
    r"youtube\.com/channel/(UC[\w-]+)(?:/videos)?/?$",
    r"youtube\.com/user/[\w.-]+(?:/videos)?/?$",
    r"youtube\.com/c/[\w.-]+(?:/videos)?/?$",
]

_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def is_channel_url(url: str) -> bool:
    """Return True if the URL points to a YouTube channel, not a single video."""
    return any(re.search(p, url, re.IGNORECASE) for p in _CHANNEL_URL_PATTERNS)


def expand_channel(
    url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[str, str]]:
    """
    Returns a list of (video_url, published_date_iso_str) tuples for videos
    published within [window_start, window_end].
    Returns an empty list on any failure.
    """
    items = expand_channel_with_meta(url, window_start, window_end)
    return [(item["url"], item["date"]) for item in items]


def expand_channel_with_meta(
    url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """
    Returns a list of dicts with keys: url, date, title, summary.
    Returns an empty list on any failure.
    """
    channel_id = _resolve_channel_id(url)
    if not channel_id:
        logger.warning("Could not resolve channel ID for: %s", url)
        return []

    rss_url = _RSS_URL.format(channel_id=channel_id)
    try:
        resp = requests.get(rss_url, headers=_HEADERS, timeout=20)
    except Exception as exc:
        logger.error("Failed to fetch channel RSS for %s: %s", url, exc)
        return []

    if resp.status_code != 200:
        logger.warning("RSS feed HTTP %s for channel: %s", resp.status_code, channel_id)
        return []

    results = _parse_rss(resp.text, window_start, window_end)
    logger.info("Channel %s: %d video(s) in window", channel_id, len(results))
    return results


def _resolve_channel_id(url: str) -> str | None:
    """
    Scrape the channel page to extract the YouTube channel ID (UC…).
    Tries two strategies:
      1. JSON key "channelId" embedded in the page source
      2. Canonical link containing /channel/UC...
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        # Strategy 1: look for "channelId":"UC..."
        m = re.search(r'"channelId"\s*:\s*"(UC[\w-]+)"', resp.text)
        if m:
            return m.group(1)
        # Strategy 2: /channel/UC... anywhere in the HTML
        m = re.search(r'youtube\.com/channel/(UC[\w-]+)', resp.text)
        if m:
            return m.group(1)
    except Exception as exc:
        logger.error("Failed to resolve channel ID for %s: %s", url, exc)
    return None


def _parse_rss(
    xml_text: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """Parse YouTube Atom RSS feed and return videos within the date window as dicts."""
    results = []
    try:
        root = ET.fromstring(xml_text)
        for entry in root.findall("atom:entry", _ATOM_NS):
            video_id_el = entry.find("yt:videoId", _ATOM_NS)
            published_el = entry.find("atom:published", _ATOM_NS)
            title_el = entry.find("atom:title", _ATOM_NS)
            desc_el = entry.find("media:group/media:description", _ATOM_NS)

            if video_id_el is None or published_el is None:
                continue

            published_str = published_el.text.strip()
            published_dt = datetime.fromisoformat(
                published_str.replace("Z", "+00:00")
            )
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)

            if window_start <= published_dt <= window_end:
                video_url = f"https://www.youtube.com/watch?v={video_id_el.text}"
                results.append({
                    "url": video_url,
                    "date": published_str[:10],
                    "title": (title_el.text or "").strip() if title_el is not None else "",
                    "summary": (desc_el.text or "").strip()[:300] if desc_el is not None else "",
                })
    except ET.ParseError as exc:
        logger.error("Failed to parse YouTube RSS XML: %s", exc)
    return results
