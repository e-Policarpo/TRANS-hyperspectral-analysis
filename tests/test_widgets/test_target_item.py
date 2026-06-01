"""
Tests for ``TargetItem`` — draggable point markers.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.widgets._pyqtgraph_ports.items.target_item import (
    HIT_NONE,
    HIT_TARGET,
    SYMBOL_CIRCLE,
    SYMBOL_CROSSHAIR,
    TargetItem,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _identity_xy():
    return lambda x, y: (float(x), float(y))


# --- defaults + setters --------------------------------------------

def test_defaults():
    t = TargetItem(target_id="peak_a", position=(10.0, 20.0))
    assert t.target_id == "peak_a"
    assert t.position() == (10.0, 20.0)
    assert t.symbol == SYMBOL_CROSSHAIR
    assert t.movable is True


def test_invalid_symbol_raises():
    with pytest.raises(ValueError):
        TargetItem(symbol="triangle")


def test_constructor_clamps_to_bounds():
    t = TargetItem(
        position=(50.0, -10.0),
        bounds_x=(0.0, 10.0),
        bounds_y=(0.0, 5.0),
    )
    assert t.position() == (10.0, 0.0)


def test_set_position_returns_changed_flag():
    t = TargetItem(position=(1.0, 2.0))
    assert t.set_position(1.0, 2.0) is False
    assert t.set_position(5.0, 6.0) is True
    assert t.position() == (5.0, 6.0)


def test_set_bounds_pulls_position_in():
    t = TargetItem(position=(15.0, 30.0))
    assert t.set_bounds(bounds_x=(0.0, 10.0), bounds_y=(0.0, 10.0)) is True
    assert t.position() == (10.0, 10.0)


# --- hit testing ----------------------------------------------------

def test_hit_test_on_symbol_centre():
    t = TargetItem(position=(50.0, 50.0), symbol_size=12.0)
    assert t.hit_test(50.0, 50.0, data_to_pixel=_identity_xy()) == HIT_TARGET


def test_hit_test_inside_radius():
    t = TargetItem(position=(50.0, 50.0), symbol_size=12.0)
    # Inside radius (6 + 2 = 8 px slop).
    assert t.hit_test(53.0, 53.0, data_to_pixel=_identity_xy()) == HIT_TARGET


def test_hit_test_misses_outside_radius():
    t = TargetItem(position=(50.0, 50.0), symbol_size=12.0)
    assert t.hit_test(200.0, 200.0, data_to_pixel=_identity_xy()) == HIT_NONE


def test_hit_test_ignored_when_not_movable():
    t = TargetItem(position=(50.0, 50.0), movable=False)
    assert t.hit_test(50.0, 50.0, data_to_pixel=_identity_xy()) == HIT_NONE


def test_hit_test_outside_ax_rect_short_circuits():
    t = TargetItem(position=(50.0, 50.0))
    rect = QRectF(0, 0, 5, 5)
    assert t.hit_test(
        50.0, 50.0, data_to_pixel=_identity_xy(), ax_rect=rect,
    ) == HIT_NONE


# --- drag state machine --------------------------------------------

def test_drag_preserves_cursor_offset():
    t = TargetItem(position=(50.0, 50.0))
    # Press 3 px below-right of centre.
    state = t.begin_drag(53.0, 53.0)
    # Drag the press point to (70, 80) — marker stays 3 px below-right
    # of the cursor, so centre lands at (67, 77).
    t.update_drag(70.0, 80.0, state)
    assert t.position() == pytest.approx((67.0, 77.0))


def test_drag_clamps_to_bounds():
    t = TargetItem(
        position=(0.0, 0.0),
        bounds_x=(-10.0, 10.0),
        bounds_y=(-10.0, 10.0),
    )
    state = t.begin_drag(0.0, 0.0)
    t.update_drag(50.0, 50.0, state)
    assert t.position() == (10.0, 10.0)


def test_end_drag_returns_position():
    t = TargetItem(position=(0.0, 0.0))
    state = t.begin_drag(0.0, 0.0)
    t.update_drag(7.5, 3.5, state)
    assert t.end_drag(state) == (7.5, 3.5)


# --- persistence ----------------------------------------------------

def test_state_round_trip():
    t = TargetItem(
        target_id="peak_b",
        position=(123.4, 56.7),
        bounds_x=(0.0, 1000.0),
        symbol=SYMBOL_CIRCLE,
        symbol_size=18.0,
        label="O-H stretch",
    )
    state = t.get_state()

    other = TargetItem()
    other.apply_state(state)
    assert other.target_id == "peak_b"
    assert other.position() == (123.4, 56.7)
    assert other.symbol == SYMBOL_CIRCLE
    assert other.label == "O-H stretch"


def test_apply_state_ignores_unknown_symbol():
    t = TargetItem(symbol=SYMBOL_CROSSHAIR)
    t.apply_state({"symbol": "totally-bogus"})
    assert t.symbol == SYMBOL_CROSSHAIR


def test_apply_state_partial_payload():
    t = TargetItem(position=(1.0, 2.0))
    t.apply_state({"position": [3.0, 4.0]})
    assert t.position() == (3.0, 4.0)


# --- rendering smoke ------------------------------------------------

def test_render_completes_on_real_painter(qapp):
    img = QImage(200, 100, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        for sym in (SYMBOL_CROSSHAIR, SYMBOL_CIRCLE):
            t = TargetItem(
                position=(80.0, 50.0), symbol=sym,
                label=f"sym={sym}",
            )
            t.render(
                p, QRectF(0, 0, 200, 100),
                data_to_pixel=_identity_xy(),
            )
            t.render(
                p, QRectF(0, 0, 200, 100),
                data_to_pixel=_identity_xy(), hover=True,
            )
        # Off-screen marker — should not raise.
        off = TargetItem(position=(-500.0, -500.0))
        off.render(
            p, QRectF(0, 0, 200, 100), data_to_pixel=_identity_xy(),
        )
    finally:
        p.end()
