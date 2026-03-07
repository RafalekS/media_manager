"""
Generic source folder scanner.

Scans an inbox/New folder, writes scan_list.json.
Media-type-specific name cleaning is provided by the plugin.
"""

import json
from pathlib import Path

from modules.core.utils import scan_source_folder, save_scan_list, load_scan_list
from modules.core.config_manager import LibraryConfig


def process_scan(lib_config: LibraryConfig, plugin, force: bool = True) -> list[dict]:
    """
    Scan the library's source folder and persist the result.

    Returns the list of scanned item dicts.
    """
    scan_file = lib_config.scan_list_file

    if not force and scan_file.exists():
        items = load_scan_list(scan_file)
        if items:
            print(f'[INFO] Using existing scan list ({len(items)} items). Use force=True to rescan.')
            return items

    source = str(lib_config.source_folder)
    if not source:
        print('[ERROR] Source folder not configured.')
        return []

    items = scan_source_folder(source, plugin.clean_name)
    if items:
        save_scan_list(items, scan_file)
    return items
