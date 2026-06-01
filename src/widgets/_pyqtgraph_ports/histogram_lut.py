"""
Histogram + LUT level-line state — pure state.

Distilled from pyqtgraph's ``HistogramLUTItem``
(``pyqtgraph/graphicsItems/HistogramLUTItem.py`` at commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). The upstream
class bundles three things:

1. A histogram of the image's intensities.
2. A draggable region (LinearRegionItem) for the display low/high.
3. A gradient editor for picking the colormap.

This port keeps just the state — TRANS already has a
``LinearRegionItem`` (Phase 6.1) the QML widget can drive for the
level lines, and the colormap picker is a QML combo. What's left on
the Python side is the histogram computation + a tiny ``HistogramState``
that round-trips through project save/load.

``compute_histogram`` mirrors upstream's pre-binning step but stays
NumPy-only (no ``ImageItem`` coupling). It handles the three dtypes
TRANS sees and the NaN-laden float case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np


@dataclass
class HistogramState:
    """JSON-serialisable state for the histogram-driven level
    picker."""

    display_min: float = 0.0
    display_max: float = 1.0
    colormap: str = "original"
    n_bins: int = 256

    def get_state(self) -> Dict[str, Any]:
        return {
            "display_min": float(self.display_min),
            "display_max": float(self.display_max),
            "colormap": self.colormap,
            "n_bins": int(self.n_bins),
        }

    @staticmethod
    def from_state(state: Dict[str, Any]) -> "HistogramState":
        out = HistogramState()
        out.apply_state(state)
        return out

    def apply_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        if isinstance(state.get("display_min"), (int, float)):
            self.display_min = float(state["display_min"])
        if isinstance(state.get("display_max"), (int, float)):
            self.display_max = float(state["display_max"])
        if isinstance(state.get("colormap"), str):
            self.colormap = state["colormap"]
        n_bins = state.get("n_bins")
        if isinstance(n_bins, int) and n_bins > 0:
            self.n_bins = n_bins

    def set_levels(self, lo: float, hi: float) -> bool:
        """Set ``(display_min, display_max)``. Returns ``True`` if the
        stored values changed."""
        lo = float(lo); hi = float(hi)
        if hi < lo:
            lo, hi = hi, lo
        if lo == self.display_min and hi == self.display_max:
            return False
        self.display_min = lo
        self.display_max = hi
        return True


def compute_histogram(
    array: np.ndarray,
    *,
    n_bins: int = 256,
    levels: Optional[Tuple[float, float]] = None,
    max_samples: Optional[int] = 1_000_000,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return ``(bin_centres, counts)`` for ``array``.

    Parameters
    ----------
    array
        2-D source array. NaN / inf samples are dropped.
    n_bins
        Number of bins. Default 256 — matches the LUT width so each
        bin maps cleanly to a colour.
    levels
        Optional ``(lo, hi)`` window. ``None`` uses the array's
        finite min/max. When ``lo == hi`` we widen by 0.5 on each
        side so the histogram still produces a usable axis.
    max_samples
        Down-sample large arrays before binning. None to disable.
        The default ``1_000_000`` keeps the call sub-millisecond on
        large maps while leaving statistical noise well below one
        pixel of histogram height for typical TRANS data.

    Returns
    -------
    ``(bin_centres, counts)`` — both 1-D NumPy arrays of length
    ``n_bins``.
    """
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    if array.size == 0:
        empty = np.zeros(n_bins, dtype=np.int64)
        centres = np.linspace(0.0, 1.0, n_bins)
        return centres, empty

    flat = array.ravel()
    if flat.dtype.kind == "f":
        finite_mask = np.isfinite(flat)
        if not finite_mask.all():
            flat = flat[finite_mask]
    if flat.size == 0:
        empty = np.zeros(n_bins, dtype=np.int64)
        centres = np.linspace(0.0, 1.0, n_bins)
        return centres, empty

    if max_samples is not None and flat.size > max_samples:
        # Stride sample so the picked subset is spatially well-mixed
        # rather than concentrated in the top rows.
        stride = max(1, flat.size // max_samples)
        flat = flat[::stride]

    if levels is not None:
        lo, hi = float(levels[0]), float(levels[1])
    else:
        lo, hi = float(flat.min()), float(flat.max())
    if hi <= lo:
        hi = lo + 0.5
        lo = lo - 0.5

    counts, edges = np.histogram(flat, bins=n_bins, range=(lo, hi))
    centres = (edges[:-1] + edges[1:]) * 0.5
    return centres, counts.astype(np.int64, copy=False)
