"""
Tests for non-map spectra support in the Hyperspectral tab.

Covers:
- AppBackend.spatialLayout classification (area / line / point / none).
- MapEditorBackend.loadDatasetAsLineScan building the kymograph (P×N) and
  scalar strip (1×N) views and entering line-scan mode.
- Line-scan-aware spectrum lookup: a click resolves the spectrum by column
  (position index), regardless of row.
- Toggling the view and exiting line-scan mode when an area map loads.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.backend.map_editor_backend import MapEditorBackend
from src.models.map_channel import MultiChannelMap
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dataset(n_spectra, n_points, dims, scan_mode="meander", integrated=False):
    x = np.linspace(0.0, 1.0, n_points)
    cols = {"X": x}
    for j in range(n_spectra):
        # Column j is the constant j, so a recovered spectrum trivially
        # identifies which position was clicked.
        cols[f"Point_{j + 1}"] = np.full(n_points, float(j))
    df = pd.concat([pd.Series(v, name=k) for k, v in cols.items()], axis=1)
    info = {"intervals": [(0, 1)]} if integrated else {}
    meta = SpectralMetadata(
        source_type="test", dimensions=dims, scan_mode=scan_mode,
        units={}, additional_info=info,
    )
    return SpectralData(df, meta)


class _FakeApp:
    """Minimal AppBackend stand-in: just a dataset registry."""
    def __init__(self):
        self._datasets = {}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@pytest.fixture
def app(qapp):
    b = AppBackend()
    yield b
    b.worker_manager.shutdown()


@pytest.mark.parametrize("layout,kw", [
    ("area",  dict(n_spectra=16, n_points=20, dims=(4, 4))),
    ("line",  dict(n_spectra=64, n_points=20, dims=(64, 1))),
    ("line",  dict(n_spectra=64, n_points=20, dims=(1, 64))),
    ("point", dict(n_spectra=1,  n_points=20, dims=(1, 1), scan_mode="single")),
    ("point", dict(n_spectra=8,  n_points=20, dims=(8, 1), scan_mode="point")),
    ("none",  dict(n_spectra=1,  n_points=1,  dims=(10, 1))),         # < 2 points
    ("none",  dict(n_spectra=20, n_points=5,  dims=(20, 1), integrated=True)),
])
def test_spatial_layout_classification(app, layout, kw):
    app._datasets["ds"] = _dataset(**kw)
    assert app.spatialLayout("ds") == layout


def test_spatial_layout_unknown_dataset(app):
    assert app.spatialLayout("nope") == "none"


def test_dataset_info_includes_layout(app):
    app._datasets["line"] = _dataset(8, 20, (8, 1))
    info = {d["name"]: d for d in app.getDatasetListWithInfo()}
    assert info["line"]["spatial_layout"] == "line"


# ---------------------------------------------------------------------------
# Line-scan loading / views / click mapping
# ---------------------------------------------------------------------------

@pytest.fixture
def line_backend(qapp):
    P, N = 40, 12
    sd = _dataset(N, P, (N, 1))
    fake = _FakeApp()
    fake._datasets["LS"] = sd
    mb = MapEditorBackend()
    mb.set_app_backend(fake)
    return mb, sd, P, N


def test_load_kymograph_array_and_state(line_backend):
    mb, sd, P, N = line_backend
    mb.loadDatasetAsLineScan("LS", "kymograph")
    assert mb.isLineScanMode is True
    assert mb.lineScanView == "kymograph"
    assert mb.lineScanPoints == N
    assert (mb.mapRows, mb.mapCols) == (P, N)
    arr = mb._multi_channel_map.active_channel.data
    np.testing.assert_array_equal(arr, sd.spectra.values)


def test_strip_view_is_column_means(line_backend):
    mb, sd, P, N = line_backend
    mb.loadDatasetAsLineScan("LS", "strip")
    assert (mb.mapRows, mb.mapCols) == (1, N)
    arr = mb._multi_channel_map.active_channel.data
    expected = np.nanmean(sd.spectra.values, axis=0).reshape(1, -1)
    np.testing.assert_allclose(arr, expected)


def test_click_resolves_spectrum_by_column(line_backend):
    mb, sd, P, N = line_backend
    mb.loadDatasetAsLineScan("LS", "kymograph")
    # Any row, column j -> spectrum j (column j is the constant j).
    spec = mb.getSpectrumFromDataset("LS", row=33, col=7)
    assert spec["y"][0] == pytest.approx(7.0)
    # Out-of-range column clamps to the last position.
    spec2 = mb.getSpectrumFromDataset("LS", row=0, col=999)
    assert spec2["y"][0] == pytest.approx(N - 1.0)


def test_toggle_view_roundtrip(line_backend):
    mb, sd, P, N = line_backend
    mb.loadDatasetAsLineScan("LS", "kymograph")
    mb.setLineScanView("strip")
    assert (mb.mapRows, mb.mapCols) == (1, N)
    mb.setLineScanView("kymograph")
    assert (mb.mapRows, mb.mapCols) == (P, N)
    assert mb.lineScanView == "kymograph"


def test_loading_area_map_exits_line_scan_mode(line_backend):
    mb, sd, P, N = line_backend
    mb.loadDatasetAsLineScan("LS", "kymograph")
    assert mb.isLineScanMode is True
    mcm = MultiChannelMap()
    mcm.add_channel("h", np.zeros((8, 8)))
    mb.setMultiChannelMap(mcm)
    assert mb.isLineScanMode is False
