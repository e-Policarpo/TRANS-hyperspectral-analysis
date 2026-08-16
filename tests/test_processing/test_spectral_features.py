"""
Tests for src.processing.spectral_features.

The fixtures build dI/dV curves with known physics -- a chosen gap width,
doping shift, band-edge steepness and number of confined states -- so each
feature can be checked against the value that was planted.

Two regressions worth naming, both found while building this and both of the
kind that would quietly poison a whole feature table rather than fail loudly:

* a bright confined state *inside* the gap stopped the gap detector at the
  state, reporting a gapless spectrum on exactly the samples this analysis
  exists for;
* the metallicity fit was allowed to run on barely more points than its
  degree, returning coefficients ~1e5 too large that would have dominated
  any PCA built on the table.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pytest

from src.processing import spectral_features as sf
from src.processing.peak_detection import Params
from src.processing.spectral_features import (
    FeatureConfig,
    confinement_features,
    doping_features,
    feature_columns,
    feature_table,
    gap_features,
    metallicity_features,
    normalize_spectrum,
    spectrum_features,
    suppress_narrow_peaks,
)


def make_sts(gap_half=0.15, centre=0.0, floor=0.02, n_states=0, amplitude=1.0,
             edge_width=0.08, n=512, seed=0):
    """A dI/dV curve with known gap, doping, steepness and state count.

    The gap floor sits at ``floor`` times the band-edge value, which is the
    realistic regime -- a floor four decades down makes a percentage
    threshold meaningless.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(-0.6, 0.6, n)
    outside = np.clip(np.abs(x - centre) - gap_half, 0.0, None)
    y = amplitude * 3e-7 * (floor + (1 - floor) * np.tanh(outside / edge_width) ** 2)
    for k in range(n_states):
        c = centre - gap_half + (k + 1) * (2 * gap_half) / (n_states + 1)
        y = y + amplitude * 2.5e-8 * np.exp(-0.5 * ((x - c) / 0.006) ** 2)
    return x, y + rng.normal(0, amplitude * 8e-11, x.size)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["max", "band-edge", "area"])
def test_normalization_removes_the_tip_height_scale(method):
    """Without this, PC1 is 'how close was the tip'."""
    x, y = make_sts()
    np.testing.assert_allclose(normalize_spectrum(x, y, method),
                               normalize_spectrum(x, 25.0 * y, method), rtol=1e-9)


def test_normalization_preserves_shape():
    x, y = make_sts()
    normalized = normalize_spectrum(x, y, "max")
    ratio = normalized / y
    np.testing.assert_allclose(ratio, ratio[0], rtol=1e-9)


def test_normalize_none_is_identity():
    x, y = make_sts()
    np.testing.assert_array_equal(normalize_spectrum(x, y, "none"), y)


def test_normalization_survives_degenerate_input():
    x = np.linspace(-1, 1, 50)
    np.testing.assert_array_equal(normalize_spectrum(x, np.zeros(50), "max"), np.zeros(50))
    allnan = np.full(50, np.nan)
    assert np.isnan(normalize_spectrum(x, allnan, "max")).all()


def test_normalize_rejects_unknown_method():
    x, y = make_sts()
    with pytest.raises(ValueError, match="normalize must be one of"):
        normalize_spectrum(x, y, "quantile")


# ---------------------------------------------------------------------------
# Gap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("half,expected", [(0.08, 0.16), (0.15, 0.30), (0.25, 0.50)])
def test_gap_width_tracks_the_planted_gap(half, expected):
    x, y = make_sts(gap_half=half)
    gap = gap_features(x, normalize_spectrum(x, y, "max"))
    # A 5%-of-max threshold on a smooth onset reads slightly wide.
    assert gap["gap_width"] == pytest.approx(expected, abs=0.05)


def test_gap_is_not_destroyed_by_in_gap_states():
    """Regression: the detector used to stop at the first confined state and
    report a gapless spectrum."""
    x, empty = make_sts(gap_half=0.15, n_states=0)
    _, occupied = make_sts(gap_half=0.15, n_states=3)

    reference = gap_features(x, normalize_spectrum(x, empty, "max"))["gap_width"]
    with_states = gap_features(x, normalize_spectrum(x, occupied, "max"))["gap_width"]

    assert reference > 0.2
    assert with_states == pytest.approx(reference, abs=1e-9)


def test_suppress_narrow_peaks_keeps_broad_structure():
    x = np.linspace(-1, 1, 400)
    broad = np.tanh(np.abs(x) / 0.2) ** 2
    spike = 0.6 * np.exp(-0.5 * (x / 0.01) ** 2)

    opened = suppress_narrow_peaks(broad + spike, 15)
    assert opened.max() < (broad + spike).max()
    np.testing.assert_allclose(opened[:50], broad[:50], atol=0.02)


def test_suppress_narrow_peaks_is_a_noop_for_silly_widths():
    y = np.arange(10.0)
    np.testing.assert_array_equal(suppress_narrow_peaks(y, 1), y)
    np.testing.assert_array_equal(suppress_narrow_peaks(y, 999), y)


def test_gap_edges_are_kept_separately():
    x, y = make_sts(gap_half=0.15, centre=0.10)
    gap = gap_features(x, normalize_spectrum(x, y, "max"))
    assert gap["gap_left"] < gap["gap_right"]
    assert gap["gap_center"] == pytest.approx((gap["gap_left"] + gap["gap_right"]) / 2)


# ---------------------------------------------------------------------------
# Doping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shift", [-0.10, 0.0, 0.10])
def test_doping_offset_recovers_the_planted_shift(shift):
    x, y = make_sts(centre=shift)
    normalized = normalize_spectrum(x, y, "max")
    gap = gap_features(x, normalized)
    doping = doping_features(x, normalized, gap)
    assert doping["doping_offset"] == pytest.approx(shift, abs=0.02)


def test_doping_reports_two_independent_estimates():
    """argmin of a noisy near-zero signal wanders, so it is reported next to
    the stable midpoint rather than instead of it."""
    x, y = make_sts(centre=-0.08)
    normalized = normalize_spectrum(x, y, "max")
    doping = doping_features(x, normalized, gap_features(x, normalized))

    assert set(["doping_offset", "doping_argmin", "doping_disagreement"]) <= set(doping)
    assert doping["doping_disagreement"] == pytest.approx(
        abs(doping["doping_offset"] - doping["doping_argmin"]), abs=1e-12)


def test_doping_type_is_classified():
    x, y = make_sts(centre=-0.10)
    normalized = normalize_spectrum(x, y, "max")
    doping = doping_features(x, normalized, gap_features(x, normalized))
    assert isinstance(doping["doping_type"], str)


# ---------------------------------------------------------------------------
# Metallicity
# ---------------------------------------------------------------------------

def test_steeper_band_edges_give_a_larger_curvature_term():
    x, wide = make_sts(gap_half=0.25)
    _, narrow = make_sts(gap_half=0.08)

    def curvature(y):
        normalized = normalize_spectrum(x, y, "max")
        gap = gap_features(x, normalized)
        return metallicity_features(x, normalized, gap)["P2"]

    assert curvature(wide) > curvature(narrow)


def test_linear_term_flips_sign_with_doping():
    """Electron-hole asymmetry shows up in the first-order coefficient."""
    x, n_doped = make_sts(centre=-0.10)
    _, p_doped = make_sts(centre=+0.10)

    def linear(y):
        normalized = normalize_spectrum(x, y, "max")
        return metallicity_features(x, normalized, gap_features(x, normalized))["P1"]

    assert linear(n_doped) > 0 > linear(p_doped)


def test_metallicity_refuses_to_fit_too_few_points():
    """Regression: a degree-4 fit through 6 points returned coefficients
    ~1e5 too large, which would have dominated the PCA."""
    x, y = make_sts()
    normalized = normalize_spectrum(x, y, "max")
    # A gap covering nearly the whole sweep leaves almost nothing outside.
    starved = {"gap_left": -0.59, "gap_right": 0.59, "gap_center": 0.0,
               "gap_width": 1.18}
    features = metallicity_features(x, normalized, starved, degree=4)
    assert all(np.isnan(features[name]) for name in ("P0", "P1", "P2", "P3", "P4"))


def test_metallicity_scalars_are_bounded_and_meaningful():
    x, y = make_sts()
    normalized = normalize_spectrum(x, y, "max")
    features = metallicity_features(x, normalized, gap_features(x, normalized))

    assert -1.0 <= features["asymmetry"] <= 1.0
    # A gap means little weight inside relative to the band edges.
    assert 0.0 < features["in_gap_weight"] < 0.5
    assert np.isfinite(features["zero_bias_conductance"])


def test_coefficient_names_follow_the_basis():
    x, y = make_sts()
    normalized = normalize_spectrum(x, y, "max")
    gap = gap_features(x, normalized)
    assert "T2" in metallicity_features(x, normalized, gap, basis="chebyshev")
    assert "c2" in metallicity_features(x, normalized, gap, basis="power")


# ---------------------------------------------------------------------------
# Confined states
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("planted", [0, 1, 3, 5])
def test_state_count_matches_what_was_planted(planted):
    x, y = make_sts(n_states=planted)
    normalized = normalize_spectrum(x, y, "max")
    gap = gap_features(x, normalized)
    assert confinement_features(x, normalized, gap)["n_states"] == planted


def test_empty_gap_reports_no_states():
    """The gap interior is flat and noisy; a percentage threshold there finds
    a dozen phantom states, which is why the noise gate exists."""
    x, y = make_sts(n_states=0)
    normalized = normalize_spectrum(x, y, "max")
    features = confinement_features(x, normalized, gap_features(x, normalized))
    assert features["n_states"] == 0
    assert np.isnan(features["state_spacing_mean"])


def test_state_spacing_and_lowest_state_are_measured():
    x, y = make_sts(gap_half=0.15, n_states=3)
    normalized = normalize_spectrum(x, y, "max")
    features = confinement_features(x, normalized, gap_features(x, normalized))

    # Three evenly spaced states across a 0.30 V gap.
    assert features["state_spacing_mean"] == pytest.approx(0.30 / 4, abs=0.02)
    assert features["lowest_state"] > 0
    assert features["state_weight"] > 0


def test_no_gap_means_no_state_search():
    x, y = make_sts()
    blank = confinement_features(x, y, {"gap_left": np.nan, "gap_right": np.nan})
    assert blank["n_states"] == 0


# ---------------------------------------------------------------------------
# Whole-spectrum and table
# ---------------------------------------------------------------------------

def test_spectrum_features_are_scale_invariant():
    """The single most important property: two spectra of identical physics
    at different tip heights must land in the same place."""
    x, y = make_sts(n_states=3)
    close = spectrum_features(x, y)
    far = spectrum_features(x, 10.0 * y)

    for name in ("gap_width", "doping_offset", "n_states", "P1", "P2",
                 "asymmetry", "in_gap_weight"):
        assert close[name] == pytest.approx(far[name], rel=1e-6, abs=1e-9), name


def test_feature_table_has_one_row_per_spectrum():
    x, _ = make_sts()
    spectra = np.column_stack([make_sts(gap_half=h)[1] for h in (0.08, 0.15, 0.25)])
    rows = feature_table(x, spectra)

    assert len(rows) == 3
    assert [row["Spectrum_Index"] for row in rows] == [0.0, 1.0, 2.0]
    widths = [row["gap_width"] for row in rows]
    assert widths[0] < widths[1] < widths[2]


def test_feature_table_accepts_a_single_spectrum():
    x, y = make_sts()
    assert len(feature_table(x, y)) == 1


def test_every_declared_column_is_produced():
    x, y = make_sts(n_states=3)
    row = feature_table(x, y)[0]
    for name in feature_columns():
        assert name in row, name


def test_feature_table_reports_progress_and_honours_cancel():
    x, _ = make_sts()
    spectra = np.column_stack([make_sts()[1]] * 5)

    seen = []
    feature_table(x, spectra, on_progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 5) for i in range(1, 6)]

    calls = {"n": 0}

    def cancel_after_two():
        calls["n"] += 1
        return calls["n"] > 2

    assert len(feature_table(x, spectra, should_cancel=cancel_after_two)) == 2


def test_a_broken_spectrum_is_flagged_not_dropped():
    """A row that fails must be marked invalid so it can be excluded from PCA
    -- silently giving it a gap of zero would define a cluster."""
    x, y = make_sts()
    spectra = np.column_stack([y, np.full_like(y, np.nan), y])
    rows = feature_table(x, spectra)

    assert len(rows) == 3
    assert rows[1]["valid"] == 0.0
    assert rows[0]["valid"] == 1.0


def test_flat_spectrum_is_marked_invalid():
    x = np.linspace(-0.6, 0.6, 512)
    row = spectrum_features(x, np.zeros_like(x))
    assert row["valid"] == 0.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_default_config_uses_legendre():
    """The only basis that actually decorrelates on a uniform sweep."""
    assert FeatureConfig().poly_basis == "legendre"
    assert "P0" in feature_columns()


@pytest.mark.parametrize("kwargs, message", [
    ({"normalize": "quantile"}, "normalize must be one of"),
    ({"edge_fraction": 0.9}, "edge_fraction must lie"),
    ({"poly_degree": -1}, "poly_degree cannot be negative"),
    ({"poly_basis": "bernstein"}, "baseline_basis must be one of"),
])
def test_config_rejects_bad_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        FeatureConfig(**kwargs).validate()


def test_config_column_order_follows_degree_and_basis():
    columns = feature_columns(FeatureConfig(poly_degree=2, poly_basis="power"))
    assert "c2" in columns and "c3" not in columns
    assert columns[0] == "Spectrum_Index"


def test_custom_confinement_params_are_used():
    x, y = make_sts(n_states=5)
    lenient = FeatureConfig(state_noise_sigmas=4.0)
    strict = FeatureConfig(state_noise_sigmas=1e6)   # nothing can clear this
    assert spectrum_features(x, y, lenient)["n_states"] == 5
    assert spectrum_features(x, y, strict)["n_states"] == 0
