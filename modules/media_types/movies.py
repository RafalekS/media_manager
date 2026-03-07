"""
Movies media type plugin.

Typical folder names: "Movie Title (2023)", "Movie.Title.2023.1080p"
"""

import re
from modules.core.base_plugin import MediaPlugin


class MoviesPlugin(MediaPlugin):
    name       = 'Movies'
    media_type = 'movies'
    icon       = '🎬'

    _STRIP_PATTERNS = [
        r'\(\d{4}\).*$',        # (2023) and everything after
        r'\.\d{4}\..*$',        # .2023. and everything after
        r'\b(1080p|720p|4K|HDR|BluRay|WEBRip|BDRip|DVDRip|HDTV|x264|x265|HEVC|AAC|AC3)\b.*$',
        r'\[.*?\]',
        r'\(.*?\)',
    ]

    def clean_name(self, raw: str) -> str:
        cleaned = raw
        for pat in self._STRIP_PATTERNS:
            cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('.', ' ').replace('_', ' ').replace('-', ' ')
        return ' '.join(cleaned.split()).strip()

    @property
    def columns(self) -> list[tuple]:
        return [
            ('display_name', 'Title',        220),
            ('genre',        'Genre',         120),
            ('year',         'Year',           60),
            ('rating',       'Rating',         65),
            ('description',  'Description',   350),
        ]
