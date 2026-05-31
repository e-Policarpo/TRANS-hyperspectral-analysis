"""
Tests for the WITec loader's per-spectrum exposure normalisation.

WITec records spectrum intensities as raw counts accumulated across
``Integration Time [s] × Number Of Accumulations``. Dividing the
columns by that factor at load time gives counts/s/accumulation —
the standard normalisation that downstream processing
(background-subtraction, peak fitting, cross-spectrum comparison)
expects.

These tests exercise:

- ``_parse_info_text`` extracting ``integration_time_s`` and
  ``accumulation_count`` out of WITec's RTF info string;
- ``_build_dataframe`` dividing each spectrum by its factor when
  supplied;
- the absence / invalid-field cases that should leave intensities
  untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from src.data_loaders.witec_wip_loader import WitecWipLoader, _parse_info_text


# -----------------------------------------------------------------
# _parse_info_text
# -----------------------------------------------------------------

_INFO_4CZIPN = (
    "Arial;Arial;\n"
    "Spectral Stitching\n\n"
    " General:\n"
    " System ID:100-1400-1232\n"
    " Start Time:4:00:16 PM\n"
    " Start Date:Friday, May 29, 2026\n"
    " Duration:0h 14m 54s\n"
    " User Name:Witec\n"
    " Configuration:Raman CCD1\n"
    " UHTS300S_VIS:\n"
    " Excitation Wavelength [nm]:456.929\n"
    " DU970P_BVF:\n"
    " Width [Pixels]:1600\n"
    " Number Of Accumulations:8\n"
    " Integration Time [s]:10.00000\n"
    " Objective:\n"
    " Objective Name:Nikon CF Plan ELWD 50x / 0.55\n"
    " Objective Magnification:50.0\n"
    " Sample Location (global position):\n"
    " Position X [µm]:-11.600\n"
    " Position Y [µm]:111.891\n"
)


def test_parse_info_text_extracts_integration_and_accumulations():
    info = _parse_info_text(_INFO_4CZIPN)
    assert info["integration_time_s"] == pytest.approx(10.0)
    assert info["accumulation_count"] == 8


def test_parse_info_text_skips_non_positive_values():
    text = _INFO_4CZIPN.replace(
        "Integration Time [s]:10.00000", "Integration Time [s]:0",
    )
    info = _parse_info_text(text)
    assert "integration_time_s" not in info
    # Accumulations still present and valid.
    assert info["accumulation_count"] == 8


def test_parse_info_text_handles_missing_fields():
    text = _INFO_4CZIPN.replace(
        "Number Of Accumulations:8\n", ""
    ).replace(
        "Integration Time [s]:10.00000\n", ""
    )
    info = _parse_info_text(text)
    assert "integration_time_s" not in info
    assert "accumulation_count" not in info


def test_parse_info_text_handles_malformed_values():
    text = _INFO_4CZIPN.replace(
        "Number Of Accumulations:8", "Number Of Accumulations:N/A",
    )
    info = _parse_info_text(text)
    assert "accumulation_count" not in info


# -----------------------------------------------------------------
# _build_dataframe normalisation
# -----------------------------------------------------------------

@dataclass
class _StubEntry:
    id: int
    caption: str


class _StubGraph:
    """Minimal stand-in for ``WipGraph`` so ``_build_dataframe`` can
    pull intensities + a caption without us building a synthetic
    wip-file byte stream."""

    def __init__(self, entry_id: int, caption: str, spectrum: np.ndarray):
        self.entry = _StubEntry(id=entry_id, caption=caption)
        self._spectrum = spectrum

    def get_spectrum(self, _ix: int = 0, _iy: int = 0) -> np.ndarray:
        return self._spectrum


def _two_spectrum_group():
    axis = np.linspace(400.0, 500.0, 5)
    a = np.array([80.0, 80.0, 80.0, 80.0, 80.0])
    b = np.array([40.0, 40.0, 40.0, 40.0, 40.0])
    return axis, [
        (_StubGraph(120, "Spec A", a), axis, "nm"),
        (_StubGraph(125, "Spec B", b), axis, "nm"),
    ]


def test_build_dataframe_divides_by_factor():
    """A spectrum captured at 10 s × 8 accumulations (= 80) should
    divide by 80 to yield counts/s/accumulation."""
    loader = WitecWipLoader()
    axis, group = _two_spectrum_group()
    df = loader._build_dataframe(
        axis, "nm", group, normalization_factors=[80.0, 40.0],
    )
    cols = list(df.columns)
    assert cols[0] == "Wavelength_nm"
    # Spec A normalised: 80 / 80 = 1.0
    np.testing.assert_allclose(df[cols[1]].values, 1.0)
    # Spec B normalised: 40 / 40 = 1.0
    np.testing.assert_allclose(df[cols[2]].values, 1.0)


def test_build_dataframe_skips_normalisation_when_none():
    """A ``None`` factor leaves the spectrum at raw counts."""
    loader = WitecWipLoader()
    axis, group = _two_spectrum_group()
    df = loader._build_dataframe(
        axis, "nm", group, normalization_factors=[None, 40.0],
    )
    cols = list(df.columns)
    np.testing.assert_allclose(df[cols[1]].values, 80.0)   # untouched
    np.testing.assert_allclose(df[cols[2]].values, 1.0)    # normalised


def test_build_dataframe_no_factors_at_all_preserves_counts():
    loader = WitecWipLoader()
    axis, group = _two_spectrum_group()
    df = loader._build_dataframe(axis, "nm", group)
    cols = list(df.columns)
    np.testing.assert_allclose(df[cols[1]].values, 80.0)
    np.testing.assert_allclose(df[cols[2]].values, 40.0)


def test_build_dataframe_rejects_zero_or_negative_factors():
    """A non-positive factor is treated the same as ``None``."""
    loader = WitecWipLoader()
    axis, group = _two_spectrum_group()
    df = loader._build_dataframe(
        axis, "nm", group, normalization_factors=[0.0, -10.0],
    )
    cols = list(df.columns)
    np.testing.assert_allclose(df[cols[1]].values, 80.0)
    np.testing.assert_allclose(df[cols[2]].values, 40.0)
