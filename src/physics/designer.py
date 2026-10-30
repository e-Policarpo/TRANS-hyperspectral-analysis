"""
The inverse designer: target energies in, candidate geometries out.

Given a ladder of measured levels, which well produces it? The search runs
over the well's dimensions in nanometres — including the parabolic dot,
whose natural parameters are energies: the confinement length l is what is
searched for and hbar*omega is derived from it. Whoever measures a dot can
estimate a size; hbar*omega is a result, not a guess.

Extracted from the standalone calculator's Tk tab, which is why it exists as
a plain class: with no widgets it runs on a worker thread and can be tested
headless, which the search buried in a GUI could be neither.

Keys are English ``snake_case`` and are what gets compared and persisted;
the display strings live in the ``*_LABELS`` maps. Nothing here compares a
label.
"""

from __future__ import annotations

import itertools
import logging
import math
from typing import Callable, List, Optional, Sequence

import numpy as np
from scipy.constants import hbar, m_e, e
from scipy.optimize import minimize, differential_evolution

from src.physics.analytical import (box_energies_1d_eV, box_energies_2d_eV,
                                    box_energies_3d_eV, cylinder_energies,
                                    disk_energies)
from src.physics.pairing import confinement_size_nm
from src.physics.quantum_dot import (dot_energies, hw_from_length,
                                     length_from_hw, levels_for)
from src.physics.solution_spec import (
    COORDS_CARTESIAN, COORDS_CIRCULAR, COORDS_CYLINDRICAL, COORDS_DISC,
    COORDS_PARABOLIC, COORDS_SPHERICAL,
)

logger = logging.getLogger(__name__)

#: Relative tolerance for "these two model levels are the SAME energy".
#:
#: Extremely tight on purpose, and mirrored from
#: :data:`src.physics.level_patterns.GROUP_RTOL`. This is a symmetry fact
#: about the model, and true partners agree to machine precision because they
#: are exact arithmetic on integers or on shared Bessel zeros. It is NOT the
#: tolerance for "can this measurement tell these two levels apart" — that one
#: is 3.5 k_B T, four hundred times wider at 90 K, belongs to the spectrum
#: rather than to the model, and is reported separately as ``n_tied``.
#: Conflating them would let a candidate claim a degeneracy the data cannot
#: see, which is the one thing a degeneracy column must never do.
_EXACT_RTOL = 1e-9

#: How far past the fitted window the level table is enumerated before its
#: degenerate groups are counted. Degeneracy is a property of a SET, so a
#: group has to be complete before it can be summed, and the group sitting on
#: the truncation never is. Five is comfortable: the most degenerate model
#: here is the 3D box, where twenty enumerated rows cover seven distinct
#: energies, so a fivefold margin puts the cut several groups above anything
#: a match can reach. It costs one extra level-table build per ACCEPTED
#: candidate — never inside :meth:`Designer.objective`.
_DEGENERACY_MARGIN = 5


# ── how a candidate is compared with the targets ────────────────────────────

MATCH_ABSOLUTE = "absolute"
MATCH_GAPS = "delta_e"
MATCH_RATIOS = "delta_e_ratios"

MATCHES = (MATCH_ABSOLUTE, MATCH_GAPS, MATCH_RATIOS)

MATCH_LABELS = {
    MATCH_ABSOLUTE: "Absolute energies",
    MATCH_GAPS: "Differences (ΔE)",
    MATCH_RATIOS: "ΔE ratios",
}

# ── which targets the fit is asked to care about ────────────────────────────

PRIORITY_UNIFORM = "uniform"
PRIORITY_GROUND = "ground_state"
PRIORITY_LOW_QN = "low_quantum_numbers"

PRIORITIES = (PRIORITY_UNIFORM, PRIORITY_GROUND, PRIORITY_LOW_QN)

PRIORITY_LABELS = {
    PRIORITY_UNIFORM: "Uniform",
    PRIORITY_GROUND: "Ground state",
    PRIORITY_LOW_QN: "Low quantum numbers",
}

# ── which computed level each target is compared with ───────────────────────
#
# Deliberately a namespace of its own, and not more PRIORITY_* keys, because
# the two answer different questions and the standalone calculator this search
# came from ran them through one setting. PRIORITY_* are WEIGHTS: given an
# assignment, how much does each target contribute to the RRMSE. ASSIGN_* come
# first and decide WHICH computed level a target is compared with at all.
#
# That distinction is not academic here. At 300 K the first in-plane gap of a
# lens is inside the thermal linewidth for R above ~3.4 nm, so a measured
# ladder is routinely one whose lowest rung was never resolved. Matched
# nearest-in-energy, such a ladder is assigned to the model's rungs 1..N and
# the geometry that comes back is the one that makes a missing level fit —
# a different answer from the same data. ``sequential`` and the two
# quantum-number rules exist to say "assign it this way instead" and see
# whether the answer survives; on the disc measured here the three rules agree
# on the error to within 0.4 percentage points and disagree on R by a factor
# of 1.9, which is the honest statement of what the data determines.

ASSIGN_ENERGY = "energy"
ASSIGN_SEQUENTIAL = "sequential"
ASSIGN_LOW_QN = "low_quantum_numbers"
ASSIGN_MIXED = "mixed"

ASSIGNMENTS = (ASSIGN_ENERGY, ASSIGN_SEQUENTIAL, ASSIGN_LOW_QN, ASSIGN_MIXED)

ASSIGN_LABELS = {
    ASSIGN_ENERGY: "Nearest energy",
    ASSIGN_SEQUENTIAL: "Sequential states",
    ASSIGN_LOW_QN: "Lowest quantum numbers",
    ASSIGN_MIXED: "Mixed (energy and quantum numbers)",
}

# ── crystal symmetry constraints on the free dimensions ─────────────────────

SYM_CUBIC = "cubic"
SYM_TETRAGONAL = "tetragonal"
SYM_ORTHORHOMBIC = "orthorhombic"
SYM_SQUARE = "square"
SYM_RECTANGULAR = "rectangular"

SYM_LABELS = {
    SYM_CUBIC: "Cubic",
    SYM_TETRAGONAL: "Tetragonal",
    SYM_ORTHORHOMBIC: "Orthorhombic",
    SYM_SQUARE: "Square",
    SYM_RECTANGULAR: "Rectangular",
}

#: Which symmetries apply in which dimensionality.
SYMS_2D = (SYM_SQUARE, SYM_RECTANGULAR)
SYMS_3D = (SYM_CUBIC, SYM_TETRAGONAL, SYM_ORTHORHOMBIC)

# ── which carriers a search describes ───────────────────────────────────────

CARRIER_ELECTRON = "electrons"
CARRIER_HOLE = "holes"
CARRIER_BOTH = "both"

CARRIERS = (CARRIER_ELECTRON, CARRIER_HOLE, CARRIER_BOTH)

CARRIER_LABELS = {
    CARRIER_ELECTRON: "Electrons",
    CARRIER_HOLE: "Holes",
    CARRIER_BOTH: "Electrons + holes",
}

# ── how the candidate list is ordered ───────────────────────────────────────
#
# The search always keeps the `maxsol` lowest-error candidates; this only
# changes the order they are shown in.

SORT_RRMSE = "rrmse"
SORT_RRMSE_GAPS = "rrmse_delta_e"
SORT_SIZE_ASC = "size_asc"
SORT_SIZE_DESC = "size_desc"
SORT_ANISOTROPY = "anisotropy"
SORT_GROUND = "ground_state"

SORTS = (SORT_RRMSE, SORT_RRMSE_GAPS, SORT_SIZE_ASC, SORT_SIZE_DESC,
         SORT_ANISOTROPY, SORT_GROUND)

SORT_LABELS = {
    SORT_RRMSE: "Error (RRMSE)",
    SORT_RRMSE_GAPS: "Error in the spacings (ΔE)",
    SORT_SIZE_ASC: "Size — smallest first",
    SORT_SIZE_DESC: "Size — largest first",
    SORT_ANISOTROPY: "Anisotropy — most symmetric",
    SORT_GROUND: "E₁ (ground state)",
}

#: Which dimensions each dot model searches for, and what to call them. In
#: the parabolic case these are confinement lengths, not energies. Keyed by
#: ``coords``, which for a 0D geometry names the model directly.
DOT_ROWS = {
    COORDS_SPHERICAL: ("R",),
    COORDS_DISC: ("R", "L_z"),
    COORDS_PARABOLIC: ("l_xy", "l_z"),
}


# ── input parsing ───────────────────────────────────────────────────────────

def parse_list(text: str, what: str) -> list:
    """``"0.067, 0.08"`` → ``[0.067, 0.08]``. A clear error on rubbish."""
    values = []
    for token in str(text).replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            raise ValueError(f"{what}: '{token}' is not a number")
    if not values:
        raise ValueError(f"{what}: no values")
    return values


def parse_energies(text: str, what: str) -> np.ndarray:
    """Target energies, sorted and checked. The hole enters with |E|."""
    Et = np.sort(np.array(parse_list(text, what)))
    if np.any(Et <= 0):
        raise ValueError(f"{what}: the energies must be positive "
                         f"(the hole enters with |E|)")
    return Et


def parse_masses(text: str, what: str) -> list:
    """Effective masses, ascending and deduplicated.

    Two identical searches would return the same candidate twice.
    """
    masses = parse_list(text, what)
    if any(m <= 0 for m in masses):
        raise ValueError(f"{what}: the masses must be > 0")
    return sorted(set(masses))


# ── units of work a process pool can run ────────────────────────────────────
#
# Module-level so they pickle. Each builds a throwaway Designer: the objective
# reads nothing off the instance but the parameters it is handed, so the
# value a worker computes is the value the serial loop would have. Errors
# come back as None, which the caller treats exactly as the serial loop
# treats the exception it swallows.

def _pool_minimize(job):
    """One L-BFGS-B descent: ``(fun, x)`` or None."""
    p, start, bounds = job
    try:
        res = minimize(Designer(seed=0).objective, start, args=(p,),
                       method='L-BFGS-B', bounds=bounds)
    except Exception:
        return None
    return res.fun, res.x


def _pool_evolve(job):
    """One differential-evolution pass from a given seed: ``(fun, x)`` or None."""
    p, bounds, seed = job
    try:
        res = differential_evolution(Designer(seed=0).objective, bounds,
                                     args=(p,), maxiter=200, tol=0.01,
                                     seed=seed)
    except Exception:
        return None
    return res.fun, res.x


def _pool_score(job):
    """The objective at each lattice node of a chunk, None where it raised."""
    p, nodes = job
    designer = Designer(seed=0)
    out = []
    for node in nodes:
        try:
            out.append(designer.objective(list(node), p))
        except Exception:
            out.append(None)
    return out


class Designer:
    """The search itself: no widgets, no plots, no state beyond its seed.

    Every method takes the search parameters as a plain dict ``p``:

    ``Et``        target energies (eV, ascending, positive)
    ``meff``      effective mass this pass runs with
    ``ndim``      "0D" / "1D" / "2D" / "3D"
    ``coords``    one of :data:`solution_spec.COORDS`; for 0D it names the model
    ``sym``       one of the ``SYM_*`` keys (2D/3D only)
    ``fixed``     ``{"d1": value or None, …}`` — dimensions the user pinned
    ``Lmin``/``Lmax``  search range, nm
    ``tol``       an optimisation result above this error is discarded
    ``maxsol``    how many candidates to keep
    ``priority``  one of the ``PRIORITY_*`` keys
    ``match``     one of the ``MATCH_*`` keys
    """

    def __init__(self, seed: Optional[int] = None, mapper=None):
        # Seedable so a test can pin the global optimisation; entropy-seeded
        # by default, exactly as the search has always run.
        self._rng = np.random.default_rng(seed)
        # Anything with ``workers`` and ``map(fn, jobs, should_cancel)`` —
        # in the app, :class:`src.backend.compute_pool.PoolMapper`. With one,
        # the independent passes of a search run on it and are replayed in
        # serial order, so the candidates are the serial ones bit for bit.
        self.mapper = mapper

    def _parallel(self) -> bool:
        return self.mapper is not None and getattr(self.mapper, 'workers', 1) > 1

    # ─── the geometry under test ─────────────────────────────────────────

    def compute_energies(self, dims, meff, n, p):
        """The ladder a given geometry produces, ``[(E_eV, qn), …]``."""
        ndim = p['ndim']
        coords = p['coords']
        if ndim == "0D":
            return dot_energies(coords, dims, meff, n)
        if ndim == "1D":
            return box_energies_1d_eV(dims[0], meff, n)
        elif ndim == "2D":
            if coords == COORDS_CIRCULAR:
                return disk_energies(dims[0], meff, n)
            else:
                return box_energies_2d_eV(dims[0], dims[1], meff, n)
        else:
            if coords == COORDS_CYLINDRICAL:
                return cylinder_energies(dims[0], dims[1], meff, n)
            else:
                return box_energies_3d_eV(dims[0], dims[1], dims[2], meff, n)

    def params_to_dims(self, opt, p):
        """Turn the optimiser's free variables into a full set of dimensions.

        Pinned dimensions and symmetry constraints are filled in here, so the
        optimiser only ever varies what is actually free.
        """
        idx = 0
        fixed = p['fixed']
        ndim = p['ndim']
        coords = p['coords']
        sym = p.get('sym', '')

        def _next():
            nonlocal idx
            v = opt[idx]
            idx += 1
            return v

        if ndim == "0D":
            d1 = fixed['d1'] if fixed['d1'] is not None else _next()
            if coords == COORDS_SPHERICAL:
                return (d1,)
            d2 = fixed['d2'] if fixed['d2'] is not None else _next()
            if coords == COORDS_DISC:
                return (d1, d2)
            # Parabolic: searched in nm and handed over in meV, which is what
            # `parabolic_dot` (and the spec) expect.
            return (hw_from_length(d1, p['meff']), hw_from_length(d2, p['meff']))

        if ndim == "1D":
            L = fixed['d1'] if fixed['d1'] is not None else _next()
            return (L,)
        elif ndim == "2D":
            if coords == COORDS_CIRCULAR:
                R = fixed['d1'] if fixed['d1'] is not None else _next()
                return (R,)
            else:
                Lx = fixed['d1'] if fixed['d1'] is not None else _next()
                if sym == SYM_SQUARE:
                    return (Lx, Lx)
                Ly = fixed['d2'] if fixed['d2'] is not None else _next()
                return (Lx, Ly)
        else:
            if coords == COORDS_CYLINDRICAL:
                R = fixed['d1'] if fixed['d1'] is not None else _next()
                H = fixed['d2'] if fixed['d2'] is not None else _next()
                return (R, H)
            else:
                Lx = fixed['d1'] if fixed['d1'] is not None else _next()
                if sym == SYM_CUBIC:
                    return (Lx, Lx, Lx)
                elif sym == SYM_TETRAGONAL:
                    Lz = fixed['d3'] if fixed['d3'] is not None else _next()
                    return (Lx, Lx, Lz)
                else:
                    Ly = fixed['d2'] if fixed['d2'] is not None else _next()
                    Lz = fixed['d3'] if fixed['d3'] is not None else _next()
                    return (Lx, Ly, Lz)

    def free_keys(self, p) -> List[str]:
        """Which dimension each free optimiser variable IS, in order.

        The same walk :meth:`params_to_dims` makes when it consumes ``opt``,
        written once so that everything which has to agree with it reads the
        same list: :meth:`bounds` (one interval per entry) and the
        sensitivity probe, which has to be able to NAME the dimension a
        candidate turned out not to depend on rather than just count them.
        """
        out: List[str] = []
        f = p['fixed']
        ndim, coords, sym = p['ndim'], p['coords'], p.get('sym', '')

        if ndim == "0D":
            for key in ("d1", "d2")[:len(DOT_ROWS[coords])]:
                if f[key] is None:
                    out.append(key)
        elif ndim == "1D":
            if f['d1'] is None:
                out.append('d1')
        elif ndim == "2D":
            if coords == COORDS_CIRCULAR:
                if f['d1'] is None:
                    out.append('d1')
            else:
                if f['d1'] is None:
                    out.append('d1')
                if sym != SYM_SQUARE and f['d2'] is None:
                    out.append('d2')
        else:
            if coords == COORDS_CYLINDRICAL:
                if f['d1'] is None:
                    out.append('d1')
                if f['d2'] is None:
                    out.append('d2')
            else:
                if f['d1'] is None:
                    out.append('d1')
                if sym == SYM_TETRAGONAL:
                    if f['d3'] is None:
                        out.append('d3')
                elif sym == SYM_ORTHORHOMBIC:
                    if f['d2'] is None:
                        out.append('d2')
                    if f['d3'] is None:
                        out.append('d3')
        return out

    @staticmethod
    def dim_keys(p) -> List[str]:
        """Which dimension key each entry of ``dims`` carries.

        NOT the same list as :meth:`free_keys`, and the difference is the
        point: a symmetry makes one key occupy several slots (a tetragonal
        cell is ``('d1', 'd1', 'd3')``) and a pinned dimension still occupies
        its own. A probe that moves a dimension has to move every slot that
        dimension fills — both edges of a square together, never one alone —
        or it is measuring a geometry the search cannot reach.
        """
        ndim, coords, sym = p['ndim'], p['coords'], p.get('sym', '')
        if ndim == "0D":
            return ['d1'] if coords == COORDS_SPHERICAL else ['d1', 'd2']
        if ndim == "1D":
            return ['d1']
        if ndim == "2D":
            if coords == COORDS_CIRCULAR:
                return ['d1']
            return ['d1', 'd1'] if sym == SYM_SQUARE else ['d1', 'd2']
        if coords == COORDS_CYLINDRICAL:
            return ['d1', 'd2']
        if sym == SYM_CUBIC:
            return ['d1', 'd1', 'd1']
        if sym == SYM_TETRAGONAL:
            return ['d1', 'd1', 'd3']
        return ['d1', 'd2', 'd3']

    @staticmethod
    def _box(p, key):
        """The search interval for ONE free dimension.

        ``p['box']`` is optional — ``{'d1': (lo, hi), …}``, an absent entry or
        a None at either end meaning "use ``Lmin``/``Lmax``". Without it every
        dimension gets the same interval, which is what the search has always
        done and what one pair of sliders in the panel can express.

        One interval for every dimension is wrong whenever the dimensions are
        not equally determined, and on a lens matched by level SPACINGS they
        are not even close. R is pinned to about a hundred picometres by the
        data; L_z is not measured at all, because the energy origin cancels in
        a difference and the axial ladder it sets goes with it. A single
        slider therefore lets L_z wander to whatever ceiling the user picked
        for R — which is, measurably, what "it diverges at 18 nm but converges
        at 13 nm" is: at 13 no pixel's L_z exceeds 10 nm, at 18 a quarter of
        them pin against the ceiling and their R collapses to compensate.
        """
        entry = (p.get('box') or {}).get(key)
        if entry is None:
            return (p['Lmin'], p['Lmax'])
        lo, hi = entry
        return (p['Lmin'] if lo is None else float(lo),
                p['Lmax'] if hi is None else float(hi))

    def bounds(self, p):
        """One ``(lo, hi)`` per free dimension, in the order they are read."""
        return [self._box(p, key) for key in self.free_keys(p)]

    # ─── matching and error ──────────────────────────────────────────────

    @staticmethod
    def find_matches(Ec, Et, assign=ASSIGN_ENERGY):
        """Pair each target with one computed level, by one of the ASSIGN_* rules.

        ``ASSIGN_ENERGY`` (the default, and what this method has always done)
        gives each target the level nearest it in RELATIVE energy, each target
        independently of the others. It is the right rule when the ladder is
        resolved; it is the wrong one when it is not, because nothing stops it
        assigning two targets to the same level, or skipping a level the
        measurement simply could not see.

        ``ASSIGN_SEQUENTIAL`` removes the freedom entirely: target *i* is
        level *i* of the list it is handed, no search. On its own that would
        force a measurement onto the model's rungs 1, 2, 3, …; it is
        :meth:`match_and_score` that makes it useful, by handing this rule a
        list that starts at each level in turn, so the pass sweeps every
        CONSECUTIVE window of the model's ladder. That is the control for a
        spectrum whose lowest rungs are below the thermal linewidth and were
        therefore never measured: the ladder is real, its bottom is missing,
        and no amount of nearest-in-energy matching can say so.

        ``ASSIGN_LOW_QN`` takes, among the levels whose relative error is
        within ten times the best (or 10 %, whichever is looser), the one with
        the smallest total quantum number — the states a real measurement
        populates first. ``ASSIGN_MIXED`` is the graded version of the same
        preference: the quantum-number penalty is spread across the ladder's
        own range of ``sum(qn)`` and scaled to the ladder's own best relative
        error, so that the cheapest state on offer is ranked as if it carried
        nine times the best error — exactly the window ``ASSIGN_LOW_QN``
        admits, but spent continuously instead of as a veto.

        THAT SCALING IS A CORRECTION, not a preference. The rule used to be
        ``rel_err + 0.01 * sum(qn)``: a dimensionless relative error plus a
        hundredth of an integer. The two terms have no common scale, so which
        one decides depends entirely on how good the fit is — and on a good
        fit it is never the energy. At ``rel_err`` around 0.005, a single unit
        of quantum number is worth twice the whole energy error and a typical
        ``sum(qn)`` of 6 is worth twelve times it; "mixed" was
        "lowest quantum numbers" wearing an arbitrary constant, while the
        RRMSE it reported stayed pure energy error, so the geometry moved and
        the number explaining it did not. Both terms are now relative errors,
        both are read off the ladder being matched, and the rule degrades
        gracefully: with a ladder the data resolves (a small best error) the
        energy decides, and only where the levels crowd does the quantum
        number break the tie.

        The two quantum-number rules deliberately change only the ASSIGNMENT,
        never the score: the standalone calculator also added the quantum
        numbers into the reported error as a penalty, which made an RRMSE mean
        two different things depending on a dropdown. Here the RRMSE is always
        the energy error, and ``qn_sum`` is reported separately as data.
        """
        Ev = np.array([x[0] for x in Ec])

        if assign == ASSIGN_SEQUENTIAL:
            # Clamped rather than cut short: a target beyond the computed
            # ladder is a real (and very bad) match, not a missing row, and it
            # has to score as such instead of shortening the comparison.
            return [{'target_E': et, 'computed_E': Ec[min(i, len(Ec) - 1)][0],
                     'qn': Ec[min(i, len(Ec) - 1)][1],
                     'idx': min(i, len(Ec) - 1)}
                    for i, et in enumerate(Et)]

        matches = []
        for et in Et:
            if assign == ASSIGN_LOW_QN:
                rel = np.abs(Ev - et) / et
                cut = max(float(rel.min()) * 10.0, 0.1)
                # The index is the last tie-break so the rule is a function of
                # the ladder alone: two levels of equal error and equal
                # quantum numbers must not resolve by list order on one run
                # and the other way on the next.
                j = min((k for k in range(len(Ec)) if rel[k] <= cut),
                        key=lambda k: (sum(Ec[k][1]), rel[k], k))
            elif assign == ASSIGN_MIXED:
                rel = np.abs(Ev - et) / et
                qn_sum = np.array([sum(Ec[k][1]) for k in range(len(Ec))],
                                  dtype=float)
                span = float(qn_sum.max() - qn_sum.min())
                # Nine times the best error is the edge of the window
                # ASSIGN_LOW_QN admits; spending exactly that much across the
                # ladder's full range of sum(qn) makes this the graded form of
                # that same rule instead of a second, unrelated one.
                scale = 9.0 * float(rel.min())
                penalty = (np.zeros_like(rel) if span <= 0 else
                           scale * (qn_sum - qn_sum.min()) / span)
                j = min(range(len(Ec)),
                        key=lambda k: (rel[k] + penalty[k], k))
            else:
                j = int(np.argmin(np.abs(Ev - et) / et))
            matches.append({'target_E': et, 'computed_E': Ec[j][0],
                            'qn': Ec[j][1], 'idx': j})
        return matches

    @staticmethod
    def make_weights(n_targets, priority=PRIORITY_UNIFORM):
        """Weight array for the objective, following the priority mode."""
        if priority == PRIORITY_GROUND:
            # Only the first (lowest) target matters
            w = np.zeros(n_targets)
            w[0] = 1.0
            return w
        elif priority == PRIORITY_LOW_QN:
            # Weight ~ 1/n^2 (n=1,2,3,…) — strongly favours low levels
            idx = np.arange(1, n_targets + 1, dtype=float)
            w = 1.0 / idx ** 2
            return w / w.sum() * n_targets  # normalise so sum = n_targets
        else:
            return np.ones(n_targets)

    def abs_rrmse(self, matches, Et, priority=PRIORITY_UNIFORM):
        """Error in the absolute energies — the classic criterion."""
        Em = np.array([m['computed_E'] for m in matches])
        w = self.make_weights(len(Et), priority)
        return float(np.sqrt(np.mean(w * ((Em - Et) / Et) ** 2)) * 100)

    def gap_rrmse(self, matches, Et, priority=PRIORITY_UNIFORM, ratios=False):
        """Error in the spacings between consecutive levels.

        This is what a measurement really pins down. In STS the energies are
        read from E_F and the model counts from the bottom of the well: the
        origins differ by an unknown offset that cancels in the difference.
        With ``ratios`` the scale cancels too, and only the shape of the
        ladder is left — which identifies the model without depending on m*,
        almost always the least known parameter.
        """
        Em = np.array([m['computed_E'] for m in matches])
        dM, dT = np.diff(Em), np.diff(np.asarray(Et, dtype=float))
        if dT.size == 0:
            return 0.0
        if ratios:
            if dM.mean() <= 0 or dT.mean() <= 0:
                return 1e6
            dM = dM / dM.mean()
            dT = dT / dT.mean()

        w = self.make_weights(len(Et), priority)[1:]
        if w.sum() <= 0:          # "ground state" puts no weight on spacings
            w = np.ones_like(dT)
        rel = np.where(dT != 0, (dM - dT) / np.where(dT != 0, dT, 1.0), 0.0)
        return float(np.sqrt(np.mean(w * rel ** 2)) * 100)

    def match_and_score(self, Ec, Et, p):
        """Match levels to targets. Returns ``(matches, offset_eV, rrmse)``.

        In the difference modes the energy origin is free, so every computed
        level is tried as the partner of the first target and the alignment
        with the smallest error wins. ``computed_E`` comes out already
        shifted, to compare directly with the target; ``offset`` records by
        how much.
        """
        mode = p.get('match', MATCH_ABSOLUTE)
        priority = p.get('priority', PRIORITY_UNIFORM)
        assign = p.get('assign', ASSIGN_ENERGY)

        if mode == MATCH_ABSOLUTE:
            matches = self.find_matches(Ec, Et, assign)
            return matches, 0.0, self.abs_rrmse(matches, Et, priority)

        ratios = (mode == MATCH_RATIOS)
        best = None
        for j0 in range(len(Ec)):
            offset = Ec[j0][0] - Et[0]
            shifted = [(E - offset, qn) for E, qn in Ec if E - offset > 0]
            if assign == ASSIGN_SEQUENTIAL:
                # Sequential matching has no freedom of its own, so the offset
                # scan has to supply it: level j0 is the partner of the first
                # target, and the assignment runs consecutively from there.
                # Without this the scan would be a no-op for it — in STS the
                # targets are read from E_F and are volts above the model's
                # levels, so the offset comes out negative, nothing is dropped
                # by the positivity filter, and every j0 would hand the same
                # list starting at the ground state to a rule that reads it
                # positionally.
                #
                # Sliding the window is the whole point of the mode: it is how
                # a ladder whose lowest rungs were never resolved (the first
                # in-plane gap of this lens is inside the thermal linewidth
                # for R above ~3.4 nm at 300 K) can be matched to rungs
                # j0, j0+1, … instead of being forced onto 1, 2, … and
                # answered with whatever geometry makes a missing level fit.
                dropped = sum(1 for E, _qn in Ec[:j0] if E - offset <= 0)
                shifted = shifted[j0 - dropped:]
            if len(shifted) < len(Et):
                continue
            matches = self.find_matches(shifted, Et, assign)
            err = self.gap_rrmse(matches, Et, priority, ratios=ratios)
            if best is None or err < best[2]:
                best = (matches, offset, err)

        if best is None:            # nothing alignable: fall back to absolute
            matches = self.find_matches(Ec, Et, assign)
            return matches, 0.0, self.abs_rrmse(matches, Et, priority)
        return best

    def fast_error(self, Ec, Et, p, scale_term=False) -> Optional[float]:
        """:meth:`match_and_score`'s error, every offset at once. None if
        this rule has no fast form.

        The scoring is three quarters of an objective evaluation, and almost
        none of it is arithmetic: twenty offsets, each building a shifted
        list, a dict per match and four NumPy calls on arrays of six. Here
        the offsets are one axis of an array — ``(offset, level, target)`` —
        so the same subtractions, the same first-minimum ``argmin`` and the
        same reductions run once. Measured on the lens at R = 4.1 nm with six
        targets: 0.63 ms down to 0.042 ms, and the error is the SAME FLOAT,
        not a close one — bit-identical on 3000 random geometries, because
        each element is computed by the same IEEE operation in the same
        order, and a row reduction over six elements sums exactly as the 1D
        one did. ``tests/test_physics/test_designer_fast_error.py`` holds it
        to that.

        Only :data:`ASSIGN_ENERGY` has a fast form: the other rules break
        ties on the quantum numbers, which are tuples, and they fall back to
        :meth:`match_and_score`. Only the error comes out — a candidate is
        still built by :meth:`extract_solution` through the full path, so
        every table column is produced exactly as before.
        """
        if p.get('assign', ASSIGN_ENERGY) != ASSIGN_ENERGY:
            return None
        mode = p.get('match', MATCH_ABSOLUTE)
        priority = p.get('priority', PRIORITY_UNIFORM)
        Ev = np.fromiter((x[0] for x in Ec), dtype=float, count=len(Ec))
        Et = np.asarray(Et, dtype=float)
        if Ev.size == 0 or Et.size == 0:
            return None

        def nearest(S, valid):
            # (rows, level, target): the relative distance, `inf` where the
            # positivity filter would have dropped the level, so the first
            # minimum is the reference's first minimum over the kept ones.
            rel = np.abs(S[:, :, None] - Et[None, None, :]) / Et
            rel = np.where(valid[:, :, None], rel, np.inf)
            return np.take_along_axis(S, rel.argmin(axis=1), axis=1)

        def absolute(Em):
            w = self.make_weights(len(Et), priority)
            return np.sqrt(np.mean(w * ((Em - Et) / Et) ** 2, axis=-1)) * 100

        if mode == MATCH_ABSOLUTE:
            S = Ev[None, :]
            return float(absolute(nearest(S, np.ones_like(S, dtype=bool)))[0])

        ratios = (mode == MATCH_RATIOS)
        offsets = Ev - Et[0]
        S = Ev[None, :] - offsets[:, None]
        valid = S > 0
        alignable = valid.sum(axis=1) >= len(Et)
        if not alignable.any():
            # Nothing alignable: the same fallback match_and_score takes.
            return float(absolute(nearest(Ev[None, :], np.ones((1, Ev.size),
                                                               dtype=bool)))[0])
        Em = nearest(S, valid)
        dT = np.diff(Et)
        if dT.size == 0:
            err = np.zeros(len(S))
        else:
            dM = np.diff(Em, axis=1)
            if ratios:
                mM = dM.mean(axis=1)
                bad = (mM <= 0) | (dT.mean() <= 0)
                dM = dM / np.where(bad, 1.0, mM)[:, None]
                dT = dT / dT.mean()
            w = self.make_weights(len(Et), priority)[1:]
            if w.sum() <= 0:
                w = np.ones_like(dT)
            rel = np.where(dT != 0, (dM - dT) / np.where(dT != 0, dT, 1.0), 0.0)
            err = np.sqrt(np.mean(w * rel ** 2, axis=1)) * 100
            if ratios:
                err = np.where(bad, 1e6, err)
        err = np.where(alignable, err, np.inf)
        best = int(np.argmin(err))
        out = float(err[best])
        if ratios and scale_term:
            # The objective's scale term, on the winning alignment's matches.
            out += 1e-3 * float(absolute(Em[best]))
        return out

    def objective(self, opt, p):
        """What the optimiser minimises: the error of one trial geometry."""
        dims = self.params_to_dims(opt, p)
        n = max(len(p['Et']) * 3, 20)
        Ec = self.compute_energies(dims, p['meff'], n, p)
        fast = self.fast_error(Ec, p['Et'], p,
                               scale_term=p.get('match') == MATCH_RATIOS)
        if fast is not None:
            return fast
        matches, _offset, err = self.match_and_score(Ec, p['Et'], p)
        if p.get('match') == MATCH_RATIOS:
            # Ratios do not fix the scale: within one model E ∝ 1/L², and
            # every size gives the same ratios. A small absolute-energy term
            # picks, among equivalent shapes, the one of compatible size —
            # without changing which shape wins.
            err += 1e-3 * self.abs_rrmse(matches, p['Et'],
                                         p.get('priority', PRIORITY_UNIFORM))
        return err

    def extract_solution(self, opt, p):
        """Turn an optimiser result into a candidate dict."""
        dims = self.params_to_dims(opt, p)
        n = max(len(p['Et']) * 3, 20)
        Ec = self.compute_energies(dims, p['meff'], n, p)
        matches, offset, rr = self.match_and_score(Ec, p['Et'], p)
        # Both errors are always kept: the chosen mode drives the search, but
        # sorting and comparing want both sides.
        priority = p.get('priority', PRIORITY_UNIFORM)
        # The mass and the targets are stored ON the candidate: with several
        # masses in play, ``p['meff']`` no longer describes any one of them —
        # and it is the candidate's mass the receiving solver has to simulate.
        sol = {'dims': dims, 'RRMSE': rr, 'matches': matches, 'Ec': Ec,
               'meff': p['meff'], 'targets': list(p['Et']),
               'carrier': p.get('carrier', 'e'),
               'RRMSE_abs': self.abs_rrmse(matches, p['Et'], priority),
               'RRMSE_dE': self.gap_rrmse(matches, p['Et'], priority),
               'offset': offset, 'match': p.get('match', MATCH_ABSOLUTE),
               'ndim': p['ndim'], 'coords': p['coords'], 'sym': p.get('sym', '')}
        self.annotate(sol, p)
        return sol

    # ─── what a candidate is, beyond its error ───────────────────────────

    #: FWHM of -df/dE, 4 ln(1 + sqrt 2) k_B T — the number usually quoted as
    #: "3.5 k_B T". Written from its derivation, not as 3.5, so it matches
    #: ``processing.edge_analysis.THERMAL_FWHM_FACTOR`` and
    #: ``ToolImplementations.THERMAL_FWHM_KT`` exactly instead of drifting a
    #: per cent away from them.
    THERMAL_FWHM_KT = 4.0 * math.log(1.0 + math.sqrt(2.0))
    #: eV per kelvin.
    K_B_EV_PER_K = 8.617333262e-5

    @staticmethod
    def resolution_eV(p) -> Optional[float]:
        """How far apart two model levels have to be for the data to see both.

        Returns ``None`` when the run has not been told, and that is the
        point: there is no defensible way to infer this from the peak list.

        Two ways to say it, both the user's own measurement:

        ``p['resolution_meV']``  an explicit window.
        ``p['temperature_K']``   the thermal linewidth 3.5 k_B T — 27 meV at
                                 90 K, 91 meV at 300 K — which is what decides
                                 whether a gap the model predicts could have
                                 been observed at all.

        This used to fall back to HALF the smallest gap the measurement
        resolved, so the diagnostic columns were always populated. That was
        wrong in the direction that matters. Half the smallest observed gap is
        a LOWER BOUND on the resolution, not the resolution: on a six-level
        lens it comes out at 6.07 meV against a real 27 meV at 90 K, and at
        that window every runaway geometry reports ``unresolvable = False``
        — (3.2, 10.0) nm, (2.9, 14.5) nm and (2.1, 18.0) nm all pass, and all
        three flip to True at 3.5 k_B T. A flag that is silent on exactly the
        geometries it was written to catch is worse than no flag, because it
        reads as a clean bill of health. Unset is honest; a guess is not.
        """
        res = p.get('resolution_meV')
        if res is not None:
            return float(res) * 1e-3
        temp = p.get('temperature_K')
        if temp is not None and float(temp) > 0:
            return (Designer.THERMAL_FWHM_KT * Designer.K_B_EV_PER_K
                    * float(temp))
        return None

    @staticmethod
    def resolution_basis(p) -> str:
        """Where the resolution window came from, in words.

        A count of levels "tied" inside a window nobody can name is a number
        without units, so the basis travels with the number everywhere it is
        displayed.
        """
        if p.get('resolution_meV') is not None:
            return f"{float(p['resolution_meV']):g} meV, entered directly"
        temp = p.get('temperature_K')
        if temp is not None and float(temp) > 0:
            return f"3.5 k_B T at {float(temp):g} K"
        return "not set — no measurement resolution given"

    def score_dims(self, dims, p, meff=None) -> float:
        """The matching error of a geometry given directly in ``dims``.

        :meth:`objective` takes the optimiser's free variables; this takes the
        full dimensions. The sensitivity probe needs the second form because a
        symmetry maps one free variable onto several dimensions and a pinned
        dimension onto none, and because :meth:`primary_alias` holds a
        geometry that no ``opt`` vector it still has produced.
        """
        n = max(len(p['Et']) * 3, 20)
        Ec = self.compute_energies(dims, p['meff'] if meff is None else meff,
                                   n, p)
        fast = self.fast_error(Ec, p['Et'], p)
        if fast is not None:
            return fast
        _matches, _offset, err = self.match_and_score(Ec, p['Et'], p)
        return err

    #: How far two scores may differ and still count as "the same number".
    #:
    #: A few ulps, and no more: the claim being made is that the dimension did
    #: not enter the arithmetic, not that its effect is small. 1e-12 is about
    #: 4500 ulps of a double, which is the width of the float noise a ΔE score
    #: actually carries (see :meth:`flat_dims`) and still twelve orders of
    #: magnitude below any real sensitivity — moving R by 2 % on this disc
    #: moves the score by tens of per cent, not by parts in a trillion.
    FLAT_RTOL = 1e-12

    def flat_dims(self, sol, p, rel=0.02) -> List[str]:
        """The free dimensions the objective is literally insensitive to.

        Each free dimension is moved by ±2 % — every slot it fills, so a
        symmetry stays a symmetry — and the error recomputed. If neither move
        changes it beyond :data:`FLAT_RTOL`, the fit never saw that dimension
        and the value reported for it is one arbitrary point of a plateau, not
        a measurement.

        THE TEST IS RELATIVE, NOT BIT EQUALITY, AND THAT IS A CORRECTION.
        Bit equality is the claim one wants to make, and it is the claim that
        holds in ``absolute`` matching, where a flat dimension contributes
        literally nothing to the arithmetic. It cannot hold in ``delta_e``.
        There the constant axial energy is added into every level and then
        subtracted again as the fitted offset, and floating-point addition is
        not associative: ``(a + c) - (b + c)`` differs from ``a - b`` in the
        last bits, and by a different last bit for each ``c``. Measured on
        this disc at R = 6.5 nm the score is

            47.48464848646017 / …003 / …009 / …006

        at L_z = 1.0 / 1.5 / 2.0 / 2.5 nm — one and two ulps apart, from a
        dimension that provably does not appear in the model's ladder over
        that window. With bit equality only L_z = 1.0 was flagged, and the
        other three printed a four-decimal L_z with no "free" badge: a
        plateau presented as a measurement, which is the one thing this
        column exists to prevent. On the real search output of her 13 nm box
        it flagged 2 of the 13 candidates sharing one R = 8.7761 plateau.

        It is not a subtle effect. On this disc at R = 6.5 nm the error is the
        identical 1.709 % at L_z = 1.0, 1.5, 2.0, 2.5 and 3.0 nm, because no
        n_z > 1 state enters the lowest twenty levels below L_z = 2.5 nm — and
        the panel prints one of those five to three decimal places. Under ΔE
        matching, where the energy origin cancels and the axial ladder goes
        with it, this is the normal state of L_z rather than an edge case.

        Two evaluations per free dimension per accepted candidate, ~1.6 ms.
        """
        free = set(self.free_keys(p))
        if not free:
            return []
        keys = self.dim_keys(p)
        meff = sol.get('meff', p['meff'])
        base = self.score_dims(sol['dims'], p, meff)
        flat = []
        for key in ('d1', 'd2', 'd3'):
            if key not in free:
                continue
            moved = False
            for factor in (1.0 - rel, 1.0 + rel):
                trial = tuple(d * factor if k == key else d
                              for d, k in zip(sol['dims'], keys))
                probe = self.score_dims(trial, p, meff)
                if abs(probe - base) > self.FLAT_RTOL * max(abs(probe),
                                                            abs(base)):
                    moved = True
                    break
            if not moved:
                flat.append(key)
        return flat

    def annotate(self, sol, p) -> dict:
        """Facts ABOUT a candidate, added to it in place. Never scoring.

        Everything here is additive and diagnostic: no dimension, no error and
        no ordering is touched, so a candidate that is annotated and one that
        is not are the same answer. It runs once per ACCEPTED candidate — at
        most a dozen per spectrum — and never inside :meth:`objective`, which
        runs thousands of times and is where the entire cost of a search sits.

        What it adds, and why each one is worth a millisecond:

        ``degeneracy`` / ``partners`` on each match
            The model has always known that a "level" can be several states —
            :class:`~src.physics.quantum_dot.Level` carries the multiplicity —
            but :func:`~src.physics.quantum_dot.dot_energies` flattens it away
            before the designer sees it, so a peak assigned to a doublet was
            reported exactly like a peak assigned to a singlet. For a 4 nm /
            5 nm lens the eight rows a candidate matches against stand for
            thirteen orbital states, twenty-six with spin.
        ``n_tied``
            How many model levels lie within one resolution window of a
            matched level — the count of assignments the measurement cannot
            rule out. It is 2 at R = 6.5 nm and 18 at R = 18 nm for this disc
            at 90 K, which is the whole of why a wider size range makes the
            answer less stable rather than more accurate: the extra room is
            filled with geometries the data cannot choose between.
        ``mean_spacing_eV`` / ``unresolvable``
            The same fact as a yes/no: the model's levels across the fitted
            window are, on average, closer together than the measurement can
            resolve, so the error stops discriminating and the fit is free to
            wander.
        ``flat_dims``
            See :meth:`flat_dims` — the dimensions the fit never saw.
        ``qn_sum`` / ``n_distinct`` / ``g_sum`` / ``g_max``
            The totals the standalone calculator used to print beside each
            solution. ``n_distinct`` below the number of targets means two
            targets were assigned to the SAME level, which nearest-in-energy
            matching allows and which is worth seeing.

        A diagnostic must never take a search down with it — the same rule the
        header readers follow — so a failure to build the level table is
        logged and leaves the degeneracy keys absent. The level tables come
        from another module; a candidate without its annotations is still a
        perfectly good candidate.
        """
        matches = sol.get('matches') or []
        window = self.resolution_eV(p)
        sol['resolution_eV'] = window
        sol['resolution_basis'] = self.resolution_basis(p)

        qns = [tuple(int(q) for q in m['qn']) for m in matches]
        sol['qn_sum'] = int(sum(sum(qn) for qn in qns))
        sol['n_distinct'] = len(set(qns))
        sol['flat_dims'] = self.flat_dims(sol, p)

        # `computed_E` comes out of the ΔE modes already shifted; the ladder
        # in `Ec` is not. Adding the offset back is exact — `shifted` was
        # built as `E - offset` — so this lands on the very same floats.
        offset = float(sol.get('offset', 0.0))
        Ev = np.array([E for E, _qn in sol.get('Ec') or []], dtype=float)
        matched = np.array([m['computed_E'] + offset for m in matches],
                           dtype=float)
        if Ev.size and matched.size:
            # The mean spacing is a property of the model alone, so it is
            # recorded either way — it is the number the window is compared
            # against, and seeing it without a verdict is still informative.
            inside = np.sort(Ev[(Ev >= matched.min()) & (Ev <= matched.max())])
            if inside.size >= 2:
                sol['mean_spacing_eV'] = float(np.mean(np.diff(inside)))
            # Both of these are statements ABOUT the measurement's resolution.
            # With no resolution given there is nothing to say, and saying it
            # anyway is what made this flag useless — see resolution_eV.
            if window is not None:
                sol['n_tied'] = int(max(int(np.sum(np.abs(Ev - e0) <= window))
                                        for e0 in matched))
                spacing = sol.get('mean_spacing_eV')
                if spacing is not None:
                    sol['unresolvable'] = bool(spacing < window)

        n = max(len(p['Et']) * 3, 20)
        try:
            # Over-enumerated on purpose, by `_DEGENERACY_MARGIN`. A
            # degenerate group is only complete if every member of it is
            # inside the list, and the group straddling the cut never is:
            # asking for exactly `n` rows and grouping them would report the
            # half of a group that happened to fit as its full multiplicity.
            # The matches all live in the lowest `n` rows, so the margin puts
            # the truncation far above any of them.
            levels = levels_for(p['ndim'], p['coords'], sol['dims'],
                                sol.get('meff', p['meff']),
                                n * _DEGENERACY_MARGIN)
        except Exception as exc:
            logger.debug("no level table for %s/%s: %s — the candidate keeps "
                         "its energies and loses only its degeneracy column",
                         p['ndim'], p['coords'], exc)
            return sol

        # Keyed by the quantum numbers, never by position: in the ΔE modes
        # `match_and_score` re-indexes the matches onto a SHIFTED, truncated
        # copy of the ladder, so a stored index points into a list that no
        # longer exists and would silently name the wrong state.
        #
        # DEGENERACY IS THE GROUP'S TOTAL, NOT THE ROW'S OWN WEIGHT, and that
        # distinction is the whole correction here. `levels_for(distinct=False)`
        # hands back one row per set of quantum numbers the enumeration
        # distinguishes, each carrying only the multiplicity its own row folded
        # away: 2 for the +/-m pair of a disc, 2l+1 for a sphere — and, for
        # every Cartesian box, the literal 1, because those enumerators list
        # each permutation as its own row and put the multiplicity in the LIST
        # rather than in the row. Reporting the row's weight therefore called
        # (1,1,2) of a 5 nm cube a singlet when it is one of three, and the
        # parabolic dot's (3,0) a fourfold when at 20/30 meV it shares its
        # energy with (0,2) for a total of five. Summing over the group gets
        # both right, and leaves the disc and the sphere exactly where they
        # were: their groups have one member each unless an accidental
        # coincidence really does join them, in which case the sum is again
        # the true answer.
        weight = {}
        groups = []
        for lv in levels:
            key = tuple(int(q) for q in lv.quantum_numbers)
            weight[key] = int(lv.degeneracy)
            if groups and abs(lv.E_eV - groups[-1][0]) <= _EXACT_RTOL * abs(
                    groups[-1][0]):
                groups[-1][1].append(key)
            else:
                groups.append((lv.E_eV, [key]))
        # The last group is the only one the cut can have split, so it is not
        # trusted: a match landing in it keeps no degeneracy at all rather
        # than a halved one. With the margin above, nothing matched ever does.
        complete = groups[:-1] if len(groups) > 1 else groups
        total = {k: sum(weight[o] for o in members)
                 for _E, members in complete for k in members}
        partners = {k: [o for o in members if o != k]
                    for _E, members in complete for k in members}

        for m, qn in zip(matches, qns):
            if qn in total:
                m['degeneracy'] = total[qn]
                m['partners'] = list(partners.get(qn, ()))
        degs = [m['degeneracy'] for m in matches if 'degeneracy' in m]
        if degs:
            sol['g_sum'] = int(sum(degs))
            sol['g_max'] = int(max(degs))
        return sol

    def in_search_range(self, dims, p, meff=None) -> bool:
        """Is this geometry inside the box the search was actually given?

        One interval per FREE dimension, from :meth:`_box` — the very same
        intervals :meth:`bounds` hands the optimiser, so "inside the range"
        means the same thing here as it does there. Pinned dimensions are not
        checked: the user put them where they are, and a pin outside the
        shared slider range is a legitimate thing to ask for.

        The parabolic dot is converted before it is compared. Its ``dims`` are
        hbar*omega in meV while its box is in nanometres, so comparing them
        directly would test an energy against a length — and, since the
        relation is inverted, would get the sense of the comparison backwards
        as well.
        """
        keys = self.dim_keys(p)
        free = set(self.free_keys(p))
        meff = p['meff'] if meff is None else meff
        parabolic = (p['ndim'] == "0D" and p['coords'] == COORDS_PARABOLIC)
        for d, key in zip(dims, keys):
            if key not in free:
                continue
            lo, hi = self._box(p, key)
            try:
                size = length_from_hw(d, meff) if parabolic else float(d)
            except Exception:
                return False
            if not (lo <= size <= hi):
                return False
        return True

    def primary_alias(self, sol, p, max_factor: int = 6):
        """The SMALLEST geometry that explains the same targets.

        In every model here the energy goes as 1/L² (as hbar*omega in the
        parabolic case), so a well k times larger matches exactly the same
        targets with the quantum numbers multiplied by k. The global search
        lands on one alias or another depending on the random seed — which on
        a map turns into flickering between L, 2L and 3L from one point to
        its neighbour, looking like structure where there is only degeneracy.

        Testing L/k is deterministic and costs a few energy evaluations. The
        smallest one that still fits as well wins — the primary solution, the
        one that matches the targets with n = 1, 2, 3.

        IT SCALES THE FREE DIMENSIONS ONLY, AND GATES EACH ONE ON ITS OWN BOX.
        It used to divide every entry of ``dims`` by ``k`` with no reference
        to ``p['fixed']``, and to check the result only through
        :func:`confinement_size_nm`, the geometric MEAN of the dimensions,
        against ``p['Lmin']``. Both are wrong for the same reason: a pinned
        dimension and a per-dimension box are statements about individual
        dimensions, and a rule that can only see their average cannot honour
        either. With ``d2`` pinned at 5.0 nm under ΔE matching this returned
        (3.0, 5.0) -> (1.5, 2.5) and (3.5, 5.0) -> (0.875, 1.25) — the pin
        silently broken, and in the second case with R below the 1.0 nm floor
        — while the candidate table went on reporting "L_z = 5 nm" for those
        rows. It is rare (0 of 29 starts broke a pin at tolerances from 5 to
        40 %) but pinning is the headline answer to the runaway, and a pin
        that holds only usually is not a pin.

        An alias of a pinned dimension does not exist in any case: the user
        fixed that length, so no ``1/L²`` rescaling of it is on offer, and
        with every dimension pinned there is nothing to alias at all.
        """
        free = set(self.free_keys(p))
        if not free:
            # Nothing is being searched, so there is no alias to find: the
            # geometry the user pinned is the geometry, at every k.
            return sol
        keys = self.dim_keys(p)
        base_err = float(sol.get('RRMSE', float('inf')))
        tol = max(0.05, 0.1 * abs(base_err))
        n = max(len(p['Et']) * 3, 20)
        meff = sol.get('meff', p['meff'])
        best = sol

        for k in range(2, max_factor + 1):
            scaled = tuple(d / k if key in free else d
                           for d, key in zip(sol['dims'], keys))
            if not self.in_search_range(scaled, p, meff):
                # Every free dimension moves monotonically in k — smaller in
                # nm, and (for the parabolic dot, whose dims are energies)
                # larger in the length the box is written in — so the first k
                # that leaves the box is the last k worth trying.
                break
            try:
                Ec = self.compute_energies(scaled, meff, n, p)
                matches, offset, err = self.match_and_score(Ec, p['Et'], p)
            except Exception:
                continue
            if err <= base_err + tol:
                priority = p.get('priority', PRIORITY_UNIFORM)
                best = {**sol, 'dims': scaled, 'RRMSE': err, 'matches': matches,
                        'Ec': Ec, 'offset': offset,
                        'RRMSE_abs': self.abs_rrmse(matches, p['Et'], priority),
                        'RRMSE_dE': self.gap_rrmse(matches, p['Et'], priority)}
                logger.debug("alias: %s → %s (÷%d), error %.3f%% → %.3f%%",
                             tuple(round(d, 3) for d in sol['dims']),
                             tuple(round(d, 3) for d in scaled), k, base_err, err)
        if best is not sol:
            logger.debug("primary alias: %s instead of %s",
                         tuple(round(d, 3) for d in best['dims']),
                         tuple(round(d, 3) for d in sol['dims']))
            # `best` was built by copying `sol`, so it arrived carrying the
            # ORIGINAL geometry's degeneracies, tie count and flat dimensions.
            # Those are facts about a geometry, and the geometry just changed.
            self.annotate(best, p)
        return best

    @staticmethod
    def is_duplicate(s, sols, tol=0.1, rel=None):
        """True when a candidate's dimensions already appear in ``sols``.

        The default is the absolute 0.1 nm test the search has always used,
        and it stays the default because every candidate list anyone has
        already produced was deduplicated with it.

        ``rel`` asks the same question fractionally instead, and there is a
        measured reason to want it: along R the sub-tolerance intervals on
        this disc are 26 to 108 pm wide, so a 100 pm absolute test is the size
        of the features it is supposed to be separating and quietly merges
        distinct minima into one candidate. It is also the wrong dimension
        entirely for a parabolic dot, whose "dims" are energies in meV, where
        0.1 means 0.1 meV.
        """
        for ex in sols:
            if rel is None:
                same = all(abs(a - b) < tol
                           for a, b in zip(s['dims'], ex['dims']))
            else:
                same = all(abs(a - b) <= rel * max(abs(a), abs(b))
                           for a, b in zip(s['dims'], ex['dims']))
            if same:
                return True
        return False

    @staticmethod
    def _seed_starts(L_est, nfree, bounds, p):
        """The starting points the analytical pass refines from.

        The inherited behaviour, and still the default, is ONE isotropic start
        per estimate: ``[L_est] * nfree``, the diagonal of the search box. For
        a cube that is the answer; for a lens it is the worst guess available,
        since the whole content of the word "lens" is that R and L_z differ by
        a factor of several. It is why the analytical pass contributes almost
        nothing on a disc and the candidate list ends up being whatever the
        random global passes happened to find.

        ``p['seed_aspect']``, a list of ratios such as ``[0.5, 1.0, 2.0]``,
        stretches the FIRST dimension — R, the observable one — against the
        rest, and costs one extra local refinement per ratio per target.
        Starts are clipped into the box, which is a no-op for the default
        start (the caller has already checked ``Lmin <= L_est <= Lmax``) and
        matters only when a per-dimension box is narrower than that.
        """
        aspects = p.get('seed_aspect')
        if not aspects or nfree < 2:
            starts = [[L_est] * nfree]
        else:
            starts = [[L_est * float(a)] + [L_est] * (nfree - 1)
                      for a in aspects]
        return [[min(max(v, lo), hi) for v, (lo, hi) in zip(s, bounds)]
                for s in starts]

    def find_solutions(self, p,
                       progress: Optional[Callable[[str], None]] = None,
                       should_cancel: Optional[Callable[[], bool]] = None
                       ) -> list:
        """Candidates for one carrier at one effective mass, best error first.

        Two passes: an analytical estimate per target refined locally, then a
        global optimisation for what that misses. Anything above ``tol`` is
        discarded rather than reported as a poor fit.

        ``should_cancel`` is asked before each analytical estimate and before
        each global pass. One differential_evolution run at maxiter=200 is
        the longest stretch this method is stuck inside with no way out, so
        between the passes is the finest granularity the search has to offer
        — and it is enough to turn a Cancel that used to be ignored for the
        whole of a carrier into one that lands within a pass. When it answers
        True the search stops where it is and RETURNS the candidates found so
        far instead of raising: a partial list is still a list of real
        solutions, and whether a partial answer is worth showing is the
        caller's decision, not this method's.

        ``progress``, when given, is told which pass is running — the global
        passes are the slow ones and a silent minute looks like a hang.
        """
        bounds = self.bounds(p)
        nfree = len(bounds)
        sols = []

        if nfree == 0:
            sols.append(self.extract_solution([], p))
            return sols

        if self._parallel():
            return self._find_solutions_parallel(p, bounds, progress,
                                                 should_cancel)

        # Analytical estimates
        m = p['meff'] * m_e
        nest = len(p['Et'])
        for i, Er in enumerate(p['Et']):
            if should_cancel is not None and should_cancel():
                # Returns rather than breaks: with the estimates abandoned
                # there is no reason to go on to the far slower global pass.
                logger.info("find_solutions cancelled during the analytical "
                            "estimates: %d candidate(s) kept", len(sols))
                sols.sort(key=lambda x: x['RRMSE'])
                return sols[:p['maxsol']]
            if progress is not None:
                progress(f"analytical estimate {i + 1}/{nest}")
            E_J = Er * e
            pf = hbar ** 2 * np.pi ** 2 / (2.0 * m)
            # A hard sphere's ground state is hbar^2*pi^2/(2 m R^2), the same
            # form as a 1D box — so 0D enters the estimate as 1.
            ndim_int = max(1, int(p['ndim'][0]))
            L_est = np.sqrt(ndim_int * pf / E_J) * 1e9
            if p['Lmin'] <= L_est <= p['Lmax']:
                for start in self._seed_starts(L_est, nfree, bounds, p):
                    try:
                        res = minimize(self.objective, start,
                                       args=(p,), method='L-BFGS-B',
                                       bounds=bounds)
                        if res.fun <= p['tol']:
                            s = self.extract_solution(res.x, p)
                            if not self.is_duplicate(s, sols,
                                                     rel=p.get('dup_rel')):
                                sols.append(s)
                    except Exception:
                        pass

        # Global optimisation
        npass = p['maxsol'] * 2
        for i in range(npass):
            if len(sols) >= p['maxsol']:
                break
            if should_cancel is not None and should_cancel():
                logger.info("find_solutions cancelled after %d/%d global "
                            "pass(es): %d candidate(s) kept",
                            i, npass, len(sols))
                break
            if progress is not None:
                progress(f"global search pass {i + 1}/{npass}")
            try:
                res = differential_evolution(
                    self.objective, bounds, args=(p,),
                    maxiter=200, tol=0.01, seed=int(self._rng.integers(10000)))
                if res.fun <= p['tol']:
                    s = self.extract_solution(res.x, p)
                    if not self.is_duplicate(s, sols, rel=p.get('dup_rel')):
                        sols.append(s)
            except Exception:
                pass

        sols.sort(key=lambda x: x['RRMSE'])
        return sols[:p['maxsol']]

    def _accept(self, out, p, sols) -> None:
        """The serial loop's acceptance step, for one pooled ``(fun, x)``."""
        if out is None:
            return
        fun, x = out
        try:
            if fun <= p['tol']:
                s = self.extract_solution(x, p)
                if not self.is_duplicate(s, sols, rel=p.get('dup_rel')):
                    sols.append(s)
        except Exception:
            pass

    def _find_solutions_parallel(self, p, bounds, progress, should_cancel):
        """:meth:`find_solutions` with its independent passes on ``mapper``.

        Every analytical start is refined at once, then the global passes run
        in waves of ``mapper.workers``. Results are replayed in the serial
        order through the serial acceptance step, and the wave stops being
        read the moment the quota fills — so the candidates are the serial
        ones, bit for bit. The seeds come from the same RNG in the same
        order; the passes a wave ran past the quota are speculative, and the
        RNG is rewound to where the serial loop would have left it, so a
        later search on this Designer draws what it always drew.

        Cancel is checked between waves (and by the mapper while it waits);
        a pass already running finishes, which is at most one pass.
        """
        sols = []
        m = p['meff'] * m_e
        ndim_int = max(1, int(p['ndim'][0]))
        pf = hbar ** 2 * np.pi ** 2 / (2.0 * m)
        starts = []
        for Er in p['Et']:
            L_est = np.sqrt(ndim_int * pf / (Er * e)) * 1e9
            if p['Lmin'] <= L_est <= p['Lmax']:
                starts.extend(self._seed_starts(L_est, len(bounds), bounds, p))
        if should_cancel is not None and should_cancel():
            return sols
        if starts:
            if progress is not None:
                progress(f"analytical estimates ({len(starts)} in parallel)")
            outs = self.mapper.map(_pool_minimize,
                                   [(p, s, bounds) for s in starts],
                                   should_cancel)
            if outs is None:
                logger.info("find_solutions cancelled during the analytical "
                            "estimates")
                return sols
            for out in outs:
                self._accept(out, p, sols)

        npass = p['maxsol'] * 2
        state = self._rng.bit_generator.state
        seeds = [int(self._rng.integers(10000)) for _ in range(npass)]
        used = 0
        wave = max(1, self.mapper.workers)
        while used < npass and len(sols) < p['maxsol']:
            if should_cancel is not None and should_cancel():
                logger.info("find_solutions cancelled after %d/%d global "
                            "pass(es): %d candidate(s) kept",
                            used, npass, len(sols))
                break
            batch = seeds[used:used + wave]
            if progress is not None:
                progress(f"global search passes {used + 1}-"
                         f"{used + len(batch)}/{npass}")
            outs = self.mapper.map(_pool_evolve,
                                   [(p, bounds, s) for s in batch],
                                   should_cancel)
            if outs is None:
                break
            for out in outs:
                if len(sols) >= p['maxsol']:
                    break
                used += 1
                self._accept(out, p, sols)
        self._rng.bit_generator.state = state
        for _ in range(used):
            self._rng.integers(10000)

        sols.sort(key=lambda x: x['RRMSE'])
        return sols[:p['maxsol']]

    # ─── enumerating the valley instead of sampling it ───────────────────

    #: The box the polish budget is counted against: ``[1 nm, 18 nm]`` per
    #: free dimension — the box she actually runs — measured in octaves,
    #: ``log2(18) = 4.17``. See :meth:`polish_budget`.
    POLISH_REFERENCE_OCTAVES = float(np.log2(18.0))

    #: Hard ceiling on the refinement budget, as a multiple of ``enum_polish``.
    POLISH_MAX_FACTOR = 10

    #: A lattice this small is refined EXHAUSTIVELY rather than by density.
    #: A box narrower than the reference has fewer basins and honestly needs
    #: fewer starting points, but density alone sends a tightly boxed search
    #: (2–8 nm by 4–6 nm at 4 nodes per octave is 27 nodes and 0.07 reference
    #: boxes) to a single refinement — and one descent that misses tolerance
    #: is then the difference between a population and an empty table. Below
    #: this many nodes the whole lattice costs less than one
    #: differential-evolution pass, so completeness is simply cheaper than
    #: choosing. Still bounded by ``POLISH_MAX_FACTOR * enum_polish``, so a
    #: user who asked for very few refinements keeps getting very few.
    POLISH_ALL_BELOW = 32

    @staticmethod
    def lattice(lo, hi, p, max_nodes=None,
                should_cancel: Optional[Callable[[], bool]] = None
                ) -> List[float]:
        """Geometric nodes ``L_k = lo * r**k <= hi``, ``r = 2**(1/per_octave)``.

        Two properties, both of which the grid this search descends from
        lacked, and both of which are the reason it is written out here rather
        than as one ``np.linspace``.

        NESTED. The nodes are anchored at ``lo`` and truncated at ``hi``, never
        redistributed between them. Widening the range can therefore only ADD
        nodes: the lattice at 13 nm is a strict subset of the lattice at 18 nm,
        and every candidate that existed at 13 nm is still found, unmoved, at
        18. ``np.linspace(Lmin, Lmax, 15)`` puts its nodes somewhere different
        for every Lmax, so moving the slider moves every node — it would
        manufacture exactly the 13-versus-18 disagreement this is meant to
        explain. ``L_k`` is computed from ``k`` rather than accumulated by
        repeated multiplication so that the same ``k`` gives the same float in
        both runs, bit for bit, which is what "subset" has to mean here.

        GEOMETRIC. E goes as 1/L², so equal RATIOS of L are equal steps in the
        quantity being fitted; log-spaced nodes are roughly evenly spaced in
        resolvable levels. A uniform grid over [1, 18] nm spends more than half
        its nodes above 10 nm, where the model's levels are closer together
        than the measurement can resolve and every node fits equally
        meaninglessly, and starves the few nm below 6 nm where all of the real
        local minima actually live.

        BOUNDED WHILE IT IS BUILT, not after. ``enum_per_octave`` is validated
        first, because the loop's termination depends on it and nothing else:
        at a NEGATIVE value ``r = 2**(1/per_octave) < 1``, so ``v`` decreases
        monotonically, never exceeds ``hi``, and the loop never ends — a hang
        with no way out, since ``enum_max_nodes`` used to be checked only
        after this method returned and ``should_cancel`` was not polled inside
        it. The panel clamps its spin box to 1..64, but the value travels
        through ``params`` from any workflow node or scripted caller, so the
        clamp is not where this belongs. A non-finite or non-positive value is
        now a ``ValueError`` before the first iteration, the node count is
        checked against ``max_nodes`` AS the nodes are appended, and
        ``should_cancel`` is asked every 256 nodes so a Cancel lands inside
        the construction rather than after it. A positive but absurd density
        is refused on the same grounds: below one node per octave the step
        ratio overflows a double (``2**10000`` at 1e-4) and above ~1e16 it
        rounds down to exactly 1.0, so the nodes stop advancing.
        """
        raw = p.get('enum_per_octave')
        per_octave = float(8 if raw is None or raw == 0 else raw)
        if not np.isfinite(per_octave) or per_octave <= 0:
            raise ValueError(
                f"'enum_per_octave' must be a positive, finite number of "
                f"nodes per octave; got {raw!r}. Zero or less makes the "
                f"geometric lattice run downwards and never reach the top of "
                f"the range")
        cap = int(max_nodes if max_nodes is not None
                  else (p.get('enum_max_nodes') or 200000))
        lo, hi = float(lo), float(hi)
        if lo <= 0 or hi < lo:
            return [lo]
        # A density far below one node per octave makes the step ratio
        # 2**(1/per_octave) larger than a double can hold — 2**10000 at
        # 1e-4 — and CPython raises OverflowError out of the exponentiation
        # itself rather than returning an infinity. A density far above
        # 1e16 rounds the ratio down to exactly 1.0, so `v` never advances
        # and the loop only stops when it hits the node cap. Both are the
        # same class of failure as the negative value refused above: a
        # number no panel can produce, arriving through `params` from a
        # workflow node or a script, and both deserve the named refusal
        # rather than an arithmetic traceback out of a worker thread or a
        # loop that runs to the cap before saying anything.
        try:
            r = 2.0 ** (1.0 / per_octave)
        except OverflowError:
            r = float('inf')
        if not np.isfinite(r) or r <= 1.0:
            raise ValueError(
                f"'enum_per_octave' = {raw!r} asks for a step ratio of "
                f"2**{1.0 / per_octave:g} per node, which is not a usable "
                f"spacing; use between one node per octave and about 1e15")
        out: List[float] = []
        while True:
            if len(out) >= cap:
                raise ValueError(
                    f"the lattice over [{lo:g}, {hi:g}] nm would exceed "
                    f"{cap} nodes at {per_octave:g} per octave; lower "
                    f"'enum_per_octave' or raise 'enum_max_nodes'")
            if (len(out) % 256) == 0 and should_cancel is not None \
                    and should_cancel():
                logger.info("lattice construction cancelled after %d node(s)",
                            len(out))
                break
            v = lo * r ** len(out)
            if v > hi * (1.0 + 1e-12):
                break
            out.append(v)
        return out

    @staticmethod
    def refinement_box(node, bounds, p):
        """The interval each refinement is allowed to move a node inside.

        ONE LATTICE STEP EITHER WAY, clipped to the search box — not the whole
        search box, which is what the refinements used to be handed and which
        is the second half of why the candidate list did not inherit the
        lattice's nesting.

        A node is a STARTING POINT for a local descent into its own basin; the
        lattice is deliberately dense enough that it has one node per basin
        and a good deal more (node spacing ~1 nm, sub-tolerance intervals
        along R 26 to 108 pm wide). Given the full box, L-BFGS-B does not do a
        local descent: on a valley that is flat along L_z its trajectory
        depends on the bounds it was given, so the SAME node refined in
        [1, 13] nm and in [1, 18] nm ends somewhere different. Measured, the
        node (6.1688, 6.7272) landed on (6.4681, 6.4105) at 13 nm and on
        (6.3130, 6.7117) at 18 — which is what "R = 6.4681 nm exists at 13 and
        is gone at 18" actually was, once the node itself was no longer being
        dropped. Confined to its own cell the same node lands on the same
        point at 13, 18 and 25 nm, bit for bit, because nothing about its box
        depends on the ceiling.

        Two things it also buys, neither of them the reason but both measured:
        the refinements get cheaper, and they get BETTER — the enumeration now
        reaches the true 4.0 nm well at RRMSE 0.0000 on her disc, where
        refining against the whole box wandered off it and returned 1.3115 %
        as its best candidate.

        Nodes within one step of the top of the range are the exception, and
        honestly so: their cell is clipped by the ceiling, so raising the
        ceiling can move them. That is the search range genuinely ending,
        not an artefact of the ranking.
        """
        raw = p.get('enum_per_octave')
        per_octave = float(8 if raw is None or raw == 0 else raw)
        step = 2.0 ** (1.0 / per_octave)
        return [(max(lo, v / step), min(hi, v * step))
                for v, (lo, hi) in zip(node, bounds)]

    @classmethod
    def polish_budget(cls, bounds, p, total_nodes=None) -> int:
        """How many lattice nodes get refined — scaled to the BOX, not fixed.

        ``enum_polish`` used to be an absolute count: the best 40 nodes,
        whatever the lattice. That is what broke the one guarantee the
        geometric lattice exists to provide. :meth:`lattice` is perfectly
        nested — the nodes at 13 nm are bit-for-bit the first nodes at 18 nm,
        verified at 3, 4, 6, 8, 12 and 16 per octave and at non-integer
        densities — but the CANDIDATE LIST was not, because a fixed 40 is a
        shrinking share of a growing lattice: 40 of 900 nodes at L_max = 13 nm
        (4.4 %), 40 of 1156 at 18 (3.5 %), 40 of 1444 at 25 (2.8 %). Nodes
        that made the cut at 13 dropped out of it at 18, and their candidates
        with them: R = 6.4681 nm existed at 13 nm and was gone at 18; five of
        the nineteen found at 18 were gone at 25; widening 18 -> 25 REDUCED
        the count from 19 to 16. Meanwhile the panel, this module's
        docstrings and ``_designer_find`` all told the user that "widening the
        range can only ADD candidates, never move the ones already found".

        So the budget is a DENSITY instead: ``enum_polish`` refinements per
        reference box, times how many reference boxes the actual box is.
        Volume is measured in OCTAVES — ``prod(log2(hi/lo))`` over the free
        dimensions, against :data:`POLISH_REFERENCE_OCTAVES` per dimension —
        because octaves are what the lattice is built in and what the physics
        is even in: E goes as 1/L². Two consequences, both wanted:

        * the refined FRACTION of the lattice no longer depends on the
          ceiling, so a node ranked inside it at 13 nm is still inside it at
          18 and at 25, and the candidate list inherits the lattice's nesting.
          Measured on her disc: 32 / 40 / 50 refinements at 13 / 18 / 25 nm,
          and the selected node set at each ceiling is a strict subset of the
          next — where the fixed 40 was 5 nodes short at 13 -> 18 and 2 short
          at 18 -> 25.
        * the budget does NOT grow with ``enum_per_octave``. A denser lattice
          over the same box has more nodes but the same basins, so refining
          more of them is spent work; at 64 per octave the old rule would
          have quadrupled the cost for nothing.

        The default is unchanged where it matters: her shipped box is exactly
        the reference one, 1 to 18 nm in two free dimensions, and still gets
        40 refinements.

        A lattice of at most :data:`POLISH_ALL_BELOW` nodes is refined IN
        FULL instead — see that constant; the floor is exhaustive or it is
        inert, never an absolute 32 under a larger lattice — and the whole
        thing is capped at
        :data:`POLISH_MAX_FACTOR` times ``enum_polish``. Past the cap the
        selection is an absolute top-N again and the subset guarantee lapses;
        below the exhaustive floor there is no selection to be nested. Both
        said out loud here rather than left to be discovered.
        """
        want = int(p.get('enum_polish', 40) or 0)
        if want <= 0:
            return 0
        volume = 1.0
        for lo, hi in bounds:
            lo, hi = float(lo), float(hi)
            if lo <= 0 or hi <= lo:
                continue
            volume *= np.log2(hi / lo) / cls.POLISH_REFERENCE_OCTAVES
        budget = int(np.ceil(want * volume))
        if total_nodes is not None and int(total_nodes) <= cls.POLISH_ALL_BELOW:
            # EXHAUSTIVE OR NOTHING. The floor refines the WHOLE lattice when
            # the lattice is tiny, and is inert otherwise. Written as
            # `max(budget, min(total_nodes, POLISH_ALL_BELOW))` it also put an
            # absolute floor of 32 under every larger lattice, which is the
            # very rule this method exists to remove: a small box (2 to 8 nm
            # at 4 per octave, 81 nodes) and a wider one (2 to 13 nm, 121)
            # then both refined exactly 32 nodes, 39.5 % of the first lattice
            # against 26.4 % of the second, and the selection stopped being
            # nested again — 14 of 28 candidates lost on widening, measured.
            # Her own box never reached it (900 nodes at 13 nm want 32
            # refinements on the density rule alone), so the floor was inert
            # where it was looked at and wrong everywhere else.
            budget = max(budget, int(total_nodes))
        return int(min(max(1, budget), cls.POLISH_MAX_FACTOR * want))

    def enumerate_solutions(self, p,
                            progress: Optional[Callable[[str], None]] = None,
                            should_cancel: Optional[Callable[[], bool]] = None
                            ) -> list:
        """Every distinct candidate in the box, deterministically. Opt-in.

        :meth:`find_solutions` answers "give me a few good geometries". It does
        it with up to ``maxsol * 2`` differential-evolution passes, each from a
        fresh random seed, and keeps the first ``maxsol`` that come in under
        tolerance. That is a SAMPLE of the acceptable set, not a survey of it,
        and when the acceptable set is large the sample is a lottery: on this
        disc there are roughly 18 distinct sub-tolerance basins inside a 13 nm
        box and 23 inside an 18 nm one, so six draws reshuffle from run to run
        while the global minimum — identical at 13, 18 and 25 nm — is missed
        about as often as it is found.

        This method answers the other question: "how many are there, and where
        are they?" It is deterministic, has no RNG anywhere, and — SINCE THE
        FIX RECORDED IN :meth:`polish_budget` AND :meth:`refinement_box` —
        nested: widening the range adds candidates and moves none of the ones
        already found, bit for bit. Measured on her disc at 13 / 18 / 25 nm,
        21 -> 23 -> 24 candidates with every earlier geometry reproduced
        exactly. It was not nested before, and the panel said it was: an
        absolute top-40 over a lattice that grows with L_max is a shrinking
        share of it, and a refinement given the whole box follows a
        trajectory that depends on the box. Both had to go, and both were
        dropping or moving candidates on their own.

        It returns the FULL deduplicated population rather than ``maxsol`` of
        it, because
        ``maxsol`` is a display quota and truncating an enumeration whose
        entire purpose is counting would defeat it. The caller decides how many
        rows to show; the population is what a marginal distribution over R is
        computed from, and that marginal — unlike the top-six list, whose
        median moves by more than a nanometre between bounds — has its mode at
        the same R at 13, 18 and 25 nm.

        Two phases, in this order for a measured reason. Raw lattice nodes are
        worthless AS candidates: scored directly on this disc, zero of them
        come in under tolerance at 13 nm, and the three that do at 18 nm score
        3.07 to 3.76 % against the 0.46 % a refinement reaches, because the
        node spacing is ~1 nm while the acceptable intervals along R are 26 to
        108 pm wide. So the nodes are used only to RANK the box, and the best
        ``enum_polish`` of them are handed to L-BFGS-B as starting points. This
        is also why the grid pass the standalone calculator had would not have
        helped: besides rescaling with the box, it kept nodes as answers.

        It is ungated. The old grid search ran only ``if len(solutions) <
        max_sol``, and since the random passes fill six slots on about 94 % of
        spectra, it was dead code almost every time it was called — which is
        the likeliest reason nobody noticed it had been dropped.

        Budget at the defaults, MEASURED on an M1 Pro rather than estimated:
        two free dimensions, 1 to 18 nm, 8 nodes per octave gives 34 nodes per
        dimension, 1156 evaluations plus its refinements — 9.5 to 9.8 s per
        spectrum per mass, so ~50 min for 300 spectra on one mass and carrier.

        The comparison worth making is not the mean but the SPREAD, because
        the default sampled search is NOT one number: over five seeds on
        the same spectrum it took 13.1, 15.1, 16.3, 42.5 and 73.8 s — a 5.6x
        spread, median 16.3 s. That variance is structural, not noise:
        ``find_solutions`` stops at ``maxsol``, so a spectrum whose quota
        fills early runs a few DE passes and one whose quota never fills runs
        all twelve. Enumeration over the same spectrum took 9.5, 9.7 and 9.8 s
        — it has no RNG, so it costs what it costs. For a 300-spectrum sweep
        that is the difference between planning for 50 minutes and not knowing
        whether to plan for 65 minutes or six hours.
        (Two earlier versions of this paragraph quoted 4.4 s and then 25.9 s
        for the sampled search; the first was optimistic, the second was one
        unlucky draw read as the typical cost.) ``enum_per_octave``
        trades node count against completeness (the refinement budget is
        deliberately independent of it — see :meth:`polish_budget`);
        ``enum_max_nodes`` refuses rather than silently spending a quarter of
        an hour on a three-dimensional lattice.

        ``should_cancel`` is polled every 64 raw nodes and before every
        refinement — finer than :meth:`find_solutions` can offer, since its
        smallest indivisible unit is a whole DE pass.
        """
        bounds = self.bounds(p)
        if not bounds:
            # Every dimension pinned: there is exactly one geometry, and it is
            # the answer. Same short-circuit as `find_solutions`.
            return [self.extract_solution([], p)]

        cap = int(p.get('enum_max_nodes') or 200000)
        # The cap is handed DOWN rather than checked on the way back: a bad
        # `enum_per_octave` makes `lattice` loop forever, so the bound has to
        # exist inside the construction. No single axis may exceed the total
        # cap, since the product cannot be smaller than any of its factors.
        axes = [self.lattice(lo, hi, p, max_nodes=cap,
                             should_cancel=should_cancel)
                for lo, hi in bounds]
        if should_cancel is not None and should_cancel():
            logger.info("enumerate_solutions cancelled while building the "
                        "lattice")
            return []
        total = 1
        for axis in axes:
            total *= len(axis)
        if total > cap:
            raise ValueError(
                f"the lattice would be {total} nodes (cap {cap}); lower "
                f"'enum_per_octave' (now {p.get('enum_per_octave') or 8}) or "
                f"raise 'enum_max_nodes'")

        if self._parallel():
            return self._enumerate_parallel(p, bounds, axes, total, progress,
                                            should_cancel)

        scored = []
        for i, node in enumerate(itertools.product(*axes)):
            if (i % 64) == 0 and should_cancel is not None and should_cancel():
                logger.info("enumerate_solutions cancelled after %d/%d lattice "
                            "nodes", i, total)
                break
            if progress is not None and (i % 256) == 0:
                progress(f"lattice node {i + 1}/{total}")
            try:
                scored.append((self.objective(list(node), p), node))
            except Exception:
                continue
        scored.sort(key=lambda entry: entry[0])

        npolish = self.polish_budget(bounds, p, total)
        window = scored[:npolish]
        sols = []
        for k, (_err, node) in enumerate(window):
            if should_cancel is not None and should_cancel():
                logger.info("enumerate_solutions cancelled after %d/%d "
                            "refinements: %d candidate(s) kept",
                            k, len(window), len(sols))
                break
            if progress is not None:
                progress(f"refining lattice node {k + 1}/{len(window)}")
            try:
                res = minimize(self.objective, list(node), args=(p,),
                               method='L-BFGS-B',
                               bounds=self.refinement_box(node, bounds, p))
            except Exception:
                continue
            if res.fun > p['tol']:
                continue
            try:
                s = self.extract_solution(res.x, p)
            except Exception:
                # Same rule as `find_solutions`, which wraps its whole
                # refine-and-extract block: one candidate that cannot be
                # built is a candidate dropped, never an enumeration
                # abandoned. `extract_solution` reaches `annotate` ->
                # `flat_dims` -> `score_dims`, so anything the level tables
                # or the sensitivity probe can raise used to take the entire
                # population down with it and return nothing at all.
                logger.debug("enumerate_solutions: candidate from node %r "
                             "could not be built; dropped", node,
                             exc_info=True)
                continue
            if p.get('reject_unresolvable') and s.get('unresolvable'):
                # Not a bad fit — an undecidable one. The model's levels
                # across the fitted window are closer together than the
                # measurement resolves, so the error has stopped
                # discriminating between geometries. Off by default: it is a
                # judgement about the DATA, and the user makes it.
                continue
            if not self.is_duplicate(s, sols, rel=p.get('dup_rel')):
                sols.append(s)

        sols.sort(key=lambda x: x['RRMSE'])
        logger.info("enumerate_solutions: %d lattice node(s), %d refinement(s)"
                    ", %d distinct candidate(s)", total, len(window), len(sols))
        return sols

    def _enumerate_parallel(self, p, bounds, axes, total, progress,
                            should_cancel):
        """:meth:`enumerate_solutions`' two phases on ``mapper``.

        The lattice is scored in contiguous chunks and concatenated in
        product order, so the stable sort ranks it exactly as the serial
        pass did; the refinements run in batches and are replayed in rank
        order through the same acceptance rules. Same population, bit for
        bit. Cancel is checked between batches and returns what was kept.
        """
        nodes = list(itertools.product(*axes))
        workers = max(1, self.mapper.workers)
        size = max(16, -(-len(nodes) // (workers * 4)))
        chunks = [nodes[i:i + size] for i in range(0, len(nodes), size)]
        if progress is not None:
            progress(f"scoring {total} lattice nodes on {workers} processes")
        outs = self.mapper.map(_pool_score, [(p, c) for c in chunks],
                               should_cancel)
        if outs is None:
            logger.info("enumerate_solutions cancelled while scoring the "
                        "lattice")
            return []
        scored = [(err, node) for chunk, errs in zip(chunks, outs)
                  for node, err in zip(chunk, errs) if err is not None]
        scored.sort(key=lambda entry: entry[0])

        npolish = self.polish_budget(bounds, p, total)
        window = scored[:npolish]
        sols = []
        batch = workers * 2
        for k in range(0, len(window), batch):
            if should_cancel is not None and should_cancel():
                logger.info("enumerate_solutions cancelled after %d/%d "
                            "refinements: %d candidate(s) kept",
                            k, len(window), len(sols))
                break
            if progress is not None:
                progress(f"refining lattice nodes {k + 1}-"
                         f"{min(k + batch, len(window))}/{len(window)}")
            part = window[k:k + batch]
            outs = self.mapper.map(
                _pool_minimize,
                [(p, list(node), self.refinement_box(node, bounds, p))
                 for _err, node in part],
                should_cancel)
            if outs is None:
                break
            for (_err, node), out in zip(part, outs):
                if out is None or out[0] > p['tol']:
                    continue
                try:
                    s = self.extract_solution(out[1], p)
                except Exception:
                    logger.debug("enumerate_solutions: candidate from node %r "
                                 "could not be built; dropped", node,
                                 exc_info=True)
                    continue
                if p.get('reject_unresolvable') and s.get('unresolvable'):
                    continue
                if not self.is_duplicate(s, sols, rel=p.get('dup_rel')):
                    sols.append(s)

        sols.sort(key=lambda x: x['RRMSE'])
        logger.info("enumerate_solutions: %d lattice node(s), %d refinement(s)"
                    ", %d distinct candidate(s), on %d processes",
                    total, len(window), len(sols), workers)
        return sols

    # ─── one search for every effective mass ─────────────────────────────

    def shares_mass_search(self, p, meffs) -> bool:
        """Can one search stand in for every mass in ``meffs``?

        Every model here depends on the mass and the lengths only through
        m*·L²: the hard-wall ladders are hbar²k²/(2 m* L²), and the parabolic
        dot's hbar*omega is hbar²/(m* l²) of the length it is searched in. So
        the geometry that fits at m₂ is the one that fits at m₁ with every
        length times sqrt(m₁/m₂), at the same error — measured on the lens to
        5e-14 relative, which is float noise. Searching each mass separately
        finds the same population again, rescaled, at full price per mass.

        Not when a dimension is pinned: a pinned length cannot rescale, so
        the equivalence breaks. ``p['share_mass_search'] = False`` restores
        the per-mass searches.
        """
        if len(meffs) < 2 or not p.get('share_mass_search', True):
            return False
        return all(v is None for v in (p.get('fixed') or {}).values())

    def _free_opt(self, sol, p, meff) -> List[float]:
        """The optimiser vector that produced ``sol['dims']`` at ``meff``."""
        keys = self.dim_keys(p)
        parabolic = (p['ndim'] == "0D" and p['coords'] == COORDS_PARABOLIC)
        out = []
        for key in self.free_keys(p):
            d = sol['dims'][keys.index(key)]
            out.append(length_from_hw(d, meff) if parabolic else float(d))
        return out

    def reference_search(self, p, meffs) -> dict:
        """The search, at ``meffs[0]``, whose box covers every mass's box.

        A length L at mass m is the length L·sqrt(m/m_ref) at the reference
        mass, so each free dimension's interval is mapped there and the union
        taken. The lattice is anchored at the union's floor, so it is the
        same lattice for the same mass list — but not the lattice a
        single-mass run builds. For :meth:`find_solutions` that does not
        matter, its starts are random anyway. For :meth:`enumerate_solutions`
        it does: the enumeration depends on where its lattice is anchored
        (on the 4/6 nm lens, Lmin 0.9-1.0 nm finds the true well and 0.85 or
        1.05 misses it), so the backend keeps enumeration per mass unless
        asked otherwise.
        """
        m_ref = float(meffs[0])
        box = {}
        for key in self.free_keys(p):
            lo, hi = self._box(p, key)
            scaled = [(lo * np.sqrt(m / m_ref), hi * np.sqrt(m / m_ref))
                      for m in meffs]
            box[key] = (min(s[0] for s in scaled), max(s[1] for s in scaled))
        return {**p, 'meff': m_ref, 'box': box,
                'Lmin': min(b[0] for b in box.values()),
                'Lmax': max(b[1] for b in box.values())}

    def rescale_to_mass(self, sols, p_ref, p_m) -> list:
        """The reference search's candidates, as candidates at ``p_m['meff']``.

        Each one is moved to its equivalent geometry, kept only if that lies
        inside this mass's own box (a relative 1e-9 of slack, so a candidate
        on the edge is not lost to the rounding of the square root), and
        rebuilt by :meth:`extract_solution` at this mass — so its ladder,
        offset, annotations and ``meff`` are this mass's, computed rather
        than copied. The tolerance and ``reject_unresolvable`` are applied
        again on the rebuilt candidate.
        """
        k = np.sqrt(p_ref['meff'] / p_m['meff'])
        bounds = self.bounds(p_m)
        out = []
        for sol in sols:
            opt = [v * k for v in self._free_opt(sol, p_ref, p_ref['meff'])]
            inside = all(lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9)
                         for v, (lo, hi) in zip(opt, bounds))
            if not inside:
                continue
            opt = [min(max(v, lo), hi) for v, (lo, hi) in zip(opt, bounds)]
            try:
                s = self.extract_solution(opt, p_m)
            except Exception:
                logger.debug("rescale_to_mass: candidate %r could not be "
                             "rebuilt at m*=%g; dropped", sol.get('dims'),
                             p_m['meff'], exc_info=True)
                continue
            if s['RRMSE'] > p_m['tol']:
                continue
            if p_m.get('reject_unresolvable') and s.get('unresolvable'):
                continue
            out.append(s)
        return out

    def search_masses(self, p: dict, carrier: dict, search,
                      progress: Optional[Callable[[str], None]] = None,
                      should_cancel: Optional[Callable[[], bool]] = None
                      ) -> list:
        """``search(pm)`` once per mass, or once for all of them.

        ``search`` is :meth:`find_solutions` or :meth:`enumerate_solutions`
        with its keyword arguments bound. When :meth:`shares_mass_search`
        allows it, it runs once over :meth:`reference_search` and every mass
        gets the rescaled population; otherwise it runs per mass, as it
        always has. The candidates come back unsorted and undeduplicated —
        that is the caller's, which knows its quota.
        """
        meffs = list(carrier['meffs'])
        base = {**p, 'Et': carrier['Et'], 'carrier': carrier['carrier']}
        if self.shares_mass_search(base, meffs):
            if should_cancel is not None and should_cancel():
                return []
            p_ref = self.reference_search(base, meffs)
            label = (f"{carrier['label']}s, one search for m* = "
                     + ", ".join(f"{m:g}" for m in meffs))
            if progress is not None:
                progress(f"Searching {label}…")
            ref = search(p_ref, label)
            found = []
            for meff in meffs:
                found.extend(self.rescale_to_mass(ref, p_ref,
                                                  {**base, 'meff': meff}))
            logger.info("search %s: one search, %d reference candidate(s), "
                        "%d over %d mass(es)", carrier['label'], len(ref),
                        len(found), len(meffs))
            return found

        found = []
        for meff in meffs:
            if should_cancel is not None and should_cancel():
                logger.info("search %s cancelled before m*=%g: %d candidate(s)"
                            " kept", carrier['label'], meff, len(found))
                break
            label = f"{carrier['label']}s with m* = {meff:g}"
            if progress is not None:
                progress(f"Searching {label}…")
            sols = search({**base, 'meff': meff}, label)
            logger.info("search %s m*=%g: %d candidate(s)",
                        carrier['label'], meff, len(sols))
            found.extend(sols)
        return found

    def search_carrier(self, p: dict, carrier: dict,
                       progress: Optional[Callable[[str], None]] = None,
                       should_cancel: Optional[Callable[[], bool]] = None
                       ) -> list:
        """Search one carrier's candidates at every effective mass.

        The same energy with a larger mass asks for a larger well, and each
        candidate comes out stamped with its own mass, so the final list can
        mix them without losing track of which mass produced which geometry.
        Where the masses allow it the search runs ONCE and every mass gets
        the rescaled population — see :meth:`search_masses`.

        ``should_cancel`` is asked before each mass and handed down to
        ``find_solutions``, which polls it between its own optimisation
        passes. A list of masses was the longest uninterruptible block in the
        designer: three masses is three full searches, and a Cancel ignored
        for that long reads as a freeze. A cancelled search returns what it
        has already found, deduplicated exactly like a complete one, instead
        of raising — the caller decides whether a partial list is worth
        keeping.

        ``progress`` is told which mass is starting and is then passed on to
        ``find_solutions`` prefixed with that mass, so the wait inside one
        mass's search is visible too and not just the gaps between them.
        """
        def search(pm, label):
            return self.find_solutions(
                pm,
                progress=(None if progress is None else
                          lambda msg: progress(f"{label}: {msg}")),
                should_cancel=should_cancel)

        found = self.search_masses(p, carrier, search, progress=progress,
                                   should_cancel=should_cancel)

        # The same geometry AND the same mass is a duplicate; the same
        # geometry at different masses is not — they are distinct answers to
        # the same question.
        unique = []
        for sol in sorted(found, key=lambda x: x['RRMSE']):
            if not any(abs(sol['meff'] - ex['meff']) < 1e-9
                       and self.is_duplicate(sol, [ex], rel=p.get('dup_rel'))
                       for ex in unique):
                unique.append(sol)
        return unique[:p['maxsol']]

    # ─── ordering the candidates ─────────────────────────────────────────

    @staticmethod
    def confinement_size(sol) -> float:
        """The candidate's effective confinement size, in nm.

        The geometric mean of the dimensions: the edge of the cube of equal
        volume, so it compares a 30x2x2 well with a 5x5x5 one by the quantity
        that sets the energy scale rather than by the longest edge.

        In the parabolic dot the "dimensions" are hbar*omega in meV; there
        the conversion to a confinement length is mandatory, or a hard dot
        (high hbar*omega) would show up as the largest of all, which is
        exactly backwards.
        """
        # The mass is the candidate's: with a list of masses, the panel's
        # describes none of them.
        return confinement_size_nm(sol, sol.get('meff'))

    @staticmethod
    def anisotropy(sol) -> float:
        """Ratio of the largest to the smallest dimension; 1.0 = isotropic."""
        dims = [abs(d) for d in sol['dims'] if d]
        if not dims:
            return float("inf")
        return max(dims) / min(dims)

    @staticmethod
    def ground_state(sol) -> float:
        """The lowest energy the candidate produces (eV)."""
        return min((E for E, _qn in sol['Ec']), default=float("inf"))

    def sort_key(self, mode, paired: bool = False):
        """``(key, reverse)`` for one of the ``SORT_*`` modes.

        ``paired`` says an electron-hole run produced these candidates: a
        good pair is not the one with the smallest electron error, it is the
        one that describes both carriers AND agrees with itself on the
        geometry.
        """
        if mode == SORT_RRMSE and paired:
            return (lambda s: s.get('pair_score', s['RRMSE']), False)
        return {
            SORT_RRMSE_GAPS: (lambda s: s.get('RRMSE_dE', s['RRMSE']), False),
            SORT_SIZE_ASC: (self.confinement_size, False),
            SORT_SIZE_DESC: (self.confinement_size, True),
            SORT_ANISOTROPY: (self.anisotropy, False),
            SORT_GROUND: (self.ground_state, False),
        }.get(mode, (lambda s: s['RRMSE'], False))

    def sort_solutions(self, solutions: List[dict], mode: str,
                       paired: bool = False) -> List[dict]:
        """The candidates, reordered. Ties fall back to the error — two
        geometries of the same size still order by which describes the
        energies better."""
        key, reverse = self.sort_key(mode, paired)
        return sorted(solutions, key=lambda s: (key(s), s['RRMSE']),
                      reverse=reverse)
