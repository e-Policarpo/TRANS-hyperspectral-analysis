"""
Tests for the ``InfiniteLine`` overlay item.

Same shape as the ``LinearRegionItem`` tests — accessor defaults,
clamp behaviour under bounds, hit-test classification for both
orientations, drag preserves cursor offset, persistence round-trip,
and a render smoke on a real ``QImage``.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.widgets._pyqtgraph_ports.items.infinite_line import (
    HIT_LINE,
    HIT_NONE,
    ORIENT_HORIZONTAL,
    ORIENT_VERTICAL,
    InfiniteLine,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _identity_xy():
    """Default ``data_to_pixel`` for tests — data IS pixel space."""
    return lambda x, y: (float(x), float(y))


# --- defaults + setters ---------------------------------------------

def test_defaults_vertical():
    line = InfiniteLine(line_id="cursor", value=5.0)
    assert line.line_id == "cursor"
    assert line.orientation == ORIENT_VERTICAL
    assert line.value() == 5.0
    assert line.movable is True


def test_invalid_orientation_raises():
    with pytest.raises(ValueError):
        InfiniteLine(orientation="diagonal")


def test_constructor_clamps_to_bounds():
    line = InfiniteLine(value=50.0, bounds=(0.0, 10.0))
    assert line.value() == 10.0


def test_set_value_returns_changed_flag():
    line = InfiniteLine(value=5.0)
    assert line.set_value(5.0) is False
    assert line.set_value(7.0) is True
    assert line.value() == 7.0


def test_set_bounds_pulls_value_in():
    line = InfiniteLine(value=15.0)
    assert line.set_bounds((0.0, 10.0)) is True
    assert line.value() == 10.0
    # Already inside, no change.
    assert line.set_bounds((0.0, 10.0)) is False


# --- hit testing ----------------------------------------------------

def test_hit_test_vertical_on_line():
    line = InfiniteLine(value=50.0)
    res = line.hit_test(50.0, 25.0, data_to_pixel=_identity_xy())
    assert res == HIT_LINE


def test_hit_test_vertical_misses_far_left():
    line = InfiniteLine(value=50.0)
    res = line.hit_test(20.0, 25.0, data_to_pixel=_identity_xy())
    assert res == HIT_NONE


def test_hit_test_vertical_ignores_y_axis():
    line = InfiniteLine(value=50.0)
    # Same x, very different y — vertical line still hit.
    res = line.hit_test(50.0, 999.0, data_to_pixel=_identity_xy())
    assert res == HIT_LINE


def test_hit_test_horizontal_on_line():
    line = InfiniteLine(orientation=ORIENT_HORIZONTAL, value=25.0)
    res = line.hit_test(50.0, 25.0, data_to_pixel=_identity_xy())
    assert res == HIT_LINE


def test_hit_test_horizontal_ignores_x_axis():
    line = InfiniteLine(orientation=ORIENT_HORIZONTAL, value=25.0)
    res = line.hit_test(999.0, 25.0, data_to_pixel=_identity_xy())
    assert res == HIT_LINE


def test_hit_test_slop_boundary():
    line = InfiniteLine(value=50.0, handle_grab_px=6.0)
    # Just inside slop window — should hit.
    assert line.hit_test(55.9, 25.0, data_to_pixel=_identity_xy()) == HIT_LINE
    # Just outside.
    assert line.hit_test(56.5, 25.0, data_to_pixel=_identity_xy()) == HIT_NONE


def test_hit_test_ignored_when_not_movable():
    line = InfiniteLine(value=50.0, movable=False)
    res = line.hit_test(50.0, 25.0, data_to_pixel=_identity_xy())
    assert res == HIT_NONE


# --- drag state machine --------------------------------------------

def test_drag_vertical_preserves_cursor_offset():
    """Press 2 px to the right of the line — when dragged, the line
    follows but stays 2 px from the cursor."""
    line = InfiniteLine(value=50.0)
    state = line.begin_drag(52.0, 0.0)  # offset = 50 - 52 = -2
    line.update_drag(60.0, 0.0, state)
    assert line.value() == pytest.approx(58.0)


def test_drag_horizontal_preserves_cursor_offset():
    line = InfiniteLine(orientation=ORIENT_HORIZONTAL, value=25.0)
    state = line.begin_drag(0.0, 27.0)  # offset = 25 - 27 = -2
    line.update_drag(0.0, 35.0, state)
    assert line.value() == pytest.approx(33.0)


def test_drag_clamps_to_bounds():
    line = InfiniteLine(value=50.0, bounds=(0.0, 100.0))
    state = line.begin_drag(50.0, 0.0)
    line.update_drag(500.0, 0.0, state)
    assert line.value() == 100.0


def test_end_drag_returns_value():
    line = InfiniteLine(value=50.0)
    state = line.begin_drag(50.0, 0.0)
    line.update_drag(75.0, 0.0, state)
    assert line.end_drag(state) == 75.0


# --- persistence ----------------------------------------------------

def test_state_round_trip():
    line = InfiniteLine(
        line_id="x_cursor",
        orientation=ORIENT_HORIZONTAL,
        value=42.0,
        bounds=(-100.0, 100.0),
        label="y=42",
        pen_color="#FF0000",
    )
    state = line.get_state()

    other = InfiniteLine()
    other.apply_state(state)
    assert other.line_id == "x_cursor"
    assert other.orientation == ORIENT_HORIZONTAL
    assert other.value() == 42.0
    assert other.bounds() == (-100.0, 100.0)
    assert other.label == "y=42"


def test_apply_state_ignores_unknown_orientation():
    line = InfiniteLine(orientation=ORIENT_VERTICAL)
    line.apply_state({"orientation": "diagonal"})
    assert line.orientation == ORIENT_VERTICAL


def test_apply_state_partial_payload():
    line = InfiniteLine(value=5.0)
    line.apply_state({"value": 17.0})
    assert line.value() == 17.0


# --- rendering smoke ------------------------------------------------

def test_render_completes_on_real_painter(qapp):
    img = QImage(200, 100, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        for orient in (ORIENT_VERTICAL, ORIENT_HORIZONTAL):
            line = InfiniteLine(
                orientation=orient, value=40.0, label=f"{orient[0]}=40",
            )
            line.render(
                p, QRectF(0, 0, 200, 100),
                data_to_pixel=_identity_xy(),
            )
            line.render(
                p, QRectF(0, 0, 200, 100),
                data_to_pixel=_identity_xy(), hover=True,
            )
        # Off-screen line — should not raise.
        off = InfiniteLine(value=-9999.0)
        off.render(
            p, QRectF(0, 0, 200, 100), data_to_pixel=_identity_xy(),
        )
    finally:
        p.end()
