"""Shared helpers for writing viewer-friendly, calibrated TIFFs.

**Project rule: every exported artefact carries real physical quantities
whenever they are available.** A file that says "666 × 666 pixels" is not an
acceptable export — opened in Gwyddion or Fiji it must report the true scan
size (e.g. 2.5 × 2.5 µm) and, for float data, the true physical values. Use
:func:`write_calibrated_tiff` rather than calling ``tifffile.imwrite``
directly; it is the single place that guarantees this.

A scientific map is stored as float32 physical values (metres, amps, ~1e-9),
which render **all-black** in Fiji / Gwyddion / Preview unless the file also
carries a *display range*. These helpers build the ``tifffile.imwrite`` keyword
arguments that embed:

* the **physical pixel scale** (``XResolution`` / ``YResolution`` + unit) so the
  image opens spatially calibrated,
* an ImageJ **display range** (``min`` / ``max``) so float data shows real
  contrast on open while the underlying values are preserved untouched, and
* the **value unit** of the Z axis when known, so the numbers are
  self-describing on re-import.

:func:`read_tiff_calibration` is the inverse — it recovers the pixel scale from
a TIFF we (or Gwyddion / Fiji / an instrument) wrote.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ImageJ spells a few units differently from the instrument metadata.
_IJ_UNIT = {
    "µm": "micron", "um": "micron", "micron": "micron", "microns": "micron",
    "nm": "nm", "mm": "mm", "cm": "cm", "m": "meter",
}


def imagej_tiff_kwargs(data: np.ndarray,
                       dx: Optional[float] = None,
                       dy: Optional[float] = None,
                       unit: Optional[str] = None,
                       clip_percentile: float = 1.0,
                       value_unit: Optional[str] = None) -> Dict[str, Any]:
    """tifffile kwargs that make ``data`` open calibrated and non-black.

    Four things are bundled here so every TIFF we emit opens *and displays
    correctly* in Fiji / Gwyddion (and Preview for 8-bit frames):

    1. **Pixel-scale tags** — ``XResolution`` / ``YResolution`` as
       pixels-per-unit with ``ResolutionUnit=NONE``, plus an ImageJ-style
       ``unit=`` line so Fiji picks up the physical scale. The rational uses a
       fixed denominator (1e6) so the uint32 numerator doesn't saturate on
       small pixel sizes (~0.12 µm/px would otherwise blow up to
       4 294 967 295 / N and trip strict TIFF parsers).
    2. **Display range** — ``min=`` / ``max=`` from a robust percentile clip,
       for floating-point data only, where it is both meaningful and necessary.
    3. **Multi-strip layout** (``rowsperstrip=64``) — single-strip TIFFs
       covering tens of megabytes break macOS Preview, which tries to read the
       whole strip into memory at once.
    4. **``metadata=None``** — suppresses tifffile's auto ``{"shape": …}`` tag,
       which would duplicate ``ImageDescription`` (two tag-270 entries) and
       confuses some viewers.

    Parameters
    ----------
    data:
        The array actually being written. A display range is embedded only for
        floating-point data.
    dx, dy:
        Physical pixel size along x / y, in ``unit``. When both are positive,
        resolution tags and a ``unit=`` line are written.
    unit:
        Physical unit of ``dx`` / ``dy`` (e.g. ``"nm"``, ``"µm"``).
    clip_percentile:
        Robust display-range clip; the range is the
        ``[clip_percentile, 100 - clip_percentile]`` percentiles of the finite
        values.

    Returns the kwargs dict; safe to ``**``-splat into ``tifffile.imwrite``.
    """
    kwargs: Dict[str, Any] = {
        "metadata": None,     # suppress tifffile's auto {"shape": …} tag
        "rowsperstrip": 64,   # multi-strip: huge single-strip TIFFs break Preview
    }
    desc_lines = ["ImageJ=1.54p"]

    if dx and dy and dx > 0 and dy > 0:
        ij_unit = _IJ_UNIT.get((unit or "").strip(), (unit or "").strip())
        denom = 1_000_000  # fixed denominator avoids uint32 saturation on tiny px
        kwargs.update({
            "resolution": ((int(round((1.0 / dx) * denom)), denom),
                           (int(round((1.0 / dy) * denom)), denom)),
            "resolutionunit": "NONE",
        })
        if ij_unit:
            desc_lines.append(f"unit={ij_unit}")

    arr = np.asarray(data)
    if np.issubdtype(arr.dtype, np.floating):
        finite = arr[np.isfinite(arr)]
        if finite.size:
            lo = float(np.percentile(finite, clip_percentile))
            hi = float(np.percentile(finite, 100.0 - clip_percentile))
            if not (hi > lo):
                hi = lo + 1.0
            desc_lines += [f"min={lo:.9g}", f"max={hi:.9g}", "mode=grayscale"]

    # Z-axis unit. TIFF has no standard tag for it, so it rides in the
    # description; ``read_tiff_calibration`` reads it back and a human opening
    # the file in Gwyddion can at least see what the numbers mean.
    if value_unit:
        desc_lines.append(f"value_unit={value_unit}")

    # Only attach a description when it says more than the bare header.
    if len(desc_lines) > 1:
        kwargs["description"] = "\n".join(desc_lines) + "\n"
    return kwargs


def write_calibrated_tiff(path: Union[str, Path],
                          data: np.ndarray,
                          dx: Optional[float] = None,
                          dy: Optional[float] = None,
                          unit: Optional[str] = None,
                          value_unit: Optional[str] = None,
                          clip_percentile: float = 1.0,
                          axis_note: Optional[str] = None,
                          context: str = "") -> str:
    """Write ``data`` to ``path`` as a calibrated TIFF. **Use this everywhere.**

    This is the project's single TIFF-writing entry point, so that
    "exports carry real physical dimensions" is enforced in one place instead
    of being re-remembered at each call site. Calling ``tifffile.imwrite``
    directly bypasses the guarantee — don't.

    When ``dx`` / ``dy`` / ``unit`` are missing the file is still written (an
    uncalibrated export beats no export), but a warning naming ``context`` is
    logged so the gap is visible rather than silent.

    Returns the path written, as a string.
    """
    import tifffile

    arr = np.asarray(data)
    if not (dx and dy and dx > 0 and dy > 0 and unit):
        logger.warning(
            "Writing UNCALIBRATED TIFF %s%s — no physical pixel size was "
            "available, so it will open as bare pixels in Gwyddion/Fiji.",
            Path(path).name, f" ({context})" if context else "",
        )
    kwargs = imagej_tiff_kwargs(arr, dx=dx, dy=dy, unit=unit,
                                value_unit=value_unit,
                                clip_percentile=clip_percentile)
    if axis_note:
        # ImageJ has a single unit= for both axes, so a field whose axes are
        # different quantities records them here instead of mislabelling one.
        kwargs["description"] = (kwargs.get("description", "")
                                 + f"axes={axis_note}\n")
    tifffile.imwrite(str(path), arr, **kwargs)
    return str(path)


def read_tiff_calibration(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Recover the physical pixel scale from a TIFF.

    Reads the standard ``XResolution`` / ``YResolution`` rationals (which store
    *pixels per unit*, so the pixel size is their reciprocal) and takes the unit
    from the ImageJ ``unit=`` line in ``ImageDescription``. That combination is
    what Fiji, Gwyddion and this app all write, so it round-trips our own
    exports and reads third-party files.

    Returns ``{'dx', 'dy', 'unit', 'value_unit'}`` or ``None`` when the file
    carries no usable calibration. ``dx`` / ``dy`` are in ``unit``.
    """
    try:
        import tifffile
        with tifffile.TiffFile(str(path)) as tf:
            page = tf.pages[0]
            tags = {t.name: t.value for t in page.tags}
            ij = tf.imagej_metadata or {}
    except Exception as e:
        logger.debug("Could not read TIFF calibration from %s: %s", path, e)
        return None

    def _pixel_size(rational) -> Optional[float]:
        """Rational is pixels-per-unit; the pixel size is its reciprocal."""
        try:
            num, den = rational
            num, den = float(num), float(den)
        except (TypeError, ValueError):
            return None
        if num <= 0 or den <= 0:
            return None
        return den / num

    dx = _pixel_size(tags.get("XResolution"))
    dy = _pixel_size(tags.get("YResolution"))
    if dx is None or dy is None:
        return None

    unit = ij.get("unit")
    if not unit:
        # Fall back to the baseline TIFF ResolutionUnit (2 = inch, 3 = cm).
        res_unit = tags.get("ResolutionUnit")
        unit = {2: "inch", 3: "cm"}.get(
            int(res_unit) if isinstance(res_unit, int) else 0)
    if not unit:
        return None

    return {"dx": dx, "dy": dy, "unit": str(unit),
            "value_unit": ij.get("value_unit")}
