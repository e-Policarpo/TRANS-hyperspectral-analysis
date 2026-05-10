"""
Backend-level tests for image entities.

Covers:
- ``addImageFromFile`` registers the image and emits ``imageAdded``
- ``deleteImage`` / ``renameImage`` round-trip
- ``getImageList`` returns shape-faithful records
- ``_absorb_dataset_images`` lifts ``additional_info['images']`` into the
  registry when a loader returns a SpectralData with embedded images
- ``convertImageToMap`` writes a TIFF and registers a map; round-trip
  preserves the float32 array exactly
- ``convertMapChannelToImage`` produces a SINGLE_FLOAT image with raw data

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtCore")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.image_data import ImageData, ImageMode
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qt_app):
    return AppBackend()


# =============================================================================
# Registration / lifecycle
# =============================================================================

def test_add_image_from_file_registers_and_signals(backend, tmp_path):
    pil = pytest.importorskip("PIL.Image")
    arr = np.zeros((4, 6, 3), dtype=np.uint8)
    p = tmp_path / "preview.png"
    pil.fromarray(arr, mode="RGB").save(p)

    received = []
    backend.imageAdded.connect(lambda iid, name: received.append((iid, name)))

    backend.addImageFromFile(str(p))
    assert len(backend._images) == 1
    iid = next(iter(backend._images))
    assert received == [(iid, "preview")]


def test_delete_image_removes_and_signals(backend):
    img = ImageData.from_array(np.zeros((4, 4), dtype=np.uint8), name="x")
    backend._images[img.id] = img

    deleted = []
    backend.imageDeleted.connect(lambda iid: deleted.append(iid))
    backend.deleteImage(img.id)

    assert img.id not in backend._images
    assert deleted == [img.id]


def test_rename_image_updates_and_signals(backend):
    img = ImageData.from_array(np.zeros((4, 4), dtype=np.uint8), name="old")
    backend._images[img.id] = img

    received = []
    backend.imageRenamed.connect(lambda iid, n: received.append((iid, n)))
    backend.renameImage(img.id, "new")

    assert backend._images[img.id].name == "new"
    assert received == [(img.id, "new")]


def test_get_image_list_returns_records(backend):
    img1 = ImageData.from_array(np.zeros((10, 20, 3), dtype=np.uint8), name="A")
    img2 = ImageData.from_array(np.zeros((5, 7), dtype=np.float32), name="B")
    backend._images[img1.id] = img1
    backend._images[img2.id] = img2

    rows = backend.getImageList()
    by_id = {r["id"]: r for r in rows}
    assert by_id[img1.id]["mode"] == "rgb"
    assert by_id[img1.id]["width"] == 20 and by_id[img1.id]["height"] == 10
    assert by_id[img2.id]["mode"] == "single_float"


def test_open_image_emits_embedded_signal_and_writes_tiff(backend, tmp_path):
    """Default: openImage emits the embedded-window signal AND writes a TIFF.

    The TIFF write makes ``openImageInOS`` available as a right-click
    fallback even when the user clicked the default ``Open`` action.
    """
    backend._output_base_dir = tmp_path
    img = ImageData.from_array(
        np.zeros((4, 4, 3), dtype=np.uint8), name="hello",
    )
    backend._images[img.id] = img

    received = []
    backend.openImageEmbedded.connect(
        lambda title, iid: received.append((title, iid))
    )

    backend.openImage(img.id)

    assert received == [("hello", img.id)]
    assert img.file_path is not None
    assert Path(img.file_path).exists()


def test_open_image_in_os_writes_tiff_and_calls_desktop_services(backend, tmp_path, monkeypatch):
    """``openImageInOS`` is the fallback path — uses QDesktopServices."""
    backend._output_base_dir = tmp_path
    img = ImageData.from_array(np.zeros((4, 4), dtype=np.uint8), name="hello")
    backend._images[img.id] = img

    opened = []
    from src.backend import app_backend as ab_mod
    monkeypatch.setattr(
        ab_mod.QDesktopServices, "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    backend.openImageInOS(img.id)

    assert img.file_path is not None
    assert Path(img.file_path).exists()
    assert opened == [img.file_path]


def test_open_image_unknown_id_emits_error(backend):
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))
    backend.openImage("not_a_real_id")
    assert len(errors) == 1


def test_open_note_emits_embedded_signal_and_writes_txt(backend, tmp_path):
    """Default: openNote emits the embedded-window signal AND writes a .txt."""
    backend._output_base_dir = tmp_path
    backend._notes["note_test"] = {
        'id': 'note_test',
        'name': 'Sample annotation',
        'text': 'Acquired at 532 nm — DtBuTPZ in toluene.',
        'source': 'witec_wip:test.wip',
    }
    received = []
    backend.openNoteEmbedded.connect(
        lambda title, body, source: received.append((title, body, source))
    )
    backend.openNote("note_test")

    assert len(received) == 1
    title, body, source = received[0]
    assert title == "Sample annotation"
    assert "Acquired at 532 nm" in body
    assert source == "witec_wip:test.wip"
    # Same data also persisted as .txt for the OS-fallback path.
    assert Path(backend._notes["note_test"]["file_path"]).exists()


def test_open_note_in_os_writes_txt_and_opens_via_os(backend, tmp_path, monkeypatch):
    """``openNoteInOS`` fallback path uses QDesktopServices."""
    backend._output_base_dir = tmp_path
    backend._notes["note_test"] = {
        'id': 'note_test',
        'name': 'Sample annotation',
        'text': 'Acquired at 532 nm — DtBuTPZ in toluene.',
        'source': 'witec_wip:test.wip',
    }
    opened = []
    from src.backend import app_backend as ab_mod
    monkeypatch.setattr(
        ab_mod.QDesktopServices, "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    backend.openNoteInOS("note_test")

    assert len(opened) == 1
    written = Path(opened[0])
    assert written.exists()
    body = written.read_text()
    assert "Sample annotation" in body
    assert "Acquired at 532 nm" in body
    assert "witec_wip:test.wip" in body


# =============================================================================
# _absorb_dataset_images: lift loader-attached images into the registry
# =============================================================================

def test_absorb_dataset_images_picks_up_metadata(backend):
    """Loader-style images attached to a SpectralData get registered."""
    img = ImageData.from_array(
        np.full((3, 4, 3), 128, dtype=np.uint8), name="optical_preview",
    )
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    meta = SpectralMetadata(
        source_type="test", dimensions=(2, 1),
        scan_mode="point", units={},
    )
    sd = SpectralData(df, meta)
    sd.metadata.additional_info["images"] = [("optical_preview", img)]

    received = []
    backend.imageAdded.connect(lambda iid, n: received.append((iid, n)))
    backend._absorb_dataset_images({"datasets": {"my_ds": sd}})

    assert img.id in backend._images
    assert backend._images[img.id].name == "optical_preview"
    assert (img.id, "optical_preview") in received


def test_absorb_dataset_images_skips_non_imagedata(backend):
    """An entry that isn't an ImageData must be silently skipped."""
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
    meta = SpectralMetadata(
        source_type="test", dimensions=(2, 1),
        scan_mode="point", units={},
    )
    sd = SpectralData(df, meta)
    sd.metadata.additional_info["images"] = [("bogus", "this is not an ImageData")]

    backend._absorb_dataset_images({"datasets": {"d": sd}})
    assert backend._images == {}


def test_on_file_loaded_absorbs_before_broadcasting_dataLoaded(backend):
    """Regression: image / note absorption must happen BEFORE the dataLoaded
    signal so the browser's onDataLoaded → refreshBrowser sees a populated
    registry. Earlier code refreshed first (empty list), then absorbed —
    leaving the browser blank.
    """
    img = ImageData.from_array(np.zeros((4, 4), dtype=np.uint8), name="A")
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})
    meta = SpectralMetadata(
        source_type="test", dimensions=(1, 1), scan_mode="point", units={},
    )
    sd = SpectralData(df, meta)
    sd.metadata.additional_info["images"] = [("A", img)]
    sd.metadata.additional_info["notes"] = [
        {"name": "Sample", "text": "Acquired at 532 nm", "source": "test"},
    ]

    events = []
    backend.imageAdded.connect(lambda iid, n: events.append(("imageAdded", iid)))
    backend.noteAdded.connect(lambda nid, n: events.append(("noteAdded", nid)))
    backend.dataLoaded.connect(lambda name: events.append(("dataLoaded", name)))

    backend._on_file_loaded({
        'datasets': {'ds': sd},
        'active_dataset': 'ds',
    })

    # imageAdded + noteAdded must come before dataLoaded.
    image_idx = next(i for i, e in enumerate(events) if e[0] == "imageAdded")
    note_idx = next(i for i, e in enumerate(events) if e[0] == "noteAdded")
    data_idx = next(i for i, e in enumerate(events) if e[0] == "dataLoaded")
    assert image_idx < data_idx, "imageAdded must fire before dataLoaded"
    assert note_idx < data_idx, "noteAdded must fire before dataLoaded"

    # Backend has them registered.
    assert img.id in backend._images
    assert len(backend._notes) == 1


def test_absorb_dataset_images_dedupes_by_id(backend):
    """The same image referenced from two datasets should register once."""
    img = ImageData.from_array(np.zeros((4, 4), dtype=np.uint8), name="shared")
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})
    meta = SpectralMetadata(
        source_type="test", dimensions=(1, 1),
        scan_mode="point", units={},
    )
    sd1 = SpectralData(df.copy(), meta)
    sd2 = SpectralData(df.copy(), meta)
    sd1.metadata.additional_info["images"] = [("shared", img)]
    sd2.metadata.additional_info["images"] = [("shared", img)]

    fired = []
    backend.imageAdded.connect(lambda iid, n: fired.append(iid))
    backend._absorb_dataset_images({"datasets": {"a": sd1, "b": sd2}})
    assert len(backend._images) == 1
    assert fired == [img.id]


# =============================================================================
# Map ↔ Image conversion
# =============================================================================

class _StubChannel:
    def __init__(self, data: np.ndarray, name: str = "Z"):
        self.data = data
        self.name = name


class _StubMCM:
    def __init__(self, channel: _StubChannel):
        self.active_channel = channel


def test_convert_map_to_image_uses_active_channel(backend):
    """Right-click → Convert to Image (raw) hands over the float32 array."""
    raw = (np.random.rand(20, 30) * 1e-9).astype(np.float32)
    backend._maps_inmem["m1"] = _StubMCM(_StubChannel(raw, name="Z"))
    backend.maps.append({
        'id': 'm1', 'title': 'Topo Map', 'path': '', 'timestamp': '',
    })
    received = []
    backend.imageAdded.connect(lambda iid, n: received.append((iid, n)))

    backend.convertMapChannelToImage("m1", "")  # empty → use active

    assert len(received) == 1
    iid, _ = received[0]
    image = backend._images[iid]
    assert image.mode == ImageMode.SINGLE_FLOAT
    assert np.array_equal(image.array, raw)
    # Name encodes the source.
    assert "Topo Map" in image.name
    assert "Z" in image.name


def test_convert_image_to_map_writes_tiff(backend, tmp_path):
    """Right-click → Convert to Map (TIFF) round-trips the float32 array."""
    tifffile = pytest.importorskip("tifffile")

    backend._output_base_dir = tmp_path
    raw = (np.random.rand(10, 8) * 5).astype(np.float32)
    img = ImageData.from_array(raw, mode=ImageMode.SINGLE_FLOAT, name="zmap")
    backend._images[img.id] = img

    map_created = []
    backend.mapCreated.connect(lambda mid, t: map_created.append((mid, t)))
    backend.convertImageToMap(img.id)

    assert len(map_created) == 1
    new_map = next(m for m in backend.maps if m['id'] == map_created[0][0])
    out_path = Path(new_map['path'])
    assert out_path.exists()
    # Read back the TIFF and verify pixel-exactness.
    restored = tifffile.imread(str(out_path))
    assert restored.dtype == np.float32
    assert np.array_equal(restored, raw)


def test_convert_image_to_map_rejects_rgb(backend, tmp_path):
    """RGB images cannot become maps; user gets a clear error."""
    backend._output_base_dir = tmp_path
    img = ImageData.from_array(
        np.zeros((4, 4, 3), dtype=np.uint8), mode=ImageMode.RGB, name="rgb",
    )
    backend._images[img.id] = img
    errors = []
    backend.errorOccurred.connect(lambda t, m: errors.append((t, m)))
    backend.convertImageToMap(img.id)
    assert errors and "single-channel" in errors[0][1].lower()
    assert backend.maps == []
