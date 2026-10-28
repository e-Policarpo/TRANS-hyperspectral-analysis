"""Confinement Designer sweeps, one spectrum per worker process.

Each spectrum's search is independent of every other — its own peaks, its
own ``Designer(seed=...)`` built fresh inside ``_design_one_spectrum`` — so a
sweep is embarrassingly parallel, and the result does not depend on how the
spectra are scheduled: a seeded run gives the same rows with one worker or
eight. Threads would not help: the search is pure Python under the GIL.

Processes are started with ``spawn``, the only start method that is safe
under Qt on macOS and the one a PyInstaller bundle supports (``main.py``
calls ``multiprocessing.freeze_support()`` for it). A worker never imports
Qt: everything ``_design_one_spectrum`` reaches is a static or class method
of ``ToolImplementations``, so it is called on the class itself.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from typing import Callable, List, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Fewer spectra than this are searched in-process: a spawned worker costs
#: about a second to start (it imports numpy, scipy and pandas afresh), which
#: a single spectrum's ~2 s search does not repay.
MIN_SPECTRA_FOR_POOL = 3

_cancel_event = None


def default_workers() -> int:
    """Every core but one, so the interface stays responsive."""
    return max(1, (os.cpu_count() or 2) - 1)


def resolve_workers(requested, n_spectra: int) -> int:
    """How many processes a sweep of ``n_spectra`` actually gets.

    ``requested`` 0 or None is automatic; 1 is the old serial loop; anything
    larger is a ceiling. Never more workers than spectra.
    """
    try:
        want = int(requested or 0)
    except (TypeError, ValueError):
        want = 0
    if want <= 0:
        want = default_workers()
    if n_spectra < MIN_SPECTRA_FOR_POOL:
        return 1
    return max(1, min(want, n_spectra))


class _OneSpectrum:
    """The two attributes ``_design_one_spectrum`` reads off a dataset.

    Only one column travels to the worker instead of the whole dataset.
    """

    def __init__(self, x, y, column):
        self.independent_var = np.asarray(x, dtype=np.float64)
        self.spectra = pd.DataFrame({column: np.asarray(y, dtype=np.float64)})


class _WorkerTask:
    """What ``_design_one_spectrum`` polls for Cancel, read across processes."""

    @property
    def cancelled(self) -> bool:
        return _cancel_event is not None and _cancel_event.is_set()


def _init_worker(event) -> None:
    global _cancel_event
    _cancel_event = event


def _search_one(job):
    index, x, y, column, params = job
    from src.backend.tool_implementations import ToolImplementations
    run = ToolImplementations._design_one_spectrum(
        ToolImplementations, _WorkerTask(), _OneSpectrum(x, y, column), 0,
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
    ctx = multiprocessing.get_context('spawn')
    event = ctx.Event()
    runs: dict = {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                             initializer=_init_worker,
                             initargs=(event,)) as pool:
        pending = {pool.submit(_search_one,
                               (int(i), x, np.asarray(values[:, i]),
                                str(columns[i]), params)): int(i)
                   for i in indices}
        try:
            while pending:
                done, _ = wait(pending, timeout=0.25,
                               return_when=FIRST_COMPLETED)
                if is_cancelled():
                    event.set()
                    for future in pending:
                        future.cancel()
                    logger.info("Confinement Designer cancelled with %d "
                                "spectrum(s) still queued or running",
                                len(pending))
                    return None
                for future in done:
                    index = pending.pop(future)
                    runs[index] = future.result()
                    if on_done is not None:
                        on_done(len(runs))
        except BaseException:
            event.set()
            for future in pending:
                future.cancel()
            raise
    return [runs[int(i)] for i in indices]
