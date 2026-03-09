import json
import logging
from processor.models import FetchedContent
from processor.claude_client import call_claude

logger = logging.getLogger(__name__)

_FILTER_SYSTEM = """
You are a content relevance classifier for an AI-focused weekly newsletter.
Your sole job is to determine whether a piece of content is meaningfully
related to artificial intelligence, machine learning, large language models,
robotics controlled by AI, AI policy, or AI safety.

Respond with ONLY a JSON object in this exact format:
{"relevant": true, "confidence": 0.95, "reason": "one-sentence reason"}

Be strict: generic tech, software engineering without AI, and pure business
news without an AI angle should return {"relevant": false, ...}.
""".strip()

_FILTER_USER_TEMPLATE = """
Classify the following content:

TITLE: {title}
SOURCE TYPE: {source_type}

CONTENT EXCERPT (first 1500 words):
{excerpt}
""".strip()


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers Claude sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def is_ai_related(content: FetchedContent) -> bool:
    excerpt = " ".join(content.raw_text.split()[:1500])
    user_msg = _FILTER_USER_TEMPLATE.format(
        title=content.title,
        source_type=content.source_type,
        excerpt=excerpt,
    )

    response = call_claude(
        system_prompt=_FILTER_SYSTEM,
        user_message=user_msg,
        max_tokens=100,
        operation="filter",
    )

    if response is None:
        logger.warning("Filter call failed for '%s' — defaulting to include", content.url)
        return True  # Fail-open: include if unsure

    try:
        data = json.loads(_strip_code_fence(response))
        relevant = bool(data.get("relevant", False))
        confidence = float(data.get("confidence", 0.0))
        reason = data.get("reason", "")
        logger.info(
            "Filter '%s': relevant=%s (%.0f%%) — %s",
            content.title, relevant, confidence * 100, reason,
        )
        return relevant
    except (json.JSONDecodeError, ValueError):
        logger.warning("Unparseable filter response for '%s': %r", content.url, response)
        return True  # Fail-open
