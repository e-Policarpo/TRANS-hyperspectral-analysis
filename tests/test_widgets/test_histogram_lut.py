"""
Tests for the ported ``HistogramState`` + ``compute_histogram``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.widgets._pyqtgraph_ports.histogram_lut import (
    HistogramState,
    compute_histogram,
)


# --- HistogramState ------------------------------------------------

def test_state_defaults():
    s = HistogramState()
    assert s.display_min == 0.0
    assert s.display_max == 1.0
    assert s.colormap == "original"
    assert s.n_bins == 256


def test_state_round_trip():
    s = HistogramState(
        display_min=10.0, display_max=200.0,
        colormap="viridis", n_bins=128,
    )
    other = HistogramState.from_state(s.get_state())
    assert other.display_min == 10.0
    assert other.display_max == 200.0
    assert other.colormap == "viridis"
    assert other.n_bins == 128


def test_apply_state_partial_payload():
    s = HistogramState(display_min=0.0, display_max=1.0)
    s.apply_state({"display_min": 5.0})
    assert s.display_min == 5.0
    # Other fields unchanged.
    assert s.display_max == 1.0


def test_apply_state_ignores_bogus_n_bins():
    s = HistogramState(n_bins=256)
    s.apply_state({"n_bins": -1})
    assert s.n_bins == 256
    s.apply_state({"n_bins": "not an int"})
    assert s.n_bins == 256


def test_set_levels_returns_changed_flag():
    s = HistogramState()
    assert s.set_levels(0.0, 1.0) is False  # already these values
    assert s.set_levels(5.0, 10.0) is True
    assert s.display_min == 5.0
    assert s.display_max == 10.0


def test_set_levels_swaps_if_inverted():
    s = HistogramState()
    s.set_levels(10.0, 5.0)  # lo > hi → swap
    assert s.display_min == 5.0
    assert s.display_max == 10.0


# --- compute_histogram ---------------------------------------------

def test_histogram_returns_n_bins():
    arr = np.linspace(0.0, 1.0, 1000).reshape(100, 10)
    centres, counts = compute_histogram(arr, n_bins=64)
    assert centres.shape == (64,)
    assert counts.shape == (64,)


def test_histogram_counts_sum_to_total_finite():
    arr = np.linspace(0.0, 10.0, 1000)
    _, counts = compute_histogram(
        arr, n_bins=10, levels=(0.0, 10.0),
        max_samples=None,
    )
    assert int(counts.sum()) == 1000


def test_histogram_drops_nan_inf():
    arr = np.array([
        [1.0, 2.0, np.nan],
        [np.inf, 3.0, -np.inf],
    ], dtype=np.float32)
    _, counts = compute_histogram(
        arr, n_bins=4, levels=(1.0, 4.0),
        max_samples=None,
    )
    # Only 3 finite samples (1, 2, 3) survive.
    assert int(counts.sum()) == 3


def test_histogram_empty_array_returns_zeros():
    arr = np.array([], dtype=np.float32)
    centres, counts = compute_histogram(arr, n_bins=10)
    assert counts.shape == (10,)
    assert int(counts.sum()) == 0


def test_histogram_all_nan_returns_zeros():
    arr = np.full((4, 4), np.nan, dtype=np.float32)
    _, counts = compute_histogram(arr, n_bins=10)
    assert int(counts.sum()) == 0


def test_histogram_degenerate_levels_does_not_divide_zero():
    """When the data is constant, the histogram still has to return
    a usable axis instead of dividing by zero."""
    arr = np.full((8, 8), 42.0, dtype=np.float32)
    centres, counts = compute_histogram(arr, n_bins=10, levels=None)
    # No exception thrown; the constant sample lands in some bin.
    assert int(counts.sum()) > 0


def test_histogram_explicit_levels_respects_range():
    arr = np.linspace(0.0, 100.0, 100)
    centres, counts = compute_histogram(
        arr, n_bins=10, levels=(0.0, 50.0),
        max_samples=None,
    )
    # All bin centres in [0, 50].
    assert centres.min() >= 0.0 and centres.max() <= 50.0
    # Samples > 50 fall outside the range and are dropped by histogram.
    # The first 50 (or so) samples land in [0, 50].
    assert 40 <= int(counts.sum()) <= 50


def test_histogram_strided_subsample_when_oversized():
    """When the input is larger than ``max_samples``, the helper
    strides through it — counts should be a fixed-stride subset of
    the full-resolution histogram, not zero."""
    arr = np.linspace(0.0, 1.0, 100_000)
    _, counts = compute_histogram(
        arr, n_bins=10, levels=(0.0, 1.0), max_samples=1000,
    )
    # ~1000 strided samples land across 10 bins → each bin ~100±.
    assert int(counts.sum()) > 0
    assert int(counts.sum()) <= 1100


def test_histogram_bad_n_bins_raises():
    with pytest.raises(ValueError):
        compute_histogram(
            np.zeros((4, 4), dtype=np.float32),
            n_bins=0,
        )
