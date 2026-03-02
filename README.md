# AI Weekly

An automated pipeline that curates, summarizes, and delivers a weekly digest of AI content — research papers, YouTube videos, and blog posts — powered by Claude.

Every Friday at 15:00 IST (configurable), it scans your source list, picks the most relevant AI stories from the past 7 days, rewrites each into a concise paragraph, and emails you a self-contained HTML report.

---

## How It Works

```
sources.txt → expand → fetch → filter → rewrite → HTML report → email
```

1. **Expand** — YouTube channels and blog homepages are expanded via RSS into individual video/article URLs. When a source yields more than 3 items, a lightweight Claude call on title + summary selects the top 3 before any full content is fetched.
2. **Fetch** — Each URL is classified (YouTube / arXiv / web) and fetched with the appropriate fetcher.
3. **Filter** — Claude classifies whether the content is AI-related. Non-AI content is dropped.
4. **Rewrite** — Claude rewrites each article into one focused paragraph: what the topic is, why it matters, and the key takeaway. Links resolve to the real primary source, not aggregators.
5. **Render** — All articles are assembled into a single self-contained HTML file.
6. **Email** — The report is sent via Gmail SMTP.

Re-runs on the same day are free — processed articles are cached and reused at zero token cost.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/brijoobopanna/AIweekly.git
cd AIweekly
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
ANTHROPIC_API_KEY=sk-ant-...

# Optional — Gmail delivery
EMAIL_SENDER=you@gmail.com
EMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_RECIPIENTS=you@gmail.com,other@example.com
```

For Gmail delivery, enable 2-Step Verification and generate an [App Password](https://myaccount.google.com/apppasswords) for "Mail".

### 3. Edit your source list

Add URLs to `sources.txt`. Lines starting with `#` are comments.

```
# YouTube channels (expanded via RSS)
https://www.youtube.com/@AndrejKarpathy/videos

# Blogs and newsletters (expanded via RSS)
https://huggingface.co/blog
https://sebastianraschka.com/blog/

# Direct article / arXiv / video URLs
https://arxiv.org/abs/2401.00001
```

**Supported source types:**
| Type | Example |
|---|---|
| YouTube channel | `https://www.youtube.com/@ChannelName/videos` |
| YouTube video | `https://www.youtube.com/watch?v=...` |
| arXiv paper | `https://arxiv.org/abs/...` |
| Blog / newsletter | `https://example.com/blog` (RSS auto-detected) |
| Direct article | `https://example.com/article` |

> **Note:** `lnkd.in` short links fail — LinkedIn blocks scraping. Replace them with direct article URLs.

---

## Running

```bash
# Run immediately (bypasses the weekly scheduler)
python main.py --run-now

# Start the scheduler (runs every Friday at 15:00 IST by default)
python main.py

# Verbose logging
LOG_LEVEL=DEBUG python main.py --run-now
```

Output is saved to `output/ai-weekly-YYYY-MM-DD.html`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `MODEL_ID` | `claude-opus-4-6` | Claude model used for all calls |
| `TOKEN_BUDGET` | `50000` | Max tokens consumed per pipeline run |
| `OUTPUT_DIR` | `output` | Directory for HTML output and state files |
| `SOURCES_FILE` | `sources.txt` | Path to your URL list |
| `REQUEST_DELAY_SECONDS` | `2.0` | Delay between HTTP fetches (be polite) |
| `MAX_RETRIES` | `4` | Retry attempts for HTTP and Claude calls |
| `SCHEDULE_TIMEZONE` | `Asia/Kolkata` | Timezone for the weekly scheduler |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | `15` / `0` | Time of the scheduled run |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `EMAIL_SENDER` | — | Gmail address to send from |
| `EMAIL_APP_PASSWORD` | — | Gmail App Password |
| `EMAIL_RECIPIENTS` | — | Comma-separated recipient list |

---

## Token Budget

The pipeline tracks real token usage across every Claude call and logs a running summary after each one:

```
[selector]  cost=48   used=48/50000 (0%)   remaining=49952   ~71 articles left
[filter]    cost=87   used=135/50000 (0%)  remaining=49865   ~70 articles left
[rewrite]   cost=312  used=447/50000 (1%)  remaining=49553   ~69 articles left
```

When the budget falls below the minimum needed for another article, the pipeline stops early and renders what it has.

---

## Project Structure

```
pipeline.py          # Orchestration — runs all four phases
config.py            # Config dataclass, reads .env
sources.txt          # Your curated URL list
fetcher/
  detector.py        # Classifies URLs into SourceType
  web_fetcher.py     # requests + BeautifulSoup4
  youtube_fetcher.py # YouTube transcript via youtube-transcript-api
  arxiv_fetcher.py   # arXiv Atom XML API
  rss_expander.py    # Expands blog homepages via RSS
  youtube_channel_expander.py
processor/
  filter.py          # AI-relevance classification
  rewriter.py        # Concise paragraph rewrite + primary source resolution
  selector.py        # Top-3 selection from expanded sources
  claude_client.py   # Claude API wrapper with token budget tracking
  models.py          # FetchedContent, Article dataclasses
renderer/
  html_renderer.py   # Self-contained HTML output
  templates/         # Jinja2 templates + CSS
sender/
  email_sender.py    # Gmail SMTP delivery
utils/
  state.py           # Processed URL history (output/.state.json)
  article_cache.py   # Article cache (output/.article_cache.json)
  token_budget.py    # Per-run token budget singleton
```

---

## Requirements

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)
- Gmail account with App Password (for email delivery)
