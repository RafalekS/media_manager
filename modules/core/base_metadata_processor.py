"""
Generic metadata processor.
Reads scan_list.json, queries primary + supplement providers,
writes results to metadata_progress.json.
"""

import json
import time
from pathlib import Path

from modules.core.utils import load_metadata_progress, save_metadata_progress
from modules.providers import get_provider_class


def process_metadata(lib_config, plugin, full_collection: bool = False, stop_fn=None):
    """
    Fetch metadata for items not yet successfully processed.
    full_collection=True: scan destination folder for ALL items, not just scan_list.json.
    """
    if full_collection:
        scan_list = _build_full_collection_scan(lib_config, plugin)
        if not scan_list:
            print('[Metadata] No items found in destination folder.')
            return
    else:
        scan_file = lib_config.scan_list_file
        if not Path(scan_file).exists():
            print(f'[Metadata] scan_list.json not found: {scan_file}')
            print('[Metadata] Run a scan first.')
            return
        with open(scan_file, 'r', encoding='utf-8') as f:
            scan_list = json.load(f)
        if not scan_list:
            print('[Metadata] Scan list is empty.')
            return

    meta_file = lib_config.metadata_file
    progress   = load_metadata_progress(meta_file)
    items      = progress.setdefault('processed_items', {})

    # Build provider instances
    api_cfg  = lib_config.api
    primary  = _build_provider(lib_config.primary_provider, api_cfg)
    supplements = [
        _build_provider(name, api_cfg)
        for name in lib_config.supplement_providers
        if name
    ]
    supplements = [p for p in supplements if p is not None]

    if primary is None:
        print(f'[Metadata] No primary provider configured for {plugin.name}.')
        return

    primary.authenticate()
    for sup in supplements:
        sup.authenticate()

    total   = len(scan_list)
    done    = 0
    skipped = 0

    for entry in scan_list:
        if stop_fn and stop_fn():
            print('[Metadata] Stopped by user. Saving progress...')
            break

        original_name = entry.get('original_name', '')
        clean_name    = entry.get('clean_name', '') or plugin.clean_name(original_name)

        if not clean_name:
            continue

        existing = items.get(clean_name, {})
        if existing.get('found') or existing.get('igdb_found'):
            skipped += 1
            continue

        done += 1
        print(f'[{done}/{total}] Looking up: {clean_name}')

        result = _query_with_supplements(primary, supplements, clean_name)

        if result:
            result['original_name'] = original_name
            result['found']         = True
            result['igdb_found']    = True  # legacy compat
            result['manual']        = False
            if plugin.is_update(original_name):
                result['is_update'] = True
            items[clean_name] = result
            print(f'       Found: {result.get("name", "")}')
        else:
            items[clean_name] = {
                'original_name': original_name,
                'found':         False,
                'igdb_found':    False,
                'manual':        False,
                'genre':         '',
                'display_name':  clean_name,
            }
            print(f'       Not found.')

        # Rate limiting — respects per-library setting
        time.sleep(lib_config.data.get('rate_limit', 0.25))

    save_metadata_progress(progress, meta_file)
    found_total = sum(1 for v in items.values() if v.get('found') or v.get('igdb_found'))
    print(f'\n[Metadata] Done. {found_total}/{len(items)} items with metadata.')


def _build_provider(name: str, api_cfg: dict):
    if not name:
        return None
    try:
        cls = get_provider_class(name)
        return cls(api_cfg)
    except Exception as e:
        print(f'[Metadata] Failed to load provider {name!r}: {e}')
        return None


def _query_with_supplements(primary, supplements, query: str) -> dict:
    """
    Query primary provider. If it returns data, merge supplement data
    to fill in missing fields. Returns normalized dict or None.
    """
    result = primary.search_and_extract(query)

    if not result or not result.get('name'):
        return None

    # Fill in missing fields from supplement providers
    for sup in supplements:
        try:
            sup_result = sup.search_and_extract(query)
            if sup_result and sup_result.get('name'):
                _merge_supplement(result, sup_result)
        except Exception as e:
            print(f'    [Supplement] Error: {e}')

    return result


def _merge_supplement(primary: dict, supplement: dict):
    """Fill missing fields in primary dict from supplement (in-place)."""
    for key in ('description', 'cover_url', 'genre', 'genres', 'rating', 'year', 'website_url'):
        if not primary.get(key) and supplement.get(key):
            primary[key] = supplement[key]


def _build_full_collection_scan(lib_config, plugin) -> list:
    """
    Build a scan list from the destination folder directly (full-collection mode).
    Scans genre subfolders and returns item dicts in the same format as scan_list.json.
    Respects scan_mode and file_extensions settings.
    """
    from modules.core.base_scanner import _scan_target
    dest = str(lib_config.destination_base)
    skip = set(lib_config.skip_folders)
    skip.add('new')
    scan_mode  = lib_config.data.get('scan_mode', 'folders')
    extensions = [e.lower() for e in lib_config.data.get('file_extensions', [])]

    items = []
    dest_path = Path(dest)
    if not dest_path.exists():
        print(f'[Metadata] Destination not found: {dest}')
        return []

    for genre_dir in sorted(dest_path.iterdir()):
        if not genre_dir.is_dir() or genre_dir.name.lower() in skip:
            continue
        items.extend(_scan_target(str(genre_dir), plugin.clean_name, scan_mode, extensions))

    print(f'[Metadata] Full collection: found {len(items)} items in {dest}')
    return items
