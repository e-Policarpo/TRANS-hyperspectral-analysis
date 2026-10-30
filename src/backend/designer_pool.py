"""Confinement Designer sweeps on the shared process pool.

Two grains of parallelism, never nested (a worker cannot feed the pool):

* **One spectrum per worker** when there are enough spectra to fill it.
  Each spectrum's search is independent of every other — its own peaks, its
  own ``Designer(seed=...)`` built fresh inside ``_design_one_spectrum`` —
  so the sweep is embarrassingly parallel and a seeded run gives the same
  rows with one worker or eight.
* **One search spread over the workers** when there are only one or two
  spectra: the search's own independent passes (analytical refinements,
  differential-evolution passes, lattice chunks, enumeration refinements) go
  to the pool through :class:`~src.backend.compute_pool.PoolMapper` and are
  replayed in serial order, so the candidates are again the serial ones.

The pool itself lives in :mod:`src.backend.compute_pool` and is kept for the
session, so neither grain pays the ~1 s worker start-up per run. A worker
never imports Qt: everything ``_design_one_spectrum`` reaches is a static or
class method of ``ToolImplementations``, so it is called on the class itself.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.backend import compute_pool
from src.backend.compute_pool import default_workers  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)

#: From this many spectra up, a sweep runs one spectrum per worker. Below
#: it, each spectrum's search is spread over the workers instead: one
#: spectrum per worker would leave the rest of the pool idle.
MIN_SPECTRA_FOR_POOL = 3


def _requested(requested) -> int:
    try:
        want = int(requested or 0)
    except (TypeError, ValueError):
        want = 0
    return default_workers() if want <= 0 else want


def resolve_workers(requested, n_spectra: int) -> int:
    """How many processes a sweep of ``n_spectra`` runs spectra on.

    ``requested`` 0 or None is automatic; 1 is the old serial loop; anything
    larger is a ceiling. Never more workers than spectra, and 1 below
    :data:`MIN_SPECTRA_FOR_POOL` — those sweeps parallelise inside the
    search instead (:func:`search_workers`).
    """
    if n_spectra < MIN_SPECTRA_FOR_POOL:
        return 1
    return max(1, min(_requested(requested), n_spectra))


def search_workers(requested, n_spectra: int) -> int:
    """How many processes ONE spectrum's search is spread over.

    The complement of :func:`resolve_workers`: the requested count for a
    sweep too short to fill the pool with spectra, 1 otherwise (and 1 when
    the serial loop was asked for).
    """
    if n_spectra >= MIN_SPECTRA_FOR_POOL:
        return 1
    return max(1, _requested(requested))


def plan_workers(requested, n_spectra: int) -> Tuple[int, int]:
    """``(spectrum workers, search workers)`` — at most one of them above 1."""
    return (resolve_workers(requested, n_spectra),
            search_workers(requested, n_spectra))


class _OneSpectrum:
    """The two attributes ``_design_one_spectrum`` reads off a dataset.

    Only one column travels to the worker instead of the whole dataset.
    """

    def __init__(self, x, y, column):
        self.independent_var = np.asarray(x, dtype=np.float64)
        self.spectra = pd.DataFrame({column: np.asarray(y, dtype=np.float64)})


class _WorkerTask:
    """What ``_design_one_spectrum`` polls for Cancel, read across processes."""

    def __init__(self, slot):
        self.slot = slot

    @property
    def cancelled(self) -> bool:
        return compute_pool.cancelled(self.slot)


def _search_one(job):
    index, x, y, column, params, slot = job
    from src.backend.tool_implementations import ToolImplementations
    run = ToolImplementations._design_one_spectrum(
        ToolImplementations, _WorkerTask(slot), _OneSpectrum(x, y, column), 0,
        params)
    run['spectrum_index'] = int(index)
    return run


def design_spectra_parallel(spectral_data, indices: Sequence[int],
                            params: dict, workers: int,
                            is_cancelled: Callable[[], bool],
                            on_done: Optional[Callable[[int], None]] = None
                            ) -> Optional[List[dict]]:
    """Run ``_design_one_spectrum`` over ``indices`` on ``workers`` processes.

    Returns the run records in the order of ``indices``, or None when the
    sweep was cancelled. ``on_done(n)`` is told how many spectra have
    finished, in completion order, so the progress bar moves as they land.
    An exception raised by one spectrum's search is re-raised here, exactly
    as the serial loop would have raised it.
    """
    x = np.asarray(spectral_data.independent_var, dtype=np.float64)
    values = spectral_data.spectra.values
    columns = spectral_data.spectra.columns
    with compute_pool.CancelToken() as token:
        runs = compute_pool.run_ordered(
            _search_one,
            [(int(i), x, np.asarray(values[:, i]), str(columns[i]), params,
              token.slot) for i in indices],
            workers, is_cancelled=is_cancelled, token=token, on_done=on_done)
    if runs is None:
        logger.info("Confinement Designer cancelled with spectra still "
                    "queued or running")
    return runs
