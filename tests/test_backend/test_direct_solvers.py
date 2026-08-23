"""
Tests for the direct-solver tools and the bridge from the designer.

The designer finds a geometry by matching energies; the solvers say what that
geometry really gives. What has to hold at this layer is the marshalling —
everything crossing to QML is a plain number — and the bridge: which solver a
candidate goes to, with what in its fields, and what happens when the answer
is "neither".

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest
from unittest.mock import Mock

from src.physics.analytical import box_energies_1d_eV


@pytest.fixture
def tool_impl(tmp_path):
    from src.backend.tool_implementations import ToolImplementations

    class MockBackend(ToolImplementations):
        def __init__(self):
            self._datasets = {}
            self._output_base_dir = tmp_path / "outputs"
            self._output_base_dir.mkdir(exist_ok=True)
            self.errorOccurred = Mock()
            self.dataLoaded = Mock()
            self._workflow_mode = False

        def _ensure_output_dir(self, subdir):
            path = self._output_base_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _sanitize_filename(self, name):
            return re.sub(r'\W+', '_', name) or "unnamed"

        def _extract_clean_base_name(self, name):
            return name

    return MockBackend()


def _candidate(**over):
    """A designer candidate map, as `_designer_candidate` emits one."""
    targets = [E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)]
    candidate = {
        'index': 0, 'dims_nm': [8.0], 'size_nm': 8.0, 'rrmse': 0.0,
        'rrmse_de': 0.0, 'meff': 0.067, 'carrier': 'e', 'offset_eV': 0.0,
        'ndim': '1D', 'coords': 'cartesian', 'sym': '',
        'targets': targets, 'computed': targets,
        'errors_pct': [0.0, 0.0, 0.0], 'qn': [[1], [2], [3]],
    }
    candidate.update(over)
    return candidate


class TestTheWellSolver:
    def test_it_solves_the_well_it_is_given(self, tool_impl):
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'n_states': 3})
        exact = [E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)]

        assert result['ok'] is True
        assert result['E_eV'] == pytest.approx(exact, rel=1e-3)

    def test_it_returns_the_potential_and_the_grid(self, tool_impl):
        """A level means nothing without the well it sits in."""
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'N': 200,
                                               'n_states': 2})

        assert len(result['x_nm']) == 200
        assert len(result['V_eV']) == 200
        assert len(result['psi']) == 2
        assert len(result['psi'][0]) == 200

    def test_a_finite_barrier_widens_the_box(self, tool_impl):
        """Room for the evanescent tail, or the walls give the box's levels."""
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'V0_eV': 0.3,
                                               'n_states': 2})

        assert result['L_box_nm'] > 8.0
        assert min(result['V_eV']) == pytest.approx(-0.3)

    def test_only_bound_states_count_with_a_finite_barrier(self, tool_impl):
        """Above the barrier the state is the box's, and reporting it as the
        well's is a lie the grid makes easy."""
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'V0_eV': 0.3,
                                               'n_states': 8})

        assert all(E < 0 for E in result['bound'])
        assert len(result['bound']) <= len(result['E_eV'])

    def test_it_compares_with_the_measured_levels_when_given_them(self, tool_impl):
        targets = [E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)]
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'n_states': 4,
                                               'targets': targets})

        assert result['comparison']['rrmse_pct'] < 0.01
        assert result['comparison']['covered'] is True

    def test_without_targets_there_is_nothing_to_compare(self, tool_impl):
        result = tool_impl.solve_quantum_well({'L_nm': 8.0, 'n_states': 2})

        assert result['comparison'] == {}

    def test_a_bad_parameter_is_reported_not_raised(self, tool_impl):
        """A solver window is turn-a-knob-and-look; a traceback into QML is
        not an answer."""
        result = tool_impl.solve_quantum_well({'L_nm': 0.0})

        assert result['ok'] is False
        assert result['error']

    def test_everything_it_returns_survives_the_bridge(self, tool_impl):
        json.dumps(tool_impl.solve_quantum_well({'L_nm': 8.0, 'n_states': 2,
                                                 'N': 100}))


class TestTheDotSolver:
    def test_it_solves_a_spherical_dot(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical',
                                              'R_nm': 5.0})

        assert result['ok'] is True
        assert result['levels'][0]['label'] == '1s'
        assert result['levels'][0]['E_eV'] == pytest.approx(0.2245, abs=1e-3)

    def test_the_shells_fill_by_the_magic_numbers(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical',
                                              'R_nm': 5.0})

        assert [s['filled'] for s in result['shells'][:3]] == [2, 8, 18]

    def test_it_returns_what_a_didv_would_see(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical',
                                              'R_nm': 5.0})

        assert len(result['dos']['x']) == len(result['dos']['y']) > 0

    def test_the_addition_energy_is_one_per_electron_gap(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical',
                                              'R_nm': 5.0})
        electrons = sum(level['occupancy'] for level in result['levels'])

        assert len(result['addition_eV']) == electrons - 1

    def test_the_charging_energy_shifts_every_addition(self, tool_impl):
        plain = tool_impl.solve_quantum_dot({'model': 'spherical', 'R_nm': 5.0})
        charged = tool_impl.solve_quantum_dot({'model': 'spherical', 'R_nm': 5.0,
                                               'charging_eV': 0.01})

        assert charged['addition_eV'] == pytest.approx(
            [v + 0.01 for v in plain['addition_eV']])

    def test_the_chosen_state_comes_with_its_radial_function(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical', 'R_nm': 5.0,
                                              'state_index': 2})

        assert result['radial']['index'] == 2
        assert len(result['radial']['r_nm']) == len(result['radial']['psi']) > 0

    def test_a_state_index_past_the_end_is_clamped(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical', 'R_nm': 5.0,
                                              'state_index': 999})

        assert result['radial']['index'] == len(result['levels']) - 1

    def test_a_disc_takes_its_second_dimension(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'disc', 'R_nm': 10.0,
                                              'Lz_nm': 3.0})

        assert result['ok'] and result['levels']

    def test_a_parabolic_dot_is_solved_in_energies(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'parabolic',
                                              'hw_xy_meV': 30.0,
                                              'hw_z_meV': 100.0})

        assert result['levels'][0]['E_eV'] == pytest.approx(0.080, abs=1e-6)

    def test_a_dot_too_shallow_to_bind_anything_says_so(self, tool_impl):
        result = tool_impl.solve_quantum_dot({'model': 'spherical', 'R_nm': 1.0,
                                              'V0_eV': 0.001})

        assert result['ok'] is False
        assert "widen" in result['error'] or "deepen" in result['error']

    def test_everything_it_returns_survives_the_bridge(self, tool_impl):
        json.dumps(tool_impl.solve_quantum_dot({'model': 'spherical',
                                                'R_nm': 5.0}))


class TestTheBridgeFromTheDesigner:
    def test_a_1d_candidate_goes_to_the_well_solver(self, tool_impl):
        described = tool_impl.describe_candidate(_candidate())

        assert described['ok'] is True
        assert described['solver'] == 'well'
        assert described['params']['L_nm'] == pytest.approx(8.0)
        assert described['params']['meff'] == pytest.approx(0.067)

    def test_it_carries_the_measured_levels_across(self, tool_impl):
        """The solver draws them across the well: the point of simulating a
        candidate is seeing whether the levels land on them."""
        described = tool_impl.describe_candidate(_candidate())

        assert len(described['targets']) == 3

    def test_it_asks_for_enough_states_to_reach_the_match(self, tool_impl):
        """Matching a target with n = 9 and solving six levels compares it
        with the wrong one."""
        high = _candidate(qn=[[7], [8], [9]])
        described = tool_impl.describe_candidate(high)

        assert described['params']['n_states'] >= 11

    def test_a_dot_candidate_goes_to_the_dot_solver(self, tool_impl):
        described = tool_impl.describe_candidate(
            _candidate(ndim='0D', coords='spherical', dims_nm=[5.0]))

        assert described['solver'] == 'dot'
        assert described['params']['model'] == 'spherical'
        assert described['params']['R_nm'] == pytest.approx(5.0)

    def test_a_disc_candidate_carries_both_dimensions(self, tool_impl):
        described = tool_impl.describe_candidate(
            _candidate(ndim='0D', coords='disc', dims_nm=[6.0, 2.0]))

        assert described['params']['R_nm'] == pytest.approx(6.0)
        assert described['params']['Lz_nm'] == pytest.approx(2.0)

    def test_a_3d_candidate_is_refused_with_a_reason(self, tool_impl):
        """No solver here builds a 3D box, and offering to simulate it would
        mean simulating something else."""
        described = tool_impl.describe_candidate(
            _candidate(ndim='3D', coords='cartesian', dims_nm=[5.0, 5.0, 5.0]))

        assert described['ok'] is False
        assert described['solver'] == ''
        assert "3D" in described['error']

    def test_a_candidate_with_no_geometry_is_refused(self, tool_impl):
        assert tool_impl.describe_candidate({})['ok'] is False
        assert tool_impl.describe_candidate(None)['ok'] is False

    def test_the_round_trip_verifies_the_candidate(self, tool_impl):
        """End to end: a candidate the designer found, described for a solver,
        solved, and compared back against the energies it was fitted to."""
        described = tool_impl.describe_candidate(_candidate())
        result = tool_impl.solve_quantum_well({**described['params'],
                                               'targets': described['targets']})

        assert result['ok'] is True
        assert result['comparison']['rrmse_pct'] < 0.01

    def test_an_alias_is_caught_by_the_numerics(self, tool_impl):
        """A well three times too large matches the same targets analytically
        with n = 3, 6, 9 — and still solves to those energies. What the
        solver adds is that it says so with its own numbers rather than the
        search's, which is the check the bridge exists for."""
        alias = _candidate(dims_nm=[24.0], qn=[[3], [6], [9]])
        described = tool_impl.describe_candidate(alias)
        result = tool_impl.solve_quantum_well({**described['params'],
                                               'targets': described['targets']})

        assert described['params']['n_states'] >= 11
        assert result['comparison']['covered'] is True

    def test_everything_the_bridge_returns_survives_it(self, tool_impl):
        json.dumps(tool_impl.describe_candidate(_candidate()))
