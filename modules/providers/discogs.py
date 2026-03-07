"""
Discogs provider (music supplement).
Docs: https://www.discogs.com/developers/
Auth: personal access token (free at https://www.discogs.com/settings/developers).
Rate limit: 60 req/min authenticated.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class DiscogsProvider(MetadataProvider):
    """Supplemental music metadata from Discogs."""

    _API_URL = 'https://api.discogs.com'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._token = api_config.get('discogs_token', '')

    def authenticate(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict:
        h = {'User-Agent': 'MediaManager/1.0'}
        if self._token:
            h['Authorization'] = f'Discogs token={self._token}'
        return h

    def search(self, query: str) -> list:
        params = {'q': query, 'type': 'release', 'per_page': 5}
        try:
            r = requests.get(
                f'{self._API_URL}/database/search',
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('results', [])
        except Exception as e:
            print(f'[Discogs] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        try:
            r = requests.get(
                f'{self._API_URL}/releases/{item_id}',
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[Discogs] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = raw.get('genre', []) or []
        styles = raw.get('style', []) or []
        all_genres = genres + styles
        genre = all_genres[0] if all_genres else ''

        year = str(raw.get('year', '')) if raw.get('year') else ''

        cover_url = raw.get('cover_image', '') or raw.get('thumb', '')

        title  = raw.get('title', '')   # Discogs: "Artist - Album"
        resource_url = raw.get('resource_url', '')
        item_id = str(raw.get('id', ''))
        provider_url = f'https://www.discogs.com/release/{item_id}' if item_id else ''

        rating = raw.get('community', {}).get('rating', {}).get('average', 0) if isinstance(raw.get('community'), dict) else 0

        return {
            'name':         title,
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  '',
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       all_genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         item_id,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        # Fetch details for community rating
        item_id = results[0].get('id')
        if item_id:
            details = self.get_details(item_id)
            if details:
                return self.extract(details)
        return self.extract(results[0])
