"""
Wizard pages for media_manager:
- NewItemsWizard  : scan → metadata → organizer → HTML
- RefreshDBWizard : selective steps re-run
Both are thin wrappers around the workers, not real QWizard pages.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QProgressBar, QGroupBox, QFrame,
)

from modules.gui.log_widget import LogWidget
from modules.gui.workers import (
    ScanWorker, MetadataWorker, OrganizerWorker, HTMLWorker, RefreshDBWorker,
)


class _BaseWizard(QDialog):
    """Shared infrastructure for step-based wizard dialogs."""

    def __init__(self, title: str, lib_config, plugin, parent=None):
        super().__init__(parent)
        self._lib_config = lib_config
        self._plugin     = plugin
        self._worker     = None
        self.setWindowTitle(title)
        self.resize(700, 500)
        self._setup_base_ui()

    def _setup_base_ui(self):
        layout = QVBoxLayout(self)

        self._status_lbl = QLabel('Ready.')
        self._status_lbl.setProperty('role', 'muted')
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._log = LogWidget()
        layout.addWidget(self._log, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_run = QPushButton('Run')
        self._btn_run.clicked.connect(self._run)
        btn_row.addWidget(self._btn_run)
        self._btn_close = QPushButton('Close')
        self._btn_close.setObjectName('btn_secondary')
        self._btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

    def _run(self):
        raise NotImplementedError

    def _start_worker(self, worker):
        self._worker = worker
        self._btn_run.setEnabled(False)
        self._progress.setVisible(True)
        self._worker.finished.connect(self._on_finished)
        if hasattr(self._worker, 'step_changed'):
            self._worker.step_changed.connect(self._status_lbl.setText)
        self._worker.start()

    def _on_finished(self, success: bool, message: str):
        self._progress.setVisible(False)
        self._btn_run.setEnabled(True)
        self._status_lbl.setText(('Done: ' if success else 'Error: ') + message)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
class NewItemsWizard(_BaseWizard):
    """
    Full pipeline: Scan → Metadata → Organizer → HTML.
    All steps run in sequence via RefreshDBWorker.
    """

    def __init__(self, lib_config, plugin, parent=None):
        super().__init__(f'Process New Items — {plugin.name}', lib_config, plugin, parent)
        self._setup_options()

    def _setup_options(self):
        layout = self.layout()
        grp = QGroupBox('Steps to run')
        grp_layout = QVBoxLayout(grp)

        self._chk_scan     = QCheckBox('1. Scan source folder')
        self._chk_metadata = QCheckBox('2. Fetch metadata from providers')
        self._chk_org      = QCheckBox('3. Generate organizer script (.bat)')
        self._chk_html     = QCheckBox('4. Generate HTML library page')

        for chk in (self._chk_scan, self._chk_metadata, self._chk_org, self._chk_html):
            chk.setChecked(True)
            grp_layout.addWidget(chk)

        layout.insertWidget(0, grp)

    def _run(self):
        worker = RefreshDBWorker(
            self._lib_config, self._plugin, self._log.stream,
            run_scan      = self._chk_scan.isChecked(),
            run_metadata  = self._chk_metadata.isChecked(),
            run_organizer = self._chk_org.isChecked(),
            run_html      = self._chk_html.isChecked(),
        )
        self._start_worker(worker)


# ──────────────────────────────────────────────────────────────────────────────
class RefreshDBWizard(_BaseWizard):
    """
    Refresh existing database: re-fetch metadata for all known items.
    Only runs metadata + HTML (no scan, no organizer by default).
    """

    def __init__(self, lib_config, plugin, parent=None):
        super().__init__(f'Refresh Database — {plugin.name}', lib_config, plugin, parent)
        self._setup_options()

    def _setup_options(self):
        layout = self.layout()
        grp = QGroupBox('Steps to run')
        grp_layout = QVBoxLayout(grp)

        self._chk_scan     = QCheckBox('1. Re-scan source folder')
        self._chk_metadata = QCheckBox('2. Re-fetch metadata (overwrites existing)')
        self._chk_org      = QCheckBox('3. Generate organizer script (.bat)')
        self._chk_html     = QCheckBox('4. Re-generate HTML library page')

        self._chk_scan.setChecked(False)
        self._chk_metadata.setChecked(True)
        self._chk_org.setChecked(False)
        self._chk_html.setChecked(True)

        for chk in (self._chk_scan, self._chk_metadata, self._chk_org, self._chk_html):
            grp_layout.addWidget(chk)

        layout.insertWidget(0, grp)

    def _run(self):
        worker = RefreshDBWorker(
            self._lib_config, self._plugin, self._log.stream,
            run_scan      = self._chk_scan.isChecked(),
            run_metadata  = self._chk_metadata.isChecked(),
            run_organizer = self._chk_org.isChecked(),
            run_html      = self._chk_html.isChecked(),
        )
        self._start_worker(worker)
