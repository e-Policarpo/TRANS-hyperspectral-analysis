"""Surface-leveling operations for SPM maps and images.

Two background-removal tools common in scanning-probe analysis:

* :func:`polynomial_level` — fit a 2-D polynomial to the whole frame and
  subtract it. Order 1 is an ordinary least-squares plane; higher orders remove
  gentle bowing / scanner creep. This is *mean*-plane removal — every pixel
  contributes to the fit.

* :func:`facet_level` — reorient the surface so its **dominant facet** becomes
  horizontal. Instead of an average plane it finds the most common local
  surface slope (the peak of the facet-normal distribution) and subtracts that,
  so a flat terrace stays flat even when steps, adsorbates or spikes would drag
  a mean-plane fit off true. Iterates to convergence.

Both are NaN-aware (non-finite pixels are ignored in the fit and preserved in
the output) and return a new array; the input is never mutated.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from typing import Optional

import numpy as np


def polynomial_level(data: np.ndarray, order: int = 2) -> np.ndarray:
    """Subtract a fitted 2-D polynomial background of the given ``order``.

    ``order=1`` is a least-squares plane; ``order=0`` just removes the mean.
    Coordinates are normalised to ``[-1, 1]`` before fitting so high orders stay
    numerically well-conditioned. Returns ``data`` unchanged if there are fewer
    finite samples than polynomial coefficients.
    """
    z = np.asarray(data, dtype=np.float64)
    if z.ndim != 2:
        raise ValueError(f"Expected a 2-D array, got {z.ndim}-D")
    order = max(0, int(order))
    rows, cols = z.shape
    Y, X = np.mgrid[0:rows, 0:cols].astype(np.float64)
    xn = (X / (cols - 1) * 2.0 - 1.0) if cols > 1 else np.zeros_like(X)
    yn = (Y / (rows - 1) * 2.0 - 1.0) if rows > 1 else np.zeros_like(Y)

    terms = [(xn ** i) * (yn ** j)
             for i in range(order + 1)
             for j in range(order + 1 - i)]
    A = np.column_stack([t.ravel() for t in terms])

    zf = z.ravel()
    finite = np.isfinite(zf)
    if int(finite.sum()) < A.shape[1]:
        return z.copy()
    coeffs, *_ = np.linalg.lstsq(A[finite], zf[finite], rcond=None)
    background = (A @ coeffs).reshape(z.shape)
    return z - background


def facet_level(data: np.ndarray, iterations: int = 6,
                hist_bins: int = 200, smooth: float = 2.0,
                clip_percentile: float = 90.0) -> np.ndarray:
    """Level ``data`` so its dominant facet is horizontal (facet reorientation).

    Each iteration estimates the most common local slope from the peak of the
    2-D histogram of per-pixel gradients (the facet-normal distribution) and
    subtracts that plane, repeating until the correction becomes negligible.
    Robust to steps and outliers, which a mean-plane fit would chase.

    Parameters
    ----------
    iterations:
        Maximum refinement passes.
    hist_bins:
        Resolution of the gradient histogram per axis.
    smooth:
        Gaussian smoothing (in bins) of the histogram before peak-picking;
        stabilises the mode on noisy data. ``0`` disables it.
    clip_percentile:
        Gradient histogram spans ``±`` this percentile of ``|gradient|``, so a
        few steep step edges don't stretch the range and blur the facet peak.
    """
    z = np.array(data, dtype=np.float64)
    if z.ndim != 2:
        raise ValueError(f"Expected a 2-D array, got {z.ndim}-D")
    rows, cols = z.shape
    if rows < 2 or cols < 2:
        return z
    Y, X = np.mgrid[0:rows, 0:cols].astype(np.float64)

    smoother = None
    if smooth and smooth > 0:
        try:
            from scipy.ndimage import gaussian_filter as smoother  # noqa: N813
        except Exception:
            smoother = None

    for _ in range(max(1, int(iterations))):
        gy, gx = np.gradient(z)             # dz/drow, dz/dcol
        m = np.isfinite(gx) & np.isfinite(gy)
        gxv, gyv = gx[m], gy[m]
        if gxv.size < 4:
            break
        rx = np.percentile(np.abs(gxv), clip_percentile)
        ry = np.percentile(np.abs(gyv), clip_percentile)
        rx = rx if rx > 0 else (np.max(np.abs(gxv)) or 1e-12)
        ry = ry if ry > 0 else (np.max(np.abs(gyv)) or 1e-12)
        H, xe, ye = np.histogram2d(gxv, gyv, bins=hist_bins,
                                   range=[[-rx, rx], [-ry, ry]])
        if smoother is not None:
            H = smoother(H, smooth)
        pi, pj = np.unravel_index(int(np.argmax(H)), H.shape)
        a = 0.5 * (xe[pi] + xe[pi + 1])    # dominant dz/dcol
        b = 0.5 * (ye[pj] + ye[pj + 1])    # dominant dz/drow
        if not (np.isfinite(a) and np.isfinite(b)):
            break
        z = z - (a * X + b * Y)
        # Converged: the dominant facet is within one histogram bin of flat.
        if abs(a) <= (xe[1] - xe[0]) and abs(b) <= (ye[1] - ye[0]):
            break

    if np.isfinite(z).any():
        z = z - np.nanmedian(z)
    return z


# Operation-name → callable, shared by the map editor and image viewer so both
# expose identical leveling. ``params`` keys are operation-specific.
def apply_leveling(operation: str, data: np.ndarray, params: Optional[dict] = None
                   ) -> np.ndarray:
    """Dispatch a named leveling ``operation`` over ``data``.

    Known operations: ``plane_level`` (order-1 polynomial), ``poly_level``
    (``order`` param, default 2), ``facet_level``. Raises ``KeyError`` for an
    unknown name.
    """
    params = params or {}
    if operation == 'plane_level':
        return polynomial_level(data, order=1)
    if operation in ('poly_level', 'polynomial_bg_removal'):
        return polynomial_level(data, order=int(params.get('order', 2)))
    if operation == 'facet_level':
        return facet_level(
            data,
            iterations=int(params.get('iterations', 6)),
        )
    raise KeyError(operation)
