# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Configure (copy and fill in ANTHROPIC_API_KEY)
cp .env.example .env

# Run the pipeline immediately (bypasses the weekly scheduler)
py main.py --run-now

# Start the scheduler (runs every Friday at 15:00 IST by default)
py main.py

# Enable verbose logging
LOG_LEVEL=DEBUG py main.py --run-now
```

Use `py` not `python` — the `python` command is blocked by a Windows App Execution Alias on this machine.

There is no test suite; `--run-now` is the primary way to test end-to-end.

## Architecture

The pipeline runs in four sequential phases, all orchestrated by `pipeline.py:run_pipeline()`:

**1. Expand sources** — `sources.txt` URLs are resolved and expanded:
- Short-link URLs (lnkd.in etc.) are followed to their final destination
- YouTube channel URLs → individual video URLs via RSS, filtered to the 7-day window, then top 3 selected by `processor/selector.py`
- Blog/newsletter homepages → individual article URLs via RSS (`fetcher/rss_expander.py`), top 3 selected
- Direct article/video/arXiv URLs pass through unchanged

**2. Fetch** — `fetcher/detector.py` classifies each URL into a `SourceType`, then the matching fetcher retrieves a `FetchedContent` dataclass:
- `YOUTUBE` → `fetcher/youtube_fetcher.py` (youtube-transcript-api, no API key; uses instance API `YouTubeTranscriptApi().list()`)
- `ARXIV` → `fetcher/arxiv_fetcher.py` (Atom XML API)
- `WEB` → `fetcher/web_fetcher.py` (requests + BeautifulSoup4); also extracts `source_links` (external URLs from page HTML before text stripping)

**3. Filter + Rewrite** — Each article is checked against the token budget before any Claude call:
- `processor/filter.py` — AI-relevance classification (100 tokens, fail-open)
- `processor/rewriter.py` — rewrites to a single concise paragraph covering: what the topic is, why it matters, key takeaway. Also identifies `primary_source_url` from `source_links` so the final article links to the real source, not an aggregator. Falls back to first non-aggregator URL in `source_links` if Claude returns the aggregator URL unchanged.
- `processor/selector.py` — called during source expansion; picks top 3 from >3 candidates using only title+summary metadata (50 tokens)
- All Claude calls route through `processor/claude_client.py` which records actual token usage to `utils/token_budget.py`

**4. Cache + Render** — Before fetching/filtering any URL, `utils/article_cache.py` is checked. Cache hits reuse the Article at zero token cost. Cache misses process normally and are saved on completion. After all articles are collected, `renderer/html_renderer.py` produces a single self-contained HTML file.

## Key Design Decisions

| Decision | Detail |
|---|---|
| Output format | Single self-contained HTML (WeasyPrint/GTK not available on this machine; PDF skipped) |
| Article format | One concise paragraph per article: what/why/key takeaway |
| Token budget | Configurable `TOKEN_BUDGET` env var (default 50,000/run); logged after every call with remaining count and estimated articles left |
| Article cache | `output/.article_cache.json` — re-runs on the same day reuse approved articles at 0 cost; cached URLs bypass state.json deduplication |
| Selector | When a source expands to >3 items, a 50-token Claude call on title+summary picks the best 3 before any full content is fetched |
| Primary source | `web_fetcher` extracts up to 20 external links before stripping to text; rewriter picks the real primary source from these; falls back to first non-aggregator link |
| Filter fail-open | If filter Claude call fails, content is included rather than silently dropped |
| State persistence | `output/.state.json` — processed URLs (cap 1000) + last-run timestamp for weekly deduplication |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `MODEL_ID` | `claude-opus-4-6` | Claude model for all calls |
| `TOKEN_BUDGET` | `50000` | Max tokens per pipeline run |
| `OUTPUT_DIR` | `output` | Directory for HTML output, `.state.json`, `.article_cache.json` |
| `SOURCES_FILE` | `sources.txt` | Path to URL list |
| `REQUEST_DELAY_SECONDS` | `2.0` | Delay between fetcher HTTP calls |
| `MAX_RETRIES` | `4` | Max retry attempts for HTTP + Claude calls |
| `SCHEDULE_TIMEZONE` | `Asia/Kolkata` | Timezone for the weekly scheduler |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | `15` / `0` | Time of scheduled run |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Extending

**Add a new source type**: add enum value to `SourceType` in `fetcher/detector.py`, add detection regex in `detect_source_type()`, create `fetcher/my_fetcher.py` implementing `BaseFetcher`, register in `_FETCHER_MAP` in `pipeline.py`.

**Add a new output format**: create `renderer/my_renderer.py` with a `render_my_format(articles, output_path)` function and call it in `pipeline.py` alongside `render_html`.

## Known Issues

- All `lnkd.in` links fail — LinkedIn blocks scraping; replace with direct article URLs in `sources.txt`
- WeasyPrint PDF skipped until GTK3 runtime is installed on Windows
