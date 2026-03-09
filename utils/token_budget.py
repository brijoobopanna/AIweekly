"""
Run-scoped token budget tracker.

A single TokenBudget instance is created at the start of each pipeline run
and shared across all Claude calls (filter, selector, rewriter).

Cost estimates (used only for "articles remaining" projections):
  filter   : ~600  tokens  (input ~500  + output ~100)
  selector : ~300  tokens  (input ~250  + output ~50)
  rewrite  : ~1900 tokens  (input ~1500 + output ~400)
  per article total: ~2500 tokens
"""
import logging

logger = logging.getLogger(__name__)

_TOKENS_PER_ARTICLE = 2_500  # rough estimate for projection only

# Minimum tokens needed before starting a new article (filter + rewrite)
MIN_TOKENS_FOR_ARTICLE = 700   # at least enough for a filter call
MIN_TOKENS_FOR_REWRITE = 1_500  # enough for a rewrite call


class TokenBudget:
    def __init__(self, total: int):
        self.total = total
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.total - self.used

    @property
    def pct_used(self) -> float:
        return 100 * self.used / self.total if self.total else 0

    def articles_remaining_estimate(self) -> int:
        return max(0, self.remaining // _TOKENS_PER_ARTICLE)

    def record(self, input_tokens: int, output_tokens: int, operation: str) -> None:
        cost = input_tokens + output_tokens
        self.used += cost
        logger.info(
            "Tokens | op=%-10s cost=%4d | used=%6d/%d (%.0f%%) | "
            "remaining=%6d | ~%d article(s) left in budget",
            operation, cost, self.used, self.total, self.pct_used,
            self.remaining, self.articles_remaining_estimate(),
        )

    def can_afford(self, min_tokens: int) -> bool:
        return self.remaining >= min_tokens

    def log_summary(self) -> None:
        logger.info(
            "Token budget summary: used %d / %d (%.0f%%) | remaining %d",
            self.used, self.total, self.pct_used, self.remaining,
        )


# Global instance — reset at the start of each pipeline run via reset()
_budget: TokenBudget | None = None


def reset(total: int) -> TokenBudget:
    global _budget
    _budget = TokenBudget(total)
    logger.info("Token budget initialised: %d tokens for this run", total)
    return _budget


def get() -> TokenBudget | None:
    return _budget
