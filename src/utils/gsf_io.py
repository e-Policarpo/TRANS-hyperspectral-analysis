"""Gwyddion Simple Field (``.gsf``) export — the format Gwyddion actually
reads dimensions from.

**Why this exists.** TIFF resolution tags (``XResolution`` / ``YResolution``
plus an ImageJ ``unit=`` line) calibrate an image for Fiji/ImageJ, but
Gwyddion ignores them: for generic image formats its pixmap importer asks the
user to type the physical dimensions in by hand, and the values it pre-fills
are "simply the last values used", not anything read from the file. So a
TIFF — however carefully tagged — always lands in Gwyddion as bare pixels.

GSF is Gwyddion's own documented interchange format and carries ``XReal`` /
``YReal`` / ``XYUnits`` / ``ZUnits`` explicitly, so a file written here opens
with the correct scan size and value units with no manual entry.

Format (from the Gwyddion user guide):

* magic line ``Gwyddion Simple Field 1.0`` + ``\\n``
* text header of ``key = value`` lines; ``XRes``/``YRes`` mandatory,
  ``XReal``/``YReal``/``XOffset``/``YOffset``/``XYUnits``/``ZUnits``/``Title``
  optional. Lengths are in the *base* unit, i.e. metres when ``XYUnits = m``.
* 1–4 NUL bytes so the header length is a multiple of 4 (a header already
  aligned still gets a full 4)
* ``XRes*YRes`` IEEE float32, little-endian, row-major, **top row first**

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

MAGIC = b"Gwyddion Simple Field 1.0\n"


def write_gsf(path: Union[str, Path],
              data: np.ndarray,
              x_real: Optional[float] = None,
              y_real: Optional[float] = None,
              xy_units: str = "m",
              z_units: Optional[str] = None,
              title: Optional[str] = None,
              x_offset: float = 0.0,
              y_offset: float = 0.0,
              extra: Optional[Dict[str, Any]] = None) -> str:
    """Write ``data`` as a Gwyddion Simple Field.

    ``x_real`` / ``y_real`` are the **total** scan extent (not per-pixel) in
    ``xy_units``, which should be an SI base unit — ``m`` for lengths. Omit
    them only when the geometry genuinely isn't known; Gwyddion then falls
    back to 1.0 and the file is no better than a bitmap.

    Non-finite values are written as-is (Gwyddion handles NaN as masked).
    Returns the path written, as a string.
    """
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise ValueError(f"GSF requires a 2D field, got shape {arr.shape}")
    rows, cols = int(arr.shape[0]), int(arr.shape[1])
    if rows < 1 or cols < 1:
        raise ValueError(f"GSF requires a non-empty field, got {arr.shape}")

    lines = [f"XRes = {cols}", f"YRes = {rows}"]
    if x_real and x_real > 0:
        lines.append(f"XReal = {float(x_real):.17g}")
    if y_real and y_real > 0:
        lines.append(f"YReal = {float(y_real):.17g}")
    if x_offset:
        lines.append(f"XOffset = {float(x_offset):.17g}")
    if y_offset:
        lines.append(f"YOffset = {float(y_offset):.17g}")
    if xy_units:
        lines.append(f"XYUnits = {xy_units}")
    if z_units:
        lines.append(f"ZUnits = {z_units}")
    if title:
        # Newlines would break the line-oriented header.
        lines.append(f"Title = {str(title).replace(chr(10), ' ').strip()}")
    for key, value in (extra or {}).items():
        lines.append(f"{key} = {value}")

    header = MAGIC + ("\n".join(lines) + "\n").encode("utf-8")
    # 1–4 NULs so the total header length is a multiple of 4. An already
    # aligned header still gets a full 4 — the spec has no zero-padding case.
    pad = 4 - (len(header) % 4)
    header += b"\0" * pad

    payload = np.ascontiguousarray(arr, dtype="<f4").tobytes()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(payload)
    return str(path)


def read_gsf(path: Union[str, Path]) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Read a ``.gsf`` back. Mainly for verifying our own writer.

    Returns ``(data, header)`` where ``header`` has ``XRes``/``YRes`` as ints,
    the real/offset fields as floats, and everything else as strings.
    """
    raw = Path(path).read_bytes()
    if not raw.startswith(MAGIC):
        raise ValueError(f"{path} is not a Gwyddion Simple Field")

    # The header ends at the first NUL after the magic line.
    nul = raw.index(b"\0", len(MAGIC))
    text = raw[len(MAGIC):nul].decode("utf-8")
    header: Dict[str, Any] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        header[key.strip()] = value.strip()

    for key in ("XRes", "YRes"):
        header[key] = int(header[key])
    for key in ("XReal", "YReal", "XOffset", "YOffset"):
        if key in header:
            header[key] = float(header[key])

    # 1–4 NULs pad the header to a 4-byte boundary; ``4 - (nul % 4)`` yields 4
    # when the header is already aligned, which is exactly the spec's rule.
    start = nul + (4 - (nul % 4))
    if raw[nul:start].strip(b"\0"):
        raise ValueError("Malformed GSF padding")

    rows, cols = header["YRes"], header["XRes"]
    expected = 4 * rows * cols
    payload = raw[start:start + expected]
    if len(payload) != expected:
        raise ValueError(
            f"GSF payload is {len(payload)} bytes, expected {expected}")
    data = np.frombuffer(payload, dtype="<f4").reshape(rows, cols)
    return data, header
