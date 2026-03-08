"""
Generic source folder scanner.

If source_folder is configured and different from destination_base,
scans only that inbox/New folder.

If source_folder is blank (or same as destination_base), scans
the destination_base directly — used for libraries where the
collection is already in one place (Music, Books, Movies, etc.).
In that case it scans top-level folders only (not genre subfolders).
"""

from pathlib import Path

from modules.core.utils import scan_source_folder, save_scan_list, load_scan_list
from modules.core.config_manager import LibraryConfig


def process_scan(lib_config: LibraryConfig, plugin, force: bool = True) -> list[dict]:
    scan_file = lib_config.scan_list_file

    if not force and scan_file.exists():
        items = load_scan_list(scan_file)
        if items:
            print(f'[INFO] Using existing scan list ({len(items)} items). Pass force=True to rescan.')
            return items

    source_folder = str(lib_config.source_folder).strip()
    dest_folder   = str(lib_config.destination_base).strip()

    # If no separate source configured, fall back to destination
    if not source_folder or source_folder == dest_folder:
        if not dest_folder:
            print('[ERROR] Neither source_folder nor destination_base is configured.')
            return []
        print(f'[INFO] No separate source folder — scanning destination directly: {dest_folder}')
        scan_target = dest_folder
    else:
        scan_target = source_folder

    items = scan_source_folder(scan_target, plugin.clean_name)
    if items:
        save_scan_list(items, scan_file)
    return items
