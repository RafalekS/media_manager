"""
Provider factory — returns MetadataProvider subclass by name.
"""

_REGISTRY = {
    'igdb':         ('modules.providers.igdb',         'IGDBProvider'),
    'rawg':         ('modules.providers.rawg',         'RAWGProvider'),
    'tmdb':         ('modules.providers.tmdb',         'TMDBProvider'),
    'omdb':         ('modules.providers.omdb',         'OMDBProvider'),
    'google_books': ('modules.providers.google_books', 'GoogleBooksProvider'),
    'open_library': ('modules.providers.open_library', 'OpenLibraryProvider'),
    'comic_vine':   ('modules.providers.comic_vine',   'ComicVineProvider'),
    'musicbrainz':  ('modules.providers.musicbrainz',  'MusicBrainzProvider'),
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
