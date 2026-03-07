"""
Marvel Comics provider (comics supplement).
Docs: https://developer.marvel.com/docs
Auth: public_key + md5(ts + private_key + public_key) hash.
Free with account at https://developer.marvel.com/
Rate limit: 3000 req/day.
"""

import hashlib
import time
import requests
from modules.core.base_metadata import MetadataProvider


class MarvelProvider(MetadataProvider):
    """Supplemental comics metadata from Marvel Developer API."""

    _API_URL = 'https://gateway.marvel.com/v1/public'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._public_key  = api_config.get('marvel_public_key', '')
        self._private_key = api_config.get('marvel_private_key', '')

    def authenticate(self) -> bool:
        return bool(self._public_key and self._private_key)

    def _auth_params(self) -> dict:
        ts   = str(int(time.time()))
        raw  = ts + self._private_key + self._public_key
        hash_val = hashlib.md5(raw.encode('utf-8')).hexdigest()
        return {'ts': ts, 'apikey': self._public_key, 'hash': hash_val}

    def _get(self, path: str, extra: dict = None) -> dict:
        if not self._public_key or not self._private_key:
            return {}
        params = self._auth_params()
        if extra:
            params.update(extra)
        try:
            r = requests.get(f'{self._API_URL}/{path}', params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[Marvel] Error ({path}): {e}')
            return {}

    def search(self, query: str) -> list:
        data = self._get('series', {'titleStartsWith': query, 'limit': 5, 'orderBy': 'title'})
        return data.get('data', {}).get('results', [])

    def get_details(self, item_id) -> dict:
        data = self._get(f'series/{item_id}')
        results = data.get('data', {}).get('results', [])
        return results[0] if results else {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        thumbnail = raw.get('thumbnail', {})
        path      = thumbnail.get('path', '')
        ext       = thumbnail.get('extension', '')
        cover_url = f'{path}.{ext}' if path and ext else ''
        if cover_url and not cover_url.startswith('http'):
            cover_url = 'https:' + cover_url.lstrip(':')
        # Marvel returns placeholder images — skip those
        if 'image_not_available' in cover_url:
            cover_url = ''

        start = raw.get('startYear', '')
        year  = str(start) if start else ''

        series_id    = raw.get('id', '')
        provider_url = raw.get('urls', [{}])[0].get('url', '') if raw.get('urls') else ''

        return {
            'name':         raw.get('title', ''),
            'year':         year,
            'rating':       '',
            'description':  raw.get('description', '') or '',
            'cover_url':    cover_url,
            'genre':        'Comics',
            'genres':       ['Comics'],
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         str(series_id),
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
