"""
Tests for the ported pyqtgraph ViewBox state machine.

These exercise the algorithmic parts of ``ViewBoxState`` — range
mutation, limits, aspect lock, axis inversion, mouse-mode interaction,
scale history. No Qt required.
"""

from __future__ import annotations

import math

import pytest

from src.widgets._pyqtgraph_ports.viewbox import (
    MOUSE_MODE_PAN,
    MOUSE_MODE_RECT,
    ViewBoxState,
    ViewRect,
)


def _identity_transforms(vb: ViewBoxState) -> None:
    """A pixel↔data adapter that's literally the identity; lets the
    tests reason about coordinates in 1:1 pixel-data units."""
    vb.set_transforms(lambda px, py: (px, py), lambda x, y: (x, y))
    vb.set_axes_pixel_rect((0.0, 0.0, 100.0, 100.0))


# --- view range ---------------------------------------------------------

def test_default_view_range_is_unit_square():
    vb = ViewBoxState()
    assert vb.view_range().as_tuple() == (0.0, 1.0, 0.0, 1.0)


def test_set_view_range_sorts_and_pushes_history():
    vb = ViewBoxState()
    vb.set_view_range(10.0, 0.0, 100.0, 50.0)
    # Sorting normalises swapped input.
    assert vb.view_range().as_tuple() == (0.0, 10.0, 50.0, 100.0)
    # Previous (default) range is on the history stack.
    assert vb.undo_view() is True
    assert vb.view_range().as_tuple() == (0.0, 1.0, 0.0, 1.0)


def test_set_view_range_disables_auto_by_default():
    vb = ViewBoxState()
    assert vb.auto_range_enabled() is True
    vb.set_view_range(0, 10, 0, 10)
    assert vb.auto_range_enabled() is False


def test_set_view_range_no_disable_keeps_auto_on():
    vb = ViewBoxState()
    vb.set_view_range(0, 10, 0, 10, disable_auto=False)
    assert vb.auto_range_enabled() is True


# --- limits -------------------------------------------------------------

def test_limits_clamp_subsequent_range_changes():
    vb = ViewBoxState()
    vb.set_limits(x_min=0, x_max=100, y_min=0, y_max=100)
    vb.set_view_range(-50, 200, -50, 200)
    assert vb.view_range().as_tuple() == (0, 100, 0, 100)


def test_limits_clamp_existing_range_on_set():
    vb = ViewBoxState()
    vb.set_view_range(-50, 200, -50, 200)  # no limits yet → kept as-is
    assert vb.view_range().x_min == -50
    vb.set_limits(x_min=0)  # now clamp x_min
    assert vb.view_range().x_min == 0


def test_partial_limits_leave_other_axis_free():
    vb = ViewBoxState()
    vb.set_limits(x_min=0)  # no x_max, no y limits
    vb.set_view_range(-10, 1e9, -1e9, 1e9)
    r = vb.view_range()
    assert r.x_min == 0  # clamped
    assert r.x_max == 1e9  # unbounded
    assert r.y_min == -1e9 and r.y_max == 1e9


# --- auto-range ---------------------------------------------------------

def test_trigger_auto_range_applies_margin():
    vb = ViewBoxState()
    vb.set_auto_range_data(ViewRect(0, 10, 0, 100))
    vb.set_auto_range_margin(0.1)
    vb.trigger_auto_range()
    r = vb.view_range()
    # 10-unit-wide data → 1.0 µm margin on each side.
    assert r.x_min == pytest.approx(-1.0)
    assert r.x_max == pytest.approx(11.0)
    assert r.y_min == pytest.approx(-10.0)
    assert r.y_max == pytest.approx(110.0)


def test_trigger_auto_range_keeps_auto_on():
    vb = ViewBoxState()
    vb.set_auto_range_data(ViewRect(0, 1, 0, 1))
    vb.set_auto_range_enabled(False)
    vb.trigger_auto_range()
    assert vb.auto_range_enabled() is True


def test_trigger_auto_range_noop_without_data():
    vb = ViewBoxState()
    initial = vb.view_range().as_tuple()
    vb.trigger_auto_range()  # no auto-range data registered
    assert vb.view_range().as_tuple() == initial


# --- aspect lock --------------------------------------------------------

def test_aspect_lock_squares_y_range_to_x():
    vb = ViewBoxState()
    vb.set_aspect_locked(True, ratio=1.0)
    vb.set_view_range(0, 10, 0, 100)
    r = vb.view_range()
    # With ratio=1, height matches width (= 10).
    assert r.height == pytest.approx(10.0)
    # Centred on original midpoint (50).
    assert (r.y_min + r.y_max) / 2 == pytest.approx(50.0)


def test_aspect_lock_with_non_unit_ratio():
    vb = ViewBoxState()
    vb.set_aspect_locked(True, ratio=2.0)
    vb.set_view_range(0, 10, 0, 100)
    # height = width / ratio = 10 / 2 = 5.
    assert vb.view_range().height == pytest.approx(5.0)


# --- inversion ----------------------------------------------------------

def test_inverted_axes_flags():
    vb = ViewBoxState()
    assert (vb.inverted_x(), vb.inverted_y()) == (False, False)
    vb.set_inverted(x=True)
    assert vb.inverted_x() is True and vb.inverted_y() is False
    vb.set_inverted(y=True)
    assert vb.inverted_x() is True and vb.inverted_y() is True


# --- zoom history -------------------------------------------------------

def test_undo_view_pops_history_in_lifo_order():
    vb = ViewBoxState()
    vb.set_view_range(0, 10, 0, 10)
    vb.set_view_range(2, 8, 2, 8)
    vb.set_view_range(4, 6, 4, 6)
    assert vb.view_range().as_tuple() == (4, 6, 4, 6)
    assert vb.undo_view() is True
    assert vb.view_range().as_tuple() == (2, 8, 2, 8)
    assert vb.undo_view() is True
    assert vb.view_range().as_tuple() == (0, 10, 0, 10)
    assert vb.undo_view() is True       # back to the initial default
    assert vb.view_range().as_tuple() == (0, 1, 0, 1)
    assert vb.undo_view() is False      # nothing left to undo


def test_history_length_caps_at_limit():
    vb = ViewBoxState()
    vb._scale_history_limit = 3  # type: ignore[attr-defined]
    for i in range(10):
        vb.set_view_range(i, i + 1, 0, 1)
    # Only the last 3 prior ranges are remembered.
    assert len(vb._scale_history) == 3  # type: ignore[attr-defined]


# --- mouse mode + interaction ------------------------------------------

def test_default_mouse_mode_is_pan():
    vb = ViewBoxState()
    assert vb.mouse_mode() == MOUSE_MODE_PAN


def test_set_mouse_mode_rejects_unknown():
    vb = ViewBoxState()
    with pytest.raises(ValueError):
        vb.set_mouse_mode("zoom-square")


def test_set_mouse_mode_cancels_in_flight_interaction():
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_mouse_mode(MOUSE_MODE_RECT)
    vb.handle_press_left((10.0, 10.0))
    assert vb.is_selecting() is True
    vb.set_mouse_mode(MOUSE_MODE_PAN)
    assert vb.is_selecting() is False


def test_left_drag_pans_in_pan_mode():
    """Default (pan) mode: left-drag pans, like a right-drag. This is
    what the toolbar pan/zoom toggle controls."""
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_view_range(0, 100, 0, 100, push_history=False)
    assert vb.mouse_mode() == MOUSE_MODE_PAN
    vb.handle_press_left((50.0, 50.0))
    assert vb.is_panning() is True
    assert vb.is_selecting() is False
    changed = vb.handle_move((40.0, 60.0))  # 10 px left, 10 px down
    assert changed is True
    r = vb.view_range()
    assert r.x_min == pytest.approx(10.0)
    assert r.x_max == pytest.approx(110.0)
    # Releasing a left-pan returns no zoom-rect.
    assert vb.handle_release_left((40.0, 60.0)) is None
    assert vb.is_panning() is False


def test_right_drag_pans_view_in_pixel_space():
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_view_range(0, 100, 0, 100, push_history=False)
    vb.handle_press_right((50.0, 50.0))
    changed = vb.handle_move((40.0, 60.0))  # 10 px left, 10 px down
    assert changed is True
    r = vb.view_range()
    # Pixel-to-data is identity, axes rect is 0..100, so a 10 px shift
    # left moves world coords +10. Y is pixel-down → world-down.
    assert r.x_min == pytest.approx(10.0)
    assert r.x_max == pytest.approx(110.0)
    assert r.y_min == pytest.approx(-10.0)
    assert r.y_max == pytest.approx(90.0)


def test_left_drag_zoom_rect_succeeds_when_long_enough():
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_mouse_mode(MOUSE_MODE_RECT)
    vb.set_view_range(0, 100, 0, 100, push_history=False)
    vb.handle_press_left((10.0, 10.0))
    vb.handle_move((90.0, 90.0))
    result = vb.handle_release_left((90.0, 90.0))
    # release returns (x_min, y_min, x_max, y_max)
    assert result == pytest.approx((10.0, 10.0, 90.0, 90.0))
    # ViewRect.as_tuple is (x_min, x_max, y_min, y_max)
    assert vb.view_range().as_tuple() == pytest.approx((10.0, 90.0, 10.0, 90.0))


def test_left_drag_zoom_rect_below_threshold_is_click():
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_mouse_mode(MOUSE_MODE_RECT)
    vb.handle_press_left((10.0, 10.0))
    # Move only 2 px — below the 5 px drag threshold.
    result = vb.handle_release_left((12.0, 12.0))
    assert result is None
    assert vb.is_selecting() is False


def test_wheel_zoom_centred_on_cursor():
    vb = ViewBoxState()
    _identity_transforms(vb)
    vb.set_view_range(0, 100, 0, 100, push_history=False)
    # Wheel up at the centre — zooms in (shrink × range).
    vb.handle_wheel((50.0, 50.0), delta_y=120.0)
    r = vb.view_range()
    # zoom_step is 0.85 → new width = 85.
    assert r.width == pytest.approx(85.0)
    # Centre stays put.
    assert (r.x_min + r.x_max) / 2 == pytest.approx(50.0)


def test_x_mode_only_pan_keeps_y_fixed():
    vb = ViewBoxState(x_mode_only=True)
    _identity_transforms(vb)
    vb.set_view_range(0, 100, 0, 100, push_history=False)
    vb.handle_press_right((50.0, 50.0))
    vb.handle_move((30.0, 80.0))
    r = vb.view_range()
    assert r.x_min != 0 and r.x_max != 100  # x panned
    assert r.y_min == 0 and r.y_max == 100  # y stayed put


def test_double_click_resets_to_auto_range():
    vb = ViewBoxState()
    vb.set_auto_range_data(ViewRect(0, 1, 0, 1))
    vb.set_view_range(50, 60, 50, 60)
    assert vb.auto_range_enabled() is False
    vb.handle_double_click()
    assert vb.auto_range_enabled() is True
    r = vb.view_range()
    # default 5 % margin: data is 1 unit wide → 0.05 each side.
    assert r.x_min == pytest.approx(-0.05)
    assert r.x_max == pytest.approx(1.05)


# --- dirty callback ----------------------------------------------------

def test_dirty_callback_fires_on_state_mutation():
    vb = ViewBoxState()
    calls = []
    vb.set_dirty_callback(lambda: calls.append(None))
    vb.set_view_range(0, 10, 0, 10)
    assert calls
    calls.clear()
    vb.set_inverted(x=True)
    assert calls
