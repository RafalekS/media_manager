"""
Comics media type plugin.

Typical folder names: "Series Name Vol 1", "Title #001", "Publisher - Title"
"""

import re
from modules.core.base_plugin import MediaPlugin


class ComicsPlugin(MediaPlugin):
    name       = 'Comics'
    media_type = 'comics'
    icon       = '💥'

    def clean_name(self, raw: str) -> str:
        cleaned = raw
        # Strip volume/issue indicators for searching
        cleaned = re.sub(r'\s+Vol\.?\s*\d+.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+#\d+.*$', '', cleaned)
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = re.sub(r'\(.*?\)', '', cleaned)
        cleaned = cleaned.replace('_', ' ').replace('.', ' ')
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
