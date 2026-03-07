"""
Trakt provider (movies supplement).
Docs: https://trakt.docs.apiary.io/
Auth: client_id header only (no OAuth needed for read-only search).
Free with account registration at https://trakt.tv/oauth/applications
"""

import requests
from modules.core.base_metadata import MetadataProvider


class TraktProvider(MetadataProvider):
    """Supplemental movie metadata from Trakt.tv."""

    _API_URL = 'https://api.trakt.tv'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._client_id = api_config.get('trakt_client_id', '')

    def authenticate(self) -> bool:
        return bool(self._client_id)

    def _headers(self) -> dict:
        return {
            'Content-Type':      'application/json',
            'trakt-api-version': '2',
            'trakt-api-key':     self._client_id,
        }

    def _get(self, path: str, params: dict = None) -> list | dict:
        if not self._client_id:
            return []
        try:
            r = requests.get(
                f'{self._API_URL}/{path}',
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[Trakt] Error ({path}): {e}')
            return []

    def search(self, query: str) -> list:
        data = self._get('search/movie', {'query': query, 'limit': 5})
        return data if isinstance(data, list) else []

    def get_details(self, item_id) -> dict:
        data = self._get(f'movies/{item_id}', {'extended': 'full'})
        return data if isinstance(data, dict) else {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        # search results wrap in {'type':'movie','score':N,'movie':{...}}
        movie = raw.get('movie', raw)

        ids     = movie.get('ids', {})
        slug    = ids.get('slug', '')
        imdb_id = ids.get('imdb', '')

        genres = movie.get('genres', [])
        genre  = genres[0].replace('-', ' ').title() if genres else ''

        year = str(movie.get('year', '')) if movie.get('year') else ''

        provider_url = f'https://trakt.tv/movies/{slug}' if slug else ''
        website_url  = f'https://www.imdb.com/title/{imdb_id}/' if imdb_id else ''

        rating = movie.get('rating', 0) or 0

        return {
            'name':         movie.get('title', ''),
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  movie.get('overview', ''),
            'cover_url':    '',   # Trakt has no image CDN — supplement only for text data
            'genre':        genre,
            'genres':       [g.replace('-', ' ').title() for g in genres],
            'provider_url': provider_url,
            'website_url':  website_url,
            'slug':         slug,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
