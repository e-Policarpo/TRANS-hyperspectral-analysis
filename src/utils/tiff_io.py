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
from typing import Any, Dict, Mapping, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ImageJ spells a few units differently from the instrument metadata.
_IJ_UNIT = {
    "µm": "micron", "um": "micron", "micron": "micron", "microns": "micron",
    "nm": "nm", "mm": "mm", "cm": "cm", "m": "meter",
}


def _clean_unit(unit: Optional[str]) -> str:
    """A unit string safe to put in an ImageJ description.

    The description is a line-based ``key=value`` block and per-channel units
    are packed one-per-channel separated by tabs, so a unit carrying a tab or
    a newline would silently corrupt every field after it. ``=`` is dropped
    for a sharper reason: tifffile parses each line with a bare
    ``line.split('=')`` and unpacks two values, so a second ``=`` anywhere on
    the line raises and the whole line is skipped — the field would be written
    and then never read back. No real unit contains any of the three.
    """
    return " ".join(str(unit or "").replace("=", "").split())


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



def write_channel_stack_tiff(path: Union[str, Path],
                             channels: Dict[str, np.ndarray],
                             dx: Optional[float] = None,
                             dy: Optional[float] = None,
                             unit: Optional[str] = None,
                             clip_percentile: float = 1.0,
                             value_units: Optional[Mapping[str, str]] = None,
                             default_value_unit: Optional[str] = None) -> str:
    """One multi-page TIFF for a whole scan: every channel a page.

    An ImageJ hyperstack (``axes=CYX``), so Fiji opens it as one image with
    a channel slider, each page carrying its channel name as the slice
    label and its own display range — a topography and a current map do
    not share a sensible min/max. The pixel scale rides on the same
    resolution tags :func:`imagej_tiff_kwargs` writes, so Fiji and Gwyddion
    read real units; Gwyddion opens each page as a separate field.

    ``value_units`` maps channel name → Z-axis unit (e.g. ``{"Z fwd/up":
    "m", "I fwd/up": "A"}``), with ``default_value_unit`` covering any
    channel not listed — the same pair :func:`src.utils.gwy_io.write_gwy`
    takes, so a scan's ``.gwy`` and its TIFF describe their numbers
    identically. Without them the pages are calibrated in *x* and *y* but
    their values are bare floats that say nothing about being metres, amps
    or volts.

    Channels are stacked as float32 when their dtypes differ (a scan mixes
    heights and currents; a uint16 page next to a float one is not a
    stack). All pages must share one shape — that is the definition of a
    scan's channels, and anything else is a different image.
    """
    import tifffile

    names = [str(n) for n in channels]
    arrays = [np.asarray(channels[n]) for n in channels]
    if not arrays:
        raise ValueError("no channels to write")
    shape = arrays[0].shape
    if any(a.shape != shape for a in arrays):
        raise ValueError("channel shapes differ: "
                         + ", ".join(f"{n}:{a.shape}" for n, a in zip(names, arrays)))
    if len({a.dtype for a in arrays}) > 1 or not np.issubdtype(arrays[0].dtype, np.floating):
        arrays = [a.astype(np.float32) for a in arrays]
    stack = np.stack(arrays, axis=0)

    ranges = []
    for a in arrays:
        finite = a[np.isfinite(a)]
        if finite.size:
            lo = float(np.percentile(finite, clip_percentile))
            hi = float(np.percentile(finite, 100.0 - clip_percentile))
            if not (hi > lo):
                hi = lo + 1.0
        else:
            lo, hi = 0.0, 1.0
        ranges += [lo, hi]

    metadata: Dict[str, Any] = {
        "axes": "CYX",
        "Labels": names,
        "mode": "grayscale",
        "hyperstack": True,
        # A tuple, not a list: tifffile writes a list as one entry per
        # element, and the IJ 'rang' block is one flat run of doubles.
        "Ranges": tuple(ranges),
    }
    # Z units, positional like Labels and Ranges: ImageJ has no per-channel
    # unit field, so they ride in the description as one tab-separated run in
    # channel order. Written only when at least one channel has a unit, so a
    # scan that knows none adds no empty tag.
    declared = dict(value_units or {})
    per_channel = [_clean_unit(declared.get(n) or default_value_unit)
                   for n in names]
    if any(per_channel):
        metadata["value_units"] = "\t".join(per_channel)
    else:
        logger.warning("Channel stack %s carries no Z units — its pages will "
                       "open as bare numbers.", Path(path).name)

    kwargs: Dict[str, Any] = {"imagej": True, "rowsperstrip": 64}
    if dx and dy and dx > 0 and dy > 0:
        ij_unit = _IJ_UNIT.get((unit or "").strip(), (unit or "").strip())
        denom = 1_000_000
        kwargs["resolution"] = ((int(round((1.0 / dx) * denom)), denom),
                                (int(round((1.0 / dy) * denom)), denom))
        if ij_unit:
            metadata["unit"] = ij_unit
    else:
        logger.warning("Writing UNCALIBRATED channel stack %s — no physical "
                       "pixel size was available.", Path(path).name)
    tifffile.imwrite(str(path), stack, metadata=metadata, **kwargs)
    return str(path)

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
    carries no usable calibration. ``dx`` / ``dy`` are in ``unit``. A channel
    stack written by :func:`write_channel_stack_tiff` also carries
    ``'value_units'``: one unit per channel, in the order of the ImageJ
    ``Labels``, with ``''`` where the unit was unknown.
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

    out: Dict[str, Any] = {"dx": dx, "dy": dy, "unit": str(unit),
                           "value_unit": ij.get("value_unit")}
    stacked = ij.get("value_units")
    if stacked:
        out["value_units"] = str(stacked).split("\t")
    return out
