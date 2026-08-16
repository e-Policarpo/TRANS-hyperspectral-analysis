"""
Tests for physical (nm / µm) map axes.

Omicron scan maps carry a real scan-window size; the Hyperspectral viewer used
to label its axes with bare pixel indices. These cover the canvas-side extent
state and the backend-side unit conversion that feeds it.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.backend.map_editor_backend import MapEditorBackend
from src.models.map_channel import (
    ChannelType, MapMetadata, MultiChannelMap,
)


# ---------------------------------------------------------------------------
# Canvas-side state
# ---------------------------------------------------------------------------

@pytest.fixture
def canvas(qt_app_or_skip):
    from src.widgets.qml_map_canvas import QMLMapCanvas
    c = QMLMapCanvas()
    c.setMapData(np.random.default_rng(0).random((32, 40)))
    yield c
    c.cleanup()


@pytest.fixture(scope="module")
def qt_app_or_skip():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_extent_defaults_to_none_pixel_indices(canvas):
    assert canvas._phys_extent is None


def test_set_physical_extent_stores_sizes_and_unit(canvas):
    canvas.setPhysicalExtent(50.0, 40.0, "nm")
    assert canvas._phys_extent == (50.0, 40.0, "nm")


def test_clear_physical_extent_reverts_to_pixels(canvas):
    canvas.setPhysicalExtent(50.0, 40.0, "nm")
    canvas.clearPhysicalExtent()
    assert canvas._phys_extent is None


@pytest.mark.parametrize("x,y", [(0.0, 10.0), (10.0, 0.0), (-5.0, 10.0)])
def test_non_positive_extent_is_rejected(canvas, x, y):
    """A degenerate scan size must fall back to pixel indices, not produce a
    divide-by-zero in the tick layout."""
    canvas.setPhysicalExtent(x, y, "nm")
    assert canvas._phys_extent is None


def test_default_unit_is_nm(canvas):
    canvas.setPhysicalExtent(50.0, 40.0)
    assert canvas._phys_extent[2] == "nm"


def test_native_axes_render_with_physical_extent(canvas):
    """The native painter path must survive a physical extent end-to-end
    (it computes tick positions as x / x_max)."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRectF

    canvas.setPhysicalExtent(50.0, 40.0, "nm")
    img = QImage(320, 240, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    painter = QPainter(img)
    try:
        canvas._native_draw_axes(painter, QRectF(40, 10, 250, 190))
    finally:
        painter.end()
    # Something was drawn (axis frame + ticks + unit titles).
    assert any(img.pixel(x, 10) != 0 for x in range(40, 290))


# ---------------------------------------------------------------------------
# Backend-side unit conversion
# ---------------------------------------------------------------------------

class _SpyCanvas:
    """Records what the backend pushes to the canvas."""

    def __init__(self):
        self.extent = "unset"

    def setMapData(self, *a, **k):
        pass

    def setPhysicalExtent(self, x, y, unit):
        self.extent = (x, y, unit)

    def clearPhysicalExtent(self):
        self.extent = None


def _map_with_size(size, units):
    mcm = MultiChannelMap()
    mcm.add_channel("Z", np.zeros((64, 64)), ChannelType.HEIGHT, "m")
    mcm.metadata = MapMetadata(
        dimensions=(64, 64), physical_size=size, physical_units=units)
    return mcm


@pytest.mark.parametrize("size,units,expected", [
    # Omicron writes metres. 20 nm scan stays in nm...
    ((20e-9, 20e-9), "m", (20.0, 20.0, "nm")),
    # ...a 2 µm scan switches to µm so the labels stay readable.
    ((2e-6, 2e-6), "m", (2.0, 2.0, "µm")),
    # Right at the 1000 nm switch point.
    ((1e-6, 1e-6), "m", (1.0, 1.0, "µm")),
    ((999e-9, 999e-9), "m", (999.0, 999.0, "nm")),
    # Other source units.
    ((0.5, 0.5), "um", (500.0, 500.0, "nm")),
    ((30.0, 30.0), "nm", (30.0, 30.0, "nm")),
])
def test_physical_extent_unit_conversion(size, units, expected):
    backend = MapEditorBackend()
    spy = _SpyCanvas()
    backend._canvas = spy
    backend._push_physical_extent(_map_with_size(size, units))
    x, y, unit = spy.extent
    assert unit == expected[2]
    assert x == pytest.approx(expected[0])
    assert y == pytest.approx(expected[1])


def test_extent_maps_x_from_width_and_y_from_height():
    """physical_size is (y, x); the canvas takes (x, y). A non-square scan
    catches a swap."""
    backend = MapEditorBackend()
    spy = _SpyCanvas()
    backend._canvas = spy
    backend._push_physical_extent(_map_with_size((10e-9, 40e-9), "m"))
    x, y, unit = spy.extent
    assert (x, y) == pytest.approx((40.0, 10.0))
    assert unit == "nm"


@pytest.mark.parametrize("size", [None, (0, 0), (None, 5e-9), (5e-9, 0)])
def test_uncalibrated_map_reverts_to_pixel_axes(size):
    backend = MapEditorBackend()
    spy = _SpyCanvas()
    backend._canvas = spy
    backend._push_physical_extent(_map_with_size(size, "m"))
    assert spy.extent is None


def test_unknown_unit_is_passed_through_not_misscaled():
    """An unrecognised unit must not be silently treated as metres (a 1e9
    error); show the raw numbers under their own label instead."""
    backend = MapEditorBackend()
    spy = _SpyCanvas()
    backend._canvas = spy
    backend._push_physical_extent(_map_with_size((3.0, 4.0), "Å"))
    assert spy.extent == (4.0, 3.0, "Å")


def test_push_is_a_noop_for_canvas_without_the_slot():
    """Older/mock canvases lacking setPhysicalExtent must not crash the load."""
    backend = MapEditorBackend()
    backend._canvas = object()
    backend._push_physical_extent(_map_with_size((20e-9, 20e-9), "m"))


def test_set_multi_channel_map_refreshes_extent():
    """Loading an uncalibrated map after a calibrated one must clear the axes,
    not inherit the previous scan's size."""
    backend = MapEditorBackend()
    spy = _SpyCanvas()
    backend._canvas = spy
    backend.setMultiChannelMap(_map_with_size((20e-9, 20e-9), "m"))
    assert spy.extent == (20.0, 20.0, "nm")
    backend.setMultiChannelMap(_map_with_size(None, "m"))
    assert spy.extent is None
