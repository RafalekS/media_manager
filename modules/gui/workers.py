"""
QThread workers for media_manager.
All heavy work happens off the main thread.
stdout is redirected to the LogWidget signal stream.
"""

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
    """Extract archives from source folder before scanning."""
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
