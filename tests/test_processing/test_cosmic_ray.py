"""
Tests for the cosmic-ray / hot-pixel filter.

Synthetic spectra inject single- and two-sample spikes on top of either
flat noise or a real Lorentzian peak, and verify that the spikes are
removed while the real peak is preserved.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processing.cosmic_ray import remove_cosmic_rays, remove_cosmic_rays_2d


def _lorentzian(x, amplitude, center, gamma):
    return amplitude * (gamma ** 2) / ((x - center) ** 2 + gamma ** 2)


def test_remove_cosmic_rays_replaces_single_pixel_spike():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 100, 1001)
    y = 0.01 * rng.standard_normal(x.size)
    spike_idx = 500
    y[spike_idx] += 50.0  # massive spike, ~5000σ above noise

    cleaned, mask = remove_cosmic_rays(y)

    assert mask[spike_idx]
    assert mask.sum() == 1
    # The cleaned value should be back near the local noise scale.
    assert abs(cleaned[spike_idx]) < 0.1


def test_remove_cosmic_rays_replaces_two_pixel_spike():
    rng = np.random.default_rng(1)
    x = np.linspace(0, 100, 1001)
    y = 0.01 * rng.standard_normal(x.size)
    y[400:402] += 30.0

    cleaned, mask = remove_cosmic_rays(y, max_width=2)

    assert mask[400] and mask[401]
    assert mask.sum() == 2
    assert np.max(np.abs(cleaned[400:402])) < 0.1


def test_remove_cosmic_rays_preserves_real_peak():
    """A genuine narrow Lorentzian (~10 samples FWHM) must not be flagged."""
    rng = np.random.default_rng(2)
    x = np.linspace(0, 100, 1001)
    noise = 0.005 * rng.standard_normal(x.size)
    peak = _lorentzian(x, amplitude=1.0, center=50.0, gamma=0.5)  # ~10 samples
    y = peak + noise

    _cleaned, mask = remove_cosmic_rays(y)
    # Default max_width=2 is much narrower than the Lorentzian, so nothing
    # should be flagged.
    assert mask.sum() == 0


def test_remove_cosmic_rays_returns_input_when_no_spikes():
    rng = np.random.default_rng(3)
    y = 0.01 * rng.standard_normal(2001)
    cleaned, mask = remove_cosmic_rays(y)
    assert mask.sum() == 0
    np.testing.assert_array_equal(cleaned, y)


def test_remove_cosmic_rays_handles_short_input():
    y = np.array([0.0, 1.0, 0.0])
    cleaned, mask = remove_cosmic_rays(y)
    np.testing.assert_array_equal(cleaned, y)
    assert mask.shape == y.shape
    assert mask.sum() == 0


def test_remove_cosmic_rays_2d_processes_each_column_independently():
    rng = np.random.default_rng(4)
    n_samples = 1001
    n_spectra = 8
    spectra = 0.01 * rng.standard_normal((n_samples, n_spectra))
    # Spikes in three different spectra at three different locations.
    spectra[200, 0] += 30.0
    spectra[500, 3] += 30.0
    spectra[800, 7] += 30.0

    cleaned, mask = remove_cosmic_rays_2d(spectra)

    assert mask[200, 0] and mask[500, 3] and mask[800, 7]
    # Other columns should not be affected at those rows.
    assert mask[200, 1:].sum() == 0
    assert mask[500, [0, 1, 2, 4, 5, 6, 7]].sum() == 0
    # Cleaned values are pulled back to the local noise scale.
    assert np.abs(cleaned[200, 0]) < 0.1
    assert np.abs(cleaned[500, 3]) < 0.1
    assert np.abs(cleaned[800, 7]) < 0.1


def test_remove_cosmic_rays_2d_raises_on_wrong_dim():
    with pytest.raises(ValueError):
        remove_cosmic_rays_2d(np.zeros(100))
