"""
Tests for batch importing many measurement folders at once.

Importing a queue of MATRIX day-folders used to get slower per folder as the
queue grew, because every import re-did per-item work over the *whole* project
(one browser rebuild per registered entity, one map-editor relink + one
``linkedDatasetsChanged`` per dataset). These tests pin the backend-side
contracts that make the cost per import independent of project size:

- ``getDatasetEntries`` — one bulk call replacing N ``getDatasetInfo`` calls
- ``relinkDatasetsToMapEditor`` — links everything, emits exactly once
- ``beginLinkBatch`` / ``endLinkBatch`` — suppress the per-dataset signal
- ``importFromFolder`` — a folder of measurement subfolders queues them all

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtCore")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.backend.map_editor_backend import MapEditorBackend
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qt_app):
    return AppBackend()


def _make_dataset(n_spectra=3, n_points=5):
    cols = {"V": np.linspace(-1, 1, n_points)}
    for i in range(n_spectra):
        cols[f"S{i}"] = np.random.rand(n_points)
    meta = SpectralMetadata(
        source_type="test", dimensions=(n_spectra, 1),
        scan_mode="point", units={},
    )
    return SpectralData(pd.DataFrame(cols), meta)


# =============================================================================
# getDatasetEntries — bulk replacement for per-dataset getDatasetInfo
# =============================================================================

def test_get_dataset_entries_matches_get_dataset_info(backend):
    backend._datasets["a"] = _make_dataset()
    backend._datasets["b"] = _make_dataset(n_spectra=2, n_points=7)

    entries = backend.getDatasetEntries()
    assert [e["name"] for e in entries] == ["a", "b"]

    for entry in entries:
        info = backend.getDatasetInfo(entry["name"])
        for key in ("name", "type", "dimensions", "num_spectra",
                    "num_points", "independent_var"):
            assert entry[key] == info[key], key


def test_get_dataset_entries_empty(backend):
    assert backend.getDatasetEntries() == []


def test_get_dataset_entries_skips_broken_dataset(backend):
    """A dataset that raises must not empty the whole browser."""
    class Broken:
        @property
        def metadata(self):
            raise RuntimeError("boom")

    backend._datasets["ok"] = _make_dataset()
    backend._datasets["bad"] = Broken()

    assert [e["name"] for e in backend.getDatasetEntries()] == ["ok"]


# =============================================================================
# Map-editor relinking: one call, one signal
# =============================================================================

def test_relink_emits_once_regardless_of_dataset_count(backend):
    me = MapEditorBackend()
    backend.setMapEditorBackend(me)
    for i in range(12):
        backend._datasets[f"ds{i}"] = _make_dataset()

    fired = []
    me.linkedDatasetsChanged.connect(lambda: fired.append(1))
    backend.relinkDatasetsToMapEditor()

    assert len(me._linked_datasets) == 12
    assert len(fired) == 1, "one batched signal, not one per dataset"


def test_relink_skips_integrated_datasets(backend):
    me = MapEditorBackend()
    backend.setMapEditorBackend(me)
    backend._datasets["spectra"] = _make_dataset()
    integrated = _make_dataset()
    integrated.metadata.additional_info["intervals"] = [[0.0, 1.0]]
    backend._datasets["integrated"] = integrated

    backend.relinkDatasetsToMapEditor()
    assert list(me._linked_datasets) == ["spectra"]


def test_relink_activates_truncated_dataset_first(backend):
    """Link order must keep the previous 'truncated wins' activation rule."""
    me = MapEditorBackend()
    backend.setMapEditorBackend(me)
    backend._datasets["a_raw"] = _make_dataset()
    backend._datasets["z_truncated"] = _make_dataset()

    backend.relinkDatasetsToMapEditor()
    assert me._active_dataset == "z_truncated"


def test_relink_replaces_previous_links(backend):
    me = MapEditorBackend()
    backend.setMapEditorBackend(me)
    me.linkDataset("stale", _make_dataset())

    backend._datasets["fresh"] = _make_dataset()
    backend.relinkDatasetsToMapEditor()
    assert list(me._linked_datasets) == ["fresh"]


def test_relink_without_map_editor_is_a_noop(backend):
    backend._datasets["a"] = _make_dataset()
    backend.relinkDatasetsToMapEditor()  # must not raise


def test_link_batch_suppresses_and_emits_once():
    me = MapEditorBackend()
    fired = []
    me.linkedDatasetsChanged.connect(lambda: fired.append(1))

    me.beginLinkBatch()
    me.clearLinkedDatasets()
    me.linkDataset("a", _make_dataset())
    me.linkDataset("b", _make_dataset())
    assert fired == []
    me.endLinkBatch()

    assert len(fired) == 1
    assert list(me._linked_datasets) == ["a", "b"]


def test_link_dataset_still_emits_outside_a_batch():
    me = MapEditorBackend()
    fired = []
    me.linkedDatasetsChanged.connect(lambda: fired.append(1))
    me.linkDataset("a", _make_dataset())
    assert len(fired) == 1


# =============================================================================
# Folder-of-folders import
# =============================================================================

def _matrix_folder(root, name):
    d = root / name
    d.mkdir()
    (d / "sample--1_1.I(V)_mtrx").write_bytes(b"stub")
    return d


def test_folder_of_session_folders_queues_each(backend, tmp_path, monkeypatch):
    parent = tmp_path / "STM UHV"
    parent.mkdir()
    subs = [_matrix_folder(parent, n)
            for n in ("21-Jul-2026", "22-Jul-2026", "24-Jul-2026")]
    (parent / "notes").mkdir()  # no data — must be skipped

    queued = []
    monkeypatch.setattr(backend, "_import_folder_path", queued.append)
    backend.importFromFolder(str(parent))

    assert queued == sorted(subs)


def test_folder_with_own_data_imports_itself(backend, tmp_path, monkeypatch):
    """A session folder must still import as ONE folder, not per subfolder."""
    session = _matrix_folder(tmp_path, "21-Jul-2026")
    (session / "extra").mkdir()
    (session / "extra" / "other.nid").write_bytes(b"stub")

    queued = []
    monkeypatch.setattr(backend, "_import_folder_path", queued.append)
    backend.importFromFolder(str(session))

    assert queued == [session]


def test_empty_folder_still_imports_itself(backend, tmp_path, monkeypatch):
    """No data anywhere → import the folder and let the loader report why."""
    empty = tmp_path / "nothing"
    empty.mkdir()

    queued = []
    monkeypatch.setattr(backend, "_import_folder_path", queued.append)
    backend.importFromFolder(str(empty))

    assert queued == [empty]


# =============================================================================
# Cloud-placeholder (iCloud "Optimize Mac Storage") pre-flight
# =============================================================================

class _FakeStat:
    def __init__(self, size, blocks):
        self.st_size = size
        self.st_blocks = blocks


def _as_placeholders(monkeypatch, *names):
    """Make the named files report as dataless cloud placeholders."""
    real = Path.stat

    def fake(self, *a, **k):
        if self.name in names:
            return _FakeStat(4200, 0)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "stat", fake)


def test_count_dataless_flags_zero_block_files(tmp_path, monkeypatch):
    a = tmp_path / "a.I(V)_mtrx"; a.write_bytes(b"x" * 10)
    b = tmp_path / "b.I(V)_mtrx"; b.write_bytes(b"x" * 10)
    _as_placeholders(monkeypatch, "a.I(V)_mtrx")

    assert AppBackend._count_dataless([a, b]) == (1, 2)


def test_count_dataless_ignores_empty_files(tmp_path):
    """A genuinely empty file has 0 blocks but is not a placeholder."""
    e = tmp_path / "empty.I(V)_mtrx"
    e.write_bytes(b"")
    assert AppBackend._count_dataless([e]) == (0, 1)


def test_load_folder_refuses_undownloaded_folder(backend, tmp_path,
                                                 monkeypatch):
    d = _matrix_folder(tmp_path, "01-Jul-2026")
    _as_placeholders(monkeypatch, "sample--1_1.I(V)_mtrx")

    task = type("T", (), {"cancelled": False})()
    with pytest.raises(ValueError) as exc:
        backend._do_load_folder(task, d)

    msg = str(exc.value)
    assert "not downloaded" in msg
    assert "iCloud" in msg
    assert "Download Now" in msg


def test_load_folder_proceeds_when_files_are_local(backend, tmp_path):
    """A fully-downloaded folder must NOT trip the pre-flight."""
    d = _matrix_folder(tmp_path, "01-Jul-2026")
    task = type("T", (), {"cancelled": False})()
    # The stub file isn't real MATRIX data, so the loader fails later — the
    # point is that it gets past _check_downloaded.
    try:
        backend._do_load_folder(task, d)
    except ValueError as e:
        assert "not downloaded" not in str(e)
    except Exception:
        pass


def test_check_downloaded_is_quiet_for_unreadable_dir(backend, tmp_path):
    backend._check_downloaded(tmp_path / "does-not-exist")  # must not raise


# =============================================================================
# Cancellation / no-result handling
# =============================================================================

def test_on_folder_loaded_tolerates_none(backend):
    backend._on_folder_loaded(None)  # cancelled load must not crash


def test_on_file_loaded_tolerates_none(backend):
    backend._on_file_loaded(None)


@pytest.mark.parametrize("filename", [
    "a.nid", "a.txt", "sample--1_1.I(V)_mtrx", "img_0001.mtrx",
    "topo.Z_flat", "curr.I_flat",
])
def test_folder_has_data_recognizes_every_supported_format(tmp_path, filename):
    (tmp_path / filename).write_bytes(b"stub")
    assert AppBackend._folder_has_data(tmp_path)


def test_folder_has_data_rejects_unrelated_files(tmp_path):
    (tmp_path / "readme.md").write_bytes(b"stub")
    (tmp_path / "photo.png").write_bytes(b"stub")
    assert not AppBackend._folder_has_data(tmp_path)
