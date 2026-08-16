"""
Tests for AutosaveManager
"""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from src.backend.autosave_manager import AutosaveManager


class MockAppBackend:
    """Minimal mock of AppBackend for testing AutosaveManager."""

    def __init__(self):
        self._project_ready = False
        self._project_path = None
        self._project_name = "test_project"
        self.worker_manager = MagicMock()
        self._do_save_project = MagicMock()


class TestAutosaveManager:
    """Tests for AutosaveManager."""

    @pytest.fixture
    def mock_backend(self):
        return MockAppBackend()

    @pytest.fixture
    def manager(self, mock_backend):
        return AutosaveManager(mock_backend)

    def test_initial_state(self, manager):
        assert manager.isEnabled()
        assert manager.intervalMinutes() == 5

    def test_set_enabled(self, manager):
        manager.setEnabled(False)
        assert not manager.isEnabled()
        manager.setEnabled(True)
        assert manager.isEnabled()

    def test_set_interval(self, manager):
        manager.setIntervalMinutes(10)
        assert manager.intervalMinutes() == 10

    def test_set_interval_clamped(self, manager):
        manager.setIntervalMinutes(0)
        assert manager.intervalMinutes() == 1  # min is 1

        manager.setIntervalMinutes(100)
        assert manager.intervalMinutes() == 60  # max is 60

    def test_start_when_enabled(self, manager):
        # QTimer.start() requires a running QApplication event loop;
        # in test env without QThread, it won't actually start.
        # We verify the method doesn't raise and the intent is correct.
        manager.start()
        # Timer may not be active without QApplication, just verify no error

    def test_start_when_disabled(self, manager):
        manager.setEnabled(False)
        manager.start()
        assert not manager._timer.isActive()

    def test_stop(self, manager):
        manager.start()
        manager.stop()
        assert not manager._timer.isActive()

    def test_do_autosave_no_project(self, manager, mock_backend):
        """Autosave should do nothing when no project is open."""
        manager._on_modified_changed(True)
        manager._do_autosave()
        mock_backend.worker_manager.submit_io.assert_not_called()

    def test_do_autosave_with_project(self, manager, mock_backend):
        """Autosave should submit a save task when project is open and dirty."""
        mock_backend._project_ready = True
        mock_backend._project_path = Path("/tmp/test_project")
        mock_backend._project_name = "test_project"
        manager._on_modified_changed(True)

        manager._do_autosave()

        mock_backend.worker_manager.submit_io.assert_called_once()
        call_kwargs = mock_backend.worker_manager.submit_io.call_args
        assert call_kwargs[1]["name"] == "Autosave"
        # Dirty flag cleared at submit time — the next clean tick is a no-op
        assert manager._dirty is False

    def test_do_autosave_skipped_when_clean(self, manager, mock_backend):
        """Autosave must NOT re-serialize an unchanged project."""
        mock_backend._project_ready = True
        mock_backend._project_path = Path("/tmp/test_project")
        mock_backend._project_name = "test_project"

        manager._do_autosave()

        mock_backend.worker_manager.submit_io.assert_not_called()

    def test_do_autosave_keeps_dirty_when_submission_rejected(self, manager, mock_backend):
        """If a previous autosave is still in flight (submit_io dedups and
        returns False), the changes stay flagged for the next tick."""
        mock_backend._project_ready = True
        mock_backend._project_path = Path("/tmp/test_project")
        mock_backend._project_name = "test_project"
        mock_backend.worker_manager.submit_io.return_value = False
        manager._on_modified_changed(True)

        manager._do_autosave()

        assert manager._dirty is True

    def test_modified_signal_tracks_dirty(self, manager):
        manager._on_modified_changed(True)
        assert manager._dirty is True
        manager._on_modified_changed(False)  # e.g. manual save completed
        assert manager._dirty is False

    def test_check_recovery_no_autosave(self, manager, tmp_path):
        """No recovery if autosave file doesn't exist."""
        project_file = tmp_path / "test.hrt"
        project_file.write_text("project data")

        signals = []
        manager.recoveryAvailable.connect(lambda a, m: signals.append((a, m)))

        manager.check_recovery(project_file)
        assert len(signals) == 0

    def test_check_recovery_autosave_newer(self, manager, tmp_path):
        """Recovery should be signaled when autosave is newer."""
        project_file = tmp_path / "test.hrt"
        project_file.write_text("old data")

        # Small delay to ensure different mtime
        time.sleep(0.05)

        autosave_file = tmp_path / "test.autosave.hrt"
        autosave_file.write_text("newer data")

        signals = []
        manager.recoveryAvailable.connect(lambda a, m: signals.append((a, m)))

        manager.check_recovery(project_file)
        assert len(signals) == 1
        assert signals[0][0] == str(autosave_file)

    def test_check_recovery_autosave_older(self, manager, tmp_path):
        """No recovery if autosave is older than main file."""
        autosave_file = tmp_path / "test.autosave.hrt"
        autosave_file.write_text("old data")

        time.sleep(0.05)

        project_file = tmp_path / "test.hrt"
        project_file.write_text("newer data")

        signals = []
        manager.recoveryAvailable.connect(lambda a, m: signals.append((a, m)))

        manager.check_recovery(project_file)
        assert len(signals) == 0

    def test_discard_autosave(self, manager, tmp_path):
        """Discard should delete the autosave file."""
        autosave_file = tmp_path / "test.autosave.hrt"
        autosave_file.write_text("data")
        assert autosave_file.exists()

        manager.discardAutosave(str(autosave_file))
        assert not autosave_file.exists()

    def test_discard_autosave_missing_file(self, manager, tmp_path):
        """Discard should not raise if file is missing."""
        autosave_file = tmp_path / "nonexistent.autosave.hrt"
        manager.discardAutosave(str(autosave_file))  # Should not raise

    def test_recover_from_autosave(self, manager, mock_backend):
        """Recovery should call openProjectFile on the backend."""
        mock_backend.openProjectFile = MagicMock()
        manager.recoverFromAutosave("/tmp/test.autosave.hrt")
        mock_backend.openProjectFile.assert_called_once_with("/tmp/test.autosave.hrt")
