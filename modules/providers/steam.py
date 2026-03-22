"""
Steam provider (games supplement).
Search:  https://store.steampowered.com/api/storesearch/?term=…  (public, no key needed)
Details: https://store.steampowered.com/api/appdetails?appids=…  (public, no key needed)
The API key is stored in config but is not required for search/details.
"""

import difflib
import requests
from modules.core.base_metadata import MetadataProvider


class SteamProvider(MetadataProvider):
    """Supplemental games metadata from the Steam storefront."""

    _SEARCH_URL  = 'https://store.steampowered.com/api/storesearch/'
    _DETAILS_URL = 'https://store.steampowered.com/api/appdetails'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('steam_api_key', '')  # stored, not required for search

    def authenticate(self) -> bool:
        return True  # storefront endpoints are public

    def search(self, query: str) -> list:
        try:
            r = requests.get(
                self._SEARCH_URL,
                params={'term': query, 'l': 'english', 'cc': 'US'},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('items') or []
        except Exception as e:
            print(f'[Steam] Search error: {e}')
            return []

    def get_details(self, app_id) -> dict:
        try:
            r = requests.get(
                self._DETAILS_URL,
                params={'appids': app_id, 'l': 'english'},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            entry = data.get(str(app_id), {})
            if entry.get('success'):
                return entry.get('data', {})
        except Exception as e:
            print(f'[Steam] Details error for {app_id}: {e}')
        return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        app_id = raw.get('id') or raw.get('steam_appid')

        # If raw is a search result (no description), fetch full details
        details = raw
        if app_id and 'short_description' not in raw:
            fetched = self.get_details(app_id)
            if fetched:
                details = fetched

        # Year from release_date dict like {"coming_soon": false, "date": "18 May, 2015"}
        year = ''
        release_date = details.get('release_date') or {}
        if isinstance(release_date, dict) and not release_date.get('coming_soon'):
            date_str = release_date.get('date', '') or ''
            for part in reversed(date_str.split()):
                if len(part) == 4 and part.isdigit():
                    year = part
                    break

        genres_raw = details.get('genres') or []
        genres = [g.get('description', '') for g in genres_raw if g.get('description')]
        genre = genres[0] if genres else ''

        cover = details.get('header_image', '') or raw.get('tiny_image', '')

        metacritic = details.get('metacritic') or {}
        rating = str(metacritic.get('score', '')) if metacritic.get('score') else ''

        store_url = f'https://store.steampowered.com/app/{app_id}/' if app_id else ''
        website = details.get('website', '') or ''

        return {
            'name':         details.get('name', '') or raw.get('name', ''),
            'year':         year,
            'rating':       rating,
            'description':  details.get('short_description', '') or '',
            'cover_url':    cover,
            'genre':        genre,
            'genres':       genres,
            'provider_url': store_url,
            'website_url':  website or store_url,
            'slug':         str(app_id) if app_id else '',
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        best = self._pick_best_match(query, results, name_key='name')
        return self.extract(best)

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
