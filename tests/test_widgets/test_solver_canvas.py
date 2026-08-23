"""
Tests for the well and dot plots.

Every panel here is drawn in one pass: `showWell`/`showDot` create the axes,
then title them. So anything that raises while building a title takes the
whole figure with it — the axes are already there, empty and unstyled. That
is how a solve opened straight from the Tools menu, with no measured levels
to compare against, came out as three blank white panels.

The comparison block is optional by design: it only exists when a candidate
was simulated against real data. These check both readings.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtQuick")
from PySide6.QtGui import QGuiApplication

from src.widgets.qml_solver_canvas import SolverCanvas


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    item = SolverCanvas()
    item.setWidth(600)
    item.setHeight(500)
    yield item
    item.cleanup()


def _well(**extra):
    result = {'ok': True, 'E_eV': [0.1, 0.4, 0.9],
              'x_nm': [0.0, 1.0, 2.0], 'V_eV': [0.0, 0.0, 0.0],
              'psi': [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]]}
    result.update(extra)
    return result


def _dot(**extra):
    result = {'ok': True,
              'levels': [{'index': 0, 'E_eV': 0.2, 'label': '1s',
                          'degeneracy': 1, 'occupancy': 2},
                         {'index': 1, 'E_eV': 0.5, 'label': '1p',
                          'degeneracy': 2, 'occupancy': 4}],
              'shells': [{'label': '1s', 'filled': 2}],
              'dos': {'x': [0.0, 0.5, 1.0], 'y': [0.0, 1.0, 0.0]},
              'addition_eV': [0.2, 0.3, 0.5],
              'radial': {'r_nm': [0.0, 1.0], 'psi': [1.0, 0.0], 'label': '1s'}}
    result.update(extra)
    return result


# ── the titles ──────────────────────────────────────────────────────────────

def test_is_number_rejects_none_and_nan():
    # `x == x` alone reads as "not NaN" and lets None through; None is what
    # a result with no comparison hands over.
    assert SolverCanvas._is_number(0.0)
    assert SolverCanvas._is_number(3)
    assert not SolverCanvas._is_number(None)
    assert not SolverCanvas._is_number(float('nan'))
    assert not SolverCanvas._is_number("0.5")
    assert not SolverCanvas._is_number(True)


@pytest.mark.parametrize("comparison", [
    {},                            # solved from the menu — nothing to compare
    {'rrmse_pct': None},           # a comparison that failed to produce one
    {'rrmse_pct': float('nan')},
])
def test_well_title_without_a_usable_comparison(comparison):
    title = SolverCanvas._well_title(_well(), comparison)
    assert title == "3 state(s)"


def test_well_title_reports_the_error_and_the_coverage():
    title = SolverCanvas._well_title(
        _well(), {'rrmse_pct': 1.25, 'covered': False})
    assert "1.250%" in title
    assert "above the last level" in title


@pytest.mark.parametrize("comparison", [
    {}, {'rrmse_pct': None}, {'rrmse_pct': float('nan')},
])
def test_dot_title_without_a_usable_comparison(comparison):
    title = SolverCanvas._dot_title(_dot(comparison=comparison))
    assert title == "2 level(s) in 1 shell(s)"


def test_dot_title_reports_the_error():
    assert "0.750%" in SolverCanvas._dot_title(
        _dot(comparison={'rrmse_pct': 0.75}))


# ── the figures they title ──────────────────────────────────────────────────

def test_well_draws_both_panels_with_no_comparison(canvas):
    canvas.showWell(_well(), 0)
    axes = canvas.figure.axes
    assert len(axes) == 2
    # The potential, the three levels, and the labelled selected one.
    assert axes[0].lines, "the well panel came out empty"
    assert axes[1].lines, "the density panel came out empty"


def test_dot_draws_all_four_panels_with_no_comparison(canvas):
    # The regression: the title raised, and showDot aborted after add_subplot
    # had already made the axes — four panels present, three of them blank.
    canvas.showDot(_dot(), 0)
    axes = canvas.figure.axes
    assert len(axes) == 4
    assert axes[0].patches, "shells panel came out empty"
    assert axes[1].lines, "density-of-states panel came out empty"
    assert axes[2].lines, "addition-energy panel came out empty"
    assert axes[3].lines, "radial panel came out empty"


def test_dot_marks_the_measured_levels_when_there_are_some(canvas):
    canvas.showDot(_dot(comparison={'rrmse_pct': 0.5, 'targets': [0.2, 0.5]}), 0)
    dos_ax = canvas.figure.axes[1]
    # Two dashed verticals, one per measured level.
    assert len([line for line in dos_ax.lines
                if line.get_linestyle() in ('--', (0, (6.4, 1.6)))]) >= 2


def test_nothing_solved_says_so_rather_than_drawing_axes(canvas):
    canvas.showWell({'E_eV': [], 'x_nm': [], 'error': "no bound states"}, 0)
    texts = [t.get_text() for ax in canvas.figure.axes for t in ax.texts]
    assert "no bound states" in texts


def test_a_state_index_past_the_end_is_clamped(canvas):
    canvas.showWell(_well(), 99)
    labels = [line.get_label() for line in canvas.figure.axes[0].lines]
    assert any("E3" in str(label) for label in labels)
    assert not math.isnan(canvas.figure.axes[0].get_ylim()[0])
