"""
The Dirac point group of Spectral Features (folded in from the old
Dirac Point Estimator tool).
"""

import numpy as np
import pytest

from src.processing.spectral_features import (DIRAC_COLUMNS, FeatureConfig,
                                              dirac_features, dirac_windows,
                                              feature_columns, spectrum_features)


def v_shape(x, x0=0.1, sl=-2.0, sr=3.0, y0=0.05):
    """Two straight branches meeting at (x0, y0): the textbook Dirac cone."""
    return np.where(x < x0, y0 + sl * (x - x0), y0 + sr * (x - x0))


@pytest.fixture
def x():
    return np.linspace(-1.0, 1.0, 401)


class TestWindows:
    def test_manual_windows_are_returned_as_given(self, x):
        cfg = FeatureConfig(dirac_mode="manual", dirac_left_min=-0.9, dirac_left_max=-0.2,
                            dirac_right_min=0.3, dirac_right_max=0.9)
        assert dirac_windows(x, {}, cfg) == ((-0.9, -0.2), (0.3, 0.9))

    def test_off_gives_none(self, x):
        assert dirac_windows(x, {"gap_left": -0.1, "gap_right": 0.1},
                             FeatureConfig(dirac_mode="off")) is None

    def test_auto_runs_from_the_sweep_ends_to_the_gap_edges(self, x):
        cfg = FeatureConfig(dirac_mode="auto", dirac_edge_trim=0.1)
        (l0, l1), (r0, r1) = dirac_windows(x, {"gap_left": -0.2, "gap_right": 0.3}, cfg)
        assert l1 == -0.2 and r0 == 0.3
        # 10% of each outer span trimmed
        assert l0 == pytest.approx(-1.0 + 0.8 * 0.1)
        assert r1 == pytest.approx(1.0 - 0.7 * 0.1)

    def test_auto_without_usable_gap_gives_none(self, x):
        cfg = FeatureConfig(dirac_mode="auto")
        assert dirac_windows(x, {"gap_left": np.nan, "gap_right": np.nan}, cfg) is None


class TestFeatures:
    def test_recovers_the_crossing_of_two_lines(self, x):
        y = v_shape(x)
        cfg = FeatureConfig(dirac_mode="manual", dirac_left_min=-0.9, dirac_left_max=-0.1,
                            dirac_right_min=0.3, dirac_right_max=0.9)
        out = dirac_features(x, y, {}, cfg)
        assert out["dirac_point"] == pytest.approx(0.1, abs=1e-6)
        assert out["dirac_conductance"] == pytest.approx(0.05, abs=1e-6)
        assert out["dirac_slope_left"] == pytest.approx(-2.0)
        assert out["dirac_slope_right"] == pytest.approx(3.0)
        assert out["dirac_r2_left"] == pytest.approx(1.0)
        assert out["dirac_slope_asymmetry"] == pytest.approx(1.5)

    def test_off_yields_nan_columns_not_missing_ones(self, x):
        out = dirac_features(x, v_shape(x), {}, FeatureConfig(dirac_mode="off"))
        assert set(out) == set(DIRAC_COLUMNS)
        assert all(np.isnan(v) for v in out.values())

    def test_columns_are_appended_at_the_end_of_the_table(self):
        cols = feature_columns()
        assert cols[-len(DIRAC_COLUMNS):] == DIRAC_COLUMNS

    def test_spectrum_features_carries_the_group(self, x):
        row = spectrum_features(x, v_shape(x) + 0.5, FeatureConfig(
            dirac_mode="manual", dirac_left_min=-0.9, dirac_left_max=-0.1,
            dirac_right_min=0.3, dirac_right_max=0.9))
        for c in DIRAC_COLUMNS:
            assert c in row
        assert np.isfinite(row["dirac_point"])


class TestValidation:
    def test_bad_mode_is_rejected(self):
        with pytest.raises(ValueError):
            FeatureConfig(dirac_mode="sideways").validate()

    def test_manual_windows_must_be_ordered(self):
        with pytest.raises(ValueError):
            FeatureConfig(dirac_mode="manual", dirac_left_min=0.0, dirac_left_max=-1.0,
                          dirac_right_min=0.0, dirac_right_max=1.0).validate()
