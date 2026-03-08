"""
TMDB provider (movies).
Docs: https://developer.themoviedb.org/docs
Auth: Bearer token (read access token) or api_key param.
Free tier: available with account registration.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class TMDBProvider(MetadataProvider):
    """Primary movie metadata from The Movie Database."""

    _API_URL  = 'https://api.themoviedb.org/3'
    _IMG_BASE = 'https://image.tmdb.org/t/p/w500'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key     = api_config.get('tmdb_api_key', '')
        self._access_token = api_config.get('tmdb_access_token', '')

    def authenticate(self) -> bool:
        return bool(self._api_key or self._access_token)

    def _headers(self) -> dict:
        if self._access_token:
            return {'Authorization': f'Bearer {self._access_token}'}
        return {}

    def _params(self, extra: dict = None) -> dict:
        p = {}
        if self._api_key and not self._access_token:
            p['api_key'] = self._api_key
        if extra:
            p.update(extra)
        return p

    def _get(self, path: str, params: dict = None) -> dict | list:
        try:
            r = requests.get(
                f'{self._API_URL}/{path}',
                headers=self._headers(),
                params=self._params(params),
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[TMDB] Error ({path}): {e}')
            return {}

    def search(self, query: str) -> list:
        data = self._get('search/movie', {'query': query, 'page': 1})
        return data.get('results', []) if isinstance(data, dict) else []

    def get_details(self, item_id) -> dict:
        data = self._get(f'movie/{item_id}', {'append_to_response': 'external_ids'})
        return data if isinstance(data, dict) else {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        release = raw.get('release_date', '')
        year    = release[:4] if release else ''

        poster = raw.get('poster_path', '')
        cover_url = f'{self._IMG_BASE}{poster}' if poster else ''

        movie_id = raw.get('id', '')
        provider_url = f'https://www.themoviedb.org/movie/{movie_id}' if movie_id else ''

        homepage = raw.get('homepage', '')

        rating = raw.get('vote_average', 0)

        return {
            'name':         raw.get('title', '') or raw.get('original_title', ''),
            'year':         year,
            'rating':       str(round(rating, 1)) if rating else '',
            'description':  raw.get('overview', ''),
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  homepage,
            'slug':         str(movie_id),
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        item_id = results[0].get('id')
        if item_id:
            details = self.get_details(item_id)
            if details:
                return self.extract(details)
        return self.extract(results[0])
