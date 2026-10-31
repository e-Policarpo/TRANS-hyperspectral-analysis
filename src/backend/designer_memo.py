"""The session's enumeration memos, one per spectrum.

:class:`~src.physics.enum_memo.EnumerationMemo` makes a rerun of the
enumerated search compute only what a changed range adds. This module keeps
those memos between runs. A spectrum is found by a fingerprint of its data —
that only routes it; correctness comes from the memo's own keys, which hold
the targets and every setting the objective reads, so new peaks or a
different model simply miss.

Bounded by the total number of searches held (each ~10 kB at the default
lattice), oldest spectrum dropped first.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Optional

import numpy as np

from src.physics.enum_memo import EnumerationMemo

#: About 25 MB at the default lattice.
MAX_SEARCHES = 2048
#: Searches kept per spectrum: carriers x masses x model settings tried.
PER_SPECTRUM = 32

_lock = threading.Lock()
_memos: "OrderedDict[str, EnumerationMemo]" = OrderedDict()


def fingerprint(x, y) -> str:
    h = hashlib.sha1()
    for a in (x, y):
        a = np.ascontiguousarray(a, dtype=np.float64)
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def memo_for(key: str) -> EnumerationMemo:
    """The memo for one spectrum, created empty the first time."""
    with _lock:
        memo = _memos.get(key)
        if memo is None:
            memo = _memos[key] = EnumerationMemo(max_keys=PER_SPECTRUM)
        else:
            _memos.move_to_end(key)
        _evict()
        return memo


def put(key: str, memo: Optional[EnumerationMemo]) -> None:
    """Store a memo that came back from a worker process."""
    if memo is None:
        return
    with _lock:
        _memos[key] = memo
        _memos.move_to_end(key)
        _evict()


def _evict() -> None:
    """Drop the least recently used spectra past the budget. Holds _lock."""
    total = sum(len(m) for m in _memos.values())
    while total > MAX_SEARCHES and len(_memos) > 1:
        _, dropped = _memos.popitem(last=False)
        total -= len(dropped)


def clear() -> None:
    with _lock:
        _memos.clear()
