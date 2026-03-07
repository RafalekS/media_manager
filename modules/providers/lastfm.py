"""
Last.fm provider (music supplement).
Docs: https://www.last.fm/api
Auth: API key (free at https://www.last.fm/api/account/create).
No rate limit published; be polite (1 req/sec).
"""

import requests
from modules.core.base_metadata import MetadataProvider


class LastFmProvider(MetadataProvider):
    """Supplemental music metadata from Last.fm."""

    _API_URL = 'https://ws.audioscrobbler.com/2.0/'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('lastfm_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _get(self, method: str, extra: dict = None) -> dict:
        if not self._api_key:
            return {}
        params = {'method': method, 'api_key': self._api_key, 'format': 'json'}
        if extra:
            params.update(extra)
        try:
            r = requests.get(self._API_URL, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[LastFM] Error ({method}): {e}')
            return {}

    def search(self, query: str) -> list:
        # Parse "Artist - Album" if present
        if ' - ' in query:
            parts = query.split(' - ', 1)
            data = self._get('album.search', {'album': parts[1], 'limit': 5})
        else:
            data = self._get('album.search', {'album': query, 'limit': 5})
        return data.get('results', {}).get('albummatches', {}).get('album', [])

    def get_details(self, item_id) -> dict:
        """item_id = 'Artist|||Album' string."""
        if '|||' in item_id:
            artist, album = item_id.split('|||', 1)
            data = self._get('album.getinfo', {'artist': artist, 'album': album})
            return data.get('album', {})
        return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        artist = raw.get('artist', '')
        album  = raw.get('name', '')
        name   = f'{artist} - {album}' if artist else album

        tags = raw.get('tags', {}).get('tag', [])
        if isinstance(tags, dict):
            tags = [tags]
        genres = [t['name'] for t in tags if isinstance(t, dict)]
        genre  = genres[0] if genres else ''

        images = raw.get('image', [])
        cover_url = ''
        for img in reversed(images):
            if img.get('#text'):
                cover_url = img['#text']
                break

        mbid         = raw.get('mbid', '')
        url          = raw.get('url', '')
        provider_url = url

        listeners = raw.get('listeners', '')
        playcount  = raw.get('playcount', '')

        return {
            'name':         name,
            'year':         '',
            'rating':       '',
            'description':  f'Listeners: {listeners}  Plays: {playcount}' if listeners else '',
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         mbid or url,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        first = results[0]
        # Fetch full details
        artist = first.get('artist', '')
        album  = first.get('name', '')
        details = self.get_details(f'{artist}|||{album}') if artist and album else {}
        return self.extract(details) if details else self.extract(first)
