"""
Giant Bomb provider (games supplement).
Docs: https://www.giantbomb.com/api/documentation
Auth: API key (free with account registration).
Rate limit: 200 req/hour.
"""

import time
import requests
from modules.core.base_metadata import MetadataProvider

_LAST = 0.0


def _get(url, params, timeout=15):
    global _LAST
    elapsed = time.time() - _LAST
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    r = requests.get(url, params=params, headers={'User-Agent': 'MediaManager/1.0'}, timeout=timeout)
    _LAST = time.time()
    return r


class GiantBombProvider(MetadataProvider):
    """Supplemental games metadata from Giant Bomb."""

    _API_URL = 'https://www.giantbomb.com/api'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('giantbomb_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _params(self, extra: dict = None) -> dict:
        p = {'api_key': self._api_key, 'format': 'json'}
        if extra:
            p.update(extra)
        return p

    def search(self, query: str) -> list:
        if not self._api_key:
            return []
        try:
            r = _get(f'{self._API_URL}/search/', self._params({
                'query':     query,
                'resources': 'game',
                'field_list': 'id,name,deck,image,genres,original_release_date,site_detail_url',
                'limit': 5,
            }))
            r.raise_for_status()
            data = r.json()
            if data.get('error') != 'OK':
                return []
            return data.get('results', [])
        except Exception as e:
            print(f'[GiantBomb] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        if not self._api_key:
            return {}
        try:
            r = _get(f'{self._API_URL}/game/{item_id}/', self._params({
                'field_list': 'id,name,deck,description,image,genres,original_release_date,site_detail_url',
            }))
            r.raise_for_status()
            data = r.json()
            return data.get('results', {}) if data.get('error') == 'OK' else {}
        except Exception as e:
            print(f'[GiantBomb] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        release = raw.get('original_release_date', '') or ''
        year = release[:4] if release else ''

        image = raw.get('image', {})
        cover_url = image.get('medium_url', '') if isinstance(image, dict) else ''

        provider_url = raw.get('site_detail_url', '')

        return {
            'name':         raw.get('name', ''),
            'year':         year,
            'rating':       '',
            'description':  raw.get('deck', '') or '',
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
