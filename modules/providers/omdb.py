"""
OMDB provider (movies supplement).
Docs: https://www.omdbapi.com/
Auth: API key (free tier: 1000 req/day).
Used to supplement TMDB with IMDb rating + extra plot.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class OMDBProvider(MetadataProvider):
    """Supplemental movie metadata from OMDB (IMDb ratings)."""

    _API_URL = 'https://www.omdbapi.com/'

    def __init__(self, api_config: dict):
        super().__init__(api_config)
        self._api_key = api_config.get('omdb_api_key', '')

    def authenticate(self) -> bool:
        return bool(self._api_key)

    def _get(self, params: dict) -> dict:
        if not self._api_key:
            return {}
        try:
            params['apikey'] = self._api_key
            r = requests.get(self._API_URL, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get('Response') == 'False':
                return {}
            return data
        except Exception as e:
            print(f'[OMDB] Error: {e}')
            return {}

    def search(self, query: str) -> list:
        data = self._get({'s': query, 'type': 'movie'})
        return data.get('Search', []) if data else []

    def get_details(self, item_id) -> dict:
        # item_id can be IMDb ID (tt1234567) or OMDB search result imdbID
        return self._get({'i': item_id, 'plot': 'full'})

    def search_by_title(self, title: str, year: str = '') -> dict:
        params = {'t': title, 'type': 'movie', 'plot': 'full'}
        if year:
            params['y'] = year
        return self._get(params)

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        genres_str = raw.get('Genre', '')
        genres = [g.strip() for g in genres_str.split(',') if g.strip()] if genres_str else []
        genre  = genres[0] if genres else ''

        year = raw.get('Year', '')
        if year and '-' in year:   # e.g. "2001-2005"
            year = year.split('-')[0]

        imdb_rating = raw.get('imdbRating', '')
        poster = raw.get('Poster', '')
        if poster == 'N/A':
            poster = ''

        imdb_id = raw.get('imdbID', '')
        provider_url = f'https://www.imdb.com/title/{imdb_id}/' if imdb_id else ''

        return {
            'name':         raw.get('Title', ''),
            'year':         year,
            'rating':       imdb_rating if imdb_rating and imdb_rating != 'N/A' else '',
            'description':  raw.get('Plot', ''),
            'cover_url':    poster,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         imdb_id,
        }

    def search_and_extract(self, query: str) -> dict:
        data = self.search_by_title(query)
        return self.extract(data) if data else self._default_item()
