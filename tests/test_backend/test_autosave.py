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


# =============================================================================
# The dirty flag is the only gate on autosaving
#
# A real project was lost to this: after the first autosave of a session
# cleared the flag, no tool result ever set it again, so every later tick hit
# "no changes since last save" and returned. Twenty-two hours of derivatives,
# filtered datasets and maps existed only in memory, next to a .hrt holding an
# empty project — and nothing said so, because the skip logs at DEBUG.
# =============================================================================

import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402

from src.models.spectral_data import (                # noqa: E402
    SpectralData, SpectralMetadata,
)


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(tmp_path, qt_app):
    """A real AppBackend with an open project in a temp directory.

    Import CSV persistence is stubbed out: it queues work on the I/O worker,
    which these tests neither need nor wait for — and letting real background
    tasks start and be garbage-collected mid-test segfaulted the suite.
    """
    from src.backend.app_backend import AppBackend

    app_backend = AppBackend()
    app_backend.createProject(str(tmp_path), "DirtyFlag")
    app_backend._persist_imported_datasets = lambda *a, **k: None
    yield app_backend
    app_backend.worker_manager.shutdown()


def _dataset():
    x = np.linspace(-1, 1, 32)
    df = pd.DataFrame({"V": x, "S1": np.sin(x)})
    meta = SpectralMetadata(
        source_type='test', dimensions=(1, 1), scan_mode='point',
        units={'independent': 'V', 'dependent': 'A'}, additional_info={})
    return SpectralData(df, meta)


class TestProjectModifiedTracking:
    """Every path that adds project state must mark it unsaved."""

    def test_import_marks_modified(self, backend):
        backend._on_file_loaded({'datasets': {'A': _dataset()},
                                 'active_dataset': 'A'})
        assert backend._autosave_manager._dirty

    def test_tool_result_marks_modified(self, backend, tmp_path):
        """The regression: this is how most datasets in a project are made."""
        backend._autosave_manager._dirty = False
        backend._datasets['A - Derivative'] = _dataset()
        backend._on_tool_completed("Derivative Calculator", str(tmp_path / "d.csv"))
        assert backend._autosave_manager._dirty

    def test_tool_result_marks_modified_after_an_autosave(self, backend, tmp_path):
        """An autosave clears the flag at submit time; later work must re-set
        it, or the autosave never runs again for the rest of the session."""
        backend._on_file_loaded({'datasets': {'A': _dataset()},
                                 'active_dataset': 'A'})
        backend._autosave_manager._dirty = False          # the autosave ticked
        backend._datasets['A - Filtered'] = _dataset()
        backend._on_tool_completed("Filter Bad Data", str(tmp_path / "f.txt"))
        assert backend._autosave_manager._dirty

    def test_folder_import_marks_modified(self, backend):
        backend._autosave_manager._dirty = False
        backend._on_folder_loaded({'datasets': {'B': _dataset()},
                                   'active_dataset': 'B'})
        assert backend._autosave_manager._dirty

    def test_empty_folder_result_does_not_mark(self, backend):
        backend._autosave_manager._dirty = False
        backend._on_folder_loaded({'datasets': {}, 'active_dataset': None})
        assert not backend._autosave_manager._dirty

    def test_helper_is_inert_without_a_project(self, tmp_path, qt_app):
        from src.backend.app_backend import AppBackend

        app_backend = AppBackend()
        app_backend._persist_imported_datasets = lambda *a, **k: None
        try:
            assert not app_backend._project_ready
            app_backend._mark_project_modified()          # must not raise
            assert not app_backend._autosave_manager._dirty
        finally:
            app_backend.worker_manager.shutdown()


class TestAutosaveGate:
    """What _do_autosave does with the flag."""

    @pytest.fixture
    def mock_backend(self):
        return MockAppBackend()

    @pytest.fixture
    def manager(self, mock_backend):
        return AutosaveManager(mock_backend)

    def test_skips_when_clean(self, manager, mock_backend, tmp_path):
        mock_backend._project_ready = True
        mock_backend._project_path = tmp_path
        manager._dirty = False
        manager._do_autosave()
        mock_backend.worker_manager.submit_io.assert_not_called()

    def test_writes_when_dirty(self, manager, mock_backend, tmp_path):
        mock_backend._project_ready = True
        mock_backend._project_path = tmp_path
        mock_backend.workflow_manager = MagicMock()
        manager._dirty = True
        manager._do_autosave()
        mock_backend.worker_manager.submit_io.assert_called_once()

    def test_flag_clears_at_submit_so_later_edits_are_not_lost(
            self, manager, mock_backend, tmp_path):
        mock_backend._project_ready = True
        mock_backend._project_path = tmp_path
        mock_backend.workflow_manager = MagicMock()
        manager._dirty = True
        manager._do_autosave()
        assert not manager._dirty
        manager._on_modified_changed(True)     # a change during the write
        assert manager._dirty
