"""
Curves that distort an average.

Everything else in Filter Bad Data judges a spectrum on its own: is it
clipped, is it noise, does it have any structure. An outlier is different —
it can be a perfectly good measurement and still be wrong to average in,
because it does not belong to the same population as the rest. One curve
sitting two orders of magnitude above the others drags the mean up on its
own, and the average stops describing anything that was actually measured.

That question only has an answer for a **set of curves taken to be
repetitions of the same thing** — an overview dataset. Run it on a line scan,
where every position is supposed to differ, and it will dutifully report that
the ends of the line are outliers.

Three kinds are told apart, because the right response to each is different:

``offset``
    The curve is displaced across the *whole* sweep — every interval departs
    from the population. Usually a gain or a zero that was not the same for
    that acquisition. It is the one that wrecks an average.
``bandgap``
    The curve departs only over *part* of the sweep, typically where the band
    edge sits: a spot with a smaller gap has its edge rise earlier, pulling
    the average edge inward. This may be real physics, so it is reported
    separately and left switched off by default.
``saturation``
    The curve covers a much shorter bias range than the others, because the
    loader turned its railed samples into NaN. There is nothing to average
    over most of the sweep.

The measurement is the **area under the curve in each of a few bias
sub-intervals**, compared across curves with a median/MAD z-score. Area
rather than point-by-point difference because it is insensitive to noise and
to a small shift in where a peak sits; sub-intervals rather than one total
because *where* a curve departs is exactly what separates an offset from a
band-edge shift.

**A large number of outliers is not a set of outliers.** If a fifth of the
curves are "outlying", what has been found is the shape of a distribution,
not a handful of bad acquisitions. Each kind therefore carries a limit, and
exceeding it removes nothing at all rather than removing a third of the data
— see :func:`select_outliers`.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .positivity import positive_integral

logger = logging.getLogger(__name__)

# The kinds, in the order a report should list them.
OFFSET = 'offset'
BANDGAP = 'bandgap'
SATURATION = 'saturation'
KINDS = (OFFSET, BANDGAP, SATURATION)

DEFAULTS = {
    'n_intervals': 8,
    'z_threshold': 3.5,
    # Fraction of intervals that must depart before a curve counts as
    # displaced everywhere rather than somewhere.
    'offset_fraction': 0.75,
    # A band edge in the wrong place moves a *contiguous* stretch of the
    # sweep. One lone interval is what noise produces: with a MAD estimated
    # from a few dozen curves the tails are heavier than Gaussian, so single
    # departures turn up regularly and would flag good repetitions as
    # "bandgap" outliers. Measured on 40 clean populations of 20 curves:
    # 3.6% of curves flagged at a run of 1, 0.0% at a run of 2.
    'min_run': 2,
    # A curve covering less than this share of the median bias range has been
    # truncated, not merely measured over a slightly different window.
    'saturation_tolerance': 0.8,
}


def _longest_run(flags: np.ndarray) -> int:
    """Length of the longest contiguous stretch of True in ``flags``."""
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


@dataclass
class OutlierAnalysis:
    """What the population looks like, and which curves stand outside it."""

    columns: List[str]
    kind_of: Dict[str, str] = field(default_factory=dict)
    z_scores: Optional[np.ndarray] = None          # (n_curves, n_intervals)
    interval_edges: Optional[np.ndarray] = None    # (n_intervals + 1,)
    diagnostics: Dict[str, dict] = field(default_factory=dict)
    n_curves: int = 0

    def of_kind(self, kind: str) -> List[str]:
        """Columns classified as ``kind``, in dataset order."""
        return [c for c in self.columns if self.kind_of.get(c) == kind]

    def counts(self) -> Dict[str, int]:
        return {kind: len(self.of_kind(kind)) for kind in KINDS}


def _interval_areas(x: np.ndarray, spectra: np.ndarray, edges: np.ndarray,
                    positive_only: bool) -> np.ndarray:
    """Area under each curve within each bias sub-interval.

    ``spectra`` is (n_points, n_curves). Returns (n_curves, n_intervals),
    NaN where an interval holds fewer than two finite samples of that curve —
    which is what tells "no data here" apart from "no signal here".
    """
    n_curves = spectra.shape[1]
    n_intervals = len(edges) - 1
    areas = np.full((n_curves, n_intervals), np.nan, dtype=np.float64)

    for j in range(n_intervals):
        lo, hi = edges[j], edges[j + 1]
        # The last interval takes its right edge, so no sample is dropped.
        in_bin = (x >= lo) & (x <= hi) if j == n_intervals - 1 else (x >= lo) & (x < hi)
        if np.count_nonzero(in_bin) < 2:
            continue
        xs = x[in_bin]
        ys = spectra[in_bin, :]
        finite = np.isfinite(ys).sum(axis=0)
        if positive_only:
            values = positive_integral(ys, xs, axis=0)
        else:
            values = np.trapz(np.nan_to_num(ys, nan=0.0), xs, axis=0)
        areas[:, j] = np.where(finite >= 2, values, np.nan)
    return areas


def _robust_z(areas: np.ndarray) -> np.ndarray:
    """Per-interval z-score of each curve against the population.

    Median and MAD across curves, so the population's own centre is not moved
    by the very curves being looked for. A degenerate interval — every curve
    identical — falls back to the scale of the whole set rather than dividing
    by zero.
    """
    with np.errstate(invalid='ignore'):
        centre = np.nanmedian(areas, axis=0)
        spread = 1.4826 * np.nanmedian(np.abs(areas - centre), axis=0)
        overall = 1.4826 * np.nanmedian(np.abs(areas - np.nanmedian(areas)))

    fallback = overall if np.isfinite(overall) and overall > 0 else 1.0
    scale = np.where(np.isfinite(spread) & (spread > 0), spread, fallback)
    with np.errstate(invalid='ignore', divide='ignore'):
        return (areas - centre) / scale


def analyze_outliers(x: np.ndarray, spectra: np.ndarray,
                     columns: Sequence[str],
                     n_intervals: int = DEFAULTS['n_intervals'],
                     z_threshold: float = DEFAULTS['z_threshold'],
                     offset_fraction: float = DEFAULTS['offset_fraction'],
                     min_run: int = DEFAULTS['min_run'],
                     saturation_tolerance: float = DEFAULTS['saturation_tolerance'],
                     positive_only: bool = True) -> OutlierAnalysis:
    """Classify each curve against the population the others form.

    Parameters
    ----------
    x : np.ndarray
        Bias axis, one value per sample.
    spectra : np.ndarray
        ``(n_points, n_curves)``.
    columns : sequence of str
        Column name per curve; the analysis is keyed by these so a caller can
        act on it after reordering.
    n_intervals : int
        How many bias sub-intervals the sweep is split into.
    z_threshold : float
        Robust z above which an interval counts as departing.
    offset_fraction : float
        Share of intervals that must depart for ``offset`` rather than
        ``bandgap``.
    min_run : int
        Contiguous departing intervals required for ``bandgap``. Below this a
        curve is left alone: a band edge in the wrong place moves a connected
        stretch of the sweep, whereas noise departs in isolated intervals.
    saturation_tolerance : float
        Share of the median bias coverage below which a curve is truncated.
    positive_only : bool
        Integrate the positive part only — the house rule for dI/dV. A curve
        displaced far *below* the population still shows up, as its intervals
        then read ~0 against everyone else's positive area.
    """
    x = np.asarray(x, dtype=np.float64)
    spectra = np.asarray(spectra, dtype=np.float64)
    columns = list(columns)
    analysis = OutlierAnalysis(columns=columns, n_curves=len(columns))

    if spectra.ndim != 2 or spectra.shape[1] != len(columns):
        raise ValueError("spectra must be (n_points, n_curves) matching columns")
    # Below three curves there is no population to be an outlier of.
    if len(columns) < 3 or x.size < 4:
        return analysis

    finite_x = np.isfinite(x)
    if np.count_nonzero(finite_x) < 4:
        return analysis

    # ---- saturation: judged on coverage, before any area is compared ----
    coverage = np.zeros(len(columns), dtype=np.float64)
    full_span = float(np.nanmax(x) - np.nanmin(x))
    for i in range(len(columns)):
        ok = np.isfinite(spectra[:, i]) & finite_x
        if np.count_nonzero(ok) >= 2 and full_span > 0:
            coverage[i] = float(x[ok].max() - x[ok].min()) / full_span
    median_coverage = float(np.median(coverage))
    saturated = set()
    if median_coverage > 0:
        for i, cov in enumerate(coverage):
            if cov < saturation_tolerance * median_coverage:
                saturated.add(i)
                analysis.kind_of[columns[i]] = SATURATION
                analysis.diagnostics[columns[i]] = {
                    'kind': SATURATION,
                    'coverage': float(cov),
                    'median_coverage': median_coverage,
                }

    # ---- offset / bandgap: area per sub-interval, compared across curves ---
    lo, hi = float(np.nanmin(x)), float(np.nanmax(x))
    edges = np.linspace(lo, hi, int(max(2, n_intervals)) + 1)
    areas = _interval_areas(x, spectra, edges, positive_only)

    # A truncated curve would drag the population's own centre around, so it
    # is left out of the comparison it is not a member of.
    comparable = np.array([i not in saturated for i in range(len(columns))])
    if np.count_nonzero(comparable) >= 3:
        z_full = np.full(areas.shape, np.nan)
        z_full[comparable, :] = _robust_z(areas[comparable, :])
    else:
        z_full = _robust_z(areas)

    analysis.z_scores = z_full
    analysis.interval_edges = edges

    for i, column in enumerate(columns):
        if i in saturated:
            continue
        row = z_full[i, :]
        usable = np.isfinite(row)
        if not usable.any():
            continue
        departing = usable & (np.abs(row) > z_threshold)
        n_departing = int(np.count_nonzero(departing))
        if n_departing == 0:
            continue
        fraction = n_departing / int(np.count_nonzero(usable))
        run = _longest_run(departing)
        if fraction >= offset_fraction:
            kind = OFFSET
        elif run >= int(max(1, min_run)):
            kind = BANDGAP
        else:
            # Departs, but only in scattered single intervals — that is what
            # noise looks like, not a curve that belongs somewhere else.
            continue
        analysis.kind_of[column] = kind
        where = np.flatnonzero(departing)
        analysis.diagnostics[column] = {
            'kind': kind,
            'n_departing': n_departing,
            'n_intervals': int(np.count_nonzero(usable)),
            'fraction': float(fraction),
            'longest_run': int(run),
            'max_abs_z': float(np.nanmax(np.abs(row[usable]))),
            'intervals': [[float(edges[j]), float(edges[j + 1])] for j in where],
        }

    return analysis


# ---------------------------------------------------------------------------
# Grouping: which curves are repetitions of the same thing
# ---------------------------------------------------------------------------

# How the population is chosen. "point" is what an overview dataset wants; a
# line scan's overview holds many points and comparing across them would call
# the ends of the line outliers, because they genuinely differ.
GROUP_BY_POINT = 'point'
GROUP_BY_DATASET = 'dataset'
GROUPINGS = (GROUP_BY_POINT, GROUP_BY_DATASET)

# Fewer than this and there is no population to stand out from.
MIN_GROUP_SIZE = 3


def build_groups(columns: Sequence[str],
                 spectrum_meta: Optional[Sequence[dict]] = None,
                 mode: str = GROUP_BY_POINT) -> "Dict[str, List[int]]":
    """Split the columns into the populations to compare within.

    ``point`` reads the per-spectrum metadata a loader recorded: an overview
    names its columns ``P<point>R<rep>`` and records ``point_index`` (or
    ``line_pos`` for a line scan's overview), so each point's repetitions form
    one population. This is the grouping that makes an average meaningful —
    averaging across points is averaging across different places on the
    sample.

    ``dataset`` puts every curve in one population. It is the honest choice
    for a set that really is repetitions of a single measurement, and the
    fallback when nothing recorded how the columns group.

    Returns ``{group label: [column indices]}``, insertion-ordered.
    """
    columns = list(columns)
    if mode == GROUP_BY_DATASET or not spectrum_meta:
        return {'all curves': list(range(len(columns)))}

    by_column = {
        entry.get('column'): entry
        for entry in spectrum_meta if isinstance(entry, dict)
    }
    groups: "Dict[str, List[int]]" = {}
    for index, column in enumerate(columns):
        entry = by_column.get(column) or {}
        key = entry.get('point_index')
        label = f"point {key}" if key is not None else None
        if label is None:
            key = entry.get('line_pos')
            label = f"position {key}" if key is not None else None
        if label is None:
            # No grouping information for this column: it cannot be compared
            # with anything, so it forms its own (undersized) group and is
            # skipped rather than silently joining someone else's population.
            label = f"ungrouped {column}"
        groups.setdefault(label, []).append(index)

    # Nothing was actually grouped — treat it as one population and let the
    # caller say so.
    if len(groups) == len(columns):
        return {'all curves': list(range(len(columns)))}
    return groups


def analyze_grouped(x: np.ndarray, spectra: np.ndarray,
                    columns: Sequence[str],
                    groups: "Dict[str, List[int]]",
                    **kwargs) -> "Dict[str, OutlierAnalysis]":
    """Run :func:`analyze_outliers` within each population.

    Groups too small to have a population are skipped, not guessed at.
    """
    spectra = np.asarray(spectra, dtype=np.float64)
    columns = list(columns)
    out: "Dict[str, OutlierAnalysis]" = {}
    for label, indices in groups.items():
        if len(indices) < MIN_GROUP_SIZE:
            continue
        out[label] = analyze_outliers(
            x, spectra[:, indices], [columns[i] for i in indices], **kwargs)
    return out


def select_outliers(analysis: OutlierAnalysis,
                    enabled: Dict[str, bool],
                    limits: Dict[str, int]) -> tuple:
    """Decide which of the classified curves are actually removed.

    Returns ``(columns_to_remove, messages)``.

    A kind that is switched off is left alone. A kind whose count exceeds its
    limit removes **nothing**: past that many, what has been found is the
    spread of the population rather than a few curves standing outside it, and
    silently deleting a fifth of the data would be the worst possible answer.
    The message says so and asks for a look by eye.
    """
    remove: List[str] = []
    messages: List[str] = []
    counts = analysis.counts()

    for kind in KINDS:
        if not enabled.get(kind, False):
            continue
        found = counts.get(kind, 0)
        limit = int(limits.get(kind, 0))
        if found == 0:
            messages.append(f"No {kind} outliers found.")
            continue
        if found > limit:
            messages.append(
                f"{found} curves look like {kind} outliers, more than the {limit} "
                f"allowed — that is a distribution of values, not a few odd "
                f"curves. None removed; check them by eye."
            )
            continue
        picked = analysis.of_kind(kind)
        remove.extend(picked)
        messages.append(f"Removed {found} {kind} outlier(s): {', '.join(picked)}.")

    # A curve can only be classified as one kind, but keep order and
    # uniqueness explicit rather than relying on that.
    seen = set()
    ordered = [c for c in analysis.columns if c in set(remove) and not (c in seen or seen.add(c))]
    return ordered, messages


def select_grouped(analyses: "Dict[str, OutlierAnalysis]",
                   enabled: Dict[str, bool],
                   limits: Dict[str, int]) -> tuple:
    """Apply :func:`select_outliers` within every population.

    The limits are **per group**, which is what makes them mean what a user
    expects: "at most 5 bad repetitions at this point", not "at most 5 across
    a 2000-column overview". Returns ``(columns_to_remove, messages)`` with
    each message naming the group it came from.
    """
    remove: List[str] = []
    messages: List[str] = []
    for label, analysis in analyses.items():
        picked, notes = select_outliers(analysis, enabled, limits)
        remove.extend(picked)
        # A clean group is the normal case; saying so for every one of 16
        # points would bury the groups that actually found something.
        for note in notes:
            if not note.startswith("No "):
                messages.append(f"{label}: {note}")
    return remove, messages
