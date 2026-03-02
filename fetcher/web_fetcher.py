import time
import logging
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from fetcher.base import BaseFetcher
from processor.models import FetchedContent
from config import config
from utils.rate_limiter import retry_with_backoff

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AIWeeklyBot/1.0; "
        "https://github.com/user/ai-weekly-pipeline)"
    )
}

_CONTENT_SELECTORS = ["article", "main", "[class*='content']", "[class*='post']"]
_BOILERPLATE_SELECTORS = [
    "nav", "footer", "header", "aside",
    ".sidebar", ".ads", ".comments",
    "script", "style",
]


class WebFetcher(BaseFetcher):
    def fetch(self, url: str) -> FetchedContent | None:
        response = retry_with_backoff(
            lambda: requests.get(url, headers=_HEADERS, timeout=20)
        )
        if response is None or response.status_code != 200:
            status = response.status_code if response else "error"
            logger.warning("HTTP %s for URL: %s", status, url)
            return None

        soup = BeautifulSoup(response.text, "lxml")
        title = _extract_title(soup)
        source_links = _extract_source_links(soup, url)
        body = _extract_body(soup)

        if not body or len(body.split()) < 100:
            logger.warning("Insufficient content extracted from: %s", url)
            return None

        published_date = _extract_published_date(soup)
        time.sleep(config.request_delay_seconds)

        return FetchedContent(
            url=url,
            source_type="web",
            raw_text=body,
            title=title,
            published_date=published_date,
            word_count=len(body.split()),
            source_links=source_links,
        )


def _extract_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else "Untitled"


def _extract_published_date(soup: BeautifulSoup) -> str:
    """
    Try to extract publication date from common meta tags and JSON-LD.
    Returns a YYYY-MM-DD string, or '' if not found.
    """
    import json as _json

    # Open Graph / article meta tags
    for prop in [
        "article:published_time",
        "og:article:published_time",
        "article:modified_time",
        "datePublished",
    ]:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return str(tag["content"])[:10]

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            if isinstance(data, dict):
                date = data.get("datePublished") or data.get("dateCreated")
                if date:
                    return str(date)[:10]
        except (_json.JSONDecodeError, AttributeError):
            pass

    return ""


_SOCIAL_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "linkedin.com",
    "instagram.com", "reddit.com", "youtube.com", "youtu.be",
    "t.co", "bit.ly", "lnkd.in", "buff.ly",
}

_SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}


def _extract_source_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """
    Extract up to 20 distinct external links from the page content,
    excluding nav/footer boilerplate, social sites, and image files.
    These are passed to Claude so it can identify the primary source.
    """
    page_host = urlparse(page_url).netloc.lower().lstrip("www.")
    seen: set[str] = set()
    links: list[str] = []

    # Search in content containers first, then fall back to whole page
    containers = [soup.select_one(sel) for sel in _CONTENT_SELECTORS]
    containers = [c for c in containers if c] or [soup]

    for container in containers:
        for a in container.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#"):
                continue
            abs_url = urljoin(page_url, href)
            parsed = urlparse(abs_url)
            if parsed.scheme not in ("http", "https"):
                continue
            host = parsed.netloc.lower().lstrip("www.")
            if host == page_host:
                continue  # same-site link
            if any(host == s or host.endswith("." + s) for s in _SOCIAL_DOMAINS):
                continue
            if any(parsed.path.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue
            if abs_url not in seen:
                seen.add(abs_url)
                links.append(abs_url)
            if len(links) >= 20:
                break
        if len(links) >= 20:
            break

    return links


def _extract_body(soup: BeautifulSoup) -> str:
    for sel in _BOILERPLATE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    for selector in _CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container:
            return container.get_text(separator=" ", strip=True)

    # Fallback: aggregate all paragraph text
    paragraphs = soup.find_all("p")
    return " ".join(p.get_text(strip=True) for p in paragraphs)
