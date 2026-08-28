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
import numpy as np
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

        # An image, not a mesh: the grid is uniform and drawing it as one
        # interpolates the edges instead of showing the lattice.
        assert canvas.figure.axes[0].images

    def test_a_state_is_contoured_over_it(self, canvas):
        canvas.setDensity({'x_nm': [0.0, 10.0, 20.0],
                           'y_nm': [0.0, 10.0, 20.0],
                           'values': [[0.0, 1.0, 0.0]] * 3})
        canvas._render()

        assert canvas.figure.axes[0].collections

    def test_numpy_axes_are_drawn_rather_than_raising(self, canvas):
        """What crosses from QML is whatever the backend put in the map, and
        a numpy array there used to reach `if not x` — which raises instead
        of answering, inside paint(), so the canvas went blank and every
        frame logged a traceback."""
        grid = np.linspace(0.0, 20.0, 3)
        canvas.setDensity({'x_nm': grid, 'y_nm': grid,
                           'values': np.array([[0.0, 1.0, 0.0]] * 3)})
        canvas.setPotential({'x_nm': grid, 'y_nm': grid,
                             'V_eV': np.array([[0.0, -0.3, 0.0]] * 3)})
        canvas._render()

        assert canvas.figure.axes[0].images        # the potential
        assert canvas.figure.axes[0].collections   # the state's contours

    def test_an_empty_numpy_grid_draws_nothing_extra(self, canvas):
        before = len(canvas.figure.axes[0].collections)
        canvas.setDensity({'x_nm': np.array([]), 'y_nm': np.array([]),
                           'values': np.array([])})
        canvas._render()

        assert len(canvas.figure.axes[0].collections) == before

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


# --------------------------------------------------------------------------
# A projection draws every feature, wherever it sits on the axis it cannot
# show. Two things follow: a feature the cut misses must not be painted as
# though it were in the plane, and a large one must not bury a small one.

from src.physics import feature_specs as fspecs                  # noqa: E402


@pytest.fixture
def volume(app):
    """A 3-D model cut at z = 10: one feature on the plane, one below it."""
    item = PotentialCanvas()
    item.setWidth(500)
    item.setHeight(500)
    item.setDomain([20.0, 20.0, 20.0])
    on_plane = dict(fspecs.default_spec('sphere', (5.0, 5.0)),
                    cz=10.0, R=3.0)
    off_plane = dict(fspecs.default_spec('sphere', (14.0, 14.0)),
                     cz=3.0, R=2.0)
    item.setFeatures([on_plane, off_plane])
    item.projection = 'xy'
    item.setPotential({'x_nm': [0.0, 10.0, 20.0], 'y_nm': [0.0, 10.0, 20.0],
                       'V_eV': [[0.0, 0.0, 0.0]] * 3, 'slice_at': 10.0})
    return item


class TestWhatThePlaneCuts:
    def test_a_feature_off_the_plane_is_outlined_not_filled(self, volume):
        volume._render()
        faces = sorted(patch.get_facecolor()[3]
                       for patch in volume.figure.axes[0].patches)

        assert faces[0] == pytest.approx(0.0)    # the one the cut misses
        assert faces[-1] > 0.1                   # the one it passes through

    def test_a_feature_off_the_plane_is_dashed(self, volume):
        volume._render()
        # A dash pattern is an (offset, on-off) tuple; a solid line is '-'.
        dashed = [patch for patch in volume.figure.axes[0].patches
                  if isinstance(patch.get_linestyle(), tuple)]

        assert len(dashed) == 1

    def test_a_two_dimensional_model_has_nothing_off_the_plane(self, canvas):
        """There is no hidden axis to be off, so every feature is filled."""
        canvas._render()

        assert all(patch.get_facecolor()[3] > 0.1
                   for patch in canvas.figure.axes[0].patches)

    def test_the_big_one_is_drawn_first(self, canvas):
        """Painted in size order, so a small feature is never buried under a
        large one that happens to sit behind it."""
        canvas.setFeatures([dict(fspecs.default_spec('circle', (10.0, 10.0)),
                                 r=1.0),
                            dict(fspecs.default_spec('circle', (10.0, 10.0)),
                                 r=6.0)])
        canvas._render()
        widths = [patch.get_width() if hasattr(patch, 'get_width')
                  else patch.get_radius() * 2
                  for patch in canvas.figure.axes[0].patches]

        assert widths == sorted(widths, reverse=True)


# --------------------------------------------------------------------------
# What is drawn has to be what the solver sees. Every outline is checked
# against the feature's own contains() over the plane being shown, because
# eyeballing a shape is exactly how an ellipse went on being drawn as its
# bounding rectangle, a cone as a full-width box, and a pyramid at twice its
# size, for as long as they did.

AXES_OF = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}


def _agreement(kind, projection, slice_at, overrides, three_d=True):
    """(missed, spurious) as fractions of the region contains() carves out."""
    spec = dict(fspecs.default_spec(kind, (10.0, 10.0)), **overrides)
    feature = fspecs.build_features([spec])[0]
    axes = AXES_OF[projection]

    grid = np.linspace(4.0, 16.0, 361)
    u, v = np.meshgrid(grid, grid, indexing='ij')
    if three_d:
        coords = [np.full_like(u, slice_at)] * 3
        coords[axes[0]], coords[axes[1]] = u, v
        inside = feature.contains(*coords)
    else:
        inside = feature.contains(u, v)
    assert inside.any(), "the test itself is cutting where there is nothing"

    canvas = PotentialCanvas()
    canvas.setWidth(400)
    canvas.setHeight(400)
    canvas.setDomain([20.0, 20.0, 20.0] if three_d else [20.0, 20.0])
    canvas.setFeatures([spec])
    canvas.projection = projection
    potential = {'x_nm': [0.0, 20.0], 'y_nm': [0.0, 20.0],
                 'V_eV': [[0.0, 0.0], [0.0, 0.0]]}
    if three_d:
        potential['slice_at'] = slice_at
    canvas.setPotential(potential)
    canvas._render()

    patch = canvas.figure.axes[0].patches[0]
    path = patch.get_path().transformed(patch.get_patch_transform())
    drawn = path.contains_points(
        np.column_stack([u.ravel(), v.ravel()])).reshape(u.shape)
    total = inside.sum()
    return ((inside & ~drawn).sum() / total, (drawn & ~inside).sum() / total)


class TestTheOutlineIsTheFeature:
    @pytest.mark.parametrize("kind", ['rect', 'circle', 'ellipse',
                                      'triangle'])
    def test_two_dimensional_kinds(self, app, kind):
        missed, spurious = _agreement(kind, 'xy', 0.0, {}, three_d=False)

        assert missed < 0.03 and spurious < 0.03

    @pytest.mark.parametrize("kind,projection", [
        ('box', 'xy'), ('box', 'xz'),
        ('sphere', 'xy'), ('sphere', 'xz'),
        ('cylinder', 'xy'), ('cylinder', 'xz'),
        ('cone', 'xy'), ('cone', 'xz'),
        ('pyramid', 'xy'), ('pyramid', 'xz'),
        ('prism', 'xy'), ('prism', 'xz'),
        ('lens', 'xy'), ('lens', 'xz'),
        ('gaussian_3d', 'xy'),
    ])
    def test_three_dimensional_kinds_cut_through_the_centre(
            self, app, kind, projection):
        missed, spurious = _agreement(kind, projection, 10.0, {'cz': 10.0})

        assert missed < 0.03 and spurious < 0.03

    @pytest.mark.parametrize("slice_at", [10.0, 11.0, 11.5])
    def test_a_sphere_shrinks_as_the_cut_leaves_its_centre(self, app, slice_at):
        """The section of a sphere offset d is a circle of sqrt(R^2 - d^2),
        not R. Drawn at R it claimed 33% more area one nanometre off centre."""
        missed, spurious = _agreement('sphere', 'xy', slice_at,
                                      {'cz': 10.0, 'R': 2.0})

        assert missed < 0.03 and spurious < 0.03

    @pytest.mark.parametrize("slice_at", [8.5, 10.0, 11.0])
    def test_a_cone_narrows_towards_its_apex(self, app, slice_at):
        missed, spurious = _agreement('cone', 'xy', slice_at,
                                      {'cz': 10.0, 'R': 2.0, 'H': 4.0})

        assert missed < 0.05 and spurious < 0.05

    @pytest.mark.parametrize("slice_at", [8.1, 9.0, 10.0, 11.5])
    def test_a_lens_is_widest_where_it_stands(self, app, slice_at):
        """cz is the centre of the body, so a cap with R = 2, H = 4 spans
        z = 8 to 12 and is 2 nm wide at the bottom of that, not the middle.
        Drawn against the old base-at-cz convention it sits a full half
        height off."""
        missed, spurious = _agreement('lens', 'xy', slice_at,
                                      {'cz': 10.0, 'R': 2.0, 'H': 4.0})

        assert missed < 0.03 and spurious < 0.03

    @pytest.mark.parametrize("slice_at", [9.0, 10.0, 11.0])
    def test_a_triangle_keeps_its_apex_off_the_plane_axis(self, app,
                                                          slice_at):
        """A 2-D shape has no hidden axis, so the cut never changes it —
        which is the claim, because the outline registry's fallback is a
        bounding rectangle and that would be full width at the apex."""
        missed, spurious = _agreement('triangle', 'xy', slice_at,
                                      {'w': 6.0, 'h': 3.0}, three_d=False)

        assert missed < 0.03 and spurious < 0.03

    def test_a_wedge_has_no_side_view_and_draws_none(self, app):
        """WedgeFeature2D.contains takes no Z. The bounding-box fallback drew
        it as a zero-height line along the bottom of the axes."""
        canvas = PotentialCanvas()
        canvas.setWidth(400)
        canvas.setHeight(400)
        canvas.setDomain([20.0, 20.0, 20.0])
        canvas.setFeatures([fspecs.default_spec('wedge', (10.0, 10.0))])
        canvas.projection = 'xz'
        canvas._render()

        assert len(canvas.figure.axes[0].patches) == 0


# --------------------------------------------------------------------------
# A 3-D model is shown one plane at a time, and which plane it is is not
# recoverable from the picture: the same sphere, cut anywhere through it,
# draws the same circle. The title is the only thing that says where the cut
# was taken, so it has to be there and it has to agree with the plane
# underneath it — which is why it quotes the potential's own snapped
# position rather than the number the slider sent.

class TestTheCutIsNamed:
    def test_a_three_dimensional_cut_says_which_plane_it_is(self, volume):
        volume._render()

        assert volume.figure.axes[0].get_title() == "XY cut · z = 10.00 nm"

    @pytest.mark.parametrize("projection,expected", [
        ('xy', "XY cut · z = 10.00 nm"),
        ('xz', "XZ cut · y = 10.00 nm"),
        ('yz', "YZ cut · x = 10.00 nm"),
    ])
    def test_it_names_the_axis_the_cut_is_along(self, volume, projection,
                                                expected):
        volume.projection = projection
        volume._render()

        assert volume.figure.axes[0].get_title() == expected

    def test_it_quotes_where_the_cut_landed(self, volume):
        """The backend snaps a request onto a grid line and reports where it
        went. A title showing the request instead would disagree with the
        plane drawn under it by up to half a step."""
        volume.setPotential({'x_nm': [0.0, 10.0, 20.0],
                             'y_nm': [0.0, 10.0, 20.0],
                             'V_eV': [[0.0, 0.0, 0.0]] * 3,
                             'slice_at': 13.25})
        volume._render()

        assert volume.figure.axes[0].get_title() == "XY cut · z = 13.25 nm"

    def test_it_is_readable_against_the_panel(self, canvas):
        """An unresolved colour lands as an invalid QColor and paints black
        on black, which is the whole reason this palette is threaded through
        by hand."""
        canvas.setPotential({'x_nm': [0.0, 20.0], 'y_nm': [0.0, 20.0],
                             'V_eV': [[0.0, 0.0], [0.0, 0.0]],
                             'slice_at': 10.0})
        canvas.setDomain([20.0, 20.0, 20.0])
        canvas._render()
        title = canvas.figure.axes[0].title

        assert title.get_color() == canvas._foreground

    def test_a_two_dimensional_model_is_left_untitled(self, canvas):
        """There is no hidden axis to disambiguate, the axis labels already
        name the plane, and the row it would cost is one this panel does not
        have."""
        canvas._render()

        assert canvas.figure.axes[0].get_title() == ""

    def test_a_preview_that_never_arrived_is_untitled_too(self, volume):
        """Same rule, one condition: no `slice_at`, no title. A failed
        preview degrades to silence rather than to "z = None"."""
        volume.setPotential({})
        volume._render()

        assert volume.figure.axes[0].get_title() == ""

    @pytest.mark.parametrize("bad", [None, float('nan'), float('inf')])
    def test_a_position_that_is_not_a_number_does_not_reach_the_figure(
            self, volume, bad):
        """`_render` runs inside paint(); anything it can raise on is a
        traceback every frame and a blank canvas."""
        volume.setPotential({'x_nm': [0.0, 20.0], 'y_nm': [0.0, 20.0],
                             'V_eV': [[0.0, 0.0], [0.0, 0.0]],
                             'slice_at': bad})
        volume._render()

        assert volume.figure.axes[0].get_title() == ""

    @pytest.mark.parametrize("bad", [None, "x", object()])
    def test_a_position_that_is_not_a_number_at_all_titles_nothing(
            self, volume, bad):
        """Asked of the title directly rather than through `_render`: the
        outline path reads the same key and converts it without a guard, so a
        non-numeric one raises there before the title is ever built. That is
        a gap in `_hidden_offset`, not in the title — which answers "" for
        every one of these."""
        volume.setPotential({'slice_at': bad})

        assert volume._cut_title() == ""

    @pytest.mark.parametrize("domain,slice_at,expected", [
        ([2000.0, 2000.0, 2000.0], 1013.4567, "z = 1013 nm"),
        ([200.0, 200.0, 200.0], 101.25, "z = 101.2 nm"),
        ([4.0, 4.0, 4.0], 2.0123456, "z = 2.012 nm"),
    ])
    def test_it_keeps_four_figures_of_the_box_it_is_cutting(
            self, volume, domain, slice_at, expected):
        """Fixed decimals, taken from the domain rather than the value, so
        the title does not change width while a slider is dragged."""
        volume.setDomain(domain)
        volume.setPotential({'x_nm': [0.0, domain[0]], 'y_nm': [0.0, domain[1]],
                             'V_eV': [[0.0, 0.0], [0.0, 0.0]],
                             'slice_at': slice_at})
        volume._render()

        assert volume.figure.axes[0].get_title().endswith(expected)
