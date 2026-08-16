"""
Length-unit conversion for instrument calibration.

Loaders read pixel sizes in whatever unit the instrument file recorded — µm
for WITec, metres for Omicron MATRIX, µm for Park. The image viewer works in
nanometres internally (``ImageMetadata.pixel_size_nm``) and picks a display
unit from the image's extent, so every loader funnels through here rather
than hardcoding its own factor. A loader that only handled one unit silently
produced uncalibrated images — no scale bar, ticks in pixels — for every
other unit.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
License: GPL
"""

from __future__ import annotations

from typing import Optional

# Nanometres per unit. Keys are lowercased and stripped; the µ/u spellings and
# the plural/long forms all appear in real instrument files.
_TO_NM = {
    "m": 1e9,
    "metre": 1e9, "metres": 1e9, "meter": 1e9, "meters": 1e9,
    "mm": 1e6, "millimetre": 1e6, "millimetres": 1e6,
    "millimeter": 1e6, "millimeters": 1e6,
    "µm": 1e3, "um": 1e3, "μm": 1e3,  # micro sign U+00B5 and Greek mu U+03BC
    "micron": 1e3, "microns": 1e3,
    "micrometre": 1e3, "micrometres": 1e3,
    "micrometer": 1e3, "micrometers": 1e3,
    "nm": 1.0,
    "nanometre": 1.0, "nanometres": 1.0,
    "nanometer": 1.0, "nanometers": 1.0,
    "å": 0.1, "a": 0.1, "angstrom": 0.1, "angstroms": 0.1, "ang": 0.1,
    "pm": 1e-3, "picometre": 1e-3, "picometres": 1e-3,
    "picometer": 1e-3, "picometers": 1e-3,
}


def nm_factor(unit: Optional[str]) -> Optional[float]:
    """Nanometres per ``unit``, or ``None`` when the unit isn't a length.

    >>> nm_factor("µm"), nm_factor("m"), nm_factor("nm")
    (1000.0, 1000000000.0, 1.0)
    >>> nm_factor("volts") is None
    True
    """
    if not unit or not isinstance(unit, str):
        return None
    return _TO_NM.get(unit.strip().lower())


def to_nm(value: float, unit: Optional[str]) -> Optional[float]:
    """Convert ``value`` expressed in ``unit`` to nanometres.

    Returns ``None`` when the unit is unrecognised or the value isn't finite,
    so callers can leave the calibration unset rather than record a wrong one.
    """
    factor = nm_factor(unit)
    if factor is None:
        return None
    try:
        out = float(value) * factor
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # reject NaN


def scale_from_metadata(info: Optional[dict], shape=None):
    """``(dx, dy, unit)`` per pixel from whatever extent a loader recorded.

    Loaders describe scan geometry in several different ways depending on the
    instrument. Rather than each export site knowing all of them, they call
    here. Checked in order of directness:

    1. ``pixel_size`` — ``{'dx','dy','unit'}`` (WITec)
    2. ``pixel_size_nm`` — ``(dy, dx)`` in nm (Omicron scan images)
    3. ``width_m`` / ``height_m`` + array shape (Omicron MATRIX scans)
    4. ``scan_width_um`` / ``scan_height_um`` + array shape (Park AFM)
    5. ``physical_size`` — ``(height, width)`` + ``units`` (TopographyData)

    ``shape`` is ``(rows, cols)`` and is required for the extent-based forms,
    which divide the total scan size by the pixel count. Returns
    ``(None, None, None)`` when nothing usable is recorded, which callers turn
    into an explicit "uncalibrated export" warning.
    """
    if not info:
        return (None, None, None)

    ps = info.get("pixel_size")
    if isinstance(ps, dict):
        try:
            dx, dy = float(ps.get("dx") or 0), float(ps.get("dy") or 0)
        except (TypeError, ValueError):
            dx = dy = 0.0
        if dx > 0 and dy > 0:
            return (dx, dy, str(ps.get("unit") or "µm").strip())

    ps_nm = info.get("pixel_size_nm")
    if ps_nm and len(ps_nm) == 2 and ps_nm[0] and ps_nm[1]:
        try:
            return (float(ps_nm[1]), float(ps_nm[0]), "nm")
        except (TypeError, ValueError):
            pass

    rows = cols = None
    if shape is not None and len(shape) >= 2:
        rows, cols = int(shape[0]), int(shape[1])

    if rows and cols:
        for w_key, h_key, unit in (("width_m", "height_m", "m"),
                                   ("scan_width_um", "scan_height_um", "µm")):
            try:
                w, h = float(info.get(w_key) or 0), float(info.get(h_key) or 0)
            except (TypeError, ValueError):
                continue
            if w > 0 and h > 0:
                return (w / cols, h / rows, unit)

        phys = info.get("physical_size")
        if phys and len(phys) == 2:
            try:
                ph, pw = float(phys[0]), float(phys[1])
            except (TypeError, ValueError):
                ph = pw = 0.0
            if ph > 0 and pw > 0:
                unit = info.get("units")
                if isinstance(unit, dict):
                    unit = unit.get("x") or unit.get("y")
                return (pw / cols, ph / rows, str(unit or "µm"))

    return (None, None, None)


def pixel_size_to_nm(dx: float, dy: float, unit: Optional[str]):
    """``(dy, dx)`` in nanometres, matching ``ImageMetadata.pixel_size_nm``
    order, or ``None`` if either axis can't be converted.

    Note the deliberate (row, column) ordering — it trips people up, but it
    matches numpy's array indexing and the rest of the image pipeline.
    """
    dy_nm = to_nm(dy, unit)
    dx_nm = to_nm(dx, unit)
    if dy_nm is None or dx_nm is None or dy_nm <= 0 or dx_nm <= 0:
        return None
    return (dy_nm, dx_nm)
