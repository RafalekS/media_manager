"""
Generic source folder scanner.

scan_mode = 'folders' (default): each subfolder is one item (games, movie folders, album folders).
scan_mode = 'files':             each matching file is one item (books, comics, loose music files).
                                 file_extensions in library config controls which types to include.

If source_folder is blank (or same as destination_base), scans the destination directly.
"""

from pathlib import Path

from modules.core.utils import save_scan_list, load_scan_list
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

    if not source_folder or source_folder == dest_folder:
        if not dest_folder:
            print('[ERROR] Neither source_folder nor destination_base is configured.')
            return []
        print(f'[INFO] No separate source folder — scanning destination directly: {dest_folder}')
        scan_target = dest_folder
    else:
        scan_target = source_folder

    scan_mode  = lib_config.data.get('scan_mode', 'folders')
    extensions = [e.lower() for e in lib_config.data.get('file_extensions', [])]

    items = _scan_target(scan_target, plugin.clean_name, scan_mode, extensions)
    if items:
        save_scan_list(items, scan_file)
    return items


def _scan_target(folder: str, clean_fn, scan_mode: str, extensions: list) -> list[dict]:
    """
    Scan a folder and return item dicts.
    scan_mode='folders': each subdirectory is one item.
    scan_mode='files':   each file matching extensions is one item.
    """
    target = Path(folder)
    if not target.exists():
        print(f'[ERROR] Folder not found: {target}')
        return []

    items = []
    print(f'Scanning ({scan_mode}): {target}')

    if scan_mode == 'files':
        ext_set = {e if e.startswith('.') else f'.{e}' for e in extensions}
        for entry in sorted(target.iterdir()):
            if entry.is_file() and (not ext_set or entry.suffix.lower() in ext_set):
                name = entry.stem
                items.append({
                    'original_name': name,
                    'clean_name':    clean_fn(name),
                    'file_path':     str(entry),
                    'name':          name,
                })
    else:  # folders
        for entry in sorted(target.iterdir()):
            if entry.is_dir():
                items.append({
                    'original_name': entry.name,
                    'clean_name':    clean_fn(entry.name),
                    'folder_path':   str(entry),
                    'name':          entry.name,
                })

    print(f'[OK] Found {len(items)} {scan_mode}')
    return items
