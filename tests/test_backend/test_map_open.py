"""
Regression tests for AppBackend.openMap.

The bug: maps imported in-memory (no on-disk TIFF) couldn't be opened by
double-click in the project browser because openMap fell through to a silent
``logger.warning`` after every disk-path probe failed.

The fix introduces a parallel ``loadMapInEditorById`` signal and an
``_maps_inmem`` registry; openMap now prefers the in-memory map and only
falls back to the path-based emission when no in-memory entry exists. When
neither resolves, the user gets an ``errorOccurred`` toast instead of silence.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import pytest

# AppBackend instantiation requires a QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Skip the whole module if PySide6 isn't usable in this environment.
pytest.importorskip("PySide6.QtCore")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject

from src.backend.app_backend import AppBackend


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def backend(qt_app):
    return AppBackend()


# =============================================================================
# In-memory path
# =============================================================================

class _StubMap:
    """Minimal stand-in for a MultiChannelMap; openMap only checks identity."""
    def __init__(self, name="StubMap"):
        self.name = name


def test_openMap_emits_by_id_when_inmemory(backend, qtbot=None):
    """An in-memory map id must trigger ``loadMapInEditorById``."""
    backend._maps_inmem["map_inmem_1"] = _StubMap()
    received = []
    backend.loadMapInEditorById.connect(lambda mid: received.append(mid))

    legacy = []
    backend.loadMapInEditor.connect(lambda p: legacy.append(p))

    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))

    backend.openMap("map_inmem_1")

    assert received == ["map_inmem_1"]
    # The legacy file-based signal must NOT fire for in-memory maps.
    assert legacy == []
    assert errors == []


def test_openMap_falls_back_to_disk_path(backend, tmp_path):
    """A registered ``self.maps`` entry pointing at an extant file emits the
    path-based signal."""
    f = tmp_path / "real_map.tiff"
    f.write_bytes(b"\x49\x49\x2a\x00")  # plausible TIFF magic; just needs to exist
    backend.maps.append({
        'id': "map_disk_1",
        'title': "Disk Map",
        'path': str(f),
        'timestamp': "2026-05-09 00:00:00",
    })
    received_id = []
    received_path = []
    backend.loadMapInEditorById.connect(lambda mid: received_id.append(mid))
    backend.loadMapInEditor.connect(lambda p: received_path.append(p))

    backend.openMap("map_disk_1")

    assert received_path == [str(f)]
    assert received_id == []


def test_openMap_unknown_id_emits_error(backend):
    """Unknown id must surface as ``errorOccurred`` (not silent warning)."""
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))
    backend.openMap("nonexistent")
    assert len(errors) == 1
    assert "not found" in errors[0][1].lower()


def test_openMap_registered_but_missing_file_emits_error(backend):
    """When a map is registered but its file doesn't exist on disk, the
    user must get an error instead of silence."""
    backend.maps.append({
        'id': "map_missing",
        'title': "Missing Map",
        'path': "/nonexistent/path/to/map.tiff",
        'timestamp': "2026-05-09 00:00:00",
    })
    errors = []
    received_id = []
    received_path = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))
    backend.loadMapInEditor.connect(lambda p: received_path.append(p))
    backend.loadMapInEditorById.connect(lambda mid: received_id.append(mid))

    backend.openMap("map_missing")

    assert received_path == []
    assert received_id == []
    assert len(errors) == 1


def test_getInMemoryMap_returns_stored_object(backend):
    """The ``getInMemoryMap`` slot must round-trip the stored map."""
    m = _StubMap("Z channel")
    backend._maps_inmem["m42"] = m
    assert backend.getInMemoryMap("m42") is m
    assert backend.getInMemoryMap("does_not_exist") is None
