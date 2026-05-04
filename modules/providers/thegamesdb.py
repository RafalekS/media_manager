"""
TheGamesDB provider (games supplement).
Docs: https://api.thegamesdb.net/
Auth: API key as query param (?apikey=...).
Free tier: 3000 requests/month.
Registration: https://forums.thegamesdb.net/viewtopic.php?t=14579
"""

import requests
from modules.core.base_metadata import MetadataProvider


class TheGamesDBProvider(MetadataProvider):
    """Games metadata from TheGamesDB — broad retro/multi-platform coverage."""

    _API_URL   = 'https://api.thegamesdb.net/v1'
    _CDN_LARGE = 'https://cdn.thegamesdb.net/images/large'
    _CDN_THUMB = 'https://cdn.thegamesdb.net/images/thumb'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('thegamesdb_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _get(self, endpoint: str, params: dict = None) -> dict | None:
        if not self._api_key:
            return None
        p = {'apikey': self._api_key}
        if params:
            p.update(params)
        try:
            r = requests.get(f'{self._API_URL}{endpoint}', params=p, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[TheGamesDB] Request error: {e}')
            return None

    def search(self, query: str) -> list:
        data = self._get('/Games/ByGameName', {
            'name':          query,
            'fields':        'genres,rating,overview,publishers',
            'include':       'boxart',
            'page':          1,
        })
        if not data or data.get('status') != 'Success':
            return []
        games = data.get('data', {}).get('games', [])
        # Attach boxart lookup for later use in extract
        self._last_boxart = data.get('include', {}).get('boxart', {}).get('data', {})
        self._last_genres = data.get('data', {}).get('genres', {})
        return games

    def get_details(self, item_id) -> dict:
        data = self._get('/Games/ByGameID', {
            'id':      item_id,
            'fields':  'genres,rating,overview,publishers,developers',
            'include': 'boxart',
        })
        if not data or data.get('status') != 'Success':
            return {}
        games = data.get('data', {}).get('games', [])
        if not games:
            return {}
        game = games[0]
        self._last_boxart = data.get('include', {}).get('boxart', {}).get('data', {})
        self._last_genres = data.get('data', {}).get('genres', {})
        return game

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        game_id = str(raw.get('id', ''))

        # Genres — stored as list of IDs in game, full map in _last_genres
        genre_ids  = raw.get('genres', []) or []
        genres_map = getattr(self, '_last_genres', {})
        genres     = [genres_map.get(str(gid), {}).get('name', str(gid)) for gid in genre_ids if gid]
        genre      = genres[0] if genres else ''

        # Year
        release = raw.get('release_date', '') or ''
        year    = release[:4] if release and release[:4].isdigit() else ''

        # Cover image — front boxart from include
        cover_url  = ''
        boxart_map = getattr(self, '_last_boxart', {})
        if game_id in boxart_map:
            arts = boxart_map[game_id]
            fronts = [a for a in arts if isinstance(a, dict) and a.get('side') == 'front']
            if fronts:
                fn = fronts[0].get('filename', '')
                if fn:
                    cover_url = f'{self._CDN_LARGE}/{fn}'

        slug     = raw.get('slug', '')
        prov_url = f'https://thegamesdb.net/game.php?id={game_id}' if game_id else ''

        rating = ''
        rat    = raw.get('rating', '')
        if rat:
            rating = str(rat)

        return {
            'name':         raw.get('game_title', ''),
            'year':         year,
            'rating':       rating,
            'description':  raw.get('overview', '') or '',
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
        # search() already fetched with fields+boxart — extract directly from first result
        extracted = self.extract(results[0])
        if extracted.get('name'):
            return extracted
        return None
