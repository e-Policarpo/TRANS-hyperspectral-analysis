"""Human-readable metadata reports for imported measurement files.

Instrument files carry far more in their headers than a loader turns into
data: scan size, feedback gains, cantilever type, lock-in settings, laser
power, the operator's comment. That information is *in* the file and the
loaders now parse all of it (see :mod:`src.data_loaders.raw_header`), but a
nested dict buried in ``metadata.additional_info`` is not something you can
read.

This module turns those parsed headers into one plain-text report — every
imported file, one section each, sorted and aligned — so the acquisition
parameters of a whole session can be read, searched and pasted into a lab
notebook without opening the app.

**Metadata only.** Nothing here writes measurement values; bulk arrays and
DataFrames are summarised by shape and never dumped. Measurement data goes
through ``src.utils.field_export`` / the dataset CSVs, not through here.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Rendering limits. They exist so one pathological header (a 100k-point
# calibration table stored as a list) cannot turn the report into something
# as unreadable as the raw metadata it replaces.
MAX_VALUE_CHARS = 300      # a single scalar value, before ellipsis
MAX_INLINE_ITEMS = 12      # items of a scalar list rendered on one line
MAX_LIST_ITEMS = 40        # entries of a list-of-dicts rendered as blocks
MAX_DEPTH = 8              # nesting depth before a dict is summarised
KEY_COLUMN = 34            # widest dotted-leader column for key/value lines
MIN_KEY_COLUMN = 22        # narrowest, so short-keyed blocks still line up

_RULE = "=" * 78
_SUBRULE = "-" * 78


# ──────────────────────────────────────────────────────────────────────
# Value formatting
# ──────────────────────────────────────────────────────────────────────

def _is_scalar(value: Any) -> bool:
    """True for things that belong on a single ``key = value`` line."""
    if value is None or isinstance(value, (str, bytes, bool, int, float,
                                           datetime)):
        return True
    # numpy scalars quack like Python ones but are not instances of them
    return hasattr(value, "item") and getattr(value, "ndim", None) == 0


def describe(value: Any) -> str:
    """One-line rendering of a leaf value.

    Bulk payloads (arrays, frames) are described by shape and range rather
    than dumped — this is a metadata report, not a data export.
    """
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "yes" if value else "no"

    if isinstance(value, bytes):
        # Header blobs (RTF, raw comments) — say how big, show nothing.
        return f"<{len(value)} bytes>"

    if isinstance(value, float):
        # %g keeps 1e-09 readable and doesn't print 0.30000000000000004
        text = f"{value:.10g}"
    elif isinstance(value, datetime):
        text = value.strftime("%Y-%m-%d %H:%M:%S")
    elif hasattr(value, "item") and getattr(value, "ndim", None) == 0:
        return describe(value.item())
    else:
        text = str(value)

    text = " ".join(text.split())  # collapse embedded newlines/tabs
    if not text:
        # An empty value is a recorded blank, not a missing key — say so
        # rather than leaving a line that trails off into nothing.
        return "—"
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS].rstrip() + " …"
    return text


def _describe_array(value: Any) -> Optional[str]:
    """Summary line for numpy arrays / pandas objects, or None if not one."""
    shape = getattr(value, "shape", None)
    if shape is None:
        return None

    # pandas DataFrame — columns are metadata, the cells are not
    columns = getattr(value, "columns", None)
    if columns is not None:
        names = [str(c) for c in list(columns)[:MAX_INLINE_ITEMS]]
        more = len(list(columns)) - len(names)
        cols = ", ".join(names) + (f", … (+{more})" if more > 0 else "")
        return f"<table {shape[0]}×{shape[1]}: {cols}>"

    dtype = getattr(value, "dtype", "?")
    dims = "×".join(str(d) for d in shape) or "scalar"
    summary = f"<array {dtype} {dims}"
    try:
        import numpy as np

        arr = np.asarray(value)
        if arr.size and np.issubdtype(arr.dtype, np.number):
            finite = arr[np.isfinite(arr)]
            if finite.size:
                summary += f", {finite.min():.6g} … {finite.max():.6g}"
    except Exception:  # pragma: no cover - summary is best effort
        pass
    return summary + ">"


# ──────────────────────────────────────────────────────────────────────
# Block rendering
# ──────────────────────────────────────────────────────────────────────

def _leaf_text(value: Any) -> Optional[str]:
    """One-line rendering of ``value``, or None if it needs its own block.

    A short list of scalars counts as a leaf: ``BitsPerSample: 8`` reads
    better than a one-item block under a heading.
    """
    array_summary = _describe_array(value)
    if array_summary is not None:
        return array_summary
    if _is_scalar(value):
        return describe(value)
    if isinstance(value, (list, tuple)) and value and \
            all(_is_scalar(v) for v in value):
        shown = [describe(v) for v in value[:MAX_INLINE_ITEMS]]
        more = len(value) - len(shown)
        return ", ".join(shown) + (f", … (+{more} more)" if more > 0 else "")
    return None


def _leader(key: str, value: str, indent: int, width: int) -> str:
    """``key ........ value`` — dot leaders keep long blocks scannable."""
    pad = " " * indent
    key_text = f"{key} "
    fill = max(width - len(key_text), 1)
    return f"{pad}{key_text}{'.' * fill} {value}"


def _render_mapping(mapping: Mapping[Any, Any], indent: int,
                    depth: int) -> List[str]:
    """Render a dict: scalars as aligned lines, sub-dicts as nested blocks."""
    lines: List[str] = []
    items = list(mapping.items())

    # Align the leaders per block, so a block of short keys doesn't inherit
    # the column of an unrelated block with one very long key.
    leaf_keys = [str(k) for k, v in items if _leaf_text(v) is not None]
    longest = max((len(k) + 1 for k in leaf_keys), default=1)
    width = min(max(longest, MIN_KEY_COLUMN), KEY_COLUMN)

    for key, value in items:
        name = str(key)
        leaf = _leaf_text(value)
        if leaf is not None:
            lines.append(_leader(name, leaf, indent, width))
        else:
            body = _render_value(value, indent + 2, depth + 1)
            if body:
                lines.append(f"{' ' * indent}{name}:")
                lines.extend(body)
            else:
                lines.append(_leader(name, "—", indent, width))
    return lines


def _render_sequence(seq: Sequence[Any], indent: int,
                     depth: int) -> List[str]:
    """Render a list: inline when it is scalars, as blocks when it is not."""
    items = list(seq)
    if not items:
        return []

    if all(_is_scalar(v) for v in items):
        shown = [describe(v) for v in items[:MAX_INLINE_ITEMS]]
        more = len(items) - len(shown)
        text = ", ".join(shown) + (f", … (+{more} more)" if more > 0 else "")
        return [f"{' ' * indent}{text}"]

    lines: List[str] = []
    for i, item in enumerate(items[:MAX_LIST_ITEMS]):
        array_summary = _describe_array(item)
        if array_summary is not None:
            lines.append(f"{' ' * indent}[{i}] {array_summary}")
        elif _is_scalar(item):
            lines.append(f"{' ' * indent}[{i}] {describe(item)}")
        else:
            lines.append(f"{' ' * indent}[{i}]")
            lines.extend(_render_value(item, indent + 2, depth + 1))
    if len(items) > MAX_LIST_ITEMS:
        lines.append(f"{' ' * indent}… ({len(items) - MAX_LIST_ITEMS} more)")
    return lines


def _render_value(value: Any, indent: int, depth: int = 0) -> List[str]:
    """Render any metadata value as report lines."""
    if depth > MAX_DEPTH:
        return [f"{' ' * indent}… (nested deeper than {MAX_DEPTH} levels)"]

    array_summary = _describe_array(value)
    if array_summary is not None:
        return [f"{' ' * indent}{array_summary}"]
    if isinstance(value, Mapping):
        return _render_mapping(value, indent, depth)
    if isinstance(value, (list, tuple, set)):
        ordered = sorted(value, key=str) if isinstance(value, set) else value
        return _render_sequence(list(ordered), indent, depth)
    return [f"{' ' * indent}{describe(value)}"]


def render_block(mapping: Mapping[Any, Any], indent: int = 2) -> str:
    """Render one metadata mapping as an indented text block."""
    return "\n".join(_render_mapping(mapping, indent, 0))


# ──────────────────────────────────────────────────────────────────────
# Report assembly
# ──────────────────────────────────────────────────────────────────────

def _file_facts(path: Optional[Path]) -> Dict[str, Any]:
    """Size / mtime of the source file — context the header itself lacks."""
    facts: Dict[str, Any] = {}
    if path is None:
        return facts
    facts["Path"] = str(path)
    try:
        stat = path.stat()
    except OSError:
        return facts
    size = stat.st_size
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            facts["File size"] = f"{size:.0f} {unit}" if unit == "B" \
                else f"{size:.1f} {unit}"
            break
        size /= 1024.0
    facts["File modified"] = datetime.fromtimestamp(
        stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return facts


def _entry_name(h: Mapping[str, Any]) -> str:
    """Display name of one report entry: the source file's name."""
    source = h.get("source_file")
    return Path(source).name if source else "unknown file"


def format_entry(header: Mapping[str, Any], index: Optional[int] = None,
                 title: Optional[str] = None) -> str:
    """Format one file's parsed header as a report section.

    ``header`` is a raw-header dict as produced by
    :func:`src.data_loaders.raw_header.read_raw_header`: the reserved keys
    ``source_file``, ``format`` and ``loader`` describe the file, everything
    else is the instrument's own metadata and is rendered verbatim.
    """
    source = header.get("source_file")
    path = Path(source) if source else None
    name = title or _entry_name(header)
    heading = f"[{index}] {name}" if index is not None else name

    lines = [heading, _SUBRULE]

    facts: Dict[str, Any] = {}
    if header.get("format"):
        facts["Format"] = header["format"]
    if header.get("loader"):
        facts["Loader"] = header["loader"]
    facts.update(_file_facts(path))
    if facts:
        lines.extend(_render_mapping(facts, 2, 0))

    body = {k: v for k, v in header.items()
            if k not in ("source_file", "format", "loader")}
    if body:
        lines.append("")
        lines.extend(_render_mapping(body, 2, 0))
    else:
        lines.append("")
        lines.append("  (no header fields could be parsed from this file)")

    return "\n".join(lines)


def build_report(headers: Iterable[Mapping[str, Any]],
                 title: str = "T.R.A.N.S. — scan parameters",
                 note: Optional[str] = None) -> str:
    """Build the full multi-file report text.

    Entries are de-duplicated by source file (loaders attach the same header
    object to every channel they produce from one file) and sorted by file
    name so the report reads in a stable order.
    """
    unique: Dict[str, Mapping[str, Any]] = {}
    anonymous: List[Mapping[str, Any]] = []
    for header in headers:
        if not header:
            continue
        source = header.get("source_file")
        if source:
            unique.setdefault(str(source), header)
        else:
            anonymous.append(header)

    ordered = [unique[k] for k in sorted(unique, key=lambda p: Path(p).name)]
    ordered.extend(anonymous)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    head = [
        _RULE,
        title,
        f"Generated: {generated}",
        f"Files: {len(ordered)}",
    ]
    if note:
        head.append(note)
    head.extend([
        "Acquisition metadata only — measurement values live in the dataset",
        "exports alongside this file.",
        _RULE,
        "",
    ])

    if not ordered:
        return "\n".join(head) + "(no files with readable headers)\n"

    # A contents list: a full header runs to hundreds of lines per file, so
    # the report needs a way in that isn't scrolling.
    contents = ["Contents", _SUBRULE]
    labels = [f"[{i + 1}] {_entry_name(h)}" for i, h in enumerate(ordered)]
    width = min(max(len(label) + 1 for label in labels), KEY_COLUMN + 24)
    for label, header in zip(labels, ordered):
        contents.append(_leader(label, str(header.get("format") or "—"),
                                0, width))
    contents.append("")

    sections = [format_entry(h, index=i + 1) for i, h in enumerate(ordered)]
    return ("\n".join(head) + "\n".join(contents) + "\n"
            + "\n\n".join(sections) + "\n")


def write_report(path: Path, headers: Iterable[Mapping[str, Any]],
                 title: str = "T.R.A.N.S. — scan parameters",
                 note: Optional[str] = None) -> Optional[Path]:
    """Write the combined report to ``path``. Returns the path, or None.

    Never raises: a metadata report failing must not fail an import.
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = build_report(headers, title=title, note=note)
        path.write_text(text, encoding="utf-8")
        logger.info("Wrote scan-parameter report: %s", path)
        return path
    except Exception as e:  # pragma: no cover - reporting is best effort
        logger.warning("Could not write scan-parameter report to %s: %s",
                       path, e)
        return None
