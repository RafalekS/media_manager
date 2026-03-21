"""
Archive extraction for source folders (e.g. Y:\\Gry\\New\\).
Supports .rar, .zip, .7z archives at root level only (no subdirs).
After successful extraction, deletes the archive.
"""
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path


ARCHIVE_EXTS = {'.rar', '.zip', '.7z'}

# Skip non-first RAR parts: file.part2.rar, file.part02.rar, etc.
_PART_RE = re.compile(r'\.part[2-9]\d*\.rar$', re.IGNORECASE)


def find_tool(configured_path: str = '') -> tuple[str, str]:
    """
    Detect extraction tool.
    Returns (tool_path, tool_type) where tool_type is 'unrar', '7z', or ''.
    Checks configured_path first, then common install locations.
    """
    if configured_path:
        p = Path(configured_path)
        if p.exists() or shutil.which(configured_path):
            kind = 'unrar' if 'unrar' in configured_path.lower() else '7z'
            return configured_path, kind

    candidates = [
        ('unrar',                                          'unrar'),
        (r'C:\Program Files\WinRAR\UnRAR.exe',             'unrar'),
        (r'C:\Program Files (x86)\WinRAR\UnRAR.exe',       'unrar'),
        ('7z',                                             '7z'),
        (r'C:\Program Files\7-Zip\7z.exe',                 '7z'),
        (r'C:\Program Files (x86)\7-Zip\7z.exe',           '7z'),
    ]
    for path, kind in candidates:
        if Path(path).exists() or shutil.which(path):
            return path, kind
    return '', ''


def find_archives(folder: str) -> list[Path]:
    """Return extractable archives at root level only (no subdirs)."""
    root = Path(folder)
    if not root.exists():
        return []
    archives = []
    for f in sorted(root.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in ARCHIVE_EXTS:
            continue
        if _PART_RE.search(f.name):
            continue  # skip part2+
        archives.append(f)
    return archives


def _extract_zip(archive: Path, dest: Path) -> tuple[bool, str]:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive, 'r') as z:
            z.extractall(dest)
        return True, ''
    except Exception as e:
        return False, str(e)


def _extract_with_tool(archive: Path, dest: Path,
                        tool_path: str, tool_type: str) -> tuple[bool, str]:
    dest.mkdir(parents=True, exist_ok=True)
    if tool_type == 'unrar':
        cmd = [tool_path, 'x', '-y', str(archive), str(dest) + '\\']
    else:  # 7z
        cmd = [tool_path, 'x', str(archive), f'-o{dest}', '-y']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return True, ''
        err = (result.stderr or result.stdout).strip()
        return False, err or f'Exit code {result.returncode}'
    except subprocess.TimeoutExpired:
        return False, 'Timed out after 10 minutes'
    except Exception as e:
        return False, str(e)


def extract_all(folder: str,
                tool_path: str = '',
                tool_type: str = '',
                delete_after: bool = True,
                stop_fn=None) -> tuple[int, int]:
    """
    Extract all archives found at root of folder.
    Returns (success_count, fail_count).
    Logs to stdout and appends to <folder>/unpack.log.
    """
    archives = find_archives(folder)
    if not archives:
        print(f'[Extract] No archives found in: {folder}')
        return 0, 0

    if not tool_path:
        tool_path, tool_type = find_tool()

    total   = len(archives)
    success = 0
    fail    = 0

    print(f'[Extract] Found {total} archive(s) in: {folder}')
    if tool_path:
        print(f'[Extract] Using: {tool_path} ({tool_type})')
    else:
        print('[Extract] WARNING: No extraction tool found. ZIP only.')

    log_path = Path(folder) / 'unpack.log'
    with open(log_path, 'a', encoding='utf-8') as log:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log.write(f'\n{"=" * 50}\n')
        log.write(f'Archive Extractor Log — {ts}\n')
        log.write(f'Source: {folder}\n')
        log.write(f'Tool: {tool_path or "none"}\n')
        log.write(f'{"=" * 50}\n')

        for i, archive in enumerate(archives, 1):
            if stop_fn and stop_fn():
                print('[Extract] Stopped by user.')
                log.write('[STOPPED by user]\n')
                break

            dest = archive.parent / archive.stem  # strip .rar → folder name

            if dest.exists():
                msg = f'[{i}/{total}] Skip — already exists: {dest.name}/'
                print(msg)
                log.write(f'[SKIP] {archive.name}\n')
                continue

            print(f'[{i}/{total}] Extracting: {archive.name}  →  {dest.name}/')

            if archive.suffix.lower() == '.zip':
                ok, err = _extract_zip(archive, dest)
            elif tool_path:
                ok, err = _extract_with_tool(archive, dest, tool_path, tool_type)
            else:
                ok, err = False, f'No tool available for {archive.suffix}'

            if ok:
                success += 1
                print(f'       [OK]')
                log.write(f'[OK] {archive.name} → {dest.name}/\n')
                if delete_after:
                    try:
                        archive.unlink()
                        print(f'       Deleted: {archive.name}')
                        log.write(f'[DELETED] {archive.name}\n')
                    except Exception as e:
                        print(f'       [WARN] Could not delete: {e}')
            else:
                fail += 1
                # Clean up empty destination if created
                try:
                    if dest.exists() and not any(dest.iterdir()):
                        dest.rmdir()
                except Exception:
                    pass
                print(f'       [FAIL] {err}')
                log.write(f'[FAIL] {archive.name} — {err}\n')

        ts_end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log.write(f'\nTotal: {success} extracted, {fail} failed — {ts_end}\n')

    print(f'\n[Extract] Done: {success} extracted, {fail} failed.')
    return success, fail
