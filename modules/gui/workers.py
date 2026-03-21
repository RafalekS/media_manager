"""
QThread workers for media_manager.
All heavy work happens off the main thread.
stdout is redirected to the LogWidget signal stream.
"""

import subprocess
import sys
import time
import traceback
from contextlib import contextmanager

from PyQt6.QtCore import QThread, pyqtSignal


@contextmanager
def _redirect_stdout(stream):
    old = sys.stdout
    sys.stdout = stream
    try:
        yield
    finally:
        sys.stdout = old


# ──────────────────────────────────────────────────────────────────────────────
class _StoppableMixin:
    """Mixin that adds a request_stop() method and should_stop() callable."""
    def __init__(self):
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def should_stop(self) -> bool:
        return self._stop_requested


class ExtractWorker(_StoppableMixin, QThread):
    """Extract archives from source folder before scanning (local)."""
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, stream, delete_after: bool = True):
        _StoppableMixin.__init__(self)
        QThread.__init__(self)
        self._lib_config   = lib_config
        self._stream       = stream
        self._delete_after = delete_after

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                from modules.core.archive_extractor import extract_all, find_tool
                source = self._lib_config.data.get('source_folder', '') or ''
                if not source:
                    print('[Extract] No source folder configured.')
                    self.finished.emit(False, 'No source folder configured.')
                    return
                configured = self._lib_config.data.get('extractor_path', '') or ''
                tool_path, tool_type = find_tool(configured)
                ok, fail = extract_all(
                    source, tool_path, tool_type,
                    delete_after=self._delete_after,
                    stop_fn=self.should_stop,
                )
                self.finished.emit(True, f'{ok} extracted, {fail} failed.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


class ExtractSSHWorker(_StoppableMixin, QThread):
    """Extract archives on a remote host (QNAP NAS) via SSH."""
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, stream, delete_after: bool = True):
        _StoppableMixin.__init__(self)
        QThread.__init__(self)
        self._lib_config   = lib_config
        self._stream       = stream
        self._delete_after = delete_after

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                ssh_host    = self._lib_config.data.get('ssh_host', '') or ''
                ssh_user    = self._lib_config.data.get('ssh_user', '') or ''
                ssh_key     = self._lib_config.data.get('ssh_key_path', '') or ''
                remote_src  = self._lib_config.data.get('ssh_source_path', '') or ''
                script_path = self._lib_config.data.get('ssh_script_path', '') or \
                              '/share/homes/admin/extractor_silent.sh'

                if not ssh_host or not ssh_user or not remote_src:
                    print('[SSH Extract] SSH host, user, and remote source path are required.')
                    print('[SSH Extract] Configure them in Settings.')
                    self.finished.emit(False, 'SSH settings incomplete.')
                    return

                delete_flag = '' if self._delete_after else '--no-delete'
                remote_cmd  = f'bash "{script_path}" "{remote_src}" {delete_flag}'
                ssh_target  = f'{ssh_user}@{ssh_host}'

                ssh_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes']
                if ssh_key:
                    ssh_cmd += ['-i', ssh_key]
                ssh_cmd += [ssh_target, remote_cmd]

                print(f'[SSH Extract] Connecting to {ssh_target}')
                if ssh_key:
                    print(f'[SSH Extract] Key: {ssh_key}')
                print(f'[SSH Extract] Running: {remote_cmd}')

                proc = subprocess.Popen(
                    ssh_cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    if self.should_stop():
                        proc.terminate()
                        print('[SSH Extract] Stopped.')
                        break
                    print(line, end='', flush=True)
                proc.wait()

                if proc.returncode == 0:
                    self.finished.emit(True, 'SSH extraction complete.')
                else:
                    self.finished.emit(False, f'SSH exited with code {proc.returncode}')
            except FileNotFoundError:
                print('[SSH Extract] ssh not found — ensure OpenSSH is installed and in PATH.')
                self.finished.emit(False, 'ssh command not found.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


class ScanWorker(_StoppableMixin, QThread):
    """Scan source folder for new items."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream, force=False):
        _StoppableMixin.__init__(self)
        QThread.__init__(self)
        self._lib_config = lib_config
        self._plugin     = plugin
        self._stream     = stream
        self._force      = force

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                from modules.core.base_scanner import process_scan
                process_scan(self._lib_config, self._plugin, force=self._force)
                self.finished.emit(True, 'Scan complete.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


# ──────────────────────────────────────────────────────────────────────────────
class MetadataWorker(_StoppableMixin, QThread):
    """Fetch metadata from providers for all items in scan_list."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream, full_collection: bool = False):
        _StoppableMixin.__init__(self)
        QThread.__init__(self)
        self._lib_config      = lib_config
        self._plugin          = plugin
        self._stream          = stream
        self._full_collection = full_collection

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                from modules.core.base_metadata_processor import process_metadata
                process_metadata(self._lib_config, self._plugin,
                                 full_collection=self._full_collection,
                                 stop_fn=self.should_stop)
                self.finished.emit(True, 'Metadata fetch complete.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


# ──────────────────────────────────────────────────────────────────────────────
class MetadataRetryWorker(_StoppableMixin, QThread):
    """Re-run metadata lookup for a specific list of failed items."""
    item_result = pyqtSignal(str, bool, str)   # key, found, display_name
    finished    = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream, retry_items: list):
        _StoppableMixin.__init__(self)
        QThread.__init__(self)
        self._lib_config   = lib_config
        self._plugin       = plugin
        self._stream       = stream
        self._retry_items  = retry_items  # [{'key', 'search_name', 'original_name'}, ...]

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                import json, time
                from pathlib import Path
                from modules.providers import get_provider_class
                from modules.core.utils import load_metadata_progress, save_metadata_progress

                api_cfg = self._lib_config.api

                def _build(name):
                    if not name:
                        return None
                    try:
                        return get_provider_class(name)(api_cfg)
                    except Exception as e:
                        print(f'[Retry] Cannot load provider {name!r}: {e}')
                        return None

                primary = _build(self._lib_config.primary_provider)
                supplements = [
                    p for p in (
                        _build(n) for n in self._lib_config.supplement_providers if n
                    ) if p is not None
                ]

                if primary is None:
                    self.finished.emit(False, 'No primary provider configured.')
                    return

                primary.authenticate()
                for sup in supplements:
                    sup.authenticate()

                meta_file = self._lib_config.metadata_file
                progress  = load_metadata_progress(meta_file)
                items     = progress.setdefault('processed_items', {})

                total = len(self._retry_items)
                for i, entry in enumerate(self._retry_items, 1):
                    if self.should_stop():
                        print('[Retry] Stopped by user.')
                        break

                    key         = entry['key']
                    search_name = entry.get('search_name') or key
                    orig        = entry.get('original_name', key)

                    print(f'[{i}/{total}] Retrying: {search_name}')

                    try:
                        from modules.core.base_metadata_processor import _query_with_supplements
                        result = _query_with_supplements(primary, supplements, search_name)
                    except Exception as e:
                        print(f'  Error: {e}')
                        result = None

                    if result:
                        result['original_name'] = orig
                        result['found']         = True
                        result['igdb_found']    = True
                        result['manual']        = False
                        items[key] = result
                        print(f'  Found: {result.get("name", "")}')
                        self.item_result.emit(key, True, result.get('name', ''))
                    else:
                        if key not in items:
                            items[key] = {
                                'original_name': orig,
                                'found': False, 'igdb_found': False, 'manual': False,
                            }
                        print('  Still not found.')
                        self.item_result.emit(key, False, '')

                    time.sleep(self._lib_config.data.get('rate_limit', 0.25))

                save_metadata_progress(progress, meta_file)
                found = sum(1 for e in self._retry_items
                            if items.get(e['key'], {}).get('found'))
                self.finished.emit(True, f'{found}/{total} found on retry.')

            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


# ──────────────────────────────────────────────────────────────────────────────
class OrganizerWorker(QThread):
    """Generate organize .bat file."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream):
        super().__init__()
        self._lib_config = lib_config
        self._plugin     = plugin
        self._stream     = stream

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                from modules.core.base_organizer import BaseOrganizer
                org = BaseOrganizer(self._lib_config, self._plugin)
                org.run_headless()
                self.finished.emit(True, 'Organizer script generated.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


# ──────────────────────────────────────────────────────────────────────────────
class HTMLWorker(QThread):
    """Generate dynamic HTML library page."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream):
        super().__init__()
        self._lib_config = lib_config
        self._plugin     = plugin
        self._stream     = stream

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                from modules.core.html_generator import DynamicHTMLGenerator
                gen = DynamicHTMLGenerator(self._lib_config, self._plugin)
                gen.generate()
                self.finished.emit(True, 'HTML generated.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))


# ──────────────────────────────────────────────────────────────────────────────
class RefreshDBWorker(QThread):
    """
    Full refresh: scan → metadata → organizer → HTML.
    Runs all steps sequentially in one worker.
    """
    step_changed = pyqtSignal(str)
    finished     = pyqtSignal(bool, str)

    def __init__(self, lib_config, plugin, stream,
                 run_scan=True, run_metadata=True,
                 run_organizer=True, run_html=True):
        super().__init__()
        self._lib_config    = lib_config
        self._plugin        = plugin
        self._stream        = stream
        self._run_scan      = run_scan
        self._run_metadata  = run_metadata
        self._run_organizer = run_organizer
        self._run_html      = run_html

    def run(self):
        with _redirect_stdout(self._stream):
            try:
                if self._run_scan:
                    self.step_changed.emit('Scanning...')
                    from modules.core.base_scanner import process_scan
                    process_scan(self._lib_config, self._plugin)

                if self._run_metadata:
                    self.step_changed.emit('Fetching metadata...')
                    from modules.core.base_metadata_processor import process_metadata
                    process_metadata(self._lib_config, self._plugin)

                if self._run_organizer:
                    self.step_changed.emit('Generating organizer script...')
                    from modules.core.base_organizer import BaseOrganizer
                    BaseOrganizer(self._lib_config, self._plugin).run_headless()

                if self._run_html:
                    self.step_changed.emit('Generating HTML...')
                    from modules.core.html_generator import DynamicHTMLGenerator
                    DynamicHTMLGenerator(self._lib_config, self._plugin).generate()

                self.finished.emit(True, 'All steps complete.')
            except Exception as e:
                traceback.print_exc()
                self.finished.emit(False, str(e))
