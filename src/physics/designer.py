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

import logging
from typing import Callable, List, Optional, Sequence

import numpy as np
from scipy.constants import hbar, m_e, e
from scipy.optimize import minimize, differential_evolution

from src.physics.analytical import (box_energies_1d_eV, box_energies_2d_eV,
                                    box_energies_3d_eV, cylinder_energies,
                                    disk_energies)
from src.physics.pairing import confinement_size_nm
from src.physics.quantum_dot import dot_energies, hw_from_length
from src.physics.solution_spec import (
    COORDS_CARTESIAN, COORDS_CIRCULAR, COORDS_CYLINDRICAL, COORDS_DISC,
    COORDS_PARABOLIC, COORDS_SPHERICAL,
)

logger = logging.getLogger(__name__)


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

    def __init__(self, seed: Optional[int] = None):
        # Seedable so a test can pin the global optimisation; entropy-seeded
        # by default, exactly as the search has always run.
        self._rng = np.random.default_rng(seed)

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

    def bounds(self, p):
        """One ``(Lmin, Lmax)`` per free dimension, in the order they are read."""
        out = []
        f = p['fixed']
        ndim, coords, sym = p['ndim'], p['coords'], p.get('sym', '')
        Lmin, Lmax = p['Lmin'], p['Lmax']

        if ndim == "0D":
            for key in ("d1", "d2")[:len(DOT_ROWS[coords])]:
                if f[key] is None:
                    out.append((Lmin, Lmax))
        elif ndim == "1D":
            if f['d1'] is None:
                out.append((Lmin, Lmax))
        elif ndim == "2D":
            if coords == COORDS_CIRCULAR:
                if f['d1'] is None:
                    out.append((Lmin, Lmax))
            else:
                if f['d1'] is None:
                    out.append((Lmin, Lmax))
                if sym != SYM_SQUARE and f['d2'] is None:
                    out.append((Lmin, Lmax))
        else:
            if coords == COORDS_CYLINDRICAL:
                if f['d1'] is None:
                    out.append((Lmin, Lmax))
                if f['d2'] is None:
                    out.append((Lmin, Lmax))
            else:
                if f['d1'] is None:
                    out.append((Lmin, Lmax))
                if sym == SYM_TETRAGONAL:
                    if f['d3'] is None:
                        out.append((Lmin, Lmax))
                elif sym == SYM_ORTHORHOMBIC:
                    if f['d2'] is None:
                        out.append((Lmin, Lmax))
                    if f['d3'] is None:
                        out.append((Lmin, Lmax))
        return out

    # ─── matching and error ──────────────────────────────────────────────

    @staticmethod
    def find_matches(Ec, Et):
        """Pair each target with the computed level nearest it, relatively."""
        Ev = np.array([x[0] for x in Ec])
        matches = []
        for et in Et:
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

        if mode == MATCH_ABSOLUTE:
            matches = self.find_matches(Ec, Et)
            return matches, 0.0, self.abs_rrmse(matches, Et, priority)

        ratios = (mode == MATCH_RATIOS)
        best = None
        for j0 in range(len(Ec)):
            offset = Ec[j0][0] - Et[0]
            shifted = [(E - offset, qn) for E, qn in Ec if E - offset > 0]
            if len(shifted) < len(Et):
                continue
            matches = self.find_matches(shifted, Et)
            err = self.gap_rrmse(matches, Et, priority, ratios=ratios)
            if best is None or err < best[2]:
                best = (matches, offset, err)

        if best is None:            # nothing alignable: fall back to absolute
            matches = self.find_matches(Ec, Et)
            return matches, 0.0, self.abs_rrmse(matches, Et, priority)
        return best

    def objective(self, opt, p):
        """What the optimiser minimises: the error of one trial geometry."""
        dims = self.params_to_dims(opt, p)
        n = max(len(p['Et']) * 3, 20)
        Ec = self.compute_energies(dims, p['meff'], n, p)
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
        return {'dims': dims, 'RRMSE': rr, 'matches': matches, 'Ec': Ec,
                'meff': p['meff'], 'targets': list(p['Et']),
                'carrier': p.get('carrier', 'e'),
                'RRMSE_abs': self.abs_rrmse(matches, p['Et'], priority),
                'RRMSE_dE': self.gap_rrmse(matches, p['Et'], priority),
                'offset': offset, 'match': p.get('match', MATCH_ABSOLUTE),
                'ndim': p['ndim'], 'coords': p['coords'], 'sym': p.get('sym', '')}

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
        """
        base_err = float(sol.get('RRMSE', float('inf')))
        tol = max(0.05, 0.1 * abs(base_err))
        n = max(len(p['Et']) * 3, 20)
        meff = sol.get('meff', p['meff'])
        best = sol

        for k in range(2, max_factor + 1):
            scaled = tuple(d / k for d in sol['dims'])
            probe = {**sol, 'dims': scaled}
            if confinement_size_nm(probe, meff) < p['Lmin']:
                break                      # outside the requested search range
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
        return best

    @staticmethod
    def is_duplicate(s, sols, tol=0.1):
        """True when a candidate's dimensions already appear in ``sols``."""
        for ex in sols:
            if all(abs(a - b) < tol for a, b in zip(s['dims'], ex['dims'])):
                return True
        return False

    def find_solutions(self, p):
        """Candidates for one carrier at one effective mass, best error first.

        Two passes: an analytical estimate per target refined locally, then a
        global optimisation for what that misses. Anything above ``tol`` is
        discarded rather than reported as a poor fit.
        """
        bounds = self.bounds(p)
        nfree = len(bounds)
        sols = []

        if nfree == 0:
            sols.append(self.extract_solution([], p))
            return sols

        # Analytical estimates
        m = p['meff'] * m_e
        for Er in p['Et']:
            E_J = Er * e
            pf = hbar ** 2 * np.pi ** 2 / (2.0 * m)
            # A hard sphere's ground state is hbar^2*pi^2/(2 m R^2), the same
            # form as a 1D box — so 0D enters the estimate as 1.
            ndim_int = max(1, int(p['ndim'][0]))
            L_est = np.sqrt(ndim_int * pf / E_J) * 1e9
            if p['Lmin'] <= L_est <= p['Lmax']:
                try:
                    res = minimize(self.objective, [L_est] * nfree,
                                   args=(p,), method='L-BFGS-B', bounds=bounds)
                    if res.fun <= p['tol']:
                        s = self.extract_solution(res.x, p)
                        if not self.is_duplicate(s, sols):
                            sols.append(s)
                except Exception:
                    pass

        # Global optimisation
        for _ in range(p['maxsol'] * 2):
            if len(sols) >= p['maxsol']:
                break
            try:
                res = differential_evolution(
                    self.objective, bounds, args=(p,),
                    maxiter=200, tol=0.01, seed=int(self._rng.integers(10000)))
                if res.fun <= p['tol']:
                    s = self.extract_solution(res.x, p)
                    if not self.is_duplicate(s, sols):
                        sols.append(s)
            except Exception:
                pass

        sols.sort(key=lambda x: x['RRMSE'])
        return sols[:p['maxsol']]

    def search_carrier(self, p: dict, carrier: dict,
                       progress: Optional[Callable[[str], None]] = None) -> list:
        """Search one carrier's candidates, once per effective mass.

        Different masses are different searches — the same energy with a
        larger mass asks for a larger well — and each candidate comes out
        stamped with its own, so the final list can mix them without losing
        track of which mass produced which geometry.
        """
        found = []
        for meff in carrier['meffs']:
            pm = {**p, 'Et': carrier['Et'], 'meff': meff,
                  'carrier': carrier['carrier']}
            if progress is not None:
                progress(f"Searching {carrier['label']}s with m* = {meff:g}…")
            sols = self.find_solutions(pm)
            logger.info("search %s m*=%g: %d candidate(s)",
                        carrier['label'], meff, len(sols))
            found.extend(sols)

        # The same geometry AND the same mass is a duplicate; the same
        # geometry at different masses is not — they are distinct answers to
        # the same question.
        unique = []
        for sol in sorted(found, key=lambda x: x['RRMSE']):
            if not any(abs(sol['meff'] - ex['meff']) < 1e-9
                       and self.is_duplicate(sol, [ex]) for ex in unique):
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
