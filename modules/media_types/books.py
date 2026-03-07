"""
Books media type plugin.

Typical folder names: "Author - Title", "Title (Author)", "Title"
"""

import re
from modules.core.base_plugin import MediaPlugin


class BooksPlugin(MediaPlugin):
    name       = 'Books'
    media_type = 'books'
    icon       = '📚'

    def clean_name(self, raw: str) -> str:
        cleaned = raw
        # Strip file extensions if folder happens to have them
        cleaned = re.sub(r'\.(epub|pdf|mobi|azw3)$', '', cleaned, flags=re.IGNORECASE)
        # Remove bracket content
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = re.sub(r'\(.*?\)', '', cleaned)
        # Author - Title pattern: keep both parts but clean
        cleaned = cleaned.replace('_', ' ')
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
