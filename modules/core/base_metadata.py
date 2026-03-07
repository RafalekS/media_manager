"""
Abstract base class for all metadata providers.

Every provider must implement search(), get_details(), and extract().
The extract() method must return a normalized dict with standard fields.

Standard normalized fields:
    name         str    Display name from provider
    year         str    Release year ('2023') or 'Unknown'
    rating       float  0-100 (or 0 if not available)
    description  str    Summary/description text
    cover_url    str    Full URL to cover/poster image
    genre        str    Primary genre (single string)
    genres       list   All genres
    provider_url str    URL to item on the provider's site
    website_url  str    Official website URL
    slug         str    URL-friendly identifier
"""

from abc import ABC, abstractmethod


class MetadataProvider(ABC):

    def __init__(self, api_config: dict):
        self.api_config = api_config

    def authenticate(self) -> bool:
        """Obtain or refresh access token. Override for OAuth providers."""
        return True

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """
        Search for an item by name.
        Returns a list of candidate dicts, each with at minimum: id, name.
        """

    @abstractmethod
    def get_details(self, item_id) -> dict:
        """
        Return full raw API response for item_id.
        Returns None on failure.
        """

    @abstractmethod
    def extract(self, raw: dict) -> dict:
        """
        Normalize a raw API response to the standard field set.
        Must always return a dict (never None), defaulting missing fields.
        """

    def search_and_extract(self, query: str) -> dict | None:
        """
        Convenience: search → get first result → extract.
        Returns normalized dict or None if nothing found.
        """
        results = self.search(query)
        if not results:
            return None
        details = self.get_details(results[0]['id'])
        if not details:
            return None
        return self.extract(details)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _default_item() -> dict:
        return {
            'name': '',
            'year': 'Unknown',
            'rating': 0.0,
            'description': 'No description available',
            'cover_url': '',
            'genre': 'Unknown',
            'genres': [],
            'provider_url': '',
            'website_url': '',
            'slug': '',
        }
