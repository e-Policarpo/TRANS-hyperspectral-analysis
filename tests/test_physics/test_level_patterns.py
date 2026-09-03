"""Tests for src.physics.level_patterns.

What is being defended here is a claim about physics, not about an
implementation: that E_n / E_1 is a fingerprint of *shape and dimensionality
alone*. So the oracles are closed form or an independent brute force — the
integer sums n^2, nx^2+ny^2, nx^2+ny^2+nz^2 enumerated directly, and the
Bessel zeros taken from ``scipy.special.jn_zeros`` rather than from the
module under test. Nothing here asserts that a particular helper was called.

Four failure modes drive most of the file, all of the quiet kind that returns
a plausible-looking ladder rather than raising:

* **A joules/eV mix-up is invisible.** ``analytical.box_energies_1d`` and
  ``box_energies_3d`` return joules while their siblings return eV, and since
  only ratios are taken the prefactor cancels either way. It is caught here
  instead by pinning the ratios against integer arithmetic.
* **Under-counted degeneracy.** ``disk_energies`` lists ``m >= 0`` only, so
  every ``m > 0`` entry stands for a +/-m pair; counting entries would halve
  every angular level's predicted step height.
* **A truncated degenerate group.** Asking for k levels and generating
  exactly k raw states can cut a degenerate group in half — same energy,
  wrong weight. Pinned by checking every truncation against the brute-force
  ladder, not against the module's own longest answer, since too small a raw
  budget would corrupt both identically.
* **A silently reordered ladder.** ``disk_energies`` stops at ``m = 7``, and
  from the 18th distinct level onward its ordering is simply wrong. The
  ceiling that refuses rather than reorders is tested, and so is the fact
  that the ceiling sits below the real divergence.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import dataclasses
import itertools
from collections import Counter
from functools import lru_cache

import numpy as np
import pytest
from scipy.special import jn_zeros

from src.physics.analytical import (
    box_energies_1d_eV,
    box_energies_2d_eV,
    box_energies_3d_eV,
    disk_energies,
)
from src.physics.level_patterns import (
    CONFINED_DIMS,
    DEFAULT_LEVELS,
    MAX_LEVELS,
    PATTERN_LABELS,
    PATTERN_NAMES,
    LevelPattern,
    all_patterns,
    expected_step_heights,
    pattern,
)
from src.physics.quantum_dot import _spherical_jn_zeros


# ---------------------------------------------------------------------------
# Independent oracles -- integer arithmetic and scipy, never the module itself.
# Memoised: they are pure, and the sphere oracle root-finds 400 Bessel zeros.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _box_ladder(dims: int, n_max: int = 40, count: int = 20):
    """Distinct (ratio, state count) of a unit hyper-cube, by brute force."""
    tally: Counter = Counter()
    for qn in itertools.product(range(1, n_max + 1), repeat=dims):
        tally[sum(n * n for n in qn)] += 1
    keys = sorted(tally)[:count]
    return [(k / keys[0], tally[k]) for k in keys]


@lru_cache(maxsize=None)
def _disc_ladder(m_max: int = 25, count: int = 20):
    """Distinct (ratio, state count, (m, n)) of a unit disc, from jn_zeros."""
    states = []
    for m in range(m_max):
        for n, z in enumerate(jn_zeros(m, m_max), start=1):
            states.append((z * z, (m, n), 1 if m == 0 else 2))
    states.sort()
    ground = states[0][0]
    return [(e / ground, w, qn) for e, qn, w in states[:count]]


@lru_cache(maxsize=None)
def _sphere_ladder(l_max: int = 20, count: int = 20):
    """Distinct (ratio, state count, (n, l)) of a unit ball, from j_l zeros."""
    states = []
    for l in range(l_max):
        for n, z in enumerate(_spherical_jn_zeros(l, l_max), start=1):
            states.append((z * z, (n, l), 2 * l + 1))
    states.sort()
    ground = states[0][0]
    return [(e / ground, w, qn) for e, qn, w in states[:count]]


def _fake(degeneracies, name="fake"):
    """A hand-built pattern, for exercising paths the real five cannot reach."""
    n = len(degeneracies)
    return LevelPattern(
        name=name,
        label="Fake",
        confined_dims=1,
        ratios=tuple(float(i + 1) for i in range(n)),
        degeneracies=tuple(degeneracies),
        quantum_numbers=tuple((i + 1,) for i in range(n)),
    )


# ---------------------------------------------------------------------------
# The documented anchors
# ---------------------------------------------------------------------------

#: E2/E1 as written in the specification, to three decimals.
SPEC_E2_OVER_E1 = {
    "box_1d": 4.000,
    "box_2d_square": 2.500,
    "disc_2d": 2.538,
    "box_3d_cube": 2.000,
    "sphere_3d": 2.046,
}


@pytest.mark.parametrize("name, expected", sorted(SPEC_E2_OVER_E1.items()))
def test_the_first_ratio_is_the_documented_fingerprint(name, expected):
    """The five numbers the module exists to produce, to the spec's precision."""
    assert pattern(name, 2).ratios[1] == pytest.approx(expected, abs=1e-3)


def test_the_disc_and_sphere_anchors_to_full_precision():
    """Regression: 2.538 is a truncation of 2.53873, not a value to match tightly."""
    assert pattern("disc_2d", 2).ratios[1] == pytest.approx(2.5387339, rel=1e-6)
    assert pattern("sphere_3d", 2).ratios[1] == pytest.approx(2.0457493, rel=1e-6)


def test_the_fingerprints_separate_the_dimensionalities():
    """The whole point: 4.00 / 2.50 / 2.00 are far apart on any real spectrum."""
    ratios = {p.name: p.ratios[1] for p in all_patterns(2)}
    assert ratios["box_1d"] > ratios["box_2d_square"] > ratios["box_3d_cube"]
    # k_B*T at 94 K is ~8 meV; on a 0.1 eV ground state these differ by whole
    # tenths of an eV, so broadening cannot confuse them.
    assert ratios["box_2d_square"] - ratios["box_3d_cube"] > 0.4


@pytest.mark.parametrize("name", PATTERN_NAMES)
def test_a_ladder_is_normalised_and_strictly_increasing(name):
    p = pattern(name, DEFAULT_LEVELS)
    assert p.ratios[0] == 1.0            # exact, not approximate
    assert np.all(np.diff(p.ratios) > 0)
    assert len(p.ratios) == len(p.degeneracies) == len(p.quantum_numbers)
    assert p.n_levels == DEFAULT_LEVELS


# ---------------------------------------------------------------------------
# The level sequences, against integer arithmetic
# ---------------------------------------------------------------------------

def test_the_line_is_n_squared_and_never_degenerate():
    p = pattern("box_1d", 8)
    np.testing.assert_allclose(p.ratios, [n * n for n in range(1, 9)], rtol=1e-12)
    assert p.degeneracies == (1,) * 8
    assert p.quantum_numbers[:3] == ((1,), (2,), (3,))


def test_the_square_groups_its_degenerate_pairs():
    """1, 2.5, 4, 5 with weights 1, 2, 1, 2 -- (1,2) and (2,1) are one level."""
    p = pattern("box_2d_square", 4)
    np.testing.assert_allclose(p.ratios, [1.0, 2.5, 4.0, 5.0], rtol=1e-12)
    assert p.degeneracies == (1, 2, 1, 2)


def test_the_cube_reproduces_the_textbook_first_five():
    """3, 6, 9, 11, 12 over 3 -- and 3, 3, 3 states in the middle."""
    p = pattern("box_3d_cube", 5)
    np.testing.assert_allclose(p.ratios, [1.0, 2.0, 3.0, 11 / 3, 4.0], rtol=1e-12)
    assert p.degeneracies == (1, 3, 3, 3, 1)


@pytest.mark.parametrize("name, dims", [("box_1d", 1),
                                        ("box_2d_square", 2),
                                        ("box_3d_cube", 3)])
def test_a_box_ladder_matches_a_brute_force_enumeration(name, dims):
    """Both the energies and the state counts, for every level offered."""
    p = pattern(name, MAX_LEVELS)
    truth = _box_ladder(dims, count=MAX_LEVELS)
    np.testing.assert_allclose(p.ratios, [r for r, _ in truth], rtol=1e-12)
    assert p.degeneracies == tuple(w for _, w in truth)


def test_the_disc_is_the_squared_zeros_of_the_bessel_functions():
    p = pattern("disc_2d", MAX_LEVELS)
    truth = _disc_ladder(count=MAX_LEVELS)
    np.testing.assert_allclose(p.ratios, [r for r, _, _ in truth], rtol=1e-9)
    assert p.quantum_numbers == tuple(qn for _, _, qn in truth)


def test_the_sphere_is_the_squared_zeros_of_the_spherical_bessel_functions():
    p = pattern("sphere_3d", MAX_LEVELS)
    truth = _sphere_ladder(count=MAX_LEVELS)
    np.testing.assert_allclose(p.ratios, [r for r, _, _ in truth], rtol=1e-9)
    assert p.quantum_numbers == tuple(qn for _, _, qn in truth)


def test_the_spherical_bessel_zeros_are_recovered_from_the_ratios():
    """3.1416, 4.4934, 5.7635, 6.2832 -- the ground zero is pi, so a ratio's
    square root times pi is the next zero, whatever the module did internally."""
    ratios = pattern("sphere_3d", 4).ratios
    zeros = [np.sqrt(r) * np.pi for r in ratios]
    np.testing.assert_allclose(zeros, [3.14159, 4.49341, 5.76346, 6.28319],
                               rtol=1e-5)


# ---------------------------------------------------------------------------
# Degeneracy accounting -- the worst of the quiet failure modes
# ---------------------------------------------------------------------------

def test_an_angular_disc_level_counts_two_states_not_one():
    """Regression: disk_energies lists m >= 0 only, so each m > 0 entry stands
    for the +/-m pair. Counting entries would halve every angular step."""
    p = pattern("disc_2d", 8)
    expected = tuple(1 if qn[0] == 0 else 2 for qn in p.quantum_numbers)
    assert p.degeneracies == expected
    assert 2 in p.degeneracies          # the trap is only live if pairs exist


def test_a_spherical_shell_counts_two_l_plus_one_states():
    p = pattern("sphere_3d", 8)
    expected = tuple(2 * qn[1] + 1 for qn in p.quantum_numbers)
    assert p.degeneracies == expected
    assert p.degeneracies[:5] == (1, 3, 5, 1, 7)   # 1s 1p 1d 2s 1f


def test_the_cube_level_at_ratio_nine_holds_four_states():
    """27 = 25+1+1 three ways and 9+9+9 one way. A ladder that stopped
    generating raw states too early reports three here and looks reasonable."""
    p = pattern("box_3d_cube", MAX_LEVELS)
    index = int(np.argmin(np.abs(np.asarray(p.ratios) - 9.0)))
    assert p.ratios[index] == pytest.approx(9.0, rel=1e-12)
    assert p.degeneracies[index] == 4


def test_the_cube_has_a_six_fold_level_before_the_ladder_ends():
    p = pattern("box_3d_cube", MAX_LEVELS)
    assert 6 in p.degeneracies


@pytest.mark.parametrize("name, dims", [("box_1d", 1),
                                        ("box_2d_square", 2),
                                        ("box_3d_cube", 3)])
def test_a_truncated_box_ladder_is_still_complete(name, dims):
    """Asking for k levels may not cut the k-th degenerate group in half.

    Checked against the brute-force enumeration at *every* k rather than
    against the module's own longest answer, since a shortfall in the raw
    state budget would corrupt both identically.
    """
    truth = _box_ladder(dims, count=MAX_LEVELS)
    for k in range(1, MAX_LEVELS + 1):
        p = pattern(name, k)
        np.testing.assert_allclose(p.ratios, [r for r, _ in truth[:k]],
                                   rtol=1e-12, err_msg=f"{name} at k={k}")
        assert p.degeneracies == tuple(w for _, w in truth[:k]), (name, k)


def test_a_truncated_disc_ladder_is_still_complete():
    truth = _disc_ladder(count=MAX_LEVELS)
    for k in range(1, MAX_LEVELS + 1):
        p = pattern("disc_2d", k)
        assert p.degeneracies == tuple(w for _, w, _ in truth[:k]), k
        assert p.quantum_numbers == tuple(qn for _, _, qn in truth[:k]), k


@pytest.mark.parametrize("k", [1, 4, 8])
def test_a_truncated_sphere_ladder_is_still_complete(k):
    """Same property for the sphere, sampled rather than swept -- its root
    search is the one expensive call in the module."""
    truth = _sphere_ladder(count=MAX_LEVELS)
    p = pattern("sphere_3d", k)
    np.testing.assert_allclose(p.ratios, [r for r, _, _ in truth[:k]], rtol=1e-9)
    assert p.degeneracies == tuple(w for _, w, _ in truth[:k])


# ---------------------------------------------------------------------------
# The key idea: independent of size, of mass, and of broadening
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("L, meff", [(1.0, 1.0), (3.7, 0.067), (42.0, 0.45)])
def test_the_line_fingerprint_ignores_size_and_mass(L, meff):
    """The single most important property: the same shape at any size, on any
    material, lands on the same list."""
    energies = [e for e, _ in box_energies_1d_eV(L, meff, 6)]
    np.testing.assert_allclose([e / energies[0] for e in energies],
                               pattern("box_1d", 6).ratios, rtol=1e-9)


@pytest.mark.parametrize("L, meff", [(2.5, 0.067), (11.0, 0.19)])
def test_the_square_and_cube_fingerprints_ignore_size_and_mass(L, meff):
    flat2 = [e for e, _ in box_energies_2d_eV(L, L, meff, 12)]
    flat3 = [e for e, _ in box_energies_3d_eV(L, L, L, meff, 20)]
    for flat, name in ((flat2, "box_2d_square"), (flat3, "box_3d_cube")):
        distinct = []
        for e in flat:
            if not distinct or abs(e - distinct[-1]) > 1e-9 * abs(distinct[-1]):
                distinct.append(e)
        got = [e / distinct[0] for e in distinct[:4]]
        np.testing.assert_allclose(got, pattern(name, 4).ratios, rtol=1e-9), name


@pytest.mark.parametrize("R, meff", [(1.0, 1.0), (6.3, 0.067)])
def test_the_disc_fingerprint_ignores_size_and_mass(R, meff):
    energies = [e for e, _ in disk_energies(R, meff, 6)]
    np.testing.assert_allclose([e / energies[0] for e in energies],
                               pattern("disc_2d", 6).ratios, rtol=1e-9)


def test_a_symmetric_broadening_kernel_leaves_the_fingerprint_alone():
    """The claim that makes this usable at 94 K: convolution with a symmetric
    kernel widens a peak without moving its centroid, so the ratios survive."""
    p = pattern("box_1d", 4)
    e1 = 0.05                                    # eV, a plausible ground state
    centres = np.asarray(p.ratios) * e1
    grid = np.linspace(0.0, 1.0, 20001)
    sigma = 8.1e-3                               # k_B * T at 94 K, in eV
    spectrum = np.zeros_like(grid)
    for centre, weight in zip(centres, p.degeneracies):
        spectrum += weight * np.exp(-0.5 * ((grid - centre) / sigma) ** 2)

    recovered = []
    for centre in centres:
        window = np.abs(grid - centre) < 5 * sigma
        w = spectrum[window]
        recovered.append(float(np.sum(grid[window] * w) / np.sum(w)))

    got = np.asarray(recovered) / recovered[0]
    # A 5-sigma window truncates the Gaussian tails symmetrically, so the
    # residual is numerical rather than physical.
    np.testing.assert_allclose(got, p.ratios, rtol=1e-4)


# ---------------------------------------------------------------------------
# Guards: refuse rather than answer badly
# ---------------------------------------------------------------------------

def test_an_unknown_pattern_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="name must be one of"):
        pattern("nope")
    with pytest.raises(ValueError, match=r"got 'nope'"):
        pattern("nope")


@pytest.mark.parametrize("n_levels", [0, -1, -20])
def test_a_non_positive_level_count_is_refused(n_levels):
    with pytest.raises(ValueError, match="n_levels must be between"):
        pattern("box_1d", n_levels)


@pytest.mark.parametrize("n_levels", [MAX_LEVELS + 1, 100])
def test_asking_past_the_ceiling_is_refused(n_levels):
    """Above the ceiling the disc's Bessel grid reorders the ladder, and a
    wrong fingerprint is worse than a refused one."""
    with pytest.raises(ValueError, match="n_levels must be between"):
        pattern("disc_2d", n_levels)
    with pytest.raises(ValueError, match="n_levels must be between"):
        pattern("box_1d", n_levels)


def test_the_ceiling_sits_below_where_the_bessel_grid_actually_fails():
    """Documents why MAX_LEVELS is 16: disk_energies' grid stops at m = 7, so
    it misses (8, 1) and everything from the 18th distinct level onward is
    misordered. The ceiling must stay strictly under that."""
    truth = [qn for _, _, qn in _disc_ladder(count=20)]
    got = [tuple(qn) for _, qn in disk_energies(1.0, 1.0, 20)]
    first_bad = next(i for i, (a, b) in enumerate(zip(truth, got)) if a != b)
    assert first_bad == 17                       # the 18th distinct level
    assert MAX_LEVELS < first_bad + 1
    # And the levels the module does offer are all on the good side of it.
    assert pattern("disc_2d", MAX_LEVELS).quantum_numbers == tuple(truth[:MAX_LEVELS])


# ---------------------------------------------------------------------------
# expected_step_heights
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", PATTERN_NAMES)
def test_step_heights_are_normalised_to_the_ground_step(name):
    p = pattern(name, DEFAULT_LEVELS)
    heights = expected_step_heights(p)
    assert heights[0] == 1.0
    assert len(heights) == len(p.degeneracies)
    np.testing.assert_allclose(heights, np.asarray(p.degeneracies, dtype=float)
                               / p.degeneracies[0], rtol=1e-12)


def test_the_cube_predicts_a_triple_second_step_and_the_line_does_not():
    assert expected_step_heights(pattern("box_3d_cube", 5)) == (1.0, 3.0, 3.0, 3.0, 1.0)
    assert expected_step_heights(pattern("box_1d", 5)) == (1.0,) * 5


def test_spin_cancels_out_of_the_step_heights():
    """Doubling every degeneracy for spin leaves the relative weights alone --
    which is why the module leaves spin out entirely."""
    p = pattern("sphere_3d", 5)
    doubled = _fake([2 * d for d in p.degeneracies])
    assert expected_step_heights(doubled) == expected_step_heights(p)


def test_an_unusable_ground_degeneracy_gives_nan_not_zero():
    """NaN, never 0.0: a zero step height would be read as 'no states here',
    which is a measurement, not a missing answer."""
    heights = expected_step_heights(_fake([0, 3, 5]))
    assert len(heights) == 3
    assert all(np.isnan(h) for h in heights)


def test_a_negative_ground_degeneracy_also_gives_nan():
    assert all(np.isnan(h) for h in expected_step_heights(_fake([-2, 4])))


def test_an_empty_pattern_gives_an_empty_result():
    assert expected_step_heights(_fake([])) == ()


# ---------------------------------------------------------------------------
# The record and the catalogue
# ---------------------------------------------------------------------------

def test_all_patterns_returns_every_name_in_order():
    got = all_patterns(4)
    assert tuple(p.name for p in got) == PATTERN_NAMES
    assert all(p.n_levels == 4 for p in got)


@pytest.mark.parametrize("name", PATTERN_NAMES)
def test_a_pattern_carries_its_label_and_its_confined_directions(name):
    p = pattern(name, 3)
    assert p.label == PATTERN_LABELS[name]
    assert p.confined_dims == CONFINED_DIMS[name]
    assert p.confined_dims in (1, 2, 3)


def test_confined_dims_counts_directions_not_quantum_numbers():
    """A disc confines in two directions and a ball in three, even though both
    are labelled by two quantum numbers."""
    assert pattern("disc_2d", 1).confined_dims == 2
    assert pattern("sphere_3d", 1).confined_dims == 3
    assert pattern("box_3d_cube", 1).confined_dims == 3


def test_a_pattern_cannot_be_mutated_by_a_caller():
    """It is memoised and shared, so a mutable one would corrupt every user."""
    p = pattern("box_1d", 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.ratios = (1.0, 2.0, 3.0)
    assert isinstance(p.ratios, tuple)
    assert isinstance(p.degeneracies, tuple)


def test_the_same_request_returns_the_same_memoised_object():
    assert pattern("box_2d_square", 5) is pattern("box_2d_square", 5)
