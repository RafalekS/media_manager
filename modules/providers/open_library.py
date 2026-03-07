"""
Open Library provider (books supplement).
Docs: https://openlibrary.org/dev/docs/api
Auth: None required.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class OpenLibraryProvider(MetadataProvider):
    """Supplemental book metadata from Open Library (Internet Archive)."""

    _API_URL   = 'https://openlibrary.org'
    _COVER_URL = 'https://covers.openlibrary.org/b'

    def authenticate(self) -> bool:
        return True

    def search(self, query: str) -> list:
        try:
            r = requests.get(
                f'{self._API_URL}/search.json',
                params={'q': query, 'fields': 'key,title,author_name,first_publish_year,subject,cover_i,ratings_average', 'limit': 5},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('docs', [])
        except Exception as e:
            print(f'[OpenLibrary] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        """item_id should be an OL works key like /works/OL123W"""
        try:
            r = requests.get(
                f'{self._API_URL}{item_id}.json',
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[OpenLibrary] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        subjects = raw.get('subject', [])
        genre    = subjects[0] if subjects else ''

        year = str(raw.get('first_publish_year', '')) if raw.get('first_publish_year') else ''

        cover_i   = raw.get('cover_i', '')
        cover_url = f'{self._COVER_URL}/id/{cover_i}-M.jpg' if cover_i else ''

        key          = raw.get('key', '')
        provider_url = f'{self._API_URL}{key}' if key else ''

        authors = raw.get('author_name', [])
        name    = raw.get('title', '')
        if authors:
            name = f"{authors[0]} - {name}"

        rating = raw.get('ratings_average', 0) or 0

        return {
            'name':         name,
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  '',
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       subjects[:5],
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         key,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
