import time
import random
import logging
from typing import Callable, TypeVar, Optional

logger = logging.getLogger(__name__)
T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_status_codes: tuple = (429, 500, 502, 503, 504, 529),
) -> Optional[T]:
    """
    Execute fn() with exponential backoff + full jitter.
    For HTTP responses, checks status code to decide whether to retry.
    Returns None after exhausting retries.
    """
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            if hasattr(result, "status_code"):
                if result.status_code in retryable_status_codes:
                    retry_after = _get_retry_after(result)
                    _sleep(attempt, base_delay, max_delay, retry_after)
                    continue
            return result
        except Exception as exc:
            if attempt == max_retries:
                logger.error("All %d retries exhausted: %s", max_retries, exc)
                return None
            _sleep(attempt, base_delay, max_delay)
    return None


def _sleep(attempt: int, base: float, max_d: float, override: float = None) -> None:
    if override is not None:
        delay = min(override, max_d)
    else:
        # Full jitter: random(0, min(max_delay, base * 2^attempt))
        delay = random.uniform(0, min(max_d, base * (2 ** attempt)))
    logger.debug("Retry attempt %d: sleeping %.1fs", attempt + 1, delay)
    time.sleep(delay)


def _get_retry_after(response) -> Optional[float]:
    """Parse Retry-After header if present."""
    val = response.headers.get("Retry-After")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return None
