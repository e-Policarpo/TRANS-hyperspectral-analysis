"""
Tests for the interactive potential editor's canvas.

The mouse work lives here: what is under a click, what a drag means, and
where a double-click lands. Two conversions have to be right for any of it —
item coordinates to figure pixels (the device pixel ratio) and figure pixels
to data (matplotlib's origin is the other corner) — and both are invisible
until something is dropped in the wrong place.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QMouseEvent

from src.physics import feature_specs as specs
from src.widgets.qml_potential_canvas import PotentialCanvas


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    item = PotentialCanvas()
    item.setWidth(500)
    item.setHeight(500)
    item.setDomain([20.0, 20.0, 20.0])
    item.setFeatures([specs.default_spec('circle', (5.0, 5.0)),
                      specs.default_spec('rect', (15.0, 15.0))])
    item._render()
    yield item
    item.cleanup()


def _event(kind, x, y):
    # The three-position form: the short one is deprecated and fills the
    # suite with warnings that hide real ones.
    point = QPointF(x, y)
    return QMouseEvent(kind, point, point, point, Qt.LeftButton,
                       Qt.LeftButton, Qt.NoModifier)


def _press(canvas, x, y):
    canvas.mousePressEvent(_event(QEvent.MouseButtonPress, x, y))


def _move(canvas, x, y):
    canvas.mouseMoveEvent(_event(QEvent.MouseMove, x, y))


def _release(canvas, x, y):
    canvas.mouseReleaseEvent(_event(QEvent.MouseButtonRelease, x, y))


def _double(canvas, x, y):
    canvas.mouseDoubleClickEvent(_event(QEvent.MouseButtonDblClick, x, y))


class TestDrawing:
    def test_it_draws_one_patch_per_feature(self, canvas):
        assert len(canvas.figure.axes[0].patches) == 2

    def test_the_axes_span_the_box(self, canvas):
        ax = canvas.figure.axes[0]

        assert ax.get_xlim() == pytest.approx((0.0, 20.0))
        assert ax.get_ylim() == pytest.approx((0.0, 20.0))

    def test_a_projection_shows_the_axes_it_names(self, canvas):
        canvas.setDomain([30.0, 20.0, 10.0])
        canvas.projection = "xz"
        canvas._render()
        ax = canvas.figure.axes[0]

        assert ax.get_xlim() == pytest.approx((0.0, 30.0))
        assert ax.get_ylim() == pytest.approx((0.0, 10.0))
        assert ax.get_ylabel().startswith("z")

    def test_the_selected_feature_gets_a_handle(self, canvas):
        canvas.selectedIndex = 0
        canvas._render()
        markers = [line for line in canvas.figure.axes[0].lines]

        assert markers, "no handle drawn on the selection"

    def test_a_potential_underneath_is_drawn(self, canvas):
        canvas.setPotential({'x_nm': [0.0, 10.0, 20.0],
                             'y_nm': [0.0, 10.0, 20.0],
                             'V_eV': [[0.0, -0.3, 0.0]] * 3})
        canvas._render()

        assert canvas.figure.axes[0].collections

    def test_a_state_is_contoured_over_it(self, canvas):
        canvas.setDensity({'x_nm': [0.0, 10.0, 20.0],
                           'y_nm': [0.0, 10.0, 20.0],
                           'values': [[0.0, 1.0, 0.0]] * 3})
        canvas._render()

        assert canvas.figure.axes[0].collections

    def test_an_empty_density_draws_nothing_extra(self, canvas):
        before = len(canvas.figure.axes[0].collections)
        canvas.setDensity({})
        canvas._render()

        assert len(canvas.figure.axes[0].collections) == before


class TestPickingAFeature:
    def test_clicking_a_feature_selects_it(self, canvas):
        picked = []
        canvas.featureSelected.connect(picked.append)
        point = canvas.item_at(5.0, 5.0)

        _press(canvas, *point)

        assert picked == [0]
        assert canvas.selectedIndex == 0

    def test_clicking_empty_space_deselects(self, canvas):
        canvas.selectedIndex = 0
        canvas._render()
        picked = []
        canvas.featureSelected.connect(picked.append)

        _press(canvas, *canvas.item_at(19.5, 1.0))

        assert picked == [-1]
        assert canvas.selectedIndex == -1

    def test_the_feature_on_top_wins(self, canvas):
        """Two features overlapping: the one drawn last is the one you see,
        and picking the one underneath is how an editor feels broken."""
        canvas.setFeatures([specs.default_spec('circle', (10.0, 10.0)),
                            specs.default_spec('rect', (10.0, 10.0))])
        canvas._render()
        picked = []
        canvas.featureSelected.connect(picked.append)

        _press(canvas, *canvas.item_at(10.0, 10.0))

        assert picked == [1]

    def test_a_click_outside_the_axes_selects_nothing(self, canvas):
        picked = []
        canvas.featureSelected.connect(picked.append)

        _press(canvas, 2, 2)

        assert picked == [-1]


class TestDragging:
    def test_dragging_a_feature_reports_where_it_should_go(self, canvas):
        moved = []
        canvas.featureMoved.connect(lambda i, u, v: moved.append((i, u, v)))

        _press(canvas, *canvas.item_at(5.0, 5.0))
        _move(canvas, *canvas.item_at(12.0, 8.0))

        assert moved
        index, u, v = moved[-1]
        assert index == 0
        assert (u, v) == pytest.approx((12.0, 8.0), abs=0.2)

    def test_a_drag_keeps_the_grab_offset(self, canvas):
        """Grabbing a feature by its edge and dragging must not snap its
        centre to the cursor."""
        moved = []
        canvas.featureMoved.connect(lambda i, u, v: moved.append((u, v)))

        _press(canvas, *canvas.item_at(6.5, 5.0))     # right of centre
        _move(canvas, *canvas.item_at(16.5, 5.0))     # ten to the right

        assert moved[-1] == pytest.approx((15.0, 5.0), abs=0.2)

    def test_nothing_moves_without_a_press(self, canvas):
        moved = []
        canvas.featureMoved.connect(lambda i, u, v: moved.append((u, v)))

        _move(canvas, 250, 250)

        assert moved == []

    def test_releasing_ends_the_drag(self, canvas):
        moved = []
        canvas.featureMoved.connect(lambda i, u, v: moved.append((u, v)))

        _press(canvas, *canvas.item_at(5.0, 5.0))
        _release(canvas, *canvas.item_at(5.0, 5.0))
        _move(canvas, *canvas.item_at(15.0, 15.0))

        assert moved == []

    def test_dragging_the_handle_reports_a_size(self, canvas):
        """The handle is dragged to where the corner should be, so its
        distance from the centre is the answer."""
        canvas.selectedIndex = 0
        canvas._render()
        sized = []
        canvas.featureResized.connect(lambda i, du, dv: sized.append((du, dv)))

        spec = specs.default_spec('circle', (5.0, 5.0))
        half = specs.spec_extent(spec, (0, 1))
        _press(canvas, *canvas.item_at(5.0 + half[0], 5.0 + half[1]))
        _move(canvas, *canvas.item_at(9.0, 8.0))

        assert sized
        assert sized[-1] == pytest.approx((4.0, 3.0), abs=0.2)

    def test_the_handle_is_grabbed_in_pixels_not_nanometres(self, canvas):
        """A handle is a fixed size on screen whatever the zoom, so the grab
        radius cannot be in data units."""
        assert PotentialCanvas.HANDLE_GRAB_PX > 0


class TestAddingByDoubleClick:
    def test_a_double_click_on_empty_space_asks_for_a_feature(self, canvas):
        added = []
        canvas.featureAdded.connect(lambda u, v: added.append((u, v)))

        _double(canvas, *canvas.item_at(18.0, 3.0))

        assert added and added[-1] == pytest.approx((18.0, 3.0), abs=0.2)

    def test_a_double_click_on_a_feature_does_not_add_one(self, canvas):
        """It selects; adding a feature on top of the one you meant to pick
        is the worst possible reading of that click."""
        added = []
        canvas.featureAdded.connect(lambda u, v: added.append((u, v)))

        _double(canvas, *canvas.item_at(5.0, 5.0))

        assert added == []
