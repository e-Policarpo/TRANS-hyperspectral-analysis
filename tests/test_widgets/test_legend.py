"""
Tests for the ported ``LegendBox``.

Exercises the geometry layout, anchor math, drag offset arithmetic,
hit-testing, and the get/apply-state round-trip. ``QFont`` /
``QPainter`` are imported but tests don't paint — the layout
algorithm is what we're locking down.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from src.widgets._pyqtgraph_ports.legend import (
    ANCHOR_BOTTOM_LEFT,
    ANCHOR_BOTTOM_RIGHT,
    ANCHOR_TOP_LEFT,
    ANCHOR_TOP_RIGHT,
    HIT_BODY,
    HIT_EYE,
    HIT_NONE,
    LegendBox,
    LegendEntry,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def font(qapp) -> QFont:
    f = QFont()
    f.setPointSize(9)
    return f


def _entries(*labels: str) -> list[LegendEntry]:
    return [
        LegendEntry(
            curve_id=i, label=label, color="#5BCEFA",
            linewidth=2.0, linestyle="-",
        )
        for i, label in enumerate(labels)
    ]


# --- state defaults + setters ------------------------------------------

def test_legend_defaults_to_top_right(font):
    lb = LegendBox()
    assert lb.anchor() == ANCHOR_TOP_RIGHT
    assert lb.offset() == (10.0, 10.0)


def test_legend_set_anchor_rejects_unknown(font):
    lb = LegendBox()
    with pytest.raises(ValueError):
        lb.set_anchor("middle-of-nowhere")


@pytest.mark.parametrize("anchor", [
    ANCHOR_TOP_LEFT, ANCHOR_TOP_RIGHT,
    ANCHOR_BOTTOM_LEFT, ANCHOR_BOTTOM_RIGHT,
])
def test_legend_geometry_lands_inside_or_near_axes_rect(font, anchor):
    """For default offset (10, 10), the anchored corner of the
    legend should sit close to the corresponding corner of
    ``ax_rect``, with the body extending into the rect."""
    lb = LegendBox(anchor=anchor, offset_px=(10.0, 10.0))
    ax_rect = QRectF(0, 0, 600, 400)
    entries = _entries("A", "B", "Long label C")
    geom = lb.compute_geometry(font, ax_rect, entries)
    assert geom is not None
    body = geom.bounding_rect
    # For each anchor, check the anchored corner is 10 px inside.
    if anchor == ANCHOR_TOP_LEFT:
        assert body.left() == pytest.approx(10.0)
        assert body.top() == pytest.approx(10.0)
    elif anchor == ANCHOR_TOP_RIGHT:
        assert body.right() == pytest.approx(590.0)
        assert body.top() == pytest.approx(10.0)
    elif anchor == ANCHOR_BOTTOM_LEFT:
        assert body.left() == pytest.approx(10.0)
        assert body.bottom() == pytest.approx(390.0)
    else:  # ANCHOR_BOTTOM_RIGHT
        assert body.right() == pytest.approx(590.0)
        assert body.bottom() == pytest.approx(390.0)


def test_legend_geometry_empty_entries_returns_none(font):
    lb = LegendBox()
    geom = lb.compute_geometry(font, QRectF(0, 0, 600, 400), [])
    assert geom is None
    assert lb.geometry() is None


def test_legend_geometry_one_row_per_entry(font):
    lb = LegendBox()
    ax_rect = QRectF(0, 0, 600, 400)
    entries = _entries("A", "B", "C", "D")
    geom = lb.compute_geometry(font, ax_rect, entries)
    assert geom is not None
    assert len(geom.row_rects) == 4
    assert len(geom.eye_rects) == 4
    assert len(geom.sample_rects) == 4
    assert len(geom.label_rects) == 4
    # Rows are vertically stacked and non-overlapping.
    for prev, curr in zip(geom.row_rects, geom.row_rects[1:]):
        assert curr.top() >= prev.bottom() - 0.5


# --- hidden-curves --------------------------------------------------

def test_legend_hidden_curve_round_trips_through_state():
    lb = LegendBox()
    lb.set_curve_hidden(3, True)
    lb.set_curve_hidden(5, True)
    state = lb.get_state()
    assert sorted(state["hidden_curves"]) == [3, 5]

    other = LegendBox()
    other.apply_state(state)
    assert other.is_curve_hidden(3)
    assert other.is_curve_hidden(5)
    assert not other.is_curve_hidden(7)


def test_legend_apply_state_ignores_missing_and_bogus_fields():
    lb = LegendBox()
    lb.apply_state({})  # nothing changes
    assert lb.anchor() == ANCHOR_TOP_RIGHT
    assert lb.offset() == (10.0, 10.0)
    assert lb.hidden_curves() == []

    lb.apply_state({"anchor": "totally-bogus",
                    "offset_px": "not a tuple",
                    "hidden_curves": "nope"})
    assert lb.anchor() == ANCHOR_TOP_RIGHT  # unchanged


def test_legend_apply_state_loads_full_payload():
    lb = LegendBox()
    lb.apply_state({
        "anchor": "bottom-left",
        "offset_px": [42.0, 17.0],
        "hidden_curves": [1, 2, 3],
    })
    assert lb.anchor() == ANCHOR_BOTTOM_LEFT
    assert lb.offset() == (42.0, 17.0)
    assert lb.hidden_curves() == [1, 2, 3]


# --- drag arithmetic -------------------------------------------------

def test_legend_shift_offset_top_left_positive_dx_moves_right(font):
    """For a top-left-anchored legend, dragging right increases
    ``offset_px[0]`` (further from the anchor corner)."""
    lb = LegendBox(anchor=ANCHOR_TOP_LEFT, offset_px=(10.0, 10.0))
    ax_rect = QRectF(0, 0, 600, 400)
    lb.shift_offset(20.0, 0.0, ax_rect)
    assert lb.offset() == (30.0, 10.0)


def test_legend_shift_offset_top_right_positive_dx_moves_right(font):
    """For a top-right legend, dragging right DECREASES the offset
    (closer to the right edge)."""
    lb = LegendBox(anchor=ANCHOR_TOP_RIGHT, offset_px=(50.0, 10.0))
    ax_rect = QRectF(0, 0, 600, 400)
    lb.shift_offset(20.0, 0.0, ax_rect)
    assert lb.offset()[0] == pytest.approx(30.0)


def test_legend_shift_offset_clamps_within_axes_rect():
    """A huge drag is soft-clamped so the legend can't escape
    the axes rect entirely."""
    lb = LegendBox(anchor=ANCHOR_TOP_LEFT, offset_px=(10.0, 10.0))
    ax_rect = QRectF(0, 0, 100, 100)
    lb.shift_offset(10_000.0, 10_000.0, ax_rect)
    dx, dy = lb.offset()
    assert dx <= 100  # never further than the axes width
    assert dy <= 100


# --- hit testing ----------------------------------------------------

def test_legend_hit_test_outside_returns_none(font):
    lb = LegendBox()
    ax_rect = QRectF(0, 0, 600, 400)
    lb.compute_geometry(font, ax_rect, _entries("A"))
    res, cid = lb.hit_test(QPointF(0, 0))
    assert res == HIT_NONE
    assert cid is None


def test_legend_hit_test_body_returns_drag_region(font):
    lb = LegendBox()
    ax_rect = QRectF(0, 0, 600, 400)
    geom = lb.compute_geometry(font, ax_rect, _entries("A", "B"))
    assert geom is not None
    # A point at the centre of the bounding rect — but not on the
    # eye toggle — should hit the body.
    body_centre = geom.bounding_rect.center()
    # Shift left so we miss the eye toggle on the right.
    test_pt = QPointF(
        geom.bounding_rect.left() + 10, body_centre.y(),
    )
    res, cid = lb.hit_test(test_pt)
    assert res == HIT_BODY
    assert cid is None


def test_legend_hit_test_eye_returns_curve_id(font):
    lb = LegendBox()
    ax_rect = QRectF(0, 0, 600, 400)
    geom = lb.compute_geometry(font, ax_rect, _entries("A", "B"))
    assert geom is not None
    # Centre of row 1's eye rect.
    eye = geom.eye_rects[1]
    res, cid = lb.hit_test(eye.center())
    assert res == HIT_EYE
    assert cid == 1  # second entry → curve_id=1
