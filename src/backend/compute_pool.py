"""One process pool for the whole application, started on first use.

The confinement searches are pure Python under the GIL, so threads do not
help them; processes do. A spawned worker costs about a second to start
(numpy, scipy, pandas and the backend imported afresh), and a pool built per
run paid that on every run — which is why a sweep of fewer than three
spectra used to stay serial. Kept alive, the pool pays it once per session,
and a single spectrum's search can hand its independent passes to it.

Processes are started with ``spawn``, the only start method that is safe
under Qt on macOS and the one a PyInstaller bundle supports (``main.py``
calls ``multiprocessing.freeze_support()`` for it). The BLAS thread caps
``main.py`` sets are environment variables, so the workers inherit them and
eight processes do not each start a thread pool.

Cancellation is per run, not per pool: every run takes a :class:`CancelToken`,
a slot in a shared byte array the workers were handed at start-up, so a
Cancel in one tool stops that tool's tasks and nobody else's. A task reads
its slot with :func:`cancelled`.
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import threading
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, List, Optional, Sequence

logger = logging.getLogger(__name__)

#: How many runs can hold a cancel slot at once.
N_SLOTS = 64

_lock = threading.Lock()
_pool: Optional[ProcessPoolExecutor] = None
_flags = None           # the parent's shared array
_free = list(range(N_SLOTS))
_worker_flags = None    # the same array, as a worker sees it


def default_workers() -> int:
    """Every core but one, so the interface stays responsive."""
    return max(1, (os.cpu_count() or 2) - 1)


def _init_worker(flags) -> None:
    global _worker_flags
    _worker_flags = flags


def cancelled(slot: Optional[int]) -> bool:
    """Inside a worker: has the run holding ``slot`` been cancelled?"""
    return (slot is not None and _worker_flags is not None
            and bool(_worker_flags[slot]))


def _get_pool() -> ProcessPoolExecutor:
    global _pool, _flags
    with _lock:
        if _pool is None:
            ctx = multiprocessing.get_context('spawn')
            if _flags is None:
                _flags = ctx.Array('b', N_SLOTS, lock=False)
            _pool = ProcessPoolExecutor(max_workers=default_workers(),
                                        mp_context=ctx,
                                        initializer=_init_worker,
                                        initargs=(_flags,))
            logger.info("compute pool: %d worker processes",
                        default_workers())
        return _pool


def _discard_pool() -> None:
    """Drop a broken pool; the next run starts a fresh one."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


@atexit.register
def shutdown() -> None:
    _discard_pool()


def _free_slot(slot: int) -> None:
    _flags[slot] = 0
    with _lock:
        _free.append(slot)


class CancelToken:
    """One run's cancel slot. Use as a context manager so the slot returns."""

    def __init__(self):
        _get_pool()                     # creates the shared array
        with _lock:
            if not _free:
                raise RuntimeError("too many concurrent pool runs")
            self.slot = _free.pop()
        _flags[self.slot] = 0
        self._running: list = []

    def set(self) -> None:
        _flags[self.slot] = 1

    def hold(self, futures) -> None:
        """Keep the slot until these (cancelled, still running) tasks end.

        A task that was already running when Cancel came keeps reading its
        slot; freeing it at once would let another run reuse the slot and
        clear the flag under it.
        """
        self._running = [f for f in futures if not f.done()]

    def release(self) -> None:
        if self.slot is None:
            return
        slot, self.slot = self.slot, None
        running = [f for f in self._running if not f.done()]
        if not running:
            _free_slot(slot)
            return
        left = [len(running)]
        guard = threading.Lock()

        def _one_done(_future):
            with guard:
                left[0] -= 1
                last = left[0] == 0
            if last:
                _free_slot(slot)
        for future in running:
            future.add_done_callback(_one_done)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def run_ordered(fn: Callable, jobs: Sequence, workers: int,
                is_cancelled: Optional[Callable[[], bool]] = None,
                token: Optional[CancelToken] = None,
                on_done: Optional[Callable[[int], None]] = None
                ) -> Optional[List]:
    """``[fn(job) for job in jobs]`` on the pool, at most ``workers`` at once.

    Results come back in the order of ``jobs`` whatever order they finish
    in, so a caller that replays them sequentially gets exactly the serial
    answer. ``fn`` must be a module-level function and ``jobs`` picklable.

    Returns None when ``is_cancelled`` answered True: queued jobs are never
    started and ``token`` (if given) is set so running ones can stop early.
    ``on_done(n)`` is told how many jobs have finished, in completion order.
    An exception raised by a job is re-raised here, as the serial loop would.
    """
    jobs = list(jobs)
    pool = _get_pool()
    workers = max(1, min(int(workers), len(jobs) or 1))
    results: dict = {}
    pending: dict = {}
    nxt = 0
    try:
        while nxt < len(jobs) or pending:
            while nxt < len(jobs) and len(pending) < workers:
                pending[pool.submit(fn, jobs[nxt])] = nxt
                nxt += 1
            done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            if is_cancelled is not None and is_cancelled():
                if token is not None:
                    token.set()
                    token.hold(pending)
                for future in pending:
                    future.cancel()
                return None
            for future in done:
                results[pending.pop(future)] = future.result()
                if on_done is not None:
                    on_done(len(results))
    except BrokenProcessPool:
        _discard_pool()
        raise
    except BaseException:
        if token is not None:
            token.set()
            token.hold(pending)
        for future in pending:
            future.cancel()
        raise
    return [results[i] for i in range(len(jobs))]


class PoolMapper:
    """What :class:`~src.physics.designer.Designer` takes as ``mapper``.

    The physics package does not import the backend; it only calls
    ``mapper.map(fn, jobs, should_cancel)`` and reads ``mapper.workers``.
    """

    def __init__(self, workers: int):
        self.workers = max(1, int(workers))

    def map(self, fn: Callable, jobs: Sequence,
            should_cancel: Optional[Callable[[], bool]] = None
            ) -> Optional[List]:
        return run_ordered(fn, jobs, self.workers, is_cancelled=should_cancel)
