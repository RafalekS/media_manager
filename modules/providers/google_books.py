"""
Google Books provider (books).
Docs: https://developers.google.com/books/docs/v1/using
Auth: API key (optional for basic searches, required for higher quota).
Free tier: 1000 req/day without key, more with key.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class GoogleBooksProvider(MetadataProvider):
    """Primary book metadata from Google Books API."""

    _API_URL = 'https://www.googleapis.com/books/v1'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('api_key', '')

    def authenticate(self) -> bool:
        return True  # No auth required for basic searches

    def _params(self, extra: dict = None) -> dict:
        p = {}
        if self._api_key:
            p['key'] = self._api_key
        if extra:
            p.update(extra)
        return p

    def search(self, query: str) -> list:
        try:
            r = requests.get(
                f'{self._API_URL}/volumes',
                params=self._params({'q': query, 'maxResults': 5, 'printType': 'books'}),
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('items', [])
        except Exception as e:
            print(f'[GoogleBooks] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        try:
            r = requests.get(
                f'{self._API_URL}/volumes/{item_id}',
                params=self._params(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[GoogleBooks] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        info = raw.get('volumeInfo', raw)  # handle both full and partial responses

        categories = info.get('categories', [])
        genre  = categories[0] if categories else ''

        published = info.get('publishedDate', '')
        year = published[:4] if published else ''

        image_links = info.get('imageLinks', {})
        cover_url = (
            image_links.get('thumbnail', '') or
            image_links.get('smallThumbnail', '')
        )
        # Upgrade to https
        if cover_url.startswith('http:'):
            cover_url = 'https:' + cover_url[5:]

        volume_id    = raw.get('id', '')
        provider_url = info.get('canonicalVolumeLink', '') or (
            f'https://books.google.com/books?id={volume_id}' if volume_id else ''
        )

        authors = info.get('authors', [])
        description = info.get('description', '')

        # Include author in name for disambiguation
        name = info.get('title', '')
        if authors:
            name = f"{authors[0]} - {name}" if authors else name

        rating = info.get('averageRating', 0)

        return {
            'name':         name,
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  description,
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       categories,
            'provider_url': provider_url,
            'website_url':  info.get('infoLink', ''),
            'slug':         volume_id,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
