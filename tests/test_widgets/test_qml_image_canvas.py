"""
Tests for QMLImageCanvas data-shaping logic.

The QML scene-graph rendering itself can't be exercised without a running
window, but the data-side machinery (LUT generation, range remap, histogram
extraction, crop bounds clamping) can be unit-tested in isolation.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QGuiApplication

from src.models.image_data import ImageData, ImageMode
from src.widgets.qml_image_canvas import QMLImageCanvas, _get_lut


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    return QMLImageCanvas()


# =============================================================================
# LUT helpers
# =============================================================================

def test_lut_returns_256x3_uint8():
    lut = _get_lut("viridis")
    assert lut.shape == (256, 3)
    assert lut.dtype == np.uint8


def test_lut_unknown_name_falls_back_to_grayscale():
    lut = _get_lut("nonexistent_colormap_zzz")
    assert lut.shape == (256, 3)
    # Diagonal should be a ramp.
    assert lut[0, 0] == 0
    assert lut[255, 0] == 255


def test_lut_caching_returns_same_object():
    a = _get_lut("hot")
    b = _get_lut("hot")
    assert a is b


# =============================================================================
# QImage construction for each mode
# =============================================================================

def test_set_image_data_rgb_builds_qimage(canvas):
    arr = np.random.randint(0, 255, (8, 12, 3), dtype=np.uint8)
    img = ImageData.from_array(arr)
    canvas.setImageData(img)
    canvas._ensure_qimage()
    assert canvas._qimage is not None
    assert canvas._qimage.width() == 12
    assert canvas._qimage.height() == 8
    assert canvas.imageMode == "rgb"
    assert canvas.imageWidth == 12
    assert canvas.imageHeight == 8


def test_set_image_data_single_float_default_is_grayscale(canvas):
    """Default colormap ``original`` should produce a native Grayscale8 QImage
    — the cleanest possible single-channel pipeline (no LUT round-trip).
    """
    arr = np.linspace(0, 1, 8 * 12, dtype=np.float32).reshape(8, 12)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT)
    canvas.setImageData(img)
    canvas._ensure_qimage()
    qimg = canvas._qimage
    assert qimg is not None
    assert qimg.format().name == "Format_Grayscale8"


def test_set_image_data_single_float_with_colormap_uses_rgb(canvas):
    """Picking a fancy colormap switches to the LUT path and Format_RGB888."""
    arr = np.linspace(0, 1, 8 * 12, dtype=np.float32).reshape(8, 12)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT)
    canvas.setImageData(img)
    canvas.colormap = "viridis"
    canvas._ensure_qimage()
    qimg = canvas._qimage
    assert qimg is not None
    assert qimg.format().name == "Format_RGB888"


def test_set_image_data_uint16_remaps_with_range(canvas):
    arr = np.linspace(0, 65535, 4 * 6, dtype=np.uint16).reshape(4, 6)
    img = ImageData.from_array(arr, mode=ImageMode.GRAY_U16)
    canvas.setImageData(img)
    # auto_range should populate display_min/max.
    assert canvas.displayMin >= 0
    assert canvas.displayMax > canvas.displayMin


def test_displayMin_setter_triggers_rebuild(canvas):
    arr = np.random.rand(4, 6).astype(np.float32)
    img = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT)
    canvas.setImageData(img)
    canvas._ensure_qimage()
    canvas._needs_remap = False  # pretend we have a fresh build
    canvas.displayMin = canvas.displayMin - 0.1
    assert canvas._needs_remap is True


def test_colormap_setter_changes_property(canvas):
    canvas.colormap = "hot"
    assert canvas.colormap == "hot"
    canvas.colormap = "gray"
    assert canvas.colormap == "gray"


# =============================================================================
# Histogram + auto-range
# =============================================================================

def test_get_histogram_returns_bins_count(canvas):
    arr = np.random.rand(20, 30).astype(np.float32)
    img = ImageData.from_array(arr)
    canvas.setImageData(img)
    counts = canvas.getHistogram(32)
    assert isinstance(counts, list)
    assert len(counts) == 32
    assert sum(counts) == 20 * 30


def test_auto_range_sets_min_max(canvas):
    arr = np.random.rand(10, 10).astype(np.float32) * 100
    img = ImageData.from_array(arr)
    canvas.setImageData(img)
    res = canvas.autoRange(2.0)
    assert "min" in res and "max" in res
    assert res["min"] < res["max"]
    assert canvas.displayMin == res["min"]
    assert canvas.displayMax == res["max"]


def test_get_histogram_no_image_returns_empty(canvas):
    canvas.setImageData(None)
    assert canvas.getHistogram(32) == []
    assert canvas.hasImage is False


# =============================================================================
# Crop tooling
# =============================================================================

def test_begin_crop_sets_active_state(canvas):
    img = ImageData.from_array(np.zeros((10, 10), dtype=np.uint8))
    canvas.setImageData(img)
    canvas.beginCrop()
    assert canvas.cropActive is True
    canvas.cancelCrop()
    assert canvas.cropActive is False


def test_apply_crop_emits_signal(canvas):
    img = ImageData.from_array(np.zeros((10, 10), dtype=np.uint8))
    canvas.setImageData(img)
    canvas._crop_rect = QRectF(2, 3, 4, 5)
    canvas.cropRectChanged.emit()
    received = []
    canvas.cropApplied.connect(lambda d: received.append(d))
    canvas.applyCrop()
    assert len(received) == 1
    rect = received[0]
    # Either delivered as dict from our cropRect getter or a QRectF —
    # the dict form is what QML actually receives.
    assert rect == {"x0": 2.0, "y0": 3.0, "x1": 6.0, "y1": 8.0}


def test_reset_crop_clears(canvas):
    img = ImageData.from_array(np.zeros((10, 10), dtype=np.uint8))
    canvas.setImageData(img)
    canvas._crop_rect = QRectF(0, 0, 5, 5)
    canvas.resetCrop()
    assert canvas.cropRect == {}
    assert canvas.cropActive is False


# =============================================================================
# Wheel zoom: sensitivity + zoom-out floor
# =============================================================================

def _zoomable_canvas(canvas, img_w=400, img_h=400, view_w=200, view_h=200):
    """Canvas with a known image + widget geometry so ``_fit_scale`` is
    deterministic. Default: 400px image in a 200px view → fit_scale 0.5."""
    img = ImageData.from_array(np.zeros((img_h, img_w), dtype=np.uint8))
    canvas.setImageData(img)
    canvas.setWidth(view_w)
    canvas.setHeight(view_h)
    return canvas


def test_fit_scale_matches_geometry(canvas):
    _zoomable_canvas(canvas)  # 400px image in 200px view
    assert canvas._fit_scale() == pytest.approx(0.5)


def test_one_full_notch_is_a_single_1_1x_step(canvas):
    _zoomable_canvas(canvas)
    canvas._fit_to_window = False
    canvas._zoom = 1.0
    canvas._zoom_by_delta(120)  # one mouse notch
    assert canvas._zoom == pytest.approx(1.1)


def test_subnotch_trackpad_delta_zooms_proportionally_less(canvas):
    """A 10-unit trackpad delta must move far less than a full 120 notch —
    the old code applied a full 1.1× per event regardless."""
    _zoomable_canvas(canvas)
    canvas._fit_to_window = False
    canvas._zoom = 1.0
    canvas._zoom_by_delta(10)
    assert 1.0 < canvas._zoom < 1.02


def test_zoom_out_cannot_go_below_fit_scale(canvas):
    _zoomable_canvas(canvas)  # fit_scale 0.5
    canvas._fit_to_window = False
    canvas._zoom = 0.5
    for _ in range(20):
        canvas._zoom_by_delta(-120)
    assert canvas._zoom == pytest.approx(0.5)


def test_leaving_fit_to_window_starts_from_fit_scale(canvas):
    """First wheel step out of fit-to-window must be continuous (seed
    ``_zoom`` from the fitted scale, not the stale 1.0)."""
    _zoomable_canvas(canvas)  # fit_scale 0.5
    canvas._fit_to_window = True
    canvas._zoom = 1.0  # stale value while fit-to-window
    canvas._zoom_by_delta(-120)  # try to zoom out
    # Seeded to 0.5 then clamped at the 0.5 floor — no jump up to ~0.9.
    assert canvas._zoom == pytest.approx(0.5)
    assert canvas._fit_to_window is False


def test_small_image_floor_is_one_to_one(canvas):
    """Image smaller than the view (fit_scale > 1): zoom-out floor is 1:1,
    not the >1 fit scale."""
    _zoomable_canvas(canvas, img_w=100, img_h=100, view_w=400, view_h=400)
    assert canvas._fit_scale() == pytest.approx(4.0)
    canvas._fit_to_window = False
    canvas._zoom = 1.0
    for _ in range(20):
        canvas._zoom_by_delta(-120)
    assert canvas._zoom == pytest.approx(1.0)


def test_zoom_in_capped_at_max(canvas):
    _zoomable_canvas(canvas)
    canvas._fit_to_window = False
    canvas._zoom = 1.0
    for _ in range(200):
        canvas._zoom_by_delta(120)
    assert canvas._zoom == pytest.approx(canvas._MAX_ZOOM)


# ----------------------------------------------------------- scale ruler

def test_nice_step_rounds_to_1_2_5():
    ns = QMLImageCanvas._nice_step
    assert ns(0.3) == 0.5
    assert ns(0.7) == 1.0
    assert ns(3) == 5.0
    assert ns(7) == 10.0
    assert ns(23) == 50.0
    assert ns(90) == 100.0
    assert ns(0) == 1.0          # degenerate input is safe


def test_fmt_tick_decimals_track_step():
    f = QMLImageCanvas._fmt_tick
    assert f(100.0, 50.0) == "100"      # integer step → no decimals
    assert f(0.5, 0.5) == "0.5"          # sub-unit step → one decimal
    assert f(0.4, 0.2) == "0.4"          # nice steps are only 1/2/5 ×10ⁿ


def test_ruler_paints_for_physical_and_pixel_images(canvas):
    """The border ruler must paint without error for an image that carries a
    physical pixel size (nm) and for one that does not (falls back to px)."""
    from PySide6.QtGui import QImage, QPainter
    from src.models.image_data import ImageMetadata

    arr = np.random.rand(400, 400).astype(np.float32)
    canvas.setWidth(600); canvas.setHeight(500)
    target = QImage(600, 500, QImage.Format_ARGB32)

    physical = ImageData.from_array(
        arr, mode=ImageMode.SINGLE_FLOAT, name="scan",
        metadata=ImageMetadata(source="omicron_matrix_scan",
                               pixel_size_nm=(20.0, 20.0)))
    canvas.setImageData(physical)
    p = QPainter(target); canvas.paint(p); p.end()

    pixels = ImageData.from_array(arr, mode=ImageMode.SINGLE_FLOAT, name="nopx")
    canvas.setImageData(pixels)
    p = QPainter(target); canvas.paint(p); p.end()
