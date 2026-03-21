"""
Wizard pages for media_manager:
- NewItemsWizard  : Scan → Metadata → Review Failures → Organize → HTML
- RefreshDBWizard : Metadata → Review Failures → HTML

Step-by-step navigation matching the game_processor wizard pattern.
"""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QSizePolicy, QMessageBox, QProgressBar, QCheckBox,
)

from modules.gui.log_widget import LogWidget


# ── Step states ──────────────────────────────────────────────────────────────
_PENDING = 'pending'
_CURRENT = 'current'
_DONE    = 'done'
_ERROR   = 'error'
_SKIPPED = 'skipped'

_STATE_CSS = {
    _PENDING: 'background:#e5e7eb; color:#6b7280;',
    _CURRENT: 'background:#2563eb; color:#ffffff;',
    _DONE:    'background:#10b981; color:#ffffff;',
    _ERROR:   'background:#ef4444; color:#ffffff;',
    _SKIPPED: 'background:#9ca3af; color:#ffffff;',
}


# ── Step indicator ────────────────────────────────────────────────────────────
class _StepIndicator(QWidget):
    def __init__(self, steps: list, parent=None):
        super().__init__(parent)
        self._pills = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        for i, label in enumerate(steps):
            pill = QLabel(f'  {i + 1}. {label}  ')
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            pill.setMinimumHeight(28)
            self._apply(pill, _PENDING)
            self._pills.append(pill)
            row.addWidget(pill)

            if i < len(steps) - 1:
                arrow = QLabel('›')
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet('color:#9ca3af; font-size:12pt;')
                arrow.setFixedWidth(18)
                row.addWidget(arrow)

    def _apply(self, pill: QLabel, state: str):
        pill.setStyleSheet(
            f'{_STATE_CSS[state]} border-radius:13px; padding:3px 8px; '
            'font-size:8.5pt; font-weight:600;'
        )

    def set_state(self, index: int, state: str):
        if 0 <= index < len(self._pills):
            self._apply(self._pills[index], state)


# ── Base wizard ───────────────────────────────────────────────────────────────
class _BaseWizard(QDialog):
    def __init__(self, title: str, steps: list, lib_config, plugin, parent=None):
        super().__init__(parent)
        self._step_defs       = steps
        self._lib_config      = lib_config
        self._plugin          = plugin
        self._current_step    = 0
        self._worker          = None
        self._finished_workers = []
        self._failures_btn    = None

        self.setWindowTitle(title)
        self.resize(720, 560)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._build_ui(title, [s['title'] for s in steps])

    def _build_ui(self, title: str, step_names: list):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)

        lbl_title = QLabel(title)
        lbl_title.setProperty('role', 'title')
        layout.addWidget(lbl_title)

        self._indicator = _StepIndicator(step_names)
        layout.addWidget(self._indicator)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setProperty('role', 'muted')
        self._desc_lbl.setMinimumHeight(52)
        layout.addWidget(self._desc_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(5)
        layout.addWidget(self._progress)

        self._log = LogWidget()
        layout.addWidget(self._log, 1)

        self._status_lbl = QLabel('')
        self._status_lbl.setMinimumHeight(18)
        layout.addWidget(self._status_lbl)

        # Nav row
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self._btn_cancel = QPushButton('Cancel')
        self._btn_cancel.setObjectName('btn_secondary')
        self._btn_cancel.clicked.connect(self._on_cancel)
        nav.addWidget(self._btn_cancel)

        nav.addStretch()

        self._btn_back = QPushButton('← Back')
        self._btn_back.setObjectName('btn_secondary')
        self._btn_back.setVisible(False)
        self._btn_back.clicked.connect(self._on_back)
        nav.addWidget(self._btn_back)

        self._btn_skip = QPushButton('Skip')
        self._btn_skip.setObjectName('btn_secondary')
        self._btn_skip.setVisible(False)
        self._btn_skip.clicked.connect(self._on_skip)
        nav.addWidget(self._btn_skip)

        self._btn_next = QPushButton('Next →')
        self._btn_next.setEnabled(False)
        self._btn_next.clicked.connect(self._on_next)
        nav.addWidget(self._btn_next)

        layout.addLayout(nav)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_wizard_started', False):
            self._wizard_started = True
            self._enter_step(0)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)

    def _enter_step(self, index: int):
        self._current_step = index
        step = self._step_defs[index]
        is_last = (index == len(self._step_defs) - 1)

        for i in range(len(self._step_defs)):
            if i < index:
                self._indicator.set_state(i, _DONE)
            elif i == index:
                self._indicator.set_state(i, _CURRENT)
            else:
                self._indicator.set_state(i, _PENDING)

        self._desc_lbl.setText(step.get('description', ''))
        self._status_lbl.setText('')
        self._status_lbl.setStyleSheet('font-size:9pt;')
        self._progress.setVisible(False)
        self._btn_back.setVisible(index > 0)
        self._btn_skip.setVisible(step.get('skippable', False))
        self._btn_skip.setEnabled(True)
        self._btn_next.setEnabled(False)
        self._btn_next.setText('Finish' if is_last else 'Next →')

        if self._failures_btn is not None:
            self._failures_btn.setVisible(False)

        self._on_enter_step(index)

    def _on_enter_step(self, index: int):
        pass

    def _on_next(self):
        if self._current_step >= len(self._step_defs) - 1:
            self.accept()
        else:
            self._enter_step(self._current_step + 1)

    def _on_back(self):
        if self._current_step > 0:
            self._enter_step(self._current_step - 1)

    def _on_skip(self):
        self._indicator.set_state(self._current_step, _SKIPPED)
        if self._current_step >= len(self._step_defs) - 1:
            self.accept()
        else:
            self._enter_step(self._current_step + 1)

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, 'Cancel Wizard',
                'An operation is running. Cancel anyway?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._worker.quit()
            self._worker.wait(3000)
        self.reject()

    def _start_worker(self, worker):
        self._worker = worker
        self._progress.setVisible(True)
        self._btn_next.setEnabled(False)
        self._btn_skip.setEnabled(False)
        self._btn_back.setEnabled(False)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_worker_finished(self, success: bool, message: str):
        if self._worker is not None:
            self._finished_workers.append(self._worker)
            QTimer.singleShot(0, self._drop_finished_workers)
        self._worker = None
        self._progress.setVisible(False)
        self._btn_back.setEnabled(True)
        self._btn_skip.setEnabled(True)

        if success:
            self._indicator.set_state(self._current_step, _DONE)
            self._btn_next.setEnabled(True)
            self._status_lbl.setStyleSheet('color:#10b981; font-size:9pt;')
            self._status_lbl.setText(message or 'Done.')
        else:
            self._indicator.set_state(self._current_step, _ERROR)
            self._btn_skip.setVisible(True)
            self._status_lbl.setStyleSheet('color:#ef4444; font-size:9pt;')
            self._status_lbl.setText(message or 'Failed — check log above.')

    def _drop_finished_workers(self):
        self._finished_workers.clear()

    # ── Shared failures helpers ──────────────────────────────────────────────
    def _count_failures(self) -> int:
        try:
            meta_file = self._lib_config.metadata_file
            if not meta_file or not Path(meta_file).exists():
                return 0
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            items = meta.get('processed_items', meta.get('processed_games', {}))
            return sum(1 for v in items.values() if not (v.get('igdb_found') or v.get('found')))
        except Exception:
            return 0

    def _show_failures_step(self):
        failed = self._count_failures()
        if failed == 0:
            self._indicator.set_state(self._current_step, _DONE)
            self._status_lbl.setStyleSheet('color:#10b981; font-size:9pt;')
            self._status_lbl.setText('No failures — all items matched successfully!')
            self._btn_next.setEnabled(True)
            return

        self._status_lbl.setStyleSheet('color:#f59e0b; font-size:9pt;')
        self._status_lbl.setText(
            f'{failed} item(s) could not be matched. '
            'Open Failed Items to fix them, or skip.'
        )
        self._btn_next.setEnabled(True)

        if self._failures_btn is None:
            self._failures_btn = QPushButton('Open Failed Items')
            self._failures_btn.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            self._failures_btn.clicked.connect(self._open_failures)
            layout = self.layout()
            layout.insertWidget(layout.count() - 1, self._failures_btn)
        self._failures_btn.setVisible(True)

    def _open_failures(self):
        from modules.gui.failed_dialog import FailedItemsDialog
        FailedItemsDialog(self._lib_config, self._plugin, self).exec()


# ══════════════════════════════════════════════════════════════════════════════
# New Items Wizard
# ══════════════════════════════════════════════════════════════════════════════
class NewItemsWizard(_BaseWizard):
    """Scan → Metadata → Review Failures → Organize → HTML"""

    def __init__(self, lib_config, plugin, parent=None):
        steps = [
            {
                'title': 'Scan',
                'description': (
                    'Scan source folder for new items and build scan_list.json.\n\n'
                    'Every subfolder (or file, depending on library type) is treated as '
                    'a new item to be processed in the next step.'
                ),
                'skippable': False,
            },
            {
                'title': 'Metadata',
                'description': (
                    'Fetch metadata from configured providers for each scanned item.\n\n'
                    'Requires valid API credentials — configure them in Settings.'
                ),
                'skippable': False,
            },
            {
                'title': 'Review Failures',
                'description': (
                    'Some items may not have been matched automatically.\n\n'
                    'Open the Failed Items dialog to manually assign genres or retry lookup. '
                    'You can skip this step and come back later via the Failed Items page.'
                ),
                'skippable': True,
            },
            {
                'title': 'Organize',
                'description': (
                    'Generate a batch script that moves items into genre folders.\n\n'
                    'Review the script before running — no files are moved until you '
                    'execute it manually.'
                ),
                'skippable': True,
            },
            {
                'title': 'Generate HTML',
                'description': (
                    'Build the dynamic HTML library page from your metadata database.\n\n'
                    'The output file can be opened in any browser and supports filtering, '
                    'sorting, and search.'
                ),
                'skippable': True,
            },
        ]
        super().__init__(f'New Items — {plugin.name}', steps, lib_config, plugin, parent)

    def _on_enter_step(self, index: int):
        if index == 0:
            self._run_scan()
        elif index == 1:
            self._run_metadata()
        elif index == 2:
            self._show_failures_step()
        elif index == 3:
            self._run_organizer()
        elif index == 4:
            self._run_html()

    def _run_scan(self):
        from modules.gui.workers import ScanWorker
        self._start_worker(
            ScanWorker(self._lib_config, self._plugin, self._log.stream, force=True)
        )

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        self._start_worker(
            MetadataWorker(self._lib_config, self._plugin, self._log.stream)
        )

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(
            OrganizerWorker(self._lib_config, self._plugin, self._log.stream)
        )

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(
            HTMLWorker(self._lib_config, self._plugin, self._log.stream)
        )


# ══════════════════════════════════════════════════════════════════════════════
# Refresh DB Wizard
# ══════════════════════════════════════════════════════════════════════════════
class RefreshDBWizard(_BaseWizard):
    """Metadata (full collection) → Review Failures → Generate HTML"""

    def __init__(self, lib_config, plugin, parent=None):
        steps = [
            {
                'title': 'Metadata',
                'description': (
                    'Re-fetch metadata for all items in the destination folder '
                    'not yet in the database.\n\n'
                    'Existing entries are preserved — only missing ones are queried. '
                    'Depending on collection size this may take several minutes.'
                ),
                'skippable': False,
            },
            {
                'title': 'Review Failures',
                'description': (
                    'Review items that could not be matched automatically.\n\n'
                    'Open the Failed Items dialog to manually assign genres or retry. '
                    'You can skip this step and come back later via the Failed Items page.'
                ),
                'skippable': True,
            },
            {
                'title': 'Generate HTML',
                'description': (
                    'Regenerate the dynamic HTML library page from the updated metadata.\n\n'
                    'The output file can be opened in any browser and supports filtering, '
                    'sorting, and search.'
                ),
                'skippable': True,
            },
        ]
        super().__init__(f'Refresh Database — {plugin.name}', steps, lib_config, plugin, parent)

    def _on_enter_step(self, index: int):
        if index == 0:
            self._run_metadata()
        elif index == 1:
            self._show_failures_step()
        elif index == 2:
            self._run_html()

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        self._start_worker(
            MetadataWorker(
                self._lib_config, self._plugin, self._log.stream,
                full_collection=True,
            )
        )

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(
            HTMLWorker(self._lib_config, self._plugin, self._log.stream)
        )


# ══════════════════════════════════════════════════════════════════════════════
# Rebuild from Scratch Wizard
# ══════════════════════════════════════════════════════════════════════════════
class RebuildWizard(_BaseWizard):
    """Wipe data → Metadata (full collection) → Review Failures → Organize → HTML"""

    def __init__(self, lib_config, plugin, parent=None):
        steps = [
            {
                'title': 'Wipe Data',
                'description': (
                    'This will permanently delete:\n'
                    '  • metadata_progress.json  (all metadata, ratings, descriptions)\n'
                    '  • scan_list.json  (pending new items list)\n\n'
                    'Your actual game files on disk are NOT touched.\n'
                    'After wiping, metadata will be re-fetched from scratch for the '
                    'entire collection.\n\n'
                    'Click  Wipe Now  to confirm and continue.'
                ),
                'skippable': False,
            },
            {
                'title': 'Metadata',
                'description': (
                    'Fetch metadata from scratch for ALL items in the destination folder.\n\n'
                    'Every genre subfolder is scanned. Already-found items from previous '
                    'runs are gone — everything is looked up fresh. '
                    'Depending on collection size this may take several minutes.'
                ),
                'skippable': False,
            },
            {
                'title': 'Review Failures',
                'description': (
                    'Review items that could not be matched automatically.\n\n'
                    'Open the Failed Items dialog to manually assign genres or retry. '
                    'You can skip this step and come back later via the Failed Items page.'
                ),
                'skippable': True,
            },
            {
                'title': 'Organize',
                'description': (
                    'Generate a batch script that moves items into genre folders.\n\n'
                    'Review the script before running — no files are moved until you '
                    'execute it manually.'
                ),
                'skippable': True,
            },
            {
                'title': 'Generate HTML',
                'description': (
                    'Build the dynamic HTML library page from the fresh metadata.\n\n'
                    'The output file can be opened in any browser and supports filtering, '
                    'sorting, and search.'
                ),
                'skippable': True,
            },
        ]
        self._wipe_btn = None
        super().__init__(f'Rebuild from Scratch — {plugin.name}', steps, lib_config, plugin, parent)

    def _on_enter_step(self, index: int):
        if index == 0:
            self._show_wipe_step()
        elif index == 1:
            self._run_metadata()
        elif index == 2:
            self._show_failures_step()
        elif index == 3:
            self._run_organizer()
        elif index == 4:
            self._run_html()

    def _show_wipe_step(self):
        if self._wipe_btn is None:
            self._wipe_btn = QPushButton('⚠  Wipe Now')
            self._wipe_btn.setStyleSheet(
                'background:#ef4444; color:#ffffff; font-weight:bold; padding:6px 18px;'
            )
            self._wipe_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._wipe_btn.clicked.connect(self._do_wipe)
            layout = self.layout()
            layout.insertWidget(layout.count() - 1, self._wipe_btn)
        self._wipe_btn.setVisible(True)
        self._btn_next.setEnabled(False)

    def _do_wipe(self):
        meta_file = Path(self._lib_config.metadata_file)
        scan_file = Path(self._lib_config.scan_list_file)

        deleted = []
        for f in (meta_file, scan_file):
            if f.exists():
                f.unlink()
                deleted.append(f.name)
                print(f'[Wipe] Deleted: {f}')
            else:
                print(f'[Wipe] Not found (skipped): {f}')

        self._wipe_btn.setVisible(False)
        self._indicator.set_state(0, _DONE)
        self._status_lbl.setStyleSheet('color:#10b981; font-size:9pt;')
        msg = (f'Deleted: {", ".join(deleted)}'
               if deleted else 'Nothing to delete — files already absent.')
        self._status_lbl.setText(msg)
        self._btn_next.setEnabled(True)

    def _run_metadata(self):
        from modules.gui.workers import MetadataWorker
        self._start_worker(
            MetadataWorker(
                self._lib_config, self._plugin, self._log.stream,
                full_collection=True,
            )
        )

    def _run_organizer(self):
        from modules.gui.workers import OrganizerWorker
        self._start_worker(
            OrganizerWorker(self._lib_config, self._plugin, self._log.stream)
        )

    def _run_html(self):
        from modules.gui.workers import HTMLWorker
        self._start_worker(
            HTMLWorker(self._lib_config, self._plugin, self._log.stream)
        )
