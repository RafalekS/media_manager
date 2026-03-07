"""
RAWG provider (games supplement).
Docs: https://rawg.io/apidocs
Auth: API key as query param.
Free tier: unlimited reads, registration required.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class RAWGProvider(MetadataProvider):
    """Supplemental games metadata from RAWG."""

    _API_URL = 'https://api.rawg.io/api'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _params(self, extra: dict = None) -> dict:
        p = {'key': self._api_key}
        if extra:
            p.update(extra)
        return p

    def search(self, query: str) -> list:
        if not self._api_key:
            return []
        try:
            r = requests.get(
                f'{self._API_URL}/games',
                params=self._params({'search': query, 'page_size': 5}),
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('results', [])
        except Exception as e:
            print(f'[RAWG] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        if not self._api_key:
            return {}
        try:
            r = requests.get(
                f'{self._API_URL}/games/{item_id}',
                params=self._params(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[RAWG] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        released = raw.get('released', '')
        year     = released[:4] if released else ''

        rating   = raw.get('rating', 0)
        slug     = raw.get('slug', '')
        provider_url = f'https://rawg.io/games/{slug}' if slug else ''

        return {
            'name':         raw.get('name', ''),
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  raw.get('description_raw', '') or raw.get('description', ''),
            'cover_url':    raw.get('background_image', ''),
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  raw.get('website', ''),
            'slug':         slug,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        # RAWG search results are partial — fetch full details for description
        item_id = results[0].get('id')
        if item_id:
            details = self.get_details(item_id)
            if details:
                return self.extract(details)
        return self.extract(results[0])
