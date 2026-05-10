"""
Tests for the WITec WIP loader (src/data_loaders/witec_wip_loader.py).

Synthetic-fixture tests build a tiny .wip file with controlled content and
verify the loader's grouping / DataFrame shape / image surfacing. Real-file
tests against ``Sheffield - UFMG/Raman/DtBuTPZ series.wip`` are skipped when
the file isn't present.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data_loaders.witec_wip_loader import WitecWipLoader
from src.models.image_data import ImageData
from src.models.spectral_data import SpectralData

# Reuse the byte-stream builder from the parser tests.
from tests.test_data_loaders.test_witec_wip_parser import WipBuilder


REAL_WIP = Path(
    "/Users/eduardapolicarpo/Documents/Doutorado/Sheffield - UFMG/"
    "Raman/DtBuTPZ series.wip"
)


# =============================================================================
# Builders for synthetic test files
# =============================================================================

def _add_spectral_transformation(
    b: WipBuilder, idx: int, transform_id: int,
    polynom: list, unit: str = "nm", caption: str = "Transform",
) -> None:
    b.add_string(f"DataClassName {idx}", "TDSpectralTransformation")
    d = b.begin_container(f"Data {idx}")
    tdata = b.begin_container("TData")
    b.add_int32("Version", 0)
    b.add_int32("ID", transform_id)
    b.add_int32("ImageIndex", 0)
    b.add_string("Caption", caption)
    b.end_container(tdata)
    tx = b.begin_container("TDTransformation")
    b.add_int32("Version", 0)
    b.add_string("StandardUnit", unit)
    b.add_int32("UnitKind", 2)
    b.add_int32("InterpretationID", 0)
    b.add_bool("IsCalibrated", True)
    b.end_container(tx)
    sx = b.begin_container("TDSpectralTransformation")
    b.add_int32("Version", 0)
    b.add_int32("SpectralTransformationType", 0)
    b.add_double_array("Polynom", polynom)
    b.add_int32("FreePolynomOrder", -1)
    b.end_container(sx)
    b.end_container(d)


def _add_graph(
    b: WipBuilder, idx: int, graph_id: int, transform_id: int,
    spectrum: np.ndarray, caption: str = "Spectrum",
    size_x: int = 1, size_y: int = 1,
) -> None:
    b.add_string(f"DataClassName {idx}", "TDGraph")
    d = b.begin_container(f"Data {idx}")
    tdata = b.begin_container("TData")
    b.add_int32("Version", 0)
    b.add_int32("ID", graph_id)
    b.add_int32("ImageIndex", 0)
    b.add_string("Caption", caption)
    b.end_container(tdata)
    g = b.begin_container("TDGraph")
    b.add_int32("Version", 1)
    b.add_int32("SizeX", size_x)
    b.add_int32("SizeY", size_y)
    b.add_int32("SizeGraph", spectrum.size if size_x * size_y == 1 else spectrum.shape[-1])
    b.add_int32("SpaceTransformationID", 0)
    b.add_int32("SecondaryTransformationID", 0)
    b.add_int32("XTransformationID", transform_id)
    b.add_int32("XInterpretationID", 0)
    b.add_int32("ZInterpretationID", 0)
    gd = b.begin_container("GraphData")
    b.add_int32("Dimension", 2)
    b.add_int32("DataType", 9)  # float32
    b.add_int32("Ranges", 0)
    b.add_blob("Data", spectrum.astype("<f4").tobytes())
    b.end_container(gd)
    b.end_container(g)
    b.end_container(d)


def _add_bitmap(
    b: WipBuilder, idx: int, bitmap_id: int,
    width: int, height: int, dtype_code: int,
    pixel_blob: bytes, caption: str = "Bitmap",
) -> None:
    """Add a TDBitmap with raw-pixel BitmapData (graph-style)."""
    b.add_string(f"DataClassName {idx}", "TDBitmap")
    d = b.begin_container(f"Data {idx}")
    tdata = b.begin_container("TData")
    b.add_int32("Version", 0)
    b.add_int32("ID", bitmap_id)
    b.add_int32("ImageIndex", 0)
    b.add_string("Caption", caption)
    b.end_container(tdata)
    tb = b.begin_container("TDBitmap")
    b.add_int32("Version", 0)
    b.add_int32("SpaceTransformationID", 0)
    b.add_int32("SecondaryTransformationID", 0)
    b.add_int32("SizeX", width)
    b.add_int32("SizeY", height)
    bd = b.begin_container("BitmapData")
    b.add_int32("Dimension", 2)
    b.add_int32("DataType", dtype_code)
    b.add_int32("Ranges", 0)
    b.add_blob("Data", pixel_blob)
    b.end_container(bd)
    b.end_container(tb)
    b.end_container(d)


def build_synthetic_wip(
    tmp_path: Path,
    spectra: list,
    bitmaps: list = None,
) -> Path:
    """Build a minimal .wip file with ``spectra`` (list of dicts) and
    optional ``bitmaps``. Returns the path."""
    bitmaps = bitmaps or []
    b = WipBuilder()
    root = b.begin_container("WITec Project")
    b.add_int32("Version", 7)
    data = b.begin_container("Data")

    idx = 0
    transforms_added = set()
    # Add unique spectral transformations first.
    for spec in spectra:
        tid = spec["transform_id"]
        if tid in transforms_added:
            continue
        _add_spectral_transformation(
            b, idx, tid, spec["polynom"], spec.get("unit", "nm"),
            caption=f"Transform_{tid}",
        )
        transforms_added.add(tid)
        idx += 1

    for spec in spectra:
        _add_graph(
            b, idx, spec["graph_id"], spec["transform_id"],
            spec["spectrum"], caption=spec.get("caption", "Spectrum"),
            size_x=spec.get("size_x", 1),
            size_y=spec.get("size_y", 1),
        )
        idx += 1

    for bm in bitmaps:
        _add_bitmap(
            b, idx, bm["bitmap_id"],
            bm["width"], bm["height"], bm["dtype_code"],
            bm["pixel_blob"], caption=bm.get("caption", "Bitmap"),
        )
        idx += 1

    b.end_container(data)
    b.end_container(root)
    out = tmp_path / "synth.wip"
    out.write_bytes(b.buffer)
    return out


# =============================================================================
# Loader unit tests (synthetic .wip files)
# =============================================================================

@pytest.fixture
def loader():
    return WitecWipLoader()


def test_loader_advertises_extension_and_type(loader):
    assert loader.supported_extensions == [".wip"]
    assert loader.loader_type == "witec_pl_raman"


@pytest.mark.parametrize("caption,expected", [
    # Verbose stitched-spectrum captions get reduced to the sample portion.
    ("Stitched Spectrum (461->629nm) DtBuTPZ Toluene 150 uW",
     "DtBuTPZ Toluene 150 uW"),
    ("Stitched Spectrum (461->841nm) DtBuTPZ:TPBI reg2 50x",
     "DtBuTPZ:TPBI reg2 50x"),
    ("Stitched Spectrum (461->841nm)", ""),
    # Single Spectrum boilerplate.
    ("Single Spectrum_107_Spec.Data 1", ""),
    # Plain "Spectrum 4" → empty (fallback path keeps the raw caption).
    ("Spectrum 4", ""),
    # Nothing to strip.
    ("DtBuTPZ Chloroform Sample A", "DtBuTPZ Chloroform Sample A"),
])
def test_clean_caption_strips_witec_boilerplate(loader, caption, expected):
    assert loader._clean_caption(caption) == expected


def test_witec_column_names_use_clean_caption(tmp_path, loader):
    """Real-world captions should produce concise column names."""
    spec = np.zeros(5, dtype=np.float32)
    f = build_synthetic_wip(tmp_path, [
        {"graph_id": 11, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": spec,
         "caption": "Stitched Spectrum (461->629nm) DtBuTPZ Toluene 150 uW"},
        {"graph_id": 12, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": spec,
         "caption": "Stitched Spectrum (461->629nm) DtBuTPZ:TPBI reg1 50x"},
    ])
    sd = loader.load_single_file(f)
    cols = list(sd.data.columns)
    assert "DtBuTPZ Toluene 150 uW" in cols
    assert "DtBuTPZ:TPBI reg1 50x" in cols


def test_load_single_spectrum(tmp_path, loader):
    """Single TDGraph with 5 bins → DataFrame with 1 column + axis."""
    spectrum = np.array([10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float32)
    f = build_synthetic_wip(tmp_path, [{
        "graph_id": 11, "transform_id": 10,
        "polynom": [400.0, 1.0, 0.0],   # axis: 400, 401, 402, 403, 404
        "spectrum": spectrum,
        "caption": "Test Spectrum",
        "unit": "nm",
    }])
    sd = loader.load_single_file(f)
    assert isinstance(sd, SpectralData)
    assert sd.num_spectra == 1
    assert sd.num_points == 5
    # First column carries the wavelength axis.
    assert sd.independent_var_name == "Wavelength_nm"
    assert np.allclose(sd.independent_var, [400, 401, 402, 403, 404])
    # Spectrum column is named after the caption.
    assert "Test Spectrum" in sd.data.columns
    assert np.allclose(sd.data["Test Spectrum"], spectrum)


def test_two_spectra_same_axis_merge_into_one_channel(tmp_path, loader):
    """Spectra sharing an axis become two columns of the same DataFrame."""
    s1 = np.array([1, 2, 3, 4, 5], dtype=np.float32)
    s2 = np.array([5, 4, 3, 2, 1], dtype=np.float32)
    f = build_synthetic_wip(tmp_path, [
        {"graph_id": 11, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": s1, "caption": "A"},
        {"graph_id": 12, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": s2, "caption": "B"},
    ])
    sd = loader.load_single_file(f)
    assert sd.num_spectra == 2
    assert "A" in sd.data.columns and "B" in sd.data.columns
    # No extra channels — only one axis present.
    extra = sd.metadata.additional_info.get("channels", {})
    assert len(extra) == 1


def test_two_spectra_different_axes_split_into_channels(tmp_path, loader):
    """Spectra with distinct spectral axes appear as separate channels."""
    s_short = np.arange(5, dtype=np.float32)
    s_long = np.arange(8, dtype=np.float32)
    f = build_synthetic_wip(tmp_path, [
        {"graph_id": 11, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": s_short, "caption": "Short"},
        {"graph_id": 12, "transform_id": 20,
         "polynom": [600.0, 2.0, 0.0], "spectrum": s_long, "caption": "Long"},
    ])
    sd = loader.load_single_file(f)
    channels = sd.metadata.additional_info["channels"]
    assert len(channels) == 2
    # Channel names encode the axis range + unit.
    keys = sorted(channels.keys())
    assert any("400" in k and "404" in k for k in keys)
    assert any("600" in k and "614" in k for k in keys)
    # Each channel has exactly one spectrum.
    for ch in channels.values():
        assert ch.num_spectra == 1


def test_duplicate_captions_get_disambiguated(tmp_path, loader):
    """Two spectra with identical captions must end up as separate columns."""
    s1 = np.ones(5, dtype=np.float32)
    s2 = np.ones(5, dtype=np.float32) * 2
    f = build_synthetic_wip(tmp_path, [
        {"graph_id": 11, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": s1, "caption": "Same"},
        {"graph_id": 12, "transform_id": 10,
         "polynom": [400.0, 1.0, 0.0], "spectrum": s2, "caption": "Same"},
    ])
    sd = loader.load_single_file(f)
    assert sd.num_spectra == 2
    # Two distinct column names referencing "Same".
    cols = [c for c in sd.data.columns if "Same" in c]
    assert len(cols) == 2


def test_bitmap_surfaced_as_image_metadata(tmp_path, loader):
    """A TDBitmap entry should appear in metadata.additional_info['images']."""
    spectrum = np.zeros(5, dtype=np.float32)
    bm = (np.arange(8 * 6) % 256).astype(np.uint8).reshape(8, 6)
    f = build_synthetic_wip(
        tmp_path,
        [{"graph_id": 11, "transform_id": 10,
          "polynom": [400.0, 1.0, 0.0], "spectrum": spectrum, "caption": "S"}],
        bitmaps=[{
            "bitmap_id": 99, "width": 6, "height": 8,
            "dtype_code": 1,  # uint8
            "pixel_blob": bm.tobytes(),
            "caption": "Optical Preview",
        }],
    )
    sd = loader.load_single_file(f)
    images = sd.metadata.additional_info.get("images")
    assert images is not None
    names = [n for n, _ in images]
    assert "Optical Preview" in names
    img = next(im for n, im in images if n == "Optical Preview")
    assert isinstance(img, ImageData)
    assert img.shape == (8, 6)
    assert np.array_equal(img.array, bm)


def test_unknown_transformation_falls_back_to_bin_axis(tmp_path, loader):
    """Spectrum referencing a non-existent transform must still load."""
    spectrum = np.array([1, 2, 3], dtype=np.float32)
    # Reference transform_id 999 but never define it.
    b = WipBuilder()
    root = b.begin_container("WITec Project")
    b.add_int32("Version", 7)
    data = b.begin_container("Data")
    _add_graph(b, 0, 11, 999, spectrum, caption="Orphan")
    b.end_container(data)
    b.end_container(root)
    f = tmp_path / "orphan.wip"
    f.write_bytes(b.buffer)

    sd = loader.load_single_file(f)
    assert sd.num_spectra == 1
    # Unit fallback is "bin" → column name is "Variable" (from sanitizer).
    assert sd.independent_var_name == "X_bin"
    # Axis is just the bin index 0,1,2.
    assert np.array_equal(sd.independent_var, [0, 1, 2])


def test_empty_wip_raises(tmp_path, loader):
    """A .wip with no spectra and no maps should raise a clear error."""
    b = WipBuilder()
    root = b.begin_container("WITec Project")
    b.add_int32("Version", 7)
    b.begin_container("Data")
    # End immediately — no children.
    b._patch_offsets(13, 0, 0)  # we don't care about exact patches
    b.end_container(root)
    f = tmp_path / "empty.wip"
    f.write_bytes(b.buffer)
    with pytest.raises(ValueError):
        loader.load_single_file(f)


def test_wrong_extension_handling_via_directory(tmp_path, loader):
    """load_from_directory must surface a ValueError when no .wip present."""
    with pytest.raises(ValueError):
        loader.load_from_directory(tmp_path)


# =============================================================================
# Real-file regression tests (skip if absent)
# =============================================================================

@pytest.fixture(scope="module")
def real_load():
    if not REAL_WIP.exists():
        pytest.skip(f"Real WIP file not available at {REAL_WIP}")
    return WitecWipLoader().load_single_file(REAL_WIP)


def test_real_file_loads_seven_spectra(real_load):
    """The DtBuTPZ test file should expose 7 spectra split across channels."""
    channels = real_load.metadata.additional_info["channels"]
    total = sum(ch.num_spectra for ch in channels.values())
    assert total == 7


def test_real_file_channels_have_consistent_units(real_load):
    """All seven spectra are recorded in nm, so every channel uses nm."""
    channels = real_load.metadata.additional_info["channels"]
    for name, ch in channels.items():
        first_col = ch.independent_var_name
        assert first_col.endswith("_nm"), (
            f"Channel {name!r} first column is {first_col!r} (not nm)"
        )


def test_real_file_axis_starts_around_461nm(real_load):
    """Most stitched spectra start near 461 nm (visible-range PL)."""
    channels = real_load.metadata.additional_info["channels"]
    found_461 = False
    for ch in channels.values():
        first_val = float(ch.independent_var[0])
        if 455 <= first_val <= 470:
            found_461 = True
            break
    assert found_461, "Expected at least one channel starting near 461 nm"


def test_real_file_surfaces_images(real_load):
    """At least the project thumbnail and one TDBitmap should surface."""
    images = real_load.metadata.additional_info.get("images") or []
    assert len(images) >= 1
    # At least one image must be tagged as the WIP source.
    sources = [img.metadata.source for _, img in images]
    assert any(s == "witec_wip_bitmap" for s in sources)
