"""
Tests for the line scan.

The logic depends on neither a UI nor the solver — the peak-finding and
candidate-search functions are injected — so almost everything here runs in
milliseconds. At the end there is a small integration test with the real
engine and the real designer, which is the loop the line-scan tool will run.
"""

import numpy as np
import pytest

from src.physics.line_scan import (BAD_FIT, CANCELLED, FEW_PEAKS, LineScan,
                                   NO_FIT, NO_PEAKS, REASON_LABELS,
                                   PointResult, analyze_line_scan,
                                   group_by_size, pick_best,
                                   segments_along_line, summarize)


def _scan(n_points=5, step_nm=None):
    x = np.linspace(-1.0, 1.0, 51)
    ys = np.tile(np.linspace(0.0, 1.0, 51), (n_points, 1)).T
    return LineScan(x=x, ys=ys, names=[f"p{i}" for i in range(n_points)],
                    step_nm=step_nm)


def _sol(L, rrmse=0.0, meff=0.067):
    return {"dims": (L,), "RRMSE": rrmse, "meff": meff, "ndim": "1D",
            "coords": "cartesian"}


def _size(sol):
    return sol["dims"][0]


# ─── the spatial axis ────────────────────────────────────────────────────────

def test_without_a_step_the_axis_is_the_point_index():
    scan = _scan(4)
    assert list(scan.positions_nm()) == [0, 1, 2, 3]
    assert scan.position_label == "Point"


def test_with_a_step_the_axis_is_in_nanometres():
    scan = _scan(4, step_nm=2.5)
    assert list(scan.positions_nm()) == [0.0, 2.5, 5.0, 7.5]
    assert "nm" in scan.position_label


def test_a_scan_is_one_curve_per_position():
    """One voltage column and one dI/dV column per position — the shape a
    line-scan dataset arrives in."""
    scan = LineScan(x=np.array([-1.0, 0.0, 1.0]),
                    ys=np.array([[1.0, 2.0, 3.0],
                                 [2.0, 3.0, 4.0],
                                 [3.0, 4.0, 5.0]]),
                    names=["p0", "p1", "p2"], step_nm=1.5)
    assert scan.n_points == 3
    assert scan.curve(1).y[0] == pytest.approx(2.0)
    assert scan.curve(1).name == "p1"
    assert scan.positions_nm()[2] == pytest.approx(3.0)


def test_a_curve_drops_the_gaps_in_its_own_column():
    """A railed sample is missing, not zero."""
    ys = np.array([[1.0, np.nan], [2.0, 2.0], [3.0, np.nan]])
    scan = LineScan(x=np.array([-1.0, 0.0, 1.0]), ys=ys, names=["a", "b"])
    assert scan.curve(1).x == pytest.approx([0.0])
    assert scan.curve(0).x.size == 3


def test_a_position_beyond_the_names_is_still_named():
    scan = LineScan(x=np.array([0.0, 1.0]), ys=np.zeros((2, 3)), names=["a"])
    assert scan.curve(2).name == "#2"


# ─── when there is no confinement ──────────────────────────────────────────────

def test_a_position_without_peaks_is_not_a_confinement():
    """Absence is a result: a map where every point has a size lies."""
    results = analyze_line_scan(_scan(3), lambda c: {"targets": []},
                                lambda f: [], _size)
    assert all(not r.converged for r in results)
    assert {r.reason for r in results} == {NO_PEAKS}


def test_a_single_peak_is_not_a_ladder():
    """With one level any size "explains" the spectrum."""
    results = analyze_line_scan(_scan(2), lambda c: {"targets": [0.2]},
                                lambda f: [_sol(8.0)], _size, min_peaks=2)
    assert {r.reason for r in results} == {FEW_PEAKS}
    assert all(r.n_peaks == 1 for r in results)


def test_absolute_matching_accepts_a_single_level():
    results = analyze_line_scan(_scan(2), lambda c: {"targets": [0.2]},
                                lambda f: [_sol(8.0)], _size, min_peaks=1)
    assert all(r.converged for r in results)


def test_a_position_with_no_candidate_says_so():
    results = analyze_line_scan(_scan(2), lambda c: {"targets": [0.1, 0.4]},
                                lambda f: [], _size)
    assert {r.reason for r in results} == {NO_FIT}


def test_a_fit_worse_than_the_tolerance_is_refused():
    results = analyze_line_scan(_scan(2), lambda c: {"targets": [0.1, 0.4]},
                                lambda f: [_sol(8.0, rrmse=42.0)], _size,
                                max_rrmse=5.0)
    assert {r.reason for r in results} == {BAD_FIT}
    assert results[0].rrmse == pytest.approx(42.0)   # the error is recorded


def test_a_failing_peak_search_does_not_stop_the_scan():
    def explode(curve):
        raise RuntimeError("odd curve")

    results = analyze_line_scan(_scan(3), explode, lambda f: [_sol(8.0)], _size)
    assert len(results) == 3
    assert {r.reason for r in results} == {NO_PEAKS}


def test_the_scan_can_be_cancelled_midway():
    """A long scan has to be interruptible."""
    seen = []

    def progress(i, total):
        seen.append(i)
        return i < 2

    results = analyze_line_scan(
        _scan(6), lambda c: {"targets": [0.1, 0.4]},
        lambda f: [_sol(8.0)], _size, progress=progress)
    assert len(results) == 6                 # the whole line comes back
    assert sum(r.converged for r in results) == 2
    assert results[-1].reason == CANCELLED


# ─── choosing between aliases ───────────────────────────────────────────────────

def test_between_tied_candidates_the_smallest_wins():
    """L and 2L match the same targets; with no fixed rule the map flickers."""
    best = pick_best([_sol(16.0, 0.001), _sol(8.0, 0.002), _sol(24.0, 0.0)],
                     _size)
    assert best["dims"][0] == 8.0


def test_a_genuinely_better_fit_beats_a_smaller_one():
    best = pick_best([_sol(8.0, rrmse=9.0), _sol(12.0, rrmse=0.1)], _size)
    assert best["dims"][0] == 12.0


def test_the_tie_band_can_be_set_explicitly():
    candidates = [_sol(8.0, rrmse=1.0), _sol(4.0, rrmse=1.4)]
    assert pick_best(candidates, _size, tie_tol=0.5)["dims"][0] == 4.0
    assert pick_best(candidates, _size, tie_tol=0.1)["dims"][0] == 8.0


# ─── grouping ─────────────────────────────────────────────────────────────

def _results(sizes):
    out = []
    for i, size in enumerate(sizes):
        out.append(PointResult(index=i, position=float(i),
                               size_nm=size, rrmse=0.0 if size else None,
                               reason="" if size else NO_PEAKS))
    return out


def test_sizes_within_the_tolerance_are_one_group():
    groups = group_by_size(_results([8.0, 8.1, 8.05]), tol_nm=1.0)
    assert len(groups) == 1
    assert groups[0]["size_nm"] == pytest.approx(8.05)
    assert groups[0]["count"] == 3


def test_a_gap_bigger_than_the_tolerance_splits_the_groups():
    groups = group_by_size(_results([8.0, 8.1, 12.0, 12.2]), tol_nm=1.0)
    assert [g["count"] for g in groups] == [2, 2]
    assert groups[0]["size_nm"] == pytest.approx(8.05)
    assert groups[1]["size_nm"] == pytest.approx(12.1)


def test_groups_come_back_sorted_by_size_and_tag_their_points():
    results = _results([12.0, 8.0, 12.1])
    groups = group_by_size(results, tol_nm=1.0)
    assert [round(g["size_nm"], 2) for g in groups] == [8.0, 12.05]
    assert results[1].group == 0                     # the 8 nm one
    assert results[0].group == results[2].group == 1


def test_points_without_confinement_belong_to_no_group():
    results = _results([8.0, None, 8.1])
    group_by_size(results, tol_nm=1.0)
    assert results[1].group is None
    assert group_by_size(_results([None, None]), tol_nm=1.0) == []


# ─── the spatial reading ────────────────────────────────────────────────────────

def test_segments_follow_the_line_including_the_empty_stretches():
    results = _results([8.0, 8.1, None, None, 12.0])
    group_by_size(results, tol_nm=1.0)
    segments = segments_along_line(results)
    assert [s["group"] for s in segments] == [0, None, 1]
    assert [s["count"] for s in segments] == [2, 2, 1]
    assert segments[1]["start_index"] == 2 and segments[1]["end_index"] == 3


def test_the_same_size_returning_later_is_a_separate_stretch():
    """Two domains of the same size, separated by a gap, are two."""
    results = _results([8.0, None, 8.05])
    group_by_size(results, tol_nm=1.0)
    segments = segments_along_line(results)
    assert [s["group"] for s in segments] == [0, None, 0]


def test_the_summary_counts_the_reasons():
    results = _results([8.0, None, None, 12.0])
    info = summarize(results)
    assert info["total"] == 4 and info["converged"] == 2
    assert info["reasons"] == {NO_PEAKS: 2}
    assert info["size_min"] == 8.0 and info["size_max"] == 12.0


# ─── the reasons are data ────────────────────────────────────────────────────

def test_every_reason_has_something_to_show_a_user():
    """The keys are what gets stored and counted; the labels are what a map
    legend shows. Neither may go missing."""
    for reason in (NO_PEAKS, FEW_PEAKS, NO_FIT, BAD_FIT, CANCELLED):
        assert REASON_LABELS[reason]
        assert reason.islower() and " " not in reason


# ─── the whole loop, with the real engine and the real search ────────────────

def _synthetic_scan(step_nm=2.0, L_nm=8.0, well_at=(2, 3), n_points=5):
    """A scan with a well at some positions and nothing at the others."""
    from src.physics.analytical import box_energies_1d_eV

    E_c = 0.30
    V = np.linspace(-0.2, 1.6, 901)
    rng = np.random.RandomState(5)
    columns = []
    for i in range(n_points):
        y = 0.01 * rng.randn(V.size) + 4 * np.exp((V - 1.3) * 5) * (V > E_c)
        if i in well_at:
            for lv in [E for E, _ in box_energies_1d_eV(L_nm, 0.067, 3)][:3]:
                y += 0.5 * np.exp(-((V - (E_c + lv)) / 0.015) ** 2)
        columns.append(y)
    return LineScan(x=V, ys=np.column_stack(columns),
                    names=[f"p{i}" for i in range(n_points)], step_nm=step_nm)


def _real_scan_run(scan, maxsol=1):
    """analyze_line_scan wired to the real peak engine and the real designer.

    This is the loop the line-scan tool runs; assembling it here is what
    keeps the two from drifting apart.
    """
    from src.physics.branches import analyze_curve
    from src.physics.designer import Designer, MATCH_GAPS, PRIORITY_UNIFORM

    designer = Designer(seed=20260822)

    def targets_fn(curve):
        peaks = analyze_curve(curve, {"height": 3.0})
        return {'targets': peaks.electron_eV, 'n_peaks': peaks.total}

    def search_fn(found):
        p = {'Et': np.array(found['targets']), 'meff': 0.067, 'ndim': "1D",
             'coords': "cartesian", 'sym': "",
             'fixed': {'d1': None, 'd2': None, 'd3': None},
             'Lmin': 1.0, 'Lmax': 20.0, 'tol': 5.0, 'maxsol': maxsol,
             'priority': PRIORITY_UNIFORM, 'match': MATCH_GAPS}
        return [designer.primary_alias(s, p)
                for s in designer.find_solutions(p)]

    return analyze_line_scan(scan, targets_fn, search_fn, _size, min_peaks=2)


def test_the_scan_maps_the_well_and_leaves_the_bare_points_empty():
    """The case that motivated all of this: part of the line has a well,
    part does not."""
    results = _real_scan_run(_synthetic_scan(well_at=(2, 3)))

    assert len(results) == 5
    with_well = [r for r in results if r.converged]
    assert {r.index for r in with_well} == {2, 3}
    for r in with_well:
        assert r.size_nm == pytest.approx(8.0, rel=0.05)
    # And the others do not get handed some number anyway.
    for r in results:
        if r.index not in (2, 3):
            assert r.size_nm is None and r.reason

    groups = group_by_size(results, tol_nm=1.0)
    assert len(groups) == 1
    assert groups[0]["size_nm"] == pytest.approx(8.0, rel=0.05)
    # The spatial reading: empty, domain, empty.
    assert [s["group"] for s in segments_along_line(results)] == [None, 0, None]


def test_a_scan_with_no_confinement_anywhere_is_an_answer():
    results = _real_scan_run(_synthetic_scan(well_at=()))
    assert all(not r.converged for r in results)
    assert group_by_size(results, tol_nm=1.0) == []
    assert summarize(results)['converged'] == 0


def test_the_positions_come_out_in_nanometres():
    results = _real_scan_run(_synthetic_scan(step_nm=2.0, n_points=3,
                                             well_at=(1,)))
    assert [r.position for r in results] == pytest.approx([0.0, 2.0, 4.0])


# ─── alias reduction ─────────────────────────────────────────────────────────

def _alias_params(**over):
    from src.physics.analytical import box_energies_1d_eV
    from src.physics.designer import MATCH_ABSOLUTE, PRIORITY_UNIFORM

    p = {'Et': np.array([E for E, _ in box_energies_1d_eV(8.0, 0.067, 3)][:3]),
         'meff': 0.067, 'ndim': "1D", 'coords': "cartesian", 'sym': "",
         'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 30.0, 'tol': 5.0, 'maxsol': 3,
         'priority': PRIORITY_UNIFORM, 'match': MATCH_ABSOLUTE}
    p.update(over)
    return p


def _alias_candidate(L=24.0):
    return {"dims": (L,), "RRMSE": 0.0, "meff": 0.067, "ndim": "1D",
            "coords": "cartesian", "sym": "", "matches": [], "Ec": []}


def test_the_alias_reduction_finds_the_primary_well():
    """A well 3x larger matches the same targets; the map must keep the
    smallest."""
    from src.physics.designer import Designer

    primary = Designer(seed=1).primary_alias(_alias_candidate(), _alias_params())
    assert primary["dims"][0] == pytest.approx(8.0, rel=1e-6)
    assert primary["RRMSE"] < 0.01


def test_the_alias_reduction_respects_the_search_range():
    """Reducing below the range the user asked for is not allowed.

    24 nm's primary alias is 8 (24/3 matches n = 3,6,9 against n = 1,2,3);
    24/2 = 12 is no alias at all, because 1.5 is not an integer. With
    Lmin = 10 the only valid alias is out of range, so the candidate stays
    as it is.
    """
    from src.physics.designer import Designer

    kept = Designer(seed=1).primary_alias(_alias_candidate(),
                                          _alias_params(Lmin=10.0))
    assert kept["dims"][0] == pytest.approx(24.0)


def test_group_members_are_listed_in_line_order():
    """The list is for knowing WHERE the group is, not what order it grew in."""
    results = _results([12.0, 8.0, 12.1, 8.05])
    groups = group_by_size(results, tol_nm=1.0)
    assert groups[0]["points"] == [1, 3]        # the 8 nm group
    assert groups[1]["points"] == [0, 2]        # the 12 nm one
    assert groups[0]["positions"] == [1.0, 3.0]
