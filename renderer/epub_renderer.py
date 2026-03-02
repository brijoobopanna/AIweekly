from __future__ import annotations
import html as html_lib
import logging
from datetime import datetime
from ebooklib import epub
from processor.models import Article

logger = logging.getLogger(__name__)

_EPUB_CSS = """
body  { font-family: Georgia, serif; line-height: 1.7; margin: 2em; }
h1    { font-size: 1.8em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
h2    { font-size: 1.1em; color: #555; font-weight: normal; font-style: italic; }
p     { margin: 0.8em 0; text-indent: 1.2em; }
p:first-of-type { text-indent: 0; }
.meta   { font-size: 0.8em; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }
.tags   { font-size: 0.8em; color: #888; margin-top: 1.5em; }
.source { font-size: 0.8em; color: #888; }
"""


def render_epub(articles: list[Article], output_path: str) -> None:
    """Compile all articles into a single EPUB with one chapter per article."""
    book = epub.EpubBook()

    datestamp = datetime.now().strftime("%Y-%m-%d")
    book.set_identifier(f"ai-weekly-{datestamp}")
    book.set_title(f"AI Weekly — {datetime.now().strftime('%B %d, %Y')}")
    book.set_language("en")
    book.add_author("AI Weekly Pipeline")
    book.add_metadata("DC", "description", "Curated weekly digest of AI news and research.")

    style = epub.EpubItem(
        uid="style_main",
        file_name="style/main.css",
        media_type="text/css",
        content=_EPUB_CSS.encode(),
    )
    book.add_item(style)

    chapters: list[epub.EpubHtml] = []
    toc_entries: list[epub.Link] = []

    for i, article in enumerate(articles):
        chapter = _make_chapter(article, i, style)
        book.add_item(chapter)
        chapters.append(chapter)
        toc_entries.append(
            epub.Link(chapter.file_name, article.title, f"chapter_{i}")
        )

    book.toc = toc_entries
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    epub.write_epub(output_path, book)
    logger.info("EPUB written: %s", output_path)


def _make_chapter(article: Article, index: int, style: epub.EpubItem) -> epub.EpubHtml:
    chapter = epub.EpubHtml(
        title=article.title,
        file_name=f"chapter_{index:03d}.xhtml",
        lang="en",
    )
    chapter.add_link(href=style.file_name, rel="stylesheet", type="text/css")
    chapter.set_content(_article_to_xhtml(article))
    return chapter


def _article_to_xhtml(article: Article) -> str:
    title = html_lib.escape(article.title)
    subtitle_html = f"<h2>{html_lib.escape(article.subtitle)}</h2>" if article.subtitle else ""
    url = html_lib.escape(article.source_url)
    # Replace named HTML entities (e.g. &nbsp;) with Unicode so the XML parser accepts them
    body_html = article.body_html.replace("&nbsp;", "\u00a0")
    tags_html = (
        f'<p class="tags">Topics: {html_lib.escape(", ".join(article.tags))}</p>'
        if article.tags else ""
    )
    return f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>{title}</title></head>
<body>
  <h1>{title}</h1>
  {subtitle_html}
  <p class="meta">{html_lib.escape(article.source_type.upper())} · {article.generated_at[:10]}</p>
  {body_html}
  {tags_html}
  <p class="source">Source: <a href="{url}">{url}</a></p>
</body>
</html>"""
