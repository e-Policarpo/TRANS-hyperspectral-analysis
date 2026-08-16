"""One entry point for exporting a 2D scientific field to disk.

**Project rule: an export always carries real physical quantities when they
are available.** "666 × 666 pixels" is not an acceptable description of a
2.5 × 2.5 µm scan. Any new feature that writes map/scan/image data to disk
should call :func:`export_field` rather than ``tifffile.imwrite`` or
``PIL.Image.save`` directly, so the rule is enforced in one place instead of
being re-remembered at every call site.

``.gsf`` (Gwyddion Simple Field) is the **default and primary** format:
Gwyddion is the analysis tool for this data, and it is the only format
Gwyddion reads real dimensions from — its pixmap importer ignores TIFF
resolution tags and asks the user to type dimensions in by hand, so a TIFF
alone always lands there as bare pixels.

``.tiff`` is **secondary**, produced on request (``formats=("gsf", "tiff")``)
when an ImageJ/Fiji copy or an OS-viewable raster is wanted. It is float32
with ImageJ-style resolution tags and a display range.

Neither normalises the data — both keep the true float values.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
License: GPL
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

import numpy as np

from src.utils.gsf_io import write_gsf
from src.utils.tiff_io import write_calibrated_tiff
from src.utils.units import to_nm

logger = logging.getLogger(__name__)

# GSF first: Gwyddion is the analysis tool for this SPM data and the only
# format it reads real dimensions from. TIFF follows as the secondary,
# general-purpose copy — several internal artefacts (generated maps, the map
# canvas "save as") are referenced by path elsewhere in the app and need it.
#
# NOTE: imported scan *images* are a different path and write Gwyddion formats
# only — see AppBackend._absorb_dataset_images. Pass formats=("gsf",) here for
# anything that should likewise skip the raster.
DEFAULT_FORMATS = ("gsf", "tiff")


def export_field(base_path: Union[str, Path],
                 data: np.ndarray,
                 dx: Optional[float] = None,
                 dy: Optional[float] = None,
                 unit: Optional[str] = None,
                 value_unit: Optional[str] = None,
                 title: Optional[str] = None,
                 formats: Sequence[str] = DEFAULT_FORMATS,
                 context: str = "") -> Dict[str, str]:
    """Write ``data`` as a calibrated field. Returns ``{format: path}``.

    ``base_path`` is the path *without* extension; each format appends its own.
    ``dx`` / ``dy`` are the **per-pixel** size in ``unit`` (that is what every
    caller has to hand); GSF's total-extent ``XReal`` / ``YReal`` are derived
    from them and the array shape.

    When the scale is unknown the files are still written — an uncalibrated
    export beats none — but a warning naming ``context`` is logged so the gap
    surfaces instead of silently producing a pixel-only file.
    """
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError(f"export_field needs a 2D field, got {arr.shape}")

    base = Path(base_path)
    # Append the extension rather than ``with_suffix``: map basenames routinely
    # contain dots (e.g. "Map_-0.500_-0.300") and with_suffix would eat the
    # "._300" as an existing extension.
    def _out(ext: str) -> Path:
        return Path(str(base) + ext)

    calibrated = bool(dx and dy and dx > 0 and dy > 0 and unit)
    if not calibrated:
        logger.warning(
            "Exporting UNCALIBRATED field %s%s — no physical pixel size "
            "available; it will open as bare pixels.",
            base.name, f" ({context})" if context else "")

    written: Dict[str, str] = {}
    float_data = arr.astype(np.float32, copy=False)

    if "tiff" in formats:
        written["tiff"] = write_calibrated_tiff(
            _out(".tiff"), float_data,
            dx=dx, dy=dy, unit=unit, value_unit=value_unit, context=context)

    if "gsf" in formats:
        # GSF wants the total extent in SI base units. Lengths convert through
        # nm; a non-length lateral unit (or none) is passed straight through
        # with no extent, so Gwyddion falls back to its 1.0 default rather
        # than being told something false.
        x_real = y_real = None
        xy_units = ""
        if calibrated:
            dx_nm, dy_nm = to_nm(dx, unit), to_nm(dy, unit)
            if dx_nm and dy_nm:
                x_real = dx_nm * arr.shape[1] * 1e-9   # nm → m
                y_real = dy_nm * arr.shape[0] * 1e-9
                xy_units = "m"
            else:
                logger.debug(
                    "export_field: %r is not a length unit; GSF written "
                    "without lateral calibration", unit)
        written["gsf"] = write_gsf(
            _out(".gsf"), float_data,
            x_real=x_real, y_real=y_real, xy_units=xy_units,
            z_units=_si_base_unit(value_unit), title=title or base.name)

    return written


def _si_base_unit(unit: Optional[str]) -> Optional[str]:
    """Gwyddion wants ZUnits as a base unit ('m', 'A', 'V'), not a prefixed
    one — the numbers we write are already in base units."""
    if not unit:
        return None
    u = str(unit).strip()
    return u or None


def export_field_from_metadata(base_path: Union[str, Path],
                               data: np.ndarray,
                               info: Optional[Dict[str, Any]] = None,
                               title: Optional[str] = None,
                               context: str = "") -> Dict[str, str]:
    """:func:`export_field` with the scale derived from loader metadata.

    Convenience for the many call sites that hold a ``metadata.additional_info``
    dict rather than an explicit pixel size.
    """
    from src.utils.units import scale_from_metadata

    info = info or {}
    dx, dy, unit = scale_from_metadata(info, data.shape)
    value_unit = None
    units = info.get("units")
    if isinstance(units, dict):
        value_unit = units.get("dependent") or units.get("z")
    return export_field(base_path, data, dx=dx, dy=dy, unit=unit,
                        value_unit=value_unit, title=title, context=context)
