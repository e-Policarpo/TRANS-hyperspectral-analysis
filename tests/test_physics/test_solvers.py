"""
Tests for the direct solvers — a geometry in, its levels out.

The other direction from the designer, and the check on it: the designer
matches energies analytically and cannot tell a real well from an alias of
the arithmetic, so what these have to get right is the numerics. A grid
solution that does not reproduce the textbook ladder is worse than useless,
because it looks like an answer.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.physics.analytical import box_energies_1d_eV
from src.physics.features import SegmentFeature1D
from src.physics.quantum_dot import dot_energies
from src.physics.solution_spec import SolutionSpec
from src.physics.solvers import (BOUNDARY_CONDITIONS, MAX_STATES,
                                 can_simulate, compare_with_targets, density,
                                 dot_from_spec, grid_axis, solve_dot,
                                 solve_well_1d, solve_well_2d, solve_well_3d,
                                 states_needed, well_from_spec)


class TestTheOneDimensionalWell:
    def test_it_reproduces_the_textbook_ladder(self):
        """An infinite well has a closed form; a grid solution that misses it
        is a bug in the grid, not physics."""
        solved = solve_well_1d(8.0, N=1200, n_states=4, meff=0.067)
        exact = [E for E, _ in box_energies_1d_eV(8.0, 0.067, 4)]

        assert solved['E_eV'] == pytest.approx(exact, rel=1e-4)

    def test_a_finer_grid_is_a_better_answer(self):
        """The error falls as the square of the spacing; if it does not, the
        discretisation is wrong somewhere."""
        exact = box_energies_1d_eV(8.0, 0.067, 1)[0][0]
        coarse = abs(solve_well_1d(8.0, N=100, n_states=1)['E_eV'][0] - exact)
        fine = abs(solve_well_1d(8.0, N=400, n_states=1)['E_eV'][0] - exact)

        assert fine < coarse / 10

    def test_a_wider_well_confines_less(self):
        """E ∝ 1/L²: double the width, a quarter of the energy."""
        narrow = solve_well_1d(5.0, N=800, n_states=1)['E_eV'][0]
        wide = solve_well_1d(10.0, N=800, n_states=1)['E_eV'][0]

        assert wide == pytest.approx(narrow / 4, rel=1e-3)

    def test_a_heavier_carrier_confines_less(self):
        light = solve_well_1d(8.0, N=800, n_states=1, meff=0.067)['E_eV'][0]
        heavy = solve_well_1d(8.0, N=800, n_states=1, meff=0.45)['E_eV'][0]

        assert heavy == pytest.approx(light * 0.067 / 0.45, rel=1e-3)

    def test_the_levels_come_back_ascending(self):
        energies = solve_well_1d(8.0, N=400, n_states=6)['E_eV']

        assert list(energies) == sorted(energies)

    def test_the_wavefunctions_come_with_them(self):
        solved = solve_well_1d(8.0, N=300, n_states=3)

        assert solved['psi'].shape == (300, 3)
        assert solved['x_nm'].shape == (300,)
        # Normalised as eigenvectors: each column has unit norm.
        assert np.linalg.norm(solved['psi'][:, 0]) == pytest.approx(1.0)

    def test_the_ground_state_has_no_node(self):
        """A basic sanity check on the solver's ordering: the lowest state of
        a simple well does not change sign."""
        psi = solve_well_1d(8.0, N=400, n_states=2)['psi']
        ground = psi[:, 0]

        assert np.all(ground >= -1e-12) or np.all(ground <= 1e-12)

    def test_a_feature_deepens_the_well_it_sits_in(self):
        """A −0.5 eV segment inside the box has to pull states below zero."""
        feature = SegmentFeature1D(5.0, 10.0, -0.5, 0.067)
        solved = solve_well_1d(20.0, N=800, n_states=3, features=[feature])

        assert solved['E_eV'][0] < 0
        assert solved['V_eV'].min() == pytest.approx(-0.5)

    def test_a_bad_boundary_condition_is_named(self):
        with pytest.raises(ValueError, match="boundary"):
            solve_well_1d(8.0, bc="springy")

    def test_a_zero_width_well_is_refused(self):
        with pytest.raises(ValueError, match="positive"):
            solve_well_1d(0.0)

    def test_the_state_count_is_capped(self):
        """Asking for a thousand levels is a mistake, not a request."""
        solved = solve_well_1d(8.0, N=400, n_states=10_000)

        assert len(solved['E_eV']) <= MAX_STATES

    def test_every_boundary_condition_solves(self):
        for bc in BOUNDARY_CONDITIONS:
            solved = solve_well_1d(8.0, N=200, n_states=2, bc=bc)
            assert len(solved['E_eV']) == 2, bc


class TestTheQuantumDot:
    def test_the_spherical_dot_fills_its_shells(self):
        """2, 8, 18 — the magic numbers a dot spectrum is read by."""
        from src.physics.quantum_dot import shell_table

        levels = solve_dot('dot_spherical', (5.0,), meff=0.067)
        shells = shell_table(levels)

        assert [s[3] for s in shells[:3]] == [2, 8, 18]

    def test_it_agrees_with_the_analytic_adapter(self):
        """The designer searches with `dot_energies`; the solver has to be
        solving the same dot, or a candidate would never verify.

        Level by level rather than list against list: the two truncate
        differently — the adapter opens as many channels as it needs for the
        count asked of it — so the lists are different lengths even though
        every level in one is in the other.
        """
        levels = solve_dot('dot_spherical', (5.0,), meff=0.067)
        fast = [E for E, _ in dot_energies('spherical', (5.0,), 0.067, 60)]

        assert levels
        for level in levels:
            assert min(abs(level.E_eV - E) for E in fast) < 1e-9, level.label

    def test_a_finite_barrier_binds_fewer_states(self):
        deep = solve_dot('dot_spherical', (5.0,), meff=0.067, V0_eV=None)
        shallow = solve_dot('dot_spherical', (5.0,), meff=0.067, V0_eV=0.5)

        assert 0 < len(shallow) < len(deep)

    def test_the_disc_takes_two_dimensions(self):
        levels = solve_dot('dot_disc', (10.0, 3.0), meff=0.067)

        assert levels
        assert all(len(lv.quantum_numbers) == 3 for lv in levels)

    def test_the_parabolic_dot_is_a_ladder(self):
        levels = solve_dot('dot_parabolic', (30.0, 100.0))
        energies = [lv.E_eV for lv in levels]

        assert energies == sorted(energies)
        assert levels[0].E_eV == pytest.approx((30.0 + 50.0) / 1000.0)

    def test_an_unknown_model_is_refused_by_name(self):
        with pytest.raises(ValueError, match="unknown dot model"):
            solve_dot('dot_cubic', (5.0,))


class TestFromACandidateToASolver:
    def _spec(self, **over):
        params = {'model': '1d', 'dims_nm': (8.0,), 'meff': 0.067,
                  'targets_eV': tuple(E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)),
                  'extras': {'max_qn': 3}}
        params.update(over)
        return SolutionSpec(**params)

    def test_a_1d_candidate_goes_to_the_well_solver(self):
        assert can_simulate(self._spec()) == "well"

    def test_a_dot_candidate_goes_to_the_dot_solver(self):
        assert can_simulate(SolutionSpec(model='dot_spherical',
                                         dims_nm=(5.0,))) == "dot"

    def test_a_3d_candidate_goes_nowhere_and_says_so(self):
        """An empty answer is a real one: no solver here builds a 3D box, and
        offering to simulate it would mean simulating something else."""
        assert can_simulate(SolutionSpec(model='3d', dims_nm=(5.0, 5.0, 5.0))) == ""

    def test_an_infinite_barrier_well_is_solved_in_its_own_box(self):
        """The walls do the confining, so the box IS the well."""
        args = well_from_spec(self._spec())

        assert args['L_nm'] == pytest.approx(8.0)
        assert args['features'][0].V0 == 0.0

    def test_a_finite_barrier_well_gets_room_for_its_tail(self):
        """Putting the box wall against the well returns the box's levels
        rather than the well's."""
        args = well_from_spec(self._spec(V0_eV=0.3))

        assert args['L_nm'] > 8.0
        assert args['features'][0].V0 == pytest.approx(-0.3)
        assert args['features'][0].width == pytest.approx(8.0)

    def test_the_candidate_verifies_against_its_own_targets(self):
        """The whole point of the bridge: the geometry the designer found,
        solved numerically, has to give back the energies it was fitted to."""
        spec = self._spec()
        solved = solve_well_1d(**well_from_spec(spec))
        comparison = compare_with_targets(solved['E_eV'], spec)

        assert comparison['rrmse_pct'] < 0.01
        assert comparison['covered'] is True

    def test_enough_states_are_solved_for_the_quantum_numbers_used(self):
        """Matching a target with n = 9 and then solving six levels compares
        it with the wrong one."""
        assert states_needed(self._spec(extras={'max_qn': 9})) >= 11
        assert states_needed(self._spec(extras={})) >= 4

    def test_the_state_count_stays_sane(self):
        assert states_needed(self._spec(extras={'max_qn': 5000})) <= MAX_STATES

    def test_a_dot_candidate_carries_its_dimensions_across(self):
        args = dot_from_spec(SolutionSpec(model='dot_disc', dims_nm=(6.0, 2.0),
                                          meff=0.067))

        assert args['dims_nm'] == [6.0, 2.0]
        assert args['model'] == 'dot_disc'

    def test_a_well_spec_is_refused_by_the_dot_bridge(self):
        with pytest.raises(ValueError, match="not a quantum dot"):
            dot_from_spec(self._spec())

    def test_a_dot_spec_is_refused_by_the_well_bridge(self):
        with pytest.raises(ValueError, match="not a 1D well"):
            well_from_spec(SolutionSpec(model='dot_spherical', dims_nm=(5.0,)))


class TestComparingWithTheMeasurement:
    def test_a_perfect_match_has_no_error(self):
        spec = SolutionSpec(model='1d', dims_nm=(8.0,),
                            targets_eV=(0.1, 0.2, 0.4))
        comparison = compare_with_targets([0.1, 0.2, 0.4], spec)

        assert comparison['rrmse_pct'] == pytest.approx(0.0)
        assert comparison['errors_pct'] == pytest.approx([0.0, 0.0, 0.0])

    def test_each_target_takes_its_nearest_level(self):
        spec = SolutionSpec(model='1d', dims_nm=(8.0,), targets_eV=(0.1, 0.4))
        comparison = compare_with_targets([0.11, 0.25, 0.39], spec)

        assert comparison['matched'] == pytest.approx([0.11, 0.39])

    def test_a_target_above_the_last_level_is_flagged(self):
        """The match is then against the wrong level, however small its error
        looks — solving further is the fix, and the user has to be told."""
        spec = SolutionSpec(model='1d', dims_nm=(8.0,), targets_eV=(0.1, 5.0))
        comparison = compare_with_targets([0.1, 0.2], spec)

        assert comparison['covered'] is False

    def test_nothing_to_compare_is_not_an_error(self):
        spec = SolutionSpec(model='1d', dims_nm=(8.0,))
        comparison = compare_with_targets([0.1], spec)

        assert comparison['matched'] == []
        assert np.isnan(comparison['rrmse_pct'])


class TestTheTwoAndThreeDimensionalWells:
    """The grids the Modeling workstation solves on."""

    def test_2d_reproduces_the_closed_form(self):
        from src.physics.analytical import box_energies_2d_eV

        solved = solve_well_2d(10.0, 6.0, Nx=120, Ny=80, n_states=4,
                               meff=0.067)
        exact = [E for E, _ in box_energies_2d_eV(10.0, 6.0, 0.067, 4)]

        assert solved['E_eV'] == pytest.approx(exact, rel=1e-3)

    def test_3d_reproduces_the_closed_form(self):
        """Coarser, because the cost is the grid cubed — so the tolerance is
        looser, and that is the honest trade rather than a weaker claim."""
        from src.physics.analytical import box_energies_3d_eV

        solved = solve_well_3d(8.0, 6.0, 5.0, Nx=28, Ny=24, Nz=20,
                               n_states=3, meff=0.067)
        exact = [E for E, _ in box_energies_3d_eV(8.0, 6.0, 5.0, 0.067, 3)]

        assert solved['E_eV'] == pytest.approx(exact, rel=6e-3)

    def test_a_square_box_is_degenerate(self):
        """(1,2) and (2,1) are the same energy; a solver that splits them has
        an asymmetry it should not have."""
        solved = solve_well_2d(8.0, 8.0, Nx=70, Ny=70, n_states=3)

        assert solved['E_eV'][1] == pytest.approx(solved['E_eV'][2], rel=1e-6)

    def test_the_potential_comes_back_shaped_like_the_grid(self):
        solved = solve_well_2d(10.0, 6.0, Nx=40, Ny=30, n_states=2)

        assert solved['shape'] == (40, 30)
        assert solved['V_eV'].shape == (40, 30)
        assert solved['psi'].shape == (1200, 2)

    def test_a_feature_binds_a_state_below_zero(self):
        from src.physics.features import CircleFeature2D

        well = CircleFeature2D(10.0, 10.0, 4.0, -0.4, 0.067)
        solved = solve_well_2d(20.0, 20.0, Nx=80, Ny=80, n_states=2,
                               features=[well])

        assert solved['E_eV'][0] < 0
        assert solved['V_eV'].min() == pytest.approx(-0.4)

    def test_a_density_is_one_state_on_the_grid(self):
        solved = solve_well_2d(10.0, 6.0, Nx=40, Ny=30, n_states=2)
        grid = density(solved['psi'], solved['shape'], 1)

        assert grid.shape == (40, 30)
        assert grid.sum() == pytest.approx(1.0)
        assert (grid >= 0).all()

    def test_a_3d_state_is_a_volume(self):
        solved = solve_well_3d(6.0, 6.0, 6.0, Nx=14, Ny=14, Nz=14, n_states=1)
        grid = density(solved['psi'], solved['shape'], 0)

        assert grid.shape == (14, 14, 14)
        assert grid.sum() == pytest.approx(1.0)

    def test_the_state_count_is_capped_here_too(self):
        solved = solve_well_2d(10.0, 10.0, Nx=30, Ny=30, n_states=10_000)

        assert len(solved['E_eV']) <= MAX_STATES


class TestTheGridAxis:
    def test_dirichlet_keeps_the_samples_inside_the_box(self):
        """The walls sit just outside the grid; a sample on the wall is a
        sample where the wavefunction is zero by construction."""
        axis, spacing = grid_axis(10.0, 9, "dirichlet")

        assert axis[0] == pytest.approx(1.0)
        assert axis[-1] == pytest.approx(9.0)
        assert spacing == pytest.approx(1e-9)

    def test_the_other_conditions_start_at_the_edge(self):
        axis, _spacing = grid_axis(10.0, 10, "neumann")

        assert axis[0] == pytest.approx(0.0)

    def test_a_zero_length_axis_is_refused(self):
        with pytest.raises(ValueError, match="positive"):
            grid_axis(0.0, 10)
