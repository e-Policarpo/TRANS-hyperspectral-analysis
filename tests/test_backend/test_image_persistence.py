"""
Round-trip tests for image-entity persistence in .hrt project files.

Builds a temporary project with mixed-mode images, saves it, loads it back,
and verifies that every image's pixel array, metadata, name, and id round-trip
losslessly.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backend.project_manager import ProjectManager
from src.models.image_data import ImageData, ImageMode
from src.models.spectral_data import SpectralData, SpectralMetadata


# =============================================================================
# Round-trip
# =============================================================================

def _stub_dataset() -> SpectralData:
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [10.0, 20.0, 30.0]})
    meta = SpectralMetadata(
        source_type="test", dimensions=(3, 1),
        scan_mode="point", units={},
    )
    return SpectralData(df, meta)


def test_save_and_load_images_round_trip(tmp_path):
    """Three images (RGB, GRAY_U16, SINGLE_FLOAT) must round-trip exactly."""
    pm = ProjectManager()
    project_path = tmp_path / "test.hrt"

    rgb = ImageData.from_array(
        np.random.randint(0, 255, (8, 12, 3), dtype=np.uint8),
        mode=ImageMode.RGB, name="optical",
    )
    gray16 = ImageData.from_array(
        np.random.randint(0, 60000, (4, 6), dtype=np.uint16),
        mode=ImageMode.GRAY_U16, name="ccd_frame",
    )
    fmap = ImageData.from_array(
        (np.random.rand(5, 7) * 1e-9).astype(np.float32),
        mode=ImageMode.SINGLE_FLOAT, name="z_topo",
    )
    images = {rgb.id: rgb, gray16.id: gray16, fmap.id: fmap}

    project_data = {
        'datasets': {'ds1': _stub_dataset()},
        'images': images,
        'metadata': {'name': 'unit-test'},
        'tables': [],
        'graphs': [],
        'image_windows': [],
        'workspace': {},
        'output_files': [],
        'maps': [],
        'naming_convention': '[dataset_name]',
    }
    assert pm.save_project(project_path, project_data) is True

    loaded = pm.load_project(project_path)
    assert loaded is not None

    restored = loaded['images']
    assert isinstance(restored, dict)
    assert set(restored.keys()) == set(images.keys())

    for image_id, original in images.items():
        rt = restored[image_id]
        assert rt.id == original.id
        assert rt.name == original.name
        assert rt.mode == original.mode
        assert rt.shape == original.shape
        assert np.array_equal(rt.array, original.array), (
            f"Image {original.name!r} did not round-trip pixel-exact"
        )


def test_save_with_no_images_loads_empty_dict(tmp_path):
    """Backward compatibility: a project saved without images must load fine."""
    pm = ProjectManager()
    project_path = tmp_path / "no_images.hrt"
    project_data = {
        'datasets': {'d': _stub_dataset()},
        'tables': [],
        'graphs': [],
        'workspace': {},
        'output_files': [],
        'maps': [],
        'naming_convention': '[dataset_name]',
    }
    pm.save_project(project_path, project_data)
    loaded = pm.load_project(project_path)
    assert loaded is not None
    assert loaded['images'] == {}


def test_save_and_load_notes_round_trip(tmp_path):
    """Note entities must round-trip through ``.hrt`` save/load."""
    pm = ProjectManager()
    project_path = tmp_path / "with_notes.hrt"
    notes = {
        'note_1': {'id': 'note_1', 'name': 'Sample A', 'text': 'Acquired at 532 nm', 'source': 'witec_wip:s.wip'},
        'note_2': {'id': 'note_2', 'name': 'Sample B', 'text': '', 'source': 'unknown'},
    }
    project_data = {
        'datasets': {'d': _stub_dataset()},
        'tables': [], 'graphs': [], 'image_windows': [],
        'workspace': {}, 'output_files': [], 'maps': [],
        'notes': notes,
        'naming_convention': '[dataset_name]',
    }
    assert pm.save_project(project_path, project_data) is True
    loaded = pm.load_project(project_path)
    assert loaded is not None
    restored = loaded['notes']
    assert set(restored.keys()) == {'note_1', 'note_2'}
    assert restored['note_1']['name'] == 'Sample A'
    assert restored['note_1']['text'] == 'Acquired at 532 nm'
    assert restored['note_2']['source'] == 'unknown'


def test_save_with_no_notes_loads_empty_dict(tmp_path):
    """Backward compatibility: project saved without notes loads as ``{}``."""
    pm = ProjectManager()
    p = tmp_path / "no_notes.hrt"
    pm.save_project(p, {
        'datasets': {'d': _stub_dataset()},
        'tables': [], 'graphs': [],
        'workspace': {}, 'output_files': [], 'maps': [],
        'naming_convention': '[dataset_name]',
    })
    loaded = pm.load_project(p)
    assert loaded is not None
    assert loaded['notes'] == {}


def test_image_window_states_persist(tmp_path):
    """Image-window states are stored alongside graph/table states."""
    pm = ProjectManager()
    project_path = tmp_path / "windows.hrt"
    project_data = {
        'datasets': {'d': _stub_dataset()},
        'tables': [],
        'graphs': [],
        'image_windows': [
            {'id': 'iw1', 'type': 'image', 'image_id': 'img_xxx',
             'x': 100, 'y': 200, 'width': 400, 'height': 300,
             'displayMin': 0.0, 'displayMax': 1.0,
             'colormap': 'viridis'},
        ],
        'workspace': {},
        'output_files': [],
        'maps': [],
        'naming_convention': '[dataset_name]',
    }
    pm.save_project(project_path, project_data)
    loaded = pm.load_project(project_path)
    assert loaded is not None
    assert len(loaded['image_windows']) == 1
    iw = loaded['image_windows'][0]
    assert iw['image_id'] == 'img_xxx'
    assert iw['colormap'] == 'viridis'
