"""
IGDB provider (games).
Docs: https://api-docs.igdb.com/
Auth: OAuth2 client_credentials via Twitch endpoint.
"""

import re
import time
import requests
from modules.core.base_metadata import MetadataProvider

# Ordered longest-first so VIII is checked before VI before I
_ROMAN_TO_ARABIC = [
    ('VIII', '8'), ('VII', '7'), ('VI', '6'), ('IV', '4'), ('IX', '9'),
    ('III', '3'), ('II', '2'), ('X', '10'), ('V', '5'), ('I', '1'),
]
_ARABIC_TO_ROMAN = [(a, r) for r, a in reversed(_ROMAN_TO_ARABIC)]


def _convert_numbers(text: str) -> str:
    """Try arabic→roman then roman→arabic. Returns variant or original if no change."""
    # Arabic → Roman (e.g. "Starcraft 2" → "Starcraft II")
    v = text
    for arabic, roman in _ARABIC_TO_ROMAN:
        v = re.sub(rf'\b{arabic}\b', roman, v)
    if v != text:
        return v
    # Roman → Arabic (e.g. "Final Fantasy VII" → "Final Fantasy 7")
    v = text
    for roman, arabic in _ROMAN_TO_ARABIC:
        v = re.sub(rf'\b{roman}\b', arabic, v, flags=re.IGNORECASE)
    if v != text:
        return v
    return ''  # no conversion possible


class IGDBProvider(MetadataProvider):
    """Primary games metadata from IGDB (Twitch)."""

    _AUTH_URL = 'https://id.twitch.tv/oauth2/token'
    _API_URL  = 'https://api.igdb.com/v4'
    _WEBSITE_PRIORITY = {1: 10, 13: 9, 16: 8, 15: 7}  # official, steam, epic, itch

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._token = None
        self._token_expires = 0
        self._client_id     = api_config.get('client_id', '')
        self._client_secret = api_config.get('client_secret', '')

    def authenticate(self) -> bool:
        if not self._client_id or not self._client_secret:
            print('[IGDB] client_id / client_secret not configured')
            return False
        try:
            r = requests.post(self._AUTH_URL, params={
                'client_id':     self._client_id,
                'client_secret': self._client_secret,
                'grant_type':    'client_credentials',
            }, timeout=10)
            r.raise_for_status()
            data = r.json()
            self._token         = data['access_token']
            self._token_expires = time.time() + data.get('expires_in', 3600) - 60
            return True
        except Exception as e:
            print(f'[IGDB] Auth failed: {e}')
            return False

    def _ensure_auth(self):
        if not self._token or time.time() >= self._token_expires:
            self.authenticate()

    def _headers(self) -> dict:
        self._ensure_auth()
        return {
            'Client-ID':     self._client_id,
            'Authorization': f'Bearer {self._token}',
        }

    def _query(self, endpoint: str, body: str) -> list:
        try:
            r = requests.post(
                f'{self._API_URL}/{endpoint}',
                headers=self._headers(),
                data=body,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[IGDB] Query error ({endpoint}): {e}')
            return []

    def search(self, query: str) -> list:
        body = (
            f'search "{query}"; '
            'fields id,name,slug,first_release_date,genres.name,'
            'cover.image_id,rating,summary,websites.url,websites.category; '
            'limit 5;'
        )
        return self._query('games', body)

    def get_details(self, item_id) -> dict:
        body = (
            f'where id = {item_id}; '
            'fields id,name,slug,first_release_date,genres.name,'
            'cover.image_id,rating,summary,websites.url,websites.category; '
            'limit 1;'
        )
        results = self._query('games', body)
        return results[0] if results else {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        cover_image_id = ''
        cover = raw.get('cover')
        if isinstance(cover, dict):
            cover_image_id = cover.get('image_id', '')
        cover_url = (
            f'//images.igdb.com/igdb/image/upload/t_cover_big/{cover_image_id}.jpg'
            if cover_image_id else ''
        )

        slug        = raw.get('slug', '')
        provider_url = f'https://www.igdb.com/games/{slug}' if slug else ''
        website_url  = self._extract_website_url(raw.get('websites', []))

        year = ''
        ts = raw.get('first_release_date')
        if ts:
            from modules.core.utils import convert_unix_to_year
            year = convert_unix_to_year(ts)

        rating = raw.get('rating', 0)
        if rating:
            rating = round(rating / 10, 1)

        return {
            'name':         raw.get('name', ''),
            'year':         year,
            'rating':       str(rating) if rating else '',
            'description':  raw.get('summary', ''),
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  website_url,
            'slug':         slug,
        }

    def _extract_website_url(self, websites: list) -> str:
        if not websites:
            return ''
        best_url  = ''
        best_prio = -1
        for w in websites:
            cat  = w.get('category', 0)
            prio = self._WEBSITE_PRIORITY.get(cat, 0)
            if prio > best_prio:
                best_prio = prio
                best_url  = w.get('url', '')
        return best_url

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        # If no exact match, also try with arabic↔roman number conversion
        q_lower = query.lower().strip()
        has_exact = any(r.get('name', '').lower().strip() == q_lower for r in results)
        if not has_exact:
            variant = _convert_numbers(query)
            if variant:
                results += self.search(variant)
        if not results:
            return self._default_item()
        return self.extract(self._pick_best_match(query, results))

    def _pick_best_match(self, query: str, results: list) -> dict:
        """
        Return the result whose name best matches the query.
        Exact match (case-insensitive) wins immediately.
        Otherwise use SequenceMatcher ratio to pick the closest name.
        """
        import difflib
        q = query.lower().strip()
        best      = results[0]
        best_score = -1.0
        for r in results:
            name = r.get('name', '').lower().strip()
            if name == q:
                return r  # exact match — done
            score = difflib.SequenceMatcher(None, q, name).ratio()
            if score > best_score:
                best_score = score
                best = r
        return best
