"""
Abstract base class for media type plugins.

Each plugin encapsulates media-type-specific logic:
- Name cleaning for API searches
- Update/patch folder detection (games only by default)
- Column definitions for browser table and HTML output
- Provider class registry
"""

from abc import ABC, abstractmethod


class MediaPlugin(ABC):

    # Subclasses set these as class attributes
    name: str = ''         # Display name, e.g. 'Games'
    media_type: str = ''   # Config key,   e.g. 'games'
    icon: str = ''         # Sidebar emoji, e.g. '🎮'

    @abstractmethod
    def clean_name(self, raw: str) -> str:
        """Clean a raw folder name to produce an API search query."""

    def is_update(self, folder_name: str) -> bool:
        """Return True if the folder represents an update/patch, not a base item."""
        return False

    def clean_update_name(self, raw: str) -> str:
        """
        Clean an update folder name for use as a destination subfolder.
        Default delegates to clean_name(); override for games-style logic.
        """
        return self.clean_name(raw)

    @property
    @abstractmethod
    def columns(self) -> list[tuple]:
        """
        Column definitions for the library browser table and HTML output.
        Each entry: (field_key, display_label, default_width_px)
        field_key must match a key in the normalized metadata dict.
        """

    def get_provider_class(self, provider_name: str):
        """
        Return the provider class for the given name.
        Import is deferred to avoid circular imports at module level.
        """
        from modules.providers import get_provider_class
        return get_provider_class(provider_name)
