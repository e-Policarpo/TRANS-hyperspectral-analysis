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
from PySide6.QtGui import QGuiApplication

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
