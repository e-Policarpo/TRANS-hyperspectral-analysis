"""
Tests for the tool dialogs' synchronous preview slots.

``previewConfinementAnalysis`` and ``previewSpectralFeatures`` run one
spectrum on the GUI thread so a tool dialog can redraw as parameters change.
They sit at the QML boundary, which imposes two obligations the batch paths
do not have:

* they must return **plain Python values** -- a QVariantMap will not carry a
  numpy array, so a stray ndarray silently arrives in QML as undefined;
* they must **never raise**. An exception in a slot invoked from a QML
  binding does not surface as a dialog, it just leaves the preview stale
  while the user keeps turning knobs.

Both therefore report failure through an ``ok``/``error`` pair, and these
tests pin that contract rather than only the happy path.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _sts_curve(x, gap_half=0.15, centre=0.0, n_states=0, amplitude=1.0, seed=0):
    rng = np.random.default_rng(seed)
    outside = np.clip(np.abs(x - centre) - gap_half, 0.0, None)
    y = amplitude * 3e-7 * (0.02 + 0.98 * np.tanh(outside / 0.08) ** 2)
    for k in range(n_states):
        c = centre - gap_half + (k + 1) * (2 * gap_half) / (n_states + 1)
        y = y + amplitude * 2.5e-8 * np.exp(-0.5 * ((x - c) / 0.006) ** 2)
    return y + rng.normal(0, amplitude * 8e-11, x.size)


@pytest.fixture
def backend(qapp, tmp_path):
    """An AppBackend holding one STS-like dataset of three spectra.

    A real backend, not a mock: these slots exist to be called from QML, so
    the tests exercise the same object QML talks to. It needs an output
    directory because the batch paths used for cross-checking write CSVs.
    """
    x = np.linspace(-0.6, 0.6, 512)
    df = pd.DataFrame({
        "V": x,
        "R1": _sts_curve(x, n_states=3),
        "R2": _sts_curve(x, gap_half=0.09, seed=1),
        # Same physics as R1 but a tip three times closer.
        "R3": _sts_curve(x, n_states=3, amplitude=3.0),
    })
    instance = AppBackend()
    instance._output_base_dir = tmp_path / "outputs"
    instance._datasets["STS"] = SpectralData(df, SpectralMetadata(
        source_type="sts", dimensions=(3, 1), scan_mode="line",
        units={"x": "V"}, additional_info={}))
    return instance


def _assert_qml_safe(payload):
    """Every value must survive the trip through a QVariantMap."""
    for key, value in payload.items():
        assert not isinstance(value, np.ndarray), f"{key} is an ndarray"
        if isinstance(value, list):
            for item in value:
                assert isinstance(item, (float, int, str)), f"{key} holds {type(item)}"
        else:
            assert isinstance(value, (float, int, str, bool)), f"{key} is {type(value)}"


# ---------------------------------------------------------------------------
# Confinement Analysis preview
# ---------------------------------------------------------------------------

class TestConfinementPreview:

    def test_returns_the_curves_the_dialog_plots(self, backend):
        result = backend.previewConfinementAnalysis(
            "STS", 0, {"baseline": "poly-iter", "baseline_degree": 5})

        assert result["ok"] is True
        assert result["name"] == "R1"
        assert len(result["x"]) == len(result["raw"]) == len(result["corrected"]) == 512
        assert len(result["baseline"]) == 512
        assert len(result["peakX"]) == len(result["peakY"]) == result["count"]

    def test_everything_returned_is_qml_safe(self, backend):
        _assert_qml_safe(backend.previewConfinementAnalysis("STS", 0, {}))

    def test_no_background_means_no_baseline_curve(self, backend):
        """The dialog keys 'draw the background' off this being empty."""
        result = backend.previewConfinementAnalysis("STS", 0, {"baseline": "none"})
        assert result["ok"] is True
        assert result["baseline"] == []

    def test_agrees_with_the_batch_run(self, backend):
        """A preview that disagrees with what Run produces is worse than none."""
        params = {"baseline": "poly-iter", "baseline_degree": 5, "height": 5.0}
        preview = backend.previewConfinementAnalysis("STS", 0, params)

        class MockTask:
            cancelled = False

        batch = backend.analyze_confinement(MockTask(), "STS", params=params)
        first = batch["peaks"].data.query("spectrum_index == 0")["position_value"]
        np.testing.assert_allclose(sorted(preview["peakX"]), sorted(first), atol=1e-12)

    def test_spectrum_index_is_clamped_not_crashed(self, backend):
        result = backend.previewConfinementAnalysis("STS", 99, {})
        assert result["ok"] is True
        assert result["name"] == "R3"

    def test_missing_dataset_reports_instead_of_raising(self, backend):
        result = backend.previewConfinementAnalysis("nope", 0, {})
        assert result["ok"] is False
        assert result["error"] == "Dataset not found"
        assert result["x"] == []

    def test_bad_parameters_report_instead_of_raising(self, backend):
        result = backend.previewConfinementAnalysis("STS", 0, {"direction": "sideways"})
        assert result["ok"] is False
        assert "direction must be one of" in result["error"]

    def test_empty_params_use_the_product_defaults(self, backend):
        """An empty map is what a freshly opened dialog sends."""
        result = backend.previewConfinementAnalysis("STS", 0, {})
        assert result["ok"] is True
        # CONFINEMENT_DEFAULTS turns the background on, so it is drawn.
        assert result["baseline"] != []


# ---------------------------------------------------------------------------
# Spectral Features preview
# ---------------------------------------------------------------------------

class TestSpectralFeaturesPreview:

    def test_returns_the_curve_the_gap_and_the_states(self, backend):
        result = backend.previewSpectralFeatures("STS", 0, {})

        assert result["ok"] is True
        assert result["name"] == "R1"
        assert result["valid"] is True
        assert len(result["x"]) == len(result["y"]) == 512
        assert result["gapLeft"] < result["gapRight"]
        # Three states were planted, and they lie inside the detected gap.
        assert len(result["stateX"]) == 3
        for position in result["stateX"]:
            assert result["gapLeft"] <= position <= result["gapRight"]

    def test_everything_returned_is_qml_safe(self, backend):
        _assert_qml_safe(backend.previewSpectralFeatures("STS", 0, {}))

    def test_readout_pairs_names_with_values(self, backend):
        result = backend.previewSpectralFeatures("STS", 0, {})

        assert len(result["names"]) == len(result["values"])
        assert "gap_width" in result["names"]
        assert "Spectrum_Index" not in result["names"]
        # Values are preformatted strings, so QML need not know about NaN.
        assert all(isinstance(v, str) for v in result["values"])

    def test_unmeasurable_features_show_as_a_dash(self, backend):
        """NaN means 'could not be measured', which is information; showing
        it as 0 would be a lie."""
        result = backend.previewSpectralFeatures("STS", 1, {})   # R2, no states
        readout = dict(zip(result["names"], result["values"]))
        assert readout["state_spacing_mean"] == "--"
        assert readout["n_states"] == "0"

    def test_agrees_with_the_batch_run(self, backend):
        preview = backend.previewSpectralFeatures("STS", 0, {})

        class MockTask:
            cancelled = False

        table = backend.extract_spectral_features(MockTask(), "STS", params={})["features"].data
        row = table.iloc[0]
        readout = dict(zip(preview["names"], preview["values"]))

        assert float(readout["n_states"]) == row["n_states"]
        assert preview["gapLeft"] == pytest.approx(row["gap_left"])
        assert preview["gapRight"] == pytest.approx(row["gap_right"])

    def test_normalisation_makes_the_preview_tip_height_independent(self, backend):
        """R1 and R3 are the same physics three times closer to the tip."""
        near = backend.previewSpectralFeatures("STS", 0, {})
        far = backend.previewSpectralFeatures("STS", 2, {})

        np.testing.assert_allclose(near["y"], far["y"], rtol=1e-6)
        assert near["gapLeft"] == pytest.approx(far["gapLeft"])
        assert len(near["stateX"]) == len(far["stateX"])

    def test_parameters_reach_the_preview(self, backend):
        loose = backend.previewSpectralFeatures("STS", 0, {"state_noise_sigmas": 4.0})
        strict = backend.previewSpectralFeatures("STS", 0, {"state_noise_sigmas": 1e6})
        assert len(loose["stateX"]) == 3
        assert strict["stateX"] == []

    def test_basis_renames_the_readout_rows(self, backend):
        legendre = backend.previewSpectralFeatures("STS", 0, {"poly_basis": "legendre"})
        power = backend.previewSpectralFeatures("STS", 0, {"poly_basis": "power"})
        assert "P2" in legendre["names"] and "c2" not in legendre["names"]
        assert "c2" in power["names"]

    def test_invalid_spectrum_is_flagged_for_the_dialog(self, backend):
        backend._datasets["dead"] = SpectralData(
            pd.DataFrame({"V": np.linspace(-0.6, 0.6, 512),
                          "flat": np.zeros(512)}),
            SpectralMetadata(source_type="sts", dimensions=(1, 1), scan_mode="point",
                             units={"x": "V"}, additional_info={}))

        result = backend.previewSpectralFeatures("dead", 0, {})
        assert result["ok"] is True      # it previewed fine...
        assert result["valid"] is False  # ...but the spectrum is unusable

    def test_spectrum_index_is_clamped_not_crashed(self, backend):
        assert backend.previewSpectralFeatures("STS", 99, {})["name"] == "R3"

    def test_missing_dataset_reports_instead_of_raising(self, backend):
        result = backend.previewSpectralFeatures("nope", 0, {})
        assert result["ok"] is False
        assert result["error"] == "Dataset not found"

    def test_bad_parameters_report_instead_of_raising(self, backend):
        result = backend.previewSpectralFeatures("STS", 0, {"normalize": "quantile"})
        assert result["ok"] is False
        assert "normalize must be one of" in result["error"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_slots_are_visible_to_qml(qapp):
    """A slot missing from the meta-object is simply not callable from QML,
    with no error at load time."""
    meta = AppBackend.staticMetaObject
    signatures = {meta.method(i).methodSignature().data().decode()
                  for i in range(meta.methodCount())}

    assert "previewConfinementAnalysis(QString,int,QVariantMap)" in signatures
    assert "previewSpectralFeatures(QString,int,QVariantMap)" in signatures
    assert "runConfinementAnalysis(QString,QVariantMap)" in signatures
    assert "extractSpectralFeatures(QString,QVariantMap)" in signatures
