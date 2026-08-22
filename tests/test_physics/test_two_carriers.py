"""
The designer with two carriers.

The same well confines electrons and holes with different masses: two
searches, and what ties them together is the geometry. A single carrier is
still the normal path — this must not have changed what already worked.

The orchestration these used to drive through the Tk tab (filling the entry
fields, the Find button) now lives in the tool that will host the search;
what is tested here is the physics underneath it, which is where the claims
actually were.
"""

import numpy as np
import pytest

from src.physics.analytical import box_energies_1d_eV
from src.physics.branches import DidvCurve, DidvPeaks, split_peaks
from src.physics.designer import (
    Designer, MATCH_ABSOLUTE, MATCH_GAPS, PRIORITY_UNIFORM, parse_energies,
    parse_masses,
)
from src.physics.pairing import (band_edges, edges_from_pair,
                                 edges_from_solutions, pair_candidates,
                                 refine_boundaries)


@pytest.fixture
def designer():
    return Designer(seed=20260822)


def _levels(L_nm, meff, n=3):
    return [E for E, _ in box_energies_1d_eV(L_nm, meff, n)][:n]


def _params(**over):
    p = {'ndim': "1D", 'coords': "cartesian", 'sym': "",
         'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 12.0, 'tol': 2.0, 'maxsol': 2,
         'priority': PRIORITY_UNIFORM, 'match': MATCH_ABSOLUTE,
         'meff': 0.067, 'Et': np.array([0.1])}
    p.update(over)
    return p


def _search(designer, targets, meffs, carrier='e', **over):
    """One carrier's candidates, the way the tool will ask for them."""
    return designer.search_carrier(
        _params(**over),
        {'carrier': carrier, 'label': 'electron' if carrier == 'e' else 'hole',
         'Et': np.array(targets), 'meffs': list(meffs)})


# ─── one carrier is unchanged ────────────────────────────────────────────────

def test_a_single_carrier_search_is_unchanged(designer):
    sols = _search(designer, _levels(8.0, 0.067), [0.067])

    assert sols
    best = min(sols, key=lambda s: s["RRMSE"])
    assert best["dims"][0] == pytest.approx(8.0, rel=1e-3)
    assert best["meff"] == pytest.approx(0.067)
    assert best["carrier"] == "e"


def test_holes_alone_use_the_hole_mass(designer):
    """In hole-only mode the one list of targets is searched with m*_h."""
    sols = _search(designer, _levels(8.0, 0.45), [0.45], carrier='h')

    assert sols
    best = min(sols, key=lambda s: s["RRMSE"])
    assert best["dims"][0] == pytest.approx(8.0, rel=1e-3)
    assert best["meff"] == pytest.approx(0.45)
    assert best["carrier"] == "h"


# ─── two carriers ────────────────────────────────────────────────────────────

def _run_pair(designer, L_e=8.0, L_h=8.0, m_e=(0.067,), m_h=(0.45,), tol=1.0):
    electrons = _search(designer, _levels(L_e, m_e[0]), m_e, carrier='e')
    holes = _search(designer, _levels(L_h, m_h[0]), m_h, carrier='h')
    return pair_candidates(electrons, holes, tol_nm=tol)


def test_the_two_searches_are_paired_by_geometry(designer):
    pairs = _run_pair(designer)
    assert pairs
    best = pairs[0]
    assert best["electron"]["dims"][0] == pytest.approx(
        best["hole"]["dims"][0], abs=0.05)
    assert best["electron"]["meff"] == pytest.approx(0.067)
    assert best["hole"]["meff"] == pytest.approx(0.45)
    assert best["score"] < 1.0


def test_geometries_need_not_agree_exactly(designer):
    """7.9 nm for the electron and 8.1 for the hole are the same well,
    within the tolerance."""
    pairs = _run_pair(designer, L_e=7.9, L_h=8.1, tol=0.5)
    assert pairs
    best = pairs[0]
    assert 0.0 < best["mismatch_nm"] <= 0.5
    assert best["size_nm"] == pytest.approx(8.0, abs=0.2)


def test_a_tight_tolerance_refuses_the_pair(designer):
    """With 0.01 nm of slack, 7.9 and 8.1 stop being the same well."""
    pairs = _run_pair(designer, L_e=7.9, L_h=8.1, tol=0.01)
    assert pairs == []


def test_a_refused_pair_is_not_a_failed_search(designer):
    """Both sides existed; it is the pair that did not. The distinction is
    what the message to the user has to keep."""
    electrons = _search(designer, _levels(7.9, 0.067), [0.067])
    holes = _search(designer, _levels(8.1, 0.45), [0.45], carrier='h')
    assert electrons and holes
    assert pair_candidates(electrons, holes, tol_nm=0.01) == []


def test_the_pair_error_needs_all_three_terms_small(designer):
    """A pair that fits both carriers but disagrees on the geometry scores
    worse than one that agrees."""
    pairs = _run_pair(designer, L_e=8.0, L_h=8.0, tol=2.0)
    spread = _run_pair(designer, L_e=7.5, L_h=8.5, tol=2.0)
    assert pairs and spread
    assert pairs[0]["score"] < spread[0]["score"]


# ─── several effective masses ────────────────────────────────────────────────

def test_a_list_of_masses_runs_one_search_each(designer):
    """The mass is the least known parameter: try several at once."""
    sols = _search(designer, _levels(8.0, 0.067), [0.050, 0.067, 0.090],
                   maxsol=12)

    masses = {round(s["meff"], 4) for s in sols}
    assert masses == {0.05, 0.067, 0.09}
    # E ∝ 1/(m L²): for the same energies, a larger mass asks for a SMALLER
    # well. Among each mass's aliases the smallest well is the primary one.
    by_mass = {}
    for s in sols:
        m = round(s["meff"], 4)
        by_mass[m] = min(by_mass.get(m, float("inf")), s["dims"][0])
    assert by_mass[0.05] > by_mass[0.067] > by_mass[0.09]
    assert by_mass[0.067] == pytest.approx(8.0, rel=1e-3)


def test_repeated_masses_are_not_searched_twice():
    assert parse_masses("0.067, 0.067", "m*_e") == [0.067]


def test_the_pair_search_crosses_both_mass_lists(designer):
    pairs = _run_pair(designer, m_e=(0.060, 0.067), m_h=(0.40, 0.45), tol=1.0)
    assert pairs
    assert {p["electron"]["meff"] for p in pairs} <= {0.060, 0.067}
    assert {p["hole"]["meff"] for p in pairs} <= {0.40, 0.45}


def test_the_same_geometry_at_two_masses_is_not_a_duplicate(designer):
    """Two masses are two answers to the same question, not one repeated."""
    sols = _search(designer, _levels(8.0, 0.067), [0.067, 0.068], maxsol=12)
    masses = {round(s["meff"], 4) for s in sols}
    assert masses == {0.067, 0.068}


# ─── invalid input ───────────────────────────────────────────────────────────

def test_a_bad_mass_is_reported_not_swallowed():
    with pytest.raises(ValueError, match="m\\*_e"):
        parse_masses("0.067, abc", "m*_e")


def test_a_negative_mass_is_refused():
    with pytest.raises(ValueError, match="> 0"):
        parse_masses("0.067, -0.1", "m*_e")


def test_a_negative_energy_is_refused():
    with pytest.raises(ValueError, match="positive"):
        parse_energies("0.1, -0.2", "Electron energies")


def test_an_empty_field_is_refused():
    with pytest.raises(ValueError, match="no values"):
        parse_energies("  ", "Electron energies")


# ─── band edges and the gap ──────────────────────────────────────────────────

def test_the_gap_is_read_from_the_two_offsets(designer):
    """The two offsets are the two edges; the difference is the gap."""
    E_c, E_v = 0.35, -0.25
    electrons = _search(designer, [E_c + lv for lv in _levels(8.0, 0.067)],
                        [0.067], match=MATCH_GAPS, maxsol=2)
    holes = _search(designer, [abs(E_v) + lv for lv in _levels(8.0, 0.45)],
                    [0.45], carrier='h', match=MATCH_GAPS, maxsol=2)
    pairs = pair_candidates(electrons, holes, tol_nm=1.0)
    assert pairs

    edges = edges_from_pair(pairs[0])
    assert edges["E_c"] == pytest.approx(E_c, abs=1e-3)
    assert edges["E_v"] == pytest.approx(E_v, abs=1e-3)
    assert edges["gap"] == pytest.approx(E_c - E_v, abs=2e-3)


def test_absolute_matching_has_no_edge_to_read(designer):
    """In that mode the offset is zero by construction."""
    pairs = _run_pair(designer)
    assert pairs
    assert edges_from_pair(pairs[0])["gap"] == pytest.approx(0.0)


def test_one_side_alone_still_gives_its_own_edge():
    """It is exactly when one branch fails that the other edge is needed."""
    edges = edges_from_solutions({'e': [{'RRMSE': 1.0, 'offset': 0.10}]}, [])
    assert edges["E_c"] == pytest.approx(-0.10)
    assert edges["E_v"] is None and edges["gap"] is None


def test_with_neither_side_there_is_nothing_to_read():
    assert edges_from_solutions({}, []) is None


def test_a_pair_is_preferred_over_two_unrelated_bests():
    """Reading E_c off one candidate and E_v off another that disagrees with
    it is how a gap comes out of two different wells."""
    pair = {'electron': {'RRMSE': 5.0, 'offset': 0.10},
            'hole': {'RRMSE': 5.0, 'offset': 0.20}}
    by_carrier = {'e': [{'RRMSE': 0.1, 'offset': 0.99}],
                  'h': [{'RRMSE': 0.1, 'offset': 0.99}]}
    edges = edges_from_solutions(by_carrier, [pair])
    assert edges["E_c"] == pytest.approx(-0.10)
    assert edges["E_v"] == pytest.approx(0.20)


# ─── the boundaries, and refining them ───────────────────────────────────────

def _charged_well_peaks(L_nm=8.0, E_c=-0.10, E_v=-0.75):
    """dI/dV peaks of an n-doped well: the low electron levels are filled."""
    e_lv = _levels(L_nm, 0.067, 4)
    h_lv = _levels(L_nm, 0.45, 3)
    centres = [E_c + lv for lv in e_lv] + [E_v - lv for lv in h_lv]
    V = np.linspace(-1.2, 0.6, 601)
    peaks = split_peaks(centres, 0.0, 0.0)        # naive split, at V = 0
    peaks.curve = DidvCurve(x=V, y=np.zeros_like(V), name="dI/dV")
    return peaks


def test_a_naive_split_at_zero_tears_the_electron_ladder():
    """The symptom that motivated all of this: half the ladder goes to the
    hole branch, where no well can explain the mixture."""
    peaks = _charged_well_peaks()
    # The lowest electron level sits at -0.012 V — filled, so at negative
    # bias — and a split at V = 0 files it as a hole, where it fits nicely
    # and lies.
    assert -0.012 == pytest.approx(max(-v for v in peaks.hole_eV), abs=1e-3)
    assert len(peaks.electron_eV) == 3            # the ladder, one level short
    assert len(peaks.hole_eV) == 4                # three holes plus the stray


def test_refining_the_boundaries_rebuilds_the_torn_ladder(designer):
    """The fixed point: one edge fixes the split, which gives the other edge."""
    peaks = _charged_well_peaks()

    def run_search(current):
        by_carrier = {}
        for carrier, targets, meff in (('e', current.electron_eV, 0.067),
                                       ('h', current.hole_eV, 0.45)):
            if len(targets) < 2:
                by_carrier[carrier] = []
                continue
            by_carrier[carrier] = _search(
                designer, targets, [meff], carrier=carrier,
                match=MATCH_GAPS, Lmax=20.0, maxsol=2)
        pairs = pair_candidates(by_carrier.get('e', []),
                                by_carrier.get('h', []), tol_nm=2.0)
        return {'pairs': pairs, 'by_carrier': by_carrier}

    refined, history = refine_boundaries(peaks, run_search)

    assert len(history) >= 2
    assert history[-1]["movement"] < 1e-3          # it converged
    assert history[-1]["split_e"] == pytest.approx(-0.10, abs=5e-3)
    assert history[-1]["split_h"] == pytest.approx(-0.75, abs=5e-3)
    # The electron ladder came back whole: four levels, from the ground state.
    assert len(refined.electron_eV) == 4
    assert refined.electron_eV[0] == pytest.approx(_levels(8.0, 0.067, 4)[0],
                                                   abs=1e-3)


def test_refining_stops_rather_than_emptying_a_branch(designer):
    """A boundary that leaves a branch empty is not an edge: it would trade a
    poor fit for no fit at all."""
    peaks = split_peaks([-0.30, 0.30])

    def run_search(_current):
        # Offsets that would push both boundaries past every peak.
        return {'pairs': [], 'by_carrier': {
            'e': [{'RRMSE': 0.1, 'offset': -5.0}],
            'h': [{'RRMSE': 0.1, 'offset': -5.0}]}}

    refined, history = refine_boundaries(peaks, run_search)
    assert history                                  # it tried
    assert refined.electron_eV and refined.hole_eV  # and kept both branches


def test_refining_without_a_search_result_says_nothing_happened():
    peaks = _charged_well_peaks()
    refined, history = refine_boundaries(peaks, lambda _c: {})
    assert history == []
    assert refined is peaks


def test_the_edges_follow_from_the_offsets_alone():
    """band_edges is arithmetic, not a fit: it must stay checkable by hand."""
    edges = band_edges(offset_e=-0.10, offset_h=0.20, split_e=0.25,
                       split_h=-0.30)
    assert edges["E_c"] == pytest.approx(0.35)
    assert edges["E_v"] == pytest.approx(-0.10)
    assert edges["gap"] == pytest.approx(0.45)
