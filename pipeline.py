"""
Main pipeline orchestration.

Run order:
  1. Determine the 7-day rolling date window
  2. Load the set of URLs already processed in previous runs
  3. Parse sources.txt (URL lines only; skip comments and plain text)
  4. For each source URL:
       - Resolve short-link redirects (lnkd.in etc.)
       - Expand YouTube channel URLs → individual video URLs filtered by date
       - Expand blog/newsletter homepages → individual article URLs via RSS
       - Treat everything else as a direct article / video URL
  5. Deduplicate against processed history
  6. For each novel URL: fetch → date-window check → AI filter → rewrite
  7. Render PDF + EPUB
  8. Persist processed URLs and run timestamp to state file
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import config
from fetcher.detector import detect_source_type, is_short_url, SourceType
from fetcher.youtube_fetcher import YouTubeFetcher
from fetcher.youtube_channel_expander import expand_channel_with_meta
from fetcher.web_fetcher import WebFetcher
from fetcher.arxiv_fetcher import ArXivFetcher
from fetcher.rss_expander import expand_feed_with_meta
from processor.selector import select_top_n
from processor.filter import is_ai_related
from processor.rewriter import rewrite_as_article
from processor.models import FetchedContent, Article
from renderer.pdf_renderer import render_pdf
from renderer.html_renderer import render_html
from sender.email_sender import send_report
from utils.state import get_window, get_processed_urls, save_run
import utils.token_budget as token_budget
from utils.token_budget import MIN_TOKENS_FOR_ARTICLE, MIN_TOKENS_FOR_REWRITE
import utils.article_cache as article_cache

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIWeeklyBot/1.0)"}

_FETCHER_MAP = {
    SourceType.YOUTUBE: YouTubeFetcher(),
    SourceType.ARXIV: ArXivFetcher(),
    SourceType.WEB: WebFetcher(),
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    logger.info("Pipeline started at %s", datetime.now().isoformat())
    budget = token_budget.reset(config.token_budget)
    cached_count, _ = article_cache.stats()
    logger.info("Article cache: %d article(s) available for reuse", cached_count)

    window_start, window_end = get_window()
    logger.info(
        "Date window: %s → %s",
        window_start.strftime("%Y-%m-%d"),
        window_end.strftime("%Y-%m-%d"),
    )

    processed_urls = get_processed_urls()
    logger.info("%d URL(s) already in history — will be skipped", len(processed_urls))

    raw_urls = _load_urls(config.sources_file)
    logger.info("Loaded %d URL(s) from %s", len(raw_urls), config.sources_file)

    # Phase 1: resolve short links + expand channels/feeds → (url, date_hint) pairs
    item_list = _expand_sources(raw_urls, window_start, window_end)

    # Phase 2: deduplicate against history — but cached articles always pass through
    novel_items = _deduplicate(item_list, processed_urls, skip_if_cached=True)
    logger.info("%d novel item(s) to process after deduplication", len(novel_items))

    if not novel_items:
        logger.info("Nothing new this week.")
        return

    # Phase 3: fetch → date filter → AI filter → rewrite
    articles: list[Article] = []
    newly_processed: list[str] = []

    for url, date_hint in novel_items:
        if not budget.can_afford(MIN_TOKENS_FOR_ARTICLE):
            logger.warning(
                "Token budget too low to process more articles "
                "(remaining=%d, need>=%d). Stopping early.",
                budget.remaining, MIN_TOKENS_FOR_ARTICLE,
            )
            break

        try:
            # Cache hit — reuse without spending any tokens
            cached = article_cache.get(url)
            if cached:
                logger.info("Cache hit — reusing article: '%s'", cached.title)
                articles.append(cached)
                newly_processed.append(url)
                continue

            content = _fetch(url)
            if content is None:
                continue

            # Use expansion-provided date if fetcher didn't populate one
            if date_hint and not content.published_date:
                content.published_date = date_hint

            # Drop content outside the 7-day window
            if not _is_within_window(content, window_start, window_end):
                logger.info(
                    "Skipped (outside window, published %s): %s",
                    content.published_date or "unknown",
                    url,
                )
                continue

            # Drop non-AI content
            if not is_ai_related(content):
                logger.info("Skipped (not AI-related): %s", url)
                # Still mark as processed so we don't re-evaluate next week
                newly_processed.append(url)
                continue

            article = rewrite_as_article(content)
            article_cache.put(url, article)
            articles.append(article)
            newly_processed.append(url)
            logger.info("Article ready: '%s'", article.title)

        except Exception as exc:
            logger.error("Failed to process %s: %s", url, exc, exc_info=True)

    budget.log_summary()

    if not articles:
        logger.warning("No AI-related articles found this week. No output generated.")
        save_run(newly_processed)
        return

    # Phase 4: render
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    datestamp = datetime.now().strftime("%Y-%m-%d")

    pdf_path = output_dir / f"ai-weekly-{datestamp}.pdf"
    html_path = output_dir / f"ai-weekly-{datestamp}.html"

    render_pdf(articles, str(pdf_path))
    render_html(articles, str(html_path))
    send_report(str(html_path))

    save_run(newly_processed)

    logger.info(
        "Done. %d article(s) compiled.\n  PDF:  %s\n  HTML: %s",
        len(articles), pdf_path, html_path,
    )


# ---------------------------------------------------------------------------
# Source expansion
# ---------------------------------------------------------------------------

def _expand_sources(
    urls: list[str],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[str, str]]:
    """
    Convert the raw list of source URLs into (article_url, date_hint) pairs.

    - Short links (lnkd.in etc.) are resolved to their final destination first.
    - YouTube channel URLs are expanded via RSS → individual video URLs in window.
    - Blog/newsletter homepages are expanded via RSS → individual article URLs in window.
    - Direct article/video/arXiv URLs are passed through as-is.
    """
    items: list[tuple[str, str]] = []

    for url in urls:
        try:
            # Resolve redirects for known shorteners
            if is_short_url(url):
                url = _resolve_redirect(url)

            source_type = detect_source_type(url)

            if source_type == SourceType.YOUTUBE_CHANNEL:
                candidates = expand_channel_with_meta(url, window_start, window_end)
                candidates = select_top_n(candidates)
                expanded = [(c["url"], c["date"]) for c in candidates]
                items.extend(expanded)
                logger.info("Channel %s → %d video(s)", url, len(expanded))

            elif source_type == SourceType.WEB_FEED:
                candidates = expand_feed_with_meta(url, window_start, window_end)
                if candidates:
                    candidates = select_top_n(candidates)
                    expanded = [(c["url"], c["date"]) for c in candidates]
                    items.extend(expanded)
                    logger.info("Feed %s → %d article(s)", url, len(expanded))
                else:
                    # Feed not found — try scraping the page directly
                    logger.debug("No RSS found for %s; queuing as direct URL", url)
                    items.append((url, ""))

            else:
                # YOUTUBE (single video), ARXIV, WEB (direct article)
                items.append((url, ""))

        except Exception as exc:
            logger.error("Failed to expand source %s: %s", url, exc)

    return items


def _resolve_redirect(url: str) -> str:
    """Follow HTTP redirects and return the final URL. Returns original on error."""
    try:
        resp = requests.head(url, headers=_HEADERS, allow_redirects=True, timeout=15)
        final = resp.url
        if final != url:
            logger.debug("Resolved %s → %s", url, final)
        return final
    except Exception as exc:
        logger.warning("Could not resolve redirect for %s: %s", url, exc)
        return url


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(
    items: list[tuple[str, str]],
    already_processed: set[str],
    skip_if_cached: bool = False,
) -> list[tuple[str, str]]:
    """
    Remove duplicates within the current batch and against processed history.
    When skip_if_cached=True, URLs that have a cached Article pass through
    regardless of processed history — so re-runs reuse cached content for free.
    """
    seen: set[str] = set(already_processed)
    result: list[tuple[str, str]] = []
    for url, date_hint in items:
        if url in seen:
            if skip_if_cached and article_cache.get(url) is not None:
                result.append((url, date_hint))  # cached — allow through
        else:
            seen.add(url)
            result.append((url, date_hint))
    return result


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch(url: str) -> FetchedContent | None:
    source_type = detect_source_type(url)
    fetcher = _FETCHER_MAP.get(source_type)
    if fetcher is None:
        logger.warning("No fetcher for type %s (URL: %s)", source_type, url)
        return None
    logger.info("Fetching [%s]: %s", source_type.value, url)
    return fetcher.fetch(url)


# ---------------------------------------------------------------------------
# Date window check
# ---------------------------------------------------------------------------

def _is_within_window(
    content: FetchedContent,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    """
    Return True if content falls within the date window.
    If no published_date is available, include the content (fail-open —
    the user manually curated the source list).
    """
    if not content.published_date:
        return True
    try:
        pub = datetime.fromisoformat(
            content.published_date[:10]  # normalise to YYYY-MM-DD
        )
        # Make timezone-aware for comparison
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return window_start <= pub <= window_end
    except ValueError:
        return True  # Unparseable date → include


# ---------------------------------------------------------------------------
# URL loading
# ---------------------------------------------------------------------------

def _load_urls(path: str) -> list[str]:
    """
    Read sources.txt and return only valid HTTP/HTTPS URLs.
    Skips blank lines, comment lines (#), and any plain text that isn't a URL.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        return [
            line.strip()
            for line in f
            if line.strip()
            and not line.strip().startswith("#")
            and line.strip().lower().startswith("http")
        ]
