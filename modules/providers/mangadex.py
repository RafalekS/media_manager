"""
MangaDex provider (comics supplement — manga/manhwa).
Docs: https://api.mangadex.org/docs/
Auth: None required for search/read.
Rate limit: 5 req/sec.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class MangaDexProvider(MetadataProvider):
    """Supplemental manga/manhwa metadata from MangaDex."""

    _API_URL = 'https://api.mangadex.org'

    def authenticate(self) -> bool:
        return True

    def _get(self, path: str, params: dict = None) -> dict:
        try:
            r = requests.get(
                f'{self._API_URL}/{path}',
                params=params,
                headers={'User-Agent': 'MediaManager/1.0'},
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[MangaDex] Error ({path}): {e}')
            return {}

    def search(self, query: str) -> list:
        data = self._get('manga', {
            'title':        query,
            'limit':        5,
            'includes[]':   ['cover_art', 'author'],
            'contentRating[]': ['safe', 'suggestive'],
        })
        return data.get('data', [])

    def get_details(self, item_id) -> dict:
        data = self._get(f'manga/{item_id}', {'includes[]': ['cover_art', 'author']})
        return data.get('data', {})

    def _cover_url(self, manga_id: str, relationships: list) -> str:
        for rel in relationships:
            if rel.get('type') == 'cover_art':
                fname = rel.get('attributes', {}).get('fileName', '')
                if fname:
                    return f'https://uploads.mangadex.org/covers/{manga_id}/{fname}.256.jpg'
        return ''

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        manga_id = raw.get('id', '')
        attrs    = raw.get('attributes', {})
        rels     = raw.get('relationships', [])

        # Title: prefer English, fall back to first available
        titles = attrs.get('title', {})
        name   = titles.get('en', '') or next(iter(titles.values()), '')

        tags = attrs.get('tags', [])
        genres = [
            t.get('attributes', {}).get('name', {}).get('en', '')
            for t in tags
            if t.get('attributes', {}).get('group') == 'genre'
        ]
        genres = [g for g in genres if g]
        genre  = genres[0] if genres else ''

        year = str(attrs.get('year', '')) if attrs.get('year') else ''

        cover_url    = self._cover_url(manga_id, rels)
        provider_url = f'https://mangadex.org/title/{manga_id}' if manga_id else ''

        desc_map = attrs.get('description', {})
        desc     = desc_map.get('en', '') or next(iter(desc_map.values()), '')

        return {
            'name':         name,
            'year':         year,
            'rating':       '',
            'description':  desc,
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         manga_id,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
