"""
The HRT3 project container: a zip with project.json and one .npy per array.

HRT2 put every array as base64 inside one gzipped JSON document; a 2.5 GB
project (Selene, 2026-11-13) took 3 min 25 s just to json.load, swapping on a
16 GB Mac. These pin the replacement and that old files still open.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

import gzip
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from src.backend.project_manager import ProjectManager
from src.models.spectral_data import SpectralData, SpectralMetadata


def _dataset(n=40, m=3, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({'V': np.linspace(-1, 1, n)})
    for i in range(m):
        df[f'S{i}'] = rng.normal(size=n)
    return SpectralData(df, SpectralMetadata(
        source_type='sts', dimensions=(m, 1), scan_mode='point',
        units={'V': 'V'}, additional_info={'note': 'x'}))


def _project():
    return {'datasets': {'A': _dataset(seed=1), 'B': _dataset(seed=2)},
            'metadata': {'name': 'Fmt'}}


def test_a_save_is_a_zip_of_json_and_npy_members(tmp_path):
    path = tmp_path / "p.hrt"
    assert ProjectManager().save_project(path, _project())

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        doc = json.loads(zf.read('project.json'))
    assert doc['format_version'] == '3.0'
    assert sum(n.startswith('arrays/') for n in names) == 4      # 2 datasets x 2 arrays
    entry = doc['datasets']['A']
    assert entry['data_binary'].startswith('npy:arrays/')
    # No array is inlined: the document stays small whatever the data size.
    assert len(json.dumps(doc)) < 5000


def test_values_round_trip_exactly(tmp_path):
    path = tmp_path / "p.hrt"
    original = _project()
    ProjectManager().save_project(path, original)
    loaded = ProjectManager().load_project(path)
    for name in ('A', 'B'):
        pd.testing.assert_frame_equal(loaded['datasets'][name].data,
                                      original['datasets'][name].data)


def test_an_autosave_stores_arrays_uncompressed(tmp_path):
    path = tmp_path / "p.hrt"
    ProjectManager().save_project(path, _project(), fast=True)
    with zipfile.ZipFile(path) as zf:
        kinds = {i.compress_type for i in zf.infolist() if i.filename.startswith('arrays/')}
    assert kinds == {zipfile.ZIP_STORED}


def test_an_hrt2_file_still_opens(tmp_path):
    """A project written by an older build: b'HRT2' + gzipped JSON with
    base64 arrays."""
    pm = ProjectManager()
    ds = _dataset(seed=3)
    values = ds.data.drop(columns=['V'])
    doc = {'format_version': '2.0', 'datasets': {'Old': {
        'type': 'SpectralData', 'format': 'binary',
        'columns': list(values.columns),
        'data_binary': pm._numpy_to_base64(values.to_numpy()),
        'independent_var_binary': pm._numpy_to_base64(ds.data['V'].to_numpy()),
        'independent_var_name': 'V',
        'metadata': {'source_type': 'sts', 'dimensions': [3, 1],
                     'scan_mode': 'point', 'units': {}, 'additional_info': {}}}}}
    path = tmp_path / "old.hrt"
    with open(path, 'wb') as f:
        f.write(b'HRT2')
        with gzip.GzipFile(fileobj=f, mode='wb') as gz:
            gz.write(json.dumps(doc).encode())

    loaded = ProjectManager().load_project(path)
    pd.testing.assert_frame_equal(loaded['datasets']['Old'].data, ds.data)


def test_resaving_an_hrt2_project_converts_it(tmp_path):
    path = tmp_path / "p.hrt"
    pm = ProjectManager()
    pm.save_project(path, _project())
    data = pm.load_project(path)
    pm.save_project(path, data)
    assert zipfile.is_zipfile(path)
    assert set(pm.load_project(path)['datasets']) == {'A', 'B'}


def test_in_memory_maps_use_array_members(tmp_path):
    from src.models.map_channel import MultiChannelMap
    mcm = MultiChannelMap()
    mcm.add_channel('Z', np.arange(12, dtype=float).reshape(3, 4))
    path = tmp_path / "p.hrt"
    ProjectManager().save_project(path, {'datasets': {}, 'maps_inmem': {'m': mcm}})

    with zipfile.ZipFile(path) as zf:
        doc = json.loads(zf.read('project.json'))
    assert 'b64' not in doc['maps_inmem'][0]['channels']['Z']
    loaded = ProjectManager().load_project(path)
    np.testing.assert_array_equal(loaded['maps_inmem']['m'].channels['Z'].data,
                                  np.arange(12, dtype=float).reshape(3, 4))


def test_a_load_leaves_no_archive_open(tmp_path):
    pm = ProjectManager()
    path = tmp_path / "p.hrt"
    pm.save_project(path, _project())
    pm.load_project(path)
    assert pm._arrays_in is None
