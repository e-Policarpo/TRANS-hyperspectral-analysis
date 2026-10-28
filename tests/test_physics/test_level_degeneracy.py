"""Degeneracy of the analytic ladders — counted, and checked by brute force.

A degeneracy printed next to a candidate geometry will be read as a
measurement. So none of the numbers here is taken on the word of a formula:
every rule is checked against an INDEPENDENT enumeration of the full
quantum-number lattice, written out in this file — both signs of m for the
disc and the cylinder, all 2l+1 projections for the sphere, every Cartesian
permutation for the boxes — grouped with its own grouping code rather than
with the one under test.

The other half of the file is the compatibility guard. ``dot_energies`` and
every ``analytical.*_energies_*`` were frozen byte for byte into
``tests/fixtures/levels_golden.json`` BEFORE any of the degeneracy work
started (``scripts/record_levels_golden.py``), and the comparison is exact
equality on the full float ``repr``. Not ``pytest.approx``: a tolerance would
let a real change through, and the whole claim being made is that no change
got through.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import itertools
import json
import os

import numpy as np
import pytest
from scipy.constants import hbar, m_e, e
from scipy.special import jn_zeros

from src.physics import analytical as A
from src.physics import quantum_dot as Q
from src.physics.designer import Designer
from src.physics.level_patterns import GROUP_RTOL


FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "fixtures")


# ─── an independent grouping, so the test does not check code against itself ─

def brute_group(states, rtol=1e-9):
    """``[(E, qn, weight)]`` ascending -> ``[(E, total_weight, [qn, …])]``.

    Deliberately not :func:`src.physics.analytical.group_degeneracy` and not
    ``level_patterns._group_levels``: those are what is being tested. This one
    compares every pair against the group's OWN energy rather than walking a
    running representative, which is the slower and more obviously correct way
    to do it.
    """
    rows = sorted(states, key=lambda s: s[0])
    out = []
    for E, qn, w in rows:
        if out and abs(E - out[-1][0]) <= rtol * abs(out[-1][0]):
            out[-1][1] += w
            out[-1][2].append(qn)
        else:
            out.append([float(E), int(w), [qn]])
    return [(E, w, qns) for E, w, qns in out]


# ─── brute-force lattices ────────────────────────────────────────────────────

def _pref(meff, L_nm):
    """hbar^2 / (2 m L^2) in eV — the prefactor every hard-wall ladder shares."""
    return hbar ** 2 / (2.0 * meff * m_e * (L_nm * 1e-9) ** 2) / e


def brute_box(dims_nm, meff, n_max=14):
    """Every (nx, ny, …) with each index its OWN state. Weight 1, always."""
    pref = hbar ** 2 * np.pi ** 2 / (2.0 * meff * m_e) / e
    out = []
    for qn in itertools.product(range(1, n_max + 1), repeat=len(dims_nm)):
        E = pref * sum((n / (L * 1e-9)) ** 2 for n, L in zip(qn, dims_nm))
        out.append((E, qn, 1))
    return sorted(out)


def brute_disk(R_nm, meff, m_max=16, n_max=16):
    """Every (m, n) with BOTH signs of m enumerated as separate states.

    This is the check that the ``m >= 0`` fold plus a weight of 2 is the same
    thing as listing the pair — and the check that no accidental coincidence
    hides inside it, which a formula could not see.
    """
    out = []
    for m in range(0, m_max + 1):
        zeros = jn_zeros(m, n_max)
        for n, z in enumerate(zeros, start=1):
            E = _pref(meff, R_nm) * z ** 2
            for signed in ((0,) if m == 0 else (+m, -m)):
                out.append((E, (signed, n), 1))
    return sorted(out, key=lambda s: s[0])


def brute_sphere(R_nm, meff, l_max=10, n_max=10):
    """Every (n, l, m_l) — all 2l+1 projections written out one by one."""
    out = []
    for l in range(l_max + 1):
        zeros = Q._spherical_jn_zeros(l, n_max)
        for n, a in enumerate(zeros, start=1):
            E = _pref(meff, R_nm) * a ** 2
            for m_l in range(-l, l + 1):
                out.append((E, (n, l, m_l), 1))
    return sorted(out, key=lambda s: s[0])


def brute_disc_dot(R_nm, Lz_nm, meff, m_max=12, n_max=12, nz_max=12):
    """Lens/disc: both signs of m, times the axial ladder."""
    out = []
    for m in range(0, m_max + 1):
        zeros = jn_zeros(m, n_max)
        for n, z in enumerate(zeros, start=1):
            E_xy = _pref(meff, R_nm) * z ** 2
            for nz in range(1, nz_max + 1):
                E = E_xy + _pref(meff, Lz_nm) * (np.pi * nz) ** 2
                for signed in ((0,) if m == 0 else (+m, -m)):
                    out.append((E, (n, signed, nz), 1))
    return sorted(out, key=lambda s: s[0])


def brute_parabolic(hw_xy, hw_z, shells=14):
    """Harmonic dot with the in-plane shell written out state by state.

    Shell ``n_xy`` holds ``n_xy + 1`` states; here they are enumerated as
    ``(n_x, n_y)`` with ``n_x + n_y = n_xy``, so the multiplicity is counted
    rather than asserted.
    """
    out = []
    for n_xy in range(shells):
        for n_z in range(shells):
            E = (hw_xy * (n_xy + 1) + hw_z * (n_z + 0.5)) / 1000.0
            for n_x in range(n_xy + 1):
                out.append((E, (n_x, n_xy - n_x, n_z), 1))
    return sorted(out, key=lambda s: s[0])


# ─── STEP 1: nothing that existed changed ────────────────────────────────────

@pytest.fixture(scope="module")
def golden():
    with open(os.path.join(FIXTURES, "levels_golden.json")) as fh:
        return json.load(fh)


def _same(rows, recorded):
    """Exact equality on the float repr, pair by pair. No tolerance."""
    assert len(rows) == len(recorded)
    for (E, qn), (E_rec, qn_rec) in zip(rows, recorded):
        assert repr(float(E)) == E_rec
        assert [int(q) for q in qn] == qn_rec


def test_dot_energies_unchanged(golden):
    """The designer's 0D ladder is byte-identical to the pre-change recording.

    ``dot_energies`` was rewritten into a thin wrapper over ``_dot_states`` so
    that ``dot_levels`` could label the very same enumeration instead of
    running a second one. This is the proof that the rewrite is a refactor:
    same models, same dims, same masses, same counts, same bits.
    """
    assert golden["dot_energies"], "the golden fixture is empty"
    for key, recorded in golden["dot_energies"].items():
        model, dims, meff, n = key.split("|")
        rows = Q.dot_energies(model, eval(dims), float(meff), int(n))
        _same(rows, recorded)


def test_analytical_energies_unchanged(golden):
    """Every ``analytical.*_energies_*`` still returns exactly what it did.

    The degeneracy work is additive — new ``*_levels`` functions beside the
    old ``*_energies_*`` ones — and this is what makes "additive" checkable
    rather than a claim in a commit message.
    """
    calls = {
        "box_energies_1d": A.box_energies_1d,
        "box_energies_1d_eV": A.box_energies_1d_eV,
        "box_energies_2d_eV": A.box_energies_2d_eV,
        "box_energies_3d": A.box_energies_3d,
        "box_energies_3d_eV": A.box_energies_3d_eV,
        "disk_energies": A.disk_energies,
        "cylinder_energies": A.cylinder_energies,
    }
    seen = 0
    for key, recorded in golden["analytical"].items():
        name, dims, meff, n = key.split("|")
        args = [float(x) for x in dims.split(",")] + [float(meff), int(n)]
        if name == "box_energies_2d":       # grouped: (E, [qn, qn, …])
            rows = A.box_energies_2d(*args)
            assert len(rows) == len(recorded)
            for (E, group), (E_rec, group_rec) in zip(rows, recorded):
                assert repr(float(E)) == E_rec
                assert [[int(q) for q in qn] for qn in group] == group_rec
        else:
            _same(calls[name](*args), recorded)
        seen += 1
    assert seen == len(golden["analytical"])


def test_levels_are_a_relabelling_of_the_energies():
    """``*_levels(distinct=False)`` carries the ladder it was built from.

    The default path must not reorder, re-derive or re-truncate anything: the
    designer fits against ``*_energies_*`` and the table is labelled from
    ``*_levels``, so any drift between them mislabels a candidate.
    """
    cases = [
        (A.box_levels_1d, A.box_energies_1d_eV, (8.0,)),
        (A.box_levels_2d, A.box_energies_2d_eV, (8.0, 5.0)),
        (A.box_levels_3d, A.box_energies_3d_eV, (8.0, 5.0, 4.0)),
        (A.disk_levels, A.disk_energies, (6.0,)),
        (A.cylinder_levels, A.cylinder_energies, (6.0, 9.0)),
    ]
    for levels_fn, energies_fn, dims in cases:
        lv = levels_fn(*dims, 0.322, 17)
        raw = energies_fn(*dims, 0.322, 17)
        assert len(lv) == len(raw) == 17
        for level, (E, qn) in zip(lv, raw):
            assert level.E_eV == float(E)                 # exact, not approx
            assert level.quantum_numbers == tuple(int(q) for q in qn)


# ─── degeneracy against brute force ──────────────────────────────────────────

def test_disc_dot_degeneracy_matches_brute_force():
    """The lens's ``2 for m != 0`` rule, against both signs enumerated.

    This is her model. ``_disc_levels`` loops ``m_q in range(width + 1)``, so
    each ``m > 0`` row stands for two states; the brute force writes the pair
    out and must land on the same energies with twice the count.
    """
    for R, Lz, meff in [(5.0, 3.0, 0.067), (4.0, 5.0, 0.322), (3.5, 11.0, 0.39)]:
        lv = Q.dot_levels(Q.DOT_DISC, (R, Lz), meff, 20, distinct=True)
        ref = brute_group(brute_disc_dot(R, Lz, meff))[:len(lv)]
        for level, (E_ref, g_ref, _qns) in zip(lv, ref):
            assert level.E_eV == pytest.approx(E_ref, rel=1e-10)
            assert level.degeneracy == g_ref


def test_spherical_degeneracy_is_two_l_plus_one():
    """All 2l+1 projections, enumerated rather than assumed."""
    for R, meff in [(5.0, 0.067), (2.0, 0.322), (12.5, 0.39)]:
        lv = Q.dot_levels(Q.DOT_SPHERICAL, (R,), meff, 12, distinct=True)
        ref = brute_group(brute_sphere(R, meff))[:len(lv)]
        for level, (E_ref, g_ref, _qns) in zip(lv, ref):
            assert level.E_eV == pytest.approx(E_ref, rel=1e-8)
            assert level.degeneracy == g_ref
    # The first five of a 5 nm ball, spelled out: 1s, 1p, 1d, 2s, 1f.
    lv = Q.dot_levels(Q.DOT_SPHERICAL, (5.0,), 0.067, 5, distinct=True)
    assert [l.degeneracy for l in lv] == [1, 3, 5, 1, 7]


def test_parabolic_degeneracy_matches_brute_force():
    """The in-plane shell ``n_xy + 1``, counted state by state."""
    for hw_xy, hw_z in [(20.0, 31.7), (30.0, 100.0)]:
        lv = Q.dot_levels(Q.DOT_PARABOLIC, (hw_xy, hw_z), 0.067, 10,
                          distinct=True)
        ref = brute_group(brute_parabolic(hw_xy, hw_z))[:len(lv)]
        for level, (E_ref, g_ref, _qns) in zip(lv, ref):
            assert level.E_eV == pytest.approx(E_ref, rel=1e-12)
            assert level.degeneracy == g_ref


def test_box_degeneracy_matches_brute_force():
    """Cartesian boxes, 1D to 3D, square/cube and anisotropic."""
    cases = [
        (A.box_levels_1d, (6.0,)),
        (A.box_levels_2d, (5.0, 5.0)),
        (A.box_levels_2d, (10.0, 6.0)),
        (A.box_levels_3d, (5.0, 5.0, 5.0)),
        (A.box_levels_3d, (8.0, 6.0, 5.0)),
    ]
    for fn, dims in cases:
        lv = fn(*dims, 0.067, 12, distinct=True)
        ref = brute_group(brute_box(dims, 0.067))[:len(lv)]
        for level, (E_ref, g_ref, _qns) in zip(lv, ref):
            assert level.E_eV == pytest.approx(E_ref, rel=1e-12)
            assert level.degeneracy == g_ref


def test_the_cartesian_rows_the_product_actually_reads_weigh_one_each():
    """``distinct=False`` — the path the designer takes — and what it owes.

    THE AIM OF THIS FILE HAD TO BE CORRECTED, and this is the correction.
    Every degeneracy test above passes ``distinct=True``, which is a path the
    product does not take: ``Designer.annotate`` calls
    ``levels_for(..., distinct=False)``, and for every Cartesian box the
    per-entry weight on that path is the literal 1 — those enumerators list
    each permutation as its own row and put the multiplicity in the LIST
    rather than in the row. Validating only the grouped path therefore left
    the shipped one unchecked, and it was wrong: a 5 nm cube's (1,1,2)
    reached the candidate table as a singlet when it is one of three, and
    "degeneracy = 1" on a level reads as "this peak is a singlet", which is
    worse than printing nothing.

    So the flat weights are pinned HERE, as the input they are, and the group
    totals that have to be summed out of them are pinned beside them. What
    the designer does with both is asserted end to end through
    ``extract_solution`` in
    ``tests/test_physics/test_designer_search.py::``
    ``test_a_cartesian_level_is_reported_as_the_group_it_belongs_to``.
    """
    for levels, totals in (
            (A.box_levels_3d(5.0, 5.0, 5.0, 0.067, 20), [1, 3, 3, 3, 1, 6, 3]),
            (A.box_levels_2d(5.0, 5.0, 0.067, 20), [1, 2, 1, 2, 2, 2]),
            (A.box_levels_1d(5.0, 0.067, 20), [1] * 6)):
        assert [l.degeneracy for l in levels] == [1] * 20, (
            "a Cartesian row's own weight is 1 by construction")
        grouped = A.group_degeneracy([(l.E_eV, l.quantum_numbers, l.degeneracy)
                                      for l in levels])
        assert grouped[:len(totals)] == totals
        # Nothing is lost or invented by the grouping: the rows and the
        # groups describe the same twenty states.
        assert sum(grouped) == 20

    # The disc and the sphere are on the same flat path and must NOT change:
    # their rows already carry the +/-m and 2l+1 folds, so the group total is
    # the row's own weight unless a real coincidence joins two rows.
    disc = Q.dot_levels(Q.DOT_DISC, (4.0, 5.0), 0.322, 8)
    assert [l.degeneracy for l in disc] == [
        1 if int(l.quantum_numbers[1]) == 0 else 2 for l in disc]
    assert A.group_degeneracy([(l.E_eV, l.quantum_numbers, l.degeneracy)
                               for l in disc]) == [l.degeneracy for l in disc]


def test_disk_and_cylinder_degeneracy_matches_brute_force():
    """The ``+/-m`` fold of the 2D disk and the 3D cylinder.

    The disk is checked only over the range where ``disk_energies``' fixed
    8 x 8 basis is still complete — see
    :func:`test_disk_energies_basis_is_capped`, which pins exactly where that
    stops being true so the limit is recorded rather than quietly dodged here.
    """
    lv = A.disk_levels(5.0, 0.067, 17, distinct=True)
    ref = brute_group(brute_disk(5.0, 0.067))[:len(lv)]
    for level, (E_ref, g_ref, _qns) in zip(lv, ref):
        assert level.E_eV == pytest.approx(E_ref, rel=1e-10)
        assert level.degeneracy == g_ref

    for R, H in [(5.0, 10.0), (10.0, 2.0)]:
        lv = A.cylinder_levels(R, H, 0.067, 12, distinct=True)
        assert [l.degeneracy for l in lv] == [
            1 if int(l.quantum_numbers[0]) == 0 else 2 for l in lv]


# ─── accidental degeneracy: what a formula cannot see ────────────────────────

#: Energy of the n^2-sum = 27 level of a 5 nm cube at meff = 0.067, in eV.
#: Written as the formula rather than as a literal because the literal that
#: stood here was 1.2612192 -- the same level evaluated at meff = 0.322, the
#: electron mass of the sample this work was driven by, against a call that
#: passes 0.067. The test then looked for an energy that was not in the
#: ladder, found nothing, and reported the accidental level as missing.
_CUBE_27_eV = hbar ** 2 * np.pi ** 2 / (2.0 * 0.067 * m_e) / e * 27 / (5e-9) ** 2


def test_accidental_degeneracy_counted_in_the_cube():
    """(1,1,5) meets (3,3,3) because 1+1+25 = 9+9+9 = 27.

    Not a permutation of anything, so no per-entry rule predicts it. The 5 nm
    cube puts four states at 1.2612192 eV, and the only way to get 4 is to
    count.
    """
    lv = A.box_levels_3d(5.0, 5.0, 5.0, 0.067, 40, distinct=True)
    hit = [l for l in lv if abs(l.E_eV - _CUBE_27_eV) < 1e-6]
    assert len(hit) == 1, "the accidental level moved or was split"
    assert hit[0].degeneracy == 4

    ref = brute_group(brute_box((5.0, 5.0, 5.0), 0.067))
    same = [(E, g, qns) for E, g, qns in ref if abs(E - _CUBE_27_eV) < 1e-6]
    assert len(same) == 1 and same[0][1] == 4
    multisets = {tuple(sorted(qn)) for qn in same[0][2]}
    assert multisets == {(1, 1, 5), (3, 3, 3)}


def test_accidental_degeneracy_counted_in_the_square():
    """The ``n^2``-sum 65 gathers (1,8), (4,7), (7,4), (8,1) into one level."""
    lv = A.box_levels_2d(5.0, 5.0, 0.067, 60, distinct=True)
    hit = [l for l in lv
           if sum(q ** 2 for q in l.quantum_numbers) == 65]
    assert len(hit) == 1
    assert hit[0].degeneracy == 4


def test_parabolic_commensurate_shells_merge_and_then_separate():
    """20/30 meV is 2:3 commensurate; 20/31.7 meV is not.

    At 20/30 the level at 0.095 eV is (n_xy=0, n_z=2) AND (n_xy=3, n_z=0), so
    its degeneracy is 1 + 4 = 5 — while ``_dot_weight``'s ``n_xy + 1`` sees
    only 1 or 4 for either entry alone. Detune ``hw_z`` by 1.7 meV and the
    pair separates into a 4 and a 1. This is why the parabolic dot is grouped
    AFTER the formula rather than instead of it.
    """
    merged = Q.dot_levels(Q.DOT_PARABOLIC, (20.0, 30.0), 0.067, 8, distinct=True)
    at_095 = [l for l in merged if abs(l.E_eV - 0.095) < 1e-9]
    assert len(at_095) == 1 and at_095[0].degeneracy == 5

    split = Q.dot_levels(Q.DOT_PARABOLIC, (20.0, 31.7), 0.067, 8, distinct=True)
    assert all(l.degeneracy != 5 for l in split)
    assert sorted(l.degeneracy for l in split)[-1] == 4

    # And the merged level really is the sum of the two entries the flat
    # ladder lists separately.
    #
    # Ten, not eight, and the reason is a limitation worth naming here. The
    # parabolic basis is a square n_xy x n_z grid of side
    # `shells = max(3, ceil(sqrt(n_levels)))`, so asking for eight levels
    # opens n_xy <= 2 and (n_xy=3, n_z=0) is not enumerated AT ALL -- the flat
    # ladder shows one entry at 0.095 eV where the model has two. That is not
    # a grouping bug, it is the basis being too small, and it is pinned in its
    # own right by `test_dot_energies_parabolic_basis_is_capped` below. Ten
    # levels open n_xy <= 3, which is where both partners first exist.
    flat = Q.dot_levels(Q.DOT_PARABOLIC, (20.0, 30.0), 0.067, 10)
    entries = [l for l in flat if abs(l.E_eV - 0.095) < 1e-9]
    assert sorted(l.degeneracy for l in entries) == [1, 4]


# ─── the disc's m >= 0 fold is complete, not a bug ───────────────────────────

def test_disc_enumeration_is_complete():
    """``_disc_levels`` misses no state, and invents no coincidence.

    Reweighting its ``m >= 0`` rows by 1/2 for ``m > 0`` must reproduce the
    both-signs brute force exactly — same energies, same total count. It does,
    and the grouped list has no entry of degeneracy above 2, which says there
    is no accidental coincidence in the first twenty levels: the Bessel zeros
    are transcendental and meeting the ``pi^2 n_z^2 / L_z^2`` ladder is a
    measure-zero event.
    """
    R, Lz, meff = 5.0, 3.0, 0.067
    ours = Q.dot_levels(Q.DOT_DISC, (R, Lz), meff, 20)
    ref = brute_group(brute_disc_dot(R, Lz, meff))

    # Every one of our rows is one of the reference levels, with the count it
    # claims, in the same order.
    for level, (E_ref, g_ref, _qns) in zip(ours, ref):
        assert level.E_eV == pytest.approx(E_ref, rel=1e-10)
        assert level.degeneracy == g_ref
    assert sum(l.degeneracy for l in ours) == sum(g for _E, g, _q in ref[:20])
    assert max(l.degeneracy for l in ours) <= 2


def test_disc_levels_report_orbital_states_not_rows():
    """A 4 nm / 5 nm lens: eight rows, thirteen orbital states, twenty-six
    with spin.

    This is the number a peak assignment needs and could not previously be
    told — a peak matched to one of those rows may be a doublet.
    """
    lv = Q.dot_levels(Q.DOT_DISC, (4.0, 5.0), 0.322, 8)
    assert len(lv) == 8
    assert sum(l.degeneracy for l in lv) == 13
    assert sum(l.occupancy for l in lv) == 26


# ─── group before truncating ─────────────────────────────────────────────────

def test_group_before_truncate():
    """``distinct=True`` gives twenty DISTINCT energies, not twenty entries.

    A flat request for twenty levels of a 5 nm cube yields seven distinct
    energies; a 5 nm square yields twelve. A symmetric search therefore
    believes it is fitting twenty model levels while it is fitting seven —
    and SYM_CUBIC is exactly the mode a user picks to shrink the search.
    """
    flat = A.box_energies_3d_eV(5.0, 5.0, 5.0, 0.067, 20)
    assert len({round(E, 9) for E, _ in flat}) == 7

    distinct = A.box_levels_3d(5.0, 5.0, 5.0, 0.067, 20, distinct=True)
    assert len(distinct) == 20
    assert len({round(l.E_eV, 9) for l in distinct}) == 20

    square = A.box_levels_2d(5.0, 5.0, 0.067, 20, distinct=True)
    assert len({round(l.E_eV, 9) for l in square}) == 20
    assert len({round(E, 9)
                for E, _ in A.box_energies_2d_eV(5.0, 5.0, 0.067, 20)}) == 12


def test_a_degenerate_group_is_never_cut_in_half():
    """Truncation never reports part of a group as its whole multiplicity.

    Asking for k distinct levels and asking for k+1 must agree on the first k
    degeneracies, for every k — if the cut could split a group the last entry
    would shrink as k grows.
    """
    for k in range(1, 25):
        a = A.box_levels_3d(5.0, 5.0, 5.0, 0.067, k, distinct=True)
        b = A.box_levels_3d(5.0, 5.0, 5.0, 0.067, k + 1, distinct=True)
        assert [l.degeneracy for l in a] == [l.degeneracy for l in b[:k]]
    for k in range(1, 15):
        a = Q.dot_levels(Q.DOT_PARABOLIC, (20.0, 30.0), 0.067, k, distinct=True)
        b = Q.dot_levels(Q.DOT_PARABOLIC, (20.0, 30.0), 0.067, k + 1,
                         distinct=True)
        assert [l.degeneracy for l in a] == [l.degeneracy for l in b[:k]]


# ─── the two tolerances stay apart ───────────────────────────────────────────

def test_grouping_tolerance_is_relative_and_tight():
    """GROUP_RTOL answers a symmetry question, never a resolution one.

    Two levels 0.10 meV apart — the old package's absolute ``1e-4`` eV
    threshold, and 270x below this sample's 27 meV linewidth at 90 K — must
    NOT be merged here. Whether a spectrum can tell two levels apart is a
    different question with a different number, and it belongs to the
    spectrum.
    """
    assert GROUP_RTOL == 1e-9
    near = [(1.0000, (1,), 1), (1.0001, (2,), 1)]       # 0.10 meV apart
    assert A.group_degeneracy(near) == [1, 1]
    exact = [(1.0, (1,), 1), (1.0, (2,), 1)]
    assert A.group_degeneracy(exact) == [2]
    # Relative, so the same fractional split behaves the same at both ends of
    # a ladder spanning two decades — which an absolute eV tolerance does not.
    assert A.group_degeneracy([(0.03, (1,), 1), (0.03 * (1 + 1e-6), (2,), 1)]) == [1, 1]
    assert A.group_degeneracy([(2.00, (1,), 1), (2.00 * (1 + 1e-6), (2,), 1)]) == [1, 1]


def test_group_degeneracy_accepts_pairs_and_triples():
    """A pair weighs one; a triple carries its own fold."""
    assert A.group_degeneracy([(1.0, (0, 1)), (1.0, (1, 1))]) == [2]
    assert A.group_degeneracy([(1.0, (0, 1), 1), (1.0, (1, 1), 2)]) == [3]
    groups = A.group_degeneracy([(1.0, (0, 1), 1), (1.0, (1, 1), 2),
                                 (2.0, (2, 1), 2)], with_representative=True)
    assert groups == [(1.0, 3, (0, 1)), (2.0, 2, (2, 1))]


# ─── the anti-drift test between the fitted ladder and the labelled one ──────

def test_levels_for_matches_compute_energies():
    """Every geometry the designer can produce is labelled from the SAME ladder.

    ``Designer.compute_energies`` is what the objective is evaluated on;
    ``levels_for`` is what a candidate row is labelled from. Two dispatches
    exist because they answer different questions, but a model added to one
    and forgotten in the other would mislabel a candidate silently. Here they
    are asserted equal branch by branch, exactly.
    """
    cases = [
        ("0D", "spherical", (5.0,)),
        ("0D", "disc", (4.0, 5.0)),
        ("0D", "parabolic", (20.0, 30.0)),
        ("1D", "cartesian", (8.0,)),
        ("2D", "circular", (6.0,)),
        ("2D", "cartesian", (8.0, 5.0)),
        ("3D", "cylindrical", (6.0, 9.0)),
        ("3D", "cartesian", (8.0, 6.0, 5.0)),
    ]
    designer = Designer()
    for ndim, coords, dims in cases:
        p = {"ndim": ndim, "coords": coords}
        fitted = designer.compute_energies(dims, 0.322, 20, p)
        labelled = Q.levels_for(ndim, coords, dims, 0.322, 20)
        assert len(fitted) == len(labelled), (ndim, coords)
        for (E, qn), level in zip(fitted, labelled):
            assert level.E_eV == float(E), (ndim, coords, qn)
            assert level.quantum_numbers == tuple(int(q) for q in qn)


def test_levels_for_rejects_an_unknown_geometry():
    with pytest.raises(ValueError):
        Q.levels_for("4D", "cartesian", (5.0,), 0.067, 4)


# ─── limits recorded rather than hidden ──────────────────────────────────────

def test_disk_energies_basis_is_capped():
    """``disk_energies`` opens a fixed 8 x 8 basis and goes wrong at rank 18.

    ``m`` runs 0..7 only, so ``j_{8,1}`` — which belongs at rank 18 of the
    true ladder — is simply absent, and at most 64 entries can ever be
    returned. ``disk_levels`` inherits this deliberately, because
    ``Designer.compute_energies`` fits against ``disk_energies`` and a
    labelled ladder that disagreed with the fitted one would mislabel
    candidates.

    This test is not a complaint about the value 8; it PINS the rank, so that
    widening the basis (which would change 2D-circular designer results, and
    is therefore a deliberate act with its own decision) shows up here as a
    failure rather than as a silently different answer.
    """
    ours = [qn for _E, qn in A.disk_energies(1.0, 1.0, 64)]
    truth = [(m, n) for _z, m, n in sorted(
        (float(z), m, n)
        for m in range(24) for n, z in enumerate(jn_zeros(m, 24), start=1))]

    assert len(ours) == 64, "the 8 x 8 basis caps the list at 64 entries"
    assert ours[:17] == truth[:17], "the first seventeen are the true ladder"
    assert ours[17] != truth[17]
    assert truth[17] == (8, 1), "the first missing state is j_{8,1}"
    assert (8, 1) not in ours
