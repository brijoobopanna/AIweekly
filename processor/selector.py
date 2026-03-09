"""
Selects the top N most relevant candidates from a list using only their
title and summary metadata — no full content fetch required.
"""
import json
import logging
from processor.claude_client import call_claude

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 3

_SELECTOR_SYSTEM = (
    "You are an AI content curator. Given a list of articles or videos "
    "with titles and short descriptions, pick the most valuable ones for "
    "an AI-focused weekly digest. Prioritise novel research, practical "
    "tools, and significant industry developments. Ignore duplicates, "
    "general tech news unrelated to AI, and promotional content."
)

_SELECTOR_USER_TEMPLATE = """
From the candidates below, choose the {n} most worth including in an AI weekly digest.

CANDIDATES:
{candidates}

Return a JSON array of the chosen indices (0-based), most valuable first.
Example: [2, 0, 4]
Only return the JSON array, nothing else.
""".strip()


def select_top_n(candidates: list[dict], max_n: int = _MAX_CANDIDATES) -> list[dict]:
    """
    Given a list of dicts with url/date/title/summary, return at most max_n
    of the most relevant ones. Falls back to the first max_n if Claude fails.
    """
    if len(candidates) <= max_n:
        return candidates

    candidate_lines = "\n".join(
        f"[{i}] {c.get('title', '(no title)')} — {c.get('summary', '').strip()}"
        for i, c in enumerate(candidates)
    )

    response = call_claude(
        system_prompt=_SELECTOR_SYSTEM,
        user_message=_SELECTOR_USER_TEMPLATE.format(
            n=max_n,
            candidates=candidate_lines,
        ),
        max_tokens=50,
        operation="selector",
    )

    if response:
        try:
            indices = json.loads(response.strip())
            selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
            selected = selected[:max_n]
            if selected:
                logger.info(
                    "Selector chose %d/%d: %s",
                    len(selected),
                    len(candidates),
                    [c.get("title", "") for c in selected],
                )
                return selected
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            logger.warning("Selector response parse failed (%s) — using first %d", exc, max_n)

    return candidates[:max_n]
