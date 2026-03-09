from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from processor.models import Article

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_html(articles: list[Article], output_path: str) -> None:
    """Compile all articles into a single self-contained HTML file."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)

    css = (_TEMPLATE_DIR / "styles.css").read_text(encoding="utf-8")

    cover_tpl = env.get_template("cover.html")
    cover_html = cover_tpl.render(
        date=datetime.now().strftime("%B %d, %Y"),
        article_count=len(articles),
    )

    article_tpl = env.get_template("article.html")
    article_fragments = [
        article_tpl.render(article=article, index=i + 1)
        for i, article in enumerate(articles)
    ]

    toc_items = "".join(
        f'<li><a href="#article-{i + 1}">{article.title}</a></li>'
        for i, article in enumerate(articles)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Weekly — {datetime.now().strftime("%B %d, %Y")}</title>
  <style>
    {_screen_overrides()}
    {css}
  </style>
</head>
<body>
{cover_html}
<nav class="toc">
  <h2>This Week</h2>
  <ol>{toc_items}</ol>
</nav>
{"".join(article_fragments)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    logger.info("HTML written: %s", output_path)


def _screen_overrides() -> str:
    """CSS that adapts the print-focused stylesheet for browser reading."""
    return """
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    @page { size: auto; margin: 0; }
    body { max-width: 780px; margin: 0 auto; padding: 0 1.5em; background: #fff; }
    .cover { padding-top: 0; margin-top: 0; margin-bottom: 2.5em; }
    .cover .brand { font-family: 'Georgia', serif; }
    .article { page-break-before: auto; border-top: 3px solid #1a1a1a; padding-top: 2em; margin-top: 3em; }
    .toc { margin: 2em 0 3em; padding: 1.2em 1.5em; background: #f0f4ff; border-left: 4px solid #2563eb; border-radius: 0 6px 6px 0; }
    .toc h2 { margin: 0 0 0.6em; font-size: 10pt; text-transform: uppercase; letter-spacing: 0.1em; color: #2563eb; }
    .toc ol { margin: 0; padding-left: 1.2em; }
    .toc li { margin-bottom: 0.35em; font-size: 11pt; }
    .toc a { color: #1a1a1a; text-decoration: none; }
    .toc a:hover { color: #2563eb; text-decoration: underline; }
    """
