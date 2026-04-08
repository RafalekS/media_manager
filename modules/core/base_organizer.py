"""
Generic folder organizer.

Reads metadata_progress.json, builds a move plan, and either:
  - Generates a .bat file (Windows)
  - Moves files directly via shutil.move

Adapted from game_processor/modules/game_organizer.py, made media-type-agnostic.
Update-folder logic (Updates subfolder) is enabled only when plugin.is_update() is True.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from modules.core.config_manager import LibraryConfig
from modules.core.utils import (
    load_metadata_progress, sanitize_folder_name,
    build_noise_re, _DEFAULT_NOISE_WORDS,
)


class BaseOrganizer:

    def __init__(self, lib_config: LibraryConfig, plugin):
        self.lib_config  = lib_config
        self.plugin      = plugin
        self.base_path   = lib_config.destination_base
        self.genre_file  = lib_config.genre_file
        self.genre_map   = {}      # raw_genre -> folder_name
        self._dest_cache: dict = {}
        self._source_cache: dict = {}
        noise_words = lib_config.data.get('sanitize_noise_words', _DEFAULT_NOISE_WORDS)
        self._noise_re = build_noise_re(noise_words)
        self._load_genre_map()

    # ── Genre mapping ──────────────────────────────────────────────────────

    def _load_genre_map(self):
        if self.genre_file.exists():
            try:
                with open(self.genre_file, 'r', encoding='utf-8') as f:
                    self.genre_map = json.load(f)
                print(f'Loaded {len(self.genre_map)} genre mappings')
            except Exception as e:
                print(f'[WARNING] Could not load genre file: {e}')

    def _save_genre_map(self):
        try:
            self.genre_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.genre_file, 'w', encoding='utf-8') as f:
                json.dump(dict(sorted(self.genre_map.items())), f, indent=2)
        except Exception as e:
            print(f'[WARNING] Could not save genre file: {e}')

    def _get_folder_name(self, genre: str) -> str:
        if genre in self.genre_map:
            return self.genre_map[genre]
        folder = self._clean_folder_name(genre)
        self.genre_map[genre] = folder
        return folder

    # ── Name cleaning ──────────────────────────────────────────────────────

    @staticmethod
    def _clean_folder_name(name: str) -> str:
        """Make a name safe for use as a folder name."""
        for ch in r'/\:*?"<>|':
            name = name.replace(ch, '-' if ch in r'/\|' else '')
        return ' '.join(name.split()).strip()

    # ── Destination / source caches ────────────────────────────────────────

    def _build_dest_cache(self):
        """Build clean_name -> (path, genre) lookup from destination."""
        self._dest_cache = {}
        if not self.base_path.exists():
            return
        try:
            for genre_dir in self.base_path.iterdir():
                if not genre_dir.is_dir() or genre_dir.name.lower() == 'new':
                    continue
                for item_dir in genre_dir.iterdir():
                    if item_dir.is_dir():
                        key = self.plugin.clean_name(item_dir.name).lower()
                        self._dest_cache[key] = (item_dir, genre_dir.name)
        except PermissionError:
            pass

    def _build_source_cache(self):
        """Build clean_name -> path lookup from source folder."""
        self._source_cache = {}
        source = self.lib_config.source_folder
        try:
            for folder in source.iterdir():
                if folder.is_dir():
                    key = self.plugin.clean_name(folder.name)
                    if key not in self._source_cache:
                        self._source_cache[key] = folder
        except (PermissionError, OSError):
            pass

    def _find_in_dest(self, clean_name: str):
        """Return (path, genre) from destination cache or None."""
        return self._dest_cache.get(clean_name.lower())

    def _get_current_path(self, item_data: dict) -> Path | None:
        """Locate the item's current folder on disk."""
        source = self.lib_config.source_folder

        # Try stored path fields
        for key in ('path', 'full_path'):
            stored = item_data.get(key, '')
            if stored:
                p = Path(stored)
                if not p.is_absolute():
                    p = self.base_path / p
                if p.exists():
                    return p

        # Match by clean name in source cache
        orig = item_data.get('original_name', '')
        if orig:
            clean = self.plugin.clean_name(orig)
            if clean in self._source_cache:
                return self._source_cache[clean]

        return None

    def _extract_genre(self, item_data: dict) -> str:
        genre_str = (
            item_data.get('type')
            or item_data.get('genre')
            or 'Unknown'
        )
        if not genre_str or genre_str == 'Unknown':
            return 'Uncategorized'
        return genre_str.split(',')[0].strip()

    # ── Plan building ──────────────────────────────────────────────────────

    def load_items_for_organization(self) -> list[dict]:
        """Build the move plan from metadata_progress.json."""
        meta = load_metadata_progress(self.lib_config.metadata_file)
        stored = meta.get('processed_items', {})
        if not stored:
            print('[WARNING] No processed items found in metadata file.')
            return []

        source = self.lib_config.source_folder
        print('\nBuilding destination index...')
        self._build_dest_cache()
        self._build_source_cache()

        plan = []
        skipped = []
        seen_paths: set = set()
        new_genres = False

        for key, item_data in stored.items():
            found = item_data.get('found', item_data.get('igdb_found', False))
            manual = item_data.get('manual', False)
            if not (found or manual):
                continue

            current_path = self._get_current_path(item_data)
            if not current_path:
                continue

            # Only organize items from source (New) folder
            if not str(current_path).startswith(str(source)):
                continue

            path_key = str(current_path).lower()
            if path_key in seen_paths:
                print(f'  Skipping duplicate: {item_data.get("original_name", key)}')
                continue
            seen_paths.add(path_key)

            raw_genre = self._extract_genre(item_data)
            folder_name = self._get_folder_name(raw_genre)
            if raw_genre not in self.genre_map:
                new_genres = True

            # Already in correct folder?
            if current_path.parent.name == folder_name:
                skipped.append(item_data.get('original_name', key))
                continue

            orig_name = item_data.get('original_name', key)

            # ── Update/patch routing ──────────────────────────────────────
            if self.plugin.is_update(orig_name):
                entry = self._build_update_entry(
                    key, orig_name, item_data, raw_genre, folder_name,
                    seen_paths, plan
                )
                if entry:
                    plan.append(entry)
                continue

            # ── Normal routing ─────────────────────────────────────────────
            safe_name = sanitize_folder_name(orig_name, self._noise_re)
            target = self.base_path / folder_name / safe_name

            plan.append({
                'key': key,
                'original_name': orig_name,
                'display_name': item_data.get('name', orig_name),
                'genre': raw_genre,
                'folder_name': folder_name,
                'current_path': current_path,
                'target_path': target,
                'is_manual': manual,
                'is_update': False,
                'is_rename': False,
            })

        if skipped:
            print(f'Skipped {len(skipped)} items already organized')
        if new_genres:
            self._save_genre_map()

        return plan

    def _build_update_entry(self, key, orig_name, item_data, raw_genre, folder_name,
                             seen_paths, plan) -> dict | None:
        update_safe = sanitize_folder_name(self.plugin.clean_update_name(orig_name), self._noise_re)
        base_clean  = self.plugin.clean_name(orig_name)
        base_result = self._find_in_dest(base_clean)

        if base_result:
            base_path, base_genre = base_result
            base_clean_name = sanitize_folder_name(base_path.name, self._noise_re)
            clean_base_path = self.base_path / base_genre / base_clean_name

            # Rename dirty base game folder if needed
            if base_clean_name != base_path.name:
                base_str = str(base_path).lower()
                if base_str not in seen_paths:
                    seen_paths.add(base_str)
                    plan.append({
                        'key': f'__rename__{base_clean_name}',
                        'original_name': base_path.name,
                        'display_name': base_clean_name,
                        'genre': base_genre,
                        'folder_name': base_genre,
                        'current_path': base_path,
                        'target_path': clean_base_path,
                        'is_manual': False,
                        'is_update': False,
                        'is_rename': True,
                    })

            return {
                'key': key,
                'original_name': orig_name,
                'display_name': item_data.get('name', orig_name),
                'genre': raw_genre,
                'folder_name': base_genre,
                'current_path': self._get_current_path(item_data),
                'target_path': clean_base_path / 'Updates' / update_safe,
                'is_manual': item_data.get('manual', False),
                'is_update': True,
                'is_rename': False,
            }
        else:
            base_safe = sanitize_folder_name(orig_name, self._noise_re)
            return {
                'key': key,
                'original_name': orig_name,
                'display_name': item_data.get('name', orig_name),
                'genre': raw_genre,
                'folder_name': folder_name,
                'current_path': self._get_current_path(item_data),
                'target_path': self.base_path / folder_name / base_safe / 'Updates' / update_safe,
                'is_manual': item_data.get('manual', False),
                'is_update': True,
                'is_rename': False,
            }

    # ── .bat generation ────────────────────────────────────────────────────

    def generate_bat(self, items: list) -> bool:
        """Generate a Windows .bat file for the given move plan."""
        bat_path_str = self.lib_config.bat_output_path
        if bat_path_str:
            bat_file = Path(os.path.expandvars(os.path.expanduser(bat_path_str)))
        else:
            bat_file = self.base_path / 'organize_items.bat'

        lines = [
            '@echo off',
            f'REM {self.plugin.name} Organization Script',
            f'REM Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'REM Total: {len(items)}',
            'REM Review before running!',
            '',
        ]
        for item in items:
            src = str(item['current_path'])
            dst = str(item['target_path'])
            dst_parent = str(Path(dst).parent)
            lines.append(f'REM {item.get("original_name", "")}')
            lines.append(f'if not exist "{dst_parent}" mkdir "{dst_parent}"')
            lines.append(f'move "{src}" "{dst}"')
            lines.append('')

        lines += ['echo Done!', 'pause']

        try:
            bat_file.parent.mkdir(parents=True, exist_ok=True)
            with open(bat_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f'[OK] .bat written to: {bat_file}')
            if items:
                print(f'\n── Planned moves ({len(items)}) ────────────────────')
                for item in items:
                    action = 'RENAME' if item.get('is_rename') else 'MOVE'
                    print(f'  [{action}] {item.get("original_name", "")}')
                    print(f'         → {item["target_path"]}')
                print('──────────────────────────────────────────')
            return True
        except Exception as e:
            print(f'[ERROR] Failed to write .bat: {e}')
            return False

    def run_headless(self):
        """Load plan and generate .bat. Returns (items, success)."""
        items = self.load_items_for_organization()
        if not items:
            return [], False
        return items, self.generate_bat(items)
