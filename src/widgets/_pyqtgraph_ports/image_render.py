"""
Image levels + LUT + downsampling — pure NumPy ports.

Distilled from pyqtgraph's ``ImageItem.render`` (the levels + LUT
branch) and ``functions.makeARGB`` (commit
``d588dd3ec30915e61c8496a0fe1db21fc25e4da5``, MIT). The QGraphicsScene
machinery is left behind; these are plain array transforms the host
canvas calls before building a ``QImage``.

Three primitives:

- ``apply_levels_and_lut(array, levels, lut)`` — clip ``array`` to
  ``levels = (lo, hi)``, rescale into 0..255, index a ``(256, 3)``
  ``uint8`` LUT, and return ``H × W × 3`` ``uint8``. Accepts the
  three input dtypes TRANS sees: ``uint8``, ``uint16``, ``float32``.
  ``levels=None`` means "min/max of the array" (computed once per
  call, no caching).
- ``downsample_image(array, target_size, mode='mean')`` — mean-pool
  a 2-D array down to ``(H', W')`` where ``H' <= target_size[1]``
  and ``W' <= target_size[0]`` (note the ``(w, h)`` order — that's
  what every existing caller passes). The result preserves overall
  intensity (mean-pool, not subsample) so large maps zoomed out
  don't develop moiré artifacts.
- ``levels_from_array(array, *, ignore_nan=True)`` — convenience for
  the histogram widget: returns ``(min, max)`` over the finite
  samples.

No QImage construction here — that stays in the canvas, since it's
the layer that knows ``Format_Grayscale8`` vs ``Format_RGB888`` and
holds the array alive past the ``QImage`` returns.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def apply_levels_and_lut(
    array: np.ndarray,
    levels: Optional[Tuple[float, float]],
    lut: np.ndarray,
) -> np.ndarray:
    """Rescale ``array`` to 0..255 via ``levels``, then look up RGB.

    Parameters
    ----------
    array
        2-D ``(H, W)`` array. Any of ``uint8`` / ``uint16`` /
        ``float32`` / ``float64`` works. NaN samples are clipped to
        the low end of the levels window.
    levels
        ``(lo, hi)`` clip window. ``None`` means use the array's
        finite min / max — no caching, so callers that hit this
        path repeatedly should pass an explicit ``levels`` instead.
    lut
        ``(256, 3)`` ``uint8`` LUT (the shape returned by
        ``src.widgets.lut.get_lut``).

    Returns
    -------
    ``H × W × 3`` ``uint8`` contiguous array.
    """
    if array.ndim != 2:
        raise ValueError(
            f"apply_levels_and_lut requires a 2-D array, got shape {array.shape}",
        )
    if lut.shape != (256, 3) or lut.dtype != np.uint8:
        raise ValueError(
            "lut must be a (256, 3) uint8 array, "
            f"got shape={lut.shape}, dtype={lut.dtype}",
        )

    lo_hi = _resolve_levels(array, levels)
    idx = _to_uint8_indices(array, lo_hi)
    out = lut[idx]
    return np.ascontiguousarray(out)


def downsample_image(
    array: np.ndarray,
    target_size: Tuple[int, int],
    *,
    mode: str = "mean",
) -> np.ndarray:
    """Mean-pool a 2-D array down so it fits within ``target_size``.

    Parameters
    ----------
    array
        2-D source array. Any numeric dtype.
    target_size
        ``(target_width, target_height)`` in pixels. Both axes are
        treated independently — the output is at most
        ``target_size`` along each axis, with the pool stride chosen
        as ``ceil(source_axis / target_axis)``.
    mode
        ``"mean"`` (default) or ``"subsample"``. Subsample skips every
        ``stride`` samples — faster, but introduces moiré on bands or
        gratings. Use ``"mean"`` for display, ``"subsample"`` only
        when the caller has already coarsened the data.

    Returns
    -------
    Downsampled 2-D array. If no axis needs downsampling (both
    sides smaller than the target), returns the input unchanged.
    """
    if array.ndim != 2:
        raise ValueError(
            f"downsample_image requires a 2-D array, got shape {array.shape}",
        )
    if mode not in ("mean", "subsample"):
        raise ValueError(f"mode must be 'mean' or 'subsample', got {mode!r}")
    tw, th = int(target_size[0]), int(target_size[1])
    if tw <= 0 or th <= 0:
        return array

    src_h, src_w = array.shape
    stride_w = max(1, _ceil_div(src_w, tw))
    stride_h = max(1, _ceil_div(src_h, th))
    if stride_w == 1 and stride_h == 1:
        return array

    if mode == "subsample":
        return array[::stride_h, ::stride_w]

    # Mean-pool. We crop the source to a multiple of the stride so
    # the reshape-and-mean stays vectorised; the trailing partial
    # block (if any) is folded into the last full block above.
    trim_h = (src_h // stride_h) * stride_h
    trim_w = (src_w // stride_w) * stride_w
    if trim_h == 0 or trim_w == 0:
        # Stride bigger than source — return a 1x1 mean.
        return np.array([[float(np.nanmean(array))]], dtype=array.dtype)
    trimmed = array[:trim_h, :trim_w]
    new_h = trim_h // stride_h
    new_w = trim_w // stride_w
    pooled = trimmed.reshape(new_h, stride_h, new_w, stride_w).mean(axis=(1, 3))
    return pooled.astype(array.dtype, copy=False)


def levels_from_array(
    array: np.ndarray,
    *,
    ignore_nan: bool = True,
) -> Tuple[float, float]:
    """Return the ``(min, max)`` over ``array``'s finite samples."""
    if ignore_nan:
        finite = array[np.isfinite(array)] if array.size else array
        if finite.size == 0:
            return 0.0, 1.0
        return float(finite.min()), float(finite.max())
    return float(array.min()), float(array.max())


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------

def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def _resolve_levels(
    array: np.ndarray,
    levels: Optional[Tuple[float, float]],
) -> Tuple[float, float]:
    if levels is not None:
        lo, hi = float(levels[0]), float(levels[1])
        if hi <= lo:
            hi = lo + 1.0
        return lo, hi
    return levels_from_array(array)


def _to_uint8_indices(
    array: np.ndarray,
    levels: Tuple[float, float],
) -> np.ndarray:
    """Map ``array`` through ``levels`` to ``uint8`` indices.

    Fast path: when ``array`` is already ``uint8`` and ``levels`` is
    ``(0, 255)``, the array IS the index. Otherwise we convert to
    ``float32`` once and run the standard ``(x - lo) / (hi - lo)``
    clip-and-scale pipeline.
    """
    lo, hi = levels
    if array.dtype == np.uint8 and lo == 0.0 and hi == 255.0:
        return np.ascontiguousarray(array)
    # Cast to float32 for the clip-and-scale — keeps memory low and
    # is plenty of precision for an 8-bit output.
    src = array.astype(np.float32, copy=False)
    span = float(hi - lo)
    normalised = (src - lo) / span
    # Replace NaN with 0 BEFORE the clip-and-cast so we don't get
    # ``invalid value encountered in cast`` from NumPy. The "clamp
    # NaN to low end" behaviour the docstring promises is what the
    # 0.0 fill produces (0 normalised → 0 in the LUT index).
    np.nan_to_num(normalised, nan=0.0, copy=False)
    np.clip(normalised, 0.0, 1.0, out=normalised)
    scaled = (normalised * 255.0).astype(np.uint8, copy=False)
    return np.ascontiguousarray(scaled)
