"""
Tests for the multi-peak fitting utility.

Synthetic spectra with known parameters drive every assertion: peaks are
reconstructed within ~1 % of the true centers / widths, baselines are
recovered, and pseudo-Voigt mixing factors fall in [0, 1].

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.backend.peak_fitting import (
    FittedPeak,
    MultiPeakFitResult,
    PeakShape,
    detect_peaks,
    fit_multipeak,
    gaussian,
    lorentzian,
    pseudo_voigt,
)


# =============================================================================
# Line-shape primitives
# =============================================================================

def test_gaussian_peak_value_at_center():
    x = np.linspace(-5, 5, 1001)
    y = gaussian(x, amplitude=2.0, center=1.0, sigma=0.5)
    # Peak occurs at center; height should equal amplitude.
    idx = int(np.argmax(y))
    assert abs(x[idx] - 1.0) < 0.01
    assert abs(y[idx] - 2.0) < 1e-6


def test_lorentzian_peak_value_at_center():
    x = np.linspace(-5, 5, 1001)
    y = lorentzian(x, amplitude=3.0, center=0.5, gamma=0.2)
    idx = int(np.argmax(y))
    assert abs(x[idx] - 0.5) < 0.01
    assert abs(y[idx] - 3.0) < 1e-6


def test_pseudo_voigt_blends_g_and_l():
    """At eta=0 pV should match Gaussian; at eta=1 it should match Lorentzian."""
    x = np.linspace(-5, 5, 1001)
    a, c, gamma = 1.5, 0.0, 0.3
    pv0 = pseudo_voigt(x, a, c, gamma, eta=0.0)
    pv1 = pseudo_voigt(x, a, c, gamma, eta=1.0)
    sigma = gamma / np.sqrt(2 * np.log(2))
    g = gaussian(x, a, c, sigma)
    l = lorentzian(x, a, c, gamma)
    assert np.allclose(pv0, g, atol=1e-9)
    assert np.allclose(pv1, l, atol=1e-9)


def test_fitted_peak_fwhm():
    """Gaussian FWHM = 2.355·σ, Lorentzian FWHM = 2γ."""
    g = FittedPeak(PeakShape.GAUSSIAN, 1.0, 0.0, 1.0)
    l = FittedPeak(PeakShape.LORENTZIAN, 1.0, 0.0, 1.0)
    assert abs(g.fwhm - 2.0 * np.sqrt(2.0 * np.log(2.0))) < 1e-9
    assert abs(l.fwhm - 2.0) < 1e-9


# =============================================================================
# Peak detection
# =============================================================================

def test_detect_peaks_finds_two_gaussians():
    x = np.linspace(0, 100, 2001)
    y = (gaussian(x, 1.0, 30.0, 1.5) + gaussian(x, 0.7, 70.0, 2.0))
    peaks = detect_peaks(x, y, n_max=4)
    assert len(peaks) == 2
    centers = sorted(p[0] for p in peaks)
    assert abs(centers[0] - 30.0) < 1.0
    assert abs(centers[1] - 70.0) < 1.0


def test_detect_peaks_returns_empty_for_flat_signal():
    x = np.linspace(0, 10, 200)
    y = np.zeros_like(x)
    assert detect_peaks(x, y) == []


def test_detect_peaks_respects_n_max():
    x = np.linspace(0, 100, 2001)
    y = (gaussian(x, 1.0, 20.0, 1.0) + gaussian(x, 1.5, 50.0, 1.0)
         + gaussian(x, 0.8, 80.0, 1.0))
    peaks = detect_peaks(x, y, n_max=2)
    assert len(peaks) == 2


# =============================================================================
# Multi-peak fit (synthetic ground truth)
# =============================================================================

def test_fit_multipeak_recovers_two_gaussians_no_baseline():
    rng = np.random.default_rng(42)
    x = np.linspace(0, 100, 2001)
    true = (gaussian(x, 1.0, 30.0, 2.0) + gaussian(x, 0.6, 70.0, 3.0))
    y = true + 0.005 * rng.standard_normal(x.size)

    res = fit_multipeak(x, y, shape=PeakShape.GAUSSIAN, baseline_degree=0)

    assert res.success
    assert len(res.peaks) == 2
    centers = sorted(p.center for p in res.peaks)
    widths = [p.width for p in sorted(res.peaks, key=lambda p: p.center)]
    assert abs(centers[0] - 30.0) < 0.5
    assert abs(centers[1] - 70.0) < 0.5
    assert abs(widths[0] - 2.0) < 0.3
    assert abs(widths[1] - 3.0) < 0.3
    assert res.rsq > 0.99


def test_fit_multipeak_recovers_baseline_plus_one_peak():
    """Linear baseline + single Lorentzian: fit should recover both."""
    rng = np.random.default_rng(7)
    x = np.linspace(-10, 10, 1001)
    baseline = 0.5 * x + 2.0
    peak = lorentzian(x, amplitude=4.0, center=0.0, gamma=1.0)
    y = baseline + peak + 0.005 * rng.standard_normal(x.size)

    res = fit_multipeak(x, y, shape=PeakShape.LORENTZIAN, baseline_degree=1)
    assert res.success
    assert len(res.peaks) == 1
    p = res.peaks[0]
    assert abs(p.center - 0.0) < 0.1
    assert abs(p.width - 1.0) < 0.1
    assert abs(p.amplitude - 4.0) < 0.2
    # Baseline coefficients (highest order first): [slope, intercept].
    assert abs(res.baseline_coeffs[0] - 0.5) < 0.05
    assert abs(res.baseline_coeffs[-1] - 2.0) < 0.1
    assert res.rsq > 0.99


def test_fit_multipeak_returns_components_per_peak():
    x = np.linspace(0, 50, 1001)
    y = gaussian(x, 1.0, 15.0, 1.5) + gaussian(x, 1.5, 35.0, 2.0)
    res = fit_multipeak(x, y, shape=PeakShape.GAUSSIAN, baseline_degree=0)
    assert len(res.components) == len(res.peaks)
    # Sum of components + baseline should equal fitted_curve.
    rebuilt = res.baseline_curve.copy()
    for c in res.components:
        rebuilt = rebuilt + c
    assert np.allclose(rebuilt, res.fitted_curve, atol=1e-9)


def test_fit_multipeak_with_explicit_seeds():
    """User-supplied initial peaks override auto-detect."""
    x = np.linspace(0, 100, 2001)
    y = gaussian(x, 1.0, 30.0, 2.0) + gaussian(x, 0.6, 70.0, 3.0)
    res = fit_multipeak(
        x, y, shape=PeakShape.GAUSSIAN, baseline_degree=-1,
        initial_peaks=[(30.0, 1.0, 2.0), (70.0, 0.6, 3.0)],
    )
    assert res.success and len(res.peaks) == 2


def test_fit_multipeak_no_peaks_returns_baseline_only():
    x = np.linspace(0, 10, 201)
    y = 0.3 * x + 1.5
    res = fit_multipeak(
        x, y, shape=PeakShape.GAUSSIAN, baseline_degree=1,
        initial_peaks=[],
    )
    assert res.success
    assert res.peaks == []
    assert np.allclose(res.fitted_curve, y, atol=1e-6)


def test_fit_multipeak_pseudo_voigt_mixing_in_range():
    rng = np.random.default_rng(13)
    x = np.linspace(-5, 5, 1001)
    y = pseudo_voigt(x, 1.0, 0.0, 0.5, 0.4) + 0.005 * rng.standard_normal(x.size)
    res = fit_multipeak(x, y, shape=PeakShape.PSEUDO_VOIGT, baseline_degree=0)
    assert res.success
    p = res.peaks[0]
    assert p.eta is not None
    assert 0.0 <= p.eta <= 1.0
    assert abs(p.center) < 0.05
    assert abs(p.width - 0.5) < 0.05


def test_fit_multipeak_validates_shape_argument():
    x = np.linspace(0, 10, 100)
    y = np.zeros_like(x)
    with pytest.raises(ValueError):
        fit_multipeak(x, y, shape="not_a_shape", baseline_degree=0)


def test_fit_multipeak_handles_short_array():
    with pytest.raises(ValueError):
        fit_multipeak(np.array([0.0, 1.0]), np.array([1.0, 2.0]),
                      shape=PeakShape.GAUSSIAN, baseline_degree=0)


# =============================================================================
# Fit-quality metrics
# =============================================================================

def test_rsq_perfect_fit_is_one():
    x = np.linspace(0, 10, 501)
    y = gaussian(x, 1.0, 5.0, 0.5)
    res = fit_multipeak(
        x, y, shape=PeakShape.GAUSSIAN, baseline_degree=-1,
        initial_peaks=[(5.0, 1.0, 0.5)],
    )
    assert res.rsq > 0.999
    assert res.rss < 1e-3
