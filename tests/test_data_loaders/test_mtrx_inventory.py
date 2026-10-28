"""Tests for the Omicron MATRIX session inventory.

The fixtures are synthetic MATRIX streams written byte by byte in the layout
real ``_0001.mtrx`` headers and bricklet files use (checked against sessions
from the instrument), so every flag can be planted deliberately.
"""

import json
import struct
from pathlib import Path

import pytest

from src.data_loaders.mtrx_inventory import (
    MAGIC, build_inventories, build_session_inventory, check_data_file,
    parse_data_filename, parse_sts_location, render_text, write_inventory)

BASE = "default_2026Jul22-162533_STM-STM_Spectroscopy"
T0 = 1784730000          # 2026-07-22, a plausible session time


# ── Stream builders ──────────────────────────────────────────────────

def _s(text):
    return struct.pack("<L", len(text)) + text.encode("utf-16-le")


def _v(value):
    if isinstance(value, bool):
        return b"LOOB" + struct.pack("<L", int(value))
    if isinstance(value, int):
        return b"GNOL" + struct.pack("<l", value)
    if isinstance(value, float):
        return b"BUOD" + struct.pack("<d", value)
    return b"GRTS" + _s(value)


def _block(tag, body, secs):
    return (tag[::-1].encode() + struct.pack("<L", len(body))
            + struct.pack("<Q", secs) + body)


def eepa(params, secs=T0):
    devices = {}
    for key, (value, unit) in params.items():
        dev, prop = key.split(".", 1)
        devices.setdefault(dev, []).append((prop, unit, value))
    body = b"\0" * 4 + struct.pack("<L", len(devices))
    for dev, props in devices.items():
        body += _s(dev) + struct.pack("<L", len(props))
        for prop, unit, value in props:
            body += _s(prop) + _s(unit) + b"\0" * 4 + _v(value)
    return _block("EEPA", body, secs)


def pmod(key, value, unit, secs):
    dev, prop = key.split(".", 1)
    body = (b"\0" * 4 + _s(dev) + _s(prop) + _s(unit) + b"\0" * 4
            + _v(value))
    return _block("PMOD", body, secs)


def bref(name, secs):
    return _block("BREF", b"\0" * 4 + _s(name), secs)


def mark(text, secs):
    return _block("MARK", _s(text), secs)


def eoed(secs):
    return _block("EOED", b"", secs)


def data_file(path, recorded, expected=None, secs=T0, truncate=0):
    """A bricklet file whose CSED says ``recorded`` of ``expected``."""
    expected = recorded if expected is None else expected
    csed = bytearray(56)
    struct.pack_into("<ii", csed, 20, expected, recorded)
    atad = b"ATAD" + struct.pack("<L", 4 * recorded) + b"\0" * (4 * recorded)
    inner = b"\0" * 4 + b"CSED" + struct.pack("<L", 56) + bytes(csed) + atad
    raw = (MAGIC + b"TLKB" + struct.pack("<L", len(inner))
           + struct.pack("<Q", secs) + inner)
    path.write_bytes(raw[:len(raw) - truncate] if truncate else raw)


def name(run, scan, channel):
    return f"{BASE}--{run}_{scan}.{channel}_mtrx"


SNAPSHOT = {
    "GapVoltageControl.Voltage": (1.0, "Volt"),
    "Regulator.Setpoint_1": (1e-10, "Ampere"),
    "XYScanner.Points": (4, "Count"),
    "XYScanner.Lines": (4, "Count"),
    "XYScanner.X_Retrace": (True, "--"),
    "XYScanner.Y_Retrace": (True, "--"),
    "XYScanner.X_Offset": (0.0, "Meter"),
}


@pytest.fixture
def session(tmp_path):
    """One image, a bias change, then a 5-scan spectroscopy run with a
    channel missing, a file deleted, a scan absent and an unlogged file."""
    d = tmp_path / "22-Jul-2026"
    d.mkdir()
    t = T0
    stream = [eepa(SNAPSHOT, t), mark("MTRX$SAMPLE_NAME-MnBi2Te4 665", t),
              mark("MTRX$ENABLE_RECORDING-I(V)", t)]
    # Image run 1: stopped after one line of the 4x4 up pass.
    for ch in ("I", "Z"):
        stream.append(bref(name(1, 1, ch), t + 10))
        data_file(d / name(1, 1, ch), recorded=8, expected=64)
    stream.append(pmod("GapVoltageControl.Voltage", -1.0, "Volt", t + 20))
    stream.append(mark("MTRX$STS_LOCATION-53,61;-1.4e-007,-1.36e-007"
                       "%%2800440043-7-12-0%%", t + 30))
    # Scan 1: both channels.
    for ch in ("I(V)", "Aux2(V)"):
        stream.append(bref(name(1, 1, ch), t + 31))
        data_file(d / name(1, 1, ch), recorded=16)
    stream.append(pmod("Regulator.Setpoint_1", 2e-10, "Ampere", t + 35))
    # Scan 2: I(V) never written.
    stream.append(bref(name(1, 2, "Aux2(V)"), t + 40))
    data_file(d / name(1, 2, "Aux2(V)"), recorded=16)
    # Scan 3: both logged, I(V) deleted from disk; Aux2(V) cut short.
    for ch in ("I(V)", "Aux2(V)"):
        stream.append(bref(name(1, 3, ch), t + 50))
    data_file(d / name(1, 3, "Aux2(V)"), recorded=10, expected=16)
    # Scan 4 absent; scan 5 on disk but never logged.
    for ch in ("I(V)", "Aux2(V)"):
        data_file(d / name(1, 5, ch), recorded=16, secs=t + 70)
    stream.append(eoed(t + 100))
    (d / f"{BASE}_0001.mtrx").write_bytes(MAGIC + b"".join(stream))
    return d


def _meas(inv, kind, run, scan):
    return next(m for m in inv["measurements"]
                if (m["kind"], m["run"], m["scan"]) == (kind, run, scan))


def _codes(m):
    return sorted((f["code"], f.get("channel")) for f in m.get("flags", []))


# ── Parsing helpers ──────────────────────────────────────────────────

def test_data_filename_parts():
    info = parse_data_filename(name(12, 3, "Aux2(V)"))
    assert info == {"base": BASE, "run": 12, "scan": 3,
                    "channel": "Aux2(V)", "kind": "spectroscopy"}
    assert parse_data_filename(name(4, 1, "Z"))["kind"] == "image"
    assert parse_data_filename(f"{BASE}_0001.mtrx") is None


def test_sts_location():
    loc = parse_sts_location("171,169;1.08108e-008,6.00601e-009"
                             "%%2a00440043-6-21-1%%")
    assert loc["px"] == [171, 169]
    assert loc["m"] == pytest.approx([1.08108e-08, 6.00601e-09])
    assert loc["image_ref"] == "2a00440043-6-21-1"


def test_check_data_file(tmp_path):
    ok, cut, short = (tmp_path / n for n in ("a", "b", "c"))
    data_file(ok, recorded=16)
    data_file(cut, recorded=10, expected=16)
    data_file(short, recorded=16, truncate=12)
    assert check_data_file(ok)["status"] == "ok"
    res = check_data_file(cut)
    assert res["status"] == "incomplete"
    assert (res["samples_recorded"], res["samples_expected"]) == (10, 16)
    assert check_data_file(short)["status"] == "truncated"
    (tmp_path / "d").write_bytes(b"not matrix")
    assert check_data_file(tmp_path / "d")["status"] == "unreadable"


# ── The session account ──────────────────────────────────────────────

def test_session_metadata(session):
    inv = build_session_inventory(BASE, session)
    s = inv["session"]
    assert s["sample_name"] == "MnBi2Te4 665"
    assert s["experiment_end"] is not None
    assert s["recording_channels"]["enabled"] == ["I(V)"]
    assert inv["flags"] == []          # closed normally, no gaps at run level
    assert inv["parameters"]["initial"]["GapVoltageControl"]["Voltage"] == {
        "value": 1.0, "unit": "Volt"}


def test_each_measurement_carries_its_parameters(session):
    inv = build_session_inventory(BASE, session)
    epochs = inv["parameter_epochs"]
    img = _meas(inv, "image", 1, 1)
    assert epochs[img["parameter_epoch"]]["values"][
        "GapVoltageControl.Voltage"] == 1.0
    s1 = _meas(inv, "spectroscopy", 1, 1)
    assert epochs[s1["parameter_epoch"]]["values"][
        "GapVoltageControl.Voltage"] == -1.0
    assert s1["location"]["px"] == [53, 61]
    # The setpoint changed between scans 1 and 2 of the run.
    s2 = _meas(inv, "spectroscopy", 1, 2)
    assert s2["changed_since_previous"] == {
        "Regulator.Setpoint_1": {"from": 1e-10, "to": 2e-10}}
    assert "changed_since_previous" not in s1   # first of its kind
    hist = [(h["param"], h["to"]) for h in inv["parameters"]["history"]]
    assert hist == [("GapVoltageControl.Voltage", -1.0),
                    ("Regulator.Setpoint_1", 2e-10)]


def test_missing_and_damaged_are_flagged(session):
    inv = build_session_inventory(BASE, session)
    assert "flags" not in _meas(inv, "spectroscopy", 1, 1)
    assert _codes(_meas(inv, "spectroscopy", 1, 2)) == [
        ("channel_missing", "I(V)")]
    assert _codes(_meas(inv, "spectroscopy", 1, 3)) == [
        ("file_missing", "I(V)"), ("incomplete", "Aux2(V)")]
    absent = _meas(inv, "spectroscopy", 1, 4)
    assert absent["status"] == "absent"
    assert _codes(absent) == [("scan_absent", None)]
    s5 = _meas(inv, "spectroscopy", 1, 5)
    assert _codes(s5) == [("not_in_header", "Aux2(V)"),
                          ("not_in_header", "I(V)")]
    assert s5["time_source"] == "data file"
    assert _meas(inv, "spectroscopy", 1, 3)["status"] == "error"


def test_stopped_image_is_info_with_line(session):
    inv = build_session_inventory(BASE, session)
    img = _meas(inv, "image", 1, 1)
    assert img["status"] == "info"
    details = {f["detail"] for f in img["flags"]}
    # 4x4 frame, both retraces → 64 samples; 8 recorded = 1 line of 4.
    assert details == {"up pass stopped at line 1 of 4 (12% of the frame)"}


def test_not_loaded_files_are_flagged(session):
    inv = build_session_inventory(BASE, session,
                                  not_loaded=[name(1, 1, "I(V)")])
    assert _codes(_meas(inv, "spectroscopy", 1, 1)) == [
        ("not_loaded", "I(V)")]


def test_summary_counts(session):
    sm = build_session_inventory(BASE, session)["summary"]
    assert sm["measurements"] == {"image": 1, "spectroscopy": 4}
    assert sm["files_on_disk"] == 8          # 7 logged + the unlogged scan 5 pair - 1 deleted
    assert sm["files_referenced_by_header"] == 7
    assert sm["measurements_by_severity"] == {
        "error": 1, "warning": 3, "info": 1}


# ── Session-level problems ───────────────────────────────────────────

def test_tracked_parameter_keeps_jumps_only(tmp_path):
    """Drift compensation rewrites the offset constantly; only the
    operator's move survives into the history, and each measurement gets
    the offset it was actually taken at."""
    stream = [eepa(SNAPSHOT)]
    x, t = 0.0, T0
    for i in range(300):
        x += 1e-12
        t += 1
        stream.append(pmod("XYScanner.X_Offset", x, "Meter", t))
        if i == 150:
            x += 5e-8                    # the operator moves the frame
            stream.append(pmod("XYScanner.X_Offset", x, "Meter", t))
        if i in (100, 250):
            stream.append(bref(name(1, 1 if i == 100 else 2, "I(V)"), t))
            data_file(tmp_path / name(1, 1 if i == 100 else 2, "I(V)"), 4)
    stream.append(eoed(t + 1))
    (tmp_path / f"{BASE}_0001.mtrx").write_bytes(MAGIC + b"".join(stream))

    inv = build_session_inventory(BASE, tmp_path)
    p = inv["parameters"]
    assert "XYScanner.X_Offset" in p["tracked"]
    assert "XYScanner.X_Offset" not in p["varying"]
    jumps = [h for h in p["history"] if h["param"] == "XYScanner.X_Offset"]
    assert len(jumps) == 1 and jumps[0]["tracked"]
    assert jumps[0]["to"] - jumps[0]["from"] == pytest.approx(5e-8)
    m1 = _meas(inv, "spectroscopy", 1, 1)
    m2 = _meas(inv, "spectroscopy", 1, 2)
    assert m1["tracked"]["XYScanner.X_Offset"] == pytest.approx(101e-12)
    assert m2["tracked"]["XYScanner.X_Offset"] == pytest.approx(
        251e-12 + 5e-8)
    # The constant drift does not split measurements into epochs.
    assert m1["parameter_epoch"] == m2["parameter_epoch"]


def test_header_chain_gap(session):
    (session / f"{BASE}_0003.mtrx").write_bytes(MAGIC)
    inv = build_session_inventory(BASE, session)
    assert [f["code"] for f in inv["flags"]] == ["header_chain_gap"]


def test_truncated_stream(session):
    h = session / f"{BASE}_0001.mtrx"
    h.write_bytes(h.read_bytes()[:-30])
    codes = {f["code"] for f in build_session_inventory(BASE, session)["flags"]}
    assert codes == {"stream_truncated", "no_end_marker"}


def test_no_header_builds_from_disk(session):
    (session / f"{BASE}_0001.mtrx").unlink()
    inv = build_session_inventory(BASE, session)
    assert [f["code"] for f in inv["flags"]] == ["header_missing"]
    s1 = _meas(inv, "spectroscopy", 1, 1)
    assert s1["time_source"] == "data file"
    # Without a header nothing is "not in header", and nothing can be missing.
    codes = {c for m in inv["measurements"] for c, _ in _codes(m)}
    assert not codes & {"not_in_header", "file_missing"}


def test_moved_file_is_found_elsewhere(session):
    other = session.parent / "23-Jul-2026"
    other.mkdir()
    moved = name(1, 1, "Aux2(V)")
    (session / moved).rename(other / moved)
    inv = build_session_inventory(BASE, session)
    assert _codes(_meas(inv, "spectroscopy", 1, 1)) == [
        ("file_elsewhere", "Aux2(V)")]
    assert inv["missing_files_found_elsewhere"] == {str(other): 1}
    # Truly gone stays an error.
    assert ("file_missing", "I(V)") in _codes(_meas(inv, "spectroscopy", 1, 3))


# ── Output ───────────────────────────────────────────────────────────

def test_write_inventory_round_trip(session, tmp_path):
    inv = build_session_inventory(BASE, session)
    jpath, tpath = write_inventory(inv, tmp_path / "out")
    assert jpath.name == f"{BASE}.inventory.json"
    back = json.loads(jpath.read_text(encoding="utf-8"))
    assert back["summary"] == inv["summary"]
    text = tpath.read_text(encoding="utf-8")
    assert "FLAGGED MEASUREMENTS" in text
    assert "file_missing I(V)" in text
    assert "GapVoltageControl.Voltage" in text


def test_folder_entry_point_covers_every_session(session):
    other = "default_2026Jul22-193426_STM-STM_Spectroscopy"
    data_file(session / f"{other}--1_1.Z_mtrx", recorded=4)
    bases = [i["session"]["base"] for i in build_inventories(session)]
    assert bases == [BASE, other]


def test_render_text_never_raises_on_minimal(session):
    inv = build_session_inventory(BASE, session, check_files=False)
    assert render_text(inv).startswith("═")


def test_recurring_automatic_steps_are_not_jumps(tmp_path):
    """Drift re-registration moves the frame by one pixel, hundreds of times
    a session. Those recur; the operator's move does not."""
    stream = [eepa(SNAPSHOT)]
    x, t = 0.0, T0
    for i in range(400):
        t += 1
        x += 4e-9 if i % 8 == 0 else 1e-12      # 50 pixel steps among ticks
        if i == 200:
            x += 1e-6                            # the operator's move
        stream.append(pmod("XYScanner.X_Offset", x, "Meter", t))
    stream.append(bref(name(1, 1, "I(V)"), t))
    data_file(tmp_path / name(1, 1, "I(V)"), 4)
    (tmp_path / f"{BASE}_0001.mtrx").write_bytes(MAGIC + b"".join(stream))

    inv = build_session_inventory(BASE, tmp_path)
    jumps = [h for h in inv["parameters"]["history"] if h.get("tracked")]
    assert len(jumps) == 1
    assert jumps[0]["to"] - jumps[0]["from"] == pytest.approx(1e-6, rel=0.01)
