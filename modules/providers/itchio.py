"""
itch.io provider (games supplement).
Docs: https://itch.io/docs/api/serverside
Auth: API key in URL path — no OAuth needed.
Best used as a supplement for indie games not found on IGDB.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class ItchIOProvider(MetadataProvider):
    """Supplemental games metadata from itch.io."""

    _API_URL = 'https://itch.io/api/1'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('itch_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str) -> list:
        if not self._api_key:
            return []
        results = self._api_search(query)
        if not results:
            # The public API excludes adult games regardless of account settings.
            # Fall back to an authenticated web search which respects them.
            results = self._web_search(query)
        return results

    def _api_search(self, query: str) -> list:
        try:
            r = requests.get(
                f'{self._API_URL}/{self._api_key}/search/games',
                params={'query': query},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('games') or []
        except Exception as e:
            print(f'[itch.io] API search error: {e}')
            return []

    def _web_search(self, query: str) -> list:
        """Authenticated web search — finds adult games the public API excludes."""
        import re
        try:
            r = requests.get(
                'https://itch.io/search',
                params={'q': query},
                cookies={'itchio_token': self._api_key},
                headers={'User-Agent': 'Mozilla/5.0 (compatible)'},
                timeout=15,
            )
            r.raise_for_status()
            game_ids = re.findall(r'data-game_id=["\'](\d+)["\']', r.text)
            if not game_ids:
                return []
            results = []
            for gid in game_ids[:5]:
                game = self._fetch_by_id(gid)
                if game:
                    results.append(game)
            return results
        except Exception as e:
            print(f'[itch.io] Web search error: {e}')
            return []

    def _fetch_by_id(self, game_id: str):
        try:
            r = requests.get(
                f'{self._API_URL}/{self._api_key}/game/{game_id}',
                timeout=10,
            )
            r.raise_for_status()
            return r.json().get('game')
        except Exception:
            return None

    def get_details(self, item_id) -> dict:
        # itch.io server API has no single-game endpoint; search is all we have
        return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        year = ''
        published = raw.get('published_at', '') or ''
        if published:
            year = published[:4]

        cover = raw.get('cover_url', '') or ''
        # Ensure https
        if cover.startswith('//'):
            cover = 'https:' + cover

        return {
            'name':         raw.get('title', ''),
            'year':         year,
            'rating':       '',
            'description':  raw.get('short_text', '') or '',
            'cover_url':    cover,
            'genre':        '',
            'genres':       [],
            'provider_url': raw.get('url', ''),
            'website_url':  raw.get('url', ''),
            'slug':         '',
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(self._pick_best_match(query, results, name_key='title'))

    def _pick_best_match(self, query: str, results: list, name_key: str = 'name') -> dict:
        import difflib
        q = query.lower().strip()
        for r in results:
            if r.get(name_key, '').lower().strip() == q:
                return r
        best = results[0]
        best_score = -1.0
        for r in results:
            name = r.get(name_key, '').lower().strip()
            score = difflib.SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best_score = score
                best = r
        return best
