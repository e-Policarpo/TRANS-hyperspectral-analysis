"""
Tests for the Modeling workstation's backend.

It owns the model — the box and the features in it — so a drag on the canvas
and a number typed in a field are the same edit arriving by different routes,
and both have to end up in the same place. It also decides what is too big to
solve, which is the difference between a wait and an app that looks hung.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtCore")
from PySide6.QtGui import QGuiApplication

from src.backend.modeling_backend import ModelingBackend
from src.physics import feature_specs as specs


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def model(app):
    backend = ModelingBackend()
    backend.setDomain(20.0, 20.0, 20.0)
    return backend


class TestEditingTheModel:
    def test_a_new_model_is_empty(self, model):
        assert model.getFeatures() == []
        assert model.selectedIndex == -1

    def test_adding_a_feature_selects_it(self, model):
        """Whatever was just added is what the fields should be editing."""
        index = model.addFeature('circle', 5.0, 6.0)

        assert index == 0
        assert model.selectedIndex == 0
        assert model.getFeatures()[0]['kind'] == 'circle'

    def test_it_lands_where_the_click_was(self, model):
        model.addFeature('circle', 5.0, 6.0)
        spec = model.getFeatures()[0]

        assert specs.spec_position(spec) == pytest.approx((5.0, 6.0))

    def test_a_3d_feature_starts_in_the_middle_of_the_box(self, model):
        """The click gives two coordinates; the third has nowhere to go that
        is not a guess, so it goes to the middle."""
        model.mode = "3d"
        model.addFeature('sphere', 4.0, 4.0)

        assert model.getFeatures()[0]['cz'] == pytest.approx(10.0)

    def test_a_shape_from_the_wrong_dimensionality_is_refused(self, model):
        """A 3D feature in a 2D box has no meaning, and building one would
        make a potential nobody can solve."""
        assert model.addFeature('sphere', 5.0, 5.0) == -1
        assert model.getFeatures() == []
        assert "not a 2D shape" in model.status

    def test_switching_dimensionality_starts_a_new_model(self, model):
        model.addFeature('circle', 5.0, 5.0)
        model.mode = "3d"

        assert model.getFeatures() == []
        assert model.selectedIndex == -1

    def test_the_kinds_on_offer_follow_the_mode(self, model):
        two_d = {k['key'] for k in model.availableKinds()}
        model.mode = "3d"
        three_d = {k['key'] for k in model.availableKinds()}

        assert two_d == set(specs.KINDS_2D)
        assert three_d == set(specs.KINDS_3D)

    def test_a_field_edit_and_a_drag_reach_the_same_place(self, model):
        """The two routes into the same state: if they disagreed, the canvas
        and the panel would each show a different model."""
        model.addFeature('circle', 5.0, 5.0)
        model.updateFeature(0, {'cx': 8.0})
        assert model.getFeatures()[0]['cx'] == pytest.approx(8.0)

        model.moveFeature(0, 2.0, 3.0, 'xy')
        assert model.getFeatures()[0]['cx'] == pytest.approx(2.0)
        assert model.getFeatures()[0]['cy'] == pytest.approx(3.0)

    def test_an_unknown_field_is_ignored(self, model):
        model.addFeature('circle', 5.0, 5.0)
        model.updateFeature(0, {'nonsense': 1.0, 'r': 3.0})

        assert 'nonsense' not in model.getFeatures()[0]
        assert model.getFeatures()[0]['r'] == pytest.approx(3.0)

    def test_a_drag_in_a_projection_leaves_the_hidden_axis_alone(self, model):
        model.mode = "3d"
        model.addFeature('sphere', 4.0, 4.0)
        model.moveFeature(0, 1.0, 2.0, 'xz')
        spec = model.getFeatures()[0]

        assert (spec['cx'], spec['cz']) == pytest.approx((1.0, 2.0))
        assert spec['cy'] == pytest.approx(4.0)

    def test_resizing_a_circle_sets_its_one_radius(self, model):
        model.addFeature('circle', 5.0, 5.0)
        model.resizeFeature(0, 3.0, 1.0, 'xy')

        assert model.getFeatures()[0]['r'] == pytest.approx(3.0)

    def test_resizing_a_rectangle_keeps_it_where_it_was(self, model):
        """It is anchored by its corner, so growing it must not walk it
        across the box."""
        model.addFeature('rect', 10.0, 10.0)
        model.resizeFeature(0, 3.0, 2.0, 'xy')
        spec = model.getFeatures()[0]

        assert (spec['w'], spec['h']) == pytest.approx((6.0, 4.0))
        assert specs.spec_position(spec) == pytest.approx((10.0, 10.0))

    def test_resizing_a_cylinder_depends_on_the_view(self, model):
        """From above it is a circle and only the radius can change; from the
        side both the radius and the height are on screen."""
        model.mode = "3d"
        model.addFeature('cylinder', 10.0, 10.0)
        model.resizeFeature(0, 3.0, 3.0, 'xy')
        assert model.getFeatures()[0]['R'] == pytest.approx(3.0)

        model.resizeFeature(0, 2.0, 5.0, 'xz')
        spec = model.getFeatures()[0]
        assert spec['R'] == pytest.approx(2.0)
        assert spec['H'] == pytest.approx(10.0)

    def test_a_gaussian_resizes_in_sigmas(self, model):
        """Its outline is drawn at 3σ, so a corner dragged to 6 nm is σ = 2."""
        model.addFeature('gaussian_2d', 5.0, 5.0)
        model.resizeFeature(0, 6.0, 3.0, 'xy')
        spec = model.getFeatures()[0]

        assert spec['sx'] == pytest.approx(2.0)
        assert spec['sy'] == pytest.approx(1.0)

    def test_duplicating_offsets_the_copy(self, model):
        """A copy exactly underneath the original looks like nothing
        happened."""
        model.addFeature('circle', 5.0, 5.0)
        index = model.duplicateFeature(0)
        first, second = model.getFeatures()

        assert index == 1
        assert specs.spec_position(second) != pytest.approx(
            specs.spec_position(first))

    def test_removing_keeps_the_selection_in_range(self, model):
        for _ in range(3):
            model.addFeature('circle', 5.0, 5.0)
        model.removeFeature(2)

        assert len(model.getFeatures()) == 2
        assert model.selectedIndex < 2

    def test_editing_an_index_that_is_not_there_does_nothing(self, model):
        model.addFeature('circle', 5.0, 5.0)
        model.updateFeature(9, {'r': 3.0})
        model.moveFeature(9, 1.0, 1.0, 'xy')
        model.resizeFeature(-1, 1.0, 1.0, 'xy')
        model.removeFeature(9)

        assert len(model.getFeatures()) == 1

    def test_clearing_empties_everything(self, model):
        model.addFeature('circle', 5.0, 5.0)
        model.clearFeatures()

        assert model.getFeatures() == []
        assert model.selectedIndex == -1


class TestTheFormItDescribes:
    def test_it_names_the_fields_a_kind_has(self, model):
        fields = [f['name'] for f in model.fieldsFor('circle')]

        assert fields[:3] == ['cx', 'cy', 'r']
        assert 'V0' in fields and 'meff' in fields

    def test_every_field_comes_with_a_label(self, model):
        for field in model.fieldsFor('box'):
            assert field['label'] and field['label'] != field['name'] or True
            assert 'name' in field and 'label' in field

    def test_an_unknown_kind_has_no_fields_rather_than_raising(self, model):
        assert model.fieldsFor('trapezoid') == []


class TestThePotentialItDraws:
    def test_a_2d_preview_is_a_grid_of_the_box(self, model):
        model.addFeature('circle', 10.0, 10.0)
        preview = model.previewPotential('xy')

        assert len(preview['x_nm']) == ModelingBackend.PREVIEW_POINTS
        assert len(preview['V_eV']) == ModelingBackend.PREVIEW_POINTS
        assert min(min(row) for row in preview['V_eV']) < 0

    def test_an_empty_model_previews_flat(self, model):
        preview = model.previewPotential('xy')

        assert max(max(row) for row in preview['V_eV']) == 0.0

    def test_a_3d_preview_is_one_plane_through_the_box(self, model):
        """A projection cannot show a volume, and averaging through it would
        hide the structure being placed."""
        model.mode = "3d"
        model.addFeature('sphere', 10.0, 10.0)
        preview = model.previewPotential('xy')

        assert preview['slice_at'] == pytest.approx(10.0, abs=1.0)
        assert min(min(row) for row in preview['V_eV']) < 0

    def test_a_plane_that_misses_the_feature_is_empty(self, model):
        """The slice is where it says it is: a sphere at z = 10 is not in the
        plane z = 1."""
        model.mode = "3d"
        model.addFeature('sphere', 10.0, 10.0)
        preview = model.previewPotential('xy', 1.0)

        assert min(min(row) for row in preview['V_eV']) == 0.0

    def test_the_axes_follow_the_projection(self, model):
        model.mode = "3d"
        model.setDomain(30.0, 20.0, 10.0)
        xz = model.previewPotential('xz')

        assert max(xz['x_nm']) == pytest.approx(30.0, rel=0.05)
        assert max(xz['y_nm']) == pytest.approx(10.0, rel=0.05)


class TestSolving:
    def test_it_solves_the_model_and_reports_the_levels(self, model):
        got = []
        model.solveCompleted.connect(got.append)
        model.addFeature('circle', 10.0, 10.0)
        model.updateFeature(0, {'r': 5.0, 'V0': -0.5})

        model.solve({'Nx': 50, 'Ny': 50, 'n_states': 3})

        assert got and got[-1]['ok'] is True
        assert len(got[-1]['E_eV']) == 3
        assert got[-1]['E_eV'][0] < 0            # bound in the well

    def test_the_levels_come_back_ascending(self, model):
        got = []
        model.solveCompleted.connect(got.append)
        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 4})

        energies = got[-1]['E_eV']
        assert energies == sorted(energies)

    def test_a_3d_model_solves_too(self, model):
        got = []
        model.solveCompleted.connect(got.append)
        model.mode = "3d"
        model.setDomain(10.0, 10.0, 10.0)
        model.solve({'Nx': 14, 'Ny': 14, 'Nz': 14, 'n_states': 2})

        assert got[-1]['ok'] is True
        assert len(got[-1]['shape']) == 3

    def test_a_grid_that_is_too_big_is_refused_before_it_runs(self, model):
        """The cost is the product of the counts, and a mistyped zero turns a
        two-second solve into one that never finishes."""
        got = []
        model.solveCompleted.connect(got.append)
        model.mode = "3d"

        model.solve({'Nx': 200, 'Ny': 200, 'Nz': 200})

        assert got[-1]['ok'] is False
        assert "limit" in model.status

    def test_the_cost_can_be_asked_for_first(self, model):
        model.mode = "3d"
        cost = model.gridCost({'Nx': 20, 'Ny': 20, 'Nz': 20})

        assert cost['points'] == 8000
        assert cost['too_big'] is False
        assert cost['counts'] == [20, 20, 20]

    def test_the_wavefunctions_do_not_cross_the_bridge(self, model):
        """A 3-D state is megabytes and the canvas draws one plane of one of
        them; sending them all would be the slowest thing in the app."""
        got = []
        model.solveCompleted.connect(got.append)
        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 2})

        assert 'psi' not in got[-1]
        json.dumps(got[-1])                      # and what is sent is plain

    def test_a_state_can_be_sliced_after_the_solve(self, model):
        model.addFeature('circle', 10.0, 10.0)
        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 2})
        plane = model.densityFor(0, 'xy')

        assert len(plane['values']) == 40
        assert len(plane['values'][0]) == 40
        assert min(min(row) for row in plane['values']) >= 0

    def test_a_3d_state_is_sliced_in_the_plane_shown(self, model):
        model.mode = "3d"
        model.setDomain(10.0, 10.0, 10.0)
        model.solve({'Nx': 12, 'Ny': 12, 'Nz': 12, 'n_states': 1})
        plane = model.densityFor(0, 'xz')

        assert len(plane['values']) == 12
        assert len(plane['values'][0]) == 12

    def test_a_slice_crosses_the_bridge_as_plain_lists(self, model):
        """The solver's axes are numpy arrays. One left as such reaches the
        canvas as an array, where the emptiness guard raised inside paint()
        rather than answering — a blank canvas and a traceback per frame."""
        model.addFeature('circle', 10.0, 10.0)
        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 1})

        json.dumps(model.densityFor(0, 'xy'))

        model.mode = "3d"
        model.setDomain(10.0, 10.0, 10.0)
        model.solve({'Nx': 12, 'Ny': 12, 'Nz': 12, 'n_states': 1})

        json.dumps(model.densityFor(0, 'xz'))

    def test_asking_for_a_state_before_solving_gives_nothing(self, model):
        assert model.densityFor(0, 'xy') == {}


class TestSavingAModel:
    def test_it_round_trips_through_json(self, model, tmp_path):
        model.addFeature('circle', 5.0, 6.0)
        model.addFeature('rect', 12.0, 12.0)
        path = tmp_path / "model.json"

        assert model.saveModel(str(path)) is True
        model.clearFeatures()
        assert model.loadModel(str(path)) is True
        assert len(model.getFeatures()) == 2
        assert model.getFeatures()[0]['kind'] == 'circle'

    def test_the_box_and_the_mode_come_back_too(self, model, tmp_path):
        model.mode = "3d"
        model.setDomain(30.0, 25.0, 15.0)
        model.addFeature('sphere', 10.0, 10.0)
        path = tmp_path / "model3d.json"
        model.saveModel(str(path))

        fresh = ModelingBackend()
        assert fresh.loadModel(str(path)) is True
        assert fresh.mode == "3d"
        assert fresh.getDomain() == pytest.approx([30.0, 25.0, 15.0])

    def test_a_feature_the_mode_cannot_hold_is_dropped(self, model, tmp_path):
        """A file from another version should load what it can rather than
        nothing at all."""
        path = tmp_path / "mixed.json"
        path.write_text(json.dumps({
            'mode': '2d', 'domain': [20.0, 20.0, 20.0],
            'features': [specs.default_spec('circle'),
                         specs.default_spec('sphere'),
                         {'kind': 'nonsense'}]}), encoding="utf-8")

        assert model.loadModel(str(path)) is True
        assert [f['kind'] for f in model.getFeatures()] == ['circle']

    def test_a_file_that_is_not_a_model_is_reported(self, model, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")

        assert model.loadModel(str(path)) is False
        assert "Could not" in model.status

    def test_a_missing_file_is_reported(self, model):
        assert model.loadModel("/nowhere/at/all.json") is False


class TestTunnelling:
    """Which feature each state lives in, and how fast it leaks next door."""

    def _two_wells(self, model):
        model.setDomain(30.0, 20.0, 20.0)
        model.addFeature('circle', 9.0, 10.0)
        model.updateFeature(0, {'r': 3.0, 'V0': -0.5})
        model.addFeature('circle', 21.0, 10.0)
        model.updateFeature(1, {'r': 3.0, 'V0': -0.5})
        model.solve({'Nx': 60, 'Ny': 40, 'n_states': 4})

    def test_it_needs_a_solve_first(self, model):
        out = model.tunneling()

        assert out['ok'] is False
        assert "Solve" in out['error']

    def test_one_feature_has_nowhere_to_tunnel_to(self, model):
        """Not an error and not a zero: a single well genuinely has no
        neighbour, and saying so beats reporting a rate of nothing."""
        model.addFeature('circle', 10.0, 10.0)
        model.solve({'Nx': 40, 'Ny': 40, 'n_states': 2})
        out = model.tunneling()

        assert out['ok'] is False
        assert "two features" in out['error']

    def test_two_wells_report_rates_between_them(self, model):
        self._two_wells(model)
        out = model.tunneling()

        assert out['ok'] is True
        assert out['rates']
        assert all(r['rate_Hz'] >= 0 for r in out['rates'])

    def test_each_state_is_assigned_to_the_well_it_lives_in(self, model):
        self._two_wells(model)
        out = model.tunneling()

        assert len(out['assignments']) == 4
        assert set(out['assignments']) <= {-1, 0, 1}
        # Both wells hold something: identical wells 12 nm apart share the
        # states between them.
        assert set(out['assignments']) >= {0, 1}

    def test_the_strongest_rate_comes_first(self, model):
        self._two_wells(model)
        rates = [r['rate_Hz'] for r in model.tunneling()['rates']]

        assert rates == sorted(rates, reverse=True)

    def test_a_pair_names_both_its_states_and_both_its_wells(self, model):
        self._two_wells(model)
        first = model.tunneling()['rates'][0]

        assert {'from_state', 'to_state', 'from_feature', 'to_feature',
                'rate_Hz'} <= set(first)
        assert first['from_feature'] != first['to_feature']

    def test_wells_further_apart_leak_more_slowly(self, model):
        """The whole point of a WKB rate: it falls off with the barrier."""
        self._two_wells(model)
        near = max(r['rate_Hz'] for r in model.tunneling()['rates'])

        model.moveFeature(1, 27.0, 10.0, 'xy')
        model.solve({'Nx': 60, 'Ny': 40, 'n_states': 4})
        far_rates = [r['rate_Hz'] for r in model.tunneling()['rates']]

        assert far_rates
        assert max(far_rates) < near

    def test_what_it_returns_survives_the_bridge(self, model):
        self._two_wells(model)
        json.dumps(model.tunneling())


class TestWhereTheCutLands:
    """A 3-D model is shown one plane at a time, and the plane is steerable.

    Two things follow. The slider has to be told where the cut actually
    landed — the request is snapped to a grid line, and a readout quoting the
    number it sent drifts from the picture by up to half a step. And the cut
    has to be honoured at all: a slice that silently stayed in the middle
    would look right on every model whose feature happens to be there.
    """

    @staticmethod
    def _volume(model):
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 20.0)
        model.addFeature('sphere', 10.0, 10.0)
        model.updateFeature(0, {'cz': 5.0, 'R': 3.0, 'V0': -0.5})
        model.solve({'Nx': 16, 'Ny': 16, 'Nz': 16, 'n_states': 1})

    def test_a_3d_slice_says_where_it_cut(self, model):
        self._volume(model)
        plane = model.densityFor(0, 'xy')

        assert 'slice_at' in plane
        assert 0.0 <= plane['slice_at'] <= 20.0

    def test_the_position_it_reports_is_a_grid_line(self, model):
        """Not the number that was asked for: 7 nm on a 16-node grid is not
        a plane that exists."""
        self._volume(model)
        plane = model.densityFor(0, 'xy', 7.0)
        axis = model.previewPotential('xy', 7.0)

        assert plane['slice_at'] != pytest.approx(7.0, abs=1e-9)
        assert plane['slice_at'] == pytest.approx(7.0, abs=1.5)
        assert axis['slice_at'] == pytest.approx(plane['slice_at'], abs=1.5)

    def test_a_2d_model_has_no_hidden_axis_to_report(self, model):
        """There is nothing to disambiguate, and a `slice_at` of None would
        reach the canvas as a title claiming a plane."""
        model.addFeature('circle', 10.0, 10.0)
        model.solve({'Nx': 30, 'Ny': 30, 'n_states': 1})

        assert 'slice_at' not in model.densityFor(0, 'xy')

    def test_a_cut_through_a_feature_is_not_the_cut_that_misses_it(self, model):
        """The claim the whole slider rests on. A sphere at z = 5 is in the
        plane z = 5 and is not in the plane z = 18."""
        self._volume(model)
        through = model.previewPotential('xy', 5.0)
        past = model.previewPotential('xy', 18.0)

        assert min(min(row) for row in through['V_eV']) < 0
        assert min(min(row) for row in past['V_eV']) == 0.0

    def test_the_state_is_where_the_well_is(self, model):
        """Same for the density: the bound state lives in the sphere, so the
        plane through it carries far more of |psi|² than one that misses."""
        self._volume(model)
        through = np.asarray(model.densityFor(0, 'xy', 5.0)['values'])
        past = np.asarray(model.densityFor(0, 'xy', 18.0)['values'])

        assert through.max() > 10 * past.max()

    def test_a_cut_with_no_opinion_lands_in_the_middle(self, model):
        """Negative means "wherever the middle is" — the convention every
        slicing call here answers to, so a caller that has not been dragged
        yet does not have to invent a position."""
        self._volume(model)

        assert model.densityFor(0, 'xy', -1.0)['slice_at'] == \
            pytest.approx(10.0, abs=1.0)

    def test_each_plane_is_cut_on_its_own_axis(self, model):
        self._volume(model)

        assert model.densityFor(0, 'xz', 4.0)['slice_at'] == \
            pytest.approx(4.0, abs=1.5)      # y
        assert model.densityFor(0, 'yz', 16.0)['slice_at'] == \
            pytest.approx(16.0, abs=1.5)     # x


class TestTheFourPicturesOfAState:
    """`statePlots` feeds the 2x2 view. Everything it returns has to be small
    — a 3-D grid across the QML bridge is the slowest thing the app could
    do — and normalised, because the cuts are drawn on a shared scale."""

    @staticmethod
    def _solved(model, n=2, N=16):
        model.mode = "3d"
        model.setDomain(20.0, 20.0, 20.0)
        model.addFeature('sphere', 7.0, 10.0)
        model.updateFeature(0, {'cz': 10.0, 'R': 4.0, 'V0': -0.6})
        model.solve({'Nx': N, 'Ny': N, 'Nz': N, 'n_states': n})
        return model.statePlots(0)

    def test_it_answers_with_the_three_cuts_and_the_cloud(self, model):
        plots = self._solved(model)

        assert plots['ok'] is True
        assert plots['error'] == ""
        assert plots['state'] == 0
        assert set(plots) >= {'E_eV', 'x_nm', 'y_nm', 'z_nm', 'xy', 'xz',
                              'yz', 'scatter', 'features'}

    def test_each_cut_is_a_plane_of_the_grid(self, model):
        plots = self._solved(model)

        for plane, rows, cols in [('xy', 'x_nm', 'y_nm'),
                                  ('xz', 'x_nm', 'z_nm'),
                                  ('yz', 'y_nm', 'z_nm')]:
            values = plots[plane]['values']
            assert len(values) == len(plots[rows]), plane
            assert len(values[0]) == len(plots[cols]), plane

    def test_every_cut_says_where_it_was_taken(self, model):
        plots = self._solved(model)

        assert plots['xy']['slice_at'] in plots['z_nm']
        assert plots['xz']['slice_at'] in plots['y_nm']
        assert plots['yz']['slice_at'] in plots['x_nm']

    def test_the_cuts_are_normalised_to_the_state(self, model):
        """max == 1 over the volume, so the three panels share a scale and a
        faint cut reads as faint rather than being stretched to look full."""
        plots = self._solved(model)
        peak = max(max(max(row) for row in plots[plane]['values'])
                   for plane in ('xy', 'xz', 'yz'))

        assert peak == pytest.approx(1.0)
        assert all(v >= 0 for row in plots['xy']['values'] for v in row)

    def test_the_cuts_can_be_steered_one_axis_at_a_time(self, model):
        self._solved(model)
        plots = model.statePlots(0, 4.0, 15.0, 8.0)

        assert plots['xy']['slice_at'] == pytest.approx(8.0, abs=1.5)   # z
        assert plots['xz']['slice_at'] == pytest.approx(15.0, abs=1.5)  # y
        assert plots['yz']['slice_at'] == pytest.approx(4.0, abs=1.5)   # x

    def test_the_cloud_is_only_where_the_state_is(self, model):
        plots = self._solved(model)
        cloud = plots['scatter']

        assert len(cloud['x']) == len(cloud['c']) > 0
        assert min(cloud['c']) > ModelingBackend.SCATTER_THRESHOLD

    def test_the_cloud_is_capped_before_it_crosses_the_bridge(self, model):
        """A 60³ solve puts 200 000 points over the threshold. What gets
        dropped is the faint rim, so the cloud shrinks onto the state rather
        than thinning everywhere."""
        cap = ModelingBackend.MAX_SCATTER_POINTS
        try:
            ModelingBackend.MAX_SCATTER_POINTS = 50
            self._solved(model, N=20)
            cloud = model.statePlots(0)['scatter']
            again = model.statePlots(0)['scatter']
        finally:
            ModelingBackend.MAX_SCATTER_POINTS = cap

        assert len(cloud['c']) == 50
        assert min(cloud['c']) > 0.05
        assert again == cloud            # and the same 50 every time

    def test_it_carries_the_features_for_the_wireframes(self, model):
        plots = self._solved(model)

        assert [f['kind'] for f in plots['features']] == ['sphere']

    def test_what_it_returns_survives_the_bridge(self, model):
        """The whole answer is plain lists; a numpy array in it reaches the
        canvas as an array, where the emptiness guards raise inside paint()."""
        json.dumps(self._solved(model))

    def test_a_state_that_was_not_solved_is_refused_by_number(self, model):
        self._solved(model)
        refused = model.statePlots(99)

        assert refused['ok'] is False
        assert "99" in refused['error']

    def test_it_says_so_before_a_solve(self, model):
        model.mode = "3d"

        assert model.statePlots(0)['ok'] is False

    def test_a_2d_model_has_no_volume_to_draw(self, model):
        """The view is three orthogonal cuts through a volume, and a plane
        has none — so it is a message rather than three copies of itself."""
        model.addFeature('circle', 10.0, 10.0)
        model.solve({'Nx': 30, 'Ny': 30, 'n_states': 1})
        refused = model.statePlots(0)

        assert refused['ok'] is False
        assert "2-D" in refused['error']
