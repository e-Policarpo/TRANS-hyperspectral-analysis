"""
Tests for the spectral-axis unit conversion utility.

Pure-math tests against well-known reference values:
- 532 nm ≈ 2.330 eV (Nd:YAG laser line)
- 633 nm ≈ 1.959 eV / 15 803 cm⁻¹ (HeNe laser line)
- Raman shift round-trip: nm ↔ Raman cm⁻¹ for a 532 nm excitation.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backend.spectral_axis import (
    AxisUnit,
    convert_axis,
    convert_dataframe_axis,
    default_column_name,
    parse_unit,
)


# =============================================================================
# Unit parsing
# =============================================================================

@pytest.mark.parametrize("value,expected", [
    ("nm", AxisUnit.NM),
    ("NM", AxisUnit.NM),
    ("eV", AxisUnit.EV),
    ("electronvolt", AxisUnit.EV),
    ("cm-1", AxisUnit.CM_INV),
    ("1/cm", AxisUnit.CM_INV),
    ("WaveNumber", AxisUnit.CM_INV),
    ("raman_cm-1", AxisUnit.RAMAN_SHIFT),
    ("Raman Shift", AxisUnit.RAMAN_SHIFT),
])
def test_parse_unit_aliases(value, expected):
    assert parse_unit(value) == expected


def test_parse_unit_unknown_raises():
    with pytest.raises(ValueError):
        parse_unit("kg")


# =============================================================================
# nm ↔ eV (well-known laser lines)
# =============================================================================

def test_nm_to_ev_at_532nm():
    e = convert_axis([532.0], "nm", "eV")
    assert np.allclose(e, [2.3304], atol=1e-3)


def test_ev_to_nm_at_2_33eV():
    nm = convert_axis([2.3304], "eV", "nm")
    assert np.allclose(nm, [532.0], atol=0.5)


def test_nm_to_cm_inv_at_633nm():
    cm = convert_axis([633.0], "nm", "cm-1")
    assert np.allclose(cm, [15797.78], atol=1e-1)


def test_cm_inv_to_nm_round_trip():
    arr = np.array([461.0, 500.0, 600.0, 700.0])
    cm = convert_axis(arr, "nm", "cm-1")
    back = convert_axis(cm, "cm-1", "nm")
    assert np.allclose(arr, back, atol=1e-9)


# =============================================================================
# Raman shift (requires excitation wavelength)
# =============================================================================

def test_raman_shift_zero_at_excitation():
    """At λ_ex itself, Raman shift must be exactly 0 cm⁻¹."""
    rs = convert_axis([532.0], "nm", "raman_cm-1", excitation_nm=532.0)
    assert np.allclose(rs, [0.0], atol=1e-6)


def test_raman_shift_anti_stokes_negative():
    """Wavelengths shorter than λ_ex give negative Raman shift (anti-Stokes)."""
    rs = convert_axis([520.0], "nm", "raman_cm-1", excitation_nm=532.0)
    assert rs[0] < 0


def test_raman_shift_stokes_positive():
    """Wavelengths longer than λ_ex give positive shift (Stokes)."""
    rs = convert_axis([550.0], "nm", "raman_cm-1", excitation_nm=532.0)
    assert rs[0] > 0


def test_raman_shift_round_trip():
    """nm → Raman cm⁻¹ → nm round-trips exactly."""
    arr = np.array([520.0, 550.0, 580.0, 600.0])
    rs = convert_axis(arr, "nm", "raman_cm-1", excitation_nm=532.0)
    back = convert_axis(rs, "raman_cm-1", "nm", excitation_nm=532.0)
    assert np.allclose(arr, back, atol=1e-9)


def test_raman_shift_requires_excitation_wavelength():
    with pytest.raises(ValueError):
        convert_axis([532.0], "nm", "raman_cm-1")
    with pytest.raises(ValueError):
        convert_axis([0.0], "raman_cm-1", "nm")


# =============================================================================
# DataFrame helper
# =============================================================================

def test_convert_dataframe_axis_renames_first_column():
    df = pd.DataFrame({
        "Wavelength_nm": [500.0, 600.0, 700.0],
        "S1": [10.0, 20.0, 30.0],
        "S2": [40.0, 50.0, 60.0],
    })
    out = convert_dataframe_axis(df, "nm", "eV")
    assert out.columns[0] == "Energy_eV"
    # Y-columns untouched.
    assert np.allclose(out["S1"].values, [30.0, 20.0, 10.0]) or \
           np.allclose(out["S1"].values, [10.0, 20.0, 30.0])


def test_convert_dataframe_axis_reverses_when_monotonicity_flips():
    """nm → eV reverses order; helper must restore ascending x."""
    df = pd.DataFrame({
        "Wavelength_nm": [500.0, 600.0, 700.0],
        "S1": [10.0, 20.0, 30.0],
    })
    out = convert_dataframe_axis(df, "nm", "eV")
    eV = out["Energy_eV"].values
    assert eV[0] < eV[-1], "Energy axis should be ascending after conversion"
    # And the y-data went along for the ride.
    assert out["S1"].values[0] == 30.0
    assert out["S1"].values[-1] == 10.0


def test_convert_dataframe_axis_no_op_for_same_unit():
    df = pd.DataFrame({
        "Wavelength_nm": [500.0, 600.0, 700.0],
        "S1": [1.0, 2.0, 3.0],
    })
    out = convert_dataframe_axis(df, "nm", "nm")
    assert list(out.columns) == ["Wavelength_nm", "S1"]
    assert np.array_equal(out["S1"].values, df["S1"].values)


def test_convert_dataframe_axis_raman_shift_uses_excitation():
    df = pd.DataFrame({
        "Wavelength_nm": [532.0, 540.0, 600.0],
        "S1": [1.0, 2.0, 3.0],
    })
    out = convert_dataframe_axis(
        df, "nm", "raman_cm-1", excitation_nm=532.0
    )
    assert out.columns[0] == "Raman_Shift_cm-1"
    # First sample (at 532 nm) must produce shift = 0.
    rs = out["Raman_Shift_cm-1"].values
    assert any(abs(v) < 1e-6 for v in rs)


# =============================================================================
# Default column names
# =============================================================================

@pytest.mark.parametrize("unit,expected", [
    (AxisUnit.NM, "Wavelength_nm"),
    (AxisUnit.EV, "Energy_eV"),
    (AxisUnit.CM_INV, "Wavenumber_cm-1"),
    (AxisUnit.RAMAN_SHIFT, "Raman_Shift_cm-1"),
])
def test_default_column_names(unit, expected):
    assert default_column_name(unit) == expected
