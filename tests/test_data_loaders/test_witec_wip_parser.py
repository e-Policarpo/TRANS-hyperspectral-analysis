"""
Tests for the WITec WIP binary parser.

Two layers of coverage:

1. Synthetic-bytes tests construct a tiny .wip-shaped buffer and assert that
   each low-level helper (read_tag, iter_children, type decoders) and the
   high-level parse_wip behave correctly. These run on every CI machine.

2. Real-file tests against ``Sheffield - UFMG/Raman/DtBuTPZ series.wip``.
   These are skipped when the file is not present so unrelated dev machines
   don't fail.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from src.data_loaders.witec_wip.wip_parser import (
    WIP_MAGIC,
    TYPE_CONTAINER,
    TYPE_FLOAT64,
    TYPE_INT32,
    TYPE_BLOB,
    TYPE_BOOL,
    TYPE_STRING,
    WipDataEntry,
    WipParseError,
    WipSpectralTransformation,
    iter_children,
    parse_wip,
    read_blob,
    read_bool,
    read_double,
    read_double_array,
    read_int,
    read_string,
    read_tag,
    synthesize_bmp_filebytes,
)


def _resolve_real_wip() -> Path:
    """Find the user's WITec test file across known locations."""
    candidates = [
        # Current location; the two below are where it used to live.
        Path("/Users/eduardapolicarpo/Documents/Doutorado/Colab Sheffield/"
             "PL/DtBuTPZ series.wip"),
        Path("/Users/eduardapolicarpo/Documents/Doutorado/Sheffield - UFMG/"
             "Raman/DtBuTPZ series.wip"),
        Path("/Users/eduardapolicarpo/Documents/Doutorado/Colab Sheffield - UFMG/"
             "Raman/DtBuTPZ series.wip"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # used in skip message


REAL_WIP = _resolve_real_wip()


# =============================================================================
# Synthetic byte stream builder
# =============================================================================

class WipBuilder:
    """Builds a valid .wip byte stream tag-by-tag.

    Each call to ``add_*`` appends a tag header + body and returns the body
    range so callers can verify offsets if they want. The builder rewrites
    the parent's data_end after children are added.
    """

    def __init__(self) -> None:
        self._buf = bytearray(WIP_MAGIC)

    @property
    def buffer(self) -> bytes:
        return bytes(self._buf)

    def _write_tag_header(self, name: str, type_code: int) -> int:
        """Write a tag header with placeholder data_start/data_end. Returns
        offset of the data_end field for later patching."""
        name_bytes = name.encode("ascii")
        self._buf += struct.pack("<I", len(name_bytes))
        self._buf += name_bytes
        self._buf += struct.pack("<I", type_code)
        ds_offset = len(self._buf)
        self._buf += struct.pack("<Q", 0)  # data_start placeholder
        self._buf += struct.pack("<Q", 0)  # data_end placeholder
        return ds_offset

    def _patch_offsets(self, ds_offset: int, ds: int, de: int) -> None:
        struct.pack_into("<Q", self._buf, ds_offset, ds)
        struct.pack_into("<Q", self._buf, ds_offset + 8, de)

    def add_int32(self, name: str, value: int) -> None:
        ds_off = self._write_tag_header(name, TYPE_INT32)
        ds = len(self._buf)
        self._buf += struct.pack("<i", value)
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def add_double(self, name: str, value: float) -> None:
        ds_off = self._write_tag_header(name, TYPE_FLOAT64)
        ds = len(self._buf)
        self._buf += struct.pack("<d", value)
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def add_double_array(self, name: str, values) -> None:
        ds_off = self._write_tag_header(name, TYPE_FLOAT64)
        ds = len(self._buf)
        for v in values:
            self._buf += struct.pack("<d", v)
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def add_bool(self, name: str, value: bool) -> None:
        ds_off = self._write_tag_header(name, TYPE_BOOL)
        ds = len(self._buf)
        self._buf += struct.pack("<B", 1 if value else 0)
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def add_string(self, name: str, value: str) -> None:
        ds_off = self._write_tag_header(name, TYPE_STRING)
        ds = len(self._buf)
        encoded = value.encode("latin-1")
        self._buf += struct.pack("<I", len(encoded))
        self._buf += encoded
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def add_blob(self, name: str, blob: bytes) -> None:
        ds_off = self._write_tag_header(name, TYPE_BLOB)
        ds = len(self._buf)
        self._buf += blob
        de = len(self._buf)
        self._patch_offsets(ds_off, ds, de)

    def begin_container(self, name: str) -> int:
        """Open a container; returns the data_end offset to patch on close."""
        ds_off = self._write_tag_header(name, TYPE_CONTAINER)
        ds = len(self._buf)
        struct.pack_into("<Q", self._buf, ds_off, ds)
        return ds_off

    def end_container(self, ds_off: int) -> None:
        de = len(self._buf)
        struct.pack_into("<Q", self._buf, ds_off + 8, de)


def _build_minimal_project() -> bytes:
    """Build a tiny .wip with one TDGraph and its TDSpectralTransformation."""
    b = WipBuilder()
    root = b.begin_container("WITec Project")

    b.add_int32("Version", 7)

    # ---- Data block with two entries: TDSpectralTransformation, TDGraph
    data = b.begin_container("Data")

    # DataClassName 0 / Data 0 — TDSpectralTransformation (id=10)
    b.add_string("DataClassName 0", "TDSpectralTransformation")
    d0 = b.begin_container("Data 0")
    tdata0 = b.begin_container("TData")
    b.add_int32("Version", 0)
    b.add_int32("ID", 10)
    b.add_int32("ImageIndex", 0)
    b.add_string("Caption", "Synthetic Spectral Transform")
    b.end_container(tdata0)
    tx = b.begin_container("TDTransformation")
    b.add_int32("Version", 0)
    b.add_string("StandardUnit", "nm")
    b.add_int32("UnitKind", 2)
    b.add_int32("InterpretationID", 0)
    b.add_bool("IsCalibrated", True)
    b.end_container(tx)
    sx = b.begin_container("TDSpectralTransformation")
    b.add_int32("Version", 0)
    b.add_int32("SpectralTransformationType", 0)
    b.add_double_array("Polynom", [400.0, 1.0, 0.0])  # axis = 400 + i
    b.add_int32("FreePolynomOrder", -1)
    b.end_container(sx)
    b.end_container(d0)

    # DataClassName 1 / Data 1 — TDGraph (5-bin float32 spectrum)
    b.add_string("DataClassName 1", "TDGraph")
    d1 = b.begin_container("Data 1")
    tdata1 = b.begin_container("TData")
    b.add_int32("Version", 0)
    b.add_int32("ID", 11)
    b.add_int32("ImageIndex", 0)
    b.add_string("Caption", "Synthetic Spectrum")
    b.end_container(tdata1)
    g = b.begin_container("TDGraph")
    b.add_int32("Version", 1)
    b.add_int32("SizeX", 1)
    b.add_int32("SizeY", 1)
    b.add_int32("SizeGraph", 5)
    b.add_int32("SpaceTransformationID", 0)
    b.add_int32("SecondaryTransformationID", 0)
    b.add_int32("XTransformationID", 10)
    b.add_int32("XInterpretationID", 0)
    b.add_int32("ZInterpretationID", 0)
    gd = b.begin_container("GraphData")
    b.add_int32("Dimension", 2)
    b.add_int32("DataType", 9)  # float32
    b.add_int32("Ranges", 0)
    samples = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype="<f4")
    b.add_blob("Data", samples.tobytes())
    b.end_container(gd)
    b.end_container(g)
    b.end_container(d1)

    b.end_container(data)
    b.end_container(root)
    return b.buffer


# =============================================================================
# Low-level helpers
# =============================================================================

def test_read_tag_decodes_header():
    raw = _build_minimal_project()
    tag = read_tag(raw, 8)
    assert tag.name == "WITec Project"
    assert tag.type_code == TYPE_CONTAINER
    assert tag.data_start > 8
    assert tag.data_end <= len(raw)


def test_iter_children_walks_siblings():
    raw = _build_minimal_project()
    root = read_tag(raw, 8)
    names = [c.name for c in iter_children(raw, root.data_start, root.data_end)]
    assert names == ["Version", "Data"]


def test_read_string_decodes_length_prefixed_ascii():
    b = WipBuilder()
    root = b.begin_container("Root")
    b.add_string("Greeting", "hello world")
    b.end_container(root)
    raw = b.buffer
    rt = read_tag(raw, 8)
    children = list(iter_children(raw, rt.data_start, rt.data_end))
    assert read_string(raw, children[0]) == "hello world"


def test_read_int_handles_4_and_8_byte_widths():
    b = WipBuilder()
    root = b.begin_container("Root")
    b.add_int32("Small", 42)
    # Manually add an 8-byte int32-typed tag.
    ds_off = b._write_tag_header("Big", TYPE_INT32)
    ds = len(b._buf)
    b._buf += struct.pack("<q", -1234567890123)
    de = len(b._buf)
    b._patch_offsets(ds_off, ds, de)
    b.end_container(root)
    raw = b.buffer
    rt = read_tag(raw, 8)
    children = list(iter_children(raw, rt.data_start, rt.data_end))
    assert read_int(raw, children[0]) == 42
    assert read_int(raw, children[1]) == -1234567890123


def test_read_double_array_returns_correct_count():
    b = WipBuilder()
    root = b.begin_container("Root")
    b.add_double_array("Coeffs", [1.5, 2.5, 3.5])
    b.end_container(root)
    raw = b.buffer
    rt = read_tag(raw, 8)
    coeffs_tag = next(iter_children(raw, rt.data_start, rt.data_end))
    arr = read_double_array(raw, coeffs_tag)
    assert arr.dtype == np.float64
    assert np.allclose(arr, [1.5, 2.5, 3.5])


def test_read_blob_returns_bytes():
    b = WipBuilder()
    root = b.begin_container("Root")
    b.add_blob("Payload", b"\x00\x01\x02\x03")
    b.end_container(root)
    raw = b.buffer
    rt = read_tag(raw, 8)
    blob_tag = next(iter_children(raw, rt.data_start, rt.data_end))
    assert read_blob(raw, blob_tag) == b"\x00\x01\x02\x03"


def test_read_bool_decodes_single_byte():
    b = WipBuilder()
    root = b.begin_container("Root")
    b.add_bool("On", True)
    b.add_bool("Off", False)
    b.end_container(root)
    raw = b.buffer
    rt = read_tag(raw, 8)
    on, off = list(iter_children(raw, rt.data_start, rt.data_end))
    assert read_bool(raw, on) is True
    assert read_bool(raw, off) is False


def test_truncated_buffer_raises():
    raw = _build_minimal_project()[:50]  # cut after only a partial header
    with pytest.raises(WipParseError):
        read_tag(raw, 8)


def test_missing_magic_raises(tmp_path):
    bogus = tmp_path / "bogus.wip"
    bogus.write_bytes(b"NOT_A_WIP_FILE_AT_ALL")
    with pytest.raises(WipParseError):
        parse_wip(bogus)


# =============================================================================
# parse_wip on the synthetic project
# =============================================================================

def test_parse_synthetic_project(tmp_path):
    raw = _build_minimal_project()
    f = tmp_path / "synth.wip"
    f.write_bytes(raw)

    project = parse_wip(f)

    assert project.version == 7
    # 2 entries (the spectral transformation + the graph).
    assert len(project.entries) == 2
    assert {e.class_name for e in project.entries} == {
        "TDSpectralTransformation", "TDGraph",
    }
    assert len(project.graphs) == 1
    g = project.graphs[0]
    assert g.size_x == 1 and g.size_y == 1 and g.size_graph == 5
    assert g.x_transformation_id == 10
    assert g.data.dtype == np.float32
    assert np.allclose(g.data[0, 0], [10, 20, 30, 40, 50])

    # The spectral transformation should be looked up by id.
    st = project.get_spectral_transformation(10)
    assert st is not None
    assert st.standard_unit == "nm"
    assert st.is_calibrated is True
    axis = st.axis(g.size_graph)
    # c0=400, c1=1, c2=0 → axis = 400, 401, 402, 403, 404
    assert np.allclose(axis, [400.0, 401.0, 402.0, 403.0, 404.0])


def test_unknown_data_class_does_not_break_parser(tmp_path):
    """A future class we don't model should be recorded but skipped."""
    b = WipBuilder()
    root = b.begin_container("WITec Project")
    b.add_int32("Version", 7)
    data = b.begin_container("Data")
    b.add_string("DataClassName 0", "TDSomeFuturisticClass")
    d0 = b.begin_container("Data 0")
    tdata = b.begin_container("TData")
    b.add_int32("ID", 99)
    b.add_string("Caption", "Mystery Data")
    b.end_container(tdata)
    payload = b.begin_container("TDSomeFuturisticClass")
    b.add_int32("Whatever", 1)
    b.end_container(payload)
    b.end_container(d0)
    b.end_container(data)
    b.end_container(root)

    f = tmp_path / "future.wip"
    f.write_bytes(b.buffer)
    project = parse_wip(f)
    assert len(project.entries) == 1
    assert project.entries[0].class_name == "TDSomeFuturisticClass"
    # No graphs/bitmaps/transformations expected.
    assert project.graphs == []


# =============================================================================
# BMP file-header synthesis
# =============================================================================

def test_synthesize_bmp_filebytes_for_24bpp_dib():
    """A 1×1 24-bpp DIB without color table should produce a valid BMP file."""
    info_header = struct.pack(
        "<IiiHHIIiiII",
        40,           # biSize
        1, 1,         # biWidth, biHeight
        1, 24,        # biPlanes, biBitCount
        0, 4,         # biCompression, biSizeImage
        2835, 2835,   # biXPelsPerMeter, biYPelsPerMeter
        0, 0,         # biClrUsed, biClrImportant
    )
    pixel = b"\xff\x00\x00\x00"  # one BGR pixel (BGR=blue) + 1-byte row pad
    blob = info_header + pixel
    file_bytes = synthesize_bmp_filebytes(blob)
    assert file_bytes.startswith(b"BM")
    # File size is field at offset 2.
    file_size = struct.unpack_from("<I", file_bytes, 2)[0]
    assert file_size == len(file_bytes)
    # Pixel offset is field at offset 10; should equal 14 + info_header size.
    pixel_offset = struct.unpack_from("<I", file_bytes, 10)[0]
    assert pixel_offset == 14 + 40


# =============================================================================
# Real-file regression tests (skip if the dev machine doesn't have the file)
# =============================================================================

@pytest.fixture(scope="module")
def real_project():
    if not REAL_WIP.exists():
        pytest.skip(f"Real WIP file not available at {REAL_WIP}")
    return parse_wip(REAL_WIP)


def test_real_file_has_seven_graphs(real_project):
    assert len(real_project.graphs) == 7


def test_real_file_graph_lengths(real_project):
    expected = sorted([2020, 1600, 2020, 4740, 4740, 4740, 4740])
    actual = sorted(g.size_graph for g in real_project.graphs)
    assert actual == expected


def test_real_file_all_single_point(real_project):
    """No hyperspectral maps in this particular file."""
    for g in real_project.graphs:
        assert g.is_single_spectrum, (
            f"{g.entry.caption!r}: SizeX×SizeY = {g.size_x}×{g.size_y}"
        )


def test_real_file_units_are_nm(real_project):
    for g in real_project.graphs:
        st = real_project.get_spectral_transformation(g.x_transformation_id)
        assert st is not None, (
            f"Graph {g.entry.caption!r} references unknown transform "
            f"id {g.x_transformation_id}"
        )
        assert st.standard_unit == "nm"


def test_real_file_axis_first_sample_in_visible_range(real_project):
    """The 461nm-starting captions should produce axis values near 461."""
    for g in real_project.graphs:
        if "461->629" not in g.entry.caption and "461->841" not in g.entry.caption:
            continue
        st = real_project.get_spectral_transformation(g.x_transformation_id)
        axis = st.axis(g.size_graph)
        assert 450 <= axis[0] <= 470, (
            f"Axis start {axis[0]} for {g.entry.caption!r} "
            "is outside expected range"
        )


def _make_spectral_transform(*, transformation_type, polynom,
                              free_polynom_order=-1, standard_unit="nm"):
    """Shortcut for unit-testing ``WipSpectralTransformation.axis()`` without
    going through the parser."""
    return WipSpectralTransformation(
        entry=WipDataEntry(index=0, class_name="TDSpectralTransformation", id=0, caption=""),
        transformation_type=transformation_type,
        polynom=np.asarray(polynom, dtype=np.float64),
        free_polynom_order=free_polynom_order,
        standard_unit=standard_unit,
        unit_kind=0,
        is_calibrated=True,
    )


def test_spectral_transformation_type0_polynomial_axis():
    """Type 0 stays a polynomial — regression guard for the existing path."""
    st = _make_spectral_transform(transformation_type=0,
                                  polynom=[400.0, 1.0, 0.0])
    axis = st.axis(5)
    assert np.allclose(axis, [400.0, 401.0, 402.0, 403.0, 404.0])


def test_spectral_transformation_type2_lut_axis():
    """Type 2 with Polynom.size == n_bins is a direct lookup table.

    Previously the loader fell back to bin indices for any non-zero
    transformation type, so spectra came in labelled ``nm`` but indexed
    0..N-1. The fix: when ``Polynom`` matches ``n_bins`` the array IS the
    axis.
    """
    lut = np.linspace(461.0, 841.0, 1600)
    st = _make_spectral_transform(transformation_type=2, polynom=lut.tolist(),
                                   standard_unit="nm")
    axis = st.axis(1600)
    np.testing.assert_allclose(axis, lut)
    # First sample should be in the visible-light range, not 0.
    assert axis[0] > 100.0


def test_spectral_transformation_unknown_type_falls_back_to_polynomial():
    """An unknown transformation type with a short Polynom array is treated
    as a polynomial rather than discarded — better to surface *something*
    than to silently return bin indices."""
    st = _make_spectral_transform(transformation_type=7,
                                  polynom=[500.0, 0.5])
    axis = st.axis(4)
    assert np.allclose(axis, [500.0, 500.5, 501.0, 501.5])


def test_spectral_transformation_empty_polynom_returns_bins():
    st = _make_spectral_transform(transformation_type=2, polynom=[])
    axis = st.axis(5)
    np.testing.assert_array_equal(axis, np.arange(5, dtype=np.float64))


def test_real_file_has_bitmaps(real_project):
    """The DtBuTPZ project includes optical/preview bitmaps."""
    assert len(real_project.bitmaps) > 0
    for bm in real_project.bitmaps:
        assert bm.array is not None, (
            f"Bitmap {bm.entry.caption!r} did not decode into a numpy array"
        )
        assert bm.width > 0 and bm.height > 0


def test_real_file_thumbnail_decodes(real_project):
    """The project thumbnail decodes into an RGB numpy array."""
    if real_project.thumbnail is None:
        pytest.skip("File has no thumbnail")
    thumb = real_project.thumbnail
    assert thumb.source == "dib"
    assert thumb.array is not None
    assert thumb.array.ndim == 3
    assert thumb.array.shape[2] in (3, 4)
    assert thumb.array.shape[0] == thumb.height
    assert thumb.array.shape[1] == thumb.width
    assert thumb.array.dtype == np.uint8


def test_real_file_video_image_decodes_as_array(real_project):
    """The optical 'Video Image' TDBitmap is a raw 2D array (e.g. uint16)."""
    candidates = [bm for bm in real_project.bitmaps if bm.source == "raw"]
    assert candidates, "Expected at least one raw-pixel TDBitmap entry"
    bm = candidates[0]
    assert bm.array is not None
    # BGRA bitmaps decode to (H, W, 3); single-channel to (H, W).
    assert bm.array.shape[:2] == (bm.height, bm.width)
    assert bm.data_type_code in (1, 2, 3, 4, 5, 6, 7, 9, 10)


def test_real_file_extracts_excitation_wavelength(real_project):
    """ExcitationWaveLength from TDSpectralInterpretation is captured."""
    assert real_project.excitation_wavelength_nm is not None
    # DtBuTPZ file uses ~457 nm Ar+ laser.
    assert 450 < real_project.excitation_wavelength_nm < 470


def test_real_file_extracts_space_cursor(real_project):
    """At least one TDSpaceCursor in the file."""
    assert len(real_project.space_cursors) >= 1
    c = real_project.space_cursors[0]
    assert c.standard_unit in ("µm", "um")
    assert len(c.positions) >= 1
    x, y, z = c.positions[0]
    assert x != 0 or y != 0  # non-trivial position


def test_real_file_extracts_spectral_cursor(real_project):
    """TDSpectralCursor position recovered as a wavelength."""
    assert len(real_project.spectral_cursors) >= 1
    c = real_project.spectral_cursors[0]
    assert c.standard_unit == "nm"
    assert c.positions and 400 < c.positions[0] < 900


def test_real_file_extracts_color_profile(real_project):
    """TDColorProfile palette decoded into an N×4 uint8 LUT."""
    assert len(real_project.color_profiles) >= 1
    cp = real_project.color_profiles[0]
    assert cp.colors.ndim == 2 and cp.colors.shape[1] == 4
    assert cp.colors.dtype == np.uint8


def test_real_file_extracts_system_info(real_project):
    """SystemInformation block exposed (software version, system id)."""
    si = real_project.system_info
    assert si.application_versions
    assert "Control FIVE" in si.application_versions[0]
    assert si.system_id  # non-empty


def test_real_file_tdtext_has_rtf_body(real_project):
    """TDText entries surface RTF stream content (not just captions)."""
    texts_with_body = [t for t in real_project.texts if t.text]
    assert texts_with_body
    assert any(len(t.rtf_bytes) > 100 for t in real_project.texts)
    # Plain-text strip pulled WITec metadata strings.
    bodies = " ".join(t.text for t in texts_with_body)
    assert "System ID" in bodies or "Start Time" in bodies


def test_real_file_space_transformation_calibrated(real_project):
    """At least one TDSpaceTransformation is calibrated with non-trivial scale."""
    for tid, st in real_project.space_transformations.items():
        if not st.is_calibrated:
            continue
        dx, dy = st.pixel_size_world
        if dx > 0 and dy > 0:
            return
    raise AssertionError("No calibrated space transformation with non-zero pixel size")
