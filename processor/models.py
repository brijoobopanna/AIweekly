from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchedContent:
    url: str
    source_type: str          # "youtube" | "arxiv" | "web"
    raw_text: str             # Full transcript / article text / abstract+body
    title: str = ""
    authors: list = field(default_factory=list)
    published_date: str = ""
    word_count: int = 0
    source_links: list = field(default_factory=list)  # External URLs found in the page


@dataclass
class Article:
    title: str
    subtitle: str
    body_html: str            # Rendered HTML for PDF/EPUB
    body_markdown: str        # Raw markdown from Claude
    source_url: str
    source_type: str
    tags: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
