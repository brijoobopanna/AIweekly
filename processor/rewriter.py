import re
import json
import logging
import html
from urllib.parse import urlparse
import markdown as md_lib
from processor.models import FetchedContent, Article
from processor.claude_client import call_claude

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = """
You are a sharp, concise AI newsletter editor. Your job is to distill any AI topic
into a single, punchy paragraph that busy professionals can read in 20 seconds.

Every paragraph must cover exactly these four things in order:
1. What is this AI topic (one clear sentence)
2. Why it matters / how it impacts the reader
3. The key takeaway or learning
4. Nothing else — no fluff, no filler

Use plain, direct language. No jargon unless unavoidable. No bullet points. Pure prose.
Target length: 4–6 sentences max.
""".strip()

_REWRITE_USER_TEMPLATE = """
Summarise the following content into one concise paragraph.

SOURCE URL: {url}
SOURCE TYPE: {source_type}
ORIGINAL TITLE: {title}
AUTHORS/SPEAKERS: {authors}
PUBLISHED: {published}

RAW CONTENT:
{raw_text}

LINKS FOUND IN PAGE (pick the real primary source if one applies):
{source_links}

Output a JSON object with exactly these keys:
{{
  "title": "clear, descriptive headline (max 10 words)",
  "body_markdown": "single paragraph — what it is, why it matters, key takeaway",
  "primary_source_url": "the direct URL of the original source (paper/blog/repo/announcement), or the SOURCE URL if this is already the primary source",
  "tags": ["tag1", "tag2", "tag3"]
}}
""".strip()


def rewrite_as_article(content: FetchedContent) -> Article:
    source_links_str = (
        "\n".join(content.source_links[:15]) if content.source_links else "(none)"
    )
    user_msg = _REWRITE_USER_TEMPLATE.format(
        url=content.url,
        source_type=content.source_type,
        title=content.title,
        authors=", ".join(content.authors) if content.authors else "Unknown",
        published=content.published_date or "Unknown",
        raw_text=content.raw_text[:6000],
        source_links=source_links_str,
    )

    response = call_claude(
        system_prompt=_REWRITE_SYSTEM,
        user_message=user_msg,
        max_tokens=400,
        operation="rewrite",
    )

    if response is None:
        logger.warning("Rewrite failed for '%s' — using stub", content.url)
        return _stub_article(content)

    try:
        data = json.loads(_extract_json(response))
        body_html = md_lib.markdown(data["body_markdown"], extensions=["extra"])
        primary_url = data.get("primary_source_url") or content.url
        primary_url = _resolve_primary_url(primary_url, content)
        if primary_url != content.url:
            logger.info("Primary source identified: %s → %s", content.url, primary_url)
        return Article(
            title=data.get("title", content.title),
            subtitle="",
            body_html=body_html,
            body_markdown=data.get("body_markdown", ""),
            source_url=primary_url,
            source_type=content.source_type,
            tags=data.get("tags", []),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse rewrite response for '%s': %s", content.url, exc)
        return _stub_article(content)


def _resolve_primary_url(claude_url: str, content: FetchedContent) -> str:
    """
    If Claude returned the aggregator/fetched URL unchanged, try to find
    a better primary source from the extracted source_links.
    Falls back to content.url if nothing better is found.
    """
    fetched_host = urlparse(content.url).netloc.lower().lstrip("www.")
    claude_host = urlparse(claude_url).netloc.lower().lstrip("www.")

    # Claude found something different — trust it
    if claude_host and claude_host != fetched_host:
        return claude_url

    # Claude returned the aggregator URL — scan source_links for a real source
    for link in content.source_links:
        link_host = urlparse(link).netloc.lower().lstrip("www.")
        if link_host and link_host != fetched_host:
            return link

    return content.url


def _extract_json(text: str) -> str:
    """Extract JSON object from response, stripping code fences and prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    return match.group(0) if match else text


def _stub_article(content: FetchedContent) -> Article:
    excerpt = content.raw_text[:800]
    return Article(
        title=content.title or "Untitled Article",
        subtitle="",
        body_html=f"<p>{html.escape(excerpt)}</p>",
        body_markdown=excerpt,
        source_url=content.url,
        source_type=content.source_type,
    )
