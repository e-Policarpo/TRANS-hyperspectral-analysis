#!/usr/bin/env python3
"""
Dump a WITec ``.wip`` project file's complete tagged-tree to a text file.

Walks every tag without filtering: lists name, type code, size, and a
sample value for leaves (strings in full, ints / doubles / bools verbatim,
blobs as hex preview + size). Used to see what's in a file beyond what
TRANS currently surfaces.

Usage::

    python3 tools/dump_wip_tree.py path/to/file.wip [out.txt]

If ``out.txt`` is omitted, the dump is written next to the source file
with the suffix ``.tree.txt``.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# Make ``src.`` importable when the script is run from the repo root.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from src.data_loaders.witec_wip.wip_parser import (
    WIP_MAGIC,
    TYPE_BOOL,
    TYPE_CONTAINER,
    TYPE_FLOAT64,
    TYPE_INT32,
    TYPE_LIST,
    TYPE_STRING,
    TYPE_BLOB,
    iter_children,
    read_tag,
    read_bool,
    read_double,
    read_double_array,
    read_int,
    read_string,
)


TYPE_NAMES = {
    TYPE_CONTAINER: "container",
    TYPE_FLOAT64: "float64",
    TYPE_INT32: "int",
    TYPE_LIST: "list",
    TYPE_BLOB: "blob",
    TYPE_BOOL: "bool",
    TYPE_STRING: "string",
}


def _format_blob_preview(buf: bytes, tag) -> str:
    """Short hex preview of the first 16 bytes of a blob tag."""
    head = buf[tag.data_start:min(tag.data_start + 16, tag.data_end)]
    hex_str = head.hex(" ", 1)
    return f"{hex_str}{'…' if tag.size > 16 else ''}"


def _format_value(buf: bytes, tag) -> str:
    """Return a printable representation of a leaf tag's value."""
    try:
        if tag.type_code == TYPE_STRING:
            text = read_string(buf, tag)
            # Wrap long strings on the next line for readability.
            if len(text) > 100:
                return f"{text[:100]!r}… ({len(text)} chars)"
            return repr(text)
        if tag.type_code == TYPE_INT32:
            if tag.size in (1, 2, 4, 8):
                return str(read_int(buf, tag))
            return f"<int size={tag.size}>"
        if tag.type_code == TYPE_FLOAT64:
            if tag.size == 8:
                return f"{read_double(buf, tag):.6g}"
            if tag.size in (16, 24, 32, 40, 48):
                arr = read_double_array(buf, tag)
                return "[" + ", ".join(f"{v:.6g}" for v in arr) + "]"
            return f"<float64 size={tag.size}>"
        if tag.type_code == TYPE_BOOL:
            return "True" if read_bool(buf, tag) else "False"
        if tag.type_code == TYPE_BLOB:
            return f"<blob {tag.size}B  first16: {_format_blob_preview(buf, tag)}>"
        if tag.type_code == TYPE_LIST:
            return f"<list size={tag.size}>"
    except Exception as e:
        return f"<read error: {e}>"
    return ""


def dump_tree(path: Path, out_path: Path) -> None:
    buf = path.read_bytes()
    if not buf.startswith(WIP_MAGIC):
        raise SystemExit(
            f"{path}: not a WITec WIP file (magic mismatch: {buf[:8]!r})"
        )

    lines: list[str] = []
    lines.append(f"# WITec WIP tree dump")
    lines.append(f"# Source: {path}")
    lines.append(f"# Size:   {len(buf):,} bytes")
    lines.append(f"# Magic:  {buf[:8].decode('ascii', errors='replace')!r}")
    lines.append("")

    # Tally counters keyed on class name so the user can see what's in the
    # file without scrolling through the whole tree.
    class_counts: dict[str, int] = {}

    def recurse(start: int, end: int, depth: int) -> None:
        prefix = "  " * depth
        for tag in iter_children(buf, start, end):
            label = TYPE_NAMES.get(tag.type_code, f"type{tag.type_code}")
            value = _format_value(buf, tag) if tag.type_code != TYPE_CONTAINER else ""
            head = f"{prefix}{tag.name!r}  ({label}, size={tag.size}"
            head += f", off={tag.data_start:#x}-{tag.data_end:#x})"
            if value:
                head += f"  → {value}"
            lines.append(head)
            if tag.type_code == TYPE_CONTAINER and tag.size > 0:
                # Track per-DataClassName entries when we see the "Data"
                # block at the top — the strings give us the class tally.
                if tag.name.startswith("DataClassName "):
                    pass  # value captured below via class_counts
                recurse(tag.data_start, tag.data_end, depth + 1)

    # First pass: tally class names to print as a summary at the top.
    root = read_tag(buf, 8)
    data_blocks = [c for c in iter_children(buf, root.data_start, root.data_end)
                   if c.name == "Data"]
    for db in data_blocks:
        for c in iter_children(buf, db.data_start, db.data_end):
            if c.name.startswith("DataClassName "):
                cls = read_string(buf, c)
                class_counts[cls] = class_counts.get(cls, 0) + 1

    if class_counts:
        lines.append("# DataClassName tally:")
        for cls, n in sorted(class_counts.items(), key=lambda x: -x[1]):
            lines.append(f"#   {n:4d}× {cls}")
        lines.append("")

    # Root tag itself.
    lines.append(
        f"{root.name!r}  (container, size={root.size}, "
        f"off={root.data_start:#x}-{root.data_end:#x})"
    )
    recurse(root.data_start, root.data_end, depth=1)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(lines):,} lines)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("wip_path", type=Path, help="Path to the .wip file")
    ap.add_argument("out_path", type=Path, nargs="?",
                    help="Output .txt (defaults to <wip>.tree.txt)")
    args = ap.parse_args(argv)
    out = args.out_path or args.wip_path.with_suffix(
        args.wip_path.suffix + ".tree.txt"
    )
    dump_tree(args.wip_path, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
