"""
Tests for AppBackend.getDatasetOverlaysForImage (Feature B).

Drives the slot with hand-built ImageData and SpectralData fixtures so we
don't need a real .wip file. Verifies:
- compatibility match by ``wip_source_stem`` vs the image's filename stem,
- pixel-coord computation through the stashed affine,
- in-bounds filtering,
- silent skip of uncalibrated entries / mismatched stems.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Headless Qt — exportImageWithOverlays needs a QApplication for signals.
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.image_data import ImageData, ImageMetadata, ImageMode
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True, scope="module")
def _preserve_probe_offset(qapp):
    """Restore the user's persisted WITec probe offset after the module.

    These tests need to mutate the calibration to assert behavior, but
    the value lives in ``~/.trans_qml/preferences.json`` and would
    otherwise stick across sessions. Snapshot before, restore after.
    """
    snap = AppBackend()
    saved_dx = snap.preferencesManager.getProbeOffsetX()
    saved_dy = snap.preferencesManager.getProbeOffsetY()
    yield
    restore = AppBackend()
    restore.preferencesManager.setProbeOffset(saved_dx, saved_dy)


def _calibrated_image(
    name: str, source_stem: str, w: int = 100, h: int = 80,
    dx: float = 1.0, dy: float = 1.0,
    world_origin=(0.0, 0.0), flip_y: bool = True,
    wip_data_id: int = 1,
) -> ImageData:
    """Axis-aligned image whose pixel (px, py) → world (origin_x + px*dx, …).

    ``flip_y=True`` mirrors WITec, where the y axis grows downward in pixel
    space but increases upward in world µm. ``wip_data_id`` simulates
    WITec's monotonic per-acquisition entry IDs used for parent-image
    matching.
    """
    arr = np.zeros((h, w), dtype=np.uint8)
    sy = -dy if flip_y else dy
    meta = ImageMetadata(
        source="witec_wip_bitmap",
        original_filename=f"{source_stem}.wip",
        additional_info={
            "wip_data_id": int(wip_data_id),
            "space_transformation_affine": {
                "world_origin_xy": [float(world_origin[0]), float(world_origin[1])],
                "model_origin_xy": [0.0, 0.0],
                "forward_2x2": [[dx, 0.0], [0.0, sy]],
                "space_transformation_id": 42,
                "unit": "µm",
            },
            "world_bounds": {
                "x_min": float(world_origin[0]),
                "x_max": float(world_origin[0] + w * dx),
                "y_min": float(world_origin[1] - h * dy) if flip_y else float(world_origin[1]),
                "y_max": float(world_origin[1]) if flip_y else float(world_origin[1] + h * dy),
                "unit": "µm",
            },
        },
    )
    return ImageData(array=arr, mode=ImageMode.GRAY_U8, metadata=meta, name=name)


def _spectra_dataset(
    source_stem: str, captions, positions,
) -> SpectralData:
    """Bundle ``len(captions)`` single-point spectra into one SpectralData.

    Each ``positions`` entry should carry ``wip_data_id`` so the backend
    can perform acquisition-order parent matching.
    """
    df = pd.DataFrame(
        {"x": [400.0, 500.0]} | {c: [1.0, 2.0] for c in captions}
    )
    meta = SpectralMetadata(
        source_type="witec_pl_raman", dimensions=(len(captions), 2),
        scan_mode="point", units={"x": "nm", "y": "counts"},
        additional_info={
            "captions": list(captions),
            "acquisition_positions": list(positions),
            "wip_source_stem": source_stem,
            "axis_unit": "nm",
        },
    )
    return SpectralData(df, meta)


def test_in_bounds_spectra_become_overlays(qapp):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    img = _calibrated_image("Map", "ses1", w=100, h=80, dx=1.0, dy=1.0,
                            world_origin=(0.0, 80.0), wip_data_id=10)
    backend._images[img.id] = img
    ds = _spectra_dataset("ses1",
        captions=["A", "B", "C"],
        positions=[
            # Acquired AFTER the image (wip_data_id 20/30/40 > 10).
            {"x_world": 10.0, "y_world": 70.0, "unit": "µm",
             "wip_data_id": 20},  # in-bounds → (10, 10)
            {"x_world": 50.0, "y_world": 40.0, "unit": "µm",
             "wip_data_id": 30},  # in-bounds → (50, 40)
            {"x_world": 200.0, "y_world": 40.0, "unit": "µm",
             "wip_data_id": 40},  # x out of bounds
        ],
    )
    backend._datasets["sample"] = ds

    out = backend.getDatasetOverlaysForImage(img.id)
    labels = [o["label"] for o in out]
    assert labels == ["A", "B"]  # C dropped (out of bounds)
    assert out[0]["x_pixel"] == pytest.approx(10.0)
    assert out[0]["y_pixel"] == pytest.approx(10.0)
    assert out[1]["x_pixel"] == pytest.approx(50.0)
    assert out[1]["y_pixel"] == pytest.approx(40.0)
    assert out[0]["dataset_name"] == "sample"


def test_probe_offset_shifts_overlay_pixel(qapp):
    """The WITec probe-offset preference *adds* ``(Dx, Dy)`` to each
    spectrum's stored video-centre coord before projecting onto the
    image, so the crosshair lands at the actual laser hit point."""
    backend = AppBackend()
    img = _calibrated_image("Map", "ses1", w=100, h=80, dx=1.0, dy=1.0,
                            world_origin=(0.0, 80.0), wip_data_id=10)
    backend._images[img.id] = img
    backend._datasets["sample"] = _spectra_dataset(
        "ses1", captions=["A"],
        positions=[{
            # Video-centre coord WITec wrote to the file.
            "x_world": 50.0, "y_world": 40.0, "unit": "µm",
            "wip_data_id": 20,
        }],
    )

    # No offset → crosshair lands at the wip-stored video centre.
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    raw = backend.getDatasetOverlaysForImage(img.id)
    assert raw[0]["x_pixel"] == pytest.approx(50.0)
    assert raw[0]["y_pixel"] == pytest.approx(40.0)
    # ``*_laser_world`` echoes the wip-stored centre (legacy name).
    assert raw[0]["x_laser_world"] == pytest.approx(50.0)
    assert raw[0]["y_laser_world"] == pytest.approx(40.0)

    # With (Dx, Dy) = (-2.0, +3.0): laser hit point world coord is
    # (50 + (-2), 40 + 3) = (48, 43). For dx=dy=1.0 and flipped Y
    # (world_origin_y=80), that's pixel (48, 80-43=37).
    backend.preferencesManager.setProbeOffset(-2.0, 3.0)
    shifted = backend.getDatasetOverlaysForImage(img.id)
    assert shifted[0]["x_pixel"] == pytest.approx(48.0)
    assert shifted[0]["y_pixel"] == pytest.approx(37.0)
    # Raw wip-stored centre is preserved for the debug marker.
    assert shifted[0]["x_pixel_laser"] == pytest.approx(50.0)
    assert shifted[0]["y_pixel_laser"] == pytest.approx(40.0)
    assert shifted[0]["x_laser_world"] == pytest.approx(50.0)
    assert shifted[0]["y_laser_world"] == pytest.approx(40.0)
    # Restore so we don't leak state across tests.
    backend.preferencesManager.setProbeOffset(0.0, 0.0)


def test_spectrum_appears_on_every_image_containing_its_world_coord(qapp):
    """A spectrum's coords land inside multiple compatible images (same
    .wip file) — the overlay backend deliberately does *not* restrict it
    to a single parent. The user wants to see spectra on every image
    whose bounds genuinely contain them."""
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    earlier = _calibrated_image(
        "earlier", "ses1", w=100, h=80, world_origin=(0.0, 80.0),
        wip_data_id=10,
    )
    later = _calibrated_image(
        "later", "ses1", w=100, h=80, world_origin=(0.0, 80.0),
        wip_data_id=20,
    )
    backend._images[earlier.id] = earlier
    backend._images[later.id] = later
    ds = _spectra_dataset("ses1",
        captions=["A"],
        positions=[{
            "x_world": 25.0, "y_world": 50.0, "unit": "µm",
            "wip_data_id": 30,
        }],
    )
    backend._datasets["sample"] = ds
    # Both images list the spectrum (bounds-based matching, no
    # acquisition-order restriction).
    assert [o["caption"] for o in backend.getDatasetOverlaysForImage(earlier.id)] == ["A"]
    assert [o["caption"] for o in backend.getDatasetOverlaysForImage(later.id)] == ["A"]


def test_mismatched_source_stem_yields_nothing(qapp):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    img = _calibrated_image("Map", "session-A")
    backend._images[img.id] = img
    backend._datasets["other"] = _spectra_dataset(
        "session-B",
        captions=["X"],
        positions=[{
            "x_world": 10.0, "y_world": 10.0, "unit": "µm",
            "wip_data_id": 5,
        }],
    )
    assert backend.getDatasetOverlaysForImage(img.id) == []


def test_image_without_affine_returns_empty(qapp):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    arr = np.zeros((10, 10), dtype=np.uint8)
    bare = ImageData(
        array=arr, mode=ImageMode.GRAY_U8,
        metadata=ImageMetadata(
            source="test",
            original_filename="sesX.wip",
        ),
        name="bare",
    )
    backend._images[bare.id] = bare
    backend._datasets["any"] = _spectra_dataset(
        "sesX", captions=["A"],
        positions=[{"x_world": 0.0, "y_world": 0.0, "unit": "µm",
                    "wip_data_id": 5}],
    )
    assert backend.getDatasetOverlaysForImage(bare.id) == []


def test_uncalibrated_position_entry_is_skipped(qapp):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    img = _calibrated_image("Map", "ses1", w=100, h=80, world_origin=(0.0, 80.0),
                            wip_data_id=1)
    backend._images[img.id] = img
    backend._datasets["sample"] = _spectra_dataset(
        "ses1",
        captions=["good", "bad"],
        positions=[
            {"x_world": 10.0, "y_world": 70.0, "unit": "µm",
             "wip_data_id": 5},
            None,  # uncalibrated spectrum — loader writes None here
        ],
    )
    out = backend.getDatasetOverlaysForImage(img.id)
    assert [o["label"] for o in out] == ["good"]


def test_zoom_regions_require_matching_world_origin(qapp):
    """Two images sharing the same world_origin (stage not moved between
    rezeros) are mutual zoom regions. Different origins → rejected,
    because we can't tell whether the stage was physically moved."""
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    # Same world_origin, child has finer pixel pitch and smaller frame
    # → covers a smaller area inside the parent.
    parent = _calibrated_image(
        "parent", "sess", w=100, h=80, dx=1.0, dy=1.0,
        world_origin=(0.0, 80.0),
    )
    child = _calibrated_image(
        "child", "sess", w=50, h=40, dx=0.4, dy=0.4,
        world_origin=(0.0, 80.0),
    )
    backend._images[parent.id] = parent
    backend._images[child.id] = child
    regs = backend.getZoomRegionsForImage(parent.id)
    assert [r["name"] for r in regs] == ["child"]
    r = regs[0]
    # Child covers world (0..20, 80..64) → parent pixels (0..20, 0..16).
    assert r["x_min_pixel"] == pytest.approx(0.0)
    assert r["x_max_pixel"] == pytest.approx(20.0)
    assert r["y_min_pixel"] == pytest.approx(0.0)
    assert r["y_max_pixel"] == pytest.approx(16.0)
    # Label includes the µm dimensions for precision.
    assert "20×16 µm" in r["label"]
    assert r["width_um"] == pytest.approx(20.0)
    assert r["height_um"] == pytest.approx(16.0)


def test_zoom_regions_skip_sibling_with_different_world_origin(qapp):
    """A sibling whose world bounds overlap but whose world_origin is
    different must be filtered out — that origin shift signals a stage
    rezero, so absolute coords are no longer comparable."""
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    parent = _calibrated_image(
        "parent", "sess", w=100, h=80, dx=1.0, dy=1.0,
        world_origin=(0.0, 80.0),
    )
    rezeroed = _calibrated_image(
        # Same physical area on disk, but world_origin is shifted by
        # more than the 1 µm tolerance: assume the user rezeroed between.
        "rezeroed", "sess", w=50, h=40, dx=0.4, dy=0.4,
        world_origin=(10.0, 80.0),
    )
    backend._images[parent.id] = parent
    backend._images[rezeroed.id] = rezeroed
    assert backend.getZoomRegionsForImage(parent.id) == []


def test_zoom_regions_skip_other_session(qapp):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    parent = _calibrated_image("parent", "A", world_origin=(0.0, 80.0))
    other = _calibrated_image("other", "B", world_origin=(0.0, 80.0))
    backend._images[parent.id] = parent
    backend._images[other.id] = other
    assert backend.getZoomRegionsForImage(parent.id) == []


def test_export_rect_overlay_draws_rectangle(qapp, tmp_path):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    img = _calibrated_image("p", "sess", w=80, h=80, world_origin=(0.0, 80.0))
    backend._images[img.id] = img
    overlays = [{
        "type": "rect",
        "x_min_pixel": 20.0, "y_min_pixel": 30.0,
        "x_max_pixel": 60.0, "y_max_pixel": 50.0,
        "label": "child", "color": "#00FF00",
    }]
    out = tmp_path / "rect.png"
    saved = backend.exportImageWithOverlays(img.id, overlays, str(out), "png")
    assert saved == str(out)
    from PIL import Image as PILImage
    arr = np.array(PILImage.open(saved))
    # Top and bottom edges should both carry the green outline colour.
    top = arr[30, 40]
    assert top[1] > 200 and top[0] < 50  # green dominant
    bottom = arr[50, 40]
    assert bottom[1] > 200 and bottom[0] < 50
    # A pixel completely outside the rectangle stays the source colour
    # (single-channel array of zeros → black after RGB conversion).
    outside = arr[5, 5]
    assert outside[0] < 30 and outside[1] < 30 and outside[2] < 30


def test_export_with_overlays_writes_tiff(qapp, tmp_path):
    backend = AppBackend()
    backend.preferencesManager.setProbeOffset(0.0, 0.0)
    img = _calibrated_image("Map", "ses1", w=100, h=80, world_origin=(0.0, 80.0))
    backend._images[img.id] = img
    backend._datasets["sample"] = _spectra_dataset(
        "ses1", captions=["only"],
        positions=[{"x_world": 25.0, "y_world": 25.0, "unit": "µm",
                    "wip_data_id": 5}],
    )
    overlays = backend.getDatasetOverlaysForImage(img.id)
    assert overlays  # sanity
    for ov in overlays:
        ov["color"] = "#FF0000"

    out = tmp_path / "annotated.tiff"
    saved = backend.exportImageWithOverlays(img.id, overlays, str(out), "tiff")
    assert saved == str(out)
    assert out.exists()
    # The exported TIFF should be RGB (overlays bake colour into pixels).
    import tifffile
    arr = tifffile.imread(str(out))
    assert arr.shape[-1] == 3
    # The crosshair pixel should carry the overlay colour somewhere near (25, 55).
    # (Image is 100×80; pixel y = (world_y_origin - world_y) / dy = (80-25)/1 = 55.)
    centre = arr[55, 25]
    assert centre[0] > 200 and centre[1] < 50  # red dominant
