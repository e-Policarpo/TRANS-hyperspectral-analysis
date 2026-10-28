"""
The designer's search API: assignment rules, per-dimension boxes, pinning,
the deterministic enumeration, and the honesty columns.

These cover the machinery added to answer one measured question — why a lens
fitted on level SPACINGS "diverges at L_max = 18 nm but converges at 13 nm".
The answer was never that the optimiser fails. It is that in ``delta_e`` the
energy origin cancels, the axial ladder cancels with it, and L_z is therefore
unmeasurable BY CONSTRUCTION: past L_z ~ 10 nm the disc's level density
inside the fitted window is finer than the measurement's own resolution, so
some level sits near every target whatever the geometry and the error stops
discriminating. Widening the ceiling does not widen the search, it widens the
set of geometries the data cannot choose between.

So what is asserted here is never "the search found the right dot". It is
that each new piece does the one thing that makes the degeneracy visible or
bounded:

* an assignment rule changes WHICH computed level a target is compared with,
  and nothing else — never the score;
* a per-dimension box lets the determined dimension (R) and the undetermined
  one (L_z) stop sharing a slider;
* pinning a dimension removes it from the search entirely, so no ceiling can
  move it;
* the enumeration is deterministic and its lattice is NESTED, so widening the
  box can only add nodes rather than move the ones already there — the exact
  defect of the ``np.linspace`` grid this replaces;
* ``flat_dims`` and ``n_tied`` say out loud what the fit did not see.

Every test here is seeded or has no RNG at all, and the whole file is a few
seconds: the expensive search (``find_solutions``) is deliberately exercised
only where its structure, not its luck, is what is being checked.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import numpy as np
import pytest

from src.processing.edge_analysis import THERMAL_FWHM_FACTOR
from src.physics.designer import (
    ASSIGN_ENERGY, ASSIGN_LOW_QN, ASSIGN_MIXED, ASSIGN_SEQUENTIAL,
    ASSIGNMENTS, ASSIGN_LABELS, Designer, MATCH_ABSOLUTE, MATCH_GAPS,
    PRIORITY_UNIFORM, SYM_ORTHORHOMBIC, SYM_SQUARE, SYM_TETRAGONAL,
)
from src.physics.quantum_dot import dot_energies, levels_for


#: Her case: a 0D lens, m* = 0.322, matched on level SPACINGS. The targets
#: are the first six levels of a 4 nm x 5 nm disc, so the true answer is
#: known exactly and any wandering is the search's, not the data's.
MEFF = 0.322
TRUE_DIMS = (4.0, 5.0)


def _targets(n=6):
    return np.array([E for E, _qn in dot_energies("disc", TRUE_DIMS, MEFF, n)])


def _params(**over):
    """The disc search she actually runs, with ΔE matching."""
    p = {'Et': _targets(), 'meff': MEFF, 'ndim': "0D", 'coords': "disc",
         'sym': '', 'fixed': {'d1': None, 'd2': None, 'd3': None},
         'Lmin': 1.0, 'Lmax': 13.0, 'tol': 5.0, 'maxsol': 6,
         'priority': PRIORITY_UNIFORM, 'match': MATCH_GAPS, 'carrier': 'e'}
    p.update(over)
    return p


def _pinned(**over):
    """The same search with L_z pinned — one free dimension, R."""
    return _params(fixed={'d1': None, 'd2': 5.0, 'd3': None}, **over)


@pytest.fixture
def designer():
    return Designer(seed=20260917)


# ─── which computed level a target is compared with ─────────────────────────
#
# Hand-built ladders, so the right answer is arithmetic rather than physics.
# ``Ec`` is the designer's own format: ``[(E_eV, (quantum numbers)), …]``.

#: The nearest level carries the HIGHER quantum numbers, so "nearest" and
#: "cheapest state" disagree and a rule cannot satisfy both by accident.
LADDER = [(0.100, (1, 1)), (0.104, (2, 1)), (0.200, (1, 2)), (0.260, (3, 3))]
LADDER_ET = [0.103, 0.210]


def test_the_default_assignment_is_still_nearest_in_energy():
    """Omitting ``assign`` must reproduce what the search has always done.

    Every candidate list anyone has already produced was matched
    nearest-in-energy, so the new parameter is only allowed to be a way of
    asking for something else — never a change of default. Checked against a
    reference ``argmin`` written out here rather than against the module's
    own code path.
    """
    Ev = np.array([E for E, _qn in LADDER])
    expected = [int(np.argmin(np.abs(Ev - et) / et)) for et in LADDER_ET]

    default = Designer.find_matches(LADDER, LADDER_ET)
    assert [m['idx'] for m in default] == expected == [1, 2]
    assert default == Designer.find_matches(LADDER, LADDER_ET, ASSIGN_ENERGY)

    # and the pairing it reports is the pairing it used
    for m in default:
        assert (m['computed_E'], m['qn']) == LADDER[m['idx']]


def test_sequential_assignment_ignores_proximity_entirely():
    """Target *i* is level *i*: the rule has no freedom, which is the point.

    It is the control for a ladder whose lowest rungs sit inside the thermal
    linewidth and were never resolved. Here it answers levels 0 and 1 where
    nearest-in-energy answers 1 and 2, so the two rules are visibly not the
    same question.
    """
    seq = Designer.find_matches(LADDER, LADDER_ET, ASSIGN_SEQUENTIAL)
    assert [m['idx'] for m in seq] == [0, 1]
    assert [m['computed_E'] for m in seq] == [0.100, 0.104]
    assert [m['idx'] for m in
            Designer.find_matches(LADDER, LADDER_ET, ASSIGN_ENERGY)] == [1, 2]


def test_sequential_assignment_clamps_instead_of_shortening_the_list():
    """A target past the end of the ladder is a very bad match, not a gap.

    Dropping it would shorten the comparison and make an inadequate model
    score BETTER the more of the spectrum it fails to reach.
    """
    Et = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    seq = Designer.find_matches(LADDER, Et, ASSIGN_SEQUENTIAL)
    assert len(seq) == len(Et)
    assert [m['idx'] for m in seq] == [0, 1, 2, 3, 3, 3]


def test_low_quantum_numbers_prefers_the_state_a_measurement_populates():
    """Within the window, the smallest total quantum number wins.

    The nearest level here is ``(2, 1)``; ``(1, 1)`` is three times further
    off in relative terms but is the state a real spectrum fills first. The
    rule must take it — that is the whole of what "low quantum numbers"
    means — while nearest-in-energy must not.
    """
    low = Designer.find_matches(LADDER, [0.103], ASSIGN_LOW_QN)
    assert low[0]['qn'] == (1, 1) and low[0]['idx'] == 0
    assert Designer.find_matches(LADDER, [0.103], ASSIGN_ENERGY)[0]['qn'] \
        == (2, 1)


def test_low_quantum_numbers_will_not_reach_outside_its_window():
    """The preference is bounded by the error, or it would fit nothing.

    ``(1, 0)`` is the cheapest state on this ladder by a wide margin and is
    50 % away from the target. The window is ten times the best relative
    error or 10 %, whichever is looser, so it is out of reach and the rule
    picks the cheapest of the two levels that are actually near.
    """
    ladder = [(0.050, (1, 0)), (0.100, (5, 5)), (0.101, (6, 6))]
    m = Designer.find_matches(ladder, [0.100], ASSIGN_LOW_QN)[0]
    assert m['idx'] == 1 and m['qn'] == (5, 5)


def test_mixed_is_the_graded_version_of_the_same_preference():
    """A penalty spent in the ladder's own error — not a veto, not a constant.

    Two ladders pin it from both sides, so it is neither of the other two
    rules in disguise. Where the cheapest level on offer is barely cheaper
    measured against the ladder's OWN range of ``sum(qn)``, the penalty does
    not pay for the energy gap and ``mixed`` keeps the nearest level that
    ``low_quantum_numbers`` walks away from. Where the two levels really are
    within the ladder's own error of each other, the quantum number decides
    and ``mixed`` leaves the nearest.

    THE ASSERTIONS MOVED WITH THE RULE, and that is the point rather than an
    accident. They used to read ``idx == 1`` on :data:`LADDER` and ``idx == 0``
    on a ``(9, 9)`` ladder, which is what ``rel_err + 0.01 * sum(qn)`` did —
    a dimensionless relative error added to a hundredth of an integer, where
    which term decides depends only on how good the fit is. See
    :func:`test_the_mixed_penalty_is_measured_in_the_ladders_own_error`.
    """
    # The nearest level is (10, 10); the only cheaper one inside the window
    # is (9, 9), one unit down out of a span of 19, so it buys almost no
    # penalty relief and loses on energy. `low_quantum_numbers`, which cannot
    # grade anything, takes it anyway.
    near_high = [(0.0500, (1, 0)), (0.10001, (10, 10)), (0.10050, (9, 9))]
    for rule, idx in ((ASSIGN_ENERGY, 1), (ASSIGN_MIXED, 1), (ASSIGN_LOW_QN, 2)):
        assert Designer.find_matches(near_high, [0.10001], rule)[0]['idx'] == idx

    # The other side: 0.5 and 0.1 basis points from the target, a gap no
    # measurement of this ladder resolves, and (1, 1) against (5, 5).
    crowded = [(0.1 * (1 - 5e-5), (1, 1)), (0.1 * (1 + 1e-5), (5, 5))]
    for rule, idx in ((ASSIGN_ENERGY, 1), (ASSIGN_MIXED, 0), (ASSIGN_LOW_QN, 0)):
        assert Designer.find_matches(crowded, [0.1], rule)[0]['idx'] == idx


def test_the_low_qn_tie_break_is_a_function_of_the_ladder_alone():
    """Equal error and equal quantum numbers must not resolve by luck.

    Two levels that are indistinguishable under the rule have to come back
    as the same one on every call, or a candidate's reported assignment
    would depend on the order a list happened to be built in.
    """
    ladder = [(0.100, (1, 1)), (0.100, (1, 1)), (0.100, (1, 1))]
    picks = {Designer.find_matches(ladder, [0.100], ASSIGN_LOW_QN)[0]['idx']
             for _ in range(5)}
    assert picks == {0}


def test_an_assignment_rule_never_changes_what_the_rrmse_means():
    """The quantum numbers are reported as data, never folded into the score.

    The standalone calculator this came from added a quantum-number penalty
    into the error itself, which made one number mean different things
    depending on a dropdown. Here the RRMSE is the energy error of whatever
    assignment was made — checked against the formula written out longhand.
    """
    d = Designer(seed=1)
    for assign in ASSIGNMENTS:
        matches = Designer.find_matches(LADDER, LADDER_ET, assign)
        Em = np.array([m['computed_E'] for m in matches])
        Et = np.array(LADDER_ET)
        longhand = float(np.sqrt(np.mean(((Em - Et) / Et) ** 2)) * 100)
        assert d.abs_rrmse(matches, Et) == pytest.approx(longhand, rel=1e-12)


def test_every_assignment_key_is_declared_and_labelled():
    """A mode the UI can offer but the engine ignores is worse than none."""
    assert set(ASSIGNMENTS) == set(ASSIGN_LABELS)
    assert ASSIGNMENTS[0] == ASSIGN_ENERGY          # the default comes first
    Ec = dot_energies("disc", TRUE_DIMS, MEFF, 20)
    for assign in ASSIGNMENTS:
        matches = Designer.find_matches(Ec, _targets(), assign)
        assert len(matches) == 6
        assert all(0 <= m['idx'] < len(Ec) for m in matches)


def test_the_offset_scan_also_defaults_to_nearest_energy(designer):
    """``match_and_score`` must inherit the same default, ΔE mode included.

    The ΔE modes re-run the assignment once per trial alignment, so a default
    that differed here and in :meth:`find_matches` would change every fitted
    geometry while both functions looked right on their own.
    """
    Ec = dot_energies("disc", (4.2, 5.3), MEFF, 20)
    plain = designer.match_and_score(Ec, _targets(), _params())
    named = designer.match_and_score(Ec, _targets(),
                                     _params(assign=ASSIGN_ENERGY))
    assert plain[1] == named[1] and plain[2] == named[2]
    assert [m['idx'] for m in plain[0]] == [m['idx'] for m in named[0]]


def test_an_absent_assign_key_reproduces_the_whole_search(designer):
    """End to end, and on the deterministic path so it is an exact claim."""
    p = _pinned(enum_per_octave=6, enum_polish=20)
    plain = Designer(seed=1).enumerate_solutions(p)
    named = Designer(seed=2).enumerate_solutions(dict(p, assign=ASSIGN_ENERGY))
    assert [s['dims'] for s in plain] == [s['dims'] for s in named]
    assert [s['RRMSE'] for s in plain] == [s['RRMSE'] for s in named]


# ─── one interval per dimension, instead of one for all of them ─────────────

def test_without_a_box_every_free_dimension_gets_the_same_interval(designer):
    """The inherited behaviour, and the ORDER free_keys reads them in.

    ``bounds`` and ``params_to_dims`` consume the optimiser's vector in
    lockstep; an interval landing on the wrong dimension would not raise, it
    would silently search the wrong box.
    """
    for p in (_params(),
              _params(ndim="3D", coords="cartesian", sym=SYM_ORTHORHOMBIC),
              _params(ndim="3D", coords="cartesian", sym=SYM_TETRAGONAL),
              _params(ndim="2D", coords="cartesian", sym=SYM_SQUARE),
              _params(ndim="1D", coords="cartesian")):
        keys = designer.free_keys(p)
        assert designer.bounds(p) == [(p['Lmin'], p['Lmax'])] * len(keys)

    # the orders these two walk in are the thing that must agree
    p3 = _params(ndim="3D", coords="cartesian", sym=SYM_ORTHORHOMBIC)
    assert designer.free_keys(p3) == ['d1', 'd2', 'd3']
    assert designer.dim_keys(p3) == ['d1', 'd2', 'd3']
    p3t = _params(ndim="3D", coords="cartesian", sym=SYM_TETRAGONAL)
    assert designer.free_keys(p3t) == ['d1', 'd3']       # d2 follows d1
    assert designer.dim_keys(p3t) == ['d1', 'd1', 'd3']


def test_a_per_dimension_box_is_honoured_dimension_by_dimension(designer):
    """R and L_z must be able to stop sharing a slider.

    R is pinned to about a hundred picometres by these gaps; L_z is not
    measured at all. One interval for both is what lets L_z run to whatever
    ceiling was chosen for R.
    """
    p = _params(box={'d1': (2.0, 8.0), 'd2': (4.0, 6.0)})
    assert designer.bounds(p) == [(2.0, 8.0), (4.0, 6.0)]

    # and it is the box the search actually runs in
    sols = Designer(seed=3).enumerate_solutions(
        dict(p, enum_per_octave=4, enum_polish=8, maxsol=3))
    assert sols
    for s in sols:
        assert 2.0 <= s['dims'][0] <= 8.0
        assert 4.0 <= s['dims'][1] <= 6.0


def test_a_half_open_box_entry_falls_back_to_the_global_range(designer):
    """A panel that only has a ceiling for L_z should not have to invent a
    floor, and an absent entry must behave exactly as no box at all."""
    p = _params(box={'d1': (None, 6.0), 'd2': (2.0, None)})
    assert designer.bounds(p) == [(1.0, 6.0), (2.0, 13.0)]
    assert designer.bounds(_params(box={'d2': (2.0, 3.0)})) \
        == [(1.0, 13.0), (2.0, 3.0)]
    assert designer.bounds(_params(box={})) == designer.bounds(_params())


def test_a_box_entry_for_a_pinned_dimension_is_simply_not_read(designer):
    """A pinned dimension is not searched, so it has no interval at all."""
    p = _pinned(box={'d1': (2.0, 8.0), 'd2': (4.0, 6.0)})
    assert designer.free_keys(p) == ['d1']
    assert designer.bounds(p) == [(2.0, 8.0)]


# ─── pinning: the fix with the most measured value ──────────────────────────

def test_pinning_the_axial_size_leaves_exactly_one_free_dimension(designer):
    """The engine has always honoured ``p['fixed']``; only the UI lost it.

    With L_z pinned the optimiser varies R alone, and the pinned value
    reaches ``dims`` untouched — not rounded, not re-optimised.
    """
    p = _pinned()
    assert designer.free_keys(p) == ['d1']
    assert len(designer.bounds(p)) == 1
    assert designer.params_to_dims([3.7], p) == (3.7, 5.0)
    assert designer.free_keys(_params()) == ['d1', 'd2']


def test_a_pinned_axial_size_cannot_follow_the_ceiling(designer):
    """The headline: the same answer at L_max = 13 and 18 nm, on any seed.

    Unpinned, this is precisely where the tool misbehaves — at 13 nm no
    pixel's L_z exceeds 10 nm, at 18 nm a quarter of them pin against the
    ceiling and their R collapses to compensate. Pinned, the ceiling is not
    a parameter of the answer at all: L_z comes back as the number that went
    in, bit for bit, and the R population is identical.

    Run through :meth:`enumerate_solutions`, which is the deterministic path.
    ``find_solutions`` stays a random SAMPLE of the acceptable set even with
    a dimension pinned — that is what it is for — so seed-independence is a
    claim about the enumeration, and asserting it of the sampler would be
    asserting something that is not true.
    """
    p13 = _pinned(Lmax=13.0, enum_per_octave=6, enum_polish=30)
    p18 = _pinned(Lmax=18.0, enum_per_octave=6, enum_polish=30)

    a = Designer(seed=1).enumerate_solutions(p13)
    b = Designer(seed=424242).enumerate_solutions(p13)
    c = Designer(seed=9).enumerate_solutions(p18)

    assert a and [s['dims'] for s in a] == [s['dims'] for s in b]
    assert all(s['dims'][1] == 5.0 for s in a + c)

    # widening the ceiling adds nothing and moves nothing
    assert len(c) >= len(a)
    for s in a:
        near = min(abs(s['dims'][0] - t['dims'][0]) for t in c)
        assert near < 1e-6, f"R = {s['dims'][0]} at 13 nm is gone at 18 nm"


def test_the_sampling_search_honours_the_pin_too():
    """``find_solutions`` is the path the panel calls, so it has to obey.

    It remains a random SAMPLE of the acceptable set — which candidates come
    back still depends on the seed — but not one of them may vary the pinned
    dimension, at any ceiling. That is the property that ends the runaway:
    with L_z fixed there is nothing for a wider L_max to inflate.
    """
    for Lmax in (13.0, 18.0):
        sols = Designer(seed=11).find_solutions(_pinned(Lmax=Lmax, maxsol=2))
        assert sols
        for s in sols:
            assert s['dims'][1] == 5.0
            assert 1.0 <= s['dims'][0] <= Lmax


def test_a_pinned_dimension_is_never_reported_as_flat(designer):
    """``flat_dims`` describes the SEARCH, not the model.

    A pinned dimension was not searched, so "the fit never saw it" is not a
    finding about it — the user put it there on purpose. Reporting it would
    turn a decision into a warning.
    """
    sol = {'dims': (6.5, 1.0), 'meff': MEFF}
    assert designer.flat_dims(sol, _params()) == ['d2']
    assert designer.flat_dims(sol, _params(fixed={'d1': None, 'd2': 1.0,
                                                  'd3': None})) == []


def test_every_dimension_pinned_is_a_single_answer(designer):
    """No free variable is not an error — it is one geometry, scored."""
    p = _params(fixed={'d1': 4.0, 'd2': 5.0, 'd3': None})
    assert designer.bounds(p) == []
    sols = Designer(seed=1).enumerate_solutions(p)
    assert len(sols) == 1
    assert sols[0]['dims'] == TRUE_DIMS
    assert sols[0]['RRMSE'] == pytest.approx(0.0, abs=1e-9)


# ─── the lattice, and the enumeration built on it ───────────────────────────

def test_the_lattice_at_a_lower_ceiling_is_a_subset_of_the_wider_one(designer):
    """Widening the box may ADD nodes; it may never move the existing ones.

    This is the specific defect of the ``np.linspace`` sweep this replaces:
    its nodes are redistributed between the endpoints, so raising L_max moves
    every node and the two runs sample different geometries — which would
    manufacture exactly the 13-versus-18 disagreement the tool is being asked
    to explain. Subset here means bit-for-bit equal floats, because a node
    that differs in the last ulp is a different starting point.
    """
    for per_octave in (3, 4, 8):
        p = _params(enum_per_octave=per_octave)
        narrow = designer.lattice(1.0, 13.0, p)
        wide = designer.lattice(1.0, 18.0, p)
        assert len(wide) > len(narrow)
        assert wide[:len(narrow)] == narrow          # bit for bit
        assert set(narrow) <= set(wide)

        # the grid it replaces fails this on the same numbers
        linear_narrow = list(np.linspace(1.0, 13.0, len(narrow)))
        linear_wide = list(np.linspace(1.0, 18.0, len(narrow)))
        assert linear_wide[:len(narrow)] != linear_narrow


def test_the_lattice_is_geometric_and_anchored_at_lmin(designer):
    """Equal ratios of L are equal steps in the quantity being fitted.

    E goes as 1/L², so log spacing is roughly even spacing in resolvable
    levels. A uniform grid over 1–18 nm spends more than half its nodes above
    10 nm, where the model's levels are finer than the measurement resolves
    and every node fits equally meaninglessly.
    """
    p = _params(enum_per_octave=8)
    nodes = designer.lattice(1.0, 13.0, p)
    assert nodes[0] == 1.0
    assert nodes[-1] <= 13.0
    ratios = [b / a for a, b in zip(nodes, nodes[1:])]
    assert ratios == pytest.approx([2.0 ** (1.0 / 8)] * len(ratios), rel=1e-12)
    # an octave is eight nodes, by construction
    assert nodes[8] == pytest.approx(2.0, rel=1e-12)
    # denser when asked, and still nested inside the sparser one
    assert len(designer.lattice(1.0, 13.0, _params(enum_per_octave=16))) \
        > len(nodes)


def test_the_lattice_degenerates_without_raising(designer):
    """An empty or inverted interval is a bad input, not a crash mid-search."""
    p = _params()
    assert designer.lattice(5.0, 3.0, p) == [5.0]
    assert designer.lattice(0.0, 3.0, p) == [0.0]
    assert designer.lattice(4.0, 4.0, p) == [4.0]


def test_the_enumeration_is_deterministic():
    """Same input, same output — no RNG anywhere in this path.

    It is the whole reason the method exists: ``find_solutions`` redraws its
    six candidates from a much larger acceptable set on every seed, so a
    population can only be counted on a path that has no seed.
    """
    p = _pinned(enum_per_octave=6, enum_polish=20)
    a = Designer(seed=1).enumerate_solutions(p)
    b = Designer(seed=987654).enumerate_solutions(p)
    c = Designer().enumerate_solutions(p)            # entropy-seeded
    assert [s['dims'] for s in a] == [s['dims'] for s in b] \
        == [s['dims'] for s in c]
    assert [s['RRMSE'] for s in a] == [s['RRMSE'] for s in c]


def test_the_enumeration_is_neither_truncated_nor_gated_by_maxsol():
    """``maxsol`` is a display quota; counting a population is not display.

    The grid pass this replaces ran only ``if len(solutions) < max_sol``, and
    since the random passes fill six slots on ~94 % of spectra it was dead
    code almost every time it was called. Here ``maxsol`` is set to 1 — the
    value that would have silenced it — and the enumeration must still return
    the whole deduplicated population.
    """
    p = _pinned(maxsol=1, enum_per_octave=6, enum_polish=20)
    sols = Designer(seed=1).enumerate_solutions(p)
    assert len(sols) > p['maxsol']
    assert [s['RRMSE'] for s in sols] == sorted(s['RRMSE'] for s in sols)
    assert Designer.is_duplicate(sols[0], sols[1:]) is False

    # and the sampler it sits beside really does stop at maxsol
    assert len(Designer(seed=1).find_solutions(p)) <= 1


def test_the_enumeration_can_be_cancelled_and_says_so_while_it_runs():
    """A survey of a box is the slowest thing the designer does.

    It polls far more finely than ``find_solutions`` can — that method's
    smallest indivisible unit is a whole differential-evolution pass — so a
    Cancel must land inside it rather than after it, and it must return what
    it has instead of raising: a partial list is still a list of real
    candidates, and whether it is worth showing is the caller's decision.
    """
    p = _pinned(enum_per_octave=6, enum_polish=20)
    seen = []
    assert Designer(seed=1).enumerate_solutions(
        p, progress=seen.append, should_cancel=lambda: True) == []
    assert seen == []           # cancelled before the first node was scored

    Designer(seed=1).enumerate_solutions(p, progress=seen.append)
    assert seen and any("lattice node" in msg for msg in seen)
    assert any("refining" in msg for msg in seen)


def test_a_lattice_too_large_to_afford_refuses_instead_of_running(designer):
    """Three free dimensions at the default density is a quarter of an hour.

    A search that silently takes that long reads as a hang, and the user
    cannot tell which knob caused it — so the error names the knob.
    """
    with pytest.raises(ValueError) as excinfo:
        designer.enumerate_solutions(_params(enum_max_nodes=10,
                                             enum_per_octave=4))
    assert "enum_per_octave" in str(excinfo.value)


# ─── the honesty columns ────────────────────────────────────────────────────

def test_a_dimension_the_gaps_never_saw_is_flagged_flat(designer):
    """At R = 6.5 nm the ΔE error does not depend on L_z at all.

    No n_z > 1 state enters the lowest twenty levels of this disc at
    L_z = 1 nm, so the axial size only shifts the whole ladder — and in ΔE
    matching the origin cancels. The reported L_z is then one arbitrary point
    of a plateau, printed to three decimals. The probe's claim is bit
    equality, not a tolerance: the number did not enter the arithmetic.
    """
    p = _params()
    base = designer.score_dims((6.5, 1.0), p)
    assert designer.score_dims((6.5, 0.98), p) == base
    assert designer.score_dims((6.5, 1.02), p) == base
    assert designer.flat_dims({'dims': (6.5, 1.0), 'meff': MEFF}, p) == ['d2']

    # R, meanwhile, is exactly what these gaps DO measure
    assert designer.score_dims((6.5 * 0.98, 1.0), p) != base
    assert designer.score_dims((6.5 * 1.02, 1.0), p) != base


def test_the_same_geometry_is_not_flat_in_absolute_energies(designer):
    """The plateau is a property of the MODE, not of the disc.

    Matched on absolute energies the axial ladder is observable — it sets
    where the whole spectrum sits — so nothing is flat. This is the
    difference that makes L_z unmeasurable in her data rather than merely
    poorly measured, and a flag that could not tell the two modes apart would
    be reporting the wrong fact.
    """
    p = _params(match=MATCH_ABSOLUTE)
    assert designer.flat_dims({'dims': (6.5, 1.0), 'meff': MEFF}, p) == []
    base = designer.score_dims((6.5, 1.0), p)
    assert designer.score_dims((6.5, 0.98), p) != base


def test_a_candidate_from_the_search_carries_its_flat_dimensions(designer):
    """The column is populated on every accepted candidate, not on request."""
    sols = Designer(seed=1).enumerate_solutions(
        _params(enum_per_octave=3, enum_polish=6, maxsol=3))
    assert sols
    for s in sols:
        assert isinstance(s['flat_dims'], list)
        assert set(s['flat_dims']) <= {'d1', 'd2'}


def test_each_match_carries_the_degeneracy_of_its_own_state(designer):
    """A "level" can be several states, and a peak assignment must know.

    Checked against :func:`levels_for` keyed by the quantum numbers, never by
    position: the ΔE modes re-index the matches onto a shifted, truncated
    copy of the ladder, so a stored index points into a list that no longer
    exists and would name the wrong state.
    """
    sol = designer.extract_solution([4.0, 5.0], _params())
    table = {tuple(int(q) for q in lv.quantum_numbers): int(lv.degeneracy)
             for lv in levels_for("0D", "disc", sol['dims'], MEFF, 20)}
    assert sol['matches']
    for m in sol['matches']:
        qn = tuple(int(q) for q in m['qn'])
        assert m['degeneracy'] == table[qn]
        assert isinstance(m['degeneracy'], int)
        assert isinstance(m['partners'], list)
        # the disc's |m| != 0 states are the twofold ones, and nothing else
        assert m['degeneracy'] == (2 if qn[1] else 1)


def test_the_degeneracy_totals_are_the_totals(designer):
    """``g_sum``/``g_max`` are what the standalone calculator printed.

    Six matched rows standing for nine orbital states is the fact: a fit that
    reported six is describing a spectrum it has not counted.
    """
    sol = designer.extract_solution([4.0, 5.0], _params())
    degs = [m['degeneracy'] for m in sol['matches']]
    assert sol['g_sum'] == sum(degs) and isinstance(sol['g_sum'], int)
    assert sol['g_max'] == max(degs) and isinstance(sol['g_max'], int)
    assert sol['g_sum'] > len(sol['matches'])
    assert sol['qn_sum'] == sum(sum(int(q) for q in m['qn'])
                                for m in sol['matches'])
    assert sol['n_distinct'] == len({tuple(m['qn']) for m in sol['matches']})


def test_an_unstated_resolution_stays_unstated(designer):
    """No resolution given, no verdict — the columns go empty, not confident.

    This used to fall back to half the smallest measured gap so the columns
    were never blank. That is a LOWER BOUND on the resolution, not the
    resolution: on these six levels it lands at 6.07 meV against a real
    27 meV at 90 K, and at that window every runaway geometry passes as
    resolvable. A flag silent on the geometries it exists to catch reads as
    a clean bill of health, which is worse than an empty cell.
    """
    p = _params()
    gaps = np.diff(np.sort(p['Et']))
    assert designer.resolution_eV(p) is None
    assert 0.5 * gaps.min() == pytest.approx(0.00607, abs=1e-4)  # the old guess
    assert 'not set' in designer.resolution_basis(p)

    # Either way of stating it is the user's own measurement.
    assert designer.resolution_eV(_params(resolution_meV=27.0)) == 0.027
    # 3.5 k_B T — written from its derivation, 4 ln(1 + sqrt 2), so it is the
    # same number as edge_analysis.THERMAL_FWHM_FACTOR: 27.3 meV at 90 K,
    # 91.1 meV at 300 K.
    assert designer.resolution_eV(_params(temperature_K=90)) == pytest.approx(
        0.02734, abs=1e-5)
    assert designer.resolution_eV(_params(temperature_K=300)) == pytest.approx(
        0.09114, abs=1e-5)
    assert Designer.THERMAL_FWHM_KT == THERMAL_FWHM_FACTOR
    assert designer.resolution_basis(_params(temperature_K=90)) == (
        '3.5 k_B T at 90 K')


def test_the_runaway_geometries_are_flagged_once_a_resolution_is_given(designer):
    """The flag has to fire on the geometries that caused the trouble.

    L_z running to the ceiling is the mechanism behind the 13-vs-18 nm
    disagreement, and under the old derived window all three runaway
    geometries reported ``unresolvable = False``. At 3.5 k_B T for 90 K they
    flip, while a genuinely resolved lens does not — the flag discriminates
    rather than firing on everything.
    """
    for dims in ([3.2, 10.0], [2.9, 14.5], [2.1, 18.0]):
        sol = designer.extract_solution(dims, _params(temperature_K=90))
        assert sol['unresolvable'] is True

    # The well these targets actually came from is resolved, so the flag
    # discriminates rather than firing on everything.
    resolved = designer.extract_solution([4.0, 5.0], _params(temperature_K=90))
    assert resolved['unresolvable'] is False
    assert resolved['mean_spacing_eV'] == pytest.approx(0.0412, abs=5e-4)

    # And it decides at the right scale: (3.75, 5.0) nm spaces its levels
    # 26.3 meV apart against a 27.1 meV window, so it is flagged — barely.
    # A threshold that only ever separated obvious cases would not be
    # telling us anything about the borderline ones, which is where the
    # L_z runaway actually lives.
    borderline = designer.extract_solution([3.75, 5.0],
                                           _params(temperature_K=90))
    assert borderline['mean_spacing_eV'] == pytest.approx(0.0263, abs=5e-4)
    assert borderline['unresolvable'] is True


def test_n_tied_counts_the_assignments_the_data_cannot_rule_out(designer):
    """Widening the resolution can only tie more levels together, never fewer.

    ``n_tied`` is the count of model levels inside one resolution window of a
    matched level. It is what makes the real failure visible: the extra room
    a wider search box buys is filled with geometries the measurement cannot
    choose between, not with better fits.
    """
    counts = []
    for res in (27.0, 91.0, 200.0):
        q = _params(resolution_meV=res)
        sol = designer.extract_solution([4.0, 5.0], q)
        assert isinstance(sol['n_tied'], int) and sol['n_tied'] >= 1
        assert sol['resolution_eV'] == designer.resolution_eV(q)
        counts.append(sol['n_tied'])
    assert counts == sorted(counts) and counts[-1] > counts[0]

    # With no resolution stated there is no count to report, and the mean
    # spacing — a property of the model alone — is recorded anyway.
    unset = designer.extract_solution([4.0, 5.0], _params())
    assert unset.get('n_tied') is None
    assert unset.get('unresolvable') is None
    assert unset['mean_spacing_eV'] > 0


def test_unresolvable_says_the_levels_are_finer_than_the_measurement(designer):
    """The yes/no form of the same fact, and the reason a wide box misleads.

    A 4 nm x 5 nm lens at 90 K is comfortably resolved; a 12 nm one is not —
    its mean model spacing across the fitted window is below the thermal
    linewidth, so some level sits near every target whatever the geometry and
    the RRMSE has stopped discriminating.
    """
    p = _params(resolution_meV=27.0)
    small = designer.extract_solution([4.0, 5.0], p)
    large = designer.extract_solution([12.0, 12.0], p)
    assert small['mean_spacing_eV'] > p['resolution_meV'] * 1e-3
    assert small['unresolvable'] is False
    assert large['mean_spacing_eV'] < p['resolution_meV'] * 1e-3
    assert large['unresolvable'] is True
    assert large['n_tied'] > small['n_tied']


def test_an_unresolvable_candidate_can_be_refused_but_is_not_by_default():
    """Whether an undecidable fit is worth seeing is the user's judgement.

    It is a statement about the DATA — this spectrum cannot tell these
    geometries apart — so the engine offers the filter and does not apply it.
    """
    p = _params(resolution_meV=100.0, enum_per_octave=3, enum_polish=8,
                maxsol=3)
    kept = Designer(seed=1).enumerate_solutions(p)
    refused = Designer(seed=1).enumerate_solutions(
        dict(p, reject_unresolvable=True))
    assert len(refused) <= len(kept)
    assert all(not s.get('unresolvable') for s in refused)
    assert any(s.get('unresolvable') for s in kept)


# ─── the defects an adversarial review measured, one test each ──────────────
#
# Every test below failed on the code as reviewed and passes on the code as
# it now stands. The numbers quoted in each docstring are the review's own
# measurements, so the "before" is not a reconstruction.

import contextlib                                                 # noqa: E402
import signal                                                     # noqa: E402

from src.physics.analytical import (box_energies_2d_eV,           # noqa: E402
                                    box_energies_3d_eV,
                                    group_degeneracy)
from src.physics.quantum_dot import length_from_hw                # noqa: E402


@contextlib.contextmanager
def _deadline(seconds):
    """Turn a hang into a failure.

    ``Designer.lattice`` used to loop forever on a non-positive
    ``enum_per_octave``, and a test that asserts it no longer does would, if
    the guard were ever removed, hang the whole suite instead of reporting a
    regression. SIGALRM is the only thing that can interrupt a pure-Python
    ``while True`` from inside the same process.
    """
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - POSIX only
        yield
        return

    def _fire(_signum, _frame):
        raise AssertionError(
            f"the call did not return within {seconds:g} s — it is looping")

    old = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, old)


#: A deliberately cheap enumeration: three targets, 2 to 8/13 nm, 4 nodes per
#: octave. 81 and 121 lattice nodes, well under a second each, and it is the
#: exact shape that the ``POLISH_ALL_BELOW`` floor used to break — a lattice
#: too big to refine exhaustively but small enough that the density rule asks
#: for fewer than 32 refinements.
def _cheap(Lmax):
    return _params(Et=_targets(3), Lmin=2.0, Lmax=Lmax,
                   enum_per_octave=4, enum_polish=8)


# ─── D1: the candidate list must inherit the lattice's nesting ──────────────

def test_the_refined_fraction_does_not_depend_on_the_ceiling(designer):
    """``enum_polish`` is a DENSITY, so the same share of a bigger lattice.

    The lattice was always nested; the candidate list was not, because
    ``enum_polish`` was an absolute top-40 over a lattice that grows with
    ``L_max``: 40 of 900 nodes at 13 nm (4.4 %), 40 of 1156 at 18 (3.5 %),
    40 of 1444 at 25 (2.8 %). A node inside the cut at 13 nm fell outside it
    at 18, and the panel meanwhile promised that "widening the range can only
    ADD candidates". Scaled to the box in octaves the budget is 32 / 40 / 50
    and the refined share is flat to within a per cent.
    """
    shares, budgets, totals = [], [], []
    for Lmax in (13.0, 18.0, 25.0):
        p = _params(Lmax=Lmax, enum_per_octave=8, enum_polish=40)
        bounds = designer.bounds(p)
        total = 1
        for lo, hi in bounds:
            total *= len(designer.lattice(lo, hi, p))
        budget = designer.polish_budget(bounds, p, total)
        totals.append(total)
        budgets.append(budget)
        shares.append(budget / total)

    assert totals == [900, 1156, 1444]
    assert budgets == [32, 40, 50]
    assert max(shares) / min(shares) < 1.05

    # The rule it replaced, on the very same lattices, for contrast.
    absolute = [40 / n for n in totals]
    assert max(absolute) / min(absolute) > 1.5

    # Her shipped box is the reference one and still gets exactly 40.
    assert designer.polish_budget(designer.bounds(_params(Lmax=18.0)),
                                  _params(Lmax=18.0, enum_polish=40),
                                  1156) == 40


def test_a_lattice_too_big_to_refine_in_full_gets_no_absolute_floor(designer):
    """The exhaustive floor is exhaustive, or it is inert — never an absolute 32.

    ``POLISH_ALL_BELOW`` says "a tiny lattice is refined in full". Written as
    ``max(budget, min(total_nodes, 32))`` it also put a floor of 32 under
    every LARGER lattice, which is the absolute top-N this method exists to
    remove: 2 to 8 nm and 2 to 13 nm at 4 nodes per octave are 81 and 121
    nodes, and both refined 32 of them — 39.5 % against 26.4 %, and the
    nesting gone again.
    """
    small = _cheap(8.0)
    wide = _cheap(13.0)
    b_small, b_wide = designer.bounds(small), designer.bounds(wide)
    n_small, n_wide = 81, 121
    assert [len(designer.lattice(lo, hi, small)) for lo, hi in b_small] == [9, 9]
    assert [len(designer.lattice(lo, hi, wide)) for lo, hi in b_wide] == [11, 11]

    share_small = designer.polish_budget(b_small, small, n_small) / n_small
    share_wide = designer.polish_budget(b_wide, wide, n_wide) / n_wide
    assert share_small == pytest.approx(share_wide, abs=0.01)
    assert designer.polish_budget(b_small, small, n_small) < Designer.POLISH_ALL_BELOW

    # And a lattice that really is tiny is still taken whole.
    tiny = _params(Et=_targets(3), Lmin=2.0, Lmax=3.0,
                   enum_per_octave=2, enum_polish=1)
    assert designer.polish_budget(designer.bounds(tiny), tiny, 4) == 4


def test_the_candidate_list_at_a_lower_ceiling_is_a_subset_of_the_wider_one():
    """The guarantee the panel prints, asserted on candidates and not on nodes.

    Reviewed: at ``enum_per_octave`` 8 and ``enum_polish`` 40 the disc gave
    17 candidates inside 13 nm, 19 inside 18 and 16 inside 25 — R = 6.4681 nm
    present at 13 and gone at 18, five of the nineteen gone at 25, and
    widening 18 -> 25 REDUCING the count. Now 21 -> 23 -> 24 with every
    earlier geometry reproduced bit for bit; this runs the same claim on the
    cheap box so the suite stays fast.
    """
    found = {}
    for Lmax in (8.0, 13.0):
        sols = Designer(seed=1).enumerate_solutions(_cheap(Lmax))
        found[Lmax] = {tuple(repr(float(d)) for d in s['dims']) for s in sols}

    assert found[8.0], "nothing to be nested"
    lost = found[8.0] - found[13.0]
    assert not lost, f"widening the ceiling moved or dropped {sorted(lost)}"
    assert len(found[13.0]) >= len(found[8.0])


# ─── D3: degeneracy on the path the product actually takes ──────────────────

def _degeneracies(designer, p, opt):
    """``{quantum numbers: degeneracy}`` as a candidate table would print it."""
    sol = designer.extract_solution(list(opt), p)
    return sol, {tuple(int(q) for q in m['qn']): m.get('degeneracy')
                 for m in sol['matches']}


def test_a_cartesian_level_is_reported_as_the_group_it_belongs_to(designer):
    """A cube's (1,1,2) is one of three, and used to print as a singlet.

    ``annotate`` asks for ``levels_for(distinct=False)``, and for every
    Cartesian box that per-row weight is the literal 1: those enumerators
    list each permutation as its own row and put the multiplicity in the
    LIST. Reviewed through ``extract_solution``: 5 nm square (1,2) -> 1
    (true 2); 5 nm cube (1,1,2) -> 1 (true 3), (1,2,2) -> 1 (true 3),
    (1,1,3) -> 1 (true 3), with g_sum = 4 for four rows standing for ten
    orbital states. A wrong degeneracy is worse than none: 1 on a cube level
    reads as "this peak is a singlet".
    """
    square = _params(Et=np.array([E for E, _ in
                                  box_energies_2d_eV(5.0, 5.0, 0.067, 6)]),
                     meff=0.067, ndim="2D", coords="cartesian",
                     sym=SYM_ORTHORHOMBIC, match=MATCH_ABSOLUTE, Lmax=20.0)
    sol, g = _degeneracies(designer, square, (5.0, 5.0))
    assert g[(1, 1)] == 1
    assert g[(1, 2)] == 2
    assert g[(2, 2)] == 1
    assert g[(1, 3)] == 2

    cube = _params(Et=np.array([E for E, _ in
                                box_energies_3d_eV(5.0, 5.0, 5.0, 0.067, 8)]),
                   meff=0.067, ndim="3D", coords="cartesian",
                   sym=SYM_ORTHORHOMBIC, match=MATCH_ABSOLUTE, Lmax=20.0)
    sol, g = _degeneracies(designer, cube, (5.0, 5.0, 5.0))
    assert g[(1, 1, 1)] == 1
    assert g[(1, 1, 2)] == 3
    assert g[(1, 2, 2)] == 3
    assert g[(1, 1, 3)] == 3
    # Four distinct levels standing for ten orbital states, over eight rows.
    assert sol['n_distinct'] == 4
    assert sum(sorted(set(g.items()))[i][1] for i in range(4)) == 10


def test_a_parabolic_level_picks_up_its_accidental_partner(designer):
    """At 20/30 meV (3,0) shares its energy with (0,2): five states, not four.

    ``_dot_weight`` gives the in-plane shell ``n_xy + 1``, which is right for
    one row and blind to the commensurate coincidence that joins two. The
    review measured (3,0) -> 4 where the level is 5 and (0,2) -> 1 where it
    is also 5.

    Ten targets, not eight, and for a reason worth naming: the parabolic
    basis is a square ``n_xy x n_z`` grid of side ``max(3, ceil(sqrt(n)))``,
    so eight targets open ``n_xy <= 2`` and (3,0) is not enumerated AT ALL in
    the list the targets are drawn from — the control below would then ask
    about a state that is not in the table. Ten open ``n_xy <= 3``, which is
    where both partners first exist. The same limit is pinned in its own
    right by ``test_dot_energies_parabolic_basis_is_capped``.
    """
    def _at(hw_z):
        p = _params(Et=np.array([E for E, _ in dot_energies(
                        "parabolic", (20.0, hw_z), 0.067, 10)]),
                    meff=0.067, ndim="0D", coords="parabolic",
                    match=MATCH_ABSOLUTE, Lmax=40.0)
        return _degeneracies(designer, p, [length_from_hw(20.0, 0.067),
                                           length_from_hw(hw_z, 0.067)])

    # 20/30 meV is 2:3 commensurate, so (3,0) and (0,2) are the same level.
    _sol, g = _at(30.0)
    assert g[(0, 0)] == 1
    assert g[(1, 0)] == 2
    assert g[(2, 0)] == 3
    assert g[(3, 0)] == 5, "the (0,2) partner was dropped"
    assert (0, 2) not in g, "it is the SAME level, not a second row"

    # The same dot away from commensurability keeps the plain shell count,
    # which is what says the 5 above is the coincidence and not an inflation.
    _sol, g = _at(31.7)
    assert g[(3, 0)] == 4
    assert g[(0, 2)] == 1
    assert g[(0, 0)] == 1 and g[(1, 0)] == 2 and g[(2, 0)] == 3


def test_the_disc_and_the_sphere_are_left_exactly_where_they_were(designer):
    """The group total must not double-count the folds that were already right.

    A disc row already stands for the ``+/-m`` pair and a sphere row for its
    ``2l+1`` projections. Summing over a group has to leave those untouched,
    because their groups have one member each unless a real coincidence joins
    them.
    """
    p = _params(match=MATCH_ABSOLUTE)
    _sol, g = _degeneracies(designer, p, (4.0, 5.0))
    for qn, deg in g.items():
        assert deg == (2 if int(qn[1]) != 0 else 1), qn

    s = _params(Et=np.array([E for E, _ in
                             dot_energies("spherical", (6.0,), 0.067, 4)]),
                meff=0.067, ndim="0D", coords="spherical",
                match=MATCH_ABSOLUTE, Lmax=20.0)
    _sol, g = _degeneracies(designer, s, (6.0,))
    for qn, deg in g.items():
        assert deg == 2 * int(qn[1]) + 1, qn


# ─── D4: a plateau is flat all the way along, not only at its first node ────

def test_every_point_of_a_plateau_is_flagged_flat_not_just_the_first(designer):
    """L_z is unmeasurable under ΔE, so no point of the plateau may print as
    measured.

    At R = 6.5 nm the score is 47.48464848646017 / …003 / …009 / …006 at
    L_z = 1.0 / 1.5 / 2.0 / 2.5 nm — one and two ulps apart, because in
    ``delta_e`` the constant axial energy is added into every level and
    subtracted again as the offset, and ``(a + c) - (b + c)`` is not
    ``a - b`` in floats. Under bit equality only L_z = 1.0 was flagged; the
    other three printed a four-decimal L_z with no "free" badge. On the real
    13 nm search output, 2 of the 13 candidates sharing one R = 8.7761
    plateau were flagged.
    """
    p = _params()
    plateau = (1.0, 1.5, 2.0, 2.5)
    scores = [designer.score_dims((6.5, lz), p) for lz in plateau]

    # The premise: they are NOT bit-equal, which is why bit equality failed.
    assert len(set(scores)) > 1
    # …and they agree to a few ulps, which is why a relative test works. The
    # number is written out rather than read from `Designer.FLAT_RTOL`: this
    # line is a fact about the floats the model produces, and reading the
    # constant would make it agree with whatever the constant happened to be.
    assert max(scores) - min(scores) <= 1e-12 * max(scores)

    for lz in plateau:
        sol = designer.extract_solution([6.5, lz], p)
        assert sol['flat_dims'] == ['d2'], f"L_z = {lz} printed as measured"

    assert Designer.FLAT_RTOL == 1e-12, "the window this rests on moved"


def test_the_flat_tolerance_is_far_below_any_real_sensitivity(designer):
    """A dimension the fit DID see must not be swept up by the ulp window.

    The window is ~4500 ulps of a double, twelve orders of magnitude below
    the tens of per cent that moving R by 2 % costs on this disc.
    """
    p = _params()
    base = designer.score_dims((6.5, 1.0), p)
    moved = designer.score_dims((6.5 * 1.02, 1.0), p)
    assert abs(moved - base) > 1e-6 * max(abs(base), abs(moved))
    assert designer.extract_solution([6.5, 1.0], p)['flat_dims'] == ['d2']


# ─── D6: the lattice refuses instead of hanging ─────────────────────────────

@pytest.mark.parametrize("per_octave", [-8, -1, -0.5, 1e-4, 1e18,
                                        float('nan'), float('inf')])
def test_a_lattice_step_that_cannot_terminate_is_refused(designer, per_octave):
    """No ``enum_per_octave`` may turn the loop into a hang.

    At -8 the ratio ``2**(-1/8)`` is below 1, so ``v`` decreases
    monotonically, never exceeds ``hi``, and ``while True`` never breaks —
    killed at 5 s by the review. ``enum_max_nodes`` could not save it,
    because the cap was checked only after ``lattice`` returned. Below one
    node per octave the ratio overflows a double instead (``2**10000`` at
    1e-4, an OverflowError out of a worker thread); above ~1e16 it rounds to
    exactly 1.0 and the nodes stop advancing. The panel clamps 1..64, but
    ``_design_one_spectrum`` passes ``params.get('enum_per_octave')``
    straight through, so any workflow node or scripted caller reaches this.
    """
    with _deadline(5.0):
        with pytest.raises(ValueError):
            designer.lattice(1.0, 13.0, _params(enum_per_octave=per_octave))


def test_the_node_count_is_bounded_as_the_lattice_is_built(designer):
    """The cap has to bite inside the loop, not after it returns.

    1e9 nodes per octave needs ~3.7e9 iterations over [1, 13] nm. Checking
    ``enum_max_nodes`` on the way back cannot help with that.
    """
    with _deadline(10.0):
        with pytest.raises(ValueError, match="exceed"):
            designer.lattice(1.0, 13.0, _params(enum_per_octave=1e9),
                             max_nodes=5000)


def test_a_cancel_lands_inside_the_lattice_construction(designer):
    """Cancel used to do nothing until the lattice was finished."""
    polls = []

    def cancel():
        polls.append(len(polls))
        return len(polls) > 2

    with _deadline(10.0):
        out = designer.lattice(1.0, 1e9, _params(enum_per_octave=64),
                               max_nodes=10 ** 7, should_cancel=cancel)
    assert polls, "should_cancel was never asked"
    assert len(out) < 10 ** 7


def test_the_shipped_densities_are_untouched_by_the_validation(designer):
    """Everything the panel can produce still builds the lattice it always did."""
    for per_octave in (None, 0, 1, 3, 8, 64):
        nodes = designer.lattice(1.0, 13.0, _params(enum_per_octave=per_octave))
        assert nodes[0] == 1.0
        assert nodes[-1] <= 13.0
        assert all(b > a for a, b in zip(nodes, nodes[1:]))
    assert len(designer.lattice(1.0, 13.0, _params(enum_per_octave=8))) == 30


# ─── D7: the alias search may not unpin or leave the box ────────────────────

def test_the_alias_search_can_never_unpin_a_pinned_dimension(designer):
    """It scaled every entry of ``dims``, ``p['fixed']`` included.

    Measured in ΔE with ``d2`` pinned at 5.0 nm: (3.0, 5.0) -> (1.5, 2.5) and
    (3.5, 5.0) -> (0.875, 1.25), the second with R below the 1.0 nm floor —
    and the candidate table went on reporting "L_z = 5 nm" for both rows.
    Pinning is the headline answer to the L_z runaway; a pin that holds only
    usually is not a pin.
    """
    p = _pinned()
    for R in (3.0, 3.5, 8.0, 12.0):
        sol = designer.extract_solution([R], p)
        out = designer.primary_alias(sol, p)
        assert out['dims'][1] == 5.0, f"the pin broke at R = {R}"
        assert designer.in_search_range(out['dims'], p)
        assert out['dims'][0] >= p['Lmin']
    # It still aliases the FREE dimension: 8 nm is really 4 nm here.
    sol = designer.extract_solution([8.0], p)
    assert designer.primary_alias(sol, p)['dims'][0] == pytest.approx(4.0)


def test_the_alias_search_gates_on_the_per_dimension_box(designer):
    """Its only range test was the geometric MEAN against ``Lmin``.

    ``confinement_size_nm`` cannot see an individual dimension, so an alias
    could put R below its own floor while the mean stayed respectable.
    """
    boxed = _params(box={'d1': (3.0, 13.0), 'd2': (1.0, 13.0)})
    sol = designer.extract_solution([12.0, 10.0], boxed)
    out = designer.primary_alias(sol, boxed)
    assert out['dims'][0] >= 3.0
    assert designer.in_search_range(out['dims'], boxed)

    # Without that box the same start is allowed further down, which is what
    # shows the gate is the box and not the arithmetic.
    plain = _params()
    sol = designer.extract_solution([12.0, 10.0], plain)
    assert designer.primary_alias(sol, plain)['dims'][0] < 3.0


def test_an_aliased_candidate_is_re_annotated_for_its_new_geometry(designer):
    """Degeneracies, ties and flat dimensions are facts about a geometry."""
    p = _pinned()
    sol = designer.extract_solution([8.0], p)
    before = list(sol['flat_dims']), sol.get('n_tied')
    out = designer.primary_alias(sol, p)
    assert out['dims'][0] == pytest.approx(4.0)
    assert 'flat_dims' in out and 'resolution_eV' in out
    assert (list(out['flat_dims']), out.get('n_tied')) != (None, None)
    assert before is not None


# ─── D10(b): one bad candidate is dropped, never the whole enumeration ──────

def test_one_unbuildable_candidate_does_not_abort_the_enumeration(monkeypatch):
    """``extract_solution`` sat outside every ``try``.

    It reaches ``annotate`` -> ``flat_dims`` -> ``score_dims``, so anything
    the level tables or the sensitivity probe can raise took the entire
    population down with it and returned nothing at all — where
    ``find_solutions``, which wraps the same block, merely drops the
    candidate.
    """
    p = _cheap(8.0)
    good = Designer(seed=1).enumerate_solutions(p)
    assert len(good) >= 2

    real = Designer.annotate
    calls = []

    def flaky(self, sol, params):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("no level table for this geometry")
        return real(self, sol, params)

    monkeypatch.setattr(Designer, "annotate", flaky)
    out = Designer(seed=1).enumerate_solutions(p)

    assert len(calls) > 1, "the enumeration stopped at the first failure"
    assert out, "one bad candidate emptied the whole population"
    assert len(out) >= len(good) - 1


# ─── D10(d): "mixed" is graded, and both its terms are relative errors ──────

#: A ladder the measurement resolves: the nearest level is fifty times better
#: in energy than the cheap one. Energy should decide.
MIXED_RESOLVED = [(0.100, (1, 1)), (0.1049, (5, 5))]
MIXED_RESOLVED_ET = np.array([0.105])

#: A ladder that crowds: the cheap level is only five times worse, inside the
#: window ``ASSIGN_LOW_QN`` admits. The quantum number should break the tie.
MIXED_CROWDED = [(0.1 * (1 - 5e-5), (1, 1)), (0.1 * (1 + 1e-5), (5, 5))]
MIXED_CROWDED_ET = np.array([0.1])


def test_mixed_lets_the_energy_decide_when_the_data_resolves_the_ladder():
    """``rel_err + 0.01 * sum(qn)`` added a relative error to an integer.

    The terms have no common scale, so which one decides depends entirely on
    how good the fit is — and on a good fit it was never the energy. At
    ``rel_err`` ~ 0.005 one unit of quantum number was worth twice the whole
    energy error. Here the cheap level is 4.8 % out and the old rule still
    took it: 0.0476 + 0.02 = 0.0676 against 0.00095 + 0.10 = 0.101.
    """
    old = min(range(len(MIXED_RESOLVED)),
              key=lambda k: abs(MIXED_RESOLVED[k][0] - MIXED_RESOLVED_ET[0])
              / MIXED_RESOLVED_ET[0] + 0.01 * sum(MIXED_RESOLVED[k][1]))
    assert MIXED_RESOLVED[old][1] == (1, 1), "the old rule's answer moved"

    got = Designer.find_matches(MIXED_RESOLVED, MIXED_RESOLVED_ET,
                                assign=ASSIGN_MIXED)
    assert got[0]['qn'] == (5, 5)
    by_energy = Designer.find_matches(MIXED_RESOLVED, MIXED_RESOLVED_ET,
                                      assign=ASSIGN_ENERGY)
    assert got[0]['qn'] == by_energy[0]['qn']


def test_mixed_still_prefers_the_cheap_state_where_the_levels_crowd():
    """Graded, not abolished: inside the low-qn window the quantum number wins.

    The penalty is spent across the ladder's own range of ``sum(qn)`` and
    scaled to nine times its own best relative error — exactly the window
    ``ASSIGN_LOW_QN`` admits, continuously instead of as a veto.
    """
    got = Designer.find_matches(MIXED_CROWDED, MIXED_CROWDED_ET,
                                assign=ASSIGN_MIXED)
    by_qn = Designer.find_matches(MIXED_CROWDED, MIXED_CROWDED_ET,
                                  assign=ASSIGN_LOW_QN)
    by_energy = Designer.find_matches(MIXED_CROWDED, MIXED_CROWDED_ET,
                                      assign=ASSIGN_ENERGY)
    assert got[0]['qn'] == (1, 1)
    assert got[0]['qn'] == by_qn[0]['qn']
    assert by_energy[0]['qn'] == (5, 5)


def test_the_mixed_penalty_is_measured_in_the_ladders_own_error():
    """Both terms are relative errors of the SAME ladder, so the rule is
    invariant when the ladder's quantum numbers are relabelled upward.

    ``0.01 * sum(qn)`` was not: it grew without bound while the energy term
    stayed in [0, 1].
    """
    inflated = [(E, tuple(q + 40 for q in qn)) for E, qn in MIXED_RESOLVED]
    got = Designer.find_matches(inflated, MIXED_RESOLVED_ET,
                                assign=ASSIGN_MIXED)
    assert tuple(int(q) - 40 for q in got[0]['qn']) == (5, 5)

    # A ladder with one distinct sum(qn) has no range to spend the penalty
    # over, and must fall back to energy rather than divide by zero.
    flat_qn = [(0.100, (2, 2)), (0.1049, (2, 2))]
    got = Designer.find_matches(flat_qn, MIXED_RESOLVED_ET, assign=ASSIGN_MIXED)
    assert got[0]['computed_E'] == 0.1049
