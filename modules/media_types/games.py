"""
Games media type plugin.

Name cleaning mirrors game_processor/modules/utils.py clean_game_name().
Update detection mirrors game_processor/modules/game_organizer.py.
"""

import re
from modules.core.base_plugin import MediaPlugin


class GamesPlugin(MediaPlugin):
    name       = 'Games'
    media_type = 'games'
    icon       = '🎮'

    _STRIP_PATTERNS = [
        r'-[A-Z]{2,}$',
        r'\.Update\..*$',
        r'\.v\d+.*$',
        r'\.Build\..*$',
        r'\[.*?\]',
        r'\.PC$',
        r'\.Windows.*$',
        r'-pc$',
        r'-win.*$',
        r'\.TENOKE$',
        r'\.GOG$',
        r'\.CODEX$',
        r'\.RUNE$',
    ]

    def clean_name(self, raw: str) -> str:
        cleaned = raw
        for pat in self._STRIP_PATTERNS:
            cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('.', ' ').replace('_', ' ')
        cleaned = ' '.join(cleaned.split())
        cleaned = re.sub(r'\s+Update$', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def is_update(self, folder_name: str) -> bool:
        return bool(re.search(r'[._\s]Update([._\s\-]|$)', folder_name, re.IGNORECASE))

    def clean_update_name(self, raw: str) -> str:
        cleaned = raw
        cleaned = re.sub(r'-[A-Za-z]{2,}$', '', cleaned)
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        # Dots → spaces, but preserve digit.digit (version numbers)
        cleaned = re.sub(r'(?<!\d)\.(?!\d)', ' ', cleaned)
        cleaned = cleaned.replace('_', ' ')
        cleaned = ' '.join(cleaned.split())
        # Sanitize for folder use
        for ch in r':*?"<>|':
            cleaned = cleaned.replace(ch, '')
        return cleaned.strip()

    @property
    def columns(self) -> list[tuple]:
        return [
            ('display_name', 'IGDB Name',    200),
            ('genre',        'Genre',         120),
            ('year',         'Year',           60),
            ('rating',       'Rating',         65),
            ('description',  'Description',   350),
        ]
