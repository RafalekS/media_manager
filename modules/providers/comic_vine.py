"""
Comic Vine provider (comics).
Docs: https://comicvine.gamespot.com/api/documentation
Auth: API key (free with account registration).
Rate limit: 200 req/hour (resource), 100 req/hour (search).
"""

import requests
from modules.core.base_metadata import MetadataProvider


class ComicVineProvider(MetadataProvider):
    """Primary comics metadata from Comic Vine."""

    _API_URL = 'https://comicvine.gamespot.com/api'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _params(self, extra: dict = None) -> dict:
        p = {'api_key': self._api_key, 'format': 'json'}
        if extra:
            p.update(extra)
        return p

    def _get(self, endpoint: str, params: dict = None) -> dict:
        if not self._api_key:
            return {}
        try:
            r = requests.get(
                f'{self._API_URL}/{endpoint}',
                params=self._params(params),
                headers={'User-Agent': 'MediaManager/1.0'},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data.get('error') != 'OK':
                print(f'[ComicVine] API error: {data.get("error")}')
                return {}
            return data
        except Exception as e:
            print(f'[ComicVine] Error ({endpoint}): {e}')
            return {}

    def search(self, query: str) -> list:
        data = self._get('search', {
            'query':     query,
            'resources': 'volume',
            'field_list': 'id,name,start_year,image,genres,deck,site_detail_url',
            'limit':     5,
        })
        return data.get('results', []) if data else []

    def get_details(self, item_id) -> dict:
        data = self._get(f'volume/4050-{item_id}', {
            'field_list': 'id,name,start_year,image,genres,deck,site_detail_url,description',
        })
        return data.get('results', {}) if data else {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        image     = raw.get('image', {})
        cover_url = image.get('medium_url', '') if isinstance(image, dict) else ''

        year = str(raw.get('start_year', '')) if raw.get('start_year') else ''

        provider_url = raw.get('site_detail_url', '')

        # deck = short description, description = full HTML
        description = raw.get('deck', '') or ''

        return {
            'name':         raw.get('name', ''),
            'year':         year,
            'rating':       '',
            'description':  description,
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         str(raw.get('id', '')),
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
