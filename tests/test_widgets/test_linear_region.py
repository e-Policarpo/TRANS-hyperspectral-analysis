"""
Tests for ``LinearRegionItem``.

Pure-state behaviour: bounds clamping, swap-mode policies, hit-test
classification, drag state-machine, persistence round-trip. The render
path is exercised by a smoke test that builds a real ``QPainter`` on a
``QImage``; we don't assert pixel contents here, only that the call
sequence completes without raising.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.widgets._pyqtgraph_ports.items.linear_region import (
    HIT_BODY,
    HIT_HANDLE_HI,
    HIT_HANDLE_LO,
    HIT_NONE,
    LinearRegionItem,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _identity_x():
    """Default ``data_to_pixel_x`` for tests — data coords ARE pixels.
    Lets us reason about hit-tests in the same units as the region."""
    return lambda x: float(x)


# --- defaults + accessors ------------------------------------------

def test_defaults():
    item = LinearRegionItem(region_id="peak_window")
    assert item.region_id == "peak_window"
    assert item.region() == (0.0, 1.0)
    assert item.movable is True
    assert item.bounds() is None


def test_horizontal_orientation_unsupported():
    with pytest.raises(NotImplementedError):
        LinearRegionItem(orientation="horizontal")


def test_invalid_swap_mode():
    with pytest.raises(ValueError):
        LinearRegionItem(swap_mode="totally-bogus")


def test_sort_swap_mode_sorts_on_read():
    item = LinearRegionItem(values=(5.0, 2.0), swap_mode="sort")
    # Raw stays as written, region() returns sorted.
    assert item.raw_values() == (5.0, 2.0)
    assert item.region() == (2.0, 5.0)


def test_no_swap_mode_preserves_raw_order():
    item = LinearRegionItem(values=(5.0, 2.0), swap_mode=None)
    assert item.region() == (5.0, 2.0)


# --- bounds clamping ------------------------------------------------

def test_set_region_clamps_to_bounds():
    item = LinearRegionItem(values=(2.0, 3.0), bounds=(0.0, 10.0))
    item.set_region(-5.0, 50.0)
    assert item.region() == (0.0, 10.0)


def test_set_bounds_pulls_existing_region_in():
    item = LinearRegionItem(values=(2.0, 8.0))
    item.set_bounds((4.0, 6.0))
    assert item.region() == (4.0, 6.0)


def test_set_bounds_none_disables():
    item = LinearRegionItem(values=(2.0, 8.0), bounds=(0.0, 10.0))
    item.set_bounds((None, None))
    assert item.bounds() is None
    item.set_region(-100.0, 100.0)
    assert item.region() == (-100.0, 100.0)


def test_set_bounds_returns_changed_flag():
    item = LinearRegionItem(values=(2.0, 8.0))
    assert item.set_bounds((4.0, 6.0)) is True
    assert item.set_bounds((4.0, 6.0)) is False  # already within


# --- hit testing ----------------------------------------------------

def test_hit_test_on_handle_lo():
    item = LinearRegionItem(values=(10.0, 20.0))
    res = item.hit_test(10.0, data_to_pixel_x=_identity_x())
    assert res == HIT_HANDLE_LO


def test_hit_test_on_handle_hi():
    item = LinearRegionItem(values=(10.0, 20.0))
    res = item.hit_test(20.0, data_to_pixel_x=_identity_x())
    assert res == HIT_HANDLE_HI


def test_hit_test_in_body():
    # Handles 50 apart, slop=6 → ample clearance for a real body hit
    # at the band centre.
    item = LinearRegionItem(values=(10.0, 60.0))
    res = item.hit_test(35.0, data_to_pixel_x=_identity_x())
    assert res == HIT_BODY


def test_hit_test_misses_outside():
    item = LinearRegionItem(values=(10.0, 20.0))
    res = item.hit_test(50.0, data_to_pixel_x=_identity_x())
    assert res == HIT_NONE


def test_hit_test_handle_wins_over_body_at_slop_boundary():
    item = LinearRegionItem(values=(10.0, 30.0), handle_grab_px=6.0)
    # 11 px → inside lo's slop window of [4, 16]; should be HANDLE_LO,
    # not BODY.
    res = item.hit_test(11.0, data_to_pixel_x=_identity_x())
    assert res == HIT_HANDLE_LO


def test_hit_test_ignored_when_not_movable():
    item = LinearRegionItem(values=(10.0, 20.0), movable=False)
    res = item.hit_test(15.0, data_to_pixel_x=_identity_x())
    assert res == HIT_NONE


def test_hit_test_outside_ax_rect_short_circuits():
    item = LinearRegionItem(values=(10.0, 20.0))
    rect = QRectF(0, 0, 5, 100)  # x_pixel=15 is outside this rect
    res = item.hit_test(15.0, data_to_pixel_x=_identity_x(), ax_rect=rect)
    assert res == HIT_NONE


# --- drag state machine --------------------------------------------

def test_drag_body_translates_both_handles():
    item = LinearRegionItem(values=(10.0, 20.0))
    state = item.begin_drag(15.0, HIT_BODY)
    changed = item.update_drag(18.0, state)
    assert changed is True
    # +3 dx → both handles shifted by 3.
    assert item.region() == (13.0, 23.0)


def test_drag_handle_lo_only_moves_low_handle():
    item = LinearRegionItem(values=(10.0, 20.0))
    state = item.begin_drag(10.0, HIT_HANDLE_LO)
    item.update_drag(12.5, state)
    assert item.region() == (12.5, 20.0)


def test_drag_block_swap_holds_handle_at_other():
    item = LinearRegionItem(values=(10.0, 20.0), swap_mode="block")
    state = item.begin_drag(10.0, HIT_HANDLE_LO)
    # Drag low handle past the high handle.
    item.update_drag(30.0, state)
    # Block mode: dragged handle is held at the fixed handle's value.
    assert item.region() == (20.0, 20.0)


def test_drag_push_carries_fixed_handle_along():
    item = LinearRegionItem(values=(10.0, 20.0), swap_mode="push")
    state = item.begin_drag(10.0, HIT_HANDLE_LO)
    item.update_drag(30.0, state)
    # Push mode: fixed handle moves to match the dragged one.
    assert item.region() == (30.0, 30.0)


def test_drag_with_bounds_collapses_band_at_edge():
    """Pyqtgraph's behaviour: each handle is clamped independently
    on a body drag, so a band pressed past the upper bound *collapses*
    to a zero-width region at the bound rather than translating."""
    item = LinearRegionItem(values=(10.0, 20.0), bounds=(0.0, 25.0))
    state = item.begin_drag(15.0, HIT_BODY)
    item.update_drag(45.0, state)
    lo, hi = item.region()
    assert lo == pytest.approx(25.0)
    assert hi == pytest.approx(25.0)


def test_begin_drag_rejects_hit_none():
    item = LinearRegionItem(values=(10.0, 20.0))
    with pytest.raises(ValueError):
        item.begin_drag(15.0, HIT_NONE)


def test_end_drag_returns_region():
    item = LinearRegionItem(values=(10.0, 20.0))
    state = item.begin_drag(15.0, HIT_BODY)
    item.update_drag(18.0, state)
    assert item.end_drag(state) == (13.0, 23.0)


# --- persistence ----------------------------------------------------

def test_get_state_round_trip():
    item = LinearRegionItem(
        region_id="cosmic_window",
        values=(10.5, 20.25),
        bounds=(0.0, 100.0),
        movable=True,
        swap_mode="sort",
        pen_color="#FF00FF",
        brush_color="#00FFFF",
        brush_alpha=80,
        label="cosmic",
    )
    state = item.get_state()

    other = LinearRegionItem()
    other.apply_state(state)
    assert other.region_id == "cosmic_window"
    assert other.region() == (10.5, 20.25)
    assert other.bounds() == (0.0, 100.0)
    assert other.movable is True
    assert other.label == "cosmic"


def test_apply_state_ignores_unknown_swap_mode():
    item = LinearRegionItem(swap_mode="sort")
    item.apply_state({"swap_mode": "totally-bogus"})
    # Swap mode unchanged.
    assert item.get_state()["swap_mode"] == "sort"


def test_apply_state_pulls_existing_values_into_new_bounds():
    item = LinearRegionItem(values=(2.0, 8.0))
    item.apply_state({"bounds": [4.0, 6.0]})
    assert item.region() == (4.0, 6.0)


def test_apply_state_tolerates_partial_payload():
    item = LinearRegionItem(values=(2.0, 8.0))
    item.apply_state({"values": [3.0, 5.0]})
    assert item.region() == (3.0, 5.0)
    # Other fields unchanged.
    assert item.bounds() is None


# --- rendering smoke ------------------------------------------------

def test_render_completes_on_real_painter(qapp):
    """Render onto a QImage so the QPainter calls execute end-to-end.
    No pixel assertions — we just want to catch obvious crashes (bad
    pen/brush, off-by-one in the rect math) before the canvas takes
    a swing."""
    img = QImage(200, 100, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        item = LinearRegionItem(
            values=(40.0, 120.0), label="test",
        )
        item.render(
            p,
            QRectF(0, 0, 200, 100),
            data_to_pixel_x=lambda x: x,  # 1-px-per-data-unit
        )
        # Hover variant + entirely off-screen variant — both should
        # complete silently.
        item.render(
            p, QRectF(0, 0, 200, 100),
            data_to_pixel_x=lambda x: x, hover=True,
        )
        item.set_region(-100.0, -10.0)  # off-screen left
        item.render(
            p, QRectF(0, 0, 200, 100), data_to_pixel_x=lambda x: x,
        )
    finally:
        p.end()
