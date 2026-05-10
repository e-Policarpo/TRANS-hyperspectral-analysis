"""
Spectral axis unit conversion.

Photoluminescence and Raman spectra can be plotted against several
equivalent independent variables, all related by simple algebra:

- **Wavelength** — λ in nm.
- **Energy** — E in eV (``E = 1239.841984 / λ_nm``).
- **Wavenumber** — ν̃ in cm⁻¹ (absolute, ``ν̃ = 1e7 / λ_nm``).
- **Raman shift** — Δν̃ in cm⁻¹ relative to a laser excitation
  wavelength λ_ex (``Δν̃ = 1e7 / λ_ex_nm − 1e7 / λ_nm``).

This module exposes a single :func:`convert_axis` helper that translates
a numpy array between any pair of these units. Conversions that flip
the sign of the dependent axis (e.g. nm → eV reverses the order) leave
the y-data alone — callers may want to reverse the DataFrame rows for
human-friendly display, but the math is unit-correct as-is.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AxisUnit(str, Enum):
    """Recognized spectral-axis units."""
    NM = "nm"
    EV = "eV"
    CM_INV = "cm-1"          # absolute wavenumber
    RAMAN_SHIFT = "raman_cm-1"  # cm⁻¹ relative to laser excitation


# Synonyms users (or WITec's StandardUnit field) may emit. Folded into the
# canonical enum on the way in so callers don't have to normalize.
_ALIASES = {
    "nm": AxisUnit.NM,
    "nanometer": AxisUnit.NM,
    "nanometers": AxisUnit.NM,
    "ev": AxisUnit.EV,
    "electronvolt": AxisUnit.EV,
    "cm-1": AxisUnit.CM_INV,
    "1/cm": AxisUnit.CM_INV,
    "wavenumber": AxisUnit.CM_INV,
    "raman_cm-1": AxisUnit.RAMAN_SHIFT,
    "raman shift": AxisUnit.RAMAN_SHIFT,
    "raman": AxisUnit.RAMAN_SHIFT,
    "delta_nu": AxisUnit.RAMAN_SHIFT,
}


def parse_unit(value) -> AxisUnit:
    """Coerce an :class:`AxisUnit` or a string alias to a canonical unit.

    Raises :class:`ValueError` for unrecognized strings.
    """
    if isinstance(value, AxisUnit):
        return value
    key = str(value).strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(f"Unknown spectral axis unit: {value!r}")


# Constant used by all conversions: hc / e in nm·eV (CODATA-2018).
_HC_OVER_E_NM_EV = 1239.841984


def _to_nm(values: np.ndarray, source: AxisUnit,
           excitation_nm: Optional[float]) -> np.ndarray:
    """Internal: convert ``values`` from ``source`` to wavelength in nm."""
    if source == AxisUnit.NM:
        return values
    if source == AxisUnit.EV:
        # E[eV] = hc/(e·λ[nm]) ⇒ λ[nm] = hc/(e·E[eV])
        return _HC_OVER_E_NM_EV / values
    if source == AxisUnit.CM_INV:
        # ν̃[cm⁻¹] = 1e7/λ[nm] ⇒ λ[nm] = 1e7/ν̃
        return 1.0e7 / values
    if source == AxisUnit.RAMAN_SHIFT:
        if excitation_nm is None or excitation_nm <= 0:
            raise ValueError(
                "Raman-shift input requires a positive excitation wavelength"
            )
        # Δν̃ = 1e7/λ_ex − 1e7/λ ⇒ 1/λ = 1/λ_ex − Δν̃/1e7 ⇒ λ = 1/(1/λ_ex − Δν̃/1e7)
        return 1.0 / (1.0 / excitation_nm - values / 1.0e7)
    raise ValueError(f"Unsupported source unit {source}")


def _from_nm(values_nm: np.ndarray, target: AxisUnit,
             excitation_nm: Optional[float]) -> np.ndarray:
    """Internal: convert wavelength (nm) values to ``target``."""
    if target == AxisUnit.NM:
        return values_nm
    if target == AxisUnit.EV:
        return _HC_OVER_E_NM_EV / values_nm
    if target == AxisUnit.CM_INV:
        return 1.0e7 / values_nm
    if target == AxisUnit.RAMAN_SHIFT:
        if excitation_nm is None or excitation_nm <= 0:
            raise ValueError(
                "Raman-shift output requires a positive excitation wavelength"
            )
        return 1.0e7 / excitation_nm - 1.0e7 / values_nm
    raise ValueError(f"Unsupported target unit {target}")


def convert_axis(
    values,
    source,
    target,
    excitation_nm: Optional[float] = None,
) -> np.ndarray:
    """Convert spectral-axis values between any pair of supported units.

    Parameters
    ----------
    values
        Scalar, list, or numpy array of axis samples in ``source`` units.
    source, target
        :class:`AxisUnit` instances or recognized aliases (``"nm"``,
        ``"eV"``, ``"cm-1"``, ``"raman_cm-1"``, plus a few obvious synonyms).
    excitation_nm
        Laser excitation wavelength in nanometers. Required whenever
        ``source`` or ``target`` is :attr:`AxisUnit.RAMAN_SHIFT`.

    Returns
    -------
    np.ndarray
        Float64 array of converted values.

    Notes
    -----
    Conversions that flip axis monotonicity (e.g. nm → eV) leave the
    y-data alone — callers should reverse DataFrame rows themselves if
    they need ascending x. This function is purely an axis transform.
    """
    src = parse_unit(source)
    tgt = parse_unit(target)
    arr = np.asarray(values, dtype=np.float64)
    if src == tgt:
        return arr.copy()
    nm = _to_nm(arr, src, excitation_nm)
    return _from_nm(nm, tgt, excitation_nm)


def convert_dataframe_axis(
    df: pd.DataFrame,
    source,
    target,
    excitation_nm: Optional[float] = None,
    new_column_name: Optional[str] = None,
) -> pd.DataFrame:
    """Return a new DataFrame whose first column has been converted.

    Parameters
    ----------
    df
        DataFrame whose first column is the spectral axis; subsequent
        columns are intensity / spectrum data left untouched.
    source, target
        Source and target :class:`AxisUnit` values.
    excitation_nm
        Required for Raman-shift conversions.
    new_column_name
        Override for the output's first-column name. Defaults to a
        domain-friendly label (``"Wavelength_nm"``, ``"Energy_eV"``,
        ``"Wavenumber_cm-1"``, ``"Raman_Shift_cm-1"``).
    """
    if df.shape[1] < 1:
        raise ValueError("DataFrame must have at least one column")
    converted = convert_axis(df.iloc[:, 0].values, source, target, excitation_nm)
    out = df.copy()
    name = new_column_name or default_column_name(parse_unit(target))
    out.columns = [name] + list(df.columns[1:])
    out.iloc[:, 0] = converted
    # If the conversion reversed monotonicity, put rows back in ascending x.
    if len(converted) > 1 and converted[0] > converted[-1]:
        out = out.iloc[::-1].reset_index(drop=True)
    return out


def default_column_name(unit: AxisUnit) -> str:
    """Domain-friendly column name for a converted DataFrame."""
    return {
        AxisUnit.NM: "Wavelength_nm",
        AxisUnit.EV: "Energy_eV",
        AxisUnit.CM_INV: "Wavenumber_cm-1",
        AxisUnit.RAMAN_SHIFT: "Raman_Shift_cm-1",
    }[unit]
