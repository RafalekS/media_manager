"""
MusicBrainz provider (music).
Docs: https://musicbrainz.org/doc/MusicBrainz_API
Auth: None required. User-Agent header is MANDATORY.
Rate limit: 1 req/sec (enforced by sleep).
"""

import time
import requests
from modules.core.base_metadata import MetadataProvider


_LAST_REQUEST = 0.0


def _rate_limited_get(url: str, params: dict, timeout: int = 15) -> requests.Response:
    global _LAST_REQUEST
    elapsed = time.time() - _LAST_REQUEST
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    r = requests.get(url, params=params, timeout=timeout,
                     headers={'User-Agent': 'MediaManager/1.0 (media.manager@example.com)'})
    _LAST_REQUEST = time.time()
    return r


class MusicBrainzProvider(MetadataProvider):
    """Primary music metadata from MusicBrainz."""

    _API_URL   = 'https://musicbrainz.org/ws/2'
    _COVER_URL = 'https://coverartarchive.org/release-group'

    def authenticate(self) -> bool:
        return True  # No auth required

    def search(self, query: str) -> list:
        """Search release-groups (albums)."""
        try:
            r = _rate_limited_get(
                f'{self._API_URL}/release-group',
                {'query': query, 'fmt': 'json', 'limit': 5},
            )
            r.raise_for_status()
            return r.json().get('release-groups', [])
        except Exception as e:
            print(f'[MusicBrainz] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        """Fetch release-group by MBID."""
        try:
            r = _rate_limited_get(
                f'{self._API_URL}/release-group/{item_id}',
                {'fmt': 'json', 'inc': 'genres+artist-credits'},
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[MusicBrainz] Details error: {e}')
            return {}

    def _cover_url(self, mbid: str) -> str:
        """Try to fetch cover art from Cover Art Archive."""
        if not mbid:
            return ''
        try:
            r = requests.get(
                f'{self._COVER_URL}/{mbid}',
                headers={'User-Agent': 'MediaManager/1.0 (media.manager@example.com)'},
                timeout=10,
                allow_redirects=True,
            )
            if r.status_code == 200:
                data = r.json()
                images = data.get('images', [])
                for img in images:
                    if img.get('front'):
                        thumbnails = img.get('thumbnails', {})
                        return thumbnails.get('500', '') or thumbnails.get('large', '') or img.get('image', '')
        except Exception:
            pass
        return ''

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        mbid   = raw.get('id', '')
        genres = [g['name'] for g in raw.get('genres', []) if isinstance(g, dict)]
        genre  = genres[0] if genres else ''

        # First release date
        year = ''
        date = raw.get('first-release-date', '')
        if date:
            year = date[:4]

        # Artist name
        artist_credits = raw.get('artist-credit', [])
        artist = ''
        if artist_credits:
            first = artist_credits[0]
            if isinstance(first, dict):
                artist = first.get('artist', {}).get('name', '')

        name  = raw.get('title', '')
        if artist:
            name = f'{artist} - {name}'

        cover_url    = self._cover_url(mbid)
        provider_url = f'https://musicbrainz.org/release-group/{mbid}' if mbid else ''

        return {
            'name':         name,
            'year':         year,
            'rating':       '',
            'description':  '',
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       genres,
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         mbid,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        # Fetch full details for genres
        mbid = results[0].get('id', '')
        if mbid:
            details = self.get_details(mbid)
            if details:
                return self.extract(details)
        return self.extract(results[0])
