"""
Config manager — loads global config and per-library config.

GlobalConfig  : config/config.json  (theme, active library, paths)
LibraryConfig : config/libraries/{media_type}.json  (per-library settings)
"""

import json
import os
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent


class GlobalConfig:
    def __init__(self):
        self.root = _ROOT
        self.path = _ROOT / 'config' / 'config.json'
        self.data = self._load()

    def _load(self) -> dict:
        with open(self.path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    @property
    def active_library(self) -> str:
        return self.data['settings'].get('active_library', 'games')

    @active_library.setter
    def active_library(self, value: str):
        self.data['settings']['active_library'] = value

    def set_active_library(self, value: str):
        self.data['settings']['active_library'] = value
        self.save()

    @property
    def theme(self) -> str:
        return self.data['settings'].get('theme', 'Light')

    @theme.setter
    def theme(self, value: str):
        self.data['settings']['theme'] = value

    def set_theme(self, value: str):
        self.data['settings']['theme'] = value
        self.save()

    def get_path(self, key: str) -> Path:
        raw = self.data['paths'].get(key, '')
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        return p if p.is_absolute() else _ROOT / p

    def ui_state_path(self) -> Path:
        return self.get_path('ui_state_file')

    def libraries_folder(self) -> Path:
        return self.get_path('libraries_folder')

    def available_libraries(self) -> list[str]:
        """Return list of media_type keys that have a config file."""
        folder = self.libraries_folder()
        if not folder.exists():
            return []
        return [
            f.stem for f in sorted(folder.glob('*.json'))
            if not f.stem.endswith('_genres')
        ]


class LibraryConfig:
    def __init__(self, media_type_or_path: str):
        """Accept either a media_type name ('games') or a full file path."""
        p = Path(media_type_or_path)
        if p.suffix == '.json' and p.is_absolute():
            self.path = p
            self.media_type = p.stem
        else:
            self.media_type = media_type_or_path
            self.path = _ROOT / 'config' / 'libraries' / f'{media_type_or_path}.json'
        self.root = _ROOT
        if not self.path.exists():
            example = self.path.with_suffix('.json.example')
            if example.exists():
                import shutil
                shutil.copy(example, self.path)
                print(f'[INFO] Created {self.path.name} from example template.')
            else:
                raise FileNotFoundError(f'Library config not found: {self.path}')
        self.data = self._load()

    def _load(self) -> dict:
        with open(self.path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_path(self, key: str) -> Path:
        raw = self.data.get(key, '')
        if not raw:
            return Path()
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        return p if p.is_absolute() else _ROOT / p

    @property
    def name(self) -> str:
        return self.data.get('name', self.media_type.title())

    @property
    def source_folder(self) -> Path:
        return self.get_path('source_folder')

    @property
    def destination_base(self) -> Path:
        return self.get_path('destination_base')

    @property
    def data_folder(self) -> Path:
        raw = self.data.get('data_folder', f'data/{self.media_type}')
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        full = p if p.is_absolute() else _ROOT / p
        full.mkdir(parents=True, exist_ok=True)
        return full

    @property
    def scan_list_file(self) -> Path:
        return self.data_folder / 'scan_list.json'

    @property
    def metadata_file(self) -> Path:
        return self.data_folder / 'metadata_progress.json'

    @property
    def html_file(self) -> Path:
        fname = self.data.get('html_filename', f'{self.media_type}_database_dynamic.html')
        return self.destination_base / fname

    @property
    def genre_file(self) -> Path:
        raw = self.data.get('genre_file', f'config/libraries/{self.media_type}_genres.json')
        p = Path(raw)
        return p if p.is_absolute() else _ROOT / p

    @property
    def primary_provider(self) -> str:
        return self.data.get('primary_provider', '')

    @property
    def supplement_providers(self) -> list[str]:
        return self.data.get('supplement_providers', [])

    @property
    def api(self) -> dict:
        return self.data.get('api', {})

    @property
    def items_per_page(self) -> int:
        return self.data.get('items_per_page', 50)

    @property
    def bat_output_path(self) -> str:
        return self.data.get('bat_output_path', '')

    @property
    def skip_folders(self) -> list:
        return self.data.get('skip_folders', [])
