import re
from enum import Enum
from urllib.parse import urlparse


class SourceType(Enum):
    YOUTUBE = "youtube"           # Single video URL
    YOUTUBE_CHANNEL = "youtube_channel"  # Channel / user page → needs expansion
    ARXIV = "arxiv"
    WEB_FEED = "web_feed"         # Blog/newsletter homepage → needs RSS expansion
    WEB = "web"                   # Direct article URL → scrape directly


_YOUTUBE_VIDEO_PATTERNS = [
    r"(?:youtube\.com/watch\?.*v=|youtu\.be/)[\w-]+",
    r"youtube\.com/shorts/[\w-]+",
    r"youtube\.com/embed/[\w-]+",
]

_YOUTUBE_CHANNEL_PATTERNS = [
    r"youtube\.com/@[\w.-]+(?:/videos)?/?$",
    r"youtube\.com/channel/UC[\w-]+(?:/videos)?/?$",
    r"youtube\.com/user/[\w.-]+(?:/videos)?/?$",
    r"youtube\.com/c/[\w.-]+(?:/videos)?/?$",
]

_ARXIV_PATTERNS = [
    r"arxiv\.org/(?:abs|pdf|html)/[\d.]+",
]

# Known URL shorteners whose final destination is unknown until resolved
_SHORT_URL_DOMAINS = {"lnkd.in", "bit.ly", "t.co", "tinyurl.com", "ow.ly", "buff.ly"}


def detect_source_type(url: str) -> SourceType:
    """
    Classify a URL. Priority: YouTube video > YouTube channel > arXiv > web feed > web.
    """
    for pattern in _YOUTUBE_VIDEO_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return SourceType.YOUTUBE
    for pattern in _YOUTUBE_CHANNEL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return SourceType.YOUTUBE_CHANNEL
    for pattern in _ARXIV_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return SourceType.ARXIV
    if _is_feed_url(url):
        return SourceType.WEB_FEED
    return SourceType.WEB


def is_short_url(url: str) -> bool:
    """Return True if the URL is from a known link-shortener service."""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return host in _SHORT_URL_DOMAINS
    except Exception:
        return False


def _is_feed_url(url: str) -> bool:
    """
    Heuristic: a URL is a feed/homepage if it has no deep path.
    Direct article URLs typically have slugs like /posts/my-article-title.
    """
    try:
        path = urlparse(url).path.rstrip("/")
    except Exception:
        return False
    if not path:
        return True
    feed_endings = ("/feed", "/rss", "/atom", "/feed.xml", "/rss.xml", "/atom.xml")
    return path.endswith(feed_endings)


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from any YouTube URL variant."""
    patterns = [
        r"[?&]v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"shorts/([\w-]{11})",
        r"embed/([\w-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def extract_arxiv_id(url: str) -> str | None:
    """Extract arXiv paper ID (e.g. '2401.12345' or '2401.12345v2')."""
    m = re.search(r"(?:abs|pdf|html)/([\d.]+(?:v\d+)?)", url)
    return m.group(1) if m else None
