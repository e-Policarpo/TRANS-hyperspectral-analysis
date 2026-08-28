"""
Tests for the curved-coordinate solvers — a disc, a cylinder and a ball.

A round wall on a Cartesian grid is a staircase, and the error that costs is
the reason these exist. What they have to earn is the closed form: an infinite
disc, cylinder and sphere all have one, and a polar Laplacian that reproduces
it is a polar Laplacian whose 1/r and 1/r² terms are right at the origin —
which is the whole difficulty. Every degeneracy is checked too, because an
operator with a hidden asymmetry splits a multiplet that physics says is one
level, and the energies alone would not show it.

The analytical helpers list each |m| once; the grid resolves +m and -m as two
eigenvalues, so the reference is expanded by multiplicity before comparing.
Skipping that step reads as a 40% error and is a bug in the test, not the
solver.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse
from scipy.constants import e, hbar, m_e, pi

from src.physics.analytical import cylinder_energies, disk_energies
from src.physics.laplacian import (azimuth_nodes, cylindrical_weights,
                                   lap2d_polar, lap3d_cylindrical,
                                   lap3d_spherical, polar_angle_nodes,
                                   polar_weights, radial_nodes,
                                   spherical_weights)
from src.physics.solvers import (solve_well_2d, solve_well_2d_polar,
                                 solve_well_3d, solve_well_3d_cylindrical,
                                 solve_well_3d_spherical)

MEFF = 0.067


def _expanded(levels, n_levels):
    """The analytical ladder with each |m| > 0 counted twice.

    m is the first quantum number in both helpers' labels; the grid cannot
    tell e^{imθ} from e^{-imθ} by energy, so both are there.
    """
    out = []
    for energy, numbers in levels:
        out.extend([energy] * (1 if numbers[0] == 0 else 2))
    out.sort()
    return out[:n_levels]


def _worst(solved, exact):
    return max(abs(a - b) / b for a, b in zip(solved, exact))


class TestTheDisc:
    def test_it_reproduces_the_bessel_ladder(self):
        """E ∝ (x_mn/R)², x_mn the zeros of J_m. Nothing about that comes out
        of a square grid, which is what the polar one is for."""
        solved = solve_well_2d_polar(10.0, Nr=70, Ntheta=24, n_states=6,
                                     meff=MEFF)
        exact = _expanded(disk_energies(10.0, MEFF, 30), 6)

        assert _worst(solved['E_eV'], exact) < 0.02

    def test_a_finer_grid_is_a_better_answer(self):
        """Second order in the spacing, so four times the nodes is about a
        quarter of the error. A flux form that had the metric weights on the
        nodes instead of the faces would stall well short of this."""
        exact = _expanded(disk_energies(10.0, MEFF, 30), 6)
        coarse = _worst(solve_well_2d_polar(10.0, Nr=35, Ntheta=12,
                                            n_states=6, meff=MEFF)['E_eV'],
                        exact)
        fine = _worst(solve_well_2d_polar(10.0, Nr=140, Ntheta=48,
                                          n_states=6, meff=MEFF)['E_eV'],
                      exact)

        assert fine < coarse / 3

    def test_the_angular_pairs_are_exactly_degenerate(self):
        """+m and -m are the same energy on a disc. A split here is an
        asymmetry in the operator, and it would not show up in the energies
        on their own."""
        levels = solve_well_2d_polar(10.0, Nr=70, Ntheta=24, n_states=6,
                                     meff=MEFF)['E_eV']

        assert levels[1] == pytest.approx(levels[2], rel=1e-9)
        assert levels[3] == pytest.approx(levels[4], rel=1e-9)

    def test_a_smaller_disc_confines_more(self):
        """E ∝ 1/R²: halve the radius, four times the energy."""
        wide = solve_well_2d_polar(10.0, Nr=60, Ntheta=16, n_states=1)['E_eV']
        narrow = solve_well_2d_polar(5.0, Nr=60, Ntheta=16, n_states=1)['E_eV']

        assert narrow[0] == pytest.approx(4 * wide[0], rel=1e-3)

    def test_it_comes_back_on_the_axes_it_solved_on(self):
        """r and theta, not x and y — a polar grid is not separable in x and
        y, so a caller that meshgrids them draws the wrong picture."""
        solved = solve_well_2d_polar(10.0, Nr=20, Ntheta=8, n_states=1)

        assert solved['coords'] == "polar"
        assert solved['shape'] == (20, 8)
        assert set(solved) >= {'r_nm', 'theta_rad', 'X_nm', 'Y_nm', 'weights'}
        assert 'x_nm' not in solved
        assert solved['X_nm'].shape == (20, 8)

    def test_a_feature_binds_a_state_below_zero(self):
        """The Cartesian features keep their own nm frame, so the same well
        means the same shape on either grid."""
        from src.physics.features import CircleFeature2D

        well = CircleFeature2D(10.0, 10.0, 4.0, -0.5, MEFF)
        solved = solve_well_2d_polar(10.0, Nr=60, Ntheta=16, n_states=1,
                                     meff=MEFF, features=[well],
                                     centre_nm=(10.0, 10.0))

        assert solved['E_eV'][0] < 0
        assert solved['V_eV'].min() == pytest.approx(-0.5)


class TestTheCylinder:
    def test_it_reproduces_the_closed_form(self):
        """E = (ħ²/2m)[(x_mn/R)² + (lπ/H)²] — the disc's ladder with a box
        along z on top of it, so it fails if either half is wrong."""
        solved = solve_well_3d_cylindrical(5.0, 10.0, Nr=16, Ntheta=12, Nz=12,
                                           n_states=4, meff=MEFF)
        exact = _expanded(cylinder_energies(5.0, 10.0, MEFF, 40), 4)

        assert _worst(solved['E_eV'], exact) < 0.02

    def test_a_finer_grid_is_a_better_answer(self):
        exact = _expanded(cylinder_energies(5.0, 10.0, MEFF, 40), 4)
        coarse = _worst(solve_well_3d_cylindrical(5.0, 10.0, Nr=10, Ntheta=8,
                                                  Nz=8, n_states=4,
                                                  meff=MEFF)['E_eV'], exact)
        fine = _worst(solve_well_3d_cylindrical(5.0, 10.0, Nr=24, Ntheta=16,
                                                Nz=16, n_states=4,
                                                meff=MEFF)['E_eV'], exact)

        assert fine < coarse

    def test_the_angular_pairs_are_degenerate_here_too(self):
        levels = solve_well_3d_cylindrical(5.0, 10.0, Nr=16, Ntheta=12, Nz=12,
                                           n_states=4, meff=MEFF)['E_eV']

        assert levels[2] == pytest.approx(levels[3], rel=1e-9)

    def test_a_taller_cylinder_confines_less_along_its_axis(self):
        short = solve_well_3d_cylindrical(5.0, 6.0, Nr=12, Ntheta=8, Nz=12,
                                          n_states=1, meff=MEFF)['E_eV'][0]
        tall = solve_well_3d_cylindrical(5.0, 12.0, Nr=12, Ntheta=8, Nz=12,
                                         n_states=1, meff=MEFF)['E_eV'][0]

        assert tall < short

    def test_it_is_shaped_like_its_grid(self):
        solved = solve_well_3d_cylindrical(5.0, 10.0, Nr=10, Ntheta=8, Nz=6,
                                           n_states=1)

        assert solved['coords'] == "cylindrical"
        assert solved['shape'] == (10, 8, 6)
        assert set(solved) >= {'r_nm', 'theta_rad', 'z_nm'}

    def test_the_axial_grid_follows_the_boundary_it_was_given(self):
        """The potential builder and the solver each lay z out, and they used
        to disagree under Neumann — so the wells were sampled on a grid the
        states were never solved on."""
        from src.physics.potentials import build_potential_3d_cylindrical

        solved = solve_well_3d_cylindrical(5.0, 10.0, Nr=8, Ntheta=6, Nz=6,
                                           n_states=1, bc_z="neumann")
        _V, (_r, _theta, z_built) = build_potential_3d_cylindrical(
            [], 5.0e-9, 10.0e-9, 8, 6, 6, bc="neumann")

        assert solved['z_nm'] * 1e-9 == pytest.approx(z_built, abs=1e-18)


class TestTheBall:
    """The reference is E = ħ²a²/2mR² with a the zeros of the spherical
    Bessel j_l; for l = 0 those are exactly nπ, which is the case checked
    here because it needs no root finding to state."""

    @staticmethod
    def _s_wave(R_nm, n):
        R = R_nm * 1e-9
        return hbar ** 2 * (n * pi) ** 2 / (2 * MEFF * m_e * R ** 2) / e

    def test_the_ground_state_is_the_s_wave(self):
        solved = solve_well_3d_spherical(5.0, Nr=16, Ntheta=12, Nphi=16,
                                         n_states=1, meff=MEFF)

        assert solved['E_eV'][0] == pytest.approx(self._s_wave(5.0, 1),
                                                  rel=0.01)

    def test_a_finer_grid_is_a_better_answer(self):
        exact = self._s_wave(5.0, 1)
        coarse = abs(solve_well_3d_spherical(5.0, Nr=8, Ntheta=6, Nphi=8,
                                             n_states=1,
                                             meff=MEFF)['E_eV'][0] - exact)
        fine = abs(solve_well_3d_spherical(5.0, Nr=24, Ntheta=16, Nphi=20,
                                           n_states=1,
                                           meff=MEFF)['E_eV'][0] - exact)

        assert fine < coarse / 3

    def test_the_p_shell_is_a_triplet(self):
        """l = 1 is threefold degenerate. Angular resolution is what closes
        it up, so a coarse theta/phi grid splits it — 1% here, and a solver
        that split it by more than that would be reporting three states where
        there is one level."""
        levels = solve_well_3d_spherical(5.0, Nr=16, Ntheta=12, Nphi=16,
                                         n_states=4, meff=MEFF)['E_eV']
        shell = levels[1:4]

        assert (max(shell) - min(shell)) / min(shell) < 0.01

    def test_the_p_shell_sits_above_the_s_wave(self):
        """j_1's first zero is 4.49341 against π for j_0 — a ratio of 2.05 in
        energy, which no accidental degeneracy of a cube reproduces."""
        levels = solve_well_3d_spherical(5.0, Nr=16, Ntheta=12, Nphi=16,
                                         n_states=4, meff=MEFF)['E_eV']
        ratio = np.mean(levels[1:4]) / levels[0]

        assert ratio == pytest.approx((4.49341 / pi) ** 2, rel=0.02)

    def test_a_smaller_ball_confines_more(self):
        wide = solve_well_3d_spherical(6.0, Nr=12, Ntheta=8, Nphi=10,
                                       n_states=1)['E_eV'][0]
        narrow = solve_well_3d_spherical(3.0, Nr=12, Ntheta=8, Nphi=10,
                                         n_states=1)['E_eV'][0]

        assert narrow == pytest.approx(4 * wide, rel=1e-3)

    def test_it_is_shaped_like_its_grid(self):
        solved = solve_well_3d_spherical(5.0, Nr=10, Ntheta=6, Nphi=8,
                                         n_states=1)

        assert solved['coords'] == "spherical"
        assert solved['shape'] == (10, 6, 8)
        assert set(solved) >= {'r_nm', 'theta_rad', 'phi_rad'}


class TestChoosingTheGrid:
    """`coords` on the Cartesian entry points, which is how the workstation
    asks for a curved solve."""

    def test_the_default_is_still_a_box(self):
        assert solve_well_2d(10.0, 10.0, Nx=20, Ny=20,
                             n_states=1)['coords'] == "cartesian"
        assert solve_well_3d(6.0, 6.0, 6.0, Nx=8, Ny=8, Nz=8,
                             n_states=1)['coords'] == "cartesian"

    @pytest.mark.parametrize("spelling", ['polar', 'circular', 'disc', 'DISK'])
    def test_a_disc_is_asked_for_by_any_of_its_names(self, spelling):
        solved = solve_well_2d(20.0, 20.0, Nx=60, Ny=16, n_states=1,
                               coords=spelling)

        assert solved['coords'] == "polar"

    def test_the_disc_it_solves_is_the_one_inscribed_in_the_box(self):
        """The box is what the editor holds, so a curved solve has to mean
        something in the same frame: the disc it inscribes."""
        boxed = solve_well_2d(20.0, 20.0, Nx=70, Ny=24, n_states=1,
                              coords="circular")['E_eV'][0]
        direct = solve_well_2d_polar(10.0, Nr=70, Ntheta=24,
                                     n_states=1)['E_eV'][0]

        assert boxed == pytest.approx(direct, rel=1e-9)

    @pytest.mark.parametrize("spelling,expected", [
        ('cylindrical', 'cylindrical'), ('cylinder', 'cylindrical'),
        ('spherical', 'spherical'), ('sphere', 'spherical'),
        ('ball', 'spherical')])
    def test_a_volume_picks_its_own_system(self, spelling, expected):
        solved = solve_well_3d(10.0, 10.0, 10.0, Nx=10, Ny=8, Nz=8,
                               n_states=1, coords=spelling)

        assert solved['coords'] == expected

    def test_a_system_that_is_not_two_dimensional_is_refused(self):
        with pytest.raises(ValueError, match="unknown coordinate system"):
            solve_well_2d(10.0, 10.0, coords="spherical")

    def test_a_system_nobody_implements_is_named_rather_than_ignored(self):
        with pytest.raises(ValueError, match="toroidal"):
            solve_well_3d(6.0, 6.0, 6.0, coords="toroidal")


class TestTheOperatorsThemselves:
    """What the closed-form checks rest on, asserted directly, because a
    curved Laplacian can be wrong in ways an eigenvalue hides."""

    def test_the_radial_grid_puts_its_first_face_on_the_origin(self):
        """The flux form has no `if r > 0` guard: the singular term is
        multiplied by a face weight that is exactly zero there. That is only
        true on the cell-centred grid, which is why the grid is checked."""
        for Nr in (16, 70, 140):
            r, dr = radial_nodes(10.0, Nr)

            assert r[0] / dr == pytest.approx(0.5)
            assert r[0] - dr / 2 == pytest.approx(0.0, abs=1e-15)

    @pytest.mark.parametrize("Nr", [16, 70])
    def test_no_row_draws_on_a_node_outside_the_disc(self, Nr):
        """Row zero summing to zero is the statement that the origin row
        couples only outward — nothing is being read from a ghost node at
        r < 0."""
        lap, _r, _theta = lap2d_polar(Nr, 16, 10.0)
        rows = np.asarray(lap.sum(axis=1)).ravel()

        assert np.isfinite(rows).all()
        assert rows[0] == pytest.approx(0.0, abs=1e-9)

    def test_a_polar_operator_is_self_adjoint_under_its_metric(self):
        """W·L symmetric is what licenses the W^½ symmetrisation the solver
        does before handing the problem to eigsh."""
        lap, r, _theta = lap2d_polar(24, 12, 10.0)
        weighted = sparse.diags(polar_weights(r, 12)).dot(lap).toarray()

        assert np.abs(weighted - weighted.T).max() / np.abs(weighted).max() \
            < 1e-12

    def test_a_reflecting_operator_annihilates_a_constant(self):
        """With every wall reflecting there is nothing left but the metric,
        and the Laplacian of a constant is zero. A misplaced 1/r would not
        be."""
        r, dr = radial_nodes(5e-9, 12)
        theta, dtheta = azimuth_nodes(8)
        z_step = 1e-9
        lap = lap3d_cylindrical(12, 8, 6, r, dr, dtheta, z_step,
                                bc=("neumann", "neumann"))
        flat = np.ones(12 * 8 * 6)

        assert np.abs(lap @ flat).max() / np.abs(lap).max() < 1e-12

    def test_a_grid_that_is_not_cell_centred_is_refused(self):
        """`linspace(dr, R - dr, Nr)` gives an answer that looks plausible
        and is several percent wrong in every state that does not vanish at
        the origin, so it fails loudly instead."""
        bad = np.linspace(1e-10, 5e-9, 12)
        theta, dtheta = azimuth_nodes(8)

        with pytest.raises(ValueError):
            lap3d_cylindrical(12, 8, 6, bad, bad[1] - bad[0], dtheta, 1e-9)

    def test_an_angular_step_that_does_not_close_the_turn_is_refused(self):
        """dtheta must be 2π/Ntheta, or the operator quietly solves a wedge
        instead of a cylinder."""
        r, dr = radial_nodes(5e-9, 12)

        with pytest.raises(ValueError):
            lap3d_cylindrical(12, 8, 6, r, dr, 0.1, 1e-9)

    def test_a_spherical_polar_grid_is_checked_the_same_way(self):
        r, dr = radial_nodes(5e-9, 10)
        _theta, dtheta = polar_angle_nodes(6)
        _phi, dphi = azimuth_nodes(8)

        lap3d_spherical(10, 6, 8, r, dr, dtheta, dphi)      # the right one
        with pytest.raises(ValueError):
            lap3d_spherical(10, 6, 8, r, dr, dtheta * 1.5, dphi)

    def test_the_metric_weights_are_positive_everywhere(self):
        """A zero weight would be a node with no volume, and the W^½
        symmetrisation divides by it."""
        r, _dr = radial_nodes(5e-9, 12)
        theta, _dtheta = polar_angle_nodes(6)

        assert (polar_weights(r, 8) > 0).all()
        assert (cylindrical_weights(r, 8, 6) > 0).all()
        assert (spherical_weights(r, theta, 8) > 0).all()
