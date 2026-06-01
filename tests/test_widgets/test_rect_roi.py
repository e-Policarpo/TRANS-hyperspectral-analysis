"""
Tests for ``RectROI`` — body + 4 corner handles, optional snap-to-grid.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.widgets._pyqtgraph_ports.items.rect_roi import (
    HIT_BODY,
    HIT_NE,
    HIT_NONE,
    HIT_NW,
    HIT_SE,
    HIT_SW,
    RectROI,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _identity_xy():
    return lambda x, y: (float(x), float(y))


# --- defaults + setters --------------------------------------------

def test_defaults():
    r = RectROI(roi_id="block_sel", rect=(0.0, 0.0, 10.0, 5.0))
    assert r.roi_id == "block_sel"
    assert r.rect() == (0.0, 0.0, 10.0, 5.0)
    assert r.movable is True


def test_constructor_normalizes_rect():
    r = RectROI(rect=(10.0, 5.0, 0.0, 0.0))  # swapped corners
    assert r.rect() == (0.0, 0.0, 10.0, 5.0)


def test_set_rect_returns_changed_flag():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    assert r.set_rect(0.0, 0.0, 10.0, 10.0) is False
    assert r.set_rect(5.0, 5.0, 15.0, 15.0) is True
    assert r.rect() == (5.0, 5.0, 15.0, 15.0)


def test_set_bounds_pulls_rect_in():
    r = RectROI(rect=(-50.0, -50.0, 50.0, 50.0))
    assert r.set_bounds(
        bounds_x=(0.0, 20.0), bounds_y=(0.0, 20.0),
    ) is True
    assert r.rect() == (0.0, 0.0, 20.0, 20.0)


# --- snap ----------------------------------------------------------

def test_snap_step_quantises_corners():
    r = RectROI(rect=(0.7, 0.4, 4.3, 2.6))
    r.set_snap_step((1.0, 1.0))
    # Each corner rounds to nearest integer.
    assert r.rect() == (1.0, 0.0, 4.0, 3.0)


def test_snap_origin_shifts_grid():
    # Origin 0.5, step 1.0 → grid lattice {..., -0.5, 0.5, 1.5, ...}.
    # Probe values that aren't exact ties (avoid 0.0, 1.0, ...) so the
    # snap result is unambiguous regardless of Python's banker's
    # rounding tie-break.
    r = RectROI(rect=(0.3, 0.2, 4.8, 4.7))
    r.set_snap_origin(0.5, 0.5)
    r.set_snap_step((1.0, 1.0))
    # 0.3 → nearest lattice = 0.5; 0.2 → 0.5; 4.8 → 4.5; 4.7 → 4.5.
    assert r.rect() == (0.5, 0.5, 4.5, 4.5)


def test_snap_step_none_disables():
    r = RectROI(rect=(0.7, 0.4, 4.3, 2.6))
    r.set_snap_step(None)
    assert r.rect() == (0.7, 0.4, 4.3, 2.6)


def test_snap_only_one_axis():
    r = RectROI(rect=(0.7, 0.4, 4.3, 2.6))
    r.set_snap_step((1.0, None))
    # x snaps to integer, y left alone.
    assert r.rect() == (1.0, 0.4, 4.0, 2.6)


# --- hit testing ----------------------------------------------------

def test_hit_test_corner_nw():
    r = RectROI(rect=(0.0, 0.0, 100.0, 100.0))
    res = r.hit_test(0.0, 0.0, data_to_pixel=_identity_xy())
    assert res == HIT_NW


def test_hit_test_corner_se():
    r = RectROI(rect=(0.0, 0.0, 100.0, 100.0))
    res = r.hit_test(100.0, 100.0, data_to_pixel=_identity_xy())
    assert res == HIT_SE


def test_hit_test_body_centre():
    r = RectROI(rect=(0.0, 0.0, 100.0, 100.0))
    res = r.hit_test(50.0, 50.0, data_to_pixel=_identity_xy())
    assert res == HIT_BODY


def test_hit_test_outside():
    r = RectROI(rect=(0.0, 0.0, 100.0, 100.0))
    res = r.hit_test(500.0, 500.0, data_to_pixel=_identity_xy())
    assert res == HIT_NONE


def test_hit_test_ignored_when_not_movable():
    r = RectROI(rect=(0.0, 0.0, 100.0, 100.0), movable=False)
    res = r.hit_test(50.0, 50.0, data_to_pixel=_identity_xy())
    assert res == HIT_NONE


# --- drag state machine --------------------------------------------

def test_body_drag_translates():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    state = r.begin_drag(5.0, 5.0, HIT_BODY)
    r.update_drag(8.0, 9.0, state)
    # +3 dx, +4 dy.
    assert r.rect() == (3.0, 4.0, 13.0, 14.0)


def test_corner_drag_resizes_one_corner():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    state = r.begin_drag(10.0, 10.0, HIT_SE)
    r.update_drag(15.0, 20.0, state)
    assert r.rect() == (0.0, 0.0, 15.0, 20.0)


def test_corner_drag_re_normalises_after_cross():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    state = r.begin_drag(10.0, 10.0, HIT_SE)
    # Pull SE corner past the NW corner — rectangle should renormalise
    # rather than producing a negative-width box.
    r.update_drag(-5.0, -3.0, state)
    x0, y0, x1, y1 = r.rect()
    assert x0 <= x1
    assert y0 <= y1


def test_drag_clamps_to_bounds():
    r = RectROI(
        rect=(5.0, 5.0, 10.0, 10.0),
        bounds_x=(0.0, 20.0), bounds_y=(0.0, 20.0),
    )
    state = r.begin_drag(7.5, 7.5, HIT_BODY)
    r.update_drag(100.0, 100.0, state)
    x0, y0, x1, y1 = r.rect()
    assert x1 <= 20.0 and y1 <= 20.0
    assert x0 >= 0.0 and y0 >= 0.0


def test_corner_drag_with_snap():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    r.set_snap_step((1.0, 1.0))
    state = r.begin_drag(10.0, 10.0, HIT_SE)
    r.update_drag(13.4, 13.6, state)
    # SE corner snaps to nearest integer.
    assert r.rect() == (0.0, 0.0, 13.0, 14.0)


def test_begin_drag_rejects_hit_none():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    with pytest.raises(ValueError):
        r.begin_drag(5.0, 5.0, HIT_NONE)


def test_end_drag_returns_rect():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    state = r.begin_drag(5.0, 5.0, HIT_BODY)
    r.update_drag(7.0, 8.0, state)
    assert r.end_drag(state) == (2.0, 3.0, 12.0, 13.0)


# --- persistence ----------------------------------------------------

def test_state_round_trip():
    r = RectROI(
        roi_id="map_select",
        rect=(1.0, 2.0, 3.0, 4.0),
        bounds_x=(0.0, 10.0),
        snap_step=(1.0, 1.0),
        label="map_select",
    )
    state = r.get_state()

    other = RectROI()
    other.apply_state(state)
    assert other.roi_id == "map_select"
    assert other.rect() == (1.0, 2.0, 3.0, 4.0)
    assert other.label == "map_select"
    assert other.snap_step() == (1.0, 1.0)


def test_apply_state_partial_payload():
    r = RectROI(rect=(0.0, 0.0, 10.0, 10.0))
    r.apply_state({"rect": [2.0, 3.0, 7.0, 8.0]})
    assert r.rect() == (2.0, 3.0, 7.0, 8.0)


# --- rendering smoke ------------------------------------------------

def test_render_completes_on_real_painter(qapp):
    img = QImage(200, 200, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        r = RectROI(rect=(40.0, 40.0, 160.0, 160.0), label="roi")
        r.render(
            p, QRectF(0, 0, 200, 200), data_to_pixel=_identity_xy(),
        )
        r.render(
            p, QRectF(0, 0, 200, 200),
            data_to_pixel=_identity_xy(), hover=True,
        )
        # Off-screen rect — should not raise.
        off = RectROI(rect=(-500.0, -500.0, -400.0, -400.0))
        off.render(
            p, QRectF(0, 0, 200, 200), data_to_pixel=_identity_xy(),
        )
    finally:
        p.end()
