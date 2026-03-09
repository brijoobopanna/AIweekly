import time
import logging
import xml.etree.ElementTree as ET
import requests
from fetcher.base import BaseFetcher
from fetcher.detector import extract_arxiv_id
from processor.models import FetchedContent
from config import config

logger = logging.getLogger(__name__)

_ARXIV_API = "https://export.arxiv.org/api/query?id_list={paper_id}"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArXivFetcher(BaseFetcher):
    def fetch(self, url: str) -> FetchedContent | None:
        paper_id = extract_arxiv_id(url)
        if not paper_id:
            logger.warning("Could not extract arXiv ID from: %s", url)
            return None

        # Strip version suffix (e.g. '2401.12345v2' → '2401.12345') for the API call
        base_id = paper_id.split("v")[0]
        api_url = _ARXIV_API.format(paper_id=base_id)

        response = requests.get(api_url, timeout=20)
        if response.status_code != 200:
            logger.warning("arXiv API error %s for ID: %s", response.status_code, paper_id)
            return None

        metadata = _parse_atom(response.text)
        if not metadata:
            logger.warning("Could not parse arXiv metadata for: %s", paper_id)
            return None

        raw_text = (
            f"Title: {metadata['title']}\n"
            f"Authors: {', '.join(metadata['authors'])}\n"
            f"Published: {metadata['published']}\n\n"
            f"Abstract:\n{metadata['summary']}"
        )

        time.sleep(config.request_delay_seconds)

        return FetchedContent(
            url=url,
            source_type="arxiv",
            raw_text=raw_text,
            title=metadata["title"],
            authors=metadata["authors"],
            published_date=metadata["published"],
            word_count=len(raw_text.split()),
        )


def _parse_atom(xml_text: str) -> dict | None:
    try:
        root = ET.fromstring(xml_text)
        entry = root.find("atom:entry", _NS)
        if entry is None:
            return None
        return {
            "title": (entry.findtext("atom:title", "", _NS) or "").strip(),
            "summary": (entry.findtext("atom:summary", "", _NS) or "").strip(),
            "published": (entry.findtext("atom:published", "", _NS) or "")[:10],
            "authors": [
                a.findtext("atom:name", "", _NS)
                for a in entry.findall("atom:author", _NS)
            ],
        }
    except ET.ParseError as exc:
        logger.error("Failed to parse arXiv XML: %s", exc)
        return None
