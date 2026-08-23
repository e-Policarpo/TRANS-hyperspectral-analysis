"""
Tests for FigureCanvasItem — a matplotlib figure hosted in a QML item.

The seam the whole designer port rests on: a caller draws into the figure
with ordinary matplotlib and the item blits the result. What has to hold is
that the blit is the right size, that it is sharp on a Retina display, and
that the figure and its timer are released when the window goes.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QGuiApplication

from src.widgets.qml_figure_canvas import FigureCanvasItem


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    item = FigureCanvasItem()
    item.setWidth(400)
    item.setHeight(300)
    yield item
    item.cleanup()


def _plot(canvas):
    ax = canvas.figure.add_subplot(111)
    ax.plot([0, 1, 2], [1, 3, 2])
    return ax


class TestRendering:
    def test_the_image_is_the_item_s_size(self, canvas):
        _plot(canvas)
        canvas._render()

        assert canvas._cached_image.width() == 400
        assert canvas._cached_image.height() == 300

    def test_nothing_is_rendered_before_the_item_has_a_size(self, app):
        item = FigureCanvasItem()
        item._render()

        assert item._cached_image is None
        item.cleanup()

    def test_a_retina_ratio_renders_at_device_resolution(self, canvas, monkeypatch):
        """Getting this wrong is the "blurry on Retina" bug this repository
        has already fixed once: the buffer has to be device-sized and the
        image has to say so, or Qt stretches a small picture over the item."""
        monkeypatch.setattr(canvas, "_device_pixel_ratio", lambda: 2.0)
        _plot(canvas)
        canvas._render()

        assert canvas._cached_image.width() == 800       # device pixels
        assert canvas._cached_image.devicePixelRatio() == 2.0
        # ...but it still occupies 400 logical points.
        assert canvas._cached_image.deviceIndependentSize().width() == 400

    def test_the_layout_does_not_change_with_the_ratio(self, canvas, monkeypatch):
        """Sizes are in points, so doubling the DPI doubles the pixels and
        leaves the composition alone — an axis in the same place, drawn
        finer."""
        ax = _plot(canvas)
        canvas._render()
        at_one = ax.get_position().bounds

        monkeypatch.setattr(canvas, "_device_pixel_ratio", lambda: 2.0)
        canvas._render()

        assert ax.get_position().bounds == pytest.approx(at_one, abs=1e-6)

    def test_no_window_means_no_scaling(self, canvas):
        """A canvas built in a test, or before its window exists, still has
        to render rather than divide by a missing ratio."""
        assert canvas._device_pixel_ratio() == 1.0

    def test_a_figure_that_cannot_draw_does_not_take_the_item_down(self, canvas,
                                                                  monkeypatch):
        """A tool's drawing code is the caller's; a mistake in it must not
        crash the window that hosts it."""
        _plot(canvas)
        canvas._render()
        good = canvas._cached_image

        def _explode():
            raise RuntimeError("an artist the caller got wrong")

        monkeypatch.setattr(canvas.canvas, "draw", _explode)
        canvas._render()

        assert canvas._cached_image is good              # kept the last good one


class TestRedrawAndResize:
    def test_redraw_marks_the_figure_dirty(self, canvas):
        _plot(canvas)
        canvas._render()
        canvas._needs_redraw = False

        canvas.redraw()
        assert canvas._needs_redraw is True

    def test_clearing_empties_the_figure(self, canvas):
        _plot(canvas)
        canvas.clearFigure()

        assert canvas.figure.axes == []

    def test_a_resize_does_not_re_render_immediately(self, canvas):
        """The cached image is stretched while the drag is happening; a
        matplotlib re-render per pixel is what the debounce exists to avoid."""
        from PySide6.QtCore import QRectF

        _plot(canvas)
        canvas._render()
        canvas._needs_redraw = False

        canvas.geometryChange(QRectF(0, 0, 500, 300), QRectF(0, 0, 400, 300))

        assert canvas._needs_redraw is False
        assert canvas._resize_timer.isActive()

    def test_the_debounce_re_renders_when_it_fires(self, canvas):
        canvas._needs_redraw = False
        canvas._on_resize_finished()

        assert canvas._needs_redraw is True

    def test_a_move_that_is_not_a_resize_is_ignored(self, canvas):
        from PySide6.QtCore import QRectF

        canvas._resize_timer.stop()
        canvas.geometryChange(QRectF(10, 10, 400, 300), QRectF(0, 0, 400, 300))

        assert not canvas._resize_timer.isActive()


class TestPalette:
    def test_the_background_reaches_the_figure(self, canvas):
        canvas.backgroundColor = "#123456"

        assert canvas.backgroundColor == "#123456"
        assert canvas.figure.get_facecolor()[:3] == pytest.approx(
            (0x12 / 255, 0x34 / 255, 0x56 / 255), abs=1e-3)

    def test_a_colour_that_is_not_one_is_refused_quietly(self, canvas):
        canvas.backgroundColor = "not a colour"

        assert canvas.backgroundColor == "not a colour"   # the request is kept
        assert canvas.figure.get_facecolor()              # the figure is intact

    def test_an_empty_colour_changes_nothing(self, canvas):
        before = canvas.backgroundColor
        canvas.backgroundColor = ""

        assert canvas.backgroundColor == before


class TestExportAndTeardown:
    def test_it_exports_a_png(self, canvas, tmp_path):
        _plot(canvas)
        path = tmp_path / "figure.png"

        assert canvas.exportToPNG(str(path)) is True
        assert path.exists() and path.stat().st_size > 0

    def test_an_unwritable_path_is_reported_not_raised(self, canvas):
        assert canvas.exportToPNG("/nowhere/at/all/figure.png") is False

    def test_cleanup_stops_the_timer_and_drops_the_image(self, canvas):
        _plot(canvas)
        canvas._render()
        canvas._resize_timer.start()

        canvas.cleanup()

        assert not canvas._resize_timer.isActive()
        assert canvas._cached_image is None

    def test_cleanup_is_safe_twice(self, canvas):
        canvas.cleanup()
        canvas.cleanup()
