import re
import time
import logging
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from fetcher.base import BaseFetcher
from fetcher.detector import extract_video_id
from processor.models import FetchedContent
from config import config

logger = logging.getLogger(__name__)

_PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]

_api = YouTubeTranscriptApi()


class YouTubeFetcher(BaseFetcher):
    def fetch(self, url: str) -> FetchedContent | None:
        video_id = extract_video_id(url)
        if not video_id:
            logger.warning("Could not extract video ID from: %s", url)
            return None

        try:
            transcript_list = _api.list(video_id)
            transcript = transcript_list.find_transcript(_PREFERRED_LANGUAGES)
            entries = transcript.fetch()
        except NoTranscriptFound:
            logger.warning("No English transcript found for video: %s", video_id)
            return None
        except TranscriptsDisabled:
            logger.warning("Transcripts disabled for video: %s", video_id)
            return None

        raw_text = " ".join(entry.text for entry in entries)
        raw_text = _clean_transcript(raw_text)

        time.sleep(config.request_delay_seconds)

        return FetchedContent(
            url=url,
            source_type="youtube",
            raw_text=raw_text,
            title=f"YouTube Video ({video_id})",
            word_count=len(raw_text.split()),
        )


def _clean_transcript(text: str) -> str:
    """Remove [Music], [Applause] noise tags and normalise whitespace."""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
