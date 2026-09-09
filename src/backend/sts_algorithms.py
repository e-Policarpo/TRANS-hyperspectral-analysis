"""
STS Analysis Algorithms
Pure-Python module with clean reimplementations of core STS analysis algorithms.
No Qt/PySide dependencies — just numpy/scipy.

Algorithms adapted from ststools by Rafael Reis (https://github.com/rafinhareis/ststools)

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo
Contact: eduardapolicarpo.fisica@gmail.com
Date: January 2026
License: GPL
"""

import math

import numpy as np
from scipy import ndimage, signal
from typing import Tuple, Optional


def numerical_derivative(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Numerical derivative via np.diff.

    Parameters
    ----------
    x : np.ndarray
        Independent variable (e.g., voltage).
    y : np.ndarray
        Dependent variable (e.g., current).

    Returns
    -------
    x_mid : np.ndarray
        Midpoints of x (length N-1).
    dy : np.ndarray
        Derivative dy/dx at midpoints.
    """
    dx = np.diff(x)
    dy = np.diff(y)
    # Avoid division by zero
    dx_safe = np.where(np.abs(dx) < 1e-30, 1e-30, dx)
    x_mid = (x[:-1] + x[1:]) / 2.0
    return x_mid, dy / dx_safe


def normalize_ldos(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Normalize dI/dV (LDOS): center at V=0, scale max positive to 1.

    Parameters
    ----------
    x : np.ndarray
        Voltage values (derivative midpoints).
    y : np.ndarray
        dI/dV values.

    Returns
    -------
    x : np.ndarray
        Same voltage values (unchanged).
    y_norm : np.ndarray
        Normalized LDOS values.
    """
    # Find index closest to V=0
    zero_idx = np.argmin(np.abs(x))

    # Subtract value at V=0 to center
    y_centered = y - y[zero_idx]

    # Scale by max of positive part
    max_positive = np.max(y_centered)
    if max_positive > 0:
        y_norm = y_centered / max_positive
    else:
        # If no positive values, normalize by absolute max
        abs_max = np.max(np.abs(y_centered))
        if abs_max > 0:
            y_norm = y_centered / abs_max
        else:
            y_norm = y_centered

    return x, y_norm


def detect_bandgap(dx: np.ndarray, dy: np.ndarray,
                   delta: float) -> Tuple[float, float, float, float]:
    """
    Find bandgap from normalized LDOS.

    The algorithm finds the region around V=0 where the normalized LDOS
    stays below a threshold (delta), identifying the bandgap edges.

    Parameters
    ----------
    dx : np.ndarray
        Voltage values.
    dy : np.ndarray
        Normalized LDOS values.
    delta : float
        Threshold for bandgap detection (fraction, e.g. 0.05 for 5%).

    Returns
    -------
    gap : float
        Bandgap width in same units as dx (typically eV).
    typ : float
        Bandgap center offset from zero (indicates doping type).
        Negative = N-type, Positive = P-type, ~0 = Neutral.
    xmin : float
        Left edge of bandgap (voltage).
    xmax : float
        Right edge of bandgap (voltage).
    """
    # Find index closest to V=0
    zero_idx = np.argmin(np.abs(dx))

    # Search left from zero for where |LDOS| exceeds delta
    xmin = dx[0]  # default: leftmost voltage
    for i in range(zero_idx, -1, -1):
        if np.abs(dy[i]) > delta:
            xmin = dx[i]
            break

    # Search right from zero for where |LDOS| exceeds delta
    xmax = dx[-1]  # default: rightmost voltage
    for i in range(zero_idx, len(dx)):
        if np.abs(dy[i]) > delta:
            xmax = dx[i]
            break

    gap = xmax - xmin
    typ = (xmax + xmin) / 2.0  # Center of the gap

    return gap, typ, xmin, xmax


def classify_doping(typ: float, resolution: float) -> str:
    """
    Classify doping type based on bandgap center offset.

    Parameters
    ----------
    typ : float
        Bandgap center offset from zero (from detect_bandgap).
    resolution : float
        Tolerance around zero for classifying as Neutral.

    Returns
    -------
    doping : str
        'N' for N-type, 'P' for P-type, or 'Neutral'.
    """
    if typ < -resolution:
        return 'N'
    elif typ > resolution:
        return 'P'
    else:
        return 'Neutral'


def validate_ldos(x: np.ndarray, y: np.ndarray) -> Tuple[bool, str]:
    """
    Sanity check: is this a physically reasonable LDOS curve?

    Checks: not all-NaN, not flat, has enough variation, derivative exists.

    Parameters
    ----------
    x : np.ndarray
        Independent variable (voltage).
    y : np.ndarray
        Dependent variable (current or dI/dV).

    Returns
    -------
    is_valid : bool
        True if the curve passes all checks.
    reason : str
        Description of why the curve failed (empty string if valid).
    """
    # Check for all-NaN
    if np.all(np.isnan(y)):
        return False, "All values are NaN"

    # Remove NaN for further checks
    valid_mask = ~np.isnan(y)
    y_clean = y[valid_mask]

    if len(y_clean) < 5:
        return False, "Too few valid data points"

    # Check if flat (zero standard deviation)
    std = np.std(y_clean)
    if std < 1e-20:
        return False, "Spectrum is flat (zero variation)"

    # Check if there's meaningful variation relative to mean
    mean_abs = np.mean(np.abs(y_clean))
    if mean_abs > 0 and std / mean_abs < 1e-10:
        return False, "Spectrum has negligible relative variation"

    # Check for enough points to compute derivative
    x_clean = x[valid_mask]
    if len(x_clean) < 3:
        return False, "Not enough points for derivative computation"

    return True, ""


# =============================================================================
# Structure vs. noise
#
# Every "is this spectrum usable?" question below reduces to one measurement:
# how much of the curve's variation is real structure, and how much is its own
# noise. Two numbers answer it.
#
# The noise sigma comes from the second difference: white noise makes it swing
# with variance 6*sigma^2, while smooth structure barely moves it at all, so a
# median absolute deviation reads the noise off a spectrum that is mostly
# signal without needing a signal-free stretch to measure on.
#
# The structure amplitude is the peak-to-peak of the *smoothed* curve. The raw
# peak-to-peak is not usable here: on a featureless spectrum it is set by the
# noise itself (and by any slow drift), which is exactly why a flat dI/dV
# sitting above the noise floor used to read as a high-SNR, "good" spectrum.
# =============================================================================

_SG_POLYORDER = 2

# Peak-to-peak of two independent Gaussian samples, E|z1 - z2| = 2/sqrt(pi).
# The asymptotic sqrt(2 ln m) law overshoots for tiny m, so this is the floor.
_MIN_EXPECTED_RANGE = 1.13


def _smoothing_window(n: int, fraction: float = 0.05,
                      minimum: int = 5, maximum: int = 51) -> int:
    """Odd Savitzky-Golay window for an ``n``-point spectrum, 0 if too short."""
    if n < minimum + 2:
        return 0
    w = int(round(n * fraction))
    if w % 2 == 0:
        w += 1
    w = max(minimum, min(w, maximum))
    if w >= n:
        w = n - 1 if (n - 1) % 2 else n - 2
    return w if w > _SG_POLYORDER else 0


def robust_sigma(spectrum: np.ndarray) -> float:
    """Noise sigma of a spectrum, from the MAD of its own second difference.

    The second difference of white noise has variance ``6*sigma^2``; a median
    absolute deviation ignores peaks and edges, which are a small minority of
    the samples. 1.4826 converts MAD to sigma for Gaussian noise.

    Returns 0.0 for a noiseless or too-short spectrum.
    """
    y = np.asarray(spectrum, dtype=np.float64)
    clean = y[np.isfinite(y)]
    if clean.size < 5:
        return 0.0
    d2 = np.diff(clean, n=2)
    if d2.size == 0:
        return 0.0
    mad = float(np.median(np.abs(d2 - np.median(d2))))
    return float(1.4826 * mad / math.sqrt(6.0))


def structure_metrics(spectrum: np.ndarray, detrend: bool = True,
                      window_fraction: float = 0.05) -> dict:
    """Separate a spectrum's smooth structure from its noise.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values; NaN/inf are stripped.
    detrend : bool
        Remove a straight line from the smoothed curve before measuring its
        amplitude (default True). A slow monotonic drift is an artifact of the
        measurement, not a feature of the sample, and without this a drifting
        flat spectrum reads as though it had structure. A tunnelling band edge
        survives detrending easily — it is nowhere near a straight line.
    window_fraction : float
        Smoothing window as a fraction of the spectrum length (default 0.05).

    Returns
    -------
    dict with keys

    ``n``
        Count of finite samples.
    ``sigma``, ``sigma_smooth``
        Noise sigma of the raw curve, and what is left of it after smoothing.
    ``amplitude``
        Peak-to-peak of the smoothed, optionally detrended curve.
    ``span``
        The same, but measured between the 2nd and 98th percentiles, so a
        single spike — the derivative of a sweep often has one at each end —
        cannot stand in for structure.
    ``expected``
        Peak-to-peak the smoothed curve would show if it were pure noise.
    ``ratio``
        ``amplitude / expected``: ~1 means the curve is a constant plus
        noise, >> 1 means real structure.
    ``coherence``
        ``span`` divided by the smoothed curve's total variation: 1 for a
        curve that rises once and stops (a band edge), ~2/N for one that
        wanders up and down N times (noise). This is the measurement that
        survives correlated 1/f noise, which inflates ``ratio`` without
        putting any shape into the curve.
    ``window``, ``level``
        Smoothing window actually used, and the curve's median value.
    """
    y = np.asarray(spectrum, dtype=np.float64)
    clean = y[np.isfinite(y)]
    n = int(clean.size)
    if n < 7:
        return {'n': n, 'sigma': 0.0, 'sigma_smooth': 0.0, 'amplitude': 0.0,
                'span': 0.0, 'expected': 0.0, 'ratio': 0.0, 'coherence': 0.0,
                'window': 0, 'level': float(np.median(clean)) if n else 0.0}

    sigma = robust_sigma(clean)
    window = _smoothing_window(n, window_fraction)
    if window:
        smooth = signal.savgol_filter(clean, window, _SG_POLYORDER, mode='interp')
        # Noise attenuation of the filter: the smoothed sample is a fixed
        # linear combination of the window's samples, so its variance is
        # sigma^2 * sum(c^2).
        gain = float(np.sqrt(np.sum(signal.savgol_coeffs(window, _SG_POLYORDER) ** 2)))
        # SG fits one-sided polynomials at the ends, which are much noisier
        # than the interior; a single wild endpoint must not set the
        # amplitude on its own.
        if n > 3 * window:
            trim = window // 2
            smooth = smooth[trim:n - trim]
    else:
        smooth = clean
        gain = 1.0

    if detrend and smooth.size >= 3:
        idx = np.arange(smooth.size, dtype=np.float64)
        slope, intercept = np.polyfit(idx, smooth, 1)
        smooth = smooth - (slope * idx + intercept)

    amplitude = float(np.max(smooth) - np.min(smooth))
    span = float(np.percentile(smooth, 98) - np.percentile(smooth, 2))
    total_variation = float(np.sum(np.abs(np.diff(smooth)))) if smooth.size > 1 else 0.0
    coherence = span / total_variation if total_variation > 0 else 0.0
    sigma_smooth = sigma * gain

    # Smoothing correlates neighbouring samples, so the smoothed curve holds
    # about n/window independent ones; the peak-to-peak of m independent
    # Gaussians grows as 2*sqrt(2 ln m).
    m = max(2.0, smooth.size / float(window or 1))
    expected_factor = max(2.0 * math.sqrt(2.0 * math.log(m)), _MIN_EXPECTED_RANGE)
    expected = expected_factor * sigma_smooth

    if float(np.max(clean) - np.min(clean)) <= 0.0:
        ratio = 0.0                # a perfectly flat line: no structure at all
    elif expected > 0:
        ratio = amplitude / expected
    elif amplitude > 0:
        ratio = float('inf')       # structure with no noise at all
    else:
        ratio = 0.0

    return {'n': n, 'sigma': float(sigma), 'sigma_smooth': float(sigma_smooth),
            'amplitude': amplitude, 'span': span, 'expected': float(expected),
            'ratio': float(ratio), 'coherence': float(coherence),
            'window': int(window), 'level': float(np.median(clean))}


def detect_featureless(x: np.ndarray, spectrum: np.ndarray,
                       min_ratio: float = 3.0,
                       min_coherence: float = 0.12,
                       window_fraction: float = 0.05,
                       detrend: bool = True) -> float:
    """Flag a spectrum that carries no structure above its own noise floor.

    This is the "flat above the noise floor" case: a dI/dV curve that sits at
    some level — often well above zero, so no amplitude test catches it — and
    never departs from it except by wandering. There is no LDOS information in
    such a spectrum, but every other detector here passes it: it is not
    clipped, not linear, not periodic, and its raw peak-to-peak (set by the
    noise and by any slow drift) makes it look like a comfortable
    signal-to-noise ratio.

    Two independent things mark a spectrum as featureless, and either is
    enough:

    **Amplitude.** The smoothed curve does not depart from a straight line by
    more than the noise could manage on its own (``ratio`` near 1).

    **Coherence.** The curve moves, but never in one direction for long: its
    excursion is a small fraction of the distance it actually travels. A band
    edge rises once and stays up (coherence near 1); a real state is a single
    excursion; 1/f noise wanders up and down dozens of times and lands near
    0.05. The amplitude test alone cannot see this, because correlated noise
    is much larger than the white-noise sigma predicts — measured on real STS
    data, dead spectra sit 10-30x above the white-noise expectation while
    showing no shape whatsoever.

    Parameters
    ----------
    x : np.ndarray
        Independent variable (unused; kept so every detector takes the same
        arguments).
    spectrum : np.ndarray
        Spectrum values.
    min_ratio : float
        Structure amplitude, in units of what the noise alone would produce,
        at or above which the spectrum is definitely real (default 3.0). The
        score falls linearly from 1.0 at ratio 1 to 0 here.
    min_coherence : float
        Coherence at or above which the spectrum is definitely real (default
        0.12). The score is 1.0 at half this value and falls linearly to 0
        here — so at the default quality threshold of 0.5 the effective cut is
        0.09, which is the valley between the dead and the structured
        populations on real STS data.
    window_fraction : float
        Smoothing window as a fraction of the spectrum length.
    detrend : bool
        Treat a straight-line drift as an artifact rather than structure.

    Returns
    -------
    score : float
        Featureless score 0-1. Higher = flatter.
    """
    metrics = structure_metrics(spectrum, detrend=detrend,
                                window_fraction=window_fraction)
    if metrics['n'] < 7:
        return 0.0

    ratio = metrics['ratio']
    if np.isfinite(ratio):
        high = max(float(min_ratio), 1.0 + 1e-6)
        amplitude_score = float(np.clip((high - ratio) / (high - 1.0), 0.0, 1.0))
    else:
        amplitude_score = 0.0      # structure with no noise at all

    coherence = metrics['coherence']
    high = max(float(min_coherence), 1e-6)
    low = high / 2.0
    if coherence <= 0.0:
        # No total variation at all: a perfectly flat line.
        coherence_score = 1.0 if metrics['amplitude'] <= 0.0 else 0.0
    else:
        coherence_score = float(np.clip((high - coherence) / (high - low), 0.0, 1.0))

    return float(max(amplitude_score, coherence_score))


def detect_saturation(spectrum: np.ndarray, threshold: float = 0.95) -> float:
    """
    Check if a spectrum clips at its min/max value (saturation artifact).

    Saturation is a *dead* plateau: once the amplifier or the ADC rails, it
    stays railed and the noise disappears with it, because the converter is no
    longer following the signal. Both halves matter.

    Counting samples near an extreme, as an earlier version did, flags every
    clean spectrum with a band gap — most of a gapped dI/dV curve sits at the
    bottom of its own range by construction. Requiring only a plateau is not
    enough either: the floor of a gap is a plateau too. What a gap still has,
    and a railed converter does not, is its own noise.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values.
    threshold : float
        Fraction of the range that still counts as "at the rail"; the
        tolerance is ``(1 - threshold) / 2`` of the range (default 0.95, i.e.
        2.5%).

    Returns
    -------
    score : float
        Saturation score 0-1. Higher = more saturated.
    """
    clean = np.asarray(spectrum, dtype=np.float64)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 3:
        return 0.0

    vmin, vmax = float(np.min(clean)), float(np.max(clean))
    vrange = vmax - vmin
    if vrange < 1e-30:
        return 1.0  # flat spectrum is saturated or dead

    tolerance = (1.0 - threshold) / 2.0 * vrange
    sigma = robust_sigma(clean)

    def longest_dead_run(at_rail: np.ndarray) -> int:
        """Longest stretch pinned at a rail *and* stripped of its noise."""
        best = 0
        start = None
        for i, flag in enumerate(list(at_rail) + [False]):
            if flag and start is None:
                start = i
            elif not flag and start is not None:
                run = clean[start:i]
                # A railed converter stops responding: the scatter inside the
                # plateau collapses well below the spectrum's own noise. The
                # floor of a real band gap keeps it.
                if sigma <= 0.0 or float(np.std(run)) < 0.25 * sigma:
                    best = max(best, i - start)
                start = None
        return best

    pinned = max(longest_dead_run(clean <= vmin + tolerance),
                 longest_dead_run(clean >= vmax - tolerance))
    fraction = pinned / len(clean)

    # A real rail holds for a good stretch of the sweep. Below 2% of the
    # points it is just the curve's own turning point; by 10% it is clipping.
    return float(np.clip((fraction - 0.02) / 0.08, 0.0, 1.0))


def detect_noise(spectrum: np.ndarray, snr_threshold: float = 3.0) -> float:
    """
    Score how far a spectrum's signal rises above its own noise.

    The signal is the peak-to-peak of the smoothed curve and the noise is the
    robust sigma of the raw one (see :func:`structure_metrics`). Comparing the
    *raw* peak-to-peak against the noise, as an earlier version did, measures
    the noise twice over on a featureless spectrum and lets a slow drift stand
    in for signal.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values.
    snr_threshold : float
        SNR below this is considered noisy (default 3.0). The score is 1 at
        ``snr_threshold / 3`` and 0 at ``snr_threshold * 3``.

    Returns
    -------
    score : float
        Noise score 0-1. Higher = noisier.
    """
    clean = np.asarray(spectrum, dtype=np.float64)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 5:
        return 0.0

    metrics = structure_metrics(clean, detrend=False)
    amplitude = metrics['amplitude']
    sigma = metrics['sigma']

    if amplitude < 1e-30:
        return 1.0        # flat signal = all noise (or a dead channel)
    if sigma <= 0.0:
        return 0.0        # structure and no noise at all

    snr = amplitude / sigma
    low = snr_threshold / 3.0
    high = snr_threshold * 3.0
    return float(np.clip(1.0 - (snr - low) / (high - low), 0.0, 1.0))


def detect_linear_artifact(x: np.ndarray, spectrum: np.ndarray,
                           r2_threshold: float = 0.85) -> float:
    """
    Check if spectrum is suspiciously linear (R^2 of linear fit).

    A real STS spectrum should have nonlinear features. A nearly-perfect
    linear fit suggests a contact artifact or failed measurement.

    Parameters
    ----------
    x : np.ndarray
        Independent variable values.
    spectrum : np.ndarray
        Spectrum values.
    r2_threshold : float
        R^2 above this is considered suspicious (default 0.85).

    Returns
    -------
    score : float
        Linear artifact score 0-1. Higher = more linear.
    """
    # Remove NaN pairs
    mask = ~(np.isnan(x) | np.isnan(spectrum))
    x_clean = x[mask]
    y_clean = spectrum[mask]

    if len(x_clean) < 3:
        return 0.0

    # Linear fit
    coeffs = np.polyfit(x_clean, y_clean, 1)
    y_pred = np.polyval(coeffs, x_clean)

    # R^2 calculation
    ss_res = np.sum((y_clean - y_pred) ** 2)
    ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)

    if ss_tot < 1e-30:
        return 1.0  # Constant spectrum is trivially "linear"

    r2 = 1.0 - ss_res / ss_tot

    # Map R^2 to score: 0 if R^2 <= r2_threshold, 1 if R^2 >= 0.995
    if r2 < r2_threshold:
        return 0.0
    score = np.clip((r2 - r2_threshold) / (0.995 - r2_threshold), 0.0, 1.0)

    return float(score)


def detect_partial_noise(x: np.ndarray, spectrum: np.ndarray,
                         window_fraction: float = 0.1,
                         snr_threshold: float = 3.0,
                         noise_ratio: float = 3.0) -> float:
    """
    Detect stretches of a sweep where the measurement broke down.

    A window is noise-dominated when it holds no structure of its own *and*
    its noise is far above the quietest part of the same sweep — a burst of
    tip instability, a lost contact. Both conditions are needed: a spectrum
    with a band gap is flat and featureless inside the gap too, and flagging
    that would condemn every good gapped dI/dV curve (measured: an earlier
    version scored 0.32-1.0 on clean synthetic gap spectra).

    A spectrum with no signal anywhere is noise-dominated everywhere, and
    scores 1.0 without any of this.

    Parameters
    ----------
    x : np.ndarray
        Independent variable (unused but kept for API consistency).
    spectrum : np.ndarray
        Spectrum values.
    window_fraction : float
        Fraction of spectrum length for each window (default 0.1).
    snr_threshold : float
        A window with a local SNR below this holds no structure (default 3.0).
    noise_ratio : float
        How many times the sweep's quietest noise level a window's own noise
        must reach to count as a breakdown (default 3.0).

    Returns
    -------
    score : float
        Partial noise score 0-1. Higher = more noise-dominated regions.
    """
    clean = np.asarray(spectrum, dtype=np.float64)
    clean = clean[np.isfinite(clean)]
    n = len(clean)

    if n < 20:
        return 0.0

    # No signal anywhere: every part of the sweep is noise.
    overall = structure_metrics(clean, detrend=False)
    if overall['sigma'] > 0 and overall['amplitude'] / overall['sigma'] < snr_threshold:
        return 1.0

    window = max(10, int(n * window_fraction))
    step = max(1, window // 2)  # 50% overlap

    starts = list(range(0, n - window + 1, step))
    if not starts:
        return 0.0

    # A short window needs a proportionally larger smoothing kernel than the
    # whole sweep does, or there is nothing left to smooth with.
    local = [structure_metrics(clean[s:s + window], detrend=False,
                               window_fraction=0.35) for s in starts]
    sigmas = np.array([m['sigma'] for m in local], dtype=np.float64)

    # The quietest stretch of the sweep is the instrument's own noise floor.
    positive = sigmas[sigmas > 0]
    floor = float(np.percentile(positive, 10)) if positive.size else 0.0

    noisy_count = 0
    for metrics, local_sigma in zip(local, sigmas):
        amplitude = metrics['amplitude']
        if amplitude < 1e-30:
            noisy_count += 1              # dead stretch
            continue
        if local_sigma <= 0.0:
            continue                      # structure and no noise at all
        if amplitude / local_sigma >= snr_threshold:
            continue                      # this window holds structure
        if floor > 0 and local_sigma <= noise_ratio * floor:
            continue                      # quiet, not broken — a gap looks like this
        noisy_count += 1

    noisy_fraction = noisy_count / len(starts)
    # Scale: 50% noisy windows -> score 1.0
    return float(np.clip(noisy_fraction * 2.0, 0.0, 1.0))


def auto_detect_dirac_ranges(dx: np.ndarray, dy: np.ndarray,
                              bandgap_delta: float = 0.05) -> Tuple[float, float, float, float]:
    """
    Auto-detect fit ranges for Dirac point estimation using bandgap edges.

    Uses detect_bandgap() to find the gap edges, then returns:
    - Left fit range: from data start to left gap edge (the linear slope leading into the gap)
    - Right fit range: from right gap edge to data end (the linear slope leaving the gap)
    Each range is trimmed by 10% on the outer edge to avoid edge artifacts.

    Parameters
    ----------
    dx : np.ndarray
        Voltage values (from normalized LDOS).
    dy : np.ndarray
        Normalized LDOS values.
    bandgap_delta : float
        Threshold for bandgap detection (fraction, e.g. 0.05 for 5%).

    Returns
    -------
    left_min : float
        Start of left fit range.
    left_max : float
        End of left fit range (left gap edge).
    right_min : float
        Start of right fit range (right gap edge).
    right_max : float
        End of right fit range.
    """
    _, _, xmin, xmax = detect_bandgap(dx, dy, bandgap_delta)

    data_start = dx[0]
    data_end = dx[-1]

    # Left range: data_start to xmin
    left_span = xmin - data_start
    trim_left = left_span * 0.10
    left_min = data_start + trim_left
    left_max = xmin

    # Right range: xmax to data_end
    right_span = data_end - xmax
    trim_right = right_span * 0.10
    right_min = xmax
    right_max = data_end - trim_right

    return left_min, left_max, right_min, right_max


def fit_dirac_point(dx: np.ndarray, dy: np.ndarray,
                    left_range: Tuple[float, float],
                    right_range: Tuple[float, float]) -> Tuple[float, float, float, float, float, float, float, float]:
    """
    Fit linear slopes in two voltage ranges and find their intersection (Dirac point).

    Parameters
    ----------
    dx : np.ndarray
        Voltage values (from normalized LDOS).
    dy : np.ndarray
        Normalized LDOS values.
    left_range : tuple of (float, float)
        Voltage range (V_min, V_max) for left linear fit.
    right_range : tuple of (float, float)
        Voltage range (V_min, V_max) for right linear fit.

    Returns
    -------
    dirac_x : float
        Voltage at Dirac point (intersection of fits).
    dirac_y : float
        LDOS value at Dirac point.
    left_slope : float
        Slope of left fit.
    right_slope : float
        Slope of right fit.
    left_r2 : float
        R^2 of left fit.
    right_r2 : float
        R^2 of right fit.
    left_intercept : float
        Intercept of left fit.
    right_intercept : float
        Intercept of right fit.
    """
    # Extract data in left range
    left_mask = (dx >= left_range[0]) & (dx <= left_range[1])
    right_mask = (dx >= right_range[0]) & (dx <= right_range[1])

    x_left = dx[left_mask]
    y_left = dy[left_mask]
    x_right = dx[right_mask]
    y_right = dy[right_mask]

    if len(x_left) < 2 or len(x_right) < 2:
        return np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan

    # Linear fits (degree 1)
    left_coeffs = np.polyfit(x_left, y_left, 1)
    right_coeffs = np.polyfit(x_right, y_right, 1)

    left_slope = left_coeffs[0]
    left_intercept = left_coeffs[1]
    right_slope = right_coeffs[0]
    right_intercept = right_coeffs[1]

    # R^2 for left fit
    y_pred_left = np.polyval(left_coeffs, x_left)
    ss_res_left = np.sum((y_left - y_pred_left) ** 2)
    ss_tot_left = np.sum((y_left - np.mean(y_left)) ** 2)
    left_r2 = 1.0 - ss_res_left / ss_tot_left if ss_tot_left > 1e-30 else 0.0

    # R^2 for right fit
    y_pred_right = np.polyval(right_coeffs, x_right)
    ss_res_right = np.sum((y_right - y_pred_right) ** 2)
    ss_tot_right = np.sum((y_right - np.mean(y_right)) ** 2)
    right_r2 = 1.0 - ss_res_right / ss_tot_right if ss_tot_right > 1e-30 else 0.0

    # Find intersection: left_slope * x + left_intercept = right_slope * x + right_intercept
    slope_diff = left_slope - right_slope
    if np.abs(slope_diff) < 1e-30:
        # Parallel lines — no intersection
        return np.nan, np.nan, left_slope, right_slope, left_r2, right_r2, left_intercept, right_intercept

    dirac_x = (right_intercept - left_intercept) / slope_diff
    dirac_y = left_slope * dirac_x + left_intercept

    return dirac_x, dirac_y, left_slope, right_slope, left_r2, right_r2, left_intercept, right_intercept


def detect_periodic_noise(spectrum: np.ndarray,
                          peak_threshold: float = 3.0,
                          min_freq_fraction: float = 0.15,
                          min_concentration: float = 5.0,
                          full_concentration: float = 20.0
                          ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """
    Detect periodic noise in a spectrum via FFT peak analysis.

    A periodic artifact — mains pickup, a piezo resonance — is a *line*: it
    puts a large share of the band's power into one or two frequency bins.
    The score is therefore the power **concentration**, the share of the
    analysed band's power carried by the detected peaks divided by the share
    that many bins would carry if the power were spread evenly. Concentration
    is 1 when the peaks are no more than their fair share and tens when a
    genuine line is present.

    Scoring the raw power share instead, as an earlier version did, cannot
    work: on a smooth spectrum nearly all the power sits at low frequency, so
    any bin flagged there saturates the score. Measured on real STS data that
    marked 91% of the spectra as periodic; the same data scores 0% here,
    while a sine artifact at 1% of the signal amplitude still scores 1.0.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values (real, 1-D).
    peak_threshold : float
        Number of MADs above the background to consider a peak (default 3.0).
    min_freq_fraction : float
        Fraction of frequency bins to skip at the low end (DC and the signal's
        own slow structure), default 0.15.
    min_concentration : float
        Concentration at or below which nothing is flagged (default 5.0 —
        real STS spectra measured between 4.5 and 8.5).
    full_concentration : float
        Concentration at or above which the score is 1.0 (default 20.0).

    Returns
    -------
    score : float
        Periodic noise score 0-1. Higher = more periodic noise.
    fft_magnitude : np.ndarray
        Magnitude of the real FFT (length N//2 + 1).
    background : np.ndarray
        Estimated smooth background of the log-magnitude.
    peak_mask : np.ndarray
        Boolean mask of detected peaks (same length as fft_magnitude).
    """
    clean = np.asarray(spectrum, dtype=np.float64)
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n < 8:
        empty = np.zeros(1)
        return 0.0, empty, empty, np.zeros(1, dtype=bool)

    fft_coeffs = np.fft.rfft(clean)
    fft_magnitude = np.abs(fft_coeffs)

    # Work in log space for background estimation
    log_mag = np.log1p(fft_magnitude)
    kernel_size = max(n // 20, 5)
    if kernel_size % 2 == 0:
        kernel_size += 1
    background = ndimage.median_filter(log_mag, size=kernel_size)

    residuals = log_mag - background

    # Robust scale: MAD
    mad = np.median(np.abs(residuals - np.median(residuals)))
    if mad < 1e-30:
        return 0.0, fft_magnitude, np.expm1(background), np.zeros(len(fft_magnitude), dtype=bool)

    height_threshold = peak_threshold * mad
    peaks, _ = signal.find_peaks(residuals, height=height_threshold)

    # Ignore DC and low frequencies
    min_bin = max(1, int(min_freq_fraction * len(fft_magnitude)))
    peaks = peaks[peaks >= min_bin]

    peak_mask = np.zeros(len(fft_magnitude), dtype=bool)
    peak_mask[peaks] = True

    n_band = len(fft_magnitude) - min_bin
    if len(peaks) == 0 or n_band <= 0:
        return 0.0, fft_magnitude, np.expm1(background), peak_mask

    band_power = float(np.sum(fft_magnitude[min_bin:] ** 2))
    if band_power < 1e-300:
        return 0.0, fft_magnitude, np.expm1(background), peak_mask

    share = float(np.sum(fft_magnitude[peaks] ** 2)) / band_power
    fair_share = len(peaks) / float(n_band)
    concentration = share / fair_share if fair_share > 0 else 0.0

    low = float(min_concentration)
    high = max(float(full_concentration), low + 1e-6)
    score = float(np.clip((concentration - low) / (high - low), 0.0, 1.0))

    return score, fft_magnitude, np.expm1(background), peak_mask


def correct_periodic_noise(spectrum: np.ndarray,
                           peak_mask: np.ndarray,
                           margin: int = 2) -> np.ndarray:
    """
    Remove periodic noise by interpolating over FFT peaks.

    For each contiguous region of detected peaks (expanded by ±margin),
    the complex FFT coefficients are linearly interpolated from the
    region edges, effectively removing the sharp frequency components.

    Parameters
    ----------
    spectrum : np.ndarray
        Original spectrum values (real, 1-D).
    peak_mask : np.ndarray
        Boolean mask from detect_periodic_noise (length N//2 + 1).
    margin : int
        Number of extra bins to expand around each peak (default 2).

    Returns
    -------
    corrected : np.ndarray
        Corrected spectrum with periodic noise removed (same length as input).
    """
    n = len(spectrum)
    fft_coeffs = np.fft.rfft(spectrum).copy()
    n_fft = len(fft_coeffs)

    # Expand peak_mask by margin
    expanded = peak_mask.copy()
    for shift in range(1, margin + 1):
        expanded[shift:] |= peak_mask[:-shift]
        expanded[:-shift] |= peak_mask[shift:]
    # Don't touch DC bin
    expanded[0] = False

    # Find contiguous regions and interpolate
    regions = np.diff(expanded.astype(int))
    starts = np.where(regions == 1)[0] + 1
    ends = np.where(regions == -1)[0] + 1

    # Handle edge cases
    if expanded[0]:
        starts = np.concatenate(([0], starts))
    if expanded[-1]:
        ends = np.concatenate((ends, [n_fft]))

    for s, e in zip(starts, ends):
        # Edge values for interpolation
        left_idx = max(s - 1, 0)
        right_idx = min(e, n_fft - 1)
        left_val = fft_coeffs[left_idx]
        right_val = fft_coeffs[right_idx]

        length = e - s
        if length <= 0:
            continue

        # Linear interpolation of complex coefficients
        t = np.linspace(0, 1, length + 2)[1:-1]  # exclude endpoints
        fft_coeffs[s:e] = left_val + t * (right_val - left_val)

    corrected = np.fft.irfft(fft_coeffs, n=n)
    return corrected
