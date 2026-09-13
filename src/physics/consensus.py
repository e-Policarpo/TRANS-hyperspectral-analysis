"""
Consensus across a line of spectra: which wells does the whole line agree on?

The Confinement Designer answers one question per spectrum — "which geometry
reproduces this ladder of levels?" — and answers it up to ``maxsol`` times,
because a ladder is usually explained by more than one geometry. Over a line
of spectra that leaves a table of several hundred candidates, and the
question a reader actually has is a different one: **how many distinct wells
does this line contain, and which spectra sit on each?**

The old answer gap-clustered every candidate of every spectrum in one flat
single-linkage pass over ``size_nm``. Three things are wrong with that, and
this module exists because of them.

**One: it conflates two questions.** The six candidates of one spectrum are
competing explanations of the *same* measurement — at most one of them is
true. Two candidates from two spectra are different measurements that may or
may not be looking at the same object. Pooling them in one pass lets a
single spectrum that happened to emit six candidates outvote five spectra
that each emitted one. Here a spectrum is the voting unit: its admissible
set carries a total weight of exactly 1, however large that set is.

**Two: it clusters in the wrong coordinate.** For the 0D disc/lens model
(``dims = R, L_z``) matched on ``delta_e``, the fitted offset cancels out of
every level *difference*, and with it L_z drops out of the data — the level
spacings fix the in-plane scale A/R², i.e. R, and say nothing about the
vertical confinement. L_z comes back from the optimiser as whatever the
bounds and the seed left it at. A geometric mean of R and L_z is therefore
half signal and half noise, and grouping in it smears real structure in R.
Grouping happens in R. The caller injects ``coord_fn`` and there is no
default, because silently picking the wrong coordinate is exactly the bug
this module was written to remove. (A/R² would do just as well — it is
mass-list invariant and an affine function of log R — but the report converts
the coordinate back to nanometres with ``exp``, so **``coord_fn`` must return
the natural log of a length in nm**.)

**Three: single linkage chains.** The R–L_z degeneracy is a continuous
valley, and gap clustering walks down it: every neighbouring pair is within
tolerance, so two genuinely different wells with a few intermediate
candidates between them fuse into one group. A weighted density with a
minimum-support rule cannot chain — an intermediate candidate has to raise an
actual peak, backed by a minimum number of *spectra*, to become a mode.

And a note on ranking: ``find_solutions`` seeds ``differential_evolution``
from an unseeded RNG, so "candidate 1" is not the same geometry from one run
to the next. Nothing in here privileges the best candidate. The unit is the
admissible set — every candidate whose error sits inside the tie band of that
spectrum's best.

Pure numpy and pure python: no Qt, no backend, no I/O. Everything is
injected or passed in, so the whole of it is testable in milliseconds.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

#: Column names as the Designer Candidates table writes them. They are
#: arguments everywhere below, not constants baked into the logic, so a
#: caller with a differently named table can still use the module.
ERROR_KEY = 'rrmse_de_pct'
SPECTRUM_KEY = 'spectrum_index'
CANDIDATE_KEY = 'candidate'
N_LEVELS_KEY = 'n_levels'
SKIPPED_KEY = 'levels_skipped'
QN_MIN_KEY = 'qn_min'
QN_MAX_KEY = 'qn_max'

#: The tie band of :func:`src.physics.line_scan.pick_best`, kept the same on
#: purpose: "within optimiser noise of the best" must mean one thing in this
#: app, not one thing per tool.
DELTA_ABS = 0.05
DELTA_REL = 0.1

#: A mode backed by fewer than one spectrum in five is one spectrum's quirk,
#: not a well the line shares. Floored at a single spectrum so a three-point
#: line is not left with nothing.
MIN_SUPPORT_FRAC = 0.2

#: Smallest kernel width, in log-coordinate units: 0.02 is 2% in R, an order
#: below anything the designer resolves. It only ever matters when the values
#: are so tightly packed that the adaptive rule would return ~0 and every
#: value would become its own mode.
MIN_BANDWIDTH = 0.02
#: And the other end: a kernel wider than this (a factor of ~1.3 in R) stops
#: being a density estimate and becomes a single smear.
MAX_BANDWIDTH = 0.25

#: Share of a mode's weight a minority assignment must carry before the mode
#: is split in two. See :func:`split_modes_by_identity`.
IDENTITY_SPLIT_FRAC = 0.25


# ── coordinates ───────────────────────────────────────────────────────────

def log_first_dim(row: dict, key: str = 'd1_nm') -> float:
    """log of the first dimension — R for the disc and the lens.

    The correct choice whenever one dimension is determined by the data and
    the others are not, which for ``ndim='0D'`` with ``match='delta_e'`` is
    the normal case: the level differences fix the in-plane scale and leave
    L_z free.
    """
    return _safe_log(row.get(key))


def log_size_nm(row: dict, key: str = 'size_nm') -> float:
    """log of the geometric-mean size — the fallback, not the default.

    For a model where no single dimension is privileged (a cube, a sphere,
    anything matched on absolute energies where the offset does not cancel)
    there is nothing better to group in. Where a dimension *is* privileged
    this coordinate mixes a measured number with an unmeasured one; use
    :func:`log_first_dim` instead.
    """
    return _safe_log(row.get(key))


#: Coordinates by name, so a tool can carry the choice as a string in its
#: parameters without importing the functions.
COORDS: Dict[str, Callable[[dict], float]] = {
    'log_r': log_first_dim,
    'log_first_dim': log_first_dim,
    'log_size': log_size_nm,
    'log_size_nm': log_size_nm,
}


def coord_function(coord_fn: Union[str, Callable[[dict], float]]) -> Callable[[dict], float]:
    """Resolve a coordinate given as a name or a callable. No default.

    Raises rather than guessing: the coordinate is a physics decision about
    which dimension the data determined, and this module has no way to know
    which model produced the table.
    """
    if callable(coord_fn):
        return coord_fn
    if isinstance(coord_fn, str) and coord_fn in COORDS:
        return COORDS[coord_fn]
    raise ValueError(
        f"unknown coordinate {coord_fn!r}: pass a callable, or one of "
        f"{sorted(set(COORDS))}. There is no default — for the disc/lens "
        f"matched on level differences the answer is 'log_r'.")


def _safe_log(value) -> float:
    """log of a positive number, NaN for anything else — never an exception."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float('nan')
    if not np.isfinite(v) or v <= 0.0:
        return float('nan')
    return float(math.log(v))


def _finite(value, default: float = float('nan')) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


# ── the admissible set ────────────────────────────────────────────────────

@dataclass
class AdmissibleSet:
    """One spectrum's candidates, and which of them are in the running.

    ``row_indices`` are every usable candidate of the spectrum (finite error,
    finite coordinate); ``admissible`` the subset inside the band. Both index
    into the ``rows`` sequence that was passed in, so a caller can write the
    result straight back onto its table.
    """
    spectrum_index: int
    row_indices: List[int] = field(default_factory=list)
    admissible: List[int] = field(default_factory=list)
    e_min: float = float('nan')
    band: float = float('nan')

    @property
    def n_candidates(self) -> int:
        return len(self.row_indices)

    @property
    def n_admissible(self) -> int:
        return len(self.admissible)


def admissible_sets(rows: Sequence[dict],
                    delta_abs: float = DELTA_ABS,
                    delta_rel: float = DELTA_REL,
                    error_key: str = ERROR_KEY,
                    spectrum_key: str = SPECTRUM_KEY,
                    coord_fn: Optional[Callable[[dict], float]] = None,
                    ) -> List[AdmissibleSet]:
    """Per spectrum: the candidates that are not distinguishable from the best.

    ``band = e_min + max(delta_abs, delta_rel * e_min)``, the same tie band
    :func:`src.physics.line_scan.pick_best` uses — 0.05 percentage points or
    10% of the error, whichever is larger. Two candidates whose RRMSE differ
    in the third decimal differ by optimiser noise, and treating that as a
    ranking is how the map ends up alternating between L, 2L and 3L.

    Rows the search could not use are dropped, not scored: a placeholder row
    (``candidate < 0``, written so the table says which positions found
    nothing) and any row whose error or coordinate is not finite. A spectrum
    left with no usable candidate gets no entry at all.

    Pass ``coord_fn`` to also require a usable coordinate — which is what
    :func:`consensus` does, since a candidate with no R cannot be grouped.
    """
    by_spectrum: Dict[int, List[int]] = {}
    order: List[int] = []
    for i, row in enumerate(rows):
        if int(_finite(row.get(CANDIDATE_KEY, 0), 0)) < 0:
            continue
        if not np.isfinite(_finite(row.get(error_key))):
            continue
        if coord_fn is not None and not np.isfinite(coord_fn(row)):
            continue
        try:
            si = int(row[spectrum_key])
        except (KeyError, TypeError, ValueError):
            continue
        if si not in by_spectrum:
            by_spectrum[si] = []
            order.append(si)
        by_spectrum[si].append(i)

    sets: List[AdmissibleSet] = []
    for si in sorted(order):
        indices = by_spectrum[si]
        errors = np.array([_finite(rows[i].get(error_key)) for i in indices], float)
        e_min = float(errors.min())
        band = e_min + max(float(delta_abs), float(delta_rel) * abs(e_min))
        admissible = [i for i, e in zip(indices, errors) if e <= band]
        sets.append(AdmissibleSet(spectrum_index=si, row_indices=list(indices),
                                  admissible=admissible, e_min=e_min, band=band))
    return sets


# ── weights ───────────────────────────────────────────────────────────────

def candidate_weight(row: dict,
                     n_levels_key: str = N_LEVELS_KEY,
                     skipped_key: str = SKIPPED_KEY,
                     skip_penalty: float = 1.0) -> float:
    """How much a candidate's opinion is worth, before normalisation.

    Two things make a candidate's geometry trustworthy. The first is how many
    levels it had to reproduce: a well fitted to five peaks is constrained,
    the same well fitted to two is barely more than an interpolation. The
    second is whether it had to claim unobserved states to do it —
    ``levels_skipped`` counts the rungs the assignment says exist between the
    lowest and the highest matched level but which no peak was found for.
    Every skipped rung is a free parameter in disguise.

    So ``weight = n_levels / (1 + skip_penalty * levels_skipped)``: monotone
    in the evidence, damped by the excuses. The absolute scale never matters
    — weights are normalised to 1 per spectrum before anything is done with
    them — only the ratio within a spectrum's admissible set does.
    """
    n_levels = _finite(row.get(n_levels_key), 0.0)
    if not np.isfinite(n_levels) or n_levels <= 0:
        n_levels = 1.0
    skipped = _finite(row.get(skipped_key), 0.0)
    if not np.isfinite(skipped) or skipped < 0:
        skipped = 0.0
    return float(n_levels) / (1.0 + max(0.0, float(skip_penalty)) * float(skipped))


def normalised_weights(rows: Sequence[dict], sets: Sequence[AdmissibleSet],
                       **weight_kwargs) -> Dict[int, float]:
    """Row index → weight, normalised so each spectrum totals exactly 1.

    This is the rule that keeps a degenerate spectrum from shouting. A
    spectrum whose search returned six admissible geometries is *less*
    informative than one that returned a single one, not six times more; it
    still gets one vote, spread over its six candidates in proportion to
    their quality.
    """
    out: Dict[int, float] = {}
    for s in sets:
        raw = np.array([candidate_weight(rows[i], **weight_kwargs) for i in s.admissible], float)
        raw = np.where(np.isfinite(raw) & (raw > 0), raw, 0.0)
        total = float(raw.sum())
        if total <= 0:
            # Every weight degenerate: fall back to one vote split evenly,
            # which is still a vote of exactly 1.
            raw = np.ones(len(s.admissible), float)
            total = float(raw.sum()) or 1.0
        for i, w in zip(s.admissible, raw / total):
            out[i] = float(w)
    return out


# ── density and modes ─────────────────────────────────────────────────────

def default_bandwidth(values: np.ndarray, weights: Optional[np.ndarray] = None,
                      floor: float = MIN_BANDWIDTH,
                      ceiling: float = MAX_BANDWIDTH) -> float:
    """Silverman's rule on the effective sample size, clipped.

    Hardcoding a kernel width would make the answer depend on how spread the
    particular line happens to be, which is the thing being measured. The
    width instead follows the data — ``0.9 * min(sd, IQR/1.34) * n^(-1/5)``
    on the log coordinate, with ``n`` the Kish effective size of the weights,
    since a hundred candidates carrying one spectrum's vote are not a hundred
    independent samples.

    The clip is there for the two degenerate ends: identical values would
    give zero width and every point its own mode, and values spread over a
    decade would give a width that smears the whole line into one blob.
    """
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float(floor)
    if weights is None:
        w = np.ones(v.size, float)
    else:
        w = np.asarray(weights, float)[np.isfinite(np.asarray(values, float))]
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
        if w.sum() <= 0:
            w = np.ones(v.size, float)
    n_eff = float(w.sum() ** 2 / np.sum(w ** 2)) if np.sum(w ** 2) > 0 else float(v.size)
    n_eff = max(1.0, n_eff)
    mean = float(np.average(v, weights=w))
    sd = float(math.sqrt(max(0.0, np.average((v - mean) ** 2, weights=w))))
    q1, q3 = np.percentile(v, [25, 75])
    iqr = float(q3 - q1)
    scale = min(x for x in (sd, iqr / 1.34) if x > 0) if (sd > 0 or iqr > 0) else 0.0
    h = 0.9 * scale * n_eff ** (-0.2)
    return float(min(max(h, floor), ceiling))


def weighted_density(values: np.ndarray, weights: np.ndarray,
                     bandwidth: float, grid: np.ndarray) -> np.ndarray:
    """Gaussian KDE evaluated on ``grid``. Normalised to unit total weight."""
    v = np.asarray(values, float).reshape(-1, 1)
    w = np.asarray(weights, float).reshape(-1, 1)
    total = float(w.sum()) or 1.0
    z = (np.asarray(grid, float).reshape(1, -1) - v) / float(bandwidth)
    return (w * np.exp(-0.5 * z * z)).sum(axis=0) / (total * bandwidth * math.sqrt(2 * math.pi))


def _local_maxima(density: np.ndarray, grid: np.ndarray) -> List[float]:
    """Interior local maxima, refined by a parabola through the three points.

    The ``>=`` on the right of the comparison takes the left edge of a flat
    top once rather than every point of it.
    """
    peaks: List[float] = []
    d = np.asarray(density, float)
    for i in range(1, d.size - 1):
        if d[i] > d[i - 1] and d[i] >= d[i + 1]:
            denom = d[i - 1] - 2 * d[i] + d[i + 1]
            shift = 0.5 * (d[i - 1] - d[i + 1]) / denom if denom != 0 else 0.0
            shift = float(np.clip(shift, -1.0, 1.0))
            peaks.append(float(grid[i] + shift * (grid[1] - grid[0])))
    return peaks


def _assign_nearest(values: np.ndarray, mode_values: Sequence[float],
                    signatures: Optional[Sequence] = None,
                    mode_signatures: Optional[Sequence] = None) -> np.ndarray:
    """Index of the mode each value belongs to.

    Nearest in the coordinate, with one exception that implements the
    assignment-identity rule: when a candidate's quantum-number signature
    matches some mode's, it is only allowed to choose among those. A
    candidate assigned n = 2,3,4 does not get absorbed into an n = 1,2,3 mode
    just because the two radii are close — they are different hypotheses that
    happen to land near each other.
    """
    m = np.asarray(mode_values, float)
    if m.size == 0:
        return np.full(len(values), -1, int)
    out = np.empty(len(values), int)
    for k, v in enumerate(np.asarray(values, float)):
        allowed = None
        if signatures is not None and mode_signatures is not None:
            allowed = [j for j, ms in enumerate(mode_signatures) if ms == signatures[k]]
        if allowed:
            out[k] = allowed[int(np.argmin(np.abs(m[allowed] - v)))]
        else:
            out[k] = int(np.argmin(np.abs(m - v)))
    return out


def _mode_records(values: np.ndarray, weights: np.ndarray,
                  spectrum_ids: np.ndarray, assignment: np.ndarray,
                  mode_values: Sequence[float],
                  mode_signatures: Optional[Sequence],
                  n_spectra: int) -> List[dict]:
    """Turn an assignment into mode dicts, ordered by coordinate."""
    records = []
    for j, mv in enumerate(mode_values):
        members = np.flatnonzero(assignment == j)
        supporters = set(int(s) for s in spectrum_ids[members])
        records.append({
            'value': float(mv),
            'value_nm': float(math.exp(mv)),
            'weight': float(weights[members].sum()) if members.size else 0.0,
            'members': [int(x) for x in members],
            'support_spectra': len(supporters),
            'support_frac': (len(supporters) / n_spectra) if n_spectra else 0.0,
            'signature': None if mode_signatures is None else mode_signatures[j],
        })
    records.sort(key=lambda r: r['value'])
    for j, r in enumerate(records):
        r['index'] = j
    return records


def find_modes(values, weights=None, bandwidth: Optional[float] = None,
               min_support_frac: float = MIN_SUPPORT_FRAC,
               spectrum_ids=None, min_support_spectra: Optional[int] = None,
               grid_size: int = 512) -> List[dict]:
    """Modes of the weighted density on the log coordinate, with a support floor.

    The replacement for gap clustering. The candidates are smoothed into a
    weighted density, the local maxima are the modes, and each value belongs
    to the nearest one — a partition that cannot chain, because a group only
    exists where the density actually turns over.

    On top of that sits the rule that does most of the work: **a mode must be
    backed by at least ``min_support_frac`` of the spectra**, counted as
    distinct spectra and not as candidates. One spectrum emitting six
    variations on 4.7 nm raises a perfectly good peak in the density and
    means nothing; four spectra out of twelve agreeing on 4.7 nm is a well.
    Modes below the floor are dropped weakest-first and their members fall to
    the nearest survivor, which is re-checked, until what is left all passes.

    ``values`` are already in the log coordinate; ``spectrum_ids`` says which
    spectrum each came from. Without ``spectrum_ids`` every value counts as
    its own spectrum, which makes the support rule a plain weight rule —
    useful for a null draw of one candidate per spectrum, wrong for a full
    admissible table.
    """
    v = np.asarray(values, float)
    if v.size == 0:
        return []
    w = np.ones(v.size, float) if weights is None else np.asarray(weights, float)
    ids = np.arange(v.size) if spectrum_ids is None else np.asarray(spectrum_ids)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w, ids = v[ok], w[ok], ids[ok]
    if v.size == 0:
        return []

    n_spectra = len(set(int(s) for s in ids))
    h = float(bandwidth) if bandwidth else default_bandwidth(v, w)
    if not np.isfinite(h) or h <= 0:
        h = MIN_BANDWIDTH

    span = float(v.max() - v.min())
    grid = np.linspace(v.min() - 3 * h, v.max() + 3 * h,
                       max(64, int(grid_size)))
    density = weighted_density(v, w, h, grid)
    mode_values = _local_maxima(density, grid)
    if not mode_values:
        # A single point, or a density so flat no interior maximum exists:
        # the weighted mean is the only honest answer.
        mode_values = [float(np.average(v, weights=w))]
    logger.debug("find_modes: %d value(s), %d spectra, h=%.4f, span=%.4f -> "
                 "%d raw mode(s)", v.size, n_spectra, h, span, len(mode_values))

    if min_support_spectra is None:
        threshold = max(1, int(math.ceil(float(min_support_frac) * n_spectra)))
    else:
        threshold = max(1, int(min_support_spectra))

    while True:
        assignment = _assign_nearest(v, mode_values)
        records = _mode_records(v, w, ids, assignment, mode_values, None, n_spectra)
        weak = [r for r in records if r['support_spectra'] < threshold]
        if not weak or len(records) <= 1:
            return records
        drop = min(weak, key=lambda r: (r['support_spectra'], r['weight']))
        logger.debug("find_modes: dropping mode at %.3f nm — %d spectrum(a), "
                     "below the floor of %d", drop['value_nm'],
                     drop['support_spectra'], threshold)
        mode_values = [r['value'] for r in records if r is not drop]


# ── assignment identity ───────────────────────────────────────────────────

def identity_signature(row: dict, qn_min_key: str = QN_MIN_KEY,
                       skipped_key: str = SKIPPED_KEY) -> Tuple:
    """What makes two candidates the *same* hypothesis, beyond a similar R.

    Two candidates can agree on the radius to three decimals and still be
    saying different things: one reads the peaks as n = 1,2,3, the other as
    n = 2,3,4 with the ground state below the measured window, and a third
    reads them as n = 1,3,4 with a level missing. Those are different
    physical claims about the same spectrum and must not be averaged into one
    "consensus well".

    **The rule chosen here: the signature is (qn_min, levels_skipped), and a
    mode is split when a minority signature carries a real share of it** —
    see :func:`split_modes_by_identity`. Splitting after clustering rather
    than stratifying before it is deliberate: stratifying first would mean a
    spectrum with four peaks and one with five could never land on the same
    well, since their ladders necessarily end at different rungs.

    Which is also why ``qn_max`` is *not* in the signature by default: it
    tracks how many peaks the spectrum had, not how the ladder was read. It
    is reported per mode as a range (``qn_min``/``qn_max``) so a reader can
    see the spread, and a caller who wants it as identity can pass its own
    key list.
    """
    qn_min = _finite(row.get(qn_min_key))
    skipped = _finite(row.get(skipped_key))
    return (None if not np.isfinite(qn_min) else int(qn_min),
            None if not np.isfinite(skipped) else int(skipped))


def split_modes_by_identity(modes: List[dict], values: np.ndarray,
                            weights: np.ndarray, signatures: Sequence,
                            spectrum_ids: np.ndarray, n_spectra: int,
                            identity_split_frac: float = IDENTITY_SPLIT_FRAC,
                            ) -> List[dict]:
    """Split a mode whose members materially disagree on the assignment.

    Within a mode the weight is tallied per signature. Any signature holding
    at least ``identity_split_frac`` of the mode becomes a mode of its own,
    placed at the weighted mean of its own members; if only one signature
    clears the bar the mode is left alone and simply carries that signature.
    Candidates whose signature cleared no bar are not discarded — they are
    re-assigned to the nearest surviving mode, which is where they would have
    gone anyway.

    The fraction, rather than "any disagreement splits", is the compromise
    that keeps one stray misassignment from fragmenting a good mode while
    still separating two hypotheses that both have real backing.
    """
    if not modes:
        return modes
    out_values: List[float] = []
    out_signatures: List = []
    for m in modes:
        members = m['members']
        if not members:
            continue
        per_sig: Dict = {}
        for k in members:
            per_sig.setdefault(signatures[k], []).append(k)
        total = float(sum(weights[k] for k in members)) or 1.0
        strong = [(sig, ks) for sig, ks in per_sig.items()
                  if float(sum(weights[k] for k in ks)) / total >= identity_split_frac]
        if len(strong) <= 1:
            dominant = max(per_sig.items(), key=lambda kv: sum(weights[k] for k in kv[1]))[0]
            out_values.append(m['value'])
            out_signatures.append(dominant)
            continue
        logger.debug("splitting the mode at %.3f nm into %d assignment(s): %s",
                     m['value_nm'], len(strong), [s for s, _ in strong])
        for sig, ks in strong:
            ws = np.array([weights[k] for k in ks], float)
            vs = np.array([values[k] for k in ks], float)
            out_values.append(float(np.average(vs, weights=ws)) if ws.sum() > 0 else float(vs.mean()))
            out_signatures.append(sig)

    order = np.argsort(np.asarray(out_values, float))
    out_values = [out_values[i] for i in order]
    out_signatures = [out_signatures[i] for i in order]
    assignment = _assign_nearest(values, out_values, signatures, out_signatures)
    return _mode_records(values, weights, spectrum_ids, assignment,
                         out_values, out_signatures, n_spectra)


def _prune_support(modes: List[dict], values: np.ndarray, weights: np.ndarray,
                   signatures: Optional[Sequence], spectrum_ids: np.ndarray,
                   n_spectra: int, threshold: int) -> List[dict]:
    """Re-apply the minimum-support rule after the modes have been rewritten."""
    while modes and len(modes) > 1:
        weak = [r for r in modes if r['support_spectra'] < threshold]
        if not weak:
            break
        drop = min(weak, key=lambda r: (r['support_spectra'], r['weight']))
        keep = [r for r in modes if r is not drop]
        mode_values = [r['value'] for r in keep]
        mode_signatures = None if signatures is None else [r['signature'] for r in keep]
        assignment = _assign_nearest(values, mode_values, signatures, mode_signatures)
        modes = _mode_records(values, weights, spectrum_ids, assignment,
                              mode_values, mode_signatures, n_spectra)
    return modes


# ── soft assignment ───────────────────────────────────────────────────────

@dataclass
class Assignment:
    """Who belongs where. ``membership`` is (n_spectra, n_modes), rows sum to 1."""
    spectrum_ids: List[int]
    membership: np.ndarray
    nearest: np.ndarray


def soft_assign(values, weights, spectrum_ids, mode_values,
                signatures: Optional[Sequence] = None,
                mode_signatures: Optional[Sequence] = None) -> Assignment:
    """Membership of each spectrum across the modes.

    Each admissible candidate goes to its nearest mode (subject to the
    identity rule) carrying its normalised weight, and a spectrum's
    membership in a mode is the total weight it sent there. Because the
    weights of a spectrum sum to 1, the memberships do too — they read as
    probabilities without pretending to be one.

    **A spectrum whose admissible set straddles two modes must say so.** It
    is the honest description of a spectrum the data cannot place: 0.5/0.5,
    not a coin flip recorded as a fact. Forcing it onto one mode is how a
    line scan ends up with a hard boundary that moves every time the search
    is re-run.
    """
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    ids = np.asarray(spectrum_ids)
    order = sorted(set(int(s) for s in ids))
    lookup = {s: k for k, s in enumerate(order)}
    n_modes = len(mode_values)
    membership = np.zeros((len(order), n_modes), float)
    nearest = _assign_nearest(v, mode_values, signatures, mode_signatures)
    for k in range(v.size):
        j = int(nearest[k])
        if j >= 0:
            membership[lookup[int(ids[k])], j] += float(w[k])
    totals = membership.sum(axis=1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        membership = np.where(totals > 0, membership / np.where(totals > 0, totals, 1.0), 0.0)
    return Assignment(spectrum_ids=order, membership=membership, nearest=nearest)


def _entropy(p: np.ndarray) -> float:
    """Shannon entropy in nats. 0 when a spectrum sits on one mode; ln(K)
    when it is spread evenly over K of them."""
    q = np.asarray(p, float)
    q = q[q > 0]
    if q.size == 0:
        return 0.0
    h = float(-(q * np.log(q)).sum())
    return h if h > 0.0 else 0.0


# ── the consensus ─────────────────────────────────────────────────────────

@dataclass
class ConsensusResult:
    """Everything the three tables need, and the knobs that produced them."""
    modes: List[dict]
    per_spectrum: List[dict]
    per_candidate: List[dict]
    meta: dict

    def to_dict(self) -> dict:
        return {'modes': self.modes, 'per_spectrum': self.per_spectrum,
                'per_candidate': self.per_candidate, 'meta': self.meta}


def consensus(rows: Sequence[dict],
              coord_fn: Union[str, Callable[[dict], float]],
              delta_abs: float = DELTA_ABS,
              delta_rel: float = DELTA_REL,
              bandwidth: Optional[float] = None,
              min_support_frac: float = MIN_SUPPORT_FRAC,
              min_support_spectra: Optional[int] = None,
              identity: bool = True,
              identity_split_frac: float = IDENTITY_SPLIT_FRAC,
              identity_fn: Optional[Callable[[dict], Tuple]] = None,
              error_key: str = ERROR_KEY,
              spectrum_key: str = SPECTRUM_KEY,
              second_dim_key: str = 'd2_nm',
              skip_penalty: float = 1.0,
              grid_size: int = 512) -> ConsensusResult:
    """How many wells does this line contain, and which spectra sit on each?

    The whole pipeline: admissible sets per spectrum, one vote per spectrum
    spread over its set, a weighted density in the injected coordinate, modes
    with a minimum-support floor, a split where the quantum-number
    assignments disagree, and a soft membership that lets an undecidable
    spectrum stay undecided.

    The three tables it returns answer three different questions — "what
    wells are there" (``modes``), "where is this spectrum" (``per_spectrum``),
    "why did this candidate land there" (``per_candidate``) — and they are
    deliberately separate, because the flat table that tried to answer all
    three at once is what this replaces.

    ``support_frac`` may sum to more than 1 over the modes. That is not a
    bookkeeping error: membership is soft, and a spectrum that straddles two
    wells supports both.

    Every length reported in nm comes back through ``exp`` of the coordinate,
    so ``coord_fn`` must return the log of a length in nm. The columns are
    named ``R_*`` because R is the coordinate this was written for; with the
    ``log_size`` fallback they hold the geometric-mean size instead.
    """
    coord = coord_function(coord_fn)
    identity_of = identity_fn or identity_signature

    sets = admissible_sets(rows, delta_abs=delta_abs, delta_rel=delta_rel,
                           error_key=error_key, spectrum_key=spectrum_key,
                           coord_fn=coord)
    n_spectra = len(sets)

    row_index: List[int] = []
    values: List[float] = []
    weights_list: List[float] = []
    ids: List[int] = []
    signatures: List[Tuple] = []
    weight_map = normalised_weights(rows, sets, n_levels_key=N_LEVELS_KEY,
                                    skipped_key=SKIPPED_KEY,
                                    skip_penalty=skip_penalty)
    band_of: Dict[int, float] = {}
    for s in sets:
        for i in s.admissible:
            band_of[i] = s.band
            row_index.append(i)
            values.append(coord(rows[i]))
            weights_list.append(weight_map.get(i, 0.0))
            ids.append(s.spectrum_index)
            signatures.append(identity_of(rows[i]))

    v = np.asarray(values, float)
    w = np.asarray(weights_list, float)
    id_arr = np.asarray(ids, int)

    meta = {
        'n_spectra': n_spectra,
        'n_rows': len(rows),
        'n_admissible': int(v.size),
        'delta_abs': float(delta_abs),
        'delta_rel': float(delta_rel),
        'min_support_frac': float(min_support_frac),
        'identity': bool(identity),
        'identity_split_frac': float(identity_split_frac),
        'coord': getattr(coord, '__name__', str(coord_fn)),
        'bandwidth': float('nan'),
        'n_modes': 0,
        'spread': float('nan'),
        'spread_pct': float('nan'),
    }
    if v.size == 0:
        logger.info("consensus: nothing to group — no usable candidate in %d row(s)",
                    len(rows))
        return ConsensusResult([], [], [], meta)

    h = float(bandwidth) if bandwidth else default_bandwidth(v, w)
    meta['bandwidth'] = h
    modes = find_modes(v, w, bandwidth=h, min_support_frac=min_support_frac,
                       spectrum_ids=id_arr, min_support_spectra=min_support_spectra,
                       grid_size=grid_size)
    if min_support_spectra is None:
        threshold = max(1, int(math.ceil(float(min_support_frac) * n_spectra)))
    else:
        threshold = max(1, int(min_support_spectra))
    mode_signatures: Optional[List] = None
    if identity and modes:
        modes = split_modes_by_identity(modes, v, w, signatures, id_arr, n_spectra,
                                        identity_split_frac=identity_split_frac)
        modes = _prune_support(modes, v, w, signatures, id_arr,
                               n_spectra, threshold)
        mode_signatures = [m['signature'] for m in modes]

    mode_values = [m['value'] for m in modes]
    assignment = soft_assign(v, w, id_arr, mode_values,
                             signatures if mode_signatures is not None else None,
                             mode_signatures)
    nearest = assignment.nearest
    meta['n_modes'] = len(modes)
    meta['spread'] = _spread(v, id_arr, mode_values)
    meta['spread_pct'] = float((math.exp(meta['spread']) - 1.0) * 100.0) \
        if np.isfinite(meta['spread']) else float('nan')

    # ── the mode table ───────────────────────────────────────────────────
    membership = assignment.membership
    spectrum_pos = {s: k for k, s in enumerate(assignment.spectrum_ids)}
    mode_rows: List[dict] = []
    for j, m in enumerate(modes):
        members = [k for k in range(v.size) if nearest[k] == j]
        r_values = np.array([math.exp(v[k]) for k in members], float)
        lz = np.array([_finite(rows[row_index[k]].get(second_dim_key)) for k in members], float)
        lz = lz[np.isfinite(lz)]
        errs = np.array([_finite(rows[row_index[k]].get(error_key)) for k in members], float)
        wts = np.array([w[k] for k in members], float)
        qn_lo = [_finite(rows[row_index[k]].get(QN_MIN_KEY)) for k in members]
        qn_hi = [_finite(rows[row_index[k]].get(QN_MAX_KEY)) for k in members]
        skipped = np.array([_finite(rows[row_index[k]].get(SKIPPED_KEY)) for k in members], float)
        col = membership[:, j] if membership.size else np.zeros(0)
        support = int((col > 1e-12).sum())
        mode_rows.append({
            'mode': j,
            'R_nm': float(math.exp(m['value'])),
            'R_lo_nm': float(r_values.min()) if r_values.size else float('nan'),
            'R_hi_nm': float(r_values.max()) if r_values.size else float('nan'),
            # The vertical size is reported as a range, never as a value:
            # with the offset cancelled it is not determined by the data, and
            # a single number there would be the optimiser's seed dressed up
            # as a measurement.
            'Lz_lo_nm': float(lz.min()) if lz.size else float('nan'),
            'Lz_hi_nm': float(lz.max()) if lz.size else float('nan'),
            'support_spectra': support,
            'support_frac': float(support / n_spectra) if n_spectra else 0.0,
            'mean_rrmse_de_pct': float(np.average(errs, weights=wts))
                                 if errs.size and wts.sum() > 0 else float('nan'),
            'qn_min': float(np.nanmin(qn_lo)) if len(qn_lo) and np.any(np.isfinite(qn_lo)) else float('nan'),
            'qn_max': float(np.nanmax(qn_hi)) if len(qn_hi) and np.any(np.isfinite(qn_hi)) else float('nan'),
            'levels_skipped_mean': float(np.average(skipped[np.isfinite(skipped)],
                                                    weights=wts[np.isfinite(skipped)]))
                                    if np.any(np.isfinite(skipped)) and wts[np.isfinite(skipped)].sum() > 0
                                    else float('nan'),
            'n_candidates': len(members),
            'weight': float(wts.sum()),
            'signature': m.get('signature'),
        })

    # ── the spectrum table ───────────────────────────────────────────────
    per_spectrum: List[dict] = []
    for s in sets:
        k = spectrum_pos.get(s.spectrum_index)
        probs = membership[k] if k is not None and membership.size else np.zeros(len(modes))
        own = [i for i in s.admissible]
        r_own = np.array([math.exp(coord(rows[i])) for i in own], float)
        if probs.size and probs.sum() > 0:
            order = np.argsort(probs)[::-1]
            first = int(order[0])
            p1 = float(probs[first])
            second = int(order[1]) if probs.size > 1 and probs[order[1]] > 0 else -1
            p2 = float(probs[order[1]]) if second >= 0 else 0.0
            consensus_nm = mode_rows[first]['R_nm']
        else:
            first, p1, second, p2, consensus_nm = -1, 0.0, -1, 0.0, float('nan')
        per_spectrum.append({
            'spectrum_index': s.spectrum_index,
            'n_candidates': s.n_candidates,
            'n_admissible': s.n_admissible,
            'best_de_pct': float(s.e_min),
            'band_de_pct': float(s.band),
            'R_lo_nm': float(r_own.min()) if r_own.size else float('nan'),
            'R_hi_nm': float(r_own.max()) if r_own.size else float('nan'),
            'R_consensus_nm': consensus_nm,
            'mode': first,
            'mode_prob': p1,
            'mode_2nd': second,
            'mode_2nd_prob': p2,
            'mode_entropy': _entropy(probs),
        })

    # ── the candidate table ──────────────────────────────────────────────
    admissible_at = {i: k for k, i in enumerate(row_index)}
    per_candidate: List[dict] = []
    for s in sets:
        for i in s.row_indices:
            k = admissible_at.get(i)
            if k is None:
                per_candidate.append({
                    'row_index': i, 'admissible': False, 'band_de_pct': float(s.band),
                    'weight': 0.0, 'mode': -1, 'mode_R_nm': float('nan'),
                    'dist_nm': float('nan'),
                })
                continue
            j = int(nearest[k])
            mode_nm = mode_rows[j]['R_nm'] if 0 <= j < len(mode_rows) else float('nan')
            per_candidate.append({
                'row_index': i,
                'admissible': True,
                'band_de_pct': float(s.band),
                'weight': float(w[k]),
                'mode': j,
                'mode_R_nm': mode_nm,
                'dist_nm': float(abs(math.exp(v[k]) - mode_nm)) if np.isfinite(mode_nm) else float('nan'),
            })

    logger.info("consensus: %d spectra, %d admissible candidate(s), h=%.3f -> "
                "%d mode(s) at %s (spread %.2f%%)", n_spectra, int(v.size), h,
                len(mode_rows), ", ".join(f"{m['R_nm']:.2f} nm x{m['support_spectra']}"
                                          for m in mode_rows) or "none",
                meta['spread_pct'])
    return ConsensusResult(mode_rows, per_spectrum, per_candidate, meta)


def _spread(values: np.ndarray, spectrum_ids: np.ndarray,
            mode_values: Sequence[float]) -> float:
    """How far the line is from its own modes, in log units — one number.

    Per spectrum, the distance from its *closest* admissible candidate to the
    nearest mode; over the line, the RMS of those. Small when every spectrum
    has a candidate sitting on a shared well, large when the candidates are
    strewn between the modes.

    One value per spectrum, not one per candidate, and that is the whole
    point: it is the same shape of number as a null draw of one candidate per
    spectrum, so the two are comparable (:func:`null_contrast`). In log units
    it is a relative spread, so it also compares across lines of different
    size — ``exp(spread) - 1`` is roughly the fractional spread in R.
    """
    m = np.asarray(mode_values, float)
    v = np.asarray(values, float)
    if m.size == 0 or v.size == 0:
        return float('nan')
    ids = np.asarray(spectrum_ids)
    per_spectrum = []
    for s in sorted(set(int(x) for x in ids)):
        own = v[ids == s]
        if own.size == 0:
            continue
        per_spectrum.append(float(np.min(np.abs(own.reshape(-1, 1) - m.reshape(1, -1)))))
    if not per_spectrum:
        return float('nan')
    d = np.asarray(per_spectrum, float)
    return float(math.sqrt(float(np.mean(d * d))))


# ── is any of this better than chance? ────────────────────────────────────

def null_contrast(rows: Sequence[dict],
                  coord_fn: Union[str, Callable[[dict], float]],
                  n_draws: int = 200,
                  seed: Optional[int] = None,
                  rng: Optional[np.random.Generator] = None,
                  delta_abs: float = DELTA_ABS,
                  delta_rel: float = DELTA_REL,
                  bandwidth: Optional[float] = None,
                  min_support_frac: float = MIN_SUPPORT_FRAC,
                  error_key: str = ERROR_KEY,
                  spectrum_key: str = SPECTRUM_KEY,
                  result: Optional[ConsensusResult] = None,
                  **consensus_kwargs) -> dict:
    """Is the consensus tighter than picking one candidate per spectrum at random?

    The informativeness check. Modes will always come out of a density — the
    question is whether they mean anything. So: draw one admissible candidate
    per spectrum uniformly at random, run the same mode-finding on the draw,
    measure the spread, and repeat. That is the null of "the admissible sets
    contain no shared well", built out of the same numbers rather than out of
    an assumed distribution.

    If the line really does sit on a few wells, the true geometry appears in
    most spectra's sets and the weighted consensus concentrates on it, while
    a random draw scatters across the degenerate alternatives — the observed
    spread lands in the left tail. If it does not, the two look alike.

    **The null is over the choice of candidate inside each set, not over the
    spectra.** When every spectrum has a single admissible candidate there is
    nothing to choose, the draws reproduce the data exactly, and ``p_value``
    is 1 by construction. That is not "the consensus is wrong", it is "this
    test has nothing to say here" — the tightness then comes from the search,
    not from the grouping.

    One asymmetry to keep in mind when reading ``p_value``: the observed
    spread lets each spectrum contribute its candidate closest to a mode,
    which is the consensus's own answer, while a draw cannot choose. The
    comparison is therefore optimistic by a little, the more so the larger
    the admissible sets — so the distribution (``spreads``, and the
    percentiles beside it) is the deliverable and the p-value the shorthand,
    not the other way round.

    Randomness is explicit: pass ``rng`` or ``seed``. Nothing in here touches
    the global numpy state, so a reported p-value can be reproduced.
    """
    coord = coord_function(coord_fn)
    generator = rng if rng is not None else np.random.default_rng(seed)

    sets = admissible_sets(rows, delta_abs=delta_abs, delta_rel=delta_rel,
                           error_key=error_key, spectrum_key=spectrum_key,
                           coord_fn=coord)
    usable = [s for s in sets if s.admissible]
    if result is None:
        result = consensus(rows, coord, delta_abs=delta_abs, delta_rel=delta_rel,
                           bandwidth=bandwidth, min_support_frac=min_support_frac,
                           error_key=error_key, spectrum_key=spectrum_key,
                           **consensus_kwargs)
    observed = float(result.meta.get('spread', float('nan')))
    out = {
        'n_draws': int(n_draws),
        'n_spectra': len(usable),
        'observed_spread': observed,
        'observed_n_modes': int(result.meta.get('n_modes', 0)),
        'spreads': np.zeros(0),
        'n_modes': np.zeros(0, int),
        'spread_mean': float('nan'), 'spread_median': float('nan'),
        'spread_p05': float('nan'), 'spread_p95': float('nan'),
        'p_value': float('nan'), 'z': float('nan'),
        'tighter_than_chance': False,
        'mean_set_size': float(np.mean([s.n_admissible for s in usable])) if usable else float('nan'),
    }
    if not usable or n_draws <= 0:
        return out

    h = bandwidth if bandwidth else float(result.meta.get('bandwidth') or MIN_BANDWIDTH)
    spreads = np.full(int(n_draws), np.nan)
    counts = np.zeros(int(n_draws), int)
    ids = np.arange(len(usable))
    for draw in range(int(n_draws)):
        picked = [s.admissible[int(generator.integers(0, s.n_admissible))] for s in usable]
        vals = np.array([coord(rows[i]) for i in picked], float)
        wts = np.ones(vals.size, float)
        modes = find_modes(vals, wts, bandwidth=h, min_support_frac=min_support_frac,
                           spectrum_ids=ids)
        mode_values = [m['value'] for m in modes]
        spreads[draw] = _spread(vals, ids, mode_values)
        counts[draw] = len(mode_values)

    finite = spreads[np.isfinite(spreads)]
    out['spreads'] = spreads
    out['n_modes'] = counts
    if finite.size:
        out['spread_mean'] = float(finite.mean())
        out['spread_median'] = float(np.median(finite))
        out['spread_p05'] = float(np.percentile(finite, 5))
        out['spread_p95'] = float(np.percentile(finite, 95))
        if np.isfinite(observed):
            # +1 in both places: the observed value is itself one of the
            # possible draws, and a p-value of exactly 0 out of 200 draws
            # would claim more than 200 draws can support.
            out['p_value'] = float((np.sum(finite <= observed) + 1) / (finite.size + 1))
            sd = float(finite.std())
            out['z'] = float((observed - finite.mean()) / sd) if sd > 0 else float('nan')
            out['tighter_than_chance'] = bool(out['p_value'] <= 0.05)
    return out


# ── does the answer survive the tolerance? ────────────────────────────────

def delta_stability(rows: Sequence[dict],
                    coord_fn: Union[str, Callable[[dict], float]],
                    deltas: Sequence = ((0.025, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 0.4)),
                    n_draws: int = 0,
                    seed: Optional[int] = None,
                    rng: Optional[np.random.Generator] = None,
                    **consensus_kwargs) -> List[dict]:
    """Rerun the consensus across a range of admissible tolerances.

    The band is a judgement call — 0.05 pp and 10% are defensible, not
    derived — so the honest thing is to show what depends on it. A consensus
    that keeps the same number of modes at the same radii from a tight band
    to a loose one is a property of the data; one that gains a mode every
    time the band widens is a property of the band.

    Each entry of ``deltas`` is either a float (read as ``delta_abs``, with
    ``delta_rel`` left at whatever the caller passed) or a ``(delta_abs,
    delta_rel)`` pair, or a dict of either key. With ``n_draws > 0`` the null
    contrast is run at every tolerance too, which is slow and off by default.
    """
    generator = rng if rng is not None else np.random.default_rng(seed)
    base_abs = consensus_kwargs.pop('delta_abs', DELTA_ABS)
    base_rel = consensus_kwargs.pop('delta_rel', DELTA_REL)
    out: List[dict] = []
    for entry in deltas:
        if isinstance(entry, dict):
            d_abs = float(entry.get('delta_abs', base_abs))
            d_rel = float(entry.get('delta_rel', base_rel))
        elif isinstance(entry, (tuple, list)):
            d_abs = float(entry[0])
            d_rel = float(entry[1]) if len(entry) > 1 else base_rel
        else:
            d_abs, d_rel = float(entry), base_rel
        res = consensus(rows, coord_fn, delta_abs=d_abs, delta_rel=d_rel,
                        **consensus_kwargs)
        record = {
            'delta_abs': d_abs,
            'delta_rel': d_rel,
            'n_modes': int(res.meta['n_modes']),
            'spread': float(res.meta['spread']),
            'spread_pct': float(res.meta['spread_pct']),
            'modes_R_nm': [m['R_nm'] for m in res.modes],
            'support_frac': [m['support_frac'] for m in res.modes],
            'n_admissible': int(res.meta['n_admissible']),
            'mean_set_size': (float(res.meta['n_admissible'] / res.meta['n_spectra'])
                              if res.meta['n_spectra'] else float('nan')),
            'p_value': float('nan'),
            'null_median_spread': float('nan'),
        }
        if n_draws > 0:
            null = null_contrast(rows, coord_fn, n_draws=n_draws, rng=generator,
                                 delta_abs=d_abs, delta_rel=d_rel, result=res,
                                 **consensus_kwargs)
            record['p_value'] = float(null['p_value'])
            record['null_median_spread'] = float(null['spread_median'])
        out.append(record)
    return out
