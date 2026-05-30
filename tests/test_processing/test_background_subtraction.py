"""
Tests for src.processing.background_subtraction.

Covers the three axis-alignment branches: identical axes, signal axis
inside the background axis (full coverage but different sampling), and
partial overlap that requires truncation.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.processing.background_subtraction import subtract_background


def _make_spectral(x, columns):
    """Build a SpectralData from an axis and a dict of column→1-D values."""
    df = pd.DataFrame({"X": x, **columns})
    metadata = SpectralMetadata(
        source_type="test", dimensions=(1, 1), scan_mode="point",
        units={"x": "nm"}, additional_info={},
    )
    return SpectralData(df, metadata)


def test_subtract_background_identical_axis():
    x = np.linspace(400.0, 600.0, 201)
    bg_curve = 0.5 + 0.001 * x
    sig = _make_spectral(x, {"S1": 2.0 + bg_curve, "S2": 5.0 + bg_curve})
    bg = _make_spectral(x, {"bg1": bg_curve, "bg2": bg_curve})

    result = subtract_background(sig, bg)
    assert not result.truncated
    assert result.samples_kept == 201
    corrected = result.corrected.spectra.values
    # S1 - bg = 2; S2 - bg = 5.
    np.testing.assert_allclose(corrected[:, 0], 2.0, atol=1e-9)
    np.testing.assert_allclose(corrected[:, 1], 5.0, atol=1e-9)


def test_subtract_background_resamples_when_background_denser():
    """Background sampled finer than signal → interpolate down to signal grid."""
    sig_x = np.linspace(400.0, 600.0, 101)
    bg_x = np.linspace(400.0, 600.0, 401)
    bg_curve_sig = 1.0 + 0.01 * sig_x
    bg_curve_dense = 1.0 + 0.01 * bg_x
    sig = _make_spectral(sig_x, {"S1": 3.0 + bg_curve_sig})
    bg = _make_spectral(bg_x, {"bg1": bg_curve_dense})

    result = subtract_background(sig, bg)
    assert not result.truncated
    assert result.samples_kept == sig_x.size
    np.testing.assert_allclose(
        result.corrected.spectra.values[:, 0], 3.0, atol=1e-9,
    )


def test_subtract_background_truncates_to_overlap():
    sig_x = np.linspace(400.0, 700.0, 301)
    bg_x = np.linspace(450.0, 650.0, 201)
    bg_curve = 0.3 + 0.0001 * bg_x
    bg_on_sig = 0.3 + 0.0001 * sig_x
    sig = _make_spectral(sig_x, {"S1": 1.0 + bg_on_sig})
    bg = _make_spectral(bg_x, {"bg1": bg_curve})

    result = subtract_background(sig, bg)
    assert result.truncated
    assert result.overlap_range == pytest.approx((450.0, 650.0))
    # Only samples inside [450, 650] should survive.
    kept_x = result.corrected.independent_var
    assert kept_x.min() >= 450.0 and kept_x.max() <= 650.0
    np.testing.assert_allclose(
        result.corrected.spectra.values[:, 0], 1.0, atol=1e-9,
    )


def test_subtract_background_raises_on_no_overlap():
    sig = _make_spectral(np.linspace(400.0, 500.0, 101), {"S": np.zeros(101)})
    bg = _make_spectral(np.linspace(600.0, 700.0, 101), {"bg": np.zeros(101)})
    with pytest.raises(ValueError, match="do not overlap"):
        subtract_background(sig, bg)


def test_subtract_background_records_overlap_in_metadata():
    sig_x = np.linspace(400.0, 700.0, 301)
    bg_x = np.linspace(450.0, 650.0, 101)
    sig = _make_spectral(sig_x, {"S": np.ones(301)})
    bg = _make_spectral(bg_x, {"bg": np.zeros(101)})

    result = subtract_background(sig, bg)
    info = result.corrected.metadata.additional_info["background_subtraction"]
    assert info["truncated"] is True
    assert info["overlap_range"] == (450.0, 650.0)
    assert info["samples_kept"] == int((sig_x >= 450.0).sum()
                                       - (sig_x > 650.0).sum())
