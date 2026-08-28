"""
Sanity-check tests for the Calculadora de Autoestados.

Each test uses a simple, analytically tractable case to verify
that the core machinery works correctly.
"""

import numpy as np
import pytest
from scipy.constants import hbar, m_e, e, pi
from scipy.sparse.linalg import eigsh

from src.physics.features import (BoxFeature3D, CircleFeature2D,
                            PyramidFeature3D, PrismFeature3D,
                            ConeFeature3D, SphereFeature3D,
                            build_potential_from_features)
from src.physics.analytical import (box_energies_1d_eV, box_energies_2d_eV,
                              box_energies_3d_eV, disk_energies,
                              cylinder_energies)
from src.physics.laplacian import lap3d_cartesian
from src.physics.tunneling import compute_overlap_matrix


# ═══════════════════════════════════════════════════════════════════════
#  1. Pirâmide N-gonal: geometria do contains()
# ═══════════════════════════════════════════════════════════════════════

class TestPyramidNGonal:
    """Verify that the N-gonal pyramid contains() is geometrically correct."""

    def test_square_pyramid_center(self):
        """Centre of base of a square pyramid must be inside."""
        pyr = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                               n_sides=4)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([-4.0])  # near the base (z_bot = -5)
        assert pyr.contains(X, Y, Z)[0]

    def test_square_pyramid_apex_empty(self):
        """Just above the apex should be outside."""
        pyr = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                               n_sides=4)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([5.1])  # above apex at z=+5
        assert not pyr.contains(X, Y, Z)[0]

    def test_triangular_excludes_square_vertex_region(self):
        """A point near a vertex of the square (N=4) polygon should be outside
        the triangular (N=3) polygon of the same circumradius.
        N=4 vertices at 0,90,180,270 deg; point along x-axis at r=4 is inside.
        N=3 vertices at 0,120,240 deg; point at y=2 near 90 deg is outside."""
        pyr4 = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                                n_sides=4)
        pyr3 = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                                n_sides=3)
        # Point along x-axis (vertex direction for N=4), inside both
        X = np.array([3.0])
        Y = np.array([0.0])
        Z = np.array([-4.9])
        assert pyr4.contains(X, Y, Z)[0]
        assert pyr3.contains(X, Y, Z)[0]  # also inside triangle (near vertex)

        # Point at ~90 deg (between triangle vertices), far from centre
        # Inradius of equilateral triangle = R*cos(60°) = 5*0.5 = 2.5
        X2 = np.array([0.0])
        Y2 = np.array([3.0])  # > 2.5 inradius
        assert pyr4.contains(X2, Y2, Z)[0]   # inside diamond
        assert not pyr3.contains(X2, Y2, Z)[0]  # outside triangle

    def test_hexagonal_contains_more_than_square(self):
        """A hexagonal base inscribed in the same circle has larger inradius,
        so a point between vertices can be closer to the edge of the hex
        while still inside, but outside the square (diamond)."""
        pyr4 = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                                n_sides=4)
        pyr6 = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                                n_sides=6)
        # Hex inradius = 5*cos(30°) ≈ 4.33; diamond inradius = 5*cos(45°) ≈ 3.54
        # Point at 45 deg (between vertices for both), r = 3.8
        angle = np.radians(45)
        r = 3.8
        X = np.array([r * np.cos(angle)])
        Y = np.array([r * np.sin(angle)])
        Z = np.array([-4.9])
        in6 = pyr6.contains(X, Y, Z)[0]
        in4 = pyr4.contains(X, Y, Z)[0]
        assert in6      # inside hex (3.8 < 4.33)
        assert not in4   # outside diamond (3.8 > 3.54)

    def test_cross_section_shrinks_with_height(self):
        """Points at the base level should be inside but same xy at mid-height
        might be outside (pyramid narrows)."""
        pyr = PyramidFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                               n_sides=4)
        X = np.array([4.0])
        Y = np.array([0.0])
        Z_base = np.array([-4.5])  # near bottom
        Z_mid = np.array([0.0])    # half-way up
        assert pyr.contains(X, Y, Z_base)[0]
        assert not pyr.contains(X, Y, Z_mid)[0]  # radius halved at midpoint

    def test_n_sides_stored(self):
        """n_sides should be stored and minimum is 3."""
        pyr = PyramidFeature3D(0, 0, 0, 10, 10, -0.3, n_sides=6)
        assert pyr.n_sides == 6
        pyr2 = PyramidFeature3D(0, 0, 0, 10, 10, -0.3, n_sides=2)
        assert pyr2.n_sides == 3  # clamped to minimum 3


# ═══════════════════════════════════════════════════════════════════════
#  2. Analytical energy levels: basic sanity
# ═══════════════════════════════════════════════════════════════════════

class TestAnalyticalEnergies:
    """Verify analytical energy formulas against manual calculations."""

    def test_1d_ground_state(self):
        """E₁ = hbar²π²/(2mL²) for GaAs electron in 10nm well."""
        L_nm, meff = 10.0, 0.067
        result = box_energies_1d_eV(L_nm, meff, 1)
        E1_eV = result[0][0]
        # Manual: hbar²π²/(2 * 0.067 * m_e * (10e-9)²) / e
        L = 10e-9
        E_manual = (hbar**2 * pi**2) / (2 * meff * m_e * L**2) / e
        assert abs(E1_eV - E_manual) / E_manual < 1e-10

    def test_1d_ratio_E2_E1(self):
        """E₂/E₁ = 4 for 1D infinite well."""
        result = box_energies_1d_eV(10.0, 0.067, 2)
        ratio = result[1][0] / result[0][0]
        assert abs(ratio - 4.0) < 1e-10

    def test_3d_cubic_degeneracy(self):
        """For a cubic box (Lx=Ly=Lz), the first excited level should be
        triply degenerate: (2,1,1), (1,2,1), (1,1,2)."""
        result = box_energies_3d_eV(10, 10, 10, 0.067, 6)
        # Ground state is (1,1,1)
        E_ground = result[0][0]
        # Next three should have equal energy
        E_1 = result[1][0]
        E_2 = result[2][0]
        E_3 = result[3][0]
        assert abs(E_1 - E_2) / E_1 < 1e-10
        assert abs(E_2 - E_3) / E_2 < 1e-10
        # And they should differ from the ground state
        assert E_1 > E_ground * 1.1

    def test_disk_ground_state_positive(self):
        """Disk ground state energy should be positive."""
        result = disk_energies(10.0, 0.067, 1)
        assert result[0][0] > 0


# ═══════════════════════════════════════════════════════════════════════
#  3. Designer inverso: priority weights
# ═══════════════════════════════════════════════════════════════════════

class TestInversePriority:
    """Test the weight-generation logic from tab_inverse."""

    def _make_weights(self, n_targets, priority):
        """Replicates the _make_weights logic from TabInverse."""
        if priority == "ground_state":
            w = np.zeros(n_targets)
            w[0] = 1.0
            return w
        elif priority == "low_quantum_numbers":
            idx = np.arange(1, n_targets + 1, dtype=float)
            w = 1.0 / idx**2
            return w / w.sum() * n_targets
        else:
            return np.ones(n_targets)

    def test_uniform_weights(self):
        w = self._make_weights(5, "uniform")
        np.testing.assert_array_equal(w, np.ones(5))

    def test_ground_state_only_first(self):
        w = self._make_weights(5, "ground_state")
        assert w[0] == 1.0
        assert all(w[i] == 0.0 for i in range(1, 5))

    def test_low_qn_decreasing(self):
        w = self._make_weights(5, "low_quantum_numbers")
        assert w[0] > w[1] > w[2] > w[3] > w[4]

    def test_low_qn_sum(self):
        """Weights normalised so sum = n_targets."""
        w = self._make_weights(5, "low_quantum_numbers")
        assert abs(w.sum() - 5.0) < 1e-10


# ═══════════════════════════════════════════════════════════════════════
#  4. Potential builder: feature contains + potential assembly
# ═══════════════════════════════════════════════════════════════════════

class TestPotentialBuilder:
    """Verify that build_potential_from_features assembles V correctly."""

    def test_empty_features_uniform(self):
        """No features => V = V_barrier everywhere."""
        x = np.linspace(-5, 5, 20)
        y = np.linspace(-5, 5, 20)
        z = np.linspace(-5, 5, 20)
        V, _ = build_potential_from_features([], (x, y, z), V_barrier_eV=0.5)
        V_expected = 0.5 * e  # in Joules
        np.testing.assert_allclose(V, V_expected)

    def test_box_feature_sets_potential(self):
        """A box feature at the centre should set V = V0 inside."""
        x = np.linspace(-10, 10, 40)
        y = np.linspace(-10, 10, 40)
        z = np.linspace(-10, 10, 40)
        box = BoxFeature3D(0, 0, 0, 6, 6, 6, V0_eV=-0.3)
        V, _ = build_potential_from_features([box], (x, y, z), V_barrier_eV=0.0)
        # Centre point should have V = -0.3 eV
        mid = len(x) // 2
        V_centre = V[mid, mid, mid]
        assert abs(V_centre - (-0.3 * e)) / (0.3 * e) < 1e-6

    def test_subsampling_gives_a_boundary_cell_a_partial_depth(self):
        """A cell the feature only half covers is only half as deep.

        Without this every cell is wholly in or wholly out: a round feature
        is a staircase of whole cells on a square grid, which is what made
        the preview blocky and the energies jump as a feature was dragged.
        """
        x = np.linspace(-10, 10, 41)
        y = np.linspace(-10, 10, 41)
        circle = CircleFeature2D(0.0, 0.0, 5.0, -0.4)

        hard, _ = build_potential_from_features([circle], (x, y))
        soft, _ = build_potential_from_features([circle], (x, y), subsample=4)

        assert set(np.unique(hard / e).round(6)) == {0.0, -0.4}
        partial = (soft / e)[(soft / e < -1e-9) & (soft / e > -0.4 + 1e-9)]
        assert partial.size > 20                # a ring of edge cells
        assert soft.min() == pytest.approx(hard.min())    # the middle is
        assert soft.max() == pytest.approx(hard.max())    # still the depth

    def test_subsampling_measures_the_area_better(self):
        """The integral of the well over the plane, against pi r^2 V0.

        Swept across one cell rather than measured at one position: the
        staircase's error is not a bias but a swing, and at a lucky radius
        and offset a centre-sampled circle can be nearly exact — which is
        the trouble with it. What sub-sampling buys is that the answer
        stops depending on where the feature happens to sit.
        """
        x = np.linspace(-10, 10, 41)
        y = np.linspace(-10, 10, 41)
        cell = (x[1] - x[0]) * (y[1] - y[0])
        exact = np.pi * 3.3 ** 2 * -0.4

        def worst(subsample):
            errors = []
            for shift in np.linspace(0.0, 0.5, 7):
                circle = CircleFeature2D(shift, 0.0, 3.3, -0.4)
                V, _ = build_potential_from_features([circle], (x, y),
                                                     subsample=subsample)
                errors.append(abs((V / e).sum() * cell - exact))
            return max(errors)

        # measured: 0.215 -> 0.022 eV nm^2 across the sweep
        assert worst(4) < worst(1) / 4

    def test_an_axis_of_one_point_is_not_averaged_through(self):
        """A preview hands the axis it has already cut in as a single sample.
        Sub-sampling that axis would smear the slice through its neighbours,
        which is the one thing a slice must not do."""
        x = np.linspace(-10, 10, 21)
        z_on = np.array([0.0])       # through the sphere's equator
        z_off = np.array([4.9])      # a whisker inside its top
        sphere = SphereFeature3D(0, 0, 0, 5.0, -0.5, 0.067)

        on, _ = build_potential_from_features([sphere], (x, x, z_on),
                                              subsample=4)
        off, _ = build_potential_from_features([sphere], (x, x, z_off),
                                               subsample=4)

        assert on.min() == pytest.approx(-0.5 * e)
        # the cap at 4.9 nm is tiny, and nothing from the equator leaks in
        assert (on < -1e-30).sum() > 10 * (off < -1e-30).sum()

    def test_sphere_contains_center(self):
        """Sphere feature should contain its own centre."""
        sph = SphereFeature3D(0, 0, 0, 5, -0.5, 0.067)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([0.0])
        assert sph.contains(X, Y, Z)[0]

    def test_sphere_excludes_outside(self):
        sph = SphereFeature3D(0, 0, 0, 5, -0.5, 0.067)
        X = np.array([6.0])
        Y = np.array([0.0])
        Z = np.array([0.0])
        assert not sph.contains(X, Y, Z)[0]


# ═══════════════════════════════════════════════════════════════════════
#  5. 3D numerical solver vs analytical (small cubic well)
# ═══════════════════════════════════════════════════════════════════════

class TestNumericalVsAnalytical:
    """Compare numerical eigensolver to analytical for a simple 3D cubic well."""

    def test_cubic_well_ground_state(self):
        """Numerical ground state of a 3D cubic well should match analytical
        to within ~2% for a 15x15x15 grid."""
        from scipy.sparse import diags, csr_matrix

        L_nm = 10.0
        meff = 0.067
        N = 15

        L_m = L_nm * 1e-9
        dx = L_m / (N + 1)
        x_nm = np.linspace(-L_nm/2 + dx*1e9, L_nm/2 - dx*1e9, N)

        Lap = lap3d_cartesian(N, N, N, dx, dx, dx,
                              bc=("dirichlet", "dirichlet", "dirichlet"))

        m = meff * m_e
        H = -(hbar**2 / (2 * m)) * Lap  # V=0 (infinite well)

        E_vals, _ = eigsh(H, k=1, sigma=-1e-20, which="LM")
        E_numerical_eV = E_vals[0] / e

        analytic = box_energies_3d_eV(L_nm, L_nm, L_nm, meff, 1)
        E_analytic_eV = analytic[0][0]

        rel_err = abs(E_numerical_eV - E_analytic_eV) / E_analytic_eV
        assert rel_err < 0.02, f"Relative error {rel_err:.4f} > 2%"


# ═══════════════════════════════════════════════════════════════════════
#  6. Cone contains — basic geometry
# ═══════════════════════════════════════════════════════════════════════

class TestConeFeature:
    def test_center_base(self):
        cone = ConeFeature3D(0, 0, 0, R_nm=5, H_nm=10, V0_eV=-0.3)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([-4.5])
        assert cone.contains(X, Y, Z)[0]

    def test_outside_radius(self):
        cone = ConeFeature3D(0, 0, 0, R_nm=5, H_nm=10, V0_eV=-0.3)
        X = np.array([6.0])
        Y = np.array([0.0])
        Z = np.array([-4.5])
        assert not cone.contains(X, Y, Z)[0]



# ═══════════════════════════════════════════════════════════════════════
#  7. Prisma N-gonal: geometria do contains()
# ═══════════════════════════════════════════════════════════════════════

class TestPrismNGonal:
    """Verify that the N-gonal prism contains() is geometrically correct."""

    def test_center_inside(self):
        """Centre of the prism must be inside."""
        pr = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                            n_sides=6)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([0.0])
        assert pr.contains(X, Y, Z)[0]

    def test_above_top_outside(self):
        """Just above the prism should be outside."""
        pr = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                            n_sides=6)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([5.1])
        assert not pr.contains(X, Y, Z)[0]

    def test_below_bottom_outside(self):
        """Just below the prism should be outside."""
        pr = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                            n_sides=4)
        X = np.array([0.0])
        Y = np.array([0.0])
        Z = np.array([-5.1])
        assert not pr.contains(X, Y, Z)[0]

    def test_uniform_cross_section(self):
        """Unlike a pyramid, the prism has the same cross-section at all z.
        A point near the edge of the polygon should be inside at both
        the bottom and the top."""
        pr = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                            n_sides=4)
        # For N=4, circumradius=5, vertex at angle 0 → (5,0)
        # Point at (3.0, 0) is well inside
        X = np.array([3.0])
        Y = np.array([0.0])
        Z_bot = np.array([-4.9])
        Z_top = np.array([4.9])
        assert pr.contains(X, Y, Z_bot)[0]
        assert pr.contains(X, Y, Z_top)[0]  # same cross-section at top

    def test_hex_vs_square_polygon(self):
        """Hexagonal prism has larger inradius than square prism at same
        circumradius, so a point between vertices can be inside hex
        but outside square."""
        pr4 = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                             n_sides=4)
        pr6 = PrismFeature3D(0, 0, 0, base_nm=10, H_nm=10, V0_eV=-0.3,
                             n_sides=6)
        # Hex inradius = 5*cos(30°) ≈ 4.33; diamond inradius = 5*cos(45°) ≈ 3.54
        angle = np.radians(45)
        r = 3.8
        X = np.array([r * np.cos(angle)])
        Y = np.array([r * np.sin(angle)])
        Z = np.array([0.0])
        assert pr6.contains(X, Y, Z)[0]       # inside hex
        assert not pr4.contains(X, Y, Z)[0]   # outside diamond

    def test_n_sides_stored_and_clamped(self):
        """n_sides should be stored; minimum is 3."""
        pr = PrismFeature3D(0, 0, 0, 10, 10, -0.3, n_sides=5)
        assert pr.n_sides == 5
        pr2 = PrismFeature3D(0, 0, 0, 10, 10, -0.3, n_sides=2)
        assert pr2.n_sides == 3


# ═══════════════════════════════════════════════════════════════════════
#  8. Overlap matrix validity
# ═══════════════════════════════════════════════════════════════════════

class TestOverlapMatrix:
    """Verify properties of the overlap matrix for a simple 3D well."""

    @pytest.fixture(scope="class")
    def eigenstates(self):
        """Solve a small 3D cubic infinite well and return (psi, E)."""
        L_nm = 10.0
        meff = 0.067
        N = 12
        L_m = L_nm * 1e-9
        dx = L_m / (N + 1)

        Lap = lap3d_cartesian(N, N, N, dx, dx, dx,
                              bc=("dirichlet", "dirichlet", "dirichlet"))
        m = meff * m_e
        H = -(hbar**2 / (2 * m)) * Lap

        k = 6
        E_vals, psi = eigsh(H, k=k, sigma=-1e-20, which="LM")
        idx = np.argsort(E_vals)
        return psi[:, idx], E_vals[idx]

    def test_diagonal_near_one(self, eigenstates):
        """Diagonal of overlap matrix should be ~1 (norm of each state)."""
        psi, _ = eigenstates
        S = compute_overlap_matrix(psi)
        np.testing.assert_allclose(np.diag(S), 1.0, atol=1e-6)

    def test_symmetry(self, eigenstates):
        """Overlap matrix should be symmetric: S[i,j] = S[j,i]."""
        psi, _ = eigenstates
        S = compute_overlap_matrix(psi)
        np.testing.assert_allclose(S, S.T, atol=1e-12)

    def test_values_in_range(self, eigenstates):
        """All overlap values should be in [0, 1]."""
        psi, _ = eigenstates
        S = compute_overlap_matrix(psi)
        assert np.all(S >= -1e-12), f"Min overlap = {S.min()}"
        assert np.all(S <= 1 + 1e-12), f"Max overlap = {S.max()}"

    def test_off_diagonal_small_non_degenerate(self, eigenstates):
        """Off-diagonal elements between non-degenerate states should be ~0."""
        psi, E = eigenstates
        S = compute_overlap_matrix(psi)
        n = S.shape[0]
        for i in range(n):
            for j in range(i + 1, n):
                # Skip near-degenerate pairs
                if abs(E[i] - E[j]) / max(abs(E[i]), 1e-30) < 0.01:
                    continue
                assert S[i, j] < 0.05, (
                    f"Overlap({i},{j}) = {S[i,j]:.4f} but states are "
                    f"non-degenerate (E={E[i]/e:.6f}, {E[j]/e:.6f} eV)")

    def test_degenerate_group_orthogonal_block(self, eigenstates):
        """Within a degenerate group, states should still be orthogonal
        (eigsh returns orthogonal vectors even for degenerate eigenvalues)."""
        psi, E = eigenstates
        S = compute_overlap_matrix(psi)
        # For a cubic box, states 1,2,3 are degenerate (2,1,1), (1,2,1), (1,1,2)
        # eigsh produces orthogonal combinations even within degenerate subspaces
        for i in range(1, min(4, S.shape[0])):
            for j in range(i + 1, min(4, S.shape[0])):
                assert S[i, j] < 0.1, (
                    f"Degenerate overlap({i},{j}) = {S[i,j]:.4f}, "
                    f"expected orthogonal from eigsh")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
