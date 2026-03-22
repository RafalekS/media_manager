"""
itch.io provider (games supplement).
Docs: https://itch.io/docs/api/serverside
Auth: Bearer token in Authorization header.
Falls back to authenticated web search for adult games excluded from the public API.
"""

import difflib
import re
import requests
from modules.core.base_metadata import MetadataProvider


class ItchIOProvider(MetadataProvider):
    """Supplemental games metadata from itch.io."""

    _API_URL = 'https://itch.io/api/1'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key        = api_config.get('itch_api_key', '')
        self._session_cookie = api_config.get('itch_session_cookie', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str) -> list:
        if not self._api_key:
            return []
        results = self._api_search(query)
        if not results:
            results = self._web_search(query)
        return results

    def _api_search(self, query: str) -> list:
        try:
            r = requests.get(
                f'{self._API_URL}/{self._api_key}/search/games',
                params={'query': query},
                headers={'Authorization': f'Bearer {self._api_key}'},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('games') or []
        except Exception as e:
            print(f'[itch.io] API search error: {e}')
            return []

    def _web_search(self, query: str) -> list:
        """Authenticated web search for adult games excluded from the public API.
        Matches on URL slug (e.g. 'divine-heel') which is reliable and present in HTML."""
        try:
            # Session cookie gives full browser auth (needed for adult games).
            # Fall back to Bearer token if no cookie configured.
            req_kwargs = {
                'params':  {'q': query},
                'headers': {'User-Agent': 'Mozilla/5.0 (compatible)'},
                'timeout': 15,
            }
            if self._session_cookie:
                req_kwargs['cookies'] = {'itchio_token': self._session_cookie}
            else:
                req_kwargs['headers']['Authorization'] = f'Bearer {self._api_key}'

            r = requests.get('https://itch.io/search', **req_kwargs)
            r.raise_for_status()

            # Extract (game_id, url) pairs — slug in URL is the reliable title source
            pairs = re.findall(
                r'data-game_id=["\'](\d+)["\'].*?href="(https://[^"]+\.itch\.io/[^"]+)"',
                r.text, re.DOTALL,
            )
            if not pairs:
                return []

            print(f'[itch.io] web search: {len(pairs)} results')

            q_slug = query.lower().strip().replace(' ', '-')
            best_id, best_slug, best_score = pairs[0][0], '', -1.0
            for gid, url in pairs:
                slug = url.rstrip('/').split('/')[-1].lower()
                if slug == q_slug:
                    best_id, best_slug, best_score = gid, slug, 1.0
                    break
                score = difflib.SequenceMatcher(None, q_slug, slug).ratio()
                if score > best_score:
                    best_score = score
                    best_id, best_slug = gid, slug

            print(f'[itch.io] best match: slug="{best_slug}" id={best_id} score={best_score:.2f}')

            if best_score < 0.6:
                return []

            game = self._fetch_by_id(best_id)
            return [game] if game else []
        except Exception as e:
            print(f'[itch.io] Web search error: {e}')
            return []

    def _fetch_by_id(self, game_id: str):
        try:
            r = requests.get(
                f'{self._API_URL}/{self._api_key}/game/{game_id}',
                headers={'Authorization': f'Bearer {self._api_key}'},
                timeout=10,
            )
            r.raise_for_status()
            return r.json().get('game')
        except Exception:
            return None

    def get_details(self, item_id) -> dict:
        return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        year = ''
        published = raw.get('published_at', '') or ''
        if published:
            year = published[:4]

        cover = raw.get('cover_url', '') or ''
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
