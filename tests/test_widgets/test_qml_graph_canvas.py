"""
Tests for QMLGraphCanvas interaction-state properties.

Focused on the ``selectedCurveId`` property, which used to be read-only
with no notify signal — a QML write (e.g. an ``onCurveSelected`` handler
that resolved the unqualified name to the canvas's own property) crashed
with "'NoneType' object is not callable", and ``enabled:`` bindings on it
never refreshed.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QGuiApplication, QImage, QPainter

from src.widgets.qml_graph_canvas import QMLGraphCanvas


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    return QMLGraphCanvas()


def _add_curve(canvas, label="c"):
    return canvas.addCurve(label, [0.0, 1.0, 2.0], [1.0, 2.0, 3.0])


def test_selected_curve_id_defaults_to_minus_one(canvas):
    assert canvas.selectedCurveId == -1


def test_writing_selected_curve_id_does_not_crash_and_sticks(canvas):
    """The regression: assigning the property must not raise (no setter
    previously) and must update the value."""
    cid = _add_curve(canvas)
    canvas.selectedCurveId = cid
    assert canvas.selectedCurveId == cid


def test_writing_unknown_curve_id_is_ignored(canvas):
    _add_curve(canvas)
    canvas.selectedCurveId = 999  # not a real curve
    assert canvas.selectedCurveId == -1


def test_writing_negative_clears_selection(canvas):
    cid = _add_curve(canvas)
    canvas.selectedCurveId = cid
    assert canvas.selectedCurveId == cid
    canvas.selectedCurveId = -1
    assert canvas.selectedCurveId == -1


def test_setter_emits_change_signal(canvas):
    cid = _add_curve(canvas)
    seen = []
    canvas.selectedCurveIdChanged.connect(lambda v: seen.append(v))
    canvas.selectedCurveId = cid
    assert seen == [cid]
    # Re-assigning the same value must not re-emit (deduped).
    canvas.selectedCurveId = cid
    assert seen == [cid]


def test_select_curve_slot_emits_change_signal(canvas):
    cid = _add_curve(canvas)
    seen = []
    canvas.selectedCurveIdChanged.connect(lambda v: seen.append(v))
    canvas.selectCurve(cid)
    assert seen == [cid]


def test_removing_selected_curve_resets_and_notifies(canvas):
    cid = _add_curve(canvas)
    canvas.selectCurve(cid)
    seen = []
    canvas.selectedCurveIdChanged.connect(lambda v: seen.append(v))
    canvas.removeCurve(cid)
    assert canvas.selectedCurveId == -1
    assert seen == [-1]


def test_clear_curves_notifies_when_selection_existed(canvas):
    cid = _add_curve(canvas)
    canvas.selectCurve(cid)
    seen = []
    canvas.selectedCurveIdChanged.connect(lambda v: seen.append(v))
    canvas.clearCurves()
    assert canvas.selectedCurveId == -1
    assert seen == [-1]


# ---------------------------------------------------------------------------
# Auto-fit on open — resetView() / _calculateAutoBounds() must frame all data
# immediately (before the first paint), with an exact 5 % margin.
# ---------------------------------------------------------------------------

def _sized_canvas(app, w=800, h=600):
    c = QMLGraphCanvas()
    c.setWidth(w)
    c.setHeight(h)
    return c


def _paint_once(canvas):
    """Drive one native paint so the data→pixel transform registers."""
    img = QImage(int(canvas.width()), int(canvas.height()),
                 QImage.Format_ARGB32)
    p = QPainter(img)
    canvas._renderNative(p)
    p.end()


def test_reset_view_frames_data_before_any_paint(app):
    c = _sized_canvas(app)
    c.addCurve("c", list(np.linspace(100, 2000, 400)),
               list(np.linspace(-5, 50, 400)))
    c.resetView()  # no paint has happened yet
    x0, x1, y0, y1 = c._viewbox.view_range().as_tuple()
    # data x in [100, 2000], y in [-5, 50] + exact 5 % margin.
    assert (round(x0, 3), round(x1, 3)) == (5.0, 2095.0)
    assert (round(y0, 3), round(y1, 3)) == (-7.75, 52.75)


def test_auto_bounds_exact_margin_is_stable_first_call(app):
    """The first auto-bounds call (from the default 0–1 view) must give
    the same exact margin as steady state — no transient edge swap."""
    c = _sized_canvas(app)
    c.addCurve("c", list(np.linspace(100, 2000, 400)),
               list(np.linspace(-5, 50, 400)))
    c._calculateAutoBounds()
    first = tuple(round(v, 3) for v in c._viewbox.view_range().as_tuple())
    c._calculateAutoBounds()
    second = tuple(round(v, 3) for v in c._viewbox.view_range().as_tuple())
    assert first == second == (5.0, 2095.0, -7.75, 52.75)


def test_auto_bounds_degenerate_axis_uses_half_unit_fallback(app):
    c = _sized_canvas(app, 400, 300)
    c.addCurve("flat", [3.0, 3.0, 3.0], [7.0, 7.0, 7.0])
    c.resetView()
    assert tuple(round(v, 3) for v in c._viewbox.view_range().as_tuple()) == (
        2.5, 3.5, 6.5, 7.5,
    )


def test_reset_view_with_no_curves_is_unit_box(app):
    c = _sized_canvas(app)
    c.resetView()
    assert c._viewbox.view_range().as_tuple() == (0.0, 1.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Cosmetic pen — the curve is stroked while the data→pixel transform is active,
# so a non-cosmetic pen has its width scaled by the transform. With small-
# magnitude data (STM currents ~1e-6) that scale is huge and the line floods
# the whole plot. The pen must be cosmetic so the width stays in device pixels.
# ---------------------------------------------------------------------------

def _interior_filled_fraction(canvas):
    """Fraction of the plot interior that differs from the background after
    one native paint. A thin line covers a few percent; a flood covers ~all."""
    w, h = int(canvas.width()), int(canvas.height())
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(canvas._NATIVE_BG_COLOR)
    p = QPainter(img)
    canvas._renderNative(p)
    p.end()
    bg = canvas._NATIVE_BG_COLOR
    bg_rgb = (bg.red(), bg.green(), bg.blue())
    filled = total = 0
    for y in range(int(h * 0.2), int(h * 0.8), 4):
        for x in range(int(w * 0.25), int(w * 0.9), 4):
            px = img.pixel(x, y)
            rgb = ((px >> 16) & 255, (px >> 8) & 255, px & 255)
            total += 1
            if sum(abs(a - b) for a, b in zip(rgb, bg_rgb)) > 60:
                filled += 1
    return filled / total


def test_small_magnitude_curve_does_not_flood_plot(app):
    """Regression: an STM-scale curve (y ~ 1e-6) must render as a thin line,
    not a solid block. Guards the cosmetic-pen fix."""
    c = _sized_canvas(app)
    xs = np.linspace(-0.4, 0.4, 580)
    ys = np.tanh(np.linspace(-3, 3, 580)) * 3e-6
    c.addCurve("Point_4", list(xs), list(ys))
    c.resetView()
    assert _interior_filled_fraction(c) < 0.25


def test_curve_pen_is_cosmetic_when_drawn(app):
    """The pen handed to ``drawPath`` must be cosmetic regardless of data scale."""
    from PySide6.QtGui import QPainter as _QP
    c = _sized_canvas(app)
    c.addCurve("c", list(np.linspace(-0.4, 0.4, 100)),
               list(np.linspace(-1e-6, 1e-6, 100)))
    c.resetView()
    seen = []
    orig = _QP.drawPath
    def spy(self, path):
        seen.append(self.pen().isCosmetic())
        return orig(self, path)
    _QP.drawPath = spy
    try:
        _paint_once(c)
    finally:
        _QP.drawPath = orig
    assert seen and all(seen)


# ---------------------------------------------------------------------------
# Curve-pick coordinate space — _findNearestCurve must compare the click and
# the curve samples in the SAME space. In native (default) mode the matplotlib
# axes is never laid out, so the old transData path could not pick any curve.
# ---------------------------------------------------------------------------

def test_find_nearest_curve_hits_in_native_mode(app):
    c = _sized_canvas(app)
    xs = np.linspace(100.0, 2000.0, 400)
    ys = np.linspace(-5.0, 50.0, 400)
    cid = c.addCurve("c", list(xs), list(ys))
    _paint_once(c)  # registers the native transform
    # A point exactly on the line, round-tripped through the transform.
    x_on = 1000.0
    y_on = float(np.interp(x_on, xs, ys))
    px, py = c._dataToPixel(x_on, y_on)
    xd, yd = c._pixelToData(px, py)
    assert c._findNearestCurve(xd, yd) == cid


def test_find_nearest_curve_misses_far_from_line(app):
    c = _sized_canvas(app)
    xs = np.linspace(100.0, 2000.0, 400)
    ys = np.linspace(-5.0, 50.0, 400)
    c.addCurve("c", list(xs), list(ys))
    _paint_once(c)
    # Top-left corner of the axes is well off the rising line.
    fx, fy = c._pixelToData(70.0, 30.0)
    assert c._findNearestCurve(fx, fy) is None


# ---------------------------------------------------------------------------
# Area-select (rubber-band) zoom must frame exactly the dragged rectangle:
# the corner pixels of the resulting view map back to the press/release
# pixels. Locks in the native-render coordinate round-trip.
# ---------------------------------------------------------------------------

def test_area_select_zoom_is_pixel_exact(app):
    c = _sized_canvas(app)
    c.addCurve("c", list(np.linspace(100.0, 2000.0, 400)),
               list(np.linspace(-5.0, 50.0, 400)))
    _paint_once(c)  # register native transform + axes rect
    c.mouseMode = "rect"

    a = (250.0, 180.0)   # press pixel
    b = (560.0, 430.0)   # release pixel
    vb = c._viewbox
    vb.handle_press_left(a)
    vb.handle_move(b)
    res = vb.handle_release_left(b)   # (x_min, y_min, x_max, y_max)
    assert res is not None
    x_min, y_min, x_max, y_max = res

    # The new view's corners must land back on the dragged pixels.
    tl = c._dataToPixel(x_min, y_max)   # top-left
    br = c._dataToPixel(x_max, y_min)   # bottom-right
    assert tl == pytest.approx(a, abs=1e-6)
    assert br == pytest.approx(b, abs=1e-6)


# ---------------------------------------------------------------------------
# Non-finite curve data — the paint-crash regression.
#
# A curve whose y column is all NaN made ``_calculateAutoBounds`` publish a
# NaN view range (``np.nanmin`` of an all-NaN array is NaN). NaN fails every
# comparison, so the degenerate-range check in ``_renderNative`` let it
# through to the tick algorithm, where ``ceil()`` raised
# "ValueError: cannot convert float NaN to integer" out of
# ``QQuickPaintedItem.paint`` — on every single frame.
# ---------------------------------------------------------------------------


def test_all_nan_curve_is_ignored_by_auto_bounds(app):
    """A finite curve still frames correctly when an all-NaN curve
    shares the plot."""
    c = _sized_canvas(app)
    c.addCurve("good", [0.0, 10.0], [0.0, 100.0])
    c.addCurve("nan", [float("nan")] * 4, [float("nan")] * 4)
    c.resetView()
    x0, x1, y0, y1 = c._viewbox.view_range().as_tuple()
    assert (round(x0, 3), round(x1, 3)) == (-0.5, 10.5)
    assert (round(y0, 3), round(y1, 3)) == (-5.0, 105.0)


def test_partially_nan_curve_bounds_use_finite_samples_only(app):
    c = _sized_canvas(app)
    c.addCurve("holes", [0.0, 1.0, float("nan"), 3.0],
               [5.0, float("nan"), 7.0, 9.0])
    c.resetView()
    x0, x1, y0, y1 = c._viewbox.view_range().as_tuple()
    # Only the pairs (0, 5) and (3, 9) are fully finite.
    assert (round(x0, 3), round(x1, 3)) == (-0.15, 3.15)
    assert (round(y0, 3), round(y1, 3)) == (4.8, 9.2)


def test_infinite_curve_values_are_ignored_by_auto_bounds(app):
    """``inf`` bounds crashed the same tick path with OverflowError."""
    c = _sized_canvas(app)
    c.addCurve("spike", [0.0, 1.0, 2.0], [1.0, float("inf"), 3.0])
    c.resetView()
    x0, x1, y0, y1 = c._viewbox.view_range().as_tuple()
    assert (round(y0, 3), round(y1, 3)) == (0.9, 3.1)
    assert (round(x0, 3), round(x1, 3)) == (-0.1, 2.1)


@pytest.mark.parametrize("xs, ys", [
    ([float("nan")] * 3, [float("nan")] * 3),
    ([0.0, 1.0, 2.0], [float("nan")] * 3),
    ([float("inf")] * 3, [float("inf")] * 3),
])
def test_paint_does_not_raise_for_non_finite_curve(app, xs, ys):
    """The regression itself: painting a plot whose only curve is
    non-finite must not raise out of ``paint``."""
    c = _sized_canvas(app)
    c.addCurve("bad", xs, ys)
    c.resetView()
    _paint_once(c)  # must not raise


def test_paint_does_not_raise_for_non_finite_view_range(app):
    """Even if a non-finite range reaches the canvas from elsewhere
    (restored zoom state, a log clamp), the render must bail cleanly."""
    c = _sized_canvas(app)
    c.addCurve("good", [0.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    c._viewbox.set_view_range(
        float("nan"), float("nan"), float("nan"), float("nan"),
        push_history=False, disable_auto=True,
    )
    _paint_once(c)  # must not raise
