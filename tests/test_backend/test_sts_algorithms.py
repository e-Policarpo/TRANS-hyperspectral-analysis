"""
Tests for STS Analysis Algorithms (sts_algorithms.py)
Covers: detect_saturation, detect_noise, detect_linear_artifact,
        detect_periodic_noise, correct_periodic_noise,
        numerical_derivative, normalize_ldos, detect_bandgap,
        classify_doping, validate_ldos
"""

import pytest
import numpy as np
from src.backend.sts_algorithms import (
    detect_saturation,
    detect_noise,
    detect_linear_artifact,
    detect_partial_noise,
    detect_periodic_noise,
    correct_periodic_noise,
    numerical_derivative,
    normalize_ldos,
    detect_bandgap,
    classify_doping,
    validate_ldos,
)


# =============================================================================
# detect_saturation
# =============================================================================

class TestDetectSaturation:
    """Tests for saturation detection."""

    def test_normal_spectrum_low_score(self):
        """Uniform ramp should have low saturation score (few points at extremes)."""
        # A linear ramp distributes points uniformly — ~3% at each extreme
        # With threshold 0.30/0.30, a ramp with 6% near extremes scores 0.
        spectrum = np.linspace(-5, 5, 200)
        score = detect_saturation(spectrum)
        assert score < 0.1

    def test_heavily_clipped_spectrum(self):
        """Clipped spectrum should score high."""
        spectrum = np.linspace(-1, 1, 200)
        # Clip to ±0.5 — many points at extremes
        spectrum = np.clip(spectrum, -0.5, 0.5)
        score = detect_saturation(spectrum)
        assert score > 0.5

    def test_all_same_value(self):
        """Flat (zero range) spectrum returns 1.0 (saturated or dead)."""
        spectrum = np.ones(100)
        score = detect_saturation(spectrum)
        assert score == 1.0

    def test_too_few_points(self):
        """Less than 3 clean points returns 0."""
        spectrum = np.array([1.0, 2.0])
        assert detect_saturation(spectrum) == 0.0

    def test_with_nans(self):
        """NaN values are ignored."""
        spectrum = np.linspace(-1, 1, 100)
        spectrum[::2] = np.nan  # Half NaN
        score = detect_saturation(spectrum)
        assert 0.0 <= score <= 1.0

    def test_all_nan(self):
        """All-NaN returns 0 (< 3 clean points)."""
        spectrum = np.full(50, np.nan)
        assert detect_saturation(spectrum) == 0.0

    def test_score_range(self):
        """Score should always be in [0, 1]."""
        for _ in range(20):
            spectrum = np.random.randn(100)
            score = detect_saturation(spectrum)
            assert 0.0 <= score <= 1.0

    def test_threshold_parameter(self):
        """Custom threshold changes the margin for saturation zone."""
        x = np.linspace(0, 1, 200)
        # With default threshold=0.95, margin = 0.025 * range
        score_default = detect_saturation(x, threshold=0.95)
        # With threshold=0.5, margin = 0.25 * range — more points at extremes
        score_wide = detect_saturation(x, threshold=0.5)
        assert score_wide >= score_default


# =============================================================================
# detect_noise
# =============================================================================

class TestDetectNoise:
    """Tests for noise detection."""

    def test_clean_signal_low_score(self):
        """Smooth signal should have low noise score."""
        x = np.linspace(0, 2 * np.pi, 200)
        spectrum = np.sin(x)
        score = detect_noise(spectrum)
        assert score < 0.3

    def test_pure_noise_high_score(self):
        """Random noise should have high noise score."""
        np.random.seed(42)
        spectrum = np.random.randn(200) * 0.1
        # The range is small relative to 2nd derivative std
        score = detect_noise(spectrum)
        assert score > 0.3

    def test_flat_signal_is_noise(self):
        """Flat signal (zero range) returns 1.0."""
        spectrum = np.ones(100) * 5.0
        score = detect_noise(spectrum)
        assert score == 1.0

    def test_too_few_points(self):
        """Less than 5 clean points returns 0."""
        spectrum = np.array([1.0, 2.0, 3.0, 4.0])
        assert detect_noise(spectrum) == 0.0

    def test_with_nans(self):
        """NaN values are stripped before analysis."""
        x = np.linspace(0, 2 * np.pi, 200)
        spectrum = np.sin(x)
        spectrum[::3] = np.nan
        score = detect_noise(spectrum)
        assert 0.0 <= score <= 1.0

    def test_score_range(self):
        """Score should always be in [0, 1]."""
        np.random.seed(123)
        for _ in range(20):
            spectrum = np.random.randn(100)
            score = detect_noise(spectrum)
            assert 0.0 <= score <= 1.0


# =============================================================================
# detect_linear_artifact
# =============================================================================

class TestDetectLinearArtifact:
    """Tests for linear artifact detection."""

    def test_perfectly_linear_high_score(self):
        """A perfectly linear spectrum should score high."""
        x = np.linspace(-2, 2, 100)
        spectrum = 3.0 * x + 1.0
        score = detect_linear_artifact(x, spectrum)
        assert score > 0.9

    def test_nonlinear_spectrum_low_score(self):
        """A typical nonlinear spectrum should score low."""
        x = np.linspace(-2, 2, 100)
        spectrum = np.sin(x) + 0.5 * np.cos(3 * x)
        score = detect_linear_artifact(x, spectrum)
        assert score < 0.1

    def test_constant_spectrum(self):
        """Constant (zero variation) returns 1.0 (trivially linear)."""
        x = np.linspace(-1, 1, 100)
        spectrum = np.ones(100) * 7.0
        score = detect_linear_artifact(x, spectrum)
        assert score == 1.0

    def test_too_few_points(self):
        """Less than 3 clean points returns 0."""
        x = np.array([1.0, 2.0])
        spectrum = np.array([3.0, 4.0])
        assert detect_linear_artifact(x, spectrum) == 0.0

    def test_with_nans(self):
        """NaN pairs are removed before fitting."""
        x = np.linspace(-2, 2, 100)
        spectrum = 2.0 * x + 1.0
        spectrum[10] = np.nan
        spectrum[50] = np.nan
        score = detect_linear_artifact(x, spectrum)
        assert score > 0.9

    def test_r2_threshold_parameter(self):
        """Custom R2 threshold changes sensitivity."""
        x = np.linspace(-2, 2, 100)
        # Slightly noisy linear signal
        np.random.seed(42)
        spectrum = 2.0 * x + 1.0 + np.random.normal(0, 0.1, 100)
        score_strict = detect_linear_artifact(x, spectrum, r2_threshold=0.999)
        score_loose = detect_linear_artifact(x, spectrum, r2_threshold=0.8)
        assert score_loose >= score_strict

    def test_score_range(self):
        """Score should always be in [0, 1]."""
        np.random.seed(0)
        for _ in range(20):
            x = np.linspace(-2, 2, 100)
            spectrum = np.random.randn(100)
            score = detect_linear_artifact(x, spectrum)
            assert 0.0 <= score <= 1.0


# =============================================================================
# detect_periodic_noise
# =============================================================================

class TestDetectPeriodicNoise:
    """Tests for periodic noise detection via FFT."""

    def test_clean_signal_low_score(self):
        """Smooth signal without periodic artifacts should score low."""
        x = np.linspace(0, 1, 256)
        spectrum = np.sin(2 * np.pi * x)  # Simple fundamental
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        assert score < 0.5

    def test_strong_periodic_artifact(self):
        """Signal with broadband noise + sharp periodic spike should be detected."""
        np.random.seed(42)
        n = 1024
        x = np.linspace(0, 1, n)
        # Broadband noise floor (so MAD > 0 in FFT residuals)
        base = np.random.randn(n) * 0.5
        # Strong narrow-band periodic artifact
        artifact = 5.0 * np.sin(2 * np.pi * 120 * x)
        spectrum = base + artifact
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        # The sharp peak at f=120 should stand out above the noise floor
        assert score > 0.0
        assert np.any(peak_mask)

    def test_returns_correct_shapes(self):
        """FFT outputs have expected shapes."""
        n = 100
        spectrum = np.random.randn(n)
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        expected_len = n // 2 + 1
        assert len(fft_mag) == expected_len
        assert len(bg) == expected_len
        assert len(peak_mask) == expected_len
        assert peak_mask.dtype == bool

    def test_too_few_points(self):
        """Less than 8 points returns zeros."""
        spectrum = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        assert score == 0.0
        assert len(fft_mag) == 1
        assert len(peak_mask) == 1

    def test_with_nans(self):
        """NaN values are stripped before FFT."""
        spectrum = np.random.randn(100)
        spectrum[::5] = np.nan
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        assert 0.0 <= score <= 1.0
        # Length based on clean points
        n_clean = np.sum(~np.isnan(spectrum))
        assert len(fft_mag) == n_clean // 2 + 1

    def test_all_nan(self):
        """All-NaN returns minimal output."""
        spectrum = np.full(50, np.nan)
        score, fft_mag, bg, peak_mask = detect_periodic_noise(spectrum)
        assert score == 0.0

    def test_score_range(self):
        """Score should always be in [0, 1]."""
        np.random.seed(7)
        for _ in range(20):
            spectrum = np.random.randn(128)
            score, _, _, _ = detect_periodic_noise(spectrum)
            assert 0.0 <= score <= 1.0


# =============================================================================
# detect_partial_noise
# =============================================================================

class TestDetectPartialNoise:
    """Tests for partial noise detection."""

    def test_clean_signal_low_score(self):
        """Smooth sine wave should have low partial noise score."""
        x = np.linspace(0, 2 * np.pi, 200)
        spectrum = np.sin(x) * 5.0
        score = detect_partial_noise(x, spectrum)
        assert score < 0.3

    def test_pure_noise_high_score(self):
        """Random noise should have high partial noise score."""
        np.random.seed(42)
        x = np.linspace(-2, 2, 200)
        spectrum = np.random.randn(200) * 0.1
        score = detect_partial_noise(x, spectrum)
        assert score > 0.5

    def test_partial_noise_detected(self):
        """Signal near center + noise at edges should give elevated score."""
        np.random.seed(42)
        x = np.linspace(-2, 2, 200)
        spectrum = np.zeros(200)
        # Good signal in center (indices 60-140)
        spectrum[60:140] = np.sin(np.linspace(0, 2 * np.pi, 80)) * 5.0
        # Noise at edges
        spectrum[:60] = np.random.randn(60) * 0.1
        spectrum[140:] = np.random.randn(60) * 0.1
        score = detect_partial_noise(x, spectrum)
        assert score >= 0.3

    def test_too_few_points(self):
        """Less than 20 points returns 0.0."""
        x = np.linspace(-1, 1, 15)
        spectrum = np.random.randn(15)
        score = detect_partial_noise(x, spectrum)
        assert score == 0.0

    def test_with_nans(self):
        """NaN values are stripped before analysis."""
        x = np.linspace(0, 2 * np.pi, 200)
        spectrum = np.sin(x) * 5.0
        spectrum[::5] = np.nan
        score = detect_partial_noise(x, spectrum)
        assert 0.0 <= score <= 1.0

    def test_score_range(self):
        """Score should always be in [0, 1]."""
        np.random.seed(123)
        for _ in range(20):
            x = np.linspace(-2, 2, 100)
            spectrum = np.random.randn(100)
            score = detect_partial_noise(x, spectrum)
            assert 0.0 <= score <= 1.0


# =============================================================================
# correct_periodic_noise
# =============================================================================

class TestCorrectPeriodicNoise:
    """Tests for periodic noise correction."""

    def test_no_peaks_no_change(self):
        """With no peaks masked, spectrum should be unchanged."""
        spectrum = np.sin(np.linspace(0, 2 * np.pi, 100))
        peak_mask = np.zeros(len(spectrum) // 2 + 1, dtype=bool)
        corrected = correct_periodic_noise(spectrum, peak_mask)
        np.testing.assert_allclose(corrected, spectrum, atol=1e-10)

    def test_output_same_length(self):
        """Corrected spectrum has same length as input."""
        n = 128
        spectrum = np.random.randn(n)
        # Create a peak mask with some peaks flagged
        peak_mask = np.zeros(n // 2 + 1, dtype=bool)
        peak_mask[20:23] = True
        corrected = correct_periodic_noise(spectrum, peak_mask)
        assert len(corrected) == n

    def test_reduces_periodic_component(self):
        """Correction should reduce the power of the periodic artifact."""
        n = 256
        x = np.linspace(0, 1, n)
        base = np.sin(2 * np.pi * 3 * x)
        artifact = 0.5 * np.sin(2 * np.pi * 50 * x)
        spectrum = base + artifact

        # Detect the periodic noise first
        _, _, _, peak_mask = detect_periodic_noise(spectrum, peak_threshold=2.0)

        if np.any(peak_mask):
            corrected = correct_periodic_noise(spectrum, peak_mask)
            # FFT of corrected should have less power at artifact frequency
            orig_fft = np.abs(np.fft.rfft(spectrum))
            corr_fft = np.abs(np.fft.rfft(corrected))
            # Total high-freq power should be reduced
            assert np.sum(corr_fft[40:60]) <= np.sum(orig_fft[40:60])

    def test_dc_preserved(self):
        """DC component (bin 0) should not be modified."""
        n = 64
        spectrum = np.random.randn(n) + 10.0  # Large DC offset
        peak_mask = np.zeros(n // 2 + 1, dtype=bool)
        peak_mask[5:10] = True
        corrected = correct_periodic_noise(spectrum, peak_mask)
        # DC component preserved
        orig_dc = np.fft.rfft(spectrum)[0]
        corr_dc = np.fft.rfft(corrected)[0]
        np.testing.assert_allclose(np.abs(corr_dc), np.abs(orig_dc), rtol=1e-5)


# =============================================================================
# numerical_derivative
# =============================================================================

class TestNumericalDerivative:
    """Tests for numerical derivative calculation."""

    def test_linear_function(self):
        """Derivative of f(x)=2x+1 should be ~2 everywhere."""
        x = np.linspace(0, 10, 100)
        y = 2.0 * x + 1.0
        x_mid, dy = numerical_derivative(x, y)
        assert len(x_mid) == len(x) - 1
        np.testing.assert_allclose(dy, 2.0, atol=1e-10)

    def test_quadratic_function(self):
        """Derivative of f(x)=x^2 should be ~2x at midpoints."""
        x = np.linspace(-5, 5, 1000)
        y = x ** 2
        x_mid, dy = numerical_derivative(x, y)
        expected = 2.0 * x_mid
        np.testing.assert_allclose(dy, expected, atol=0.02)

    def test_output_lengths(self):
        """Output arrays have length N-1."""
        x = np.linspace(0, 1, 50)
        y = np.sin(x)
        x_mid, dy = numerical_derivative(x, y)
        assert len(x_mid) == 49
        assert len(dy) == 49

    def test_zero_dx_handled(self):
        """Division by near-zero dx does not produce inf."""
        x = np.array([0.0, 0.0, 1.0])  # dx[0] = 0
        y = np.array([1.0, 2.0, 3.0])
        x_mid, dy = numerical_derivative(x, y)
        assert np.all(np.isfinite(dy))


# =============================================================================
# normalize_ldos
# =============================================================================

class TestNormalizeLdos:
    """Tests for LDOS normalization."""

    def test_positive_data(self):
        """Max of positive part should be 1 after normalization."""
        x = np.linspace(-2, 2, 100)
        y = np.abs(x) + 0.5
        x_out, y_norm = normalize_ldos(x, y)
        # After centering at V=0 and scaling
        assert np.max(y_norm) == pytest.approx(1.0, abs=1e-10)

    def test_x_unchanged(self):
        """x values should be returned unchanged."""
        x = np.linspace(-3, 3, 50)
        y = np.sin(x)
        x_out, _ = normalize_ldos(x, y)
        np.testing.assert_array_equal(x_out, x)

    def test_all_zero(self):
        """All-zero input should return all zeros."""
        x = np.linspace(-1, 1, 50)
        y = np.zeros(50)
        _, y_norm = normalize_ldos(x, y)
        np.testing.assert_array_equal(y_norm, np.zeros(50))


# =============================================================================
# detect_bandgap
# =============================================================================

class TestDetectBandgap:
    """Tests for bandgap detection."""

    def test_clear_gap(self):
        """Clear gap around zero should be detected."""
        dx = np.linspace(-2, 2, 500)
        # LDOS with clear gap: zero near V=0, rises away from zero
        dy = np.where(np.abs(dx) < 0.5, 0.0, np.abs(dx))
        dy = dy / np.max(dy)  # Normalize
        gap, typ, xmin, xmax = detect_bandgap(dx, dy, delta=0.1)
        # Gap should be ~1.0 (from -0.5 to +0.5)
        assert gap == pytest.approx(1.0, abs=0.1)
        # Center should be near zero
        assert abs(typ) < 0.1

    def test_n_type_doping(self):
        """Gap shifted to negative voltage = N-type."""
        dx = np.linspace(-2, 2, 500)
        # Gap centered at -0.3
        dy = np.where((dx > -0.8) & (dx < 0.2), 0.0, np.abs(dx))
        dy = dy / np.max(dy)
        _, typ, _, _ = detect_bandgap(dx, dy, delta=0.1)
        assert typ < 0  # Negative = N-type

    def test_p_type_doping(self):
        """Gap shifted to positive voltage = P-type."""
        dx = np.linspace(-2, 2, 500)
        # Gap centered at +0.3
        dy = np.where((dx > -0.2) & (dx < 0.8), 0.0, np.abs(dx))
        dy = dy / np.max(dy)
        _, typ, _, _ = detect_bandgap(dx, dy, delta=0.1)
        assert typ > 0  # Positive = P-type


# =============================================================================
# classify_doping
# =============================================================================

class TestClassifyDoping:
    """Tests for doping classification."""

    def test_n_type(self):
        assert classify_doping(-0.1, 0.01) == 'N'

    def test_p_type(self):
        assert classify_doping(0.1, 0.01) == 'P'

    def test_neutral(self):
        assert classify_doping(0.005, 0.01) == 'Neutral'

    def test_neutral_negative_within_resolution(self):
        assert classify_doping(-0.005, 0.01) == 'Neutral'

    def test_edge_at_negative_resolution(self):
        """Exactly at -resolution is Neutral (not < -resolution)."""
        assert classify_doping(-0.01, 0.01) == 'Neutral'

    def test_edge_at_positive_resolution(self):
        """Exactly at +resolution is Neutral (not > +resolution)."""
        assert classify_doping(0.01, 0.01) == 'Neutral'


# =============================================================================
# validate_ldos
# =============================================================================

class TestValidateLdos:
    """Tests for LDOS validation."""

    def test_valid_curve(self):
        """Normal curve should pass validation."""
        x = np.linspace(-2, 2, 100)
        y = np.sin(x)
        is_valid, reason = validate_ldos(x, y)
        assert is_valid is True
        assert reason == ""

    def test_all_nan(self):
        """All-NaN should fail."""
        x = np.linspace(-2, 2, 100)
        y = np.full(100, np.nan)
        is_valid, reason = validate_ldos(x, y)
        assert is_valid is False
        assert "NaN" in reason

    def test_too_few_points(self):
        """Less than 5 valid points should fail."""
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([0.5, 1.0, 0.5])
        is_valid, reason = validate_ldos(x, y)
        assert is_valid is False
        assert "few" in reason.lower()

    def test_flat_spectrum(self):
        """Flat (zero variation) should fail."""
        x = np.linspace(-2, 2, 100)
        y = np.ones(100) * 5.0
        is_valid, reason = validate_ldos(x, y)
        assert is_valid is False
        assert "flat" in reason.lower()

    def test_with_some_nans(self):
        """Curve with some NaN but enough valid points should pass."""
        x = np.linspace(-2, 2, 100)
        y = np.sin(x)
        y[::10] = np.nan  # 10 NaN out of 100
        is_valid, reason = validate_ldos(x, y)
        assert is_valid is True
