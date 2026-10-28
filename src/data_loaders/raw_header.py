"""Full instrument-header parsing, one function per file format.

Every loader in this package reads the *measurement* it needs and, on the
way, picks a handful of fields out of the file header — grid size, a
timestamp, a scan range. The rest of the header is read past and lost, even
though it holds what an acquisition actually has to be reported with:
feedback gains, cantilever and scan-head identity, lock-in settings,
bias and setpoint, integration time, the operator's comment.

This module parses the **whole** header of each supported format into a
plain nested dict of built-in types, with no measurement data attached, and
:func:`read_raw_header` dispatches on the file. Loaders attach the result to
``metadata.additional_info['raw_header']``; :mod:`src.utils.metadata_report`
renders a set of them as one readable text report.

Design rules:

* **Nothing here raises.** A header that cannot be parsed returns ``None``
  (or a partial dict carrying ``parse_error``) — a metadata read must never
  be able to fail an import.
* **Verbatim, not interpreted.** Values are kept as the instrument wrote
  them (``"3µm"``, ``"922m°"``). Physical interpretation stays in the
  loaders, which is where the unit conventions already live.
* **Metadata only.** No bulk arrays are copied into the returned dict.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Spectroscopy/scan extensions MATRIX writes; they all share one header.
_MTRX_DATA_RE = re.compile(r"\.[A-Za-z0-9()_]+_mtrx$")


# ──────────────────────────────────────────────────────────────────────
# Dispatch
# ──────────────────────────────────────────────────────────────────────

def read_raw_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """Parse the complete header of ``filepath``, or None if unsupported.

    Reads metadata only — for every format except WITec ``.wip`` (whose
    container has to be walked to reach its metadata) this touches a small
    prefix of the file rather than loading the measurement.
    """
    try:
        filepath = Path(filepath)
        if not filepath.is_file():
            return None
        name = filepath.name
        suffix = filepath.suffix.lower()

        if suffix == ".nid":
            return parse_nid_header(filepath)
        # Omicron FLAT files are named ``*.Z_flat`` / ``*.I_flat``, so the
        # suffix carries the channel — match on the trailing token instead.
        if name.lower().endswith("_flat"):
            return parse_flat_header(filepath)
        if suffix == ".wip":
            return parse_wip_header(filepath)
        if suffix == ".ps-ppt":
            return parse_park_ppt_header(filepath)
        if suffix in (".tiff", ".tif"):
            return parse_tiff_header(filepath)
        if suffix == ".mtrx" or _MTRX_DATA_RE.search(name):
            return parse_mtrx_header(filepath)
        if suffix in (".txt", ".dat"):
            return parse_neaspec_header(filepath)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not read header of %s: %s", filepath, exc)
    return None


def _base(filepath: Path, fmt: str) -> Dict[str, Any]:
    """The reserved keys every header dict starts with."""
    return {"source_file": str(filepath), "format": fmt}


# ──────────────────────────────────────────────────────────────────────
# Nanosurf .nid — INI text header terminated by the ``#!`` data marker
# ──────────────────────────────────────────────────────────────────────

# The header is ASCII/Latin-1 INI text at the head of the file; ``#!``
# marks the start of the binary channel data. 512 KB is far beyond the
# largest header seen (~32 KB for a 512×512 KPFM scan with 41 sections)
# and bounds the read for a file that lacks the marker entirely.
_NID_MAX_HEADER = 512 * 1024
_NID_DATA_MARKER = b"#!"


def read_nid_header_text(filepath: Path) -> Optional[str]:
    """The raw INI text of a ``.nid`` header, without the binary payload."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(_NID_MAX_HEADER)
    except OSError as exc:
        logger.debug("Could not read %s: %s", filepath, exc)
        return None
    cut = chunk.find(_NID_DATA_MARKER)
    if cut > 0:
        chunk = chunk[:cut]
    # Nanosurf's own encoding varies by software version: recent releases
    # write UTF-8, older ones ISO-8859-1. Decoding UTF-8 text as Latin-1
    # turns every "µm" into "Âµm", so try the stricter one first and fall
    # back only when the bytes are genuinely not UTF-8.
    try:
        return chunk.decode("utf-8")
    except UnicodeDecodeError:
        return chunk.decode("ISO-8859-1", errors="replace")


def parse_ini_text(text: str) -> Dict[str, Dict[str, str]]:
    """Parse ``[Section]`` / ``key=value`` text into a nested dict.

    Written rather than handed to :mod:`configparser` because instrument
    INI dialects break it: duplicate keys (kept here as ``key (2)``),
    section names containing backslashes, values containing ``=``, and
    lines like ``-- Scan --=--------`` that are separators, not settings.
    """
    sections: Dict[str, Dict[str, str]] = {}
    current = "(no section)"
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            sections.setdefault(current, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        block = sections.setdefault(current, {})
        if key in block:
            n = 2
            while f"{key} ({n})" in block:
                n += 1
            key = f"{key} ({n})"
        block[key] = value
    return {name: body for name, body in sections.items() if body}


# Nanosurf stores parameter-section values in a typed notation:
# ``D[3]*[N/m]`` (double + unit), ``L[65000]*[]`` (long), ``B[0]*[]``
# (bool), ``V[5e-06,5e-06,0]*[m,m,m]`` (vector, one unit per component),
# ``S[...]*[]`` (string). Left as-is it is the main reason these sections
# are unreadable, so it is decoded to "3 N/m" / "5e-06 m, 5e-06 m, 0 m".
_NID_TYPED_RE = re.compile(r"^([DLBVS])\[(.*)\]\*\[(.*)\]$", re.DOTALL)


def decode_nid_value(raw: str) -> str:
    """Decode Nanosurf's ``T[value]*[unit]`` notation to readable text.

    Values that do not use the notation (the human-facing ``DataSet-Info``
    section writes ``3µm`` directly) are returned untouched.
    """
    match = _NID_TYPED_RE.match(raw)
    if not match:
        return raw
    kind, value, unit = match.groups()

    if kind == "B":
        return {"0": "no", "1": "yes"}.get(value.strip(), value)
    if kind == "S":
        return value
    if kind == "V":
        parts = [p.strip() for p in value.split(",")]
        units = [u.strip() for u in unit.split(",")] if unit else []
        pieces = [f"{p} {units[i]}".strip() if i < len(units) else p
                  for i, p in enumerate(parts)]
        return ", ".join(pieces)
    return f"{value} {unit}".strip() if unit else value


def parse_nid_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """Every section of a Nanosurf ``.nid`` header.

    Typical content: ``DataSet-Info`` (scan size, direction, time/line,
    points/lines, slopes, rotation, position, setpoint, PID gains, tip
    voltage, vibration frequency and amplitude, advanced-mode/KPFM block,
    cantilever and scan-head identity), ``DataSet\\Calibration``,
    ``DataSet\\Parameters`` (imaging, spectroscopy, signal I/O, feedback)
    and the per-channel ``DataSet-n:m`` blocks.
    """
    text = read_nid_header_text(filepath)
    if text is None:
        return None
    header = _base(filepath, "Nanosurf NID")
    sections = parse_ini_text(text)
    if not sections:
        header["parse_error"] = "no INI sections found in header"
        return header
    for name, body in sections.items():
        header[name] = {k: decode_nid_value(v) for k, v in body.items()}
    logger.debug("NID header %s: %d sections", filepath.name, len(sections))
    return header


# ──────────────────────────────────────────────────────────────────────
# NeaSpec SNOM — ``#``-commented text header
# ──────────────────────────────────────────────────────────────────────

_NEASPEC_MAX_HEADER_LINES = 200


def parse_neaspec_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """Every ``# Key: value`` line of a NeaSpec/attocube export header.

    The loaders read the handful of fields they need (scan area, pixel
    area, demodulation mode); this keeps all of them — project, description,
    date, tip/tapping amplitude, wavenumber scaling, averaging, interferometer
    settings — plus the column header line and any comment lines that carry
    no key at all.
    """
    fields: Dict[str, str] = {}
    notes: List[str] = []
    columns: Optional[str] = None
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= _NEASPEC_MAX_HEADER_LINES:
                    break
                stripped = line.strip()
                if not stripped.startswith("#"):
                    # First non-comment line: the column header of the data.
                    if stripped and columns is None:
                        columns = stripped
                    break
                body = stripped.lstrip("#").strip()
                if not body:
                    continue
                if ":" in body:
                    key, value = body.split(":", 1)
                    key = key.strip()
                    value = " ".join(value.split())
                    if key:
                        if key in fields:
                            n = 2
                            while f"{key} ({n})" in fields:
                                n += 1
                            key = f"{key} ({n})"
                        fields[key] = value
                        continue
                notes.append(body)
    except OSError as exc:
        logger.debug("Could not read %s: %s", filepath, exc)
        return None

    if not fields:
        # A plain .txt/.dat with no ``# Key: value`` header is not an
        # instrument export — report nothing rather than guess.
        return None

    header = _base(filepath, "NeaSpec SNOM (text export)")
    if fields:
        header["Header fields"] = fields
    if columns:
        header["Data columns"] = [c.strip() for c in columns.split("\t")
                                  if c.strip()]
    if notes:
        header["Header notes"] = notes
    return header


# ──────────────────────────────────────────────────────────────────────
# Omicron FLAT — binary header, parsed by the loader already
# ──────────────────────────────────────────────────────────────────────

def parse_flat_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """The full FLAT0100 header: axes, channel, transfer function, comment."""
    try:
        from .omicron_flat_loader import OmicronFlatLoader

        content = Path(filepath).read_bytes()
        parsed = OmicronFlatLoader()._parse_flat_header(content)
    except Exception as exc:
        logger.debug("Could not parse FLAT header of %s: %s", filepath, exc)
        return None
    if not parsed:
        return None

    header = _base(filepath, "Omicron FLAT")
    axes = parsed.get("axes") or []
    if axes:
        header["Axes"] = axes
    header["Channel"] = {
        "Name": parsed.get("channel"),
        "Unit": (parsed.get("transfer_function") or {}).get("unit"),
    }
    xfer = parsed.get("transfer_function") or {}
    if xfer:
        header["Transfer function"] = {
            "Name": xfer.get("name"),
            "Unit": xfer.get("unit"),
            **(xfer.get("params") or {}),
        }
    if parsed.get("metadata"):
        header["Creation info"] = parsed["metadata"]
    if parsed.get("timestamp"):
        header["Acquired"] = parsed["timestamp"]
    header["Data points"] = parsed.get("data_count")
    return header


# ──────────────────────────────────────────────────────────────────────
# Omicron MATRIX — the ``_0001.mtrx`` experiment parameter stream
# ──────────────────────────────────────────────────────────────────────

def _mtrx_header_path(filepath: Path) -> Optional[Path]:
    """The ``*_0001.mtrx`` parameter file governing ``filepath``.

    Resolution is delegated to the loader, so a data file whose own header
    is missing borrows one exactly as the import does (same session first,
    then the folder, then a sibling folder).
    """
    filepath = Path(filepath)
    if filepath.name.endswith("_0001.mtrx"):
        return filepath
    try:
        from .omicron_mtrx_loader import OmicronMatrixSTSLoader

        loader = OmicronMatrixSTSLoader()
        base = loader._session_base(filepath)
        header, _is_own = loader._resolve_header(base, filepath.parent)
        return header
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not resolve MATRIX header for %s: %s",
                     filepath, exc)
        return None


def parse_mtrx_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """The complete MATRIX experiment parameter tree for ``filepath``.

    MATRIX keeps every instrument setting — scanner ranges, gap-voltage and
    setpoint, regulator gains, lock-in configuration, preamplifier gain,
    spectroscopy sweep definition — in the session's ``_0001.mtrx`` stream,
    of which the loader reads only the STS location and the lock-in entries.
    Scanning the stream to its end leaves the full configuration in
    ``param``, and that is what is returned here, grouped by the
    ``<Device>.<Property>`` prefix MATRIX names parameters with.
    """
    header_path = _mtrx_header_path(filepath)
    if header_path is None:
        return None
    try:
        from .omicron_mtrx_loader import OmicronMatrixSTSLoader

        loader = OmicronMatrixSTSLoader()
        template = loader._borrowed_template(header_path)
    except Exception as exc:
        logger.debug("Could not parse MATRIX header %s: %s", header_path, exc)
        return None
    if not template:
        return None

    param = template.get("param") or {}
    header = _base(filepath, "Omicron MATRIX")
    header["Parameter file"] = str(header_path)
    if header_path.name != f"{loader._session_base(Path(filepath))}_0001.mtrx":
        header["Parameter file note"] = (
            "borrowed from another session — instrument settings apply, "
            "session-specific positions do not"
        )

    # MATRIX names parameters "<Device>.<Property>"; grouping by device turns
    # a flat 500-entry dict into the instrument panels it came from.
    grouped: Dict[str, Dict[str, Any]] = {}
    ungrouped: Dict[str, Any] = {}
    for key, value in param.items():
        if key == "BREF":  # parser bookkeeping, not an instrument setting
            continue
        text_key = str(key)
        if "." in text_key:
            device, prop = text_key.split(".", 1)
            grouped.setdefault(device, {})[prop] = value
        else:
            ungrouped[text_key] = value
    if grouped:
        header["Experiment parameters"] = dict(sorted(grouped.items()))
    if ungrouped:
        header["Other parameters"] = ungrouped

    channels = template.get("channel_id") or {}
    if channels:
        header["Channels"] = {str(k): v for k, v in channels.items()}
    return header


# ──────────────────────────────────────────────────────────────────────
# Park Systems — .ps-ppt event stream and .tiff tags
# ──────────────────────────────────────────────────────────────────────

def parse_park_ppt_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """Park PinPoint ``.ps-ppt`` header: the scan and parameter events.

    ``scan.start`` and ``ppt.param`` are JSON records holding the entire
    acquisition configuration (geometry, rate, setpoint, cantilever
    calibration, PinPoint timing). The loader consumes four of their fields;
    both records are returned here whole.
    """
    try:
        from .park_afm_loader import PsPptParser

        parser = PsPptParser(Path(filepath))
        parser.parse_metadata()
    except Exception as exc:
        logger.debug("Could not parse Park PPT header %s: %s", filepath, exc)
        return None

    header = _base(filepath, "Park Systems PinPoint (.ps-ppt)")
    scan_info = getattr(parser, "scan_info", None) or {}
    param_info = getattr(parser, "param_info", None) or {}
    if scan_info:
        header["Scan"] = scan_info
    if param_info:
        header["Parameters"] = param_info
    channels = getattr(parser, "channels", None)
    if channels:
        header["Channels"] = channels
    direction = getattr(parser, "is_forward", None)
    if direction is not None:
        header["Trace direction"] = "forward" if direction else "backward"
    if not scan_info and not param_info:
        return None
    return header


# The two custom tags carry the float32 image and a binary parameter blob.
# Both are decoded separately — dumping their raw bytes into a text report
# would be noise, so they are excluded from the generic tag listing.
_PARK_TAG_DATA = 50434
_PARK_TAG_META = 50435
# 320 is the 768-entry display palette: a rendering choice, not an
# acquisition parameter, and it would dominate the report.
_TIFF_BULK_TAGS = {273, 279, 288, 289, 320, 324, 325, _PARK_TAG_DATA,
                   _PARK_TAG_META}


def parse_tiff_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """All TIFF tags of a scan image, plus Park's private parameter block.

    Park Systems writes its channel name, scan mode and physical scan size
    into private tag 50435; everything else an acquisition records lives in
    the standard tags (software version, acquisition date, resolution).
    Returns None for a TIFF that carries no usable metadata at all.
    """
    try:
        from PIL import Image
        from PIL.TiffTags import TAGS_V2
    except Exception:
        return None

    try:
        with Image.open(str(filepath)) as img:
            tags = dict(getattr(img, "tag_v2", {}) or {})
            size = img.size
    except Exception as exc:
        logger.debug("Could not read TIFF tags of %s: %s", filepath, exc)
        return None

    is_park = _PARK_TAG_META in tags or _PARK_TAG_DATA in tags
    header = _base(filepath,
                   "Park Systems TIFF" if is_park else "TIFF image")
    header["Pixels"] = f"{size[0]} × {size[1]}"

    listed: Dict[str, Any] = {}
    for code, value in sorted(tags.items()):
        if code in _TIFF_BULK_TAGS:
            continue
        name = TAGS_V2.get(code).name if TAGS_V2.get(code) else f"Tag {code}"
        if isinstance(value, bytes):
            value = f"<{len(value)} bytes>"
        listed[f"{name} ({code})"] = value
    if listed:
        header["TIFF tags"] = listed

    if is_park:
        header["Park scan parameters"] = _park_tiff_block(
            tags.get(_PARK_TAG_META), filepath)
    return header if listed or is_park else None


def _park_tiff_block(blob: Any, filepath: Path) -> Dict[str, Any]:
    """Decode the fields of Park's private tag-50435 parameter blob.

    Only the offsets the loader has verified against real files are read;
    the rest of the blob is reported by size rather than guessed at, so a
    wrong number never reaches the report as if it were a measurement.
    """
    out: Dict[str, Any] = {}
    if not isinstance(blob, bytes):
        return out
    from struct import unpack_from

    out["Block size"] = f"{len(blob)} bytes"
    try:
        if len(blob) >= 0x44:
            out["Channel"] = blob[0x04:0x44].decode(
                "utf-16-le", errors="replace").rstrip("\x00").strip()
        if len(blob) >= 0x64:
            out["Scan mode"] = blob[0x44:0x64].decode(
                "utf-16-le", errors="replace").rstrip("\x00").strip()
        if len(blob) >= 0x9C:
            out["Scan width (µm)"] = unpack_from("<d", blob, 0x8C)[0]
            out["Scan height (µm)"] = unpack_from("<d", blob, 0x94)[0]
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Park tag 50435 decode failed for %s: %s", filepath, exc)
    return out


# ──────────────────────────────────────────────────────────────────────
# WITec .wip — project-level info plus every per-acquisition info text
# ──────────────────────────────────────────────────────────────────────

_WIP_FIELD_RE = re.compile(
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 /_\-\.]*?(?:\[[^\]]*\])?)\s*:\s*"
    r"([^\n\r]*?)(?=\s{2,}[A-Za-zÀ-ÿ][^:\n\r]*?:|$)",
    re.MULTILINE,
)

# A value that is itself ``Key: value`` — WITec's RTF puts a section
# heading and its first field on one line ("General: System ID: 100-…"),
# so the outer key is a heading and the inner one is the real field name.
_WIP_GLUED_RE = re.compile(
    r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 /_\-\.]{0,40}?(?:\[[^\]]*\])?)\s*:\s*(\S.*)$"
)


def parse_info_text_fields(text: str) -> Dict[str, str]:
    """Every ``Key: value`` pair in a WITec info text.

    The loader looks up a fixed list of seventeen fields it needs; a WITec
    info text carries far more (laser power, grating, spectral centre,
    detector temperature, binning, stitching geometry, camera exposure).
    This reads them all, generically.

    Two quirks of WITec's RTF are handled: a value runs to the next
    ``Key:`` pair rather than to the end of the line, and a section heading
    glued to its first field (``"General: System ID: 100-1400-1232"``) is
    unwrapped to the inner, meaningful field name.
    """
    out: Dict[str, str] = {}
    if not text:
        return out

    def _store(key: str, value: str) -> None:
        key = " ".join(key.split())
        value = " ".join(value.split())
        if not key or not value or len(key) > 60:
            return
        if key in out:
            if out[key] == value:
                return
            n = 2
            while f"{key} ({n})" in out:
                n += 1
            key = f"{key} ({n})"
        out[key] = value

    for raw_key, raw_value in _WIP_FIELD_RE.findall(text):
        key, value = raw_key, raw_value
        # Unwrap heading-glued-to-field, as deep as it goes.
        for _ in range(4):
            glued = _WIP_GLUED_RE.match(value.strip())
            if not glued:
                break
            key, value = glued.group(1), glued.group(2)
        _store(key, value)
    return out


def parse_wip_header(filepath: Path) -> Optional[Dict[str, Any]]:
    """WITec project metadata, parsing the ``.wip`` from disk.

    The loader already holds a parsed project when it imports one — it calls
    :func:`wip_header_from_project` directly rather than re-reading the file.
    """
    try:
        from .witec_wip.wip_parser import parse_wip

        project = parse_wip(Path(filepath))
    except Exception as exc:
        logger.debug("Could not parse WIP header %s: %s", filepath, exc)
        return None
    return wip_header_from_project(project, Path(filepath))


def wip_header_from_project(project: Any, filepath: Path
                            ) -> Optional[Dict[str, Any]]:
    """WITec project metadata: system info plus each acquisition's info text.

    A ``.wip`` is a session container, so its "header" is really one block
    per acquisition. Each data entry has a sibling info text listing the
    conditions it was recorded under — grating, spectral range, CCD
    temperature and readout, integration time, accumulations, objective,
    stage position — and all of them are returned, keyed by the entry
    caption.
    """
    header = _base(filepath, "WITec Project (.wip)")
    header["Project"] = {
        "WIP version": project.version,
        "Data entries": len(project.entries),
        "Graphs": len(project.graphs),
        "Bitmaps": len(project.bitmaps),
        "Excitation wavelength (nm)": project.excitation_wavelength_nm,
    }
    sysinfo = project.system_info
    system = {
        "Application versions": list(sysinfo.application_versions),
        "License IDs": sysinfo.license_ids,
        "Service ID": sysinfo.service_id,
        "System ID": sysinfo.system_id,
    }
    if any(system.values()):
        header["System information"] = system

    captions = {int(e.id): (e.caption or "").strip()
                for e in project.entries if e.id is not None}
    acquisitions: Dict[str, Dict[str, str]] = {}
    for txt in project.texts:
        fields = parse_info_text_fields(txt.text or "")
        if not fields:
            continue
        data_id = int(txt.entry.id) - 1
        label = captions.get(data_id) or (txt.entry.caption or "").strip() \
            or f"Entry {data_id}"
        if label in acquisitions:
            n = 2
            while f"{label} ({n})" in acquisitions:
                n += 1
            label = f"{label} ({n})"
        acquisitions[label] = fields
    if acquisitions:
        header["Acquisitions"] = acquisitions

    if project.spectral_cursors:
        header["Spectral cursors"] = [
            {"label": (c.entry.caption or "Cursor").strip(),
             "unit": c.standard_unit,
             "positions": list(c.positions)}
            for c in project.spectral_cursors
        ]
    return header


# ──────────────────────────────────────────────────────────────────────
# Attachment helper used by the loaders
# ──────────────────────────────────────────────────────────────────────

def attach_raw_header(targets: Any, filepath: Path,
                      header: Optional[Dict[str, Any]] = None
                      ) -> Optional[Dict[str, Any]]:
    """Attach ``filepath``'s parsed header to one or many loaded objects.

    ``targets`` may be anything carrying ``metadata.additional_info`` (a
    :class:`SpectralData`, :class:`ImageData`, …), a plain
    ``additional_info`` dict, or an iterable of either. The **same** header
    dict object is shared by every target, so attaching it to a hundred
    channels of one file costs one copy, and the report can de-duplicate on
    the source path.

    Returns the header, or None when the format carries none.
    """
    if header is None:
        header = read_raw_header(Path(filepath))
    if not header:
        return None

    def _one(target: Any) -> None:
        info = target
        if not isinstance(info, dict):
            meta = getattr(target, "metadata", None)
            info = getattr(meta, "additional_info", None)
        if not isinstance(info, dict):
            return
        info.setdefault("raw_header", header)
        info.setdefault("source_file", str(filepath))

    if isinstance(targets, dict) or not hasattr(targets, "__iter__"):
        _one(targets)
    else:
        for target in targets:
            _one(target)
    return header
