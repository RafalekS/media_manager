"""
Provider factory — returns MetadataProvider subclass by name.
"""

_REGISTRY = {
    # Games
    'igdb':             ('modules.providers.igdb',             'IGDBProvider'),
    'rawg':             ('modules.providers.rawg',             'RAWGProvider'),
    'giantbomb':        ('modules.providers.giantbomb',        'GiantBombProvider'),
    'itchio':           ('modules.providers.itchio',           'ItchIOProvider'),
    # Movies
    'tmdb':             ('modules.providers.tmdb',             'TMDBProvider'),
    'omdb':             ('modules.providers.omdb',             'OMDBProvider'),
    'trakt':            ('modules.providers.trakt',            'TraktProvider'),
    # Books
    'google_books':     ('modules.providers.google_books',     'GoogleBooksProvider'),
    'open_library':     ('modules.providers.open_library',     'OpenLibraryProvider'),
    'internet_archive': ('modules.providers.internet_archive', 'InternetArchiveProvider'),
    # Comics
    'comic_vine':       ('modules.providers.comic_vine',       'ComicVineProvider'),
    'mangadex':         ('modules.providers.mangadex',         'MangaDexProvider'),
    'marvel':           ('modules.providers.marvel',           'MarvelProvider'),
    # Music
    'musicbrainz':      ('modules.providers.musicbrainz',      'MusicBrainzProvider'),
    'lastfm':           ('modules.providers.lastfm',           'LastFmProvider'),
    'discogs':          ('modules.providers.discogs',          'DiscogsProvider'),
}


def get_provider_class(name: str):
    """Return the provider class for the given provider name string."""
    entry = _REGISTRY.get(name.lower())
    if entry is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(_REGISTRY)}")
    module_path, class_name = entry
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)
