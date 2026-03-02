from abc import ABC, abstractmethod
from processor.models import FetchedContent


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> "FetchedContent | None":
        """
        Fetch raw content from a URL.
        Returns None if content cannot be retrieved.
        Raises exceptions for hard failures (caller handles logging).
        """
        ...
