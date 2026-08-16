"""
Tests for src.processing.peak_detection.

The central case is the STS shape from the confinement analysis: exponential
band edges around 4e-7 with in-gap states around 1e-8. A percentage height
threshold over the full sweep sees only the edges, and the whole point of the
polynomial background is that the small features survive it without having to
hand-pick a narrow window around them.

Also covers the three baseline estimators moved here from
backend.tool_implementations, which must keep behaving exactly as before.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processing import peak_detection as pd_mod
from src.processing.peak_detection import (
    Analysis,
    BASELINE_KINDS,
    Params,
    Peak,
    analyze,
    analyze_many,
    als_baseline,
    endpoint_baseline,
    estimate_baseline,
    find_peaks,
    moving_average,
    peak_matrix,
    polynomial_baseline,
    rubberband_baseline,
    savgol,
    smooth,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

GAP_CENTERS = (-0.25, -0.10, 0.08, 0.22)


def _gaussians(x, centers, amplitude=2e-7, width=0.012):
    y = np.zeros_like(x)
    for c in centers:
        y = y + amplitude * np.exp(-0.5 * ((x - c) / width) ** 2)
    return y


def _sts_curve(n=512, gap_amplitude=1.2e-8):
    """Exponential band edges (~4e-7) plus four small in-gap states (~1e-8)."""
    x = np.linspace(-0.6, 0.6, n)
    band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
    y = band_edges + _gaussians(x, GAP_CENTERS, amplitude=gap_amplitude, width=0.008)
    return x, y


def _flat_curve(centers=GAP_CENTERS, n=512):
    """Same peaks on a flat background, so detection needs no help."""
    x = np.linspace(-0.6, 0.6, n)
    return x, 1e-9 + _gaussians(x, centers)


def _centers(peaks, ndigits=2):
    return [round(p.x, ndigits) for p in peaks]


# ---------------------------------------------------------------------------
# Smoothing
# ---------------------------------------------------------------------------

def test_smooth_none_and_zero_width_are_noops():
    y = np.array([1.0, 5.0, 2.0, 8.0, 3.0])
    np.testing.assert_array_equal(smooth(y, "none", 3), y)
    np.testing.assert_array_equal(smooth(y, "average", 0), y)


def test_moving_average_spans_two_half_widths_plus_one():
    y = np.zeros(21)
    y[10] = 1.0
    smoothed = moving_average(y, 2)
    # A 5-sample window spreads the spike over exactly 5 samples, each 1/5.
    assert np.count_nonzero(smoothed) == 5
    np.testing.assert_allclose(smoothed[8:13], 0.2)
    np.testing.assert_allclose(smoothed.sum(), 1.0)


def test_moving_average_preserves_length_and_edges():
    y = np.linspace(0.0, 1.0, 50)
    smoothed = moving_average(y, 3)
    assert smoothed.shape == y.shape
    # A straight line survives an edge-padded moving average in the interior.
    np.testing.assert_allclose(smoothed[10:40], y[10:40], atol=1e-12)


def test_window_larger_than_data_is_a_noop():
    y = np.array([1.0, 2.0, 3.0])
    np.testing.assert_array_equal(moving_average(y, 10), y)
    np.testing.assert_array_equal(savgol(y, 10), y)


def test_smooth_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown smoother"):
        smooth(np.zeros(10), "bilateral", 2)


# ---------------------------------------------------------------------------
# Background estimation
# ---------------------------------------------------------------------------

def test_baseline_none_returns_zeros():
    x, y = _sts_curve()
    np.testing.assert_array_equal(estimate_baseline(x, y, "none"), np.zeros_like(y))


def test_estimate_baseline_rejects_unknown_kind():
    x, y = _flat_curve()
    with pytest.raises(ValueError, match="Unknown background method"):
        estimate_baseline(x, y, "wavelet")


@pytest.mark.parametrize("kind", [k for k in BASELINE_KINDS if k != "none"])
def test_every_baseline_returns_a_finite_curve_of_the_right_shape(kind):
    x, y = _sts_curve()
    baseline = estimate_baseline(x, y, kind, degree=3)
    assert baseline.shape == y.shape
    assert np.all(np.isfinite(baseline))


def test_poly_iter_tracks_background_and_ignores_peaks():
    """The whole reason poly-iter exists: a plain fit is dragged up by peaks."""
    x = np.linspace(-1.0, 1.0, 400)
    true_background = 3.0 + 0.5 * x + 2.0 * x ** 2
    y = true_background + _gaussians(x, (-0.3, 0.4), amplitude=5.0, width=0.02)

    plain = polynomial_baseline(x, y, "poly", degree=2)
    stripped = polynomial_baseline(x, y, "poly-iter", degree=2)

    plain_error = np.max(np.abs(plain - true_background))
    stripped_error = np.max(np.abs(stripped - true_background))
    assert stripped_error < plain_error / 5
    assert stripped_error < 0.05


def test_poly_iter_does_not_drift_with_more_iterations():
    """Clipping against the original spectrum converges; against the running
    result it wanders off the background the longer it runs."""
    x = np.linspace(-1.0, 1.0, 400)
    true_background = 3.0 + 0.5 * x + 2.0 * x ** 2
    y = true_background + _gaussians(x, (-0.3, 0.4), amplitude=5.0, width=0.02)

    errors = [
        np.max(np.abs(polynomial_baseline(x, y, "poly-iter", 2, iterations=n) - true_background))
        for n in (5, 25, 100)
    ]
    assert max(errors) < 0.05
    assert errors[2] <= errors[0] + 1e-6


def test_poly_iter_clips_the_other_way_for_negative_peaks():
    x = np.linspace(-1.0, 1.0, 400)
    true_background = 1.0 + 0.3 * x
    y = true_background - _gaussians(x, (0.1,), amplitude=4.0, width=0.02)

    stripped = polynomial_baseline(x, y, "poly-iter", degree=1, direction="negative")
    assert np.max(np.abs(stripped - true_background)) < 0.05


def test_polynomial_baseline_handles_degenerate_input():
    x = np.linspace(0.0, 1.0, 50)
    # All-zero signal has no scale to normalise by.
    np.testing.assert_array_equal(polynomial_baseline(x, np.zeros(50)), np.zeros(50))
    # Fewer samples than the polynomial needs.
    short_x, short_y = np.arange(3.0), np.ones(3)
    np.testing.assert_array_equal(polynomial_baseline(short_x, short_y, degree=5), np.zeros(3))
    # Degree 0 is a constant offset, not a crash.
    assert polynomial_baseline(x, np.ones(50), "poly", degree=0).shape == (50,)


def test_polynomial_baseline_survives_tiny_magnitudes():
    """y ~ 1e-7 against x ~ 1e-1 is the actual STS conditioning problem."""
    x, y = _sts_curve()
    baseline = polynomial_baseline(x, y, "poly-iter", degree=5)
    assert np.all(np.isfinite(baseline))
    assert np.max(np.abs(baseline)) < 10 * np.max(np.abs(y))


# --- the three estimators moved out of tool_implementations ----------------

def test_als_baseline_stays_below_peaks():
    x = np.linspace(0.0, 10.0, 300)
    y = 1.0 + 0.1 * x + _gaussians(x, (3.0, 7.0), amplitude=5.0, width=0.15)
    baseline = als_baseline(y, lam=1e5, p=0.01)
    assert baseline.shape == y.shape
    peak_idx = int(np.argmax(y))
    assert baseline[peak_idx] < y[peak_idx] / 2


def test_rubberband_baseline_anchors_on_the_endpoints():
    x = np.linspace(0.0, 10.0, 300)
    y = 2.0 + _gaussians(x, (5.0,), amplitude=4.0, width=0.3)
    baseline = rubberband_baseline(x, y)

    assert baseline.shape == y.shape
    assert np.all(np.isfinite(baseline))
    np.testing.assert_allclose(baseline[0], y[0], rtol=1e-6)
    np.testing.assert_allclose(baseline[-1], y[-1], rtol=1e-6)


def test_rubberband_baseline_stays_under_the_curve():
    """Regression: the hull used to keep every vertex, including the peak
    apex, so the 'baseline' was a tent over the peak that erased it."""
    x = np.linspace(0.0, 10.0, 300)
    y = 2.0 + _gaussians(x, (5.0,), amplitude=4.0, width=0.3)

    baseline = rubberband_baseline(x, y)
    assert np.all(baseline <= y + 1e-9)
    # Flat floor either side of the peak, and the peak survives subtraction.
    np.testing.assert_allclose(baseline, 2.0, atol=1e-9)
    assert np.max(y - baseline) == pytest.approx(4.0, abs=0.01)


def test_rubberband_baseline_handles_a_descending_axis():
    """STS sweeps are sometimes stored high-to-low."""
    x = np.linspace(0.0, 10.0, 300)
    y = 2.0 + _gaussians(x, (5.0,), amplitude=4.0, width=0.3)

    forward = rubberband_baseline(x, y)
    reversed_ = rubberband_baseline(x[::-1], y[::-1])
    np.testing.assert_allclose(reversed_, forward[::-1], atol=1e-9)


def test_rubberband_baseline_follows_a_sloping_floor():
    x = np.linspace(0.0, 10.0, 300)
    slope = 1.0 + 0.3 * x
    y = slope + _gaussians(x, (5.0,), amplitude=4.0, width=0.3)

    baseline = rubberband_baseline(x, y)
    np.testing.assert_allclose(baseline, slope, atol=1e-6)


def test_rubberband_baseline_falls_back_on_degenerate_input():
    x = np.linspace(0.0, 1.0, 50)
    flat = rubberband_baseline(x, np.full(50, 3.0))
    np.testing.assert_allclose(flat, 3.0, atol=1e-9)


def test_endpoint_baseline_fits_only_the_ends():
    x = np.linspace(0.0, 10.0, 300)
    trend = 1.0 + 0.4 * x
    y = trend + _gaussians(x, (5.0,), amplitude=8.0, width=0.3)
    baseline = endpoint_baseline(x, y, n_points=20, degree=1)
    # The middle bump must not tilt a line fitted to the endpoints.
    np.testing.assert_allclose(baseline, trend, atol=1e-6)


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------

def test_finds_known_peaks_on_a_flat_background():
    x, y = _flat_curve()
    peaks = find_peaks(x, y, Params(height=5.0))
    assert _centers(peaks) == [round(c, 2) for c in GAP_CENTERS]


def test_band_edges_hide_in_gap_states_without_a_background():
    """The by-hand problem: 5% of the band edges buries everything else."""
    x, y = _sts_curve()
    assert find_peaks(x, y, Params(height=5.0, baseline="none")) == []


def test_polynomial_background_recovers_the_in_gap_states():
    x, y = _sts_curve()
    peaks = find_peaks(x, y, Params(height=5.0, baseline="poly-iter", baseline_degree=5))
    found = _centers(peaks)
    for center in GAP_CENTERS:
        assert round(center, 2) in found


def test_narrow_search_window_is_the_other_way_to_find_them():
    """Restricting the range rescales the threshold, as the QtiPlot flow does."""
    x, y = _sts_curve()
    peaks = find_peaks(x, y, Params(height=5.0, xmin=-0.3, xmax=0.3))
    assert _centers(peaks) == [round(c, 2) for c in GAP_CENTERS]


def test_window_bounds_exclude_outside_peaks():
    x, y = _flat_curve()
    peaks = find_peaks(x, y, Params(xmin=-0.15, xmax=0.15))
    assert _centers(peaks) == [-0.1, 0.08]


def test_direction_negative_finds_troughs():
    x = np.linspace(-0.6, 0.6, 512)
    y = 1.0 - _gaussians(x, (-0.2, 0.3), amplitude=0.5, width=0.01)
    peaks = find_peaks(x, y, Params(direction="negative"))
    assert _centers(peaks, 1) == [-0.2, 0.3]


def test_direction_both_finds_peaks_and_troughs():
    x = np.linspace(-0.6, 0.6, 512)
    y = 1.0 + _gaussians(x, (-0.2,), amplitude=0.5, width=0.01) \
        - _gaussians(x, (0.3,), amplitude=0.5, width=0.01)
    assert _centers(find_peaks(x, y, Params(direction="both")), 1) == [-0.2, 0.3]


def test_higher_threshold_rejects_smaller_peaks():
    x = np.linspace(-0.6, 0.6, 512)
    y = _gaussians(x, (-0.2,), amplitude=1.0, width=0.01) \
        + _gaussians(x, (0.2,), amplitude=0.1, width=0.01)
    assert len(find_peaks(x, y, Params(height=1.0))) == 2
    assert _centers(find_peaks(x, y, Params(height=50.0)), 1) == [-0.2]


def test_max_peaks_keeps_the_most_prominent_in_x_order():
    x = np.linspace(-0.6, 0.6, 512)
    y = (_gaussians(x, (-0.4,), amplitude=0.2, width=0.01)
         + _gaussians(x, (0.0,), amplitude=1.0, width=0.01)
         + _gaussians(x, (0.4,), amplitude=0.6, width=0.01))
    peaks = find_peaks(x, y, Params(max_peaks=2))
    assert _centers(peaks, 1) == [0.0, 0.4]


def test_min_distance_thins_neighbours_keeping_the_strongest():
    x = np.linspace(-0.6, 0.6, 512)
    y = (_gaussians(x, (0.00,), amplitude=1.0, width=0.004)
         + _gaussians(x, (0.02,), amplitude=0.5, width=0.004))
    assert len(find_peaks(x, y, Params(height=1.0))) == 2
    peaks = find_peaks(x, y, Params(height=1.0, min_distance=0.05))
    assert _centers(peaks, 2) == [0.0]


def test_smoothing_suppresses_noise_peaks():
    rng = np.random.default_rng(3)
    x = np.linspace(-0.6, 0.6, 512)
    y = _gaussians(x, (-0.25, 0.0, 0.2), amplitude=2e-7, width=0.012) \
        + rng.normal(0, 8e-9, x.size)

    raw = len(find_peaks(x, y, Params()))
    smoothed = len(find_peaks(x, y, Params(smooth_points=3)))
    assert smoothed < raw / 2

    # Derivative smoothing is the other lever on the same noise.
    deriv = len(find_peaks(x, y, Params(deriv_smooth_type="savgol", deriv_smooth_points=4)))
    assert deriv < raw


def test_interpolated_centre_lands_between_samples():
    x = np.linspace(-0.6, 0.6, 201)
    y = _gaussians(x, (0.1234,), amplitude=1.0, width=0.02)

    grid = find_peaks(x, y, Params())[0]
    fine = find_peaks(x, y, Params(interpolate_center=True))[0]
    assert grid.index == fine.index
    assert abs(fine.x - 0.1234) < abs(grid.x - 0.1234)


def test_peak_carries_raw_and_corrected_heights():
    x = np.linspace(-1.0, 1.0, 400)
    y = 10.0 + _gaussians(x, (0.0,), amplitude=1.0, width=0.05)
    peak = find_peaks(x, y, Params(baseline="poly-iter", baseline_degree=1))[0]
    assert peak.y == pytest.approx(11.0, abs=0.05)
    assert peak.y_corrected == pytest.approx(1.0, abs=0.05)
    assert peak.prominence > 0


def test_peak_index_addresses_the_full_spectrum_not_the_window():
    x, y = _flat_curve()
    peaks = find_peaks(x, y, Params(xmin=0.0, xmax=0.4))
    assert peaks, "expected the 0.08 and 0.22 peaks"
    for pk in peaks:
        assert x[pk.index] == pytest.approx(pk.x, abs=1e-9)


def test_nan_samples_are_skipped_without_crashing():
    x, y = _flat_curve()
    y = y.copy()
    y[[5, 6, 400]] = np.nan
    peaks = find_peaks(x, y, Params())
    assert _centers(peaks) == [round(c, 2) for c in GAP_CENTERS]


def test_too_few_samples_returns_an_empty_analysis():
    result = analyze(np.array([0.0, 1.0]), np.array([1.0, 2.0]))
    assert result.peaks == []
    assert isinstance(result, Analysis)


def test_flat_curve_has_no_peaks():
    x = np.linspace(0.0, 1.0, 200)
    assert find_peaks(x, np.ones_like(x)) == []


# ---------------------------------------------------------------------------
# Params validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs, message", [
    ({"baseline": "wavelet"}, "baseline must be one of"),
    ({"direction": "up"}, "direction must be one of"),
    ({"height_mode": "absolute"}, "height_mode must be one of"),
    ({"smooth_type": "bilateral"}, "smooth_type must be one of"),
    ({"deriv_smooth_type": "bilateral"}, "deriv_smooth_type must be one of"),
    ({"xmin": 0.5, "xmax": 0.1}, "must be below"),
])
def test_params_validate_rejects_bad_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Params(**kwargs).validate()


def test_params_validate_accepts_defaults():
    Params().validate()


# ---------------------------------------------------------------------------
# Batch entry points
# ---------------------------------------------------------------------------

def test_analyze_many_runs_every_column():
    x = np.linspace(-0.6, 0.6, 300)
    spectra = np.column_stack([
        _gaussians(x, (-0.2,)),
        _gaussians(x, (0.0, 0.3)),
        np.zeros_like(x),
    ])
    results = analyze_many(x, spectra)
    assert [len(r.peaks) for r in results] == [1, 2, 0]


def test_analyze_many_accepts_a_single_spectrum():
    x, y = _flat_curve()
    assert len(analyze_many(x, y)) == 1


def test_analyze_many_reports_progress_and_honours_cancel():
    x = np.linspace(-0.6, 0.6, 100)
    spectra = np.column_stack([_gaussians(x, (0.0,))] * 6)

    seen = []
    analyze_many(x, spectra, on_progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 6) for i in range(1, 7)]

    calls = {"n": 0}

    def cancel_after_two():
        calls["n"] += 1
        return calls["n"] > 2

    partial = analyze_many(x, spectra, should_cancel=cancel_after_two)
    assert len(partial) == 2


def test_analyze_many_validates_params_once():
    x, y = _flat_curve()
    with pytest.raises(ValueError, match="direction must be one of"):
        analyze_many(x, y, Params(direction="sideways"))


def test_peak_matrix_marks_centres_only():
    x = np.linspace(-0.6, 0.6, 300)
    spectra = np.column_stack([_gaussians(x, (-0.2,)), _gaussians(x, (0.0, 0.3))])
    results = analyze_many(x, spectra)

    matrix = peak_matrix(len(x), results)
    assert matrix.shape == (300, 2)
    assert matrix.dtype == np.float32
    # 1 at a peak, blank everywhere else -- no zeros to read past.
    assert set(np.unique(matrix[np.isfinite(matrix)])) == {1}
    assert np.nansum(matrix[:, 0]) == 1
    assert np.nansum(matrix[:, 1]) == 2

    # Every mark sits on a detected centre.
    for col, result in enumerate(results):
        assert sorted(np.flatnonzero(matrix[:, col] == 1)) == sorted(p.index for p in result.peaks)


def test_peak_matrix_of_no_results_is_empty():
    assert peak_matrix(10, []).shape == (10, 0)


# ---------------------------------------------------------------------------
# params_from_dict (the QML / workflow boundary)
# ---------------------------------------------------------------------------

def test_params_from_dict_defaults_on_empty():
    assert pd_mod.params_from_dict(None) == Params()
    assert pd_mod.params_from_dict({}) == Params()


def test_params_from_dict_casts_qml_floats_to_int():
    """QML hands every number over as a float; scipy and range() need ints."""
    p = pd_mod.params_from_dict({
        'baseline_degree': 5.0, 'baseline_iterations': 30.0,
        'smooth_points': 3.0, 'deriv_smooth_points': 2.0, 'endpoint_points': 12.0,
    })
    for field in ('baseline_degree', 'baseline_iterations', 'smooth_points',
                  'deriv_smooth_points', 'endpoint_points'):
        assert isinstance(getattr(p, field), int), field


def test_params_from_dict_treats_zero_max_peaks_as_all():
    assert pd_mod.params_from_dict({'max_peaks': 0}).max_peaks is None
    assert pd_mod.params_from_dict({'max_peaks': 3.0}).max_peaks == 3


def test_params_from_dict_ignores_unknown_and_none_values():
    p = pd_mod.params_from_dict({'nonsense': 42, 'baseline': None, 'height': 12.5})
    assert p.height == 12.5
    assert p.baseline == Params().baseline
    assert not hasattr(p, 'nonsense')


def test_params_from_dict_keeps_window_bounds_as_floats():
    p = pd_mod.params_from_dict({'xmin': -1, 'xmax': 1})
    assert (p.xmin, p.xmax) == (-1.0, 1.0)
    assert isinstance(p.xmin, float)


# ---------------------------------------------------------------------------
# Thermal grouping (k_B * T)
# ---------------------------------------------------------------------------

def test_thermal_broadening_matches_the_textbook_value():
    # The by-hand sheet is labelled "T = 94 K, kbT = 8 meV".
    assert pd_mod.thermal_broadening(94.0) == pytest.approx(8.1e-3, rel=1e-3)
    assert pd_mod.thermal_broadening(94.0, "meV") == pytest.approx(8.1, rel=1e-3)
    assert pd_mod.thermal_broadening(300.0, "meV") == pytest.approx(25.85, rel=1e-3)


def test_thermal_broadening_disabled_at_or_below_zero():
    assert pd_mod.thermal_broadening(0) == 0.0
    assert pd_mod.thermal_broadening(None) == 0.0


def test_thermal_broadening_rejects_unknown_unit():
    with pytest.raises(ValueError, match="x_energy_unit must be one of"):
        pd_mod.thermal_broadening(94.0, "wavenumber")


def test_params_exposes_bin_width():
    assert Params().bin_width == 0.0
    assert Params(temperature_k=94.0).bin_width == pytest.approx(8.1e-3, rel=1e-3)


def test_params_validate_rejects_bad_temperature_settings():
    with pytest.raises(ValueError, match="temperature_k cannot be negative"):
        Params(temperature_k=-5).validate()
    with pytest.raises(ValueError, match="x_energy_unit must be one of"):
        Params(x_energy_unit="nm").validate()


def test_energy_bins_are_anchored_on_zero():
    """Two sweeps with different ranges must share a bin grid to be comparable."""
    wide, _ = pd_mod.energy_bins(np.linspace(-0.6, 0.6, 10), 0.008)
    narrow, _ = pd_mod.energy_bins(np.linspace(-0.3, 0.3, 10), 0.008)
    shared = set(np.round(wide, 12)) & set(np.round(narrow, 12))
    assert len(shared) == len(narrow)
    assert 0.0 in np.round(wide, 12)


def test_energy_bins_cover_the_data():
    x = np.linspace(-0.6, 0.6, 512)
    edges, centers = pd_mod.energy_bins(x, 0.0081)
    assert edges[0] <= x.min() and edges[-1] >= x.max()
    assert len(centers) == len(edges) - 1
    np.testing.assert_allclose(np.diff(centers), 0.0081)


def test_energy_bins_rejects_nonpositive_width():
    with pytest.raises(ValueError, match="bin width must be positive"):
        pd_mod.energy_bins(np.linspace(0, 1, 10), 0.0)


def test_assign_bins_places_values_and_clamps_the_edges():
    edges = np.array([0.0, 1.0, 2.0, 3.0])
    np.testing.assert_array_equal(pd_mod.assign_bins([0.5, 1.5, 2.5], edges), [0, 1, 2])
    # On an edge, the upper bin; outside, clamped rather than dropped.
    np.testing.assert_array_equal(pd_mod.assign_bins([1.0, -9.0, 99.0], edges), [1, 0, 2])
    assert pd_mod.assign_bins([], edges).size == 0


def test_group_peaks_by_bin_keeps_the_most_prominent():
    edges = np.array([0.0, 1.0, 2.0])
    peaks = [
        Peak(index=0, x=0.1, y=1.0, y_corrected=1.0, prominence=0.5),
        Peak(index=1, x=0.9, y=9.0, y_corrected=9.0, prominence=5.0),   # same bin, taller
        Peak(index=2, x=1.5, y=2.0, y_corrected=2.0, prominence=1.0),
    ]
    grouped = pd_mod.group_peaks_by_bin(peaks, edges)
    assert [(b, pk.x, n) for b, pk, n in grouped] == [(0, 0.9, 2), (1, 1.5, 1)]


def test_group_peaks_by_bin_of_nothing():
    assert pd_mod.group_peaks_by_bin([], np.array([0.0, 1.0])) == []


def test_occupancy_matrix_blanks_are_nan_by_default():
    matrix = pd_mod.occupancy_matrix(4, [[0, 2], [], [3]])
    assert matrix.shape == (4, 3)
    assert matrix.dtype == np.float32
    assert set(np.unique(matrix[np.isfinite(matrix)])) == {1}
    assert np.isnan(matrix[1, 0]) and np.isnan(matrix[:, 1]).all()
    np.testing.assert_array_equal(np.flatnonzero(matrix[:, 0] == 1), [0, 2])


def test_occupancy_matrix_blank_is_configurable():
    matrix = pd_mod.occupancy_matrix(3, [[1]], blank=0.0)
    np.testing.assert_array_equal(matrix[:, 0], [0.0, 1.0, 0.0])


def test_binned_peak_matrix_collapses_peaks_sharing_a_bin():
    x = np.linspace(-0.05, 0.05, 800)
    # Two peaks 4 meV apart, both inside one 8 meV bin.
    y = 1e-10 + _gaussians(x, (0.001, 0.005), amplitude=2e-8, width=0.0004)
    results = analyze_many(x, y, Params(height=1.0))
    assert len(results[0].peaks) == 2

    edges, centers = pd_mod.energy_bins(x, pd_mod.thermal_broadening(94.0))
    matrix = pd_mod.binned_peak_matrix(results, edges)
    assert matrix.shape == (len(centers), 1)
    assert np.nansum(matrix) == 1


def test_binning_alone_cannot_merge_across_a_bin_edge():
    """Why the tool also sets min_distance: two peaks closer than kBT still
    land in different bins when they straddle an edge."""
    x = np.linspace(-0.05, 0.05, 800)
    y = 1e-10 + _gaussians(x, (-0.0015, 0.0015), amplitude=2e-8, width=0.0004)
    width = pd_mod.thermal_broadening(94.0)

    straddling = analyze_many(x, y, Params(height=1.0))
    edges, _ = pd_mod.energy_bins(x, width)
    assert np.nansum(pd_mod.binned_peak_matrix(straddling, edges)) == 2

    # With k_B*T as the minimum separation as well, they become one feature.
    merged = analyze_many(x, y, Params(height=1.0, min_distance=width))
    assert np.nansum(pd_mod.binned_peak_matrix(merged, edges)) == 1


def test_binned_peak_matrix_keeps_resolvable_peaks_apart():
    x = np.linspace(-0.3, 0.3, 2048)
    y = 1e-10 + _gaussians(x, (-0.1, 0.1), amplitude=2e-8, width=0.001)
    results = analyze_many(x, y, Params(height=1.0))

    edges, _ = pd_mod.energy_bins(x, pd_mod.thermal_broadening(94.0))
    assert np.nansum(pd_mod.binned_peak_matrix(results, edges)) == 2


# ---------------------------------------------------------------------------
# Polynomial bases
# ---------------------------------------------------------------------------

def _sts_background(x):
    return 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)


@pytest.mark.parametrize("basis", pd_mod.POLYNOMIAL_BASES)
def test_every_basis_fits_the_same_curve(basis):
    """The bases span the same space -- only the coefficients differ."""
    x = np.linspace(-0.6, 0.6, 512)
    t = pd_mod.normalized_axis(x)
    y = _sts_background(x)

    fitted = pd_mod.eval_polynomial(pd_mod.fit_polynomial(t, y, 4, basis), t, basis)
    reference = pd_mod.eval_polynomial(pd_mod.fit_polynomial(t, y, 4, "power"), t, "power")
    np.testing.assert_allclose(fitted, reference, rtol=1e-6, atol=1e-12)


def test_legendre_coefficients_are_decorrelated():
    """The reason to offer an orthogonal basis at all.

    With an orthogonal design matrix the fitted coefficients are uncorrelated
    under noise, so each one carries independent information -- which is what
    makes them usable as PCA / classification features. Monomial coefficients
    trade off against each other instead.
    """
    rng = np.random.default_rng(0)
    x = np.linspace(-0.6, 0.6, 512)
    t = pd_mod.normalized_axis(x)
    truth = _sts_background(x)
    degree = 4

    def mean_abs_offdiag(basis):
        coeffs = np.array([
            pd_mod.fit_polynomial(t, truth + rng.normal(0, 2e-9, x.size), degree, basis)
            for _ in range(400)
        ])
        corr = np.corrcoef(coeffs.T)
        return np.abs(corr[~np.eye(degree + 1, dtype=bool)]).mean()

    power = mean_abs_offdiag("power")
    legendre = mean_abs_offdiag("legendre")
    assert legendre < 0.15
    assert legendre < power / 3


def test_chebyshev_is_not_orthogonal_on_a_uniform_grid():
    """Documents a real trap: Chebyshev is orthogonal under the weight
    1/sqrt(1-t^2), so on uniformly sampled spectra it decorrelates far less
    well than Legendre. Prefer Legendre for STS sweeps."""
    rng = np.random.default_rng(1)
    x = np.linspace(-0.6, 0.6, 512)
    t = pd_mod.normalized_axis(x)
    truth = _sts_background(x)
    degree = 4

    def mean_abs_offdiag(basis):
        coeffs = np.array([
            pd_mod.fit_polynomial(t, truth + rng.normal(0, 2e-9, x.size), degree, basis)
            for _ in range(300)
        ])
        corr = np.corrcoef(coeffs.T)
        return np.abs(corr[~np.eye(degree + 1, dtype=bool)]).mean()

    assert mean_abs_offdiag("legendre") < mean_abs_offdiag("chebyshev")


def test_orthogonal_bases_are_better_conditioned():
    t = np.linspace(-1.0, 1.0, 512)
    monomial = np.linalg.cond(np.vander(t, 9))
    legendre = np.linalg.cond(np.polynomial.legendre.legvander(t, 8))
    assert legendre < monomial / 20


def test_normalized_axis_maps_onto_the_unit_interval():
    x = np.linspace(-0.6, 0.6, 100)
    t = pd_mod.normalized_axis(x)
    assert t.min() == pytest.approx(-1.0)
    assert t.max() == pytest.approx(1.0)
    # A constant axis must not divide by zero.
    assert np.all(np.isfinite(pd_mod.normalized_axis(np.full(10, 3.0))))


def test_coefficient_names_say_which_basis():
    assert pd_mod.coefficient_names(2, "power") == ["c0", "c1", "c2"]
    assert pd_mod.coefficient_names(2, "legendre") == ["P0", "P1", "P2"]
    assert pd_mod.coefficient_names(2, "chebyshev") == ["T0", "T1", "T2"]


def test_coefficients_are_ascending_order_in_every_basis():
    t = np.linspace(-1.0, 1.0, 200)
    # A pure constant: only the zeroth term is non-zero, whichever basis.
    for basis in pd_mod.POLYNOMIAL_BASES:
        coeffs = pd_mod.fit_polynomial(t, np.full_like(t, 5.0), 3, basis)
        assert coeffs[0] == pytest.approx(5.0)
        np.testing.assert_allclose(coeffs[1:], 0.0, atol=1e-9)


@pytest.mark.parametrize("basis", pd_mod.POLYNOMIAL_BASES)
def test_baseline_estimation_accepts_every_basis(basis):
    x, y = _sts_curve()
    baseline = estimate_baseline(x, y, "poly-iter", degree=5, basis=basis)
    assert baseline.shape == y.shape
    assert np.all(np.isfinite(baseline))


def test_basis_does_not_change_which_peaks_are_found():
    """The background is the same curve, so detection must agree."""
    x, y = _sts_curve()
    found = {
        basis: _centers(find_peaks(x, y, Params(baseline="poly-iter", baseline_degree=5,
                                                baseline_basis=basis)))
        for basis in pd_mod.POLYNOMIAL_BASES
    }
    assert found["legendre"] == found["power"]
    assert found["chebyshev"] == found["power"]


def test_fit_polynomial_rejects_an_unknown_basis():
    t = np.linspace(-1, 1, 50)
    with pytest.raises(ValueError, match="basis must be one of"):
        pd_mod.fit_polynomial(t, t, 2, "bernstein")
    with pytest.raises(ValueError, match="basis must be one of"):
        pd_mod.eval_polynomial(np.zeros(3), t, "bernstein")


def test_params_validate_rejects_an_unknown_basis():
    with pytest.raises(ValueError, match="baseline_basis must be one of"):
        Params(baseline_basis="bernstein").validate()
