"""
MobyGames provider (games supplement).
Docs: https://www.mobygames.com/info/api/
Auth: API key as query param (?api_key=...).
Free tier: 360 requests/hour, 1 req/sec max.
Registration: https://www.mobygames.com/user/register/
"""

import requests
from modules.core.base_metadata import MetadataProvider


class MobyGamesProvider(MetadataProvider):
    """Games metadata from MobyGames — strong retro/classic game coverage."""

    _API_URL = 'https://api.mobygames.com/v1'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('mobygames_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str, params: dict = None) -> dict | list | None:
        if not self._api_key:
            return None
        p = {'api_key': self._api_key}
        if params:
            p.update(params)
        try:
            r = requests.get(f'{self._API_URL}{endpoint}', params=p, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[MobyGames] Request error: {e}')
            return None

    def search(self, query: str) -> list:
        data = self._get('/games', {'title': query, 'format': 'brief', 'limit': 5})
        if not data:
            return []
        return data.get('games', [])

    def get_details(self, item_id) -> dict:
        data = self._get(f'/games/{item_id}')
        return data or {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres_raw = raw.get('genres', [])
        genres     = [g['genre_name'] for g in genres_raw if isinstance(g, dict) and g.get('genre_name')]
        genre      = genres[0] if genres else ''

        platforms  = raw.get('platforms', [])
        first_year = ''
        if platforms:
            years = []
            for p in platforms:
                yr = str(p.get('first_release_date', '') or '')
                if yr and yr[:4].isdigit():
                    years.append(yr[:4])
            if years:
                first_year = min(years)

        moby_id  = raw.get('game_id', '')
        slug     = raw.get('moby_url', '').rstrip('/').split('/')[-1] if raw.get('moby_url') else ''
        prov_url = raw.get('moby_url', '')

        # Cover: sample_cover from list result, or moby_score from detail
        cover_url = ''
        cover     = raw.get('sample_cover') or {}
        if isinstance(cover, dict):
            cover_url = cover.get('image', '')

        rating = ''
        score  = raw.get('moby_score')
        if score is not None:
            rating = str(round(float(score), 1))

        return {
            'name':         raw.get('title', ''),
            'year':         first_year,
            'rating':       rating,
            'description':  raw.get('description', '') or '',
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': prov_url,
            'website_url':  '',
            'slug':         slug,
        }

    def search_and_extract(self, query: str) -> dict | None:
        results = self.search(query)
        if not results:
            return None
        game_id = results[0].get('game_id')
        if game_id:
            details = self.get_details(game_id)
            if details:
                return self.extract(details)
        return self.extract(results[0])
