"""
Multi-peak Gaussian / Lorentzian / pseudo-Voigt fitting.

Spectroscopy data (PL, Raman, STS dI/dV) frequently consists of a smooth
baseline (instrument response, scattered light, fluorescence) plus a sum
of overlapping peaks. The user interface for fitting needs to cover

- Multiple peaks at unknown positions (peak detection),
- A choice of line shape (Gaussian / Lorentzian / pseudo-Voigt),
- A polynomial baseline fitted simultaneously, and
- Residuals + per-peak components for diagnostic plotting.

This module is a pure-numpy / scipy utility — no Qt, no app-state coupling
— so it can be unit-tested in isolation. The :class:`AppBackend` exposes
it via a single :meth:`multiPeakFit` slot.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import least_squares

from src.processing.positivity import positive_mask
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API: shapes, results, and entry points
# ---------------------------------------------------------------------------

class PeakShape(str, Enum):
    """Parametric line shape for a single peak.

    Each shape is fully parameterized by ``(amplitude, center, width)`` plus,
    for pseudo-Voigt, an additional ``eta`` ∈ [0, 1] mixing factor.
    """
    GAUSSIAN = "gaussian"
    LORENTZIAN = "lorentzian"
    PSEUDO_VOIGT = "pseudo_voigt"


@dataclass
class FittedPeak:
    """One peak in a multi-peak fit result."""
    shape: PeakShape
    amplitude: float
    center: float
    width: float                      # σ for Gaussian; γ (HWHM) for Lorentzian / pV
    eta: Optional[float] = None       # pseudo-Voigt mixing factor (None for G/L)

    @property
    def fwhm(self) -> float:
        """Full-width at half-maximum derived from the line-shape ``width``."""
        if self.shape == PeakShape.GAUSSIAN:
            return 2.0 * np.sqrt(2.0 * np.log(2.0)) * self.width
        # Lorentzian and pseudo-Voigt use γ = HWHM by convention here.
        return 2.0 * self.width

    def evaluate(self, x: np.ndarray) -> np.ndarray:
        """Compute this peak's contribution at ``x``."""
        return _eval_peak(x, self.shape, self.amplitude,
                          self.center, self.width, self.eta or 0.5)


@dataclass
class MultiPeakFitResult:
    """Bundle of everything a caller might want from one fit."""
    x: np.ndarray
    y: np.ndarray                              # original data
    peaks: List[FittedPeak]
    baseline_coeffs: np.ndarray                # highest-order first (np.polyval order)
    fitted_curve: np.ndarray                   # baseline + Σ peaks at x
    baseline_curve: np.ndarray                 # baseline at x
    components: List[np.ndarray] = field(default_factory=list)  # one curve per peak
    residuals: Optional[np.ndarray] = None
    rss: float = 0.0                           # residual sum of squares
    rsq: float = 0.0                           # coefficient of determination
    success: bool = True
    message: str = ""


# ---------------------------------------------------------------------------
# Line-shape primitives
# ---------------------------------------------------------------------------

def gaussian(x, amplitude, center, sigma):
    """Standard Gaussian line shape with peak height = ``amplitude``."""
    return amplitude * np.exp(-0.5 * ((x - center) / max(sigma, 1e-12)) ** 2)


def lorentzian(x, amplitude, center, gamma):
    """Lorentzian line shape (HWHM = ``gamma``) with peak height = ``amplitude``."""
    return amplitude * (gamma * gamma) / ((x - center) ** 2 + gamma * gamma)


def pseudo_voigt(x, amplitude, center, gamma, eta):
    """Linear-combination pseudo-Voigt: ``eta·Lorentz + (1−eta)·Gauss``.

    ``gamma`` is interpreted as the HWHM of both components, which is the
    standard choice for the linear-combination form.
    """
    eta = float(np.clip(eta, 0.0, 1.0))
    sigma = gamma / np.sqrt(2.0 * np.log(2.0))
    return (
        eta * lorentzian(x, amplitude, center, gamma)
        + (1.0 - eta) * gaussian(x, amplitude, center, sigma)
    )


def _eval_peak(x, shape: PeakShape, amplitude, center, width, eta=0.5):
    if shape == PeakShape.GAUSSIAN:
        return gaussian(x, amplitude, center, width)
    if shape == PeakShape.LORENTZIAN:
        return lorentzian(x, amplitude, center, width)
    if shape == PeakShape.PSEUDO_VOIGT:
        return pseudo_voigt(x, amplitude, center, width, eta)
    raise ValueError(f"Unknown peak shape: {shape}")


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------

_DEFAULT_AUTO_PEAK_CAP = 10  # safety cap when callers ask for "all peaks"


def estimate_noise_sigma(y: np.ndarray) -> float:
    """Estimate the noise σ of a 1-D spectrum from MAD of first differences.

    The median absolute deviation of ``diff(y)`` is robust to outliers and
    smooth structure (slow trends contribute negligibly to a single-step
    difference). 1.4826 converts MAD → σ for Gaussian noise; the √2 corrects
    for taking the difference of two independent samples.

    Returns ``0.0`` for arrays with fewer than two samples.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size < 2:
        return 0.0
    diffs = np.diff(y)
    mad = float(np.median(np.abs(diffs - np.median(diffs))))
    return 1.4826 * mad / np.sqrt(2.0)


def adaptive_prominence(y: np.ndarray, *, span_fraction: float = 0.05,
                        noise_sigmas: float = 3.0) -> float:
    """Compute an adaptive peak-prominence threshold for a 1-D spectrum.

    Returns ``max(span_fraction × (max−min), noise_sigmas × σ_noise)`` so the
    same threshold protects flat / noisy spectra (where the noise term
    dominates) and well-resolved spectra (where the span fraction dominates).
    Use this everywhere the user might otherwise have to hand-tune a
    prominence number per measurement.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size == 0:
        return 0.0
    span = float(np.max(y) - np.min(y))
    span_floor = span_fraction * span if span > 0 else 0.0
    noise_floor = noise_sigmas * estimate_noise_sigma(y)
    return max(span_floor, noise_floor)


def detect_peaks(
    x: np.ndarray,
    y: np.ndarray,
    *,
    prominence: Optional[float] = None,
    height: Optional[float] = None,
    distance: Optional[int] = None,
    n_max: Optional[int] = None,
) -> List[Tuple[float, float, float]]:
    """Detect local-maximum peaks via :func:`scipy.signal.find_peaks`.

    Returns a list of ``(center, height, width_x)`` tuples (sorted by
    descending prominence). ``width_x`` is in the units of ``x`` (FWHM at
    half-prominence, converted from sample units), giving callers a sensible
    seed for the line-shape ``width`` parameter.

    Parameters
    ----------
    prominence
        Minimum prominence required. Defaults to ``max(5 % of data span,
        3 × noise σ)`` where σ is estimated from the median absolute deviation
        of first differences. The noise floor prevents flat / noisy spectra
        from seeding the multi-peak fitter with dozens of spurious peaks.
    height
        Minimum absolute height. Defaults to baseline-subtracted threshold.
    distance
        Minimum sample spacing between detected peaks.
    n_max
        Cap the returned peak count (highest-prominence first). When ``None``,
        a default safety cap is applied so a noisy spectrum can't seed an
        unbounded fit.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.shape != y.shape or x.size < 5:
        return []

    if prominence is None:
        prominence = adaptive_prominence(y)

    if n_max is None:
        n_max = _DEFAULT_AUTO_PEAK_CAP

    indices, props = find_peaks(
        y, prominence=prominence, height=height,
        distance=distance, width=1,
    )
    if indices.size == 0:
        return []

    # Sort by prominence (highest first).
    order = np.argsort(-props["prominences"])
    indices = indices[order]
    proms = props["prominences"][order]
    widths_idx = props["widths"][order]
    if n_max is not None:
        indices = indices[:n_max]
        proms = proms[:n_max]
        widths_idx = widths_idx[:n_max]

    # Convert sample-index width → x-units width (FWHM half-prominence).
    dx = float(np.median(np.diff(x))) if x.size > 1 else 1.0
    out: List[Tuple[float, float, float]] = []
    for idx, w in zip(indices, widths_idx):
        out.append((float(x[idx]), float(y[idx]), float(w * abs(dx))))
    return out


# ---------------------------------------------------------------------------
# Multi-peak fit
# ---------------------------------------------------------------------------

def _pack_params(
    peaks: Sequence[Tuple[float, float, float]],
    shape: PeakShape,
    baseline_degree: int,
    baseline_coeffs0: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, int]:
    """Pack initial parameters: [peak0_amp, peak0_cen, peak0_wid, (eta), …, baseline]."""
    per_peak = 4 if shape == PeakShape.PSEUDO_VOIGT else 3
    n_peaks = len(peaks)
    p = np.empty(n_peaks * per_peak + (baseline_degree + 1), dtype=np.float64)
    for i, (cen, amp, wid) in enumerate(peaks):
        base = i * per_peak
        p[base] = amp
        p[base + 1] = cen
        p[base + 2] = max(wid, 1e-9)
        if shape == PeakShape.PSEUDO_VOIGT:
            p[base + 3] = 0.5
    if baseline_coeffs0 is None:
        p[n_peaks * per_peak:] = 0.0
    else:
        # np.polyval expects highest-degree first
        p[n_peaks * per_peak:] = baseline_coeffs0
    return p, per_peak


def _unpack_params(
    p: np.ndarray, n_peaks: int, shape: PeakShape, baseline_degree: int,
) -> Tuple[List[FittedPeak], np.ndarray]:
    per_peak = 4 if shape == PeakShape.PSEUDO_VOIGT else 3
    peaks: List[FittedPeak] = []
    for i in range(n_peaks):
        base = i * per_peak
        amp, cen, wid = p[base], p[base + 1], p[base + 2]
        eta = p[base + 3] if shape == PeakShape.PSEUDO_VOIGT else None
        peaks.append(FittedPeak(
            shape=shape, amplitude=float(amp),
            center=float(cen), width=float(abs(wid)),
            eta=float(np.clip(eta, 0.0, 1.0)) if eta is not None else None,
        ))
    base_coeffs = p[n_peaks * per_peak:]
    return peaks, base_coeffs


def _model(p, x, n_peaks, shape, baseline_degree):
    peaks, base = _unpack_params(p, n_peaks, shape, baseline_degree)
    y = np.polyval(base, x) if base.size else np.zeros_like(x)
    for peak in peaks:
        y = y + peak.evaluate(x)
    return y


def fit_multipeak(
    x: np.ndarray,
    y: np.ndarray,
    *,
    initial_peaks: Optional[Sequence[Tuple[float, float, float]]] = None,
    shape: PeakShape = PeakShape.GAUSSIAN,
    baseline_degree: int = 1,
    n_peaks_auto: Optional[int] = None,
    auto_prominence: Optional[float] = None,
    max_nfev: int = 4000,
    positive_only: bool = True,
) -> MultiPeakFitResult:
    """Fit a sum of peaks plus a polynomial baseline to ``y(x)``.

    Parameters
    ----------
    x, y
        Input data arrays (1-D, equal length).
    initial_peaks
        Sequence of ``(center, height, width)`` tuples to seed the optimizer.
        When ``None`` the helper calls :func:`detect_peaks` (limited to
        ``n_peaks_auto`` peaks if given).
    shape
        Line shape applied to all peaks.
    baseline_degree
        Polynomial degree for the simultaneously-fitted baseline. Use 0 for
        a constant offset, 1 for linear, etc. ``-1`` (or any negative) means
        no baseline term.
    n_peaks_auto
        Cap on auto-detected peaks when ``initial_peaks`` is None.
    auto_prominence
        Minimum prominence forwarded to :func:`detect_peaks` when auto-detecting.
    max_nfev
        Forwarded to :func:`scipy.optimize.least_squares`.
    positive_only
        Fit only the samples at or above zero. Default True: a dI/dV curve
        is a density of states, so a sample below zero is noise or an
        over-subtracted background, and letting it into the least-squares
        pulls the model down exactly where the curve is weakest. Peaks are
        still *detected* on the whole curve — a detector needs a contiguous
        grid to measure width and prominence on — and the mask is dropped
        if it would leave too few points to determine the model. Set False
        for a signed quantity such as I(V) or a difference spectrum.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    shape = PeakShape(shape)
    if x.shape != y.shape or x.size < 4:
        raise ValueError("x and y must be 1-D arrays of the same length (≥ 4)")

    # Which samples the least-squares is allowed to see. Detection below
    # still runs on the whole curve.
    fit_mask = positive_mask(y) if positive_only else np.isfinite(y)
    if fit_mask.sum() < max(4, 2 * (max(baseline_degree, 0) + 1)):
        # An all-negative or nearly-all-negative curve: honouring the rule
        # would leave nothing to determine the model from, and a fit to three
        # points is not a measurement. Fall back rather than fail.
        if positive_only and np.isfinite(y).any():
            logger.debug("positive_only left %d of %d samples; fitting all of them",
                         int(fit_mask.sum()), y.size)
        fit_mask = np.isfinite(y)
    if not fit_mask.all():
        x_fit, y_fit = x[fit_mask], y[fit_mask]
    else:
        x_fit, y_fit = x, y

    if baseline_degree is None or baseline_degree < 0:
        baseline_degree = -1
        base_init = None
    else:
        base_init = np.polyfit(x_fit, y_fit, baseline_degree)

    if initial_peaks is None:
        # Subtract baseline before detection so peaks stand out.
        residual = y - (np.polyval(base_init, x) if base_init is not None else 0.0)
        seeds = detect_peaks(
            x, residual,
            prominence=auto_prominence, n_max=n_peaks_auto,
        )
        if not seeds:
            seeds = detect_peaks(x, y, prominence=auto_prominence, n_max=n_peaks_auto)
        initial_peaks = seeds

    initial_peaks = list(initial_peaks)
    if not initial_peaks:
        # Nothing to fit other than the baseline — still return a result.
        peaks: List[FittedPeak] = []
        if base_init is None:
            fitted = np.zeros_like(x)
            base_curve = np.zeros_like(x)
            base_coeffs = np.array([])
        else:
            base_curve = np.polyval(base_init, x)
            fitted = base_curve.copy()
            base_coeffs = base_init
        return _make_result(
            x, y, peaks, base_coeffs, fitted, base_curve,
            success=True, message="No peaks detected; baseline only.",
            fit_mask=fit_mask,
        )

    p0, per_peak = _pack_params(
        initial_peaks, shape,
        max(baseline_degree, 0),
        baseline_coeffs0=base_init,
    )
    n_peaks = len(initial_peaks)

    # Construct loose lower/upper bounds. Centers are constrained to the data
    # range; widths must be positive; pseudo-Voigt eta ∈ [0, 1].
    lower = np.full_like(p0, -np.inf)
    upper = np.full_like(p0, np.inf)
    x_min, x_max = float(x.min()), float(x.max())
    span = max(x_max - x_min, 1e-9)
    for i in range(n_peaks):
        base = i * per_peak
        # amplitude unbounded (positive or negative peaks both work)
        lower[base + 1] = x_min - 0.1 * span
        upper[base + 1] = x_max + 0.1 * span
        lower[base + 2] = 1e-9
        upper[base + 2] = 5.0 * span
        if shape == PeakShape.PSEUDO_VOIGT:
            lower[base + 3] = 0.0
            upper[base + 3] = 1.0

    n_base = max(baseline_degree + 1, 0)
    bdeg = max(baseline_degree, 0)

    def residuals(p):
        return _model(p, x_fit, n_peaks, shape, bdeg) - y_fit

    try:
        result = least_squares(
            residuals, p0, bounds=(lower, upper), max_nfev=max_nfev,
        )
        success = result.success
        message = result.message
        p_opt = result.x
    except Exception as e:
        logger.exception("least_squares failed: %s", e)
        return _make_result(
            x, y, [], np.array([]), np.zeros_like(x), np.zeros_like(x),
            success=False, message=str(e), fit_mask=fit_mask,
        )

    fitted_peaks, base_coeffs = _unpack_params(p_opt, n_peaks, shape, bdeg)
    base_curve = np.polyval(base_coeffs, x) if base_coeffs.size else np.zeros_like(x)
    fitted_curve = base_curve.copy()
    components: List[np.ndarray] = []
    for peak in fitted_peaks:
        comp = peak.evaluate(x)
        components.append(comp)
        fitted_curve = fitted_curve + comp

    res = _make_result(
        x, y, fitted_peaks, base_coeffs, fitted_curve, base_curve,
        success=success, message=message, fit_mask=fit_mask,
    )
    res.components = components
    return res


def _make_result(x, y, peaks, base_coeffs, fitted, baseline,
                 *, success: bool, message: str,
                 fit_mask: Optional[np.ndarray] = None) -> MultiPeakFitResult:
    # The residual curve spans the whole spectrum so it can be plotted
    # against it, but the goodness of fit is measured only where the fit was
    # actually made: scoring it against samples deliberately excluded as
    # unphysical would report a worse fit for obeying the rule.
    residuals = y - fitted
    scored = residuals if fit_mask is None else residuals[fit_mask]
    y_scored = y if fit_mask is None else y[fit_mask]
    rss = float(np.sum(scored ** 2))
    ss_tot = float(np.sum((y_scored - np.mean(y_scored)) ** 2)) if y_scored.size else 0.0
    rsq = 1.0 - rss / ss_tot if ss_tot > 1e-30 else 1.0
    return MultiPeakFitResult(
        x=x, y=y, peaks=peaks, baseline_coeffs=base_coeffs,
        fitted_curve=fitted, baseline_curve=baseline,
        residuals=residuals, rss=rss, rsq=rsq,
        success=success, message=message,
    )
