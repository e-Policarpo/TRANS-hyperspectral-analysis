"""
Convert ``(x, y)`` arrays into a ``QPainterPath`` for fast curve
rendering, plus log-scale gating and downsampling helpers.

Pure-Python port of the parts of
``pyqtgraph/graphicsItems/PlotCurveItem.py::generatePath`` and
``pyqtgraph/functions.py::arrayToQPath`` /
``_arrayToQPath_finite`` that TRANS needs for the native renderer.

The full pyqtgraph version reaches into Qt's binary path format with
a ``QDataStream`` for the absolute fastest path build; this port uses
the supported ``QPainterPath.moveTo`` / ``lineTo`` API which is plenty
fast at TRANS's typical curve sizes (1k–10k points). The hot path on
interaction is ``QPainter.setTransform`` + ``drawPath``; building the
path is one-shot per curve.

Upstream: https://github.com/pyqtgraph/pyqtgraph @ d588dd3
Originally: pyqtgraph, MIT-licensed (see ``LICENSE`` in this package).
"""

from __future__ import annotations

import struct
from typing import Optional, Tuple

import numpy as np

from PySide6.QtCore import QByteArray, QDataStream
from PySide6.QtGui import QPainterPath


# Above this point count the path build switches to chunked
# ``addPath`` so very long curves don't blow Qt's internal
# vertex buffer.
_CHUNK_SIZE = 10_000


def array_to_qpainterpath(
    x: np.ndarray,
    y: np.ndarray,
) -> QPainterPath:
    """Build a ``QPainterPath`` from ``x`` and ``y``.

    The path is constructed in **data coordinates** — the caller
    applies a ``QTransform`` to map data → pixels at paint time so
    zoom and pan don't trigger a path rebuild.

    NaN samples in either array split the path: the segment ending
    just before the NaN is closed and the next segment starts at the
    next finite sample.

    For performance, the path is built via Qt's internal binary
    ``QDataStream`` representation rather than per-vertex ``moveTo`` /
    ``lineTo`` calls. The format is documented in pyqtgraph's
    ``arrayToQPath`` (originally inferred from
    ``qtbase/src/gui/painting/qpainterpath.cpp``) and is roughly:

    .. code-block:
        numVerts(i4)
        connect(i4)  x(f8)  y(f8)      # one per vertex
        ...
        cStart(i4)  fillRule(i4)        # trailer

    All values big-endian. ``connect=0`` means ``MoveTo`` (start a new
    subpath); ``connect=1`` means ``LineTo``. We use that to break the
    path at NaN runs cheaply.
    """
    if len(x) != len(y):
        raise ValueError(
            f"x and y must be the same length; got {len(x)} and {len(y)}"
        )
    n = len(x)
    if n < 2:
        return QPainterPath()

    x = np.ascontiguousarray(x, dtype=np.float64)
    y = np.ascontiguousarray(y, dtype=np.float64)

    isfinite = np.isfinite(x) & np.isfinite(y)
    finite_count = int(isfinite.sum())
    if finite_count < 2:
        return QPainterPath()

    if finite_count == n:
        # All-finite fast path: every vertex contributes; only the
        # first has connect=0.
        finite_idx = None
    else:
        # Filter to finite vertices only; reset ``connect=0`` at every
        # discontinuity in the original index.
        finite_idx = np.flatnonzero(isfinite)

    return _build_path_via_datastream(x, y, finite_idx)


def _build_path_via_datastream(
    x: np.ndarray,
    y: np.ndarray,
    finite_idx: Optional[np.ndarray],
) -> QPainterPath:
    """Build a ``QPainterPath`` from the binary stream Qt expects.

    When ``finite_idx`` is ``None`` every sample is kept; otherwise we
    only emit vertices at those positions and break the path
    (``connect=0``) whenever the gap between consecutive original
    indices is > 1.
    """
    if finite_idx is None:
        n = len(x)
        x_use = x
        y_use = y
        connect = np.ones(n, dtype=">i4")
        connect[0] = 0
    else:
        n = len(finite_idx)
        x_use = x[finite_idx]
        y_use = y[finite_idx]
        connect = np.ones(n, dtype=">i4")
        connect[0] = 0
        # Break the path wherever the source index jumped (NaN gap).
        gaps = np.flatnonzero(np.diff(finite_idx) > 1)
        if gaps.size:
            connect[gaps + 1] = 0

    # Total buffer: i4 header + (i4 + f8 + f8) per vertex + 2*i4 trailer.
    buf = bytearray(4 + n * 20 + 8)
    struct.pack_into(">i", buf, 0, n)
    arr = np.frombuffer(
        buf,
        dtype=[("c", ">i4"), ("x", ">f8"), ("y", ">f8")],
        count=n, offset=4,
    )
    arr["c"] = connect
    arr["x"] = x_use
    arr["y"] = y_use
    # cStart=0, fillRule=Qt::OddEvenFill (0).
    struct.pack_into(">ii", buf, 4 + n * 20, 0, 0)

    path = QPainterPath()
    ba = QByteArray(bytes(buf))
    ds = QDataStream(ba)
    ds >> path
    return path


def apply_log_scale(
    data: np.ndarray, *, log: bool,
) -> np.ndarray:
    """Return ``log10(data)`` with non-positive samples NaN-masked.

    Matplotlib silently masks ``<= 0`` samples in log mode; pyqtgraph's
    ``np.log10`` would inject ``-inf`` / ``NaN`` into the path. Mask
    first, then log: the path builder above splits at the NaNs so the
    curve breaks at the masked samples instead of producing a gap
    that's silently filled with garbage values.

    When ``log=False`` the array is returned unchanged (with a copy
    converted to float64 so the caller can mutate freely).
    """
    out = np.asarray(data, dtype=np.float64)
    if not log:
        return out.copy()
    masked = np.where(out > 0, out, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log10(masked)


# Downsampling modes — match pyqtgraph's setDownsampling(method=...)
# semantics; only the modes TRANS actually needs are implemented.
DOWNSAMPLE_SUBSAMPLE = "subsample"   # take every Nth point (fastest)
DOWNSAMPLE_MEAN = "mean"             # average in N-wide blocks
DOWNSAMPLE_PEAK = "peak"             # min + max in N-wide blocks


def downsample(
    x: np.ndarray, y: np.ndarray,
    *,
    target_n: int,
    mode: str = DOWNSAMPLE_PEAK,
) -> Tuple[np.ndarray, np.ndarray]:
    """Reduce ``(x, y)`` to roughly ``target_n`` samples.

    Returns ``(x, y)`` unchanged when ``len(x) <= target_n`` or
    ``target_n <= 0``. Otherwise picks a stride and applies the
    requested ``mode``:

    - ``"subsample"`` — every Nth sample. Fastest but loses sharp
      features when the stride straddles a peak.
    - ``"mean"`` — block-averages. Smooth, lossy on noise.
    - ``"peak"`` — alternating block-min and block-max samples (so the
      reduced curve always touches the local extremes). The default
      because Raman/PL/STS spectra are mostly flat with sharp peaks
      and the peak mode preserves them visually even at ~30× downsample.
    """
    n = len(x)
    if target_n <= 0 or n <= target_n or n < 2:
        return x, y
    stride = max(1, int(np.ceil(n / target_n)))
    if stride == 1:
        return x, y

    if mode == DOWNSAMPLE_SUBSAMPLE:
        return x[::stride], y[::stride]

    # Truncate to a length divisible by the stride so the reshape
    # below works without an awkward remainder.
    trim = (n // stride) * stride
    xt = x[:trim].reshape(-1, stride)
    yt = y[:trim].reshape(-1, stride)

    if mode == DOWNSAMPLE_MEAN:
        return xt.mean(axis=1), yt.mean(axis=1)

    if mode == DOWNSAMPLE_PEAK:
        # Each block contributes two samples (its min and its max) so
        # the reduced curve traces the actual envelope. The min/max
        # alternate at the same x-position pair (block centre) — that
        # keeps the visual shape while halving the number of distinct
        # x-positions.
        x_centres = xt.mean(axis=1)
        # Interleave x_centres with itself so each block has two
        # rendered samples that share an x but alternate min / max.
        x_out = np.repeat(x_centres, 2)
        y_min = yt.min(axis=1)
        y_max = yt.max(axis=1)
        y_out = np.empty_like(x_out)
        y_out[0::2] = y_min
        y_out[1::2] = y_max
        return x_out, y_out

    raise ValueError(
        f"unknown downsample mode {mode!r}; "
        f"expected {DOWNSAMPLE_SUBSAMPLE}, {DOWNSAMPLE_MEAN}, "
        f"or {DOWNSAMPLE_PEAK}"
    )


def prepare_curve_xy(
    x: np.ndarray,
    y: np.ndarray,
    *,
    log_x: bool = False,
    log_y: bool = False,
    max_points: Optional[int] = None,
    downsample_mode: str = DOWNSAMPLE_PEAK,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run the full pre-render pipeline on ``(x, y)``.

    Composition of :func:`apply_log_scale` (per axis) and
    :func:`downsample` so call sites stay short. The returned arrays
    are float64 in *post-log* coordinates — pass them straight to
    :func:`array_to_qpainterpath`.
    """
    x_p = apply_log_scale(x, log=log_x)
    y_p = apply_log_scale(y, log=log_y)
    if max_points is not None and max_points > 0:
        x_p, y_p = downsample(
            x_p, y_p, target_n=max_points, mode=downsample_mode,
        )
    return x_p, y_p
