"""
Negative LDOS is not a measurement.

A dI/dV curve is proportional to the local density of states, and a density
of states cannot be negative. Where a corrected spectrum dips below zero it
is noise, or a background that was subtracted a little too hard — never
signal. Two things must therefore not let it in:

* **Model fits.** A polynomial fitted through the band edges, or a peak
  fitted to a state, should be fitted to the measurement, not to the part of
  the curve that is an artefact of the correction. Negative samples pull the
  fit down at exactly the places where the curve is weakest.
* **Integrals.** Integrating a signed curve lets a negative excursion cancel
  real spectral weight somewhere else in the same interval, so a map cell can
  come out small because the noise happened to be two-sided rather than
  because there is nothing there.

Both are handled here so the rule is stated once.

**This does not apply to background fitting.** arPLS, ALS and ModPoly work by
*sitting below* the data; dropping the samples underneath them biases the
baseline upward and breaks the very asymmetry they are built on. Those
functions in :mod:`src.processing.peak_detection` deliberately see the whole
curve, negatives included.

**Nor does it apply to signed quantities.** Current in an I(V) sweep is
genuinely negative at negative bias, and so is a differentiated or
difference spectrum. Every entry point here is opt-in at the call site for
that reason.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

__all__ = ["positive_mask", "positive_part", "positive_integral"]


def positive_mask(y: np.ndarray) -> np.ndarray:
    """Samples a fit may use: finite, and not negative.

    Zero is kept — it is a real reading of "no states here", and dropping it
    would bias a fit through a gap interior upward.
    """
    y = np.asarray(y, dtype=np.float64)
    return np.isfinite(y) & (y >= 0.0)


def positive_part(y: np.ndarray) -> np.ndarray:
    """``max(y, 0)`` with NaN read as zero rather than propagating."""
    y = np.asarray(y, dtype=np.float64)
    return np.maximum(np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0), 0.0)


def positive_integral(y: np.ndarray, x: np.ndarray, axis: int = 0) -> np.ndarray:
    """Trapezoidal integral of the positive part of ``y``.

    This is the area of the regions where the curve is above zero, which is
    not the same thing as the trapezoidal integral of ``max(y, 0)``: on a
    segment that crosses zero, clipping first moves the crossing to the
    segment end and over-counts the little triangle beyond it. The crossing
    is solved for instead, so a curve that is half positive contributes
    exactly its positive half however coarse the bias grid is.

    ``x`` is the sample positions along ``axis`` (need not be evenly spaced).
    NaN samples are read as zero, matching the rest of the integration path:
    one railed point must not wipe out a whole spectrum's integral.
    """
    y = np.asarray(y, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    if y.shape[axis] != x.size:
        raise ValueError(
            f"x has {x.size} samples but y has {y.shape[axis]} along axis {axis}")
    if x.size < 2:
        return np.zeros(np.delete(y.shape, axis), dtype=np.float64)

    y = np.moveaxis(np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0), axis, 0)

    lo, hi = y[:-1], y[1:]
    width = np.diff(x).reshape((-1,) + (1,) * (y.ndim - 1))

    lo_pos = np.maximum(lo, 0.0)
    hi_pos = np.maximum(hi, 0.0)
    both_up = (lo >= 0.0) & (hi >= 0.0)

    # Only on a crossing segment is exactly one endpoint positive, so
    # lo_pos**2 + hi_pos**2 is that endpoint squared and the triangle is
    # half its height times the fraction of the segment it spans.
    span = np.abs(lo - hi)
    safe = np.where(span > 0.0, span, 1.0)
    crossing = 0.5 * width * (lo_pos ** 2 + hi_pos ** 2) / safe

    area = np.where(both_up, 0.5 * width * (lo + hi), crossing)
    # A segment with both ends at or below zero contributes nothing; the
    # crossing branch already gives 0 there, but not when span == 0.
    area = np.where((lo <= 0.0) & (hi <= 0.0), 0.0, area)
    return np.moveaxis(area.sum(axis=0), 0, axis) if area.ndim > 1 else area.sum(axis=0)
