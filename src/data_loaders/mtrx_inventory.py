"""Omicron MATRIX session inventory — the ``_0001.mtrx`` stream as a timeline.

A MATRIX session header is not a static header. It is an append-only event
log that the instrument writes while it runs: one full parameter snapshot
when the experiment starts, then a timestamped record every time a setting
changes (``PMOD``), every time a data file is written (``BREF``) and every
time something is annotated (``MARK``: STS location, sample name, channel
recording on/off). The loader reads only the end state of that log plus the
entry of each file it needs, and :func:`~.raw_header.parse_mtrx_header`
reports only the end state, so *when* a setpoint was changed and which
measurements were taken under which settings is lost.

This module replays the whole log and reconciles it with the files on disk.
The result is one structured account per session:

* the session (MATRIX version, experiment, sample, data-set name, start/end);
* the initial parameter snapshot, and every parameter that changed, with its
  full history;
* every **measurement** — one ``(kind, run, scan)`` acquisition, i.e. the
  set of channel files MATRIX wrote together — with its time, STS location,
  the parameter state it was taken under (``parameter_epoch``) and the
  settings changed since the previous measurement of the same kind;
* **flags** for anything missing or damaged: files the header references but
  the disk lacks, files on disk the header never referenced, aborted
  (incomplete) and truncated files, a channel missing from one scan of a
  run, gaps in the scan and run counters, gaps in the header chain, and a
  log that stops before its end.

:func:`write_inventory` puts it on disk as JSON (complete, for programs) and
TXT (readable). ``python -m src.data_loaders.mtrx_inventory <session file or
folder>`` does the same from the command line.

Like :mod:`.raw_header`, nothing here raises into an import: a stream that
cannot be read yields an inventory with a flag, not an exception. No
measurement values are read, only the first 72 bytes of each data file.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
License: GPL
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import struct
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAGIC = b"ONTMATRX0101"
SCHEMA_VERSION = 1

# Block tags are stored byte-reversed ("DOMP" is PMOD). These carry no
# 8-byte timestamp between the length and the body (same set as
# access2theMatrix's _scan_raw_param).
_UNSTAMPED = {b"REFX", b"NACS", b"TCID", b"SCHC", b"TSNI", b"SXNC", b"LNEG"}

# A stamp outside this window is not a time (INCI uses the slot for
# something else).
_STAMP_MIN = 631152000      # 1990-01-01
_STAMP_MAX = 4102444800     # 2100-01-01

_DATA_FILE_RE = re.compile(r"^(?P<base>.*)--(?P<run>\d+)_(?P<scan>\d+)"
                           r"\.(?P<channel>.+)_mtrx$")
_MARK_RE = re.compile(r"^MTRX\$(?P<key>[A-Z_]+)-(?P<value>.*)$", re.S)
_STS_RE = re.compile(r"^(-?\d+),(-?\d+);([^,;]+),([^%]+?)(%%.*%%)?$")

# Bytes of a data file needed to judge its integrity: magic (12), the TLKB
# tag + length + stamp (16), padding (4), the CSED block up to its counts.
_DATA_HEAD = 72

# More measurements than this and the JSON is written without indentation:
# a 200k-file session is tens of MB either way, and indentation doubles it.
_INDENT_LIMIT = 20000


# ──────────────────────────────────────────────────────────────────────
# Low-level stream decoding
# ──────────────────────────────────────────────────────────────────────

def _stamp(secs: int) -> Optional[str]:
    """Local ISO time for a MATRIX stamp, or None if it is not a time.

    MATRIX stamps are POSIX seconds rendered in local time (as
    access2theMatrix does), which matches the session names.
    """
    if not _STAMP_MIN < secs < _STAMP_MAX:
        return None
    return datetime.fromtimestamp(secs).isoformat(timespec="seconds")


def _string(buf: bytes, o: int) -> Tuple[int, str]:
    """Length-prefixed UTF-16LE string at ``o``; returns (end, text)."""
    n = struct.unpack_from("<L", buf, o)[0]
    o += 4
    end = o + 2 * n
    if end > len(buf):
        raise ValueError("string runs past its block")
    return end, buf[o:end].decode("utf-16-le", errors="replace")


def _value(buf: bytes, o: int) -> Tuple[int, Any]:
    """Typed value (``LOOB``/``GNOL``/``BUOD``/``GRTS``) at ``o``."""
    kind = buf[o:o + 4]
    o += 4
    if kind == b"LOOB":
        return o + 4, bool(struct.unpack_from("<L", buf, o)[0])
    if kind == b"GNOL":
        return o + 4, struct.unpack_from("<l", buf, o)[0]
    if kind == b"BUOD":
        return o + 8, struct.unpack_from("<d", buf, o)[0]
    if kind == b"GRTS":
        return _string(buf, o)
    raise ValueError(f"unknown value type {kind!r}")


def _strings(buf: bytes, o: int = 0, limit: int = 32) -> List[str]:
    """Consecutive length-prefixed strings from ``o``, skipping 4-byte
    non-string fields between them. Used for the loosely structured
    ``ATEM`` / ``DPXE`` blocks; stops at the first thing it cannot read."""
    out: List[str] = []
    n = len(buf)
    while o + 4 <= n and len(out) < limit:
        try:
            end, s = _string(buf, o)
        except Exception:
            o += 4
            continue
        if s and s.isprintable():
            out.append(s)
            o = end
        else:
            o += 4
    return out


def iter_blocks(raw: bytes) -> Iterator[Tuple[bytes, int, Optional[int], bytes]]:
    """Yield ``(tag, offset, stamp_secs, body)`` for each top-level block.

    ``tag`` is returned in reading order ("PMOD", not "DOMP"). Stops at the
    first block whose declared length runs past the data; the caller sees
    that through :func:`stream_end`.
    """
    n = len(raw)
    dp = len(MAGIC)
    while dp + 8 <= n:
        tag = raw[dp:dp + 4]
        length = struct.unpack_from("<L", raw, dp + 4)[0]
        if tag in _UNSTAMPED:
            start, stamp = dp + 8, None
        else:
            if dp + 16 > n:
                return
            start = dp + 16
            stamp = struct.unpack_from("<Q", raw, dp + 8)[0]
        end = start + length
        if end > n:
            return
        yield tag[::-1], dp, stamp, raw[start:end]
        dp = end


def stream_end(raw: bytes) -> int:
    """Offset where :func:`iter_blocks` stops (== len(raw) when intact)."""
    n = len(raw)
    dp = len(MAGIC)
    while dp + 8 <= n:
        tag = raw[dp:dp + 4]
        length = struct.unpack_from("<L", raw, dp + 4)[0]
        start = dp + 8 if tag in _UNSTAMPED else dp + 16
        if start + length > n:
            return dp
        dp = start + length
    return dp


def _decode_snapshot(body: bytes) -> Dict[str, Tuple[Any, str]]:
    """``EEPA``: the full parameter set at experiment start."""
    out: Dict[str, Tuple[Any, str]] = {}
    n_dev = struct.unpack_from("<L", body, 4)[0]
    o = 8
    for _ in range(n_dev):
        o, device = _string(body, o)
        n_prop = struct.unpack_from("<L", body, o)[0]
        o += 4
        for _ in range(n_prop):
            o, prop = _string(body, o)
            o, unit = _string(body, o)
            o, value = _value(body, o + 4)
            out[f"{device}.{prop}"] = (value, unit)
    return out


def _decode_pmod(body: bytes) -> Tuple[str, Any, str]:
    """``PMOD``: one parameter change → (``Device.Prop``, value, unit)."""
    o, device = _string(body, 4)
    o, prop = _string(body, o)
    o, unit = _string(body, o)
    _o, value = _value(body, o + 4)
    return f"{device}.{prop}", value, unit


def parse_sts_location(value: str) -> Optional[Dict[str, Any]]:
    """``STS_LOCATION`` mark value → pixel, metre position and the raw
    reference to the scan image it was placed on."""
    m = _STS_RE.match(value.strip())
    if not m:
        return None
    try:
        return {"px": [int(m.group(1)), int(m.group(2))],
                "m": [float(m.group(3)), float(m.group(4))],
                "image_ref": (m.group(5) or "").strip("%") or None}
    except ValueError:
        return None


def parse_data_filename(name: str) -> Optional[Dict[str, Any]]:
    """``base--run_scan.Channel_mtrx`` → its parts, or None."""
    m = _DATA_FILE_RE.match(name)
    if not m:
        return None
    channel = m.group("channel")
    return {"base": m.group("base"), "run": int(m.group("run")),
            "scan": int(m.group("scan")), "channel": channel,
            # Spectroscopy channels are named after their sweep, "I(V)";
            # scan-image channels are bare, "Z" / "I".
            "kind": "spectroscopy" if "(" in channel else "image"}


def check_data_file(path: Path) -> Dict[str, Any]:
    """Integrity of one data file from its first 72 bytes.

    ``status`` is ``ok``, ``incomplete`` (MATRIX allocated more samples than
    it recorded — a scan or sweep stopped early), ``truncated`` (the file is
    shorter than its own block length says) or ``unreadable``.
    """
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            head = fh.read(_DATA_HEAD)
    except OSError as exc:
        return {"status": "unreadable", "detail": str(exc)}
    if len(head) < 68 or head[:12] != MAGIC or head[12:16] != b"TLKB":
        return {"status": "unreadable", "detail": "not a MATRIX data file"}
    tlkb_len = struct.unpack_from("<L", head, 16)[0]
    out: Dict[str, Any] = {"written": _stamp(struct.unpack_from("<Q", head, 20)[0])}
    if head[32:36] == b"CSED":
        expected, recorded = struct.unpack_from("<ii", head, 60)
        out["samples_expected"] = expected
        out["samples_recorded"] = recorded
        if recorded < expected:
            out["status"] = "incomplete"
            return out
    if size < 20 + 8 + tlkb_len:
        out["status"] = "truncated"
        out["detail"] = f"{size} of {20 + 8 + tlkb_len} bytes"
        return out
    out["status"] = "ok"
    return out


# ──────────────────────────────────────────────────────────────────────
# Header chain
# ──────────────────────────────────────────────────────────────────────

def header_chain(header: Path) -> Tuple[List[Path], List[str]]:
    """The ``_0001``, ``_0002``… links of ``header`` and any gap problems.

    MATRIX splits a long log into numbered links. A link missing from the
    middle (``_0003`` absent while ``_0004`` exists) silently drops every
    event in it, so it is reported rather than just stopping at the gap.
    """
    stem = str(header)[:-len("_0001.mtrx")]
    pattern = re.compile(re.escape(Path(stem).name) + r"_(\d{4})\.mtrx$")
    numbers = []
    try:
        for f in header.parent.iterdir():
            m = pattern.match(f.name)
            if m:
                numbers.append(int(m.group(1)))
    except OSError:
        pass
    numbers.sort()
    links, problems = [], []
    expect = 1
    for k in numbers:
        if k != expect:
            problems.append(f"header link(s) _{expect:04d}"
                            f"{'' if k - 1 == expect else f'.._{k - 1:04d}'}"
                            f" missing before _{k:04d}; events after the gap "
                            f"were not read")
            break
        links.append(Path(f"{stem}_{k:04d}.mtrx"))
        expect += 1
    return links, problems


def read_header_chain(header: Path) -> bytes:
    """Concatenate a header chain the way MATRIX/access2theMatrix do (the
    magic prefix is stripped from every link after the first)."""
    links, _ = header_chain(header)
    raw = b""
    for i, link in enumerate(links):
        data = link.read_bytes()
        raw += data if i == 0 else data[len(MAGIC):]
    return raw


# ──────────────────────────────────────────────────────────────────────
# Inventory
# ──────────────────────────────────────────────────────────────────────

# How bad each flag is. ``error``: data is gone or unusable. ``warning``:
# data is there but something about it is off. ``info``: worth knowing,
# normal practice (an image stopped once the area of interest was seen).
SEVERITY = {
    "file_missing": "error", "truncated": "error", "unreadable": "error",
    "not_loaded": "error", "header_missing": "error",
    "header_unreadable": "error", "header_chain_gap": "error",
    "stream_truncated": "error",
    "not_in_header": "warning", "incomplete": "warning",
    "channel_missing": "warning", "scan_absent": "warning",
    "no_end_marker": "warning", "block_undecodable": "warning",
    "run_absent": "info", "stopped_early": "info", "file_elsewhere": "info",
}


def _flag(code: str, detail: str = "", channel: Optional[str] = None
          ) -> Dict[str, Any]:
    f: Dict[str, Any] = {"code": code,
                         "severity": SEVERITY.get(code, "warning")}
    if channel:
        f["channel"] = channel
    if detail:
        f["detail"] = detail
    return f


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) <= 1e-12 * max(abs(a), abs(b))
    return a == b


def _session_disk_files(base: str, directory: Path) -> Dict[str, Path]:
    prefix = f"{base}--"
    out: Dict[str, Path] = {}
    try:
        with os.scandir(directory) as it:
            for e in it:
                if e.name.startswith(prefix) and e.name.endswith("_mtrx"):
                    out[e.name] = Path(e.path)
    except OSError as exc:
        logger.debug("Could not list %s: %s", directory, exc)
    return out


def _locate_elsewhere(names: Iterable[str], directory: Path,
                      limit: int = 64) -> Dict[str, List[str]]:
    """Where missing files actually are, if they were moved nearby.

    A session spanning midnight is often filed in two day folders, so a file
    "missing" here may sit in a sibling or a sub-folder. Searches the parent,
    its sub-folders and theirs (two levels), plus this folder's
    sub-folders. Returns ``{folder: [names…]}``.
    """
    wanted = set(names)
    if not wanted:
        return {}
    roots: List[Path] = []
    parent = directory.parent
    try:
        for d in [parent] + sorted(p for p in parent.iterdir() if p.is_dir()):
            roots.append(d)
            if d != parent:
                roots.extend(sorted(p for p in d.iterdir() if p.is_dir()))
    except OSError:
        pass
    found: Dict[str, List[str]] = {}
    for d in roots[:limit]:
        if d == directory:
            continue
        try:
            with os.scandir(d) as it:
                hits = [e.name for e in it if e.name in wanted]
        except OSError:
            continue
        if hits:
            found[str(d)] = sorted(hits)
            wanted.difference_update(hits)
            if not wanted:
                break
    return found


def build_session_inventory(base: str, directory: Path,
                            header: Optional[Path] = None,
                            raw: Optional[bytes] = None,
                            check_files: bool = True,
                            not_loaded: Iterable[str] = (),
                            ) -> Dict[str, Any]:
    """Structured account of one MATRIX session.

    ``base`` is the session base name and ``directory`` the folder holding
    its data files. ``header`` defaults to ``{base}_0001.mtrx`` in that
    folder; ``raw`` may pass an already-read header chain to avoid reading a
    100 MB log twice. ``check_files`` reads each data file's 72-byte head to
    find aborted and truncated files. ``not_loaded`` names data files the
    loader could not turn into curves; they are flagged too.
    """
    directory = Path(directory)
    if header is None:
        cand = directory / f"{base}_0001.mtrx"
        header = cand if cand.exists() else None

    inv: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "format": "Omicron MATRIX session inventory",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "session": {"base": base, "directory": str(directory)},
        "file_pattern": f"{base}--{{run}}_{{scan}}.{{channel}}_mtrx",
        "flags": [],
    }
    session = inv["session"]
    flags: List[Dict[str, Any]] = inv["flags"]

    # ── Replay the parameter log ────────────────────────────────────
    initial: Dict[str, Tuple[Any, str]] = {}
    state: Dict[str, Tuple[Any, str]] = {}
    # Real changes only, as (stamp_secs, param, new_value): a drift-
    # compensated session writes ~10^6 of them, so no per-change dict.
    changes: List[Tuple[Optional[int], str, Any]] = []
    units: Dict[str, str] = {}
    marks: List[Dict[str, Any]] = []
    recording: Dict[str, bool] = {}
    meas: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    referenced: Dict[str, Tuple[str, int, int]] = {}
    first_time = last_time = None

    if header is not None:
        links, problems = header_chain(header)
        session["header_files"] = [str(p) for p in links]
        for p in problems:
            flags.append(_flag("header_chain_gap", p))
        if raw is None:
            try:
                raw = read_header_chain(header)
            except OSError as exc:
                flags.append(_flag("header_unreadable", str(exc)))
                raw = b""
    else:
        flags.append(_flag(
            "header_missing",
            f"no {base}_0001.mtrx in this folder: parameters, times and STS "
            f"locations are unknown and the inventory is built from the "
            f"files on disk alone"))
        raw = b""

    if raw and raw[:len(MAGIC)] != MAGIC:
        flags.append(_flag("header_unreadable", "not a MATRIX parameter file"))
        raw = b""

    sts: Optional[Dict[str, Any]] = None
    n_noop = 0
    for tag, offset, secs, body in iter_blocks(raw):
        when = _stamp(secs) if secs is not None else None
        if when:
            first_time = first_time or when
            last_time = when
        try:
            if tag == b"PMOD":
                key, value, unit = _decode_pmod(body)
                old = state.get(key, (None, unit))[0]
                if key in state and _same(old, value):
                    n_noop += 1
                    continue
                state[key] = (value, unit)
                units[key] = unit
                changes.append((secs, key, value))
            elif tag == b"EEPA":
                snap = _decode_snapshot(body)
                if not initial:
                    initial = dict(snap)
                    session["parameters_snapshot_time"] = when
                state.update(snap)
            elif tag == b"BREF":
                _o, name = _string(body, 4)
                info = parse_data_filename(name)
                if info is None:
                    marks.append({"time": when, "key": "UNPARSED_BREF",
                                  "value": name})
                    continue
                key3 = (info["kind"], info["run"], info["scan"])
                m = meas.get(key3)
                if m is None:
                    m = meas[key3] = {
                        "kind": info["kind"], "run": info["run"],
                        "scan": info["scan"], "time": when,
                        "channels": [], "_version": len(changes),
                        "flags": [],
                    }
                    if info["kind"] == "spectroscopy" and sts is not None:
                        m["location"] = sts
                if info["channel"] not in m["channels"]:
                    m["channels"].append(info["channel"])
                referenced[name] = key3
            elif tag == b"MARK":
                _o, text = _string(body, 0)
                mm = _MARK_RE.match(text)
                if not mm:
                    marks.append({"time": when, "key": "TEXT", "value": text})
                    continue
                k, v = mm.group("key"), mm.group("value")
                if k == "STS_LOCATION":
                    sts = parse_sts_location(v) or {"raw": v}
                    sts = dict(sts, time=when)
                elif k in ("ENABLE_RECORDING", "DISABLE_RECORDING"):
                    recording[v] = k == "ENABLE_RECORDING"
                    continue          # state, reported once at the end
                elif k == "SAMPLE_NAME":
                    session["sample_name"] = v
                elif k == "DATA_SET_NAME":
                    session["data_set_name"] = v
                elif k == "CREATION_COMMENT":
                    session["creation_comment"] = v
                elif k in ("FOREIGN_PARAM_ADDITION", "FOREIGN_PARAM_VALUE"):
                    parts = v.split(";")
                    if len(parts) == 4:
                        unit, _typ, val, prop = parts
                        key = f"Foreign.{prop}"
                        old = state.get(key, (None, unit))[0]
                        if not _same(old, val):
                            state[key] = (val, unit)
                            units[key] = unit
                            changes.append((secs, key, val))
                if k != "STS_LOCATION":
                    marks.append({"time": when, "key": k, "value": v})
            elif tag == b"META":
                session["matrix_version"] = " · ".join(_strings(body))
            elif tag == b"EXPD":
                session["experiment"] = _strings(body, 4)
            elif tag == b"EOED":
                session["experiment_end"] = when
        except Exception as exc:
            flags.append(_flag("block_undecodable",
                               f"{tag.decode(errors='replace')} at byte "
                               f"{offset}: {exc}"))

    if raw:
        end = stream_end(raw)
        if end < len(raw):
            flags.append(_flag(
                "stream_truncated",
                f"parameter log stops at byte {end} of {len(raw)}: the last "
                f"block is cut short (MATRIX killed while writing?) and "
                f"anything after it is lost"))
        if "experiment_end" not in session:
            flags.append(_flag(
                "no_end_marker",
                "the log has no end-of-experiment record: the session was "
                "not closed normally (crash, power loss, or still running "
                "when copied)"))
    session["start"] = first_time
    session["end"] = last_time
    if recording:
        session["recording_channels"] = {
            "enabled": sorted(c for c, on in recording.items() if on),
            "disabled": sorted(c for c, on in recording.items() if not on)}

    # ── Reconcile with the disk ─────────────────────────────────────
    disk = _session_disk_files(base, directory)
    not_loaded = set(not_loaded)
    missing: Dict[str, Tuple[Dict[str, Any], str]] = {}
    for name, key3 in referenced.items():
        chan = parse_data_filename(name)["channel"]
        m = meas[key3]
        path = disk.get(name)
        if path is None:
            missing[name] = (m, chan)
            continue
        if check_files:
            _check_into(m, path, chan)
        if name in not_loaded:
            m["flags"].append(_flag("not_loaded",
                                    "on disk but could not be read as a curve",
                                    chan))
    for name, path in disk.items():
        if name in referenced:
            continue
        info = parse_data_filename(name)
        if info is None:
            continue
        key3 = (info["kind"], info["run"], info["scan"])
        m = meas.get(key3)
        if m is None:
            m = meas[key3] = {"kind": info["kind"], "run": info["run"],
                              "scan": info["scan"], "time": None,
                              "channels": [], "flags": []}
        if info["channel"] not in m["channels"]:
            m["channels"].append(info["channel"])
        if header is not None:
            m["flags"].append(_flag(
                "not_in_header",
                "on disk but never referenced by the header log", info["channel"]))
        res = check_data_file(path) if (check_files or m["time"] is None) else {}
        if m["time"] is None and res.get("written"):
            m["time"] = res["written"]
            m["time_source"] = "data file"
        if check_files:
            _record_check(m, res, info["channel"])
        if name in not_loaded:
            m["flags"].append(_flag("not_loaded",
                                    "on disk but could not be read as a curve",
                                    info["channel"]))
    # A referenced file that is not here may only have been filed in another
    # day folder (sessions running past midnight are split that way): that
    # is worth knowing, not lost data.
    where: Dict[str, str] = {}
    if missing:
        elsewhere = _locate_elsewhere(missing, directory)
        if elsewhere:
            inv["missing_files_found_elsewhere"] = {
                d: len(v) for d, v in elsewhere.items()}
        where = {n: d for d, names in elsewhere.items() for n in names}
    for name, (m, chan) in missing.items():
        if name in where:
            m["flags"].append(_flag("file_elsewhere",
                                    f"not in this folder; found in {where[name]}",
                                    chan))
        else:
            m["flags"].append(_flag("file_missing",
                                    "referenced by the header, not on disk "
                                    "here or in nearby folders", chan))

    # ── Gaps: channels within a run, scans within a run, runs ───────
    runs: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
    for m in meas.values():
        runs[(m["kind"], m["run"])].append(m)
    for (kind, run), ms in runs.items():
        union = sorted({c for m in ms for c in m["channels"]})
        for m in ms:
            for c in union:
                if c not in m["channels"]:
                    m["flags"].append(_flag(
                        "channel_missing",
                        f"recorded at other scans of run {run}, not this one",
                        c))
        present = {m["scan"] for m in ms}
        for s in range(1, max(present) + 1):
            if s not in present:
                meas[(kind, run, s)] = {
                    "kind": kind, "run": run, "scan": s, "time": None,
                    "channels": [], "status": "absent",
                    "flags": [_flag("scan_absent",
                                    f"scan {s} of run {run} is neither in the "
                                    f"header nor on disk, but later scans are")]}
    for kind in ("image", "spectroscopy"):
        run_ids = sorted({r for (k, r) in runs if k == kind})
        if not run_ids:
            continue
        gaps = [r for r in range(1, run_ids[-1] + 1) if r not in set(run_ids)]
        if gaps:
            flags.append(_flag(
                "run_absent",
                f"{kind} run(s) {_ranges(gaps)} have no files and no header "
                f"reference (aborted before writing, or deleted)"))

    # ── Parameter epochs and per-measurement change sets ────────────
    # Two sorts of parameter change. *Settings* are changed by the operator
    # a handful of times (bias, setpoint, frame size); every distinct
    # combination in use becomes a parameter epoch, and each measurement
    # names its epoch and what changed since the previous one. *Tracked*
    # parameters are written by MATRIX itself, more often than measurements
    # are taken — drift compensation rewrites the scan offsets several times
    # a second. Their every value would bury the settings and give each
    # measurement its own epoch, so instead each measurement carries their
    # value at that moment, and the history keeps only their jumps.
    n_changes: Dict[str, int] = defaultdict(int)
    for _t, k, _v in changes:
        n_changes[k] += 1
    tracked_limit = max(_TRACKED_MIN_CHANGES, len(meas))
    tracked = sorted(k for k, n in n_changes.items() if n > tracked_limit)
    settings = sorted(k for k in n_changes if k not in set(tracked))
    jump = {k: _jump_threshold(k, changes, initial) for k in tracked}

    ordered = sorted(meas.values(),
                     key=lambda m: (m["time"] or "9999", m["kind"],
                                    m["run"], m["scan"]))
    by_version: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for m in ordered:
        if "_version" in m:
            by_version[m.pop("_version")].append(m)

    cur = {k: initial.get(k, (None, ""))[0] for k in n_changes}
    epochs: List[Dict[str, Any]] = []
    seen_states: Dict[Tuple, int] = {}
    history: List[Dict[str, Any]] = []
    last_change_time = session.get("parameters_snapshot_time")
    pending = sorted(by_version)
    pi = 0
    for ci in range(len(changes) + 1):
        # Measurements whose BREF came after exactly `ci` changes.
        while pi < len(pending) and pending[pi] == ci:
            frozen = tuple(_hashable(cur[k]) for k in settings)
            eid = seen_states.get(frozen)
            if eid is None:
                eid = seen_states[frozen] = len(epochs)
                epochs.append({"id": eid, "from": last_change_time,
                               "values": {k: cur[k] for k in settings}})
            for m in by_version[pending[pi]]:
                m["parameter_epoch"] = eid
                if tracked:
                    m["tracked"] = {k: cur[k] for k in tracked}
            pi += 1
        if ci == len(changes):
            break
        secs, k, v = changes[ci]
        old = cur.get(k)
        cur[k] = v
        t = _stamp(secs) if secs is not None else None
        if k in jump:
            th = jump[k]
            if th is None or not _is_num(old) or abs(v - old) <= th:
                continue
            history.append({"time": t, "param": k, "from": old, "to": v,
                            "unit": units.get(k, ""), "tracked": True})
        else:
            last_change_time = t
            history.append({"time": t, "param": k, "from": old, "to": v,
                            "unit": units.get(k, "")})

    def param_at(m: Dict[str, Any], key: str) -> Any:
        """Value of ``key`` when ``m`` was taken."""
        if key in (m.get("tracked") or {}):
            return m["tracked"][key]
        if "parameter_epoch" in m and key in epochs[m["parameter_epoch"]]["values"]:
            return epochs[m["parameter_epoch"]]["values"][key]
        return initial.get(key, (None, ""))[0]

    previous: Dict[str, int] = {}
    for m in ordered:
        for chan, res in sorted(m.pop("_stopped", {}).items()):
            m["flags"].append(_flag("stopped_early",
                                    _image_coverage(res, m, param_at), chan))
        eid = m.get("parameter_epoch")
        if eid is not None:
            pe = previous.get(m["kind"])
            if pe is not None and pe != eid:
                a, b = epochs[pe]["values"], epochs[eid]["values"]
                diff = {k: {"from": a[k], "to": b[k]} for k in settings
                        if not _same(a[k], b[k])}
                if diff:
                    m["changed_since_previous"] = diff
            previous[m["kind"]] = eid
        # ok / info / warning / error (worst flag), or "absent" for a gap.
        m.setdefault("status", max((f["severity"] for f in m["flags"]),
                                   key=_RANK.__getitem__, default="ok"))
        if not m["flags"]:
            del m["flags"]

    # ── Assemble ────────────────────────────────────────────────────
    def _describe(k: str) -> Dict[str, Any]:
        d = {"unit": units.get(k) or initial.get(k, (None, ""))[1],
             "initial": initial.get(k, (None, ""))[0],
             "final": state.get(k, (None, ""))[0],
             "n_changes": n_changes[k]}
        if k in jump:
            d["jump_threshold"] = jump[k]
            d["n_jumps"] = sum(1 for h in history
                               if h["param"] == k and h.get("tracked"))
        return d

    inv["parameters"] = {
        "initial": _group({k: {"value": v, "unit": u}
                           for k, (v, u) in initial.items()}),
        "constant_count": sum(1 for k in initial if k not in n_changes),
        "varying": {k: _describe(k) for k in settings},
        "tracked": {k: _describe(k) for k in tracked},
        "history": history,
        "no_op_writes": n_noop,
    }
    inv["parameter_epochs"] = epochs
    inv["marks"] = marks
    inv["runs"] = _run_summary(runs, meas)
    inv["measurements"] = ordered
    inv["summary"] = _summary(inv, disk, referenced)
    return inv


def _check_into(m: Dict[str, Any], path: Path, chan: str) -> None:
    _record_check(m, check_data_file(path), chan)


def _record_check(m: Dict[str, Any], res: Dict[str, Any], chan: str) -> None:
    status = res.get("status")
    if status in (None, "ok"):
        return
    if status == "incomplete" and m["kind"] == "image":
        # Judged once the scan geometry at that time is known, in
        # _image_coverage: stopping a frame early is routine, not damage.
        m.setdefault("_stopped", {})[chan] = res
        return
    if status == "incomplete":
        detail = (f"{res.get('samples_recorded')} of "
                  f"{res.get('samples_expected')} samples recorded "
                  f"(stopped early)")
    else:
        detail = res.get("detail", "")
    m["flags"].append(_flag(status, detail, chan))


def _image_coverage(res: Dict[str, Any], m: Dict[str, Any], param_at) -> str:
    """Where a stopped scan image stopped, in lines, when the geometry it
    was taken with accounts for its allocated size; else the raw count."""
    rec, exp = res.get("samples_recorded"), res.get("samples_expected")
    generic = f"{rec} of {exp} samples recorded"
    try:
        pts = int(param_at(m, "XYScanner.Points"))
        lines = int(param_at(m, "XYScanner.Lines"))
        xr = 2 if param_at(m, "XYScanner.X_Retrace") else 1
        yr = 2 if param_at(m, "XYScanner.Y_Retrace") else 1
    except (TypeError, ValueError):
        return generic
    if not pts or pts * lines * xr * yr != exp:
        return generic
    done = rec // (pts * xr)
    if done < lines:
        where = f"up pass stopped at line {done} of {lines}"
    else:
        where = (f"up pass complete, down pass stopped at line "
                 f"{done - lines} of {lines}")
    return f"{where} ({100 * rec / exp:.0f}% of the frame)"


# A parameter changed more often than this (and more often than there are
# measurements) is being written by MATRIX, not by the operator.
_TRACKED_MIN_CHANGES = 200

# A tracked parameter's change is reported as a jump when it is larger than
# both _JUMP_FACTOR x its median step and _JUMP_TAIL_FACTOR x the largest
# step size that RECURS (>= _RECURRING steps within a tenth of a decade).
# Measured on a drift-compensated session (480k offset writes): ticks are
# ~1 pm (the median); re-registration steps of one image pixel (3.9 / 6.2
# nm) recur hundreds of times; the operator's frame moves are one-offs from
# ~30 nm to µm. The median rule alone kept 630 pixel steps as "jumps". A
# percentile cannot replace the recurrence test: on a short log the top
# percentile IS the operator's move.
_JUMP_FACTOR = 100.0
_JUMP_TAIL_FACTOR = 10.0
_RECURRING = 10


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _jump_threshold(key: str, changes, initial) -> Optional[float]:
    """Smallest step of a tracked parameter that counts as a jump, scaled
    to its own step distribution (see ``_JUMP_FACTOR``), or None if it is
    not numeric."""
    prev = initial.get(key, (None, ""))[0]
    steps = []
    for _t, k, v in changes:
        if k != key:
            continue
        if _is_num(prev) and _is_num(v) and v != prev:
            steps.append(abs(v - prev))
        prev = v
    if not steps:
        return None
    steps.sort()
    median = steps[len(steps) // 2]
    bins: Dict[int, int] = defaultdict(int)
    for st in steps:
        bins[math.floor(10 * math.log10(st))] += 1
    recurring = [b for b, n in bins.items() if n >= _RECURRING]
    tail = 10 ** ((max(recurring) + 1) / 10) if recurring else median
    return max(_JUMP_FACTOR * median, _JUMP_TAIL_FACTOR * tail)


def _hashable(v: Any) -> Any:
    return tuple(v) if isinstance(v, list) else v


def _ranges(nums: List[int]) -> str:
    """[1,2,3,7,9,10] → "1-3, 7, 9-10"."""
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def _group(flat: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """``Device.Prop`` keys → ``{Device: {Prop: …}}``, sorted."""
    grouped: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for k, v in flat.items():
        dev, _, prop = k.partition(".")
        grouped[dev][prop or k] = v
    return {d: dict(sorted(p.items())) for d, p in sorted(grouped.items())}


def _run_summary(runs, meas) -> List[Dict[str, Any]]:
    out = []
    for (kind, run) in sorted(runs, key=lambda kr: (kr[0], kr[1])):
        ms = sorted((m for m in meas.values()
                     if m["kind"] == kind and m["run"] == run),
                    key=lambda m: m["scan"])
        times = [m["time"] for m in ms if m["time"]]
        entry = {
            "kind": kind, "run": run, "scans": len(ms),
            "channels": sorted({c for m in ms for c in m["channels"]}),
            "start": min(times) if times else None,
            "end": max(times) if times else None,
            "flagged_scans": sum(1 for m in ms if m.get("flags")),
        }
        locs = []
        for m in ms:
            loc = m.get("location")
            if loc and loc.get("px") and loc["px"] not in locs:
                locs.append(loc["px"])
        if locs:
            entry["locations_px"] = locs
        epochs = sorted({m["parameter_epoch"] for m in ms
                         if "parameter_epoch" in m})
        if epochs:
            entry["parameter_epochs"] = epochs
        out.append(entry)
    return out


_RANK = {"info": 0, "warning": 1, "error": 2}


def _summary(inv, disk, referenced) -> Dict[str, Any]:
    ms = inv["measurements"]
    by_code: Dict[str, int] = defaultdict(int)
    by_sev: Dict[str, int] = defaultdict(int)
    for m in ms:
        worst = None
        for f in m.get("flags", []):
            by_code[f["code"]] += 1
            if worst is None or _RANK[f["severity"]] > _RANK[worst]:
                worst = f["severity"]
        if worst:
            by_sev[worst] += 1
    kinds: Dict[str, int] = defaultdict(int)
    for m in ms:
        if m.get("status") != "absent":
            kinds[m["kind"]] += 1
    return {
        "measurements": dict(kinds),
        "runs": {k: sum(1 for r in inv["runs"] if r["kind"] == k)
                 for k in ("image", "spectroscopy")},
        "files_on_disk": len(disk),
        "files_referenced_by_header": len(referenced),
        "measurements_flagged": sum(1 for m in ms if m.get("flags")),
        # Each measurement counted once, under its worst flag.
        "measurements_by_severity": {k: by_sev[k] for k in
                                     ("error", "warning", "info") if by_sev[k]},
        "flags_by_code": dict(sorted(by_code.items())),
        "session_flags": [f["code"] for f in inv["flags"]],
        "parameters_changed": len(inv["parameters"]["varying"]),
        "parameter_changes": sum(d["n_changes"] for d in
                                 inv["parameters"]["varying"].values()),
        "parameters_tracked": len(inv["parameters"]["tracked"]),
        "parameter_epochs": len(inv["parameter_epochs"]),
    }


# ──────────────────────────────────────────────────────────────────────
# Folder-level entry point
# ──────────────────────────────────────────────────────────────────────

def session_bases(directory: Path) -> List[str]:
    """Every session base in ``directory``, from data files AND headers
    (a session whose data files are all gone still has a header)."""
    bases = set()
    try:
        with os.scandir(directory) as it:
            for e in it:
                n = e.name
                if "--" in n and n.endswith("_mtrx"):
                    bases.add(n.rsplit("--", 1)[0])
                else:
                    m = re.match(r"(.*?)_\d{4}\.mtrx$", n)
                    if m:
                        bases.add(m.group(1))
    except OSError:
        pass
    return sorted(bases)


def build_inventories(path: Path, check_files: bool = True
                      ) -> List[Dict[str, Any]]:
    """Inventories for a session file (its session) or a folder (every
    session in it)."""
    path = Path(path)
    if path.is_dir():
        return [build_session_inventory(b, path, check_files=check_files)
                for b in session_bases(path)]
    name = path.name
    base = (name.rsplit("--", 1)[0] if "--" in name
            else re.sub(r"_\d{4}\.mtrx$", "", name))
    return [build_session_inventory(base, path.parent, check_files=check_files)]


# ──────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────

def _json_default(o: Any) -> Any:
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, bytes):
        return o.hex()
    return str(o)


def write_inventory(inv: Dict[str, Any], out_dir: Path,
                    stem: Optional[str] = None) -> Tuple[Path, Path]:
    """Write ``inv`` as ``<stem>.inventory.json`` and ``.txt`` in
    ``out_dir`` (created if needed). Returns both paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or inv["session"]["base"]
    jpath = out_dir / f"{stem}.inventory.json"
    tpath = out_dir / f"{stem}.inventory.txt"
    big = len(inv.get("measurements", [])) > _INDENT_LIMIT
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(inv, fh, ensure_ascii=False, default=_json_default,
                  indent=None if big else 1,
                  separators=(",", ":") if big else None)
    tpath.write_text(render_text(inv), encoding="utf-8")
    return jpath, tpath


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def render_text(inv: Dict[str, Any], max_flag_lines: int = 2000) -> str:
    """Readable account of one inventory. Complete for the session, its
    parameters, history, runs and flags; individual measurements without
    problems are summarised per run (the JSON lists every one)."""
    s = inv["session"]
    summ = inv["summary"]
    # Clock time alone is ambiguous once a session runs past midnight
    # (some run for a week): add the date then.
    multi_day = bool(s.get("start") and s.get("end")
                     and s["start"][:10] != s["end"][:10])

    def when(iso: Optional[str]) -> str:
        if not iso:
            return ""
        return iso[5:].replace("T", " ") if multi_day else iso[11:]

    L: List[str] = []
    rule = "═" * 78
    L += [rule, f"MATRIX SESSION INVENTORY · {s['base']}", rule]
    for label, key in (("Folder", "directory"), ("Sample", "sample_name"),
                       ("Data set", "data_set_name"),
                       ("Comment", "creation_comment"),
                       ("Started", "start"), ("Last event", "end"),
                       ("Closed", "experiment_end"),
                       ("MATRIX", "matrix_version")):
        if s.get(key):
            L.append(f"  {label:<12} {s[key]}")
    if s.get("experiment"):
        L.append(f"  {'Experiment':<12} {' · '.join(s['experiment'][:3])}")
    for h in s.get("header_files", []):
        L.append(f"  {'Header':<12} {Path(h).name}")
    rec = s.get("recording_channels")
    if rec:
        L.append(f"  {'Recording':<12} {', '.join(rec['enabled'])}")

    L += ["", "SUMMARY", "─" * 78]
    for k, v in summ["measurements"].items():
        L.append(f"  {k} measurements: {v}  (runs: {summ['runs'].get(k, 0)})")
    L.append(f"  files on disk: {summ['files_on_disk']}   referenced by header: "
             f"{summ['files_referenced_by_header']}")
    L.append(f"  parameters changed during session: {summ['parameters_changed']}"
             f" ({summ['parameter_changes']} changes, "
             f"{summ['parameter_epochs']} distinct states used)")
    sev = summ.get("measurements_by_severity") or {}
    L.append(f"  measurements flagged: {summ['measurements_flagged']}"
             + (f"  ({', '.join(f'{n} {k}' for k, n in sev.items())})"
                if sev else ""))
    for code, n in summ["flags_by_code"].items():
        L.append(f"    {code:<20} {n}")
    for f in inv["flags"]:
        L.append(f"  ! SESSION {f['severity']} {f['code']}: "
                 f"{f.get('detail', '')}")
    for d, n in (inv.get("missing_files_found_elsewhere") or {}).items():
        L.append(f"  → {n} referenced file(s) not here are in {d}")

    var = inv["parameters"]["varying"]
    trk = inv["parameters"]["tracked"]
    if var:
        L += ["", "PARAMETERS THAT CHANGED", "─" * 78]
        for k, d in var.items():
            L.append(f"  {k:<40} {_fmt(d['initial'])} → {_fmt(d['final'])} "
                     f"{d['unit']}  ({d['n_changes']}×)")
    if trk:
        L += ["", "PARAMETERS WRITTEN CONTINUOUSLY BY MATRIX", "─" * 78,
              "  (value at each measurement is in the JSON, 'tracked'; only "
              "jumps are in the history)"]
        for k, d in trk.items():
            th = (f", jumps > {_fmt(d['jump_threshold'])}: {d['n_jumps']}"
                  if d.get("jump_threshold") is not None else "")
            L.append(f"  {k:<40} {_fmt(d['initial'])} → {_fmt(d['final'])} "
                     f"{d['unit']}  ({d['n_changes']}×{th})")
    if inv["parameters"]["history"]:
        L += ["", "PARAMETER HISTORY", "─" * 78]
        for c in inv["parameters"]["history"]:
            t = when(c["time"])
            tag = "  (jump)" if c.get("tracked") else ""
            L.append(f"  {t:<9} {c['param']:<40} {_fmt(c['from'])} → "
                     f"{_fmt(c['to'])} {c['unit']}{tag}")

    L += ["", "RUNS", "─" * 78]
    for r in inv["runs"]:
        t0 = when(r["start"])
        t1 = when(r["end"])
        loc = ""
        if r.get("locations_px"):
            loc = " at " + "; ".join(f"({x},{y})"
                                     for x, y in r["locations_px"][:4])
            if len(r["locations_px"]) > 4:
                loc += f" +{len(r['locations_px']) - 4}"
        ep = ""
        if r.get("parameter_epochs"):
            ep = f" epoch {_ranges(r['parameter_epochs'])}"
        bad = f"  ⚑ {r['flagged_scans']} flagged" if r["flagged_scans"] else ""
        L.append(f"  {r['kind'][:4]} run {r['run']:>4}  {r['scans']:>5} scan(s)"
                 f"  {t0}–{t1}  [{', '.join(r['channels'])}]{loc}{ep}{bad}")

    flagged = [m for m in inv["measurements"] if m.get("flags")]
    if flagged:
        L += ["", "FLAGGED MEASUREMENTS", "─" * 78]
        for m in flagged[:max_flag_lines]:
            t = when(m.get("time")) or "?"
            for f in m["flags"]:
                ch = f" {f['channel']}" if f.get("channel") else ""
                L.append(f"  {m['kind'][:4]} {m['run']}_{m['scan']:<6} {t:<9}"
                         f" {f['severity']:<7} {f['code']}{ch}: "
                         f"{f.get('detail', '')}")
        if len(flagged) > max_flag_lines:
            L.append(f"  … {len(flagged) - max_flag_lines} more in the JSON")

    if inv["marks"]:
        L += ["", "ANNOTATIONS", "─" * 78]
        for mk in inv["marks"]:
            L.append(f"  {when(mk['time']):<9} {mk['key']}: "
                     f"{str(mk['value'])[:200]}")

    init = inv["parameters"]["initial"]
    if init:
        L += ["", "PARAMETERS AT SESSION START", "─" * 78]
        for dev, props in init.items():
            L.append(f"  [{dev}]")
            for p, d in props.items():
                L.append(f"    {p:<38} {_fmt(d['value'])} {d['unit']}")
    L.append("")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Write a metadata inventory (JSON + TXT) for Omicron "
                    "MATRIX sessions.")
    ap.add_argument("path", help="a session file (_0001.mtrx or any data "
                                 "file) or a folder of sessions")
    ap.add_argument("-o", "--out", help="output folder (default: next to "
                                        "the data)")
    ap.add_argument("--no-file-check", action="store_true",
                    help="skip reading each data file's head (faster; "
                         "aborted/truncated files are then not detected)")
    a = ap.parse_args(argv)
    path = Path(a.path).expanduser()
    out = Path(a.out).expanduser() if a.out else (
        path if path.is_dir() else path.parent)
    for inv in build_inventories(path, check_files=not a.no_file_check):
        j, t = write_inventory(inv, out)
        sm = inv["summary"]
        print(f"{inv['session']['base']}: "
              f"{sum(sm['measurements'].values())} measurements, "
              f"{sm['measurements_flagged']} flagged → {j.name}, {t.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
