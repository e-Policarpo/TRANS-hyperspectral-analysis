"""
Tests for the Confinement Designer's plots.

Two pictures answer the two questions a candidate raises — does it explain
the measurement, and what was it fitted to. These check that each one draws
what it claims: the right number of bars, error colours that mean what the
legend says, and the branch boundaries visible where they fall.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QGuiApplication

from src.widgets.qml_designer_canvas import DesignerCanvas


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    item = DesignerCanvas()
    item.setWidth(640)
    item.setHeight(320)
    yield item
    item.cleanup()


def _candidate(**over):
    candidate = {
        'targets': [0.100, 0.200, 0.400],
        'computed': [0.101, 0.199, 0.410],
        'errors_pct': [1.0, -0.5, 2.5],
        'dims_nm': [8.001],
        'ndim': '1D',
        'coords': 'cartesian',
        'rrmse': 1.4,
        'meff': 0.067,
        'carrier': 'e',
    }
    candidate.update(over)
    return candidate


def _bars(ax):
    from matplotlib.patches import Rectangle
    return [p for p in ax.patches if isinstance(p, Rectangle)]


class TestTheCandidatePlot:
    def test_it_draws_the_levels_and_the_errors_side_by_side(self, canvas):
        canvas.showCandidate(_candidate())

        assert len(canvas.figure.axes) == 2
        levels, errors = canvas.figure.axes
        # One measured bar and one model bar per level, then one error bar.
        assert len(_bars(levels)) == 6
        assert len(_bars(errors)) == 3

    def test_the_bars_carry_the_numbers_they_were_given(self, canvas):
        canvas.showCandidate(_candidate())
        heights = sorted(round(b.get_height(), 3) for b in _bars(canvas.figure.axes[0]))

        assert heights == [0.1, 0.101, 0.199, 0.2, 0.4, 0.41]

    def test_the_error_colour_says_how_bad_it_is(self, canvas):
        """Green is as good as the measurement, red is a level the candidate
        does not explain — a number alone does not read at a glance."""
        canvas.showCandidate(_candidate(errors_pct=[0.5, 3.0, 12.0]))
        colours = [b.get_facecolor() for b in _bars(canvas.figure.axes[1])]

        from matplotlib.colors import to_rgba
        assert colours[0][:3] == pytest.approx(to_rgba(DesignerCanvas.ERROR_BANDS[0][1])[:3])
        assert colours[1][:3] == pytest.approx(to_rgba(DesignerCanvas.ERROR_BANDS[1][1])[:3])
        assert colours[2][:3] == pytest.approx(to_rgba(DesignerCanvas.ERROR_BAD)[:3])

    def test_a_negative_error_is_judged_by_its_size(self, canvas):
        canvas.showCandidate(_candidate(errors_pct=[-12.0]))
        from matplotlib.colors import to_rgba
        colour = _bars(canvas.figure.axes[1])[0].get_facecolor()

        assert colour[:3] == pytest.approx(to_rgba(DesignerCanvas.ERROR_BAD)[:3])

    def test_the_title_names_the_geometry(self, canvas):
        canvas.showCandidate(_candidate())

        assert "L = 8.001 nm" in canvas.figure.axes[0].get_title()

    def test_a_parabolic_dot_is_labelled_in_meV(self, canvas):
        """Its "dimensions" are confinement energies, and calling them nm
        would be a unit error on the face of the plot."""
        canvas.showCandidate(_candidate(ndim='0D', coords='parabolic',
                                        dims_nm=[20.0, 40.0]))
        title = canvas.figure.axes[0].get_title()

        assert "meV" in title and "ħω_xy" in title

    def test_an_unknown_model_still_gets_a_label(self, canvas):
        canvas.showCandidate(_candidate(ndim='4D', coords='hypercubic',
                                        dims_nm=[1.0, 2.0]))

        assert "d1" in canvas.figure.axes[0].get_title()

    def test_a_pair_draws_both_carriers(self, canvas):
        hole = _candidate(carrier='h', meff=0.45,
                          targets=[0.05, 0.09], computed=[0.051, 0.089],
                          errors_pct=[2.0, -1.1], dims_nm=[8.1])
        canvas.showCandidate(_candidate(hole=hole, pair_score=1.8,
                                        pair_mismatch_nm=0.099))
        levels, errors = canvas.figure.axes

        assert len(_bars(levels)) == 10           # 3 electron + 2 hole levels
        assert len(_bars(errors)) == 5
        assert "e⁻" in levels.get_title() and "h⁺" in levels.get_title()
        assert "pair error" in errors.get_title()

    def test_the_rrmse_is_on_the_error_panel(self, canvas):
        canvas.showCandidate(_candidate(rrmse=2.75))

        assert "2.75" in canvas.figure.axes[1].get_title()

    def test_nothing_selected_says_so_instead_of_drawing(self, canvas):
        canvas.showCandidate({})

        assert len(canvas.figure.axes) == 1
        assert canvas.figure.axes[0].texts[0].get_text() == "No candidate selected"


class TestTheSpectrumPlot:
    def _preview(self, **over):
        x = np.linspace(-1.0, 1.0, 101)
        preview = {
            'x': x.tolist(),
            'raw': (x ** 2).tolist(),
            'corrected': (x ** 2 - 0.1).tolist(),
            'baseline': np.full_like(x, 0.1).tolist(),
            'peaks_V': [-0.5, 0.5],
            'column': 'P1',
            'split_e': 0.2,
            'split_h': -0.3,
        }
        preview.update(over)
        return preview

    def test_it_draws_the_curve_its_background_and_the_peaks(self, canvas):
        canvas.showSpectrum(self._preview())
        ax = canvas.figure.axes[0]
        labels = [line.get_label() for line in ax.lines]

        assert "Raw" in labels and "Background" in labels and "Corrected" in labels
        assert any("peak(s)" in str(label) for label in labels)

    def test_the_branch_boundaries_are_drawn_where_they_fall(self, canvas):
        """A split at 0 V tears a charged well's ladder in half; seeing the
        line is how a user notices before the search reports nonsense."""
        canvas.showSpectrum(self._preview())
        verticals = [line.get_xdata()[0] for line in canvas.figure.axes[0].lines
                     if len(set(line.get_xdata())) == 1]

        assert 0.2 in verticals and -0.3 in verticals

    def test_a_missing_boundary_draws_no_line(self, canvas):
        canvas.showSpectrum(self._preview(split_e=None, split_h=None))
        verticals = [line for line in canvas.figure.axes[0].lines
                     if len(set(line.get_xdata())) == 1]

        assert verticals == []

    def test_the_title_names_the_spectrum(self, canvas):
        canvas.showSpectrum(self._preview(column='P7'))

        assert canvas.figure.axes[0].get_title() == 'P7'

    def test_an_empty_preview_shows_its_error(self, canvas):
        canvas.showSpectrum({'x': [], 'error': 'Dataset not found'})

        assert canvas.figure.axes[0].texts[0].get_text() == 'Dataset not found'

    def test_a_preview_without_a_background_still_draws(self, canvas):
        canvas.showSpectrum(self._preview(baseline=[], corrected=[]))
        labels = [line.get_label() for line in canvas.figure.axes[0].lines]

        assert "Raw" in labels and "Background" not in labels


class TestPaletteAndMessages:
    def test_the_foreground_reaches_the_axes(self, canvas):
        from matplotlib.colors import to_rgba

        canvas.foregroundColor = "#ff0000"
        canvas.showCandidate(_candidate())
        ax = canvas.figure.axes[0]

        assert ax.xaxis.label.get_color() == "#ff0000"
        assert to_rgba(ax.title.get_color()) == to_rgba("#ff0000")

    def test_the_background_reaches_the_axes_too(self, canvas):
        from matplotlib.colors import to_rgba

        canvas.backgroundColor = "#101010"
        canvas.showCandidate(_candidate())

        assert canvas.figure.axes[0].get_facecolor() == to_rgba("#101010")

    def test_a_message_replaces_whatever_was_drawn(self, canvas):
        canvas.showCandidate(_candidate())
        canvas.showMessage("Searching…")

        assert len(canvas.figure.axes) == 1
        assert canvas.figure.axes[0].texts[0].get_text() == "Searching…"

    def test_a_message_renders(self, canvas):
        canvas.showMessage("Nothing yet")
        canvas._render()

        assert canvas._cached_image is not None


class TestTheLineStrip:
    """Position across, colour by size, grey where there is nothing."""

    def _run(self, **over):
        points = [
            {'point_index': 0, 'position_nm': 0.0, 'size_nm': float('nan'),
             'group': -1, 'converged': False, 'reason': 'no_peaks'},
            {'point_index': 1, 'position_nm': 5.0, 'size_nm': 8.0,
             'group': 0, 'converged': True, 'reason': ''},
            {'point_index': 2, 'position_nm': 10.0, 'size_nm': 8.05,
             'group': 0, 'converged': True, 'reason': ''},
            {'point_index': 3, 'position_nm': 15.0, 'size_nm': float('nan'),
             'group': -1, 'converged': False, 'reason': 'too_few_peaks'},
        ]
        run = {'points': points,
               'groups': [{'index': 0, 'size_nm': 8.025, 'count': 2,
                           'points': [1, 2]}],
               'segments': [{'group': -1, 'start': 0.0, 'end': 0.0, 'count': 1},
                            {'group': 0, 'start': 5.0, 'end': 10.0, 'count': 2},
                            {'group': -1, 'start': 15.0, 'end': 15.0, 'count': 1}],
               'position_label': 'Position (nm)'}
        run.update(over)
        return run

    def test_it_draws_the_strip_over_the_profile(self, canvas):
        canvas.showLineScan(self._run())

        # The strip, the profile, and the colourbar's own axes.
        assert len(canvas.figure.axes) == 3

    def test_a_position_with_no_confinement_is_masked_not_coloured(self, canvas):
        """Absence is a result; giving it a colour from the scale would be
        inventing a size for it."""
        canvas.showLineScan(self._run())
        mesh = canvas.figure.axes[0].collections[0]

        assert np.ma.is_masked(mesh.get_array())
        assert mesh.get_array().mask.sum() == 2

    def test_the_masked_cells_show_the_axes_grey(self, canvas):
        canvas.showLineScan(self._run())

        assert canvas.figure.axes[0].get_facecolor()[:3] == pytest.approx(
            (0.82, 0.82, 0.82), abs=1e-2)

    def test_each_cell_is_one_position_wide(self, canvas):
        """pcolormesh and not imshow: with one row of cells imshow resamples
        and blurs the boundary between one domain and its neighbour."""
        canvas.showLineScan(self._run())
        mesh = canvas.figure.axes[0].collections[0]

        assert mesh.get_array().shape == (1, 4)

    def test_the_profile_marks_each_group_separately(self, canvas):
        canvas.showLineScan(self._run())
        profile = canvas.figure.axes[1]

        assert len(profile.lines) == 1                 # one group
        assert profile.lines[0].get_xdata().tolist() == [5.0, 10.0]

    def test_the_empty_stretches_are_shaded(self, canvas):
        canvas.showLineScan(self._run())
        spans = [p for p in canvas.figure.axes[1].patches]

        assert len(spans) == 2                         # the two bare ends

    def test_the_axis_is_labelled_with_the_position_unit(self, canvas):
        canvas.showLineScan(self._run(position_label="Point"))

        assert canvas.figure.axes[1].get_xlabel() == "Point"

    def test_a_line_with_nothing_on_it_still_draws(self, canvas):
        """A scan where nothing converged is an answer, not an error."""
        run = self._run()
        for point in run['points']:
            point['converged'] = False
            point['size_nm'] = float('nan')
        run['groups'] = []
        canvas.showLineScan(run)

        assert canvas.figure.axes[0].collections[0].get_array().mask.all()

    def test_no_run_at_all_says_so(self, canvas):
        canvas.showLineScan({'points': []})

        assert canvas.figure.axes[0].texts[0].get_text() == "No line scan yet"

    def test_a_single_position_does_not_divide_by_zero(self, canvas):
        canvas.showLineScan({'points': [
            {'point_index': 0, 'position_nm': 0.0, 'size_nm': 8.0,
             'group': 0, 'converged': True, 'reason': ''}]})

        assert canvas.figure.axes[0].collections[0].get_array().shape == (1, 1)
