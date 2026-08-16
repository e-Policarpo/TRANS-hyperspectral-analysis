"""Gwyddion native ``.gwy`` export — all channels of a scan in one file.

``.gsf`` (see :mod:`src.utils.gsf_io`) is single-field by spec, so a scan with
Z and I in four trace directions becomes eight loose files. Gwyddion's own
``.gwy`` container holds every channel in one document, each with its own
title, lateral scale and value units — open one file and switch channels
inside Gwyddion, mirroring the app's own channel selector.

Written through the pure-Python ``gwyfile`` package, so no Gwyddion
installation is required and it works the same on macOS and Windows. The
dependency is optional: :func:`gwy_available` lets callers degrade to ``.gsf``
rather than fail an import.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


def gwy_available() -> bool:
    """Whether ``.gwy`` export is usable in this environment."""
    try:
        import gwyfile  # noqa: F401
    except Exception:
        return False
    return True


def write_gwy(path: Union[str, Path],
              channels: Mapping[str, np.ndarray],
              x_real: Optional[float] = None,
              y_real: Optional[float] = None,
              xy_units: str = "m",
              z_units: Optional[Mapping[str, str]] = None,
              default_z_unit: Optional[str] = None,
              x_offset: float = 0.0,
              y_offset: float = 0.0) -> str:
    """Write ``channels`` as a multi-channel Gwyddion file.

    ``channels`` maps channel name → 2D array; each becomes a titled Gwyddion
    data field. ``x_real`` / ``y_real`` are the **total** scan extent in
    ``xy_units`` (SI base units — metres for lengths), shared by all channels,
    which is correct because they are simultaneous views of one scan.

    ``z_units`` gives the value unit per channel (e.g. ``{"Z fwd/up": "m",
    "I fwd/up": "A"}``); ``default_z_unit`` covers any channel not listed.

    Raises ``ImportError`` when ``gwyfile`` is missing and ``ValueError`` when
    the channel set is empty or ragged.
    """
    try:
        from gwyfile.objects import GwyContainer, GwyDataField
    except ImportError as e:  # pragma: no cover - exercised via gwy_available
        raise ImportError(
            "Writing .gwy requires the 'gwyfile' package (pip install gwyfile)"
        ) from e

    if not channels:
        raise ValueError("write_gwy requires at least one channel")

    shapes = {np.asarray(a).shape for a in channels.values()}
    if len(shapes) != 1:
        raise ValueError(
            f"All channels must share one shape, got {sorted(shapes)}")
    shape = next(iter(shapes))
    if len(shape) != 2:
        raise ValueError(f".gwy channels must be 2D, got {shape}")

    z_units = dict(z_units or {})
    container = GwyContainer()
    for index, (name, array) in enumerate(channels.items()):
        # Gwyddion stores data as float64 fields; xreal/yreal default to the
        # pixel count when the scan geometry is unknown, which at least keeps
        # the aspect ratio honest rather than asserting a wrong size.
        field = GwyDataField(
            np.ascontiguousarray(array, dtype=np.float64),
            xreal=float(x_real) if x_real else float(shape[1]),
            yreal=float(y_real) if y_real else float(shape[0]),
            xoff=float(x_offset), yoff=float(y_offset),
            si_unit_xy=(xy_units or ""),
            si_unit_z=(z_units.get(name) or default_z_unit or ""),
        )
        container[f"/{index}/data"] = field
        title_key = f"/{index}/data/title"
        container[title_key] = str(name)
        # gwyfile types a one-character string as a Gwyddion ``char`` rather
        # than a string (objects.py: ``if len(value) == 1: return 'c'``), which
        # writes the title as an integer code and loses it in Gwyddion. Single
        # -pass Omicron scans have channels named exactly "Z" and "I", so force
        # the string typecode for every title.
        container.typecodes[title_key] = "s"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    container.tofile(str(path))
    return str(path)


def read_gwy_titles(path: Union[str, Path]) -> Dict[int, str]:
    """Channel index → title. Mainly for verifying our own writer."""
    from gwyfile.objects import GwyContainer

    container = GwyContainer.fromfile(str(path))
    out: Dict[int, str] = {}
    for key, value in container.items():
        if key.endswith("/data/title"):
            try:
                out[int(key.split("/")[1])] = str(value)
            except (IndexError, ValueError):
                continue
    return out
