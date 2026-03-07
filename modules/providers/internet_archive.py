"""
Internet Archive / Open Library full-text provider (books supplement).
Docs: https://archive.org/developers/internetarchive/
Auth: None required.
Searches the Archive's book collection for cover art and metadata
not available in Open Library's search endpoint.
"""

import requests
from modules.core.base_metadata import MetadataProvider


class InternetArchiveProvider(MetadataProvider):
    """Supplemental book metadata from Internet Archive."""

    _SEARCH_URL = 'https://archive.org/advancedsearch.php'
    _META_URL   = 'https://archive.org/metadata'
    _THUMB_URL  = 'https://archive.org/services/img'

    def authenticate(self) -> bool:
        return True

    def search(self, query: str) -> list:
        try:
            r = requests.get(
                self._SEARCH_URL,
                params={
                    'q':      f'({query}) AND mediatype:texts',
                    'fl[]':   ['identifier', 'title', 'creator', 'subject', 'date', 'description'],
                    'rows':   5,
                    'page':   1,
                    'output': 'json',
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('response', {}).get('docs', [])
        except Exception as e:
            print(f'[InternetArchive] Search error: {e}')
            return []

    def get_details(self, item_id) -> dict:
        try:
            r = requests.get(f'{self._META_URL}/{item_id}', timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[InternetArchive] Details error: {e}')
            return {}

    def extract(self, raw: dict) -> dict:
        if not raw:
            return self._default_item()

        meta = raw.get('metadata', raw)  # handle both search doc and metadata response

        identifier = meta.get('identifier', raw.get('identifier', ''))
        cover_url  = f'{self._THUMB_URL}/{identifier}' if identifier else ''

        title    = meta.get('title', '')
        creators = meta.get('creator', [])
        if isinstance(creators, str):
            creators = [creators]
        author = creators[0] if creators else ''
        name   = f'{author} - {title}' if author else title

        subjects = meta.get('subject', [])
        if isinstance(subjects, str):
            subjects = [subjects]
        genre = subjects[0] if subjects else ''

        date = meta.get('date', '')
        year = date[:4] if date else ''

        provider_url = f'https://archive.org/details/{identifier}' if identifier else ''

        desc = meta.get('description', '')
        if isinstance(desc, list):
            desc = ' '.join(desc)

        return {
            'name':         name,
            'year':         year,
            'rating':       '',
            'description':  desc,
            'cover_url':    cover_url,
            'genre':        genre,
            'genres':       subjects[:5],
            'provider_url': provider_url,
            'website_url':  '',
            'slug':         identifier,
        }

    def search_and_extract(self, query: str) -> dict:
        results = self.search(query)
        if not results:
            return self._default_item()
        return self.extract(results[0])
