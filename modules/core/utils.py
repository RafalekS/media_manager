"""
Shared utilities — generic folder scanning and metadata enrichment.
All functions are media-type-agnostic; behaviour is controlled by the plugin.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def is_path_skipped(path: Path, skip_list: list) -> bool:
    """Return True if *path* matches any entry in skip_list.

    Each entry may be a bare folder name (e.g. 'New') or a full path
    (e.g. 'Y:\\Gry\\Emu').  Comparison is always case-insensitive and
    path-separator-agnostic.
    """
    name = path.name.lower()
    full = str(path).lower().replace('/', '\\').rstrip('\\')
    for s in skip_list:
        s_norm = s.lower().replace('/', '\\').rstrip('\\')
        if s_norm == name or s_norm == full:
            return True
    return False


# ── Date helpers ─────────────────────────────────────────────────────────────

def convert_unix_to_year(unix_timestamp) -> str:
    """Convert a Unix timestamp to a 4-digit year string."""
    if unix_timestamp:
        try:
            return str(datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).year)
        except Exception:
            pass
    return 'Unknown'


# ── Source folder scanning ────────────────────────────────────────────────────

def scan_source_folder(source_folder: str, clean_fn) -> list[dict]:
    """
    Scan the source (New/inbox) folder and return a list of item dicts.

    Each dict: name, clean_name, folder_path.
    clean_fn(name) -> str  (provided by the plugin).
    """
    items = []
    source = Path(source_folder)
    if not source.exists():
        print(f'[ERROR] Source folder not found: {source}')
        return []

    print(f'Scanning source folder: {source}')
    for entry in sorted(source.iterdir()):
        if entry.is_dir():
            items.append({
                'name': entry.name,
                'clean_name': clean_fn(entry.name),
                'folder_path': str(entry),
            })

    print(f'[OK] Found {len(items)} folders')
    return items


def save_scan_list(items: list, path: Path) -> bool:
    try:
        from modules.core.db import LibraryDB
        LibraryDB(path).save_scan_list(items)
        print(f'[OK] Saved {len(items)} items to {Path(path).name}')
        return True
    except Exception as e:
        print(f'[ERROR] Failed to save scan list: {e}')
        return False


def load_scan_list(path: Path) -> list:
    try:
        from modules.core.db import LibraryDB
        return LibraryDB(path).load_scan_list()
    except Exception as e:
        print(f'[ERROR] Failed to load scan list: {e}')
        return []


# ── Destination folder scanning ───────────────────────────────────────────────

def scan_organized_items(destination_base: str, skip_folders: list | None = None) -> dict:
    """
    Scan the organized destination folder (genre subfolders).

    Returns dict: genre_name -> list of item dicts.
    Each item dict: name, folder_path, genre.
    """
    skip_list = list(skip_folders or ['new'])
    result = {}
    total = 0

    dest = Path(destination_base)
    if not dest.exists():
        print(f'[ERROR] Destination not found: {dest}')
        return {}

    print('Scanning organized collection...')
    for genre_dir in sorted(dest.iterdir()):
        if not genre_dir.is_dir() or is_path_skipped(genre_dir, skip_list):
            continue
        items = []
        try:
            for item_dir in genre_dir.iterdir():
                if item_dir.is_dir() and not is_path_skipped(item_dir, skip_list):
                    items.append({
                        'name': item_dir.name,
                        'folder_path': str(item_dir),
                        'genre': genre_dir.name,
                    })
                    total += 1
        except PermissionError:
            print(f'[WARNING] Permission denied: {genre_dir}')
            continue
        if items:
            result[genre_dir.name] = sorted(items, key=lambda x: x['name'].lower())

    print(f'[OK] {total} items across {len(result)} genres')
    return result


# ── Metadata progress ─────────────────────────────────────────────────────────

def load_metadata_progress(path: Path) -> dict:
    """Load metadata from SQLite DB, returning empty structure on missing/error."""
    try:
        from modules.core.db import LibraryDB
        return LibraryDB(path).load_metadata()
    except Exception as e:
        print(f'[ERROR] Failed to load metadata progress: {e}')
        return {'schema_version': 2, 'processed_items': {}}


def save_metadata_progress(data: dict, path: Path) -> bool:
    try:
        from modules.core.db import LibraryDB
        LibraryDB(path).save_metadata(data)
        return True
    except Exception as e:
        print(f'[ERROR] Failed to save metadata progress: {e}')
        return False


# ── Enrichment ────────────────────────────────────────────────────────────────

def enrich_with_metadata(organized: dict, metadata_file: Path) -> dict:
    """
    Enrich scanned organized items with stored metadata.

    Looks up each item by folder name in metadata_progress.json.
    Adds normalized fields to each item dict in-place.
    Returns the enriched organized dict.
    """
    print('Enriching with stored metadata...')
    progress = load_metadata_progress(metadata_file)
    stored = progress.get('processed_items', {})

    # Build lookup by original_name (folder name)
    lookup = {}
    for entry in stored.values():
        orig = entry.get('original_name', '') or entry.get('folder_name', '')
        if orig:
            lookup[orig] = entry

    enriched = 0
    for genre, items in organized.items():
        for item in items:
            folder_name = item['name']
            data = lookup.get(folder_name)
            if data:
                item['clean_name']    = data.get('clean_name', folder_name)
                item['display_name']  = data.get('name', folder_name)
                item['year']          = str(data.get('year') or 'Unknown')
                item['rating']        = float(data.get('rating') or 0)
                item['description']   = data.get('description', 'No description available')
                item['cover_url']     = _resolve_cover_url(data)
                item['provider_url']  = _resolve_provider_url(data)
                item['website_url']   = data.get('website_url', '')
                enriched += 1
            else:
                item.setdefault('clean_name',   folder_name)
                item.setdefault('display_name', folder_name)
                item.setdefault('year',         'Unknown')
                item.setdefault('rating',       0.0)
                item.setdefault('description',  'No description available')
                item.setdefault('cover_url',    '')
                item.setdefault('provider_url', '')
                item.setdefault('website_url',  '')

    print(f'[OK] Enriched {enriched} items')
    return organized


def _resolve_cover_url(data: dict) -> str:
    url = data.get('cover_url', '')
    if url and url.startswith('//'):
        return 'https:' + url
    if not url:
        # Fallback: igdb_data.cover.url
        raw = data.get('igdb_data') or data.get('raw', {})
        if isinstance(raw, dict):
            cover = raw.get('cover', {})
            if isinstance(cover, dict):
                u = cover.get('url', '') or cover.get('image_id', '')
                if u and u.startswith('//'):
                    return 'https:' + u
                # image_id → construct URL
                if u and not u.startswith('http'):
                    return f'https://images.igdb.com/igdb/image/upload/t_cover_big/{u}.jpg'
    return url


def _resolve_provider_url(data: dict) -> str:
    url = data.get('provider_url', '') or data.get('igdb_url', '')
    if not url:
        slug = data.get('slug', '')
        if not slug:
            raw = data.get('igdb_data') or data.get('raw', {})
            if isinstance(raw, dict):
                slug = raw.get('slug', '')
        if slug:
            return f'https://www.igdb.com/games/{slug}'
    return url
