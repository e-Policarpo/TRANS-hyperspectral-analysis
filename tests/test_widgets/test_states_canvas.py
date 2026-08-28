"""
Tests for the 2x2 state view and the tunnelling view behind it.

This is the picture the Qt port had lost: a 3-D state is a volume, and the
only way to see one is three orthogonal cuts through it plus a cloud of where
it actually is. Two things have to hold. Each cut has to say where it was
taken — two cuts of the same state at different z are different pictures and
otherwise indistinguishable — and nothing here may raise, because it is
reached from a property write and from a slot, and a half-built figure is
then painted on every frame.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
import numpy as np
from PySide6.QtGui import QGuiApplication

from src.physics import feature_specs as specs
from src.widgets.qml_states_canvas import StatesCanvas


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def canvas(app):
    item = StatesCanvas()
    item.setWidth(600)
    item.setHeight(600)
    yield item
    item.cleanup()


def _plots(ix=6, iy=5, iz=4):
    """A `statePlots()` answer, built by hand rather than solved for.

    The backend's contract is what this view is written against, so the
    fixture is that contract — a solve would drag a minute of eigensolving
    into a drawing test and still only produce one shape of dict.
    """
    x = np.linspace(0.0, 22.0, 12)
    y = np.linspace(0.0, 18.0, 10)
    z = np.linspace(0.0, 14.0, 8)
    gx, gy, gz = np.meshgrid(x, y, z, indexing='ij')
    prob = np.exp(-(((gx - 11) / 4) ** 2 + ((gy - 9) / 4) ** 2
                    + ((gz - 7) / 3) ** 2))
    prob /= prob.max()

    over = prob > 0.05
    px, py, pz = np.nonzero(over)
    return {
        'ok': True, 'error': "",
        'state': 2, 'E_eV': 0.12345,
        'x_nm': x.tolist(), 'y_nm': y.tolist(), 'z_nm': z.tolist(),
        'xy': {'values': prob[:, :, iz].tolist(), 'slice_at': float(z[iz])},
        'xz': {'values': prob[:, iy, :].tolist(), 'slice_at': float(y[iy])},
        'yz': {'values': prob[ix, :, :].tolist(), 'slice_at': float(x[ix])},
        'scatter': {'x': x[px].tolist(), 'y': y[py].tolist(),
                    'z': z[pz].tolist(), 'c': prob[over].tolist()},
        'features': [dict(specs.default_spec('sphere', (11.0, 9.0)), cz=7.0)],
    }


def _titles(canvas):
    return [ax.get_title() for ax in canvas.figure.axes if ax.get_title()]


def _messages(canvas):
    return [text.get_text() for ax in canvas.figure.axes
            for text in ax.texts]


class TestTheStateView:
    def test_a_state_is_four_pictures_of_itself(self, canvas):
        """The cloud and three cuts. Colorbars carry their own axes, so the
        count is taken from the ones that were given a title."""
        canvas.setPlots(_plots())

        assert len(_titles(canvas)) == 4

    def test_every_cut_says_where_it_was_taken(self, canvas):
        """Without the number there is no telling one cut of a state from
        another, and the whole point of steering them is gone."""
        canvas.setPlots(_plots())
        titles = _titles(canvas)

        assert "XY cut  z = 8.0 nm" in titles
        assert "XZ cut  y = 10.0 nm" in titles
        assert "YZ cut  x = 12.0 nm" in titles

    def test_the_cloud_is_labelled_with_the_state_it_is(self, canvas):
        canvas.setPlots(_plots())

        assert "|ψ|²  state 2  E=0.1235 eV" in _titles(canvas)

    def test_moving_a_cut_moves_what_the_title_says(self, canvas):
        canvas.setPlots(_plots(iz=1))

        assert "XY cut  z = 2.0 nm" in _titles(canvas)

    def test_the_colorbars_do_not_pile_up(self, canvas):
        """The Tk app grew a strip of them down the side: clearing the figure
        drops the axes but a colorbar keeps its own, so redrawing without
        removing them adds one per redraw."""
        for _ in range(4):
            canvas.setPlots(_plots())

        assert len(canvas._colorbars) == 3

    def test_it_draws_a_wireframe_for_each_feature(self, canvas):
        plots = _plots()
        plots['features'].append(
            dict(specs.default_spec('box', (4.0, 4.0)), cz=4.0))
        canvas.setPlots(plots)
        cloud = canvas.figure.axes[0]

        assert len(cloud.collections) >= 3      # the points plus two shapes

    def test_a_kind_it_has_no_wireframe_for_is_skipped_quietly(self, canvas):
        plots = _plots()
        plots['features'].append({'kind': 'trapezoid', 'cx': 5.0, 'cy': 5.0})
        canvas.setPlots(plots)

        assert len(_titles(canvas)) == 4


class TestNothingToDraw:
    def test_an_empty_answer_does_not_raise(self, canvas):
        """The view is mounted before anything is solved, so this is the
        state it spends most of its life in."""
        canvas.setPlots({})

        assert _titles(canvas) == []
        assert "Solve the model" in " ".join(_messages(canvas))

    def test_a_refusal_is_shown_as_the_reason_it_gave(self, canvas):
        canvas.setPlots({'ok': False,
                         'error': "The state view draws a volume — "
                                  "this model is 2-D."})

        assert "2-D" in " ".join(_messages(canvas))

    def test_a_cut_with_no_values_still_gets_its_panel(self, canvas):
        plots = _plots()
        plots['xz'] = {}
        canvas.setPlots(plots)

        assert len(_titles(canvas)) == 4

    def test_junk_where_a_grid_should_be_leaves_the_view_usable(self, canvas):
        """Whatever QML put in the map is what arrives. A bad one has to
        land as a drawn figure and has to be recoverable — a canvas that
        stays broken after one malformed answer is worse than a blank one."""
        plots = _plots()
        plots['x_nm'] = "not an axis"
        canvas.setPlots(plots)

        assert canvas.figure.axes                # something was drawn
        canvas.setPlots(_plots())
        assert len(_titles(canvas)) == 4         # and the next one is fine

    def test_clearing_it_drops_what_it_was_holding(self, canvas):
        canvas.setPlots(_plots())
        canvas.cleanup()

        assert canvas._plots == {}
        assert canvas._colorbars == []


class TestTheTunnellingView:
    def test_switching_view_does_not_go_back_to_the_backend(self, canvas):
        """Both sets of data are kept, so a switch is a redraw. A round trip
        would re-solve on every toggle."""
        canvas.setPlots(_plots())
        canvas.setTunneling({'ok': True, 'rates': [
            {'from_state': 0, 'to_state': 1, 'rate_Hz': 1e12},
            {'from_state': 1, 'to_state': 0, 'rate_Hz': 1e9}]})
        canvas.mode = "tunneling"

        assert "Tunnelling rates" in _titles(canvas)

        canvas.mode = "states"
        assert "|ψ|²  state 2  E=0.1235 eV" in _titles(canvas)

    def test_it_draws_the_panels_the_backend_actually_sent(self, canvas):
        """`tunneling()` publishes rates and nothing else today, so the
        ladder and the overlap matrix are drawn only when they arrive rather
        than the view refusing to draw the rates it does have."""
        canvas.mode = "tunneling"
        canvas.setTunneling({'ok': True, 'rates': [
            {'from_state': 0, 'to_state': 1, 'rate_Hz': 1e12}]})

        assert _titles(canvas) == ["Tunnelling rates"]

        canvas.setTunneling({'ok': True, 'E_eV': [-0.3, -0.1, 0.05],
                             'overlap': [[1.0, 0.2, 0.0], [0.2, 1.0, 0.1],
                                         [0.0, 0.1, 1.0]],
                             'rates': [{'from_state': 0, 'to_state': 1,
                                        'rate_Hz': 1e12}]})

        assert _titles(canvas) == ["Energy levels", "Overlap |⟨ψᵢ|ψⱼ⟩|",
                                   "Tunnelling rates"]

    def test_nothing_to_tunnel_between_is_a_message(self, canvas):
        canvas.mode = "tunneling"
        canvas.setTunneling({})

        assert _messages(canvas)

    def test_an_unknown_mode_is_ignored_rather_than_blanking_the_view(
            self, canvas):
        canvas.setPlots(_plots())
        canvas.mode = "sideways"

        assert canvas.mode == "states"
        assert len(_titles(canvas)) == 4


class TestItIsReadableOnThisPalette:
    def test_the_titles_are_not_left_matplotlib_black(self, canvas):
        """Unstyled, they are near-black on a near-black panel — which is why
        every colour in this view is set by hand."""
        canvas.setPlots(_plots())

        for ax in canvas.figure.axes:
            if ax.get_title():
                assert ax.title.get_color() == canvas._foreground

    def test_a_new_foreground_is_picked_up_without_new_data(self, canvas):
        canvas.setPlots(_plots())
        canvas.foregroundColor = "#ff00ff"

        assert len(_titles(canvas)) == 4
        titled = [ax for ax in canvas.figure.axes if ax.get_title()]
        assert all(ax.title.get_color() == "#ff00ff" for ax in titled)
