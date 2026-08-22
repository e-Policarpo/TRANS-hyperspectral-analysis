"""
Line scan: one confinement search per spectrum.

A line scan is a voltage column and one dI/dV column per position. Each
position is an independent spectrum, and the question is the usual one —
which well produces this ladder of levels? — repeated point by point.

**Not converging is an answer.** On an arbitrary scan most positions
usually fall outside the confining structure: no peaks, a single peak, or
peaks no well explains. Marking that as "no confinement", with the reason,
is worth more than pushing out some number — a map where every point has a
size is a map that lies.

The module knows nothing about the UI or the solver: the caller injects the
peak-finding and candidate-search functions. That keeps the whole of the
logic testable without opening a window and without waiting on a global
optimisation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np

from src.physics.branches import DidvCurve

logger = logging.getLogger(__name__)

#: Why a point has no confinement. These are data, not loose text: the map
#: colours by them and the summary counts them. Keys are stable and
#: persisted; :data:`REASON_LABELS` holds what a user reads.
NO_PEAKS = "no_peaks"
FEW_PEAKS = "too_few_peaks"
NO_FIT = "no_candidate"
BAD_FIT = "error_above_limit"
NO_PAIR = "no_carrier_pair"
CANCELLED = "cancelled"

REASONS = (NO_PEAKS, FEW_PEAKS, NO_FIT, BAD_FIT, NO_PAIR, CANCELLED)

REASON_LABELS = {
    NO_PEAKS: "No peaks",
    FEW_PEAKS: "Too few peaks",
    NO_FIT: "No candidate",
    BAD_FIT: "Error above the limit",
    NO_PAIR: "No electron-hole pair",
    CANCELLED: "Cancelled",
}


@dataclass
class LineScan:
    """The curves of one scan, in the order they were measured."""

    x: np.ndarray                       # sample voltage (V), shared by all
    ys: np.ndarray                      # (n_curve_points, n_positions)
    names: List[str] = field(default_factory=list)
    path: str = ""
    #: Step between positions, in nm. None = axis in point index.
    step_nm: Optional[float] = None

    @property
    def n_points(self) -> int:
        return int(self.ys.shape[1])

    def curve(self, index: int) -> DidvCurve:
        """One position's curve, in the format the dI/dV analysis takes."""
        y = self.ys[:, index]
        keep = np.isfinite(y)
        return DidvCurve(x=self.x[keep], y=y[keep],
                         name=self.names[index] if index < len(self.names)
                         else f"#{index}")

    def positions_nm(self) -> np.ndarray:
        """Spatial axis: nm when there is a step, point index when there is not."""
        idx = np.arange(self.n_points, dtype=float)
        return idx * self.step_nm if self.step_nm else idx

    @property
    def position_label(self) -> str:
        return "Position (nm)" if self.step_nm else "Point"


@dataclass
class PointResult:
    """What the search found at one position along the line."""

    index: int
    position: float
    name: str = ""
    size_nm: Optional[float] = None      # None = no confinement
    rrmse: Optional[float] = None
    dims_nm: tuple = ()
    meff: Optional[float] = None
    n_peaks: int = 0
    reason: str = ""                     # empty when it converged
    solution: Optional[dict] = None
    hole_size_nm: Optional[float] = None
    mismatch_nm: Optional[float] = None
    group: Optional[int] = None          # filled in by `group_by_size`

    @property
    def converged(self) -> bool:
        return self.size_nm is not None


# ── point-by-point analysis ──────────────────────────────────────────────

def analyze_line_scan(scan: LineScan,
                      targets_fn: Callable[[DidvCurve], dict],
                      search_fn: Callable[[dict], List[dict]],
                      size_fn: Callable[[dict], float],
                      min_peaks: int = 2,
                      max_rrmse: Optional[float] = None,
                      progress: Optional[Callable[[int, int], bool]] = None
                      ) -> List[PointResult]:
    """Run the search at every position and return one result per point.

    ``targets_fn`` takes the curve and returns ``{'targets': [...], …}`` (the
    peaks already split by branch); ``search_fn`` takes that dict and returns
    candidates; ``size_fn`` extracts the confinement size from a candidate.
    ``progress`` is called at each point and may return False to stop — a
    long scan has to be cancellable.
    """
    positions = scan.positions_nm()
    results: List[PointResult] = []
    started = time.perf_counter()
    logger.info("line scan: %d positions, at least %d peak(s) per point, "
                "maximum error %s", scan.n_points, min_peaks,
                "unbounded" if max_rrmse is None else f"{max_rrmse:g}%")

    for i in range(scan.n_points):
        name = scan.names[i] if i < len(scan.names) else f"#{i}"
        point = PointResult(index=i, position=float(positions[i]), name=name)

        if progress is not None and not progress(i, scan.n_points):
            point.reason = CANCELLED
            results.append(point)
            for j in range(i + 1, scan.n_points):
                results.append(PointResult(
                    index=j, position=float(positions[j]),
                    name=scan.names[j] if j < len(scan.names) else f"#{j}",
                    reason=CANCELLED))
            break

        point_started = time.perf_counter()
        try:
            found = targets_fn(scan.curve(i))
        except Exception as exc:
            logger.warning("point %d (%s): peak analysis failed — %s",
                           i, name, exc)
            point.reason = NO_PEAKS
            results.append(point)
            continue

        targets = list(found.get('targets') or [])
        point.n_peaks = int(found.get('n_peaks', len(targets)))
        logger.debug("point %d (%s) at %.3f: %d peak(s), %d target(s) in the "
                     "branch: [%s]", i, name, point.position, point.n_peaks,
                     len(targets), ", ".join(f"{t:.4f}" for t in targets[:8]))

        if not targets:
            point.reason = NO_PEAKS
            _log_point(point, point_started)
            results.append(point)
            continue
        if len(targets) < min_peaks:
            # With a single peak there is no ladder: any size "explains" one
            # isolated level, and the fit would be a tautology.
            point.reason = FEW_PEAKS
            _log_point(point, point_started)
            results.append(point)
            continue

        try:
            candidates = search_fn(found)
        except Exception:
            logger.exception("point %d (%s): search failed", i, name)
            candidates = []

        logger.debug("point %d: %d candidate(s) — %s", i, len(candidates),
                     ", ".join(f"{size_fn(c):.3f} nm ({c.get('RRMSE', float('nan')):.3f}%)"
                               for c in candidates[:6]) or "none")

        if not candidates:
            point.reason = found.get('reason') or NO_FIT
            _log_point(point, point_started)
            results.append(point)
            continue

        best = pick_best(candidates, size_fn)
        rrmse = float(best.get('RRMSE', float('nan')))
        if max_rrmse is not None and not (rrmse <= max_rrmse):
            point.reason = BAD_FIT
            point.rrmse = rrmse
            _log_point(point, point_started)
            results.append(point)
            continue

        point.size_nm = float(size_fn(best))
        point.rrmse = rrmse
        point.dims_nm = tuple(best.get('dims', ()))
        point.meff = best.get('meff')
        point.solution = best
        point.hole_size_nm = found.get('hole_size_nm')
        point.mismatch_nm = found.get('mismatch_nm')
        _log_point(point, point_started)
        results.append(point)

    converged = sum(1 for r in results if r.converged)
    elapsed = time.perf_counter() - started
    logger.info("line scan finished: %d of %d positions converged in %.1f s "
                "(%.0f ms/position)", converged, len(results), elapsed,
                elapsed / max(1, len(results)) * 1000)
    for reason, count in sorted(summarize(results)['reasons'].items(),
                                key=lambda kv: -kv[1]):
        logger.info("  no confinement: %dx %s", count,
                    REASON_LABELS.get(reason, reason))
    return results


def _log_point(point: PointResult, started: float) -> None:
    """One line per position — the trail that says where the map came from."""
    elapsed = (time.perf_counter() - started) * 1000
    if point.converged:
        extra = ""
        if point.hole_size_nm is not None:
            extra = (f", hole {point.hole_size_nm:.3f} nm, "
                     f"delta {point.mismatch_nm:.3f} nm")
        logger.info("point %3d @ %8.3f: %7.3f nm (error %.3f%%, m*=%s%s) [%.0f ms]",
                    point.index, point.position, point.size_nm,
                    point.rrmse or 0.0,
                    f"{point.meff:g}" if point.meff else "?", extra, elapsed)
    else:
        logger.info("point %3d @ %8.3f: no confinement — %s (%d peak(s)) [%.0f ms]",
                    point.index, point.position,
                    REASON_LABELS.get(point.reason, point.reason),
                    point.n_peaks, elapsed)


def pick_best(candidates: Sequence[dict], size_fn: Callable[[dict], float],
              tie_tol: Optional[float] = None) -> dict:
    """The candidate that represents the point: of those tied, the smallest.

    A tie is the common case, not the exception: a well of 2L matches the
    same targets with twice the quantum numbers, and the two errors differ in
    the fourth decimal — optimiser noise, not physics. Comparing the errors
    as exact numbers makes the map alternate between L, 2L and 3L from one
    point to the next and look like structure where there is only degeneracy.

    So "tied" is a **band** around the best error rather than equality: by
    default 0.05 percentage points or 10% of the error itself, whichever is
    larger. Within it the smallest confinement wins — the primary solution,
    the one that matches the targets with n = 1, 2, 3.
    """
    if not candidates:
        raise ValueError("no candidates")
    errors = [float(s.get('RRMSE', float('inf'))) for s in candidates]
    best_error = min(errors)
    if tie_tol is None:
        tie_tol = max(0.05, 0.1 * abs(best_error))
    tied = [s for s, err in zip(candidates, errors)
            if err <= best_error + tie_tol]
    chosen = min(tied, key=size_fn)
    if len(tied) > 1:
        logger.debug("tie between %d candidate(s) within %.3f pp: %s → taking "
                     "%.3f nm", len(tied), tie_tol,
                     ", ".join(f"{size_fn(s):.3f}" for s in tied[:6]),
                     size_fn(chosen))
    return chosen


# ── grouping ─────────────────────────────────────────────────────────────

def group_by_size(results: Sequence[PointResult], tol_nm: float = 1.0) -> List[dict]:
    """Join the positions that converged to the same size.

    Gap clustering: the sizes are sorted and a split happens where two
    neighbours are more than ``tol_nm`` apart. It is the same idea as the
    pair tolerance — two numbers within it describe the same well — and it
    has the advantage of not needing to know how many groups there are.

    Writes the group index onto each point and returns the groups ordered by
    size.
    """
    converged = [r for r in results if r.converged]
    for r in results:
        r.group = None
    if not converged:
        return []

    ordered = sorted(converged, key=lambda r: r.size_nm)
    groups: List[List[PointResult]] = [[ordered[0]]]
    for previous, current in zip(ordered, ordered[1:]):
        if current.size_nm - previous.size_nm > tol_nm:
            groups.append([current])
        else:
            groups[-1].append(current)

    logger.debug("grouping %d size(s) with a %.3f nm tolerance: [%s%s]",
                 len(ordered), tol_nm,
                 ", ".join(f"{r.size_nm:.3f}" for r in ordered[:20]),
                 ", …" if len(ordered) > 20 else "")
    out = []
    for gi, members in enumerate(groups):
        sizes = [m.size_nm for m in members]
        for m in members:
            m.group = gi
        # Members in line order, not in the size order they were grouped in:
        # whoever reads the list wants to know WHERE the group is.
        along_line = sorted(members, key=lambda m: m.index)
        out.append({
            'index': gi,
            'size_nm': float(np.mean(sizes)),
            'min_nm': float(min(sizes)),
            'max_nm': float(max(sizes)),
            'spread_nm': float(max(sizes) - min(sizes)),
            'count': len(members),
            'points': [m.index for m in along_line],
            'positions': [m.position for m in along_line],
        })
    logger.info("grouping: %d group(s) over %d converged position(s)",
                len(out), len(converged))
    for g in out:
        listed = g['points'][:12]
        logger.info("  group %d: %.3f nm (%.3f-%.3f), %d position(s): %s%s",
                    g['index'], g['size_nm'], g['min_nm'], g['max_nm'],
                    g['count'], ", ".join(str(i) for i in listed),
                    ", …" if len(g['points']) > len(listed) else "")
    return out


def segments_along_line(results: Sequence[PointResult]) -> List[dict]:
    """Contiguous stretches of the line with the same group (or none).

    Grouping by size ignores where the points are; this returns the spatial
    reading — where each domain starts and ends, with the empty stretches in
    between, which are part of the answer.
    """
    segments = []
    for r in results:
        key = r.group if r.converged else None
        if segments and segments[-1]['group'] == key:
            segments[-1]['end_index'] = r.index
            segments[-1]['end'] = r.position
            segments[-1]['count'] += 1
        else:
            segments.append({'group': key, 'start_index': r.index,
                             'end_index': r.index, 'start': r.position,
                             'end': r.position, 'count': 1})
    return segments


def summarize(results: Sequence[PointResult]) -> dict:
    """Counts for the summary: how many converged, and why the rest did not."""
    reasons = {}
    for r in results:
        if not r.converged and r.reason:
            reasons[r.reason] = reasons.get(r.reason, 0) + 1
    converged = [r for r in results if r.converged]
    sizes = [r.size_nm for r in converged]
    return {
        'total': len(results),
        'converged': len(converged),
        'reasons': reasons,
        'size_min': min(sizes) if sizes else None,
        'size_max': max(sizes) if sizes else None,
        'size_mean': float(np.mean(sizes)) if sizes else None,
    }
