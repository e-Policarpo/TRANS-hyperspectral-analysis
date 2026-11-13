"""
Scan images read by one forward pass over the session header are the images
access2theMatrix's own open() returns -- traces, geometry, units, all of it.

open() replays the header from the start for every image (~2 s each on a
drift-compensated session: 60% of the 07-Jul-2026 folder import). Runs on the
real data when it is on this machine; skipped elsewhere.

T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
"""

from pathlib import Path

import numpy as np
import pytest

from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader

FOLDER = Path("/Users/eduardapolicarpo/Documents/Doutorado/Colab UFV/"
              "Artigo MnBi2Te4/STM UHV/Jun-Jul 26/07-Jul-2026")
BASE = "default_2026Jul07-151828_STM-STM_Spectroscopy"


def _images(limit):
    files = sorted(FOLDER.glob(BASE + "--*.[ZI]_mtrx"))
    return files[:limit]


@pytest.mark.skipif(not (FOLDER / f"{BASE}_0001.mtrx").exists(),
                    reason="real MATRIX session not on this machine")
def test_incremental_images_match_a2m_open():
    loader = OmicronMatrixSTSLoader()
    raw = loader._read_header_chain(FOLDER / f"{BASE}_0001.mtrx")
    files = _images(6)
    assert files

    md = loader._new_md()
    md.raw_param, md.param, md.channel_id = raw, {'BREF': ''}, {}
    cursor = [12]
    fast = {f: loader._image_incremental(md, raw, cursor, f)
            for f in loader._header_order(raw, files)}

    for f in files:
        slow = loader._image_via_a2m(loader._new_md(), f)
        got = fast[f]
        assert got is not None, f.name
        assert set(got['traces']) == set(slow['traces']), f.name
        for name, arr in slow['traces'].items():
            np.testing.assert_array_equal(got['traces'][name], arr)
        for key in ('channel_name', 'unit', 'width_m', 'height_m',
                    'x_offset_m', 'y_offset_m', 'angle', 'timestamp'):
            assert got[key] == slow[key], (f.name, key)


def test_header_order_follows_the_bref_entries():
    names = [Path("a--1_1.Z_mtrx"), Path("a--2_1.Z_mtrx"), Path("a--3_1.Z_mtrx")]
    raw = b"x" + "a--2_1.Z_mtrx".encode("utf-16-le") + b"y" + \
        "a--1_1.Z_mtrx".encode("utf-16-le")
    order = OmicronMatrixSTSLoader._header_order(raw, names)
    assert [p.name for p in order] == ["a--2_1.Z_mtrx", "a--1_1.Z_mtrx", "a--3_1.Z_mtrx"]


def test_lockin_keys_follow_a_growing_tree():
    loader = OmicronMatrixSTSLoader
    param = {'EEPA::Lockin.Amplitude': (0.01, 'V'), 'EEPA::Other.X': (1, '')}
    assert loader._lockin_settings(param)['v_mod'] == 0.01
    param['EEPA::Lockin.Frequency'] = (900.0, 'Hz')
    assert loader._lockin_settings(param)['lockin_frequency_hz'] == 900.0
    param['EEPA::Lockin.Amplitude'] = (0.02, 'V')      # same size, new value
    assert loader._lockin_settings(param)['v_mod'] == 0.02
