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


def detect_saturation(spectrum: np.ndarray, threshold: float = 0.95) -> float:
    """
    Check if spectrum clips at min/max values (saturation artifact).

    Looks for values that are very close to the global min or max,
    indicating ADC saturation or amplifier clipping.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values.
    threshold : float
        Fraction of range considered as "saturated" zone (default 0.95).
        Values in the top/bottom (1 - threshold)/2 of the range are flagged.

    Returns
    -------
    score : float
        Saturation score 0-1. Higher = more saturated.
    """
    clean = spectrum[~np.isnan(spectrum)]
    if len(clean) < 3:
        return 0.0

    vmin, vmax = np.min(clean), np.max(clean)
    vrange = vmax - vmin
    if vrange < 1e-30:
        return 1.0  # Flat spectrum is saturated or dead

    # Fraction of range for saturation zone
    margin = (1.0 - threshold) / 2.0 * vrange

    # Count points near min or max
    near_min = np.sum(clean < (vmin + margin))
    near_max = np.sum(clean > (vmax - margin))
    saturated_count = near_min + near_max

    # Score: fraction of points that are saturated
    # Normal curves (sine, Gaussian) can have 10-40% near extremes naturally,
    # so only flag when fraction is high enough to indicate actual clipping.
    # Score is normalized: 0 if <= 30% at extremes, 1 if >= 60%
    frac = saturated_count / len(clean)
    score = np.clip((frac - 0.30) / 0.30, 0.0, 1.0)

    return float(score)


def detect_noise(spectrum: np.ndarray, snr_threshold: float = 3.0) -> float:
    """
    Estimate noise level via high-frequency content.

    Uses the standard deviation of the second derivative as a proxy
    for high-frequency noise content, compared to the signal amplitude.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values.
    snr_threshold : float
        SNR below this is considered noisy (default 3.0).

    Returns
    -------
    score : float
        Noise score 0-1. Higher = noisier.
    """
    clean = spectrum[~np.isnan(spectrum)]
    if len(clean) < 5:
        return 0.0

    # High-frequency content via second derivative
    d2 = np.diff(clean, n=2)
    noise_estimate = np.std(d2)

    # Signal amplitude
    signal_range = np.max(clean) - np.min(clean)
    if signal_range < 1e-30:
        return 1.0  # Flat signal = all noise

    # SNR estimate
    snr = signal_range / (noise_estimate + 1e-30)

    # Map to score: high SNR -> low score, low SNR -> high score
    # Score = 0 if SNR >= snr_threshold * 3, score = 1 if SNR <= snr_threshold / 3
    score = np.clip(1.0 - (snr - snr_threshold / 3.0) / (snr_threshold * 3.0 - snr_threshold / 3.0), 0.0, 1.0)

    return float(score)


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
                         snr_threshold: float = 3.0) -> float:
    """
    Detect regions where noise dominates the signal.

    Splits the spectrum into overlapping windows and computes local SNR
    in each. Score reflects the fraction of the spectrum that is
    noise-dominated.

    Parameters
    ----------
    x : np.ndarray
        Independent variable (unused but kept for API consistency).
    spectrum : np.ndarray
        Spectrum values.
    window_fraction : float
        Fraction of spectrum length for each window (default 0.1).
    snr_threshold : float
        Local SNR below this is considered noisy (default 3.0).

    Returns
    -------
    score : float
        Partial noise score 0-1. Higher = more noise-dominated regions.
    """
    clean_mask = ~np.isnan(spectrum)
    clean = spectrum[clean_mask]
    n = len(clean)

    if n < 20:
        return 0.0

    # Adaptive window size
    window = max(10, int(n * window_fraction))
    step = max(1, window // 2)  # 50% overlap

    noisy_count = 0
    total_windows = 0

    for start in range(0, n - window + 1, step):
        segment = clean[start:start + window]
        total_windows += 1

        if len(segment) < 5:
            continue

        # Local SNR via 2nd derivative
        d2 = np.diff(segment, n=2)
        local_noise = np.std(d2)
        local_range = np.max(segment) - np.min(segment)

        if local_range < 1e-30:
            noisy_count += 1
            continue

        local_snr = local_range / (local_noise + 1e-30)
        if local_snr < snr_threshold:
            noisy_count += 1

    if total_windows == 0:
        return 0.0

    noisy_fraction = noisy_count / total_windows
    # Scale: 50% noisy windows -> score 1.0
    score = np.clip(noisy_fraction * 2.0, 0.0, 1.0)
    return float(score)


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
                          min_freq_fraction: float = 0.05
                          ) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """
    Detect periodic noise in a spectrum via FFT peak analysis.

    Looks for sharp peaks in the FFT magnitude spectrum that rise
    significantly above the local background, indicating periodic artifacts.

    Parameters
    ----------
    spectrum : np.ndarray
        Spectrum values (real, 1-D).
    peak_threshold : float
        Number of MADs above the background to consider a peak (default 3.0).
    min_freq_fraction : float
        Fraction of total frequency bins to skip at the low end (DC + slow trends).

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
    clean = spectrum[~np.isnan(spectrum)]
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

    if len(peaks) == 0:
        return 0.0, fft_magnitude, np.expm1(background), peak_mask

    # Score: power in peaks vs total power (skip DC)
    power = fft_magnitude[1:] ** 2
    total_power = np.sum(power)
    if total_power < 1e-30:
        return 0.0, fft_magnitude, np.expm1(background), peak_mask

    peak_power = np.sum(fft_magnitude[peaks] ** 2)
    score = np.clip(peak_power / total_power * 10.0, 0.0, 1.0)

    return float(score), fft_magnitude, np.expm1(background), peak_mask


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
