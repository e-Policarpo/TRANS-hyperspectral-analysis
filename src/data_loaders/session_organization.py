"""
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy

Shared session-organisation helpers for data loaders.

A measurement folder is rarely one experiment. It is a day's work: several
acquisition **sessions**, each with its own settings, taken minutes or hours
apart. The Omicron MATRIX loader has always modelled that — it discovers every
session in a directory, labels each one, and files its datasets, images and
maps into a per-session browser folder. This module is that model, factored
out so the other loaders can follow it instead of reimplementing it.

Three things make up the convention:

**Labels.** A session is named after when it was taken. The clock time is
dropped, because ``2026May06`` reads far better in a browser row and an
exported filename than ``2026May06-195231`` — but *only* while it stays
unambiguous. Two sessions on the same day both keep their times, because
otherwise they would merge into one folder and collide their dataset names.

**Filing.** A loader returns ``browser_folders`` mapping each entity
reference to its session label, and stamps ``session_label`` into the
metadata of anything the backend registers separately (images, maps, notes).
``AppBackend._group_label`` reads the latter; ``_on_file_loaded`` reads the
former.

**Per-spectrum provenance.** ``spectrum_meta`` is a list of dicts, one per
data column, each carrying at least ``column`` (the DataFrame column it
describes). Keying on the column name rather than on position is what lets it
survive both a meander correction, which reorders columns, and a tool that
keeps only a subset of them. Where the loader knows where a spectrum was
taken, ``location_m`` puts it on the sample in metres — which is what makes a
map come out in nanometres instead of point indices.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Hashable, List, Optional, Sequence, Tuple

from ..utils.naming import strip_acquisition_time

logger = logging.getLogger(__name__)

# Matches the Omicron MATRIX result-file convention (``2026Jun15-203637``), so
# every loader's session folders read the same way in the browser.
_DATE_FMT = "%Y%b%d"
_DATETIME_FMT = "%Y%b%d-%H%M%S"


def format_session_label(when: Optional[datetime], keep_time: bool = False,
                         fallback: str = "session") -> str:
    """Session label for an acquisition time.

    ``datetime(2026, 5, 6, 19, 52, 31)`` -> ``'2026May06'``, or
    ``'2026May06-195231'`` with ``keep_time``. Falls back to ``fallback`` for a
    session whose time could not be read.
    """
    if when is None:
        return fallback
    try:
        return when.strftime(_DATETIME_FMT if keep_time else _DATE_FMT)
    except (ValueError, AttributeError):      # pragma: no cover - defensive
        return fallback


def disambiguate_labels(keys: Sequence[Hashable],
                        short_of: Callable[[Any], str],
                        full_of: Callable[[Any], str]) -> Dict[Hashable, str]:
    """Map each session key to the shortest label that stays unique.

    ``short_of`` gives the preferred, human-friendly label (no clock time);
    ``full_of`` gives the unambiguous one. A key whose short label is shared
    with another key gets the full form — and if even that collides, a numeric
    suffix, so the result is unique by construction. Callers rely on that:
    two sessions sharing a label would merge into one browser folder and
    overwrite each other's datasets.
    """
    short = {key: short_of(key) for key in keys}
    counts: Dict[str, int] = {}
    for label in short.values():
        counts[label] = counts.get(label, 0) + 1

    out: Dict[Hashable, str] = {}
    used: Dict[str, int] = {}
    for key in keys:
        label = short[key] if counts[short[key]] == 1 else full_of(key)
        if label in used:
            used[label] += 1
            label = f"{label}_{used[label]}"
        else:
            used[label] = 1
        out[key] = label
    return out


def session_labels_from_times(times: Sequence[Optional[datetime]],
                              fallback: str = "session") -> List[str]:
    """Labels for a list of acquisition times, in the same order.

    The common case of :func:`disambiguate_labels`: sessions identified purely
    by when they were taken.
    """
    indices = list(range(len(times)))
    mapping = disambiguate_labels(
        indices,
        lambda i: format_session_label(times[i], False, fallback),
        lambda i: format_session_label(times[i], True, fallback),
    )
    return [mapping[i] for i in indices]


def grid_positions_m(geometry: Optional[Dict[str, Any]], count: int
                     ) -> Optional[List[Tuple[float, float]]]:
    """Sample positions in metres for a rectangular grid of spectra.

    ``geometry`` is the loader's parsed map rectangle — ``x_start``, ``y_start``,
    ``x_end``, ``y_end`` in metres plus ``nx``/``ny``. Positions come back in
    **row-major order** (row 0 left to right, then row 1), which is the order a
    dataset's columns are in *after* a meander correction, not the order the
    instrument visited them in. Callers that have not corrected for the
    meander must not use this.

    Returns None when the geometry is missing, degenerate, or does not describe
    ``count`` points — an honest "unknown" beats an invented scale.
    """
    if not geometry or count <= 0:
        return None
    try:
        nx = int(geometry['nx'])
        ny = int(geometry['ny'])
        x0 = float(geometry['x_start'])
        y0 = float(geometry['y_start'])
        x1 = float(geometry['x_end'])
        y1 = float(geometry['y_end'])
    except (KeyError, TypeError, ValueError):
        return None
    if nx <= 0 or ny <= 0 or nx * ny != count:
        return None

    def _axis(start: float, end: float, n: int) -> List[float]:
        # A grid of n samples spans the rectangle end to end; a single sample
        # sits at its centre rather than at one edge.
        if n == 1:
            return [(start + end) / 2.0]
        step = (end - start) / (n - 1)
        return [start + i * step for i in range(n)]

    xs = _axis(x0, x1, nx)
    ys = _axis(y0, y1, ny)
    return [(xs[col], ys[row]) for row in range(ny) for col in range(nx)]


def spatial_info(spectrum_meta: Optional[List[dict]] = None,
                 positions_m: Optional[Sequence[Tuple[float, float]]] = None,
                 layout: Optional[str] = None) -> Dict[str, Any]:
    """The spatial ``additional_info`` keys, omitting whatever is unknown.

    Kept in one place so every loader spells them the same way as the tools
    that carry them across (``ToolImplementations._carry_spatial_info``).
    """
    info: Dict[str, Any] = {}
    if spectrum_meta:
        info['spectrum_meta'] = spectrum_meta
    if positions_m:
        info['position_m'] = [list(p) for p in positions_m]
    if layout:
        info['spatial_layout'] = layout
    return info
