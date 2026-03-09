from __future__ import annotations
import logging
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from processor.models import Article

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except OSError:
    WEASYPRINT_AVAILABLE = False

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_pdf(articles: list[Article], output_path: str) -> None:
    """Compile all articles into a single styled PDF."""
    if not WEASYPRINT_AVAILABLE:
        logger.warning(
            "PDF rendering skipped — WeasyPrint GTK libraries not found. "
            "See https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows"
        )
        return

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)

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

    master_html = _assemble_master(cover_html, article_fragments)
    css = CSS(filename=str(_TEMPLATE_DIR / "styles.css"))

    HTML(string=master_html, base_url=str(_TEMPLATE_DIR)).write_pdf(
        output_path,
        stylesheets=[css],
    )
    logger.info("PDF written: %s", output_path)


def _assemble_master(cover: str, articles: list[str]) -> str:
    """Wrap all HTML fragments in a complete HTML document."""
    body = "\n".join(articles)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AI Weekly</title>
</head>
<body>
{cover}
{body}
</body>
</html>"""
