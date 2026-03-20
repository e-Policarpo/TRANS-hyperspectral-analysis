"""
Autosave Manager for T.R.A.N.S. application.
Provides periodic automatic saving and crash recovery.
"""

import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QTimer

logger = logging.getLogger(__name__)


class AutosaveManager(QObject):
    """Periodic autosave with crash recovery."""

    recoveryAvailable = Signal(str, str, arguments=['autosavePath', 'mainPath'])

    def __init__(self, app_backend, parent=None):
        super().__init__(parent)
        self._app_backend = app_backend
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._do_autosave)
        self._interval_ms = 5 * 60 * 1000  # 5 minutes default
        self._enabled = True

    @Slot(bool)
    def setEnabled(self, enabled: bool):
        """Enable or disable autosave."""
        self._enabled = enabled
        if not enabled:
            self._timer.stop()
        elif self._app_backend._project_ready:
            self._timer.start(self._interval_ms)
        logger.info(f"Autosave {'enabled' if enabled else 'disabled'}")

    @Slot(int)
    def setIntervalMinutes(self, minutes: int):
        """Set autosave interval in minutes."""
        minutes = max(1, min(60, minutes))
        self._interval_ms = minutes * 60 * 1000
        if self._timer.isActive():
            self._timer.start(self._interval_ms)
        logger.info(f"Autosave interval set to {minutes} minutes")

    @Slot(result=bool)
    def isEnabled(self) -> bool:
        return self._enabled

    @Slot(result=int)
    def intervalMinutes(self) -> int:
        return self._interval_ms // (60 * 1000)

    def start(self):
        """Start autosave timer."""
        if self._enabled:
            self._timer.start(self._interval_ms)
            logger.info(f"Autosave started (interval: {self._interval_ms // 1000}s)")

    def stop(self):
        """Stop autosave timer."""
        self._timer.stop()
        logger.info("Autosave stopped")

    def _do_autosave(self):
        """Save to .autosave.hrt next to the main project file."""
        if not self._app_backend._project_ready or not self._app_backend._project_path:
            return

        project_path = self._app_backend._project_path
        project_name = self._app_backend._project_name
        autosave_path = project_path / f"{project_name}.autosave.hrt"

        self._app_backend.worker_manager.submit(
            name="Autosave",
            operation=self._app_backend._do_save_project,
            project_path=autosave_path,
            on_finished=lambda _: logger.info(f"Autosaved: {autosave_path}")
        )

    def check_recovery(self, project_path: Path):
        """Check if autosave is newer than main file."""
        if isinstance(project_path, str):
            project_path = Path(project_path)

        project_dir = project_path.parent if project_path.suffix == '.hrt' else project_path
        project_name = project_path.stem if project_path.suffix == '.hrt' else project_path.name

        # Look for autosave file
        autosave_path = project_dir / f"{project_name}.autosave.hrt"
        main_path = project_dir / f"{project_name}.hrt"

        if autosave_path.exists() and main_path.exists():
            if autosave_path.stat().st_mtime > main_path.stat().st_mtime:
                logger.info(f"Recovery available: {autosave_path}")
                self.recoveryAvailable.emit(str(autosave_path), str(main_path))

    @Slot(str)
    def recoverFromAutosave(self, autosave_path: str):
        """Load from autosave file."""
        logger.info(f"Recovering from autosave: {autosave_path}")
        self._app_backend.openProjectFile(autosave_path)

    @Slot(str)
    def discardAutosave(self, autosave_path: str):
        """Delete autosave file."""
        try:
            Path(autosave_path).unlink(missing_ok=True)
            logger.info(f"Discarded autosave: {autosave_path}")
        except Exception as e:
            logger.error(f"Error discarding autosave: {e}")
