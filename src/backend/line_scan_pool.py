"""Line Scan Designer positions on the shared process pool.

Every position is its own question — its own peaks, its own search — so a
line is embarrassingly parallel once nothing is shared between positions.
Two things used to be shared and no longer are:

* **The RNG.** One ``Designer`` searched every position, so position 30's
  random starts depended on how many draws positions 0-29 had used. Now each
  position builds ``Designer(seed=run_seed)``: the whole run has one seed,
  recorded beside the results, and a position's answer does not depend on
  which process ran it or in what order.
* **The closures.** The peak and search functions were defined inside
  ``design_line_scan`` and could not be pickled. :class:`LinePointSearch`
  holds the same settings as plain data and is what travels to a worker.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

import numpy as np

from src.backend import compute_pool

logger = logging.getLogger(__name__)

#: Shorter lines are searched in-process; the pool is not worth the trip.
MIN_POINTS_FOR_POOL = 3


class LinePointSearch:
    """Everything one position's search needs, as picklable data."""

    def __init__(self, params: dict, search: dict, carriers: list,
                 paired: bool, hole_first: bool, min_peaks: int,
                 max_rrmse: float):
        self.params = params
        self.search = search
        self.carriers = carriers
        self.paired = paired
        self.hole_first = hole_first
        self.min_peaks = min_peaks
        self.max_rrmse = max_rrmse
        self.split_e = float(params.get('split_e', 0.0) or 0.0)
        self.split_h = float(params.get('split_h', 0.0) or 0.0)

    @staticmethod
    def size(sol) -> float:
        from src.physics.pairing import confinement_size_nm
        return confinement_size_nm(sol, sol.get('meff'))

    def run(self, curve, index: int, position: float, name: str,
            should_cancel: Callable[[], bool], mapper=None):
        """The :class:`~src.physics.line_scan.PointResult` for one position."""
        from src.physics.branches import analyze_curve
        from src.physics.designer import Designer
        from src.physics.line_scan import NO_PAIR, analyze_point
        from src.physics.pairing import confinement_size_nm, pair_candidates

        params, search = self.params, self.search
        designer = Designer(seed=params['seed'], mapper=mapper)

        def targets_fn(curve):
            peaks = analyze_curve(curve, params, split_e=self.split_e,
                                  split_h=self.split_h,
                                  min_abs_V=float(params.get('min_abs_V', 0.0)))
            branch = peaks.hole_eV if self.hole_first else peaks.electron_eV
            return {'targets': branch, 'peaks': peaks,
                    'n_peaks': len(peaks.peaks_V)}

        def _candidates(targets, carrier):
            # Every mass from one search where the masses allow it —
            # see Designer.shares_mass_search. Each candidate carries its
            # own mass, so the alias test runs at that mass.
            carrier = {**carrier, 'Et': np.asarray(targets, dtype=float)}
            found = designer.search_masses(
                search, carrier,
                lambda pm, _label: designer.find_solutions(
                    pm, should_cancel=should_cancel),
                should_cancel=should_cancel)
            return [designer.primary_alias(
                        sol, {**search, 'Et': carrier['Et'],
                              'meff': sol['meff'],
                              'carrier': carrier['carrier']})
                    for sol in found]

        def search_fn(found):
            solutions = _candidates(found['targets'], self.carriers[0])
            if not self.paired:
                return solutions

            # Both carriers: the position only counts when the two close
            # on the same well — the pair's requirement, point by point.
            hole_targets = found['peaks'].hole_eV
            if len(hole_targets) < 2:
                found['reason'] = NO_PAIR
                return []
            holes = _candidates(hole_targets, self.carriers[-1])
            pairs = pair_candidates(solutions, holes,
                                    tol_nm=float(params['pair_tol_nm']),
                                    max_pairs=int(params['maxsol']))
            if not pairs:
                found['reason'] = NO_PAIR
                return []
            found['hole_size_nm'] = confinement_size_nm(
                pairs[0]['hole'], pairs[0]['hole'].get('meff'))
            found['mismatch_nm'] = pairs[0]['mismatch_nm']
            return [pair['electron'] for pair in pairs]

        return analyze_point(curve, index, position, name, targets_fn,
                             search_fn, self.size, self.min_peaks,
                             self.max_rrmse)


def _point_job(job):
    plan, curve, index, position, name, slot = job
    return plan.run(curve, index, position, name,
                    lambda: compute_pool.cancelled(slot))


def analyze_line_parallel(scan, plan: LinePointSearch, workers: int,
                          is_cancelled: Callable[[], bool],
                          on_done: Optional[Callable[[int], None]] = None
                          ) -> List:
    """Every position of ``scan`` on ``workers`` processes, in scan order.

    A cancelled run comes back with every position marked CANCELLED; the
    caller discards it, as it does a cancelled serial run.
    """
    from src.physics.line_scan import (cancelled_point, log_finish, log_start,
                                       point_name)
    positions = scan.positions_nm()
    started = time.perf_counter()
    log_start(scan, plan.min_peaks, plan.max_rrmse)
    logger.info("line scan: %d positions on %d worker processes",
                scan.n_points, workers)
    with compute_pool.CancelToken() as token:
        jobs = [(plan, scan.curve(i), i, float(positions[i]),
                 point_name(scan, i), token.slot)
                for i in range(scan.n_points)]
        results = compute_pool.run_ordered(
            _point_job, jobs, workers, is_cancelled=is_cancelled,
            token=token, on_done=on_done)
    if results is None:
        return [cancelled_point(scan, i, positions[i])
                for i in range(scan.n_points)]
    log_finish(results, started)
    return results
