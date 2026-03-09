import logging
import anthropic
from config import config
from utils.rate_limiter import retry_with_backoff
import utils.token_budget as token_budget

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    return _client


def call_claude(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 400,
    operation: str = "claude",
) -> str | None:
    """
    Single Claude call with retry logic and token budget tracking.
    Returns the text response or None on failure or budget exhaustion.
    """
    budget = token_budget.get()
    if budget and not budget.can_afford(max_tokens):
        logger.warning(
            "Token budget exhausted (remaining=%d, needed>=%d) — skipping %s call",
            budget.remaining, max_tokens, operation,
        )
        return None

    def _call():
        return get_client().messages.create(
            model=config.model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

    response = retry_with_backoff(_call, max_retries=config.max_retries)
    if response is None:
        return None

    if budget and hasattr(response, "usage"):
        budget.record(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            operation=operation,
        )

    return response.content[0].text if response.content else None
