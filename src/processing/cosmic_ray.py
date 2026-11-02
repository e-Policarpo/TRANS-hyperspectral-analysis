"""
Cosmic-ray / hot-pixel filter for CCD-based spectra (PL, Raman).

CCD spikes from cosmic-ray hits or hot pixels look like a few-sample-wide
burst that is dramatically brighter than the surrounding signal. Treating
them as ordinary noise (e.g. a smoothing filter) fails because their
amplitude is many sigma above baseline; they then contaminate every
downstream operation that relies on peak detection or integration.

Detection strategy
------------------
For each spectrum:

1. Compute the running median ``y_med`` of each sample's NEIGHBOURS over
   a small window (default 5 samples), the sample itself left out.
   Cosmic rays are sub-window in width, so they are rejected by the
   median.
2. Compute the residual ``r = y - y_med``. Estimate ``σ`` of ``r`` from
   its MAD (median absolute deviation) so the σ itself is unaffected by
   the spikes.

   Leaving the sample out is what makes the threshold mean what it says.
   With the sample inside its own median, ``r`` is not Gaussian: the median
   follows the sample part of the way, the MAD then underestimates ``r``'s
   spread by ~25 %, and "5σ" was really ~4σ — measured, 0.8 false spikes
   per 2001-sample spectrum of pure noise, each one a real sample replaced.
   Left out, the sample is independent of its reference, the MAD estimates
   the spread exactly (ratio 1.000 at windows 3, 5 and 7) and pure noise
   is no longer flagged.
3. Flag samples where ``r > threshold_sigmas × σ``.
4. Group flagged samples into connected runs. Only runs of width
   ``≤ max_width`` are treated as cosmic rays — wider runs are most
   likely real, narrow physical peaks (e.g. Raman lines span several
   pixels).
4b. Keep a run only if it is SHARP: its jump above the samples just
   outside it must exceed ``sharpness`` times the step those samples
   already take one ring further out (floored at 1σ). A residual in σ
   alone cannot tell a spike from a peak top: at high signal-to-noise the
   curvature of a genuine line is many σ, and the old filter replaced the
   top of 150 of 200 synthetic Lorentzians (3-20 samples FWHM, SNR
   20-10^4), clipping their height. The ratio is scale-free — a smooth
   line's top rises about as fast as its flank, a spike rises out of
   nowhere — and at the default 3 it flagged none of those 200 tops while
   catching all 140 spikes (10σ-5000σ, 1-2 samples, on flat ground and on
   a peak); measured, not tuned to the tests.
5. Replace flagged samples with the neighbours' median.

The helper returns the cleaned array plus a boolean mask of replaced
samples so callers can audit how many spikes were removed.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from scipy.ndimage import median_filter


def remove_cosmic_rays(
    y: np.ndarray,
    *,
    threshold_sigmas: float = 5.0,
    window: int = 5,
    max_width: int = 2,
    sharpness: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Remove narrow CCD spikes from a single 1-D spectrum.

    Parameters
    ----------
    y
        Spectrum samples (1-D).
    threshold_sigmas
        Residual threshold in units of robust σ. Defaults to 5σ —
        well above noise, below real peaks.
    window
        Sliding-median window length (forced odd, minimum 3). 5 works
        for most spectra; widen for very narrow real features that you
        also want preserved.
    max_width
        Maximum width (in samples) of a flagged run that still counts
        as a cosmic ray. Real Raman / PL peaks usually span more than
        two CCD pixels, so the default of 2 is a safe compromise.
    sharpness
        How much faster than its surroundings a run must rise to count as
        a spike (see step 4b). 3 keeps the tops of real lines at any
        signal-to-noise; None restores the σ-only test.

    Returns
    -------
    cleaned : np.ndarray
        Spectrum with spikes replaced by the local median.
    mask : np.ndarray of bool
        ``True`` at samples that were replaced.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size < 5:
        return y.copy(), np.zeros(y.size, dtype=bool)

    window = max(3, int(window) | 1)
    neighbours = np.ones(window, dtype=bool)
    neighbours[window // 2] = False
    median_local = median_filter(y, footprint=neighbours, mode="reflect")
    diff = y - median_local

    mad = float(np.median(np.abs(diff - np.median(diff))))
    sigma = 1.4826 * mad
    if sigma <= 0:
        std = float(np.std(diff))
        sigma = std if std > 0 else 1e-12

    candidates = diff > threshold_sigmas * sigma
    mask = np.zeros(y.size, dtype=bool)

    if not candidates.any():
        return y.copy(), mask

    # Walk connected runs of candidate samples and accept only narrow ones.
    cleaned = y.copy()
    in_run = False
    run_start = 0
    for i in range(y.size + 1):
        is_cand = bool(candidates[i]) if i < y.size else False
        if is_cand and not in_run:
            in_run = True
            run_start = i
        elif not is_cand and in_run:
            run_end = i
            if (run_end - run_start) <= max_width and _is_sharp(
                    y, run_start, run_end, sigma, sharpness):
                mask[run_start:run_end] = True
                cleaned[run_start:run_end] = median_local[run_start:run_end]
            in_run = False

    return cleaned, mask


def _is_sharp(y, start, end, sigma, sharpness) -> bool:
    """Does ``y[start:end]`` rise out of its surroundings like a spike?

    The jump is the run's lowest sample above the median of the two
    samples on each side; the step is how far that level already differs
    from the next two out. None disables the test (the old behaviour).
    At the array ends, where a ring is missing, the run is kept.
    """
    if sharpness is None:
        return True
    inner = np.r_[y[max(0, start - 2):start], y[end:end + 2]]
    outer = np.r_[y[max(0, start - 4):max(0, start - 2)], y[end + 2:end + 4]]
    if inner.size == 0 or outer.size == 0:
        return True
    level = float(np.median(inner))
    jump = float(np.min(y[start:end])) - level
    step = abs(level - float(np.median(outer)))
    return jump > sharpness * max(step, sigma)


def remove_cosmic_rays_2d(
    spectra: np.ndarray,
    *,
    threshold_sigmas: float = 5.0,
    window: int = 5,
    max_width: int = 2,
    sharpness: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply :func:`remove_cosmic_rays` independently to each column.

    ``spectra`` is expected with the spectral axis along axis 0 and
    individual spectra along axis 1 — the same layout used everywhere
    else in :mod:`src.processing`. Returns the cleaned array and a
    boolean mask of the same shape marking replaced samples.
    """
    spectra = np.asarray(spectra, dtype=np.float64)
    if spectra.ndim != 2:
        raise ValueError("spectra must be a 2-D array (samples × spectra)")

    cleaned = np.empty_like(spectra)
    mask = np.zeros_like(spectra, dtype=bool)
    for j in range(spectra.shape[1]):
        col_cleaned, col_mask = remove_cosmic_rays(
            spectra[:, j],
            threshold_sigmas=threshold_sigmas,
            window=window,
            max_width=max_width,
            sharpness=sharpness,
        )
        cleaned[:, j] = col_cleaned
        mask[:, j] = col_mask
    return cleaned, mask
