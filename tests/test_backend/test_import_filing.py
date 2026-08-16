"""Every loader's imports are filed as ``<Type>/<session>`` in the browser.

Omicron MATRIX was the only loader whose imports landed in per-session
subfolders; everything else piled into a flat "Spectral Data". The backend now
derives the session group from whatever source information the loader already
recorded, so a loader inherits the convention without opting in.
"""

import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.models.image_data import ImageData, ImageMetadata
from src.models.spectral_data import SpectralData, SpectralMetadata


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def backend(qt_app):
    return AppBackend()


def _dataset(**info):
    df = pd.DataFrame({"V": [0.0, 1.0], "Spectrum_01": [1.0, 2.0]})
    return SpectralData(
        df, SpectralMetadata("t", (1, 1), "meander", {}, additional_info=info))


def _paths(backend):
    """placement ref -> "Parent/Child" folder path."""
    folders = {f["id"]: f for f in backend._browser_tree["folders"]}

    def path(fid):
        parts = []
        while fid:
            parts.append(folders[fid]["name"])
            fid = folders[fid].get("parent") or ""
        return "/".join(reversed(parts))

    return {ref: path(fid)
            for ref, fid in backend._browser_tree["placements"].items()}


class TestGroupLabel:
    @pytest.mark.parametrize("info,expected", [
        ({"session_label": "run_03"}, "run_03"),
        ({"source_file": "/data/DtBuTPZ.wip"}, "DtBuTPZ"),
        ({"source_directory": "/data/ParkRun_2026"}, "ParkRun_2026"),
        ({"original_filename": "scan.tiff"}, "scan"),
        ({"dataset_name": "MySample"}, "MySample"),
    ])
    def test_derives_from_any_recorded_source(self, info, expected):
        assert AppBackend._group_label(info) == expected

    def test_explicit_label_wins_over_derived(self):
        assert AppBackend._group_label({
            "session_label": "explicit",
            "source_file": "/data/other.wip",
        }) == "explicit"

    @pytest.mark.parametrize("info", [None, {}, {"unrelated": "x"},
                                      {"source_file": ""}])
    def test_no_source_means_no_subfolder(self, info):
        assert AppBackend._group_label(info) is None


class TestFilingConvention:
    def test_single_file_import_groups_by_file_stem(self, backend):
        img = ImageData.from_array(np.zeros((4, 4), np.float32), name="thumb")
        img.metadata = ImageMetadata(source="witec",
                                     original_filename="sample.wip")
        ds = _dataset(source_file="/data/DtBuTPZ_run3.wip")
        ds.metadata.additional_info["images"] = [("thumb", img)]
        ds.metadata.additional_info["notes"] = [
            {"name": "n1", "text": "hi", "source": "witec_wip:x"}]

        backend._on_file_loaded(
            {"datasets": {"PL map": ds}, "active_dataset": "PL map"})

        paths = _paths(backend)
        assert paths["dataset:PL map"] == "Spectral Data/DtBuTPZ_run3"
        assert [v for k, v in paths.items() if k.startswith("image:")] \
            == ["Images/DtBuTPZ_run3"]
        assert [v for k, v in paths.items() if k.startswith("note:")] \
            == ["Notes/DtBuTPZ_run3"]

    def test_images_inherit_the_dataset_session_not_their_own_filename(
            self, backend):
        """Otherwise a Park import gets one subfolder per preview TIFF."""
        imgs = []
        for ch in ("Height", "Phase"):
            im = ImageData.from_array(np.zeros((4, 4), np.float32), name=ch)
            im.metadata = ImageMetadata(source="park",
                                        original_filename=f"scan_{ch}.tiff")
            imgs.append((ch, im))
        ds = _dataset(source_directory="/data/ParkRun_2026")
        ds.metadata.additional_info["images"] = imgs

        backend._on_file_loaded(
            {"datasets": {"Park ch1": ds}, "active_dataset": "Park ch1"})

        image_paths = {v for k, v in _paths(backend).items()
                       if k.startswith("image:")}
        assert image_paths == {"Images/ParkRun_2026"}

    def test_explicit_browser_folders_are_honoured(self, backend):
        ds = _dataset(session_label="default_2026Jun15")
        backend._on_file_loaded({
            "datasets": {"ov": ds}, "active_dataset": "ov",
            "browser_folders": {"dataset:ov": "default_2026Jun15"},
        })
        assert _paths(backend)["dataset:ov"] == "Spectral Data/default_2026Jun15"

    def test_legacy_matrix_folders_key_still_works(self, backend):
        """Older result payloads used ``matrix_folders``."""
        ds = _dataset()
        backend._on_file_loaded({
            "datasets": {"ov": ds}, "active_dataset": "ov",
            "matrix_folders": {"dataset:ov": "legacy_session"},
        })
        assert _paths(backend)["dataset:ov"] == "Spectral Data/legacy_session"

    def test_uncharacterised_import_still_lands_in_the_type_folder(
            self, backend):
        ds = _dataset()  # no source info at all
        backend._on_file_loaded(
            {"datasets": {"bare": ds}, "active_dataset": "bare"})
        assert _paths(backend)["dataset:bare"] == "Spectral Data"

    def test_two_sessions_get_separate_subfolders(self, backend):
        backend._on_file_loaded({
            "datasets": {"a": _dataset(source_file="/d/run_a.wip")},
            "active_dataset": "a"})
        backend._on_file_loaded({
            "datasets": {"b": _dataset(source_file="/d/run_b.wip")},
            "active_dataset": "b"})
        paths = _paths(backend)
        assert paths["dataset:a"] == "Spectral Data/run_a"
        assert paths["dataset:b"] == "Spectral Data/run_b"

    def test_reimport_reuses_the_same_subfolder(self, backend):
        for name in ("a", "b"):
            backend._on_file_loaded({
                "datasets": {name: _dataset(source_file="/d/run.wip")},
                "active_dataset": name})
        subfolders = [f for f in backend._browser_tree["folders"]
                      if f["name"] == "run"]
        assert len(subfolders) == 1

    def test_derived_images_sit_beside_their_source(self, backend, tmp_path):
        """A crop belongs next to the image it came from — including inside
        whatever folder the user moved that image into."""
        backend._output_base_dir = tmp_path
        img = ImageData.from_array(
            np.arange(400, dtype=np.uint8).reshape(20, 20), name="src")
        backend._images[img.id] = img
        mine = backend.createFolder("My Analysis", "")
        backend.moveItem(f"image:{img.id}", mine)

        new_id = backend.cropImage(img.id, 2, 2, 10, 10)

        assert new_id
        assert _paths(backend)[f"image:{new_id}"] == "My Analysis"

    def test_derived_image_falls_back_to_the_type_folder(self, backend,
                                                         tmp_path):
        backend._output_base_dir = tmp_path
        img = ImageData.from_array(
            np.arange(400, dtype=np.uint8).reshape(20, 20), name="src")
        backend._images[img.id] = img  # never filed

        new_id = backend.cropImage(img.id, 2, 2, 10, 10)

        assert _paths(backend)[f"image:{new_id}"] == "Images"

    def test_user_placement_is_never_overridden(self, backend):
        ds = _dataset(source_file="/d/run.wip")
        backend._on_file_loaded(
            {"datasets": {"a": ds}, "active_dataset": "a"})
        mine = backend.createFolder("My Analysis", "")
        backend.moveItem("dataset:a", mine)
        # Re-import the same dataset name.
        backend._on_file_loaded(
            {"datasets": {"a": _dataset(source_file="/d/run.wip")},
             "active_dataset": "a"})
        assert _paths(backend)["dataset:a"] == "My Analysis"
