"""
The inverse designer in 0D, the ordering of the candidates, and matching by
energy differences.

The thread running through these is that the inverse problem is degenerate,
so what is tested is not "it found the right answer" but that each criterion
separates what it promises to separate — size, shape, ladder of levels.

They used to need Tk, because the search lived inside the tab that drew it.
It does not any more.
"""

import numpy as np
import pytest

from scipy.constants import hbar, m_e, e

from src.physics.designer import (
    Designer, MATCH_ABSOLUTE, MATCH_GAPS, MATCH_RATIOS, PRIORITY_GROUND,
    PRIORITY_UNIFORM, SORT_ANISOTROPY, SORT_GROUND, SORT_RRMSE,
    SORT_RRMSE_GAPS, SORT_SIZE_ASC, SORT_SIZE_DESC,
)
from src.physics.quantum_dot import (dot_energies, hw_from_length, length_from_hw,
                                     _spherical_infinite, disc_dot, parabolic_dot)
from src.physics.solution_spec import spec_from_designer


@pytest.fixture
def designer():
    """The search, seeded so a global optimisation is reproducible."""
    return Designer(seed=20260822)


def _params(**over):
    p = {'ndim': "3D", 'coords': "cartesian", 'sym': "orthorhombic",
         'meff': 0.067, 'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 30.0, 'tol': 2.0, 'maxsol': 4,
         'priority': PRIORITY_UNIFORM, 'match': MATCH_ABSOLUTE}
    p.update(over)
    return p


def _run(designer, targets, **over):
    return designer.find_solutions(_params(Et=np.array(targets), **over))


# ─── the analytical adapter ──────────────────────────────────────────────────

def test_the_spherical_ground_state_is_the_textbook_one():
    E = dot_energies("spherical", (5.0,), meff=0.067, n_levels=4)[0][0]
    exact = hbar ** 2 * np.pi ** 2 / (2 * 0.067 * m_e * (5e-9) ** 2) / e
    assert E == pytest.approx(exact, rel=1e-9)


def test_the_adapter_agrees_with_the_full_solver():
    """Same channels, same energies — the shortcut is not an approximation."""
    fast = [E for E, _ in dot_energies("spherical", (5.0,), 0.067, 20)]
    full = [lv.E_eV for lv in _spherical_infinite(5.0, 0.067, 4, 4)][:20]
    assert fast == pytest.approx(full, rel=1e-12)

    fast = [E for E, _ in dot_energies("disc", (10.0, 3.0), 0.067, 20)]
    full = [lv.E_eV for lv in disc_dot(10.0, 3.0, meff=0.067, m_max=4,
                                       n_per_channel=4, nz_max=3)][:20]
    assert fast == pytest.approx(full, rel=1e-12)

    fast = [E for E, _ in dot_energies("parabolic", (30.0, 100.0), 0.067, 20)]
    full = [lv.E_eV for lv in parabolic_dot(30.0, 100.0, n_shells=5)][:20]
    assert fast == pytest.approx(full, rel=1e-12)


def test_the_levels_come_out_sorted_and_counted():
    levels = dot_energies("spherical", (5.0,), 0.067, 7)
    assert len(levels) == 7
    energies = [E for E, _ in levels]
    assert energies == sorted(energies)
    assert all(len(qn) == 2 for _E, qn in levels)      # (n, l)


def test_the_adapter_is_fast_enough_for_an_optimizer():
    """The Bessel zeros are memoised; without that the 0D search was hopeless."""
    import timeit
    dot_energies("spherical", (5.0,), 0.067, 20)        # warm the cache
    per_call = timeit.timeit(
        lambda: dot_energies("spherical", (5.0,), 0.067, 20), number=100) / 100
    assert per_call < 5e-3


def test_an_unknown_dot_model_is_refused():
    with pytest.raises(ValueError):
        dot_energies("cubic", (5.0,), 0.067, 4)


def test_a_negative_radius_is_refused():
    with pytest.raises(ValueError):
        dot_energies("spherical", (-5.0,), 0.067, 4)


# ─── confinement length ↔ hbar*omega ─────────────────────────────────────────

def test_length_and_confinement_energy_are_inverses():
    assert length_from_hw(hw_from_length(10.0)) == pytest.approx(10.0, rel=1e-12)


def test_a_tighter_dot_confines_harder():
    assert hw_from_length(5.0) > hw_from_length(10.0)
    # E ∝ 1/l²: half the size, four times the energy.
    assert hw_from_length(5.0) == pytest.approx(4 * hw_from_length(10.0), rel=1e-12)


def test_a_zero_length_has_no_confinement_energy():
    with pytest.raises(ValueError):
        hw_from_length(0.0)
    with pytest.raises(ValueError):
        length_from_hw(-1.0)


# ─── the designer in 0D ──────────────────────────────────────────────────────

def test_the_designer_recovers_a_spherical_dot(designer):
    targets = [E for E, _ in dot_energies("spherical", (6.0,), 0.067, 3)]
    sols = _run(designer, targets, ndim="0D", coords="spherical",
                meff=0.067, Lmin=1.0, Lmax=30.0, tol=2.0)

    assert sols, "no candidate for a spectrum that came from a dot"
    best = min(sols, key=lambda s: s['RRMSE'])
    assert best['dims'][0] == pytest.approx(6.0, rel=1e-3)
    assert best['RRMSE'] < 0.01


def test_a_dot_solution_becomes_a_dot_spec():
    for coords, model in [("spherical", "dot_spherical"),
                          ("disc", "dot_disc"),
                          ("parabolic", "dot_parabolic")]:
        sol = {'dims': (5.0, 3.0), 'ndim': "0D", 'coords': coords,
               'matches': [], 'RRMSE': 0.0}
        assert spec_from_designer(sol, 0.067, None).model == model


def test_the_parabolic_search_runs_in_nanometres(designer):
    """The search box is in nm; hbar*omega is a result, not the user's guess."""
    p = _params(ndim="0D", coords="parabolic", meff=0.067)
    dims = designer.params_to_dims([10.0, 5.0], p)
    assert dims[0] == pytest.approx(hw_from_length(10.0, 0.067))
    assert dims[1] == pytest.approx(hw_from_length(5.0, 0.067))
    assert dims[1] > dims[0]              # tighter in z = larger hbar*omega


def test_zero_d_asks_for_the_dimensions_its_model_has(designer):
    p = _params(ndim="0D", coords="spherical")
    assert len(designer.bounds(p)) == 1              # R only
    p['coords'] = "disc"
    assert len(designer.bounds(p)) == 2              # R and L_z
    p['fixed']['d1'] = 8.0
    assert len(designer.bounds(p)) == 1              # a pinned R leaves the search


# ─── ordering ────────────────────────────────────────────────────────────────

def _sol(dims, rrmse=1.0, ndim="3D", coords="cartesian", Ec=None, dE=None,
         meff=0.067):
    return {'dims': dims, 'RRMSE': rrmse, 'RRMSE_dE': rrmse if dE is None else dE,
            'RRMSE_abs': rrmse, 'ndim': ndim, 'coords': coords, 'sym': "",
            'meff': meff, 'matches': [], 'offset': 0.0,
            'Ec': Ec or [(0.1, (1,))]}


def test_the_confinement_size_is_the_geometric_mean(designer):
    # 8x2x2 and 4x4x2 have the same volume: the same effective size.
    assert designer.confinement_size(_sol((8, 2, 2))) == pytest.approx(
        designer.confinement_size(_sol((4, 4, 2))))
    assert designer.confinement_size(_sol((5, 5, 5))) == pytest.approx(5.0)


def test_a_parabolic_dot_is_sized_by_length_not_by_energy(designer):
    """A high hbar*omega is a small dot; ordering by the raw number would
    invert the list."""
    tight = _sol((hw_from_length(3.0), hw_from_length(3.0)),
                 ndim="0D", coords="parabolic")
    loose = _sol((hw_from_length(20.0), hw_from_length(20.0)),
                 ndim="0D", coords="parabolic")
    assert designer.confinement_size(tight) == pytest.approx(3.0, rel=1e-9)
    assert designer.confinement_size(tight) < designer.confinement_size(loose)


def test_anisotropy_is_one_for_a_cube(designer):
    assert designer.anisotropy(_sol((5, 5, 5))) == pytest.approx(1.0)
    assert designer.anisotropy(_sol((10, 5, 2))) == pytest.approx(5.0)


def test_the_ground_state_key_reads_the_lowest_level(designer):
    assert designer.ground_state(
        _sol((5,), Ec=[(0.3, (2,)), (0.1, (1,)), (0.7, (3,))])) == 0.1


def test_each_sort_mode_orders_by_its_own_criterion(designer):
    solutions = [
        _sol((9, 9, 9), rrmse=3.0, Ec=[(0.05, (1,))]),      # large, isotropic
        _sol((2, 2, 8), rrmse=1.0, Ec=[(0.40, (1,))]),      # small, elongated
        _sol((6, 6, 6), rrmse=2.0, Ec=[(0.12, (1,))]),
    ]

    by_error = designer.sort_solutions(solutions, SORT_RRMSE)
    assert [s['RRMSE'] for s in by_error] == [1.0, 2.0, 3.0]

    smallest = designer.sort_solutions(solutions, SORT_SIZE_ASC)
    sizes = [designer.confinement_size(s) for s in smallest]
    assert sizes == sorted(sizes)

    largest = designer.sort_solutions(solutions, SORT_SIZE_DESC)
    sizes = [designer.confinement_size(s) for s in largest]
    assert sizes == sorted(sizes, reverse=True)

    symmetric = designer.sort_solutions(solutions, SORT_ANISOTROPY)
    assert designer.anisotropy(symmetric[0]) == pytest.approx(1.0)

    lowest = designer.sort_solutions(solutions, SORT_GROUND)
    assert designer.ground_state(lowest[0]) == 0.05


def test_a_size_tie_falls_back_to_the_fit(designer):
    """Two geometries of the same size: which describes the energies better."""
    solutions = [_sol((5, 5, 5), rrmse=4.0), _sol((5, 5, 5), rrmse=0.5)]
    assert designer.sort_solutions(solutions, SORT_SIZE_ASC)[0]['RRMSE'] == 0.5


def test_sorting_by_spacing_error_uses_the_gap_column(designer):
    solutions = [_sol((5,), rrmse=0.1, dE=9.0), _sol((7,), rrmse=5.0, dE=0.2)]
    assert designer.sort_solutions(solutions, SORT_RRMSE_GAPS)[0]['dims'] == (7,)


def test_resorting_does_not_need_a_new_search(designer):
    """Reordering hands back the same candidate objects — the search is not
    repeated to change a combo box."""
    solutions = [_sol((9, 9, 9), rrmse=3.0), _sol((2, 2, 2), rrmse=1.0)]
    resorted = designer.sort_solutions(solutions, SORT_SIZE_ASC)
    assert set(map(id, resorted)) == set(map(id, solutions))


def test_an_empty_list_survives_a_sort(designer):
    assert designer.sort_solutions([], SORT_SIZE_DESC) == []


def test_a_paired_run_sorts_by_the_pair_error(designer):
    """A good pair is not the one with the smallest electron error."""
    solutions = [dict(_sol((5,), rrmse=0.1), pair_score=9.0),
                 dict(_sol((7,), rrmse=5.0), pair_score=0.2)]
    assert designer.sort_solutions(solutions, SORT_RRMSE,
                                   paired=True)[0]['dims'] == (7,)
    assert designer.sort_solutions(solutions, SORT_RRMSE)[0]['dims'] == (5,)


# ─── matching by differences ─────────────────────────────────────────────────

def _matches(computed, targets):
    return [{'target_E': t, 'computed_E': c, 'qn': (1,), 'idx': i}
            for i, (t, c) in enumerate(zip(targets, computed))]


def test_a_perfect_ladder_has_no_spacing_error(designer):
    targets = [0.1, 0.2, 0.4]
    assert designer.gap_rrmse(_matches(targets, targets),
                              targets) == pytest.approx(0.0)


def test_a_rigid_shift_leaves_the_spacings_untouched(designer):
    """The whole point of the ΔE mode: the origin does not enter the sum."""
    targets = [0.1, 0.2, 0.4]
    shifted = [t + 0.05 for t in targets]
    assert designer.gap_rrmse(_matches(shifted, targets),
                              targets) == pytest.approx(0.0)
    # in absolute energy the same shift is an enormous error
    assert designer.abs_rrmse(_matches(shifted, targets), targets) > 10


def test_ratios_ignore_the_overall_scale(designer):
    targets = [0.1, 0.2, 0.4]
    doubled = [2 * t for t in targets]
    assert designer.gap_rrmse(_matches(doubled, targets), targets,
                              ratios=True) == pytest.approx(0.0)
    # unnormalised, doubling the scale is a 100% error in the spacings
    assert designer.gap_rrmse(_matches(doubled, targets), targets) > 50


def test_a_single_target_has_no_spacing_to_compare(designer):
    assert designer.gap_rrmse(_matches([0.1], [0.1]), [0.1]) == 0.0


def test_the_ground_state_priority_does_not_blank_the_spacings(designer):
    """w = [1,0,0] would zero every ΔE weight; the criterion falls back to
    uniform rather than reporting a perfect fit."""
    targets = [0.1, 0.2, 0.4]
    wrong = [0.1, 0.25, 0.4]
    err = designer.gap_rrmse(_matches(wrong, targets), targets,
                             priority=PRIORITY_GROUND)
    assert err > 0


def test_matching_by_gaps_finds_the_shift(designer):
    """A spectrum measured from E_F returns to the model's frame."""
    Et = np.array([E for E, _ in dot_energies("spherical", (6.0,), 0.067, 3)])
    offset = 0.150
    Ec = [(E + offset, qn) for E, qn in dot_energies("spherical", (6.0,), 0.067, 12)]

    p = {'match': MATCH_GAPS, 'priority': PRIORITY_UNIFORM}
    matches, found, err = designer.match_and_score(Ec, Et, p)
    assert found == pytest.approx(offset, rel=1e-6)
    assert err == pytest.approx(0.0, abs=1e-6)
    assert [m['computed_E'] for m in matches] == pytest.approx(list(Et), rel=1e-6)


def test_absolute_matching_leaves_the_origin_alone(designer):
    Et = np.array([0.1, 0.2])
    Ec = [(0.1, (1,)), (0.2, (2,))]
    _m, offset, err = designer.match_and_score(
        Ec, Et, {'match': MATCH_ABSOLUTE, 'priority': PRIORITY_UNIFORM})
    assert offset == 0.0
    assert err == pytest.approx(0.0)


def test_the_spec_moves_targets_into_the_model_frame():
    """If the designer shifted the origin, the receiver gets the same shift."""
    sol = {'dims': (10.0,), 'ndim': "1D", 'coords': "cartesian", 'RRMSE': 0.0,
           'offset': -0.120, 'match': MATCH_GAPS,
           'matches': [{'target_E': 0.176, 'computed_E': 0.176, 'qn': (1,)}]}
    spec = spec_from_designer(sol, 0.067, [0.176])
    assert spec.targets_eV[0] == pytest.approx(0.056)     # 176 − 120 meV
    assert spec.computed_eV[0] == pytest.approx(0.056)    # the same frame
    assert spec.extras["offset_eV"] == pytest.approx(-0.120)


def test_without_a_shift_the_targets_are_untouched():
    sol = {'dims': (10.0,), 'ndim': "1D", 'coords': "cartesian", 'RRMSE': 0.0,
           'matches': []}
    assert spec_from_designer(sol, 0.067, [0.1, 0.2]).targets_eV == (0.1, 0.2)


def test_a_shifted_spectrum_is_only_solvable_by_gaps(designer):
    """The real case: energies read from E_F, the well counted from its floor."""
    from src.physics.analytical import box_energies_1d_eV
    truth = [E for E, _ in box_energies_1d_eV(10.0, 0.067, 4)][:4]
    targets = [E + 0.120 for E in truth]

    absolute = _run(designer, targets, ndim="1D", coords="cartesian",
                    meff=0.067, tol=8.0, maxsol=4, match=MATCH_ABSOLUTE)
    assert all(abs(s['dims'][0] - 10.0) > 1.0 for s in absolute)

    by_gaps = _run(designer, targets, ndim="1D", coords="cartesian",
                   meff=0.067, tol=8.0, maxsol=4, match=MATCH_GAPS)
    # Loose candidates fit inside the tolerance with a different alignment;
    # the claim is about the ones that actually reproduce the ladder.
    exact = [s for s in by_gaps if s['RRMSE_dE'] < 0.01]
    assert exact, "the ΔE mode found no exact ladder"
    for s in exact:
        # The origin returns to the bottom of the well, whichever candidate.
        assert s['offset'] == pytest.approx(-0.120, abs=1e-6)
        # The candidates are the usual aliases: a well k times larger
        # reproduces the same ladder with levels n, 2n, 3n… Which one is real
        # only a numerical simulation decides — not this test.
        ratio = s['dims'][0] / 10.0
        assert ratio == pytest.approx(round(ratio), abs=1e-3)
