"""
Music media type plugin.

Typical folder names: "Artist - Album (Year)", "Artist - Album", "Album"
"""

import re
from modules.core.base_plugin import MediaPlugin


class MusicPlugin(MediaPlugin):
    name       = 'Music'
    media_type = 'music'
    icon       = '🎵'

    def clean_name(self, raw: str) -> str:
        cleaned = raw
        # Strip quality tags
        cleaned = re.sub(r'\b(FLAC|MP3|320kbps|V0|V2|lossless|CBR|VBR)\b.*$', '', cleaned, flags=re.IGNORECASE)
        # Strip year in parens at end
        cleaned = re.sub(r'\(\d{4}\)$', '', cleaned)
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = cleaned.replace('_', ' ')
        # "Artist - Album" → search for "Artist Album" (strip dash separator)
        if ' - ' in cleaned:
            parts = cleaned.split(' - ', 1)
            cleaned = ' '.join(parts)
        return ' '.join(cleaned.split()).strip()

    @property
    def columns(self) -> list[tuple]:
        return [
            ('display_name', 'Album',        220),
            ('genre',        'Genre',         120),
            ('year',         'Year',           60),
            ('rating',       'Rating',         65),
            ('description',  'Description',   350),
        ]
