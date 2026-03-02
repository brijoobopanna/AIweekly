# DEVELOPER.md — AI Weekly Pipeline

## Purpose

This document describes the internal architecture, data flow, and key design
decisions of the AI Weekly Pipeline. It is intended for contributors and for
anyone running or extending this system.

---

## High-Level Data Flow

```
sources.txt
    |
    v
[URL Loader]       pipeline.py: _load_urls()
    |
    v
[Detector]         fetcher/detector.py: detect_source_type()
    |
    +-- YouTube --> fetcher/youtube_fetcher.py  --> FetchedContent
    +-- arXiv   --> fetcher/arxiv_fetcher.py    --> FetchedContent
    +-- Web     --> fetcher/web_fetcher.py       --> FetchedContent
    |
    v
[Filter]           processor/filter.py: is_ai_related()
    |
    +-- not AI-related --> SKIP (logged)
    +-- AI-related     --> continue
    |
    v
[Rewriter]         processor/rewriter.py: rewrite_as_article()
    |
    v
Article dataclass  (title, subtitle, body_html, body_markdown, tags)
    |
    +-- renderer/pdf_renderer.py  --> output/ai-weekly-YYYY-MM-DD.pdf
    +-- renderer/epub_renderer.py --> output/ai-weekly-YYYY-MM-DD.epub
```

---

## Project Structure

```
ai-weekly-pipeline/
├── main.py                       Entry point + APScheduler (Friday 3 PM IST)
├── pipeline.py                   Orchestration loop: fetch → filter → rewrite → render
├── config.py                     Centralised config loaded from .env
├── requirements.txt
├── .env.example                  Copy to .env and fill in ANTHROPIC_API_KEY
├── sources.txt                   One URL per line; # lines are comments
├── DEVELOPER.md                  This file
├── fetcher/
│   ├── base.py                   Abstract BaseFetcher
│   ├── detector.py               URL type classification (no network calls)
│   ├── youtube_fetcher.py        Transcript via youtube-transcript-api
│   ├── web_fetcher.py            HTML via requests + BeautifulSoup4
│   └── arxiv_fetcher.py          Metadata via arXiv Atom XML API
├── processor/
│   ├── models.py                 FetchedContent and Article dataclasses
│   ├── claude_client.py          Anthropic SDK singleton + retry wrapper
│   ├── filter.py                 AI-relevance classification (100 tokens)
│   └── rewriter.py               Magazine-style rewrite (2000 tokens, JSON output)
├── renderer/
│   ├── pdf_renderer.py           WeasyPrint — single HTML doc for correct pagination
│   ├── epub_renderer.py          ebooklib — one chapter per article
│   └── templates/
│       ├── article.html          Jinja2 article fragment
│       ├── cover.html            Cover page fragment
│       └── styles.css            Magazine CSS + CSS Paged Media for WeasyPrint
├── utils/
│   └── rate_limiter.py           retry_with_backoff() with full jitter + Retry-After
└── output/                       Generated PDF and EPUB files land here
```

---

## Module Responsibilities

### `fetcher/detector.py`
Classifies any URL into one of three source types using regex patterns.
Priority order: YouTube > arXiv > Web. Runs synchronously with zero network calls.
All URL routing decisions flow from this single file.

### `fetcher/youtube_fetcher.py`
Uses `youtube-transcript-api` to fetch auto-generated or manual captions without
requiring a YouTube Data API key. Supports `youtube.com/watch?v=`, `youtu.be/`,
and `youtube.com/shorts/` URL formats. Strips bracketed noise tokens such as
`[Music]` and `[Applause]`. Returns `None` if no English transcript exists.

### `fetcher/web_fetcher.py`
Uses `requests` + `BeautifulSoup4` with the `lxml` parser. Boilerplate removal
targets `nav`, `footer`, `sidebar`, and ad containers before content extraction.
Content extraction prefers semantic HTML5 containers (`article`, `main`) then
falls back to aggregating all `<p>` tags. A descriptive `User-Agent` identifies
the bot to webmasters.

### `fetcher/arxiv_fetcher.py`
Calls the arXiv Atom XML API (`export.arxiv.org/api/query`) directly. This
returns structured metadata (title, authors, abstract, publication date) without
parsing the HTML page or downloading the PDF. Version suffixes in the URL (e.g.
`v2`) are stripped before the API call so the canonical record is always fetched.

### `processor/claude_client.py`
Singleton wrapper around the Anthropic Python SDK. All Claude calls route through
`call_claude()`, which applies `retry_with_backoff()` from `utils/rate_limiter.py`.
Token budgets are set per call type: 100 for filtering, 2000 for rewriting.

### `processor/filter.py`
Sends the first 1500 words of each piece plus its title to Claude Opus for
classification. Claude responds with a JSON object:
`{"relevant": bool, "confidence": float, "reason": str}`.
**Fail-open**: if the API call fails the content is included rather than
silently dropped. This prevents invisible data loss.

### `processor/rewriter.py`
Two-part prompt design: the system prompt establishes a persistent editorial
persona ("MIT Technology Review meets Wired"); the user prompt supplies the raw
content and a JSON output schema with keys `title`, `subtitle`, `body_markdown`,
and `tags`. Raw input is capped at 6000 characters to control cost and context
budget. On parse failure a stub article is returned using the raw excerpt, so
the pipeline never crashes due to a rewrite error.

### `renderer/pdf_renderer.py`
All articles are rendered into HTML fragments via Jinja2 templates, assembled
into one master HTML document, and passed to WeasyPrint in a single call. The
single-document approach is required for correct cross-article page numbering
and PDF footer generation via CSS Paged Media `@page` rules.

### `renderer/epub_renderer.py`
Each article becomes a standalone `EpubHtml` chapter item. The spine and NCX
table of contents are built from the ordered chapter list. A shared CSS item is
linked from all chapters. EPUB 3 navigation (`EpubNav`) is included for modern
e-reader compatibility.

### `utils/rate_limiter.py`
Shared retry utility used by all HTTP fetchers and the Claude client.
Implements full-jitter exponential backoff (recommended over pure exponential
backoff for avoiding thundering herd). Reads the `Retry-After` response header
from HTTP 429 responses to honour server-specified wait times.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| PDF library | WeasyPrint | Accepts HTML+CSS; reuses Jinja2 templates; CSS Paged Media for page numbers |
| arXiv fetching | Atom XML API | No extra library; structured data in one HTTP call |
| YouTube transcripts | youtube-transcript-api | No YouTube API key required |
| Filter behaviour on error | Fail-open (include) | Prevents silent data loss; worst case is one non-AI article |
| Scheduler timezone | `Asia/Kolkata` (IANA) | India never observes DST; identifier is permanently stable |
| Scheduler misfire grace | 3600 s | Handles laptop sleep during the Friday 3 PM window |
| Claude output format | JSON with fixed schema | Deterministic parsing; `_extract_json()` handles prose preamble |
| Rewriter input cap | 6000 characters | Controls token cost and context budget |
| Filter token budget | 100 tokens | JSON response is tiny; near-zero cost for rejected articles |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `MODEL_ID` | No | `claude-opus-4-6` | Claude model to use |
| `OUTPUT_DIR` | No | `output` | Directory for PDF/EPUB output |
| `SOURCES_FILE` | No | `sources.txt` | Path to URL list |
| `REQUEST_DELAY_SECONDS` | No | `2.0` | Delay between fetcher HTTP calls (seconds) |
| `MAX_RETRIES` | No | `4` | Max retry attempts for HTTP + Claude calls |
| `SCHEDULE_TIMEZONE` | No | `Asia/Kolkata` | Timezone for the weekly scheduler |
| `SCHEDULE_HOUR` | No | `15` | Hour of scheduled run (24-hour format) |
| `SCHEDULE_MINUTE` | No | `0` | Minute of scheduled run |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`) |

---

## Running the Pipeline

### Install dependencies
```bash
pip install -r requirements.txt
```

### Configure
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### Run immediately (bypass scheduler — for testing)
```bash
python main.py --run-now
```

### Start the scheduler (runs every Friday at 3:00 PM IST)
```bash
python main.py
```

### Add sources
Edit `sources.txt` — one URL per line. Lines starting with `#` are ignored.
Supported URL types: YouTube, arXiv, any web article or blog.

---

## Output Files

All output lands in the `output/` directory (configurable via `OUTPUT_DIR`):

| File | Description |
|---|---|
| `ai-weekly-YYYY-MM-DD.pdf` | Full magazine-style PDF with cover page, per-article page breaks, and footer page numbers |
| `ai-weekly-YYYY-MM-DD.epub` | EPUB for e-reader devices with chapter table of contents |

Files are named with the run date. If the pipeline runs twice in one day the
second run overwrites the first.

---

## Extending the Pipeline

### Adding a new source type

1. Add a new enum value to `SourceType` in `fetcher/detector.py`
2. Add detection regex in `detect_source_type()` in the same file
3. Create `fetcher/my_source_fetcher.py` implementing `BaseFetcher`
4. Register the fetcher in `_FETCHER_MAP` in `pipeline.py`

### Changing the output format

The rendering layer is fully decoupled from the pipeline. To add a new output
format (e.g. Markdown, HTML), create `renderer/my_renderer.py` with a
`render_my_format(articles, output_path)` function, then call it in
`pipeline.py` alongside the existing PDF and EPUB calls.

---

## Logging

The pipeline uses Python's standard `logging` module configured in `config.py`.
Set `LOG_LEVEL=DEBUG` in `.env` to see retry sleep times and detailed per-step
output.

Key log events:

| Message | Location | Meaning |
|---|---|---|
| `Pipeline started at ...` | `pipeline.py` | Run has begun |
| `Loaded N URL(s)` | `pipeline.py` | URLs read from sources.txt |
| `Fetching [type]: url` | `pipeline.py` | About to call a fetcher |
| `Skipped (not AI-related): url` | `pipeline.py` | Filter rejected content |
| `Filter '...': relevant=True (95%)` | `processor/filter.py` | Per-URL filter decision |
| `Article ready: 'title'` | `pipeline.py` | Rewrite succeeded |
| `PDF written: path` | `renderer/pdf_renderer.py` | PDF saved |
| `EPUB written: path` | `renderer/epub_renderer.py` | EPUB saved |
| `Done. N article(s) compiled.` | `pipeline.py` | Run complete |
