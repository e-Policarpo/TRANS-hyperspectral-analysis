"""
Electron-hole pairing of the inverse designer's candidates.

One well confines both carriers at once, and it is the *same* geometry that
produces the two ladders of levels — but with different effective masses, so
each carrier is a separate search. What ties the two together is the
geometry: the good solution is the pair whose dimensions agree.

They do not agree exactly, and should not: each carrier's fit is numerical
and the effective masses are known loosely. 7.91 nm for the electron and
8.09 nm for the hole describe the same dot. Hence the tolerance, in
nanometres, and a pair error that adds the three disagreements — the
electron's, the hole's, and the one between the two geometries — in the same
relative unit.

No UI and no solver: just data.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, List, Optional, Sequence

from src.physics.quantum_dot import DOT_PARABOLIC, length_from_hw

logger = logging.getLogger(__name__)


def dims_in_nm(sol: dict, meff: Optional[float] = None) -> tuple:
    """The candidate's dimensions in nanometres.

    Almost every geometry already stores nm. The parabolic dot stores
    hbar*omega in meV, and converting is mandatory here: hbar*omega depends
    on the mass, so the same confinement length gives different values for
    the electron and the hole. Comparing the meV directly would say the
    geometries disagree when they are the same one.
    """
    dims = tuple(sol.get("dims", ()))
    if sol.get("ndim") == "0D" and sol.get("coords") == DOT_PARABOLIC:
        m = meff if meff is not None else sol.get("meff", 0.067)
        return tuple(length_from_hw(d, m) for d in dims)
    return dims


def confinement_size_nm(sol: dict, meff: Optional[float] = None) -> float:
    """Effective confinement size, in nm.

    The geometric mean of the dimensions — the edge of the cube of equal
    volume, which is the quantity that sets the energy scale (see the
    designer's ``_confinement_size``).
    """
    dims = [abs(d) for d in dims_in_nm(sol, meff) if d]
    if not dims:
        return float("inf")
    return float(math.exp(sum(math.log(d) for d in dims) / len(dims)))


def geometry_mismatch(sol_a: dict, sol_b: dict) -> tuple:
    """``(deviation_nm, deviation_pct)`` between two candidates.

    The deviation is the **worst** dimension's, not the mean size's: a
    3 x 12 nm disc and a 12 x 3 nm one have the same effective size and are
    not the same thing. When the geometries have different numbers of
    dimensions (which should not happen — both carriers use the same model)
    only the effective-size comparison is left.
    """
    da = dims_in_nm(sol_a)
    db = dims_in_nm(sol_b)
    if len(da) != len(db) or not da:
        sa, sb = confinement_size_nm(sol_a), confinement_size_nm(sol_b)
        pairs = [(sa, sb)]
    else:
        pairs = list(zip(da, db))

    worst_nm, worst_pct = 0.0, 0.0
    for a, b in pairs:
        a, b = abs(float(a)), abs(float(b))
        diff = abs(a - b)
        mean = (a + b) / 2.0
        worst_nm = max(worst_nm, diff)
        worst_pct = max(worst_pct, (diff / mean * 100.0) if mean > 0 else 0.0)
    return worst_nm, worst_pct


def pair_score(rrmse_e: float, rrmse_h: float, mismatch_pct: float,
               geometry_weight: float = 1.0) -> float:
    """The pair's error, in %.

    All three disagreements are already relative: how far the electron
    misses its energies, how far the hole misses its own, and how far the
    two geometries differ. The root mean square of the three is the pair
    error — a pair is only good when all three terms are small, which is
    exactly the criterion wanted.
    """
    terms = [float(rrmse_e), float(rrmse_h),
             float(geometry_weight) * float(mismatch_pct)]
    return math.sqrt(sum(t * t for t in terms) / len(terms))


def pair_candidates(electrons: Sequence[dict], holes: Sequence[dict],
                    tol_nm: float = 1.0, max_pairs: int = 20,
                    geometry_weight: float = 1.0) -> List[dict]:
    """Match each electron candidate with the best hole candidate.

    One pair per electron geometry rather than every combination: 20 x 20
    would return 400 rows that are the same half-dozen geometries repeated.
    Pairs above the tolerance are dropped — that is what it means.

    Returns dicts ``{'electron', 'hole', 'mismatch_nm', 'mismatch_pct',
    'score', 'size_nm'}``, ordered by the pair error.
    """
    pairs = []
    for sol_e in electrons:
        best = None
        for sol_h in holes:
            mismatch_nm, mismatch_pct = geometry_mismatch(sol_e, sol_h)
            if mismatch_nm > tol_nm:
                continue
            score = pair_score(sol_e.get("RRMSE", float("inf")),
                               sol_h.get("RRMSE", float("inf")),
                               mismatch_pct, geometry_weight)
            if best is None or score < best["score"]:
                best = {
                    "electron": sol_e,
                    "hole": sol_h,
                    "mismatch_nm": mismatch_nm,
                    "mismatch_pct": mismatch_pct,
                    "score": score,
                    "size_nm": (confinement_size_nm(sol_e)
                                + confinement_size_nm(sol_h)) / 2.0,
                }
        if best is not None:
            pairs.append(best)

    pairs.sort(key=lambda p: p["score"])
    return pairs[:max_pairs]


# ── band edges from the energy offsets ──────────────────────────────────────

def band_edges(offset_e: float, offset_h: float, split_e: float = 0.0,
               split_h: float = 0.0) -> dict:
    """Band edges and gap, read off the offsets the fit returned.

    In STS the energy is counted from E_F and the model counts from the
    bottom of the well; the difference is the position of the band edge,
    which is precisely the offset that matching by delta-E has to estimate.
    That is: what looked like a nuisance parameter **is** the measurement.

    With ``offset = E_model - E_measured`` and the measured energies taken
    from the branch boundaries::

        E_c - E_F = split_e - offset_e
        E_v - E_F = split_h + offset_h
        E_gap     = (E_c - E_F) - (E_v - E_F)

    And this beats reading the gap off the curve: the peak-free window of a
    confined system is wider than the gap by E_1 + E_1h, because the first
    peak on each side already sits one confinement energy above its edge.
    The fit knows by how much, and subtracts it.

    Careful: the offset depends on which candidate you look at (an alias
    matches the same targets with different quantum numbers and a different
    offset). Use the best pair's.
    """
    E_c = float(split_e) - float(offset_e)
    E_v = float(split_h) + float(offset_h)
    return {"E_c": E_c, "E_v": E_v, "gap": E_c - E_v}


def edges_from_pair(pair: dict, split_e: float = 0.0,
                    split_h: float = 0.0) -> Optional[dict]:
    """:func:`band_edges` for one electron-hole pair, or None if a side is missing."""
    electron, hole = pair.get("electron"), pair.get("hole")
    if not electron or not hole:
        return None
    return band_edges(electron.get("offset", 0.0), hole.get("offset", 0.0),
                      split_e, split_h)


def edges_from_solutions(by_carrier: dict, pairs: Sequence[dict],
                         split_e: float = 0.0, split_h: float = 0.0
                         ) -> Optional[dict]:
    """``{'E_c', 'E_v', 'gap'}`` read off the offsets, or None.

    Each edge comes from its own side, and **one alone is already useful**:
    it is precisely when one branch fails — because a naive split tore a
    ladder in half — that the other edge is needed to fix the split. The gap
    does need both.

    ``pairs`` wins over ``by_carrier`` when it has anything: the two sides of
    a pair are mutually consistent, so preferring them avoids reading E_c off
    one candidate and E_v off another that disagrees with it.
    """
    if pairs:
        best_e = pairs[0].get('electron')
        best_h = pairs[0].get('hole')
    else:
        by = by_carrier or {}
        best_e = min(by.get('e', []), key=lambda s: s['RRMSE'], default=None)
        best_h = min(by.get('h', []), key=lambda s: s['RRMSE'], default=None)

    E_c = None if best_e is None else float(split_e) - best_e.get('offset', 0.0)
    E_v = None if best_h is None else float(split_h) + best_h.get('offset', 0.0)
    if E_c is None and E_v is None:
        return None
    gap = None if (E_c is None or E_v is None) else E_c - E_v
    return {'E_c': E_c, 'E_v': E_v, 'gap': gap}


def refine_boundaries(peaks, run_search: Callable[[object], dict],
                      split_e: float = 0.0, split_h: float = 0.0,
                      max_passes: int = 4, tol: float = 1e-3) -> tuple:
    """Move the branch boundaries onto the band edges the fit itself found.

    A fixed point, not a one-line calculation: the edges come out of the
    offsets, the offsets come out of the two searches, and the searches need
    the peaks already split. Start from whatever split there is (V = 0,
    usually), read the edges, split again, and repeat until the boundary
    stops moving.

    It converges even from a bad start because matching by delta-E does not
    need to know WHICH levels it was given: handed only the empty stretch of
    a ladder, it still finds L by matching n = 3, 4, 5 instead of 1, 2, 3.

    ``run_search`` takes a :class:`~src.physics.branches.DidvPeaks` and
    returns ``{'pairs': [...], 'by_carrier': {'e': [...], 'h': [...]}}`` —
    injected rather than imported, so this loop stays testable and the caller
    keeps control of threading and cancellation.

    Returns ``(peaks, history)``: the peaks as finally split, and one entry
    per pass.
    """
    from src.physics.branches import split_peaks

    history: List[dict] = []
    for _ in range(max_passes):
        found = run_search(peaks) or {}
        edges = edges_from_solutions(found.get('by_carrier') or {},
                                     found.get('pairs') or [],
                                     split_e, split_h)
        if edges is None:
            break

        # With only one side, the other boundary is pushed up against it:
        # E_v < E_c always, and everything below the conduction edge that is
        # not an electron is a candidate hole. Leaving the two crossed would
        # put the same peak in both branches.
        new_e = edges['E_c'] if edges['E_c'] is not None else edges['E_v']
        new_h = edges['E_v'] if edges['E_v'] is not None else new_e
        new_h = min(new_h, new_e)

        movement = max(abs(new_e - split_e), abs(new_h - split_h))
        history.append({'E_c': edges['E_c'], 'E_v': edges['E_v'],
                        'gap': edges['gap'], 'movement': movement,
                        'split_e': new_e, 'split_h': new_h})
        logger.info("refining boundaries: E_c=%s E_v=%s gap=%s (moved %.4f V)",
                    "-" if edges['E_c'] is None else f"{edges['E_c']:+.4f}",
                    "-" if edges['E_v'] is None else f"{edges['E_v']:+.4f}",
                    "-" if edges['gap'] is None else f"{edges['gap']:.4f}",
                    movement)
        if movement < tol:
            break

        resplit = split_peaks(peaks.peaks_V, new_e, new_h)
        if not resplit.electron_eV or not resplit.hole_eV:
            # A boundary that empties a branch is not an edge: it would trade
            # a poor fit for no fit at all.
            logger.warning("refining: boundaries %+.4f / %+.4f would leave a "
                           "branch empty — stopping", new_e, new_h)
            break

        resplit.curve = peaks.curve
        resplit.baseline = peaks.baseline
        resplit.corrected = peaks.corrected
        peaks = resplit
        split_e, split_h = new_e, new_h

    return peaks, history
