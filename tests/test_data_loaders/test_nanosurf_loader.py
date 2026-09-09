# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: test_nanosurf_loader.py
# Description: Tests for Nanosurf STS data loaders
# ============================================================================

"""
Tests for Nanosurf STS data loaders.
Tests cover both NanosurfSTSLoader and NanosurfSTSEnhancedLoader.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, patch, MagicMock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.models.topography_data import TopographyData


# =============================================================================
# NSFopen is now vendored - always available
# =============================================================================
from src.data_loaders.nsfopen import read as nid_read
NSFOPEN_AVAILABLE = True


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_nsfopen():
    """Create a mock NSFopen module."""
    mock_nid = MagicMock()

    # Mock spectroscopy data
    n_points = 100
    n_reps = 3
    V = np.linspace(-1, 1, n_points)
    I_forward = np.random.randn(n_reps, n_points) * 1e-9
    I_backward = np.random.randn(n_reps, n_points) * 1e-9

    mock_nid.data.Spec.Forward = {
        "Tip Current": I_forward,
        "Tip voltage": V.reshape(1, -1)
    }
    mock_nid.data.Spec.Backward = {
        "Tip Current": I_backward
    }

    # Mock topography
    topo_size = 64
    z_forward = np.random.randn(topo_size, topo_size) * 1e-9
    z_backward = np.random.randn(topo_size, topo_size) * 1e-9

    mock_nid.data.Image.Forward = {"Z-Axis": z_forward}
    mock_nid.data.Image.Backward = {"Z-Axis": z_backward}

    # Mock parameters
    mock_nid.param = {
        "V_min": -1.0,
        "V_max": 1.0,
        "GridDimX": 10,
        "GridDimY": 10
    }

    return mock_nid


@pytest.fixture
def sample_nid_file(tmp_path):
    """Create a mock .nid file path."""
    filepath = tmp_path / "test.nid"
    filepath.write_bytes(b"mock nid content")
    return filepath


# =============================================================================
# NanosurfSTSLoader Tests (with mocked NSFopen)
# =============================================================================

@pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
class TestNanosurfSTSLoaderBasic:
    """Basic tests for NanosurfSTSLoader."""

    def test_loader_creation(self):
        """NS-01: Can create loader instance when NSFopen is available."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        assert loader is not None
        assert loader.loader_type == 'nanosurf_sts'

    def test_supported_extensions(self):
        """NS-02: Loader has correct supported extensions."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        assert '.nid' in loader.supported_extensions


class TestNanosurfSTSLoaderWithMock:
    """Tests for NanosurfSTSLoader using mocked NSFopen."""

    @pytest.fixture
    def patched_loader(self, mock_nsfopen):
        """Create loader with mocked nid_read function."""
        with patch('src.data_loaders.nanosurf_sts_loader.nid_read', return_value=mock_nsfopen):
            from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader
            loader = NanosurfSTSLoader.__new__(NanosurfSTSLoader)
            loader.supported_extensions = ['.nid']
            loader.loader_type = 'nanosurf_sts'
            loader.last_loaded_path = None
            yield loader, mock_nsfopen

    def test_generate_voltage_array_from_metadata(self, patched_loader):
        """NS-03: Can generate voltage array from metadata."""
        loader, mock_nid = patched_loader

        V = loader._generate_voltage_array_from_metadata(mock_nid)

        assert V is not None
        assert len(V) == 100
        assert V[0] == pytest.approx(-1.0)
        assert V[-1] == pytest.approx(1.0)

    def test_extract_dimensions_from_params(self, patched_loader):
        """NS-04: Can extract dimensions from parameters."""
        loader, mock_nid = patched_loader

        dims = loader.extract_dimensions_from_params(mock_nid)

        assert dims is not None
        assert dims == (10, 10)


# =============================================================================
# NanosurfSTSEnhancedLoader Tests
# =============================================================================

@pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
class TestNanosurfSTSEnhancedLoaderBasic:
    """Basic tests for NanosurfSTSEnhancedLoader."""

    def test_enhanced_loader_creation(self):
        """NS-ENH-01: Can create enhanced loader instance."""
        from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader

        loader = NanosurfSTSEnhancedLoader()
        assert loader is not None
        assert loader.loader_type == 'nanosurf_sts'

    def test_enhanced_loader_has_metadata_parser(self):
        """NS-ENH-02: Enhanced loader has metadata parsing methods."""
        from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader

        loader = NanosurfSTSEnhancedLoader()
        assert hasattr(loader, 'parse_nid_metadata')
        assert hasattr(loader, '_parse_map0_line')


class TestNanosurfMetadataParsing:
    """Tests for metadata parsing in enhanced loader."""

    def test_parse_map0_line_valid(self):
        """NS-ENH-03: Can parse valid Map0 line."""
        # Import and create loader only if available
        if not NSFOPEN_AVAILABLE:
            pytest.skip("NSFopen not available")

        from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader

        loader = NanosurfSTSEnhancedLoader()

        # Example Map0 line from real files
        map0_str = "-5.05339e-007;-1.46048e-008;-5.57349e-007;-6.85389e-008;100;100;0;1"

        dims = loader._parse_map0_line(map0_str)

        assert dims is not None
        assert dims == (100, 100)

    def test_parse_map0_line_invalid(self):
        """NS-ENH-04: Returns None for invalid Map0 line."""
        if not NSFOPEN_AVAILABLE:
            pytest.skip("NSFopen not available")

        from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader

        loader = NanosurfSTSEnhancedLoader()

        dims = loader._parse_map0_line("invalid;format")

        assert dims is None

    def test_parse_map0_line_too_short(self):
        """NS-ENH-05: Returns None for Map0 line with insufficient values."""
        if not NSFOPEN_AVAILABLE:
            pytest.skip("NSFopen not available")

        from src.data_loaders.nanosurf_sts_enhanced import NanosurfSTSEnhancedLoader

        loader = NanosurfSTSEnhancedLoader()

        dims = loader._parse_map0_line("1;2;3")  # Less than 6 values

        assert dims is None


# =============================================================================
# Integration Tests
# =============================================================================

class TestNanosurfLoaderIntegration:
    """Integration tests for Nanosurf loaders."""

    @pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
    def test_loader_info(self):
        """NS-INT-01: Loader info returns correct structure."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        info = loader.get_info()

        assert isinstance(info, dict)
        assert info['type'] == 'nanosurf_sts'
        assert '.nid' in info['supported_extensions']

    @pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
    def test_loader_repr(self):
        """NS-INT-02: Loader has valid string representation."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        repr_str = repr(loader)

        assert 'NanosurfSTSLoader' in repr_str
        assert 'nanosurf_sts' in repr_str


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestNanosurfLoaderErrors:
    """Error handling tests for Nanosurf loaders."""

    @pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
    def test_load_nonexistent_file_raises(self, tmp_path):
        """NS-ERR-01: Loading nonexistent file raises error."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        fake_path = tmp_path / "nonexistent.nid"

        with pytest.raises(FileNotFoundError):
            loader.load_single_file(fake_path)

    @pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
    def test_load_wrong_extension_raises(self, tmp_path):
        """NS-ERR-02: Loading wrong extension raises error."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        wrong_file = tmp_path / "test.txt"
        wrong_file.write_text("not an nid file")

        with pytest.raises(ValueError):
            loader.load_single_file(wrong_file)

    @pytest.mark.skipif(not NSFOPEN_AVAILABLE, reason="NSFopen not available")
    def test_validate_empty_directory(self, tmp_path):
        """NS-ERR-03: Validating empty directory returns False."""
        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        assert loader.validate_directory(empty_dir) is False


# =============================================================================
# Data Processing Tests
# =============================================================================

class TestNanosurfDataProcessing:
    """Tests for data processing functionality."""

    def test_meander_correction_concept(self):
        """NS-PROC-01: Verify meander correction concept."""
        # Test the meander correction algorithm conceptually
        # Create a simple 3x3 grid
        cols = [f"P_{i}" for i in range(9)]
        data = pd.DataFrame({
            "V": np.linspace(-1, 1, 10),
            **{c: np.random.rand(10) for c in cols}
        })

        metadata = SpectralMetadata(
            source_type='nanosurf_sts',
            dimensions=(3, 3),
            scan_mode='meander',
            units={'x': 'V', 'y': 'nA'}
        )

        spectral_data = SpectralData(data, metadata)

        # Verify meander correction can be applied
        spectral_data.correct_meander()

        assert spectral_data._corrected_meander is True

    def test_concatenate_spectra(self):
        """NS-PROC-02: Can concatenate multiple spectra."""
        if not NSFOPEN_AVAILABLE:
            pytest.skip("NSFopen not available")

        from src.data_loaders.nanosurf_sts_loader import NanosurfSTSLoader

        loader = NanosurfSTSLoader()

        spectra = [
            np.array([1, 2, 3, 4, 5]),
            np.array([6, 7, 8, 9, 10])
        ]
        x = np.linspace(0, 1, 5)

        df = loader.concatenate_spectra(spectra, x)

        assert isinstance(df, pd.DataFrame)
        assert len(df.columns) == 3  # Variable + 2 spectra
        assert len(df) == 5


# =============================================================================
# Session organisation
#
# A .nid folder is a day's work, not one experiment. The loader used to
# cluster it into sessions and then hand back only the largest one, so a
# folder of 193 spectroscopy files imported as 52 and lost the other 141
# without an error. These cover the discovery, the labels the sessions get,
# and the per-spectrum provenance now carried on each dataset.
# =============================================================================

from datetime import datetime, timedelta      # noqa: E402
from pathlib import Path                      # noqa: E402
from unittest.mock import patch               # noqa: E402

from src.data_loaders.nanosurf_sts_enhanced import (   # noqa: E402
    NanosurfSTSEnhancedLoader,
)


def _fingerprint(name, when, *, spec_mode='Map', data_points=512,
                 map_dims='8;8', rep='Repeat each position'):
    """A fingerprint dict shaped like _parse_file_fingerprint's output."""
    return {
        'filepath': Path(f"/fake/{name}.nid"),
        'repetition_mode': rep,
        'data_points': data_points,
        'modulation_time': '200ms',
        'mod_output': 'Tip voltage',
        'spec_mode': spec_mode,
        'map_dims': map_dims,
        'map0': None,
        'timestamp': when,
    }


class TestDiscoverSessions:
    """Session discovery over a directory of .nid files."""

    @pytest.fixture
    def loader(self):
        return NanosurfSTSEnhancedLoader()

    def _run(self, loader, fingerprints):
        with patch.object(loader, 'find_files',
                          return_value=[fp['filepath'] for fp in fingerprints]), \
             patch.object(loader, '_parse_file_fingerprint',
                          side_effect=lambda p: next(
                              (fp for fp in fingerprints if fp['filepath'] == p), None)):
            return loader.discover_sessions(Path("/fake"))

    def test_splits_on_a_long_gap(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("a", base),
               _fingerprint("b", base + timedelta(minutes=1)),
               _fingerprint("c", base + timedelta(hours=2))]
        sessions = self._run(loader, fps)
        assert [len(s['files']) for s in sessions] == [2, 1]

    def test_splits_on_different_settings(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("a", base),
               _fingerprint("b", base + timedelta(seconds=30), data_points=128)]
        sessions = self._run(loader, fps)
        assert len(sessions) == 2

    def test_every_file_is_kept(self, loader):
        """The defect: sessions beyond the largest used to be dropped."""
        base = datetime(2026, 5, 2, 19, 0)
        fps = ([_fingerprint(f"big{i}", base + timedelta(seconds=i))
                for i in range(10)]
               + [_fingerprint("lone", base + timedelta(hours=3))])
        sessions = self._run(loader, fps)
        assert sum(len(s['files']) for s in sessions) == 11

    def test_sessions_are_in_acquisition_order(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("late", base + timedelta(hours=3)),
               _fingerprint("early", base)]
        sessions = self._run(loader, fps)
        assert sessions[0]['files'][0].name == "early.nid"

    def test_labels_are_unique(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("a", base),
               _fingerprint("b", base + timedelta(hours=2)),
               _fingerprint("c", base + timedelta(hours=4))]
        labels = [s['label'] for s in self._run(loader, fps)]
        assert len(set(labels)) == 3

    def test_same_day_sessions_keep_their_times(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("a", base), _fingerprint("b", base + timedelta(hours=2))]
        labels = [s['label'] for s in self._run(loader, fps)]
        assert all(label.startswith("2026May02-") for label in labels)

    def test_topography_only_files_are_ignored(self, loader):
        base = datetime(2026, 5, 2, 19, 0)
        fps = [_fingerprint("a", base)]
        with patch.object(loader, 'find_files',
                          return_value=[Path("/fake/a.nid"), Path("/fake/topo.nid")]), \
             patch.object(loader, '_parse_file_fingerprint',
                          side_effect=lambda p: fps[0] if p.name == "a.nid" else None):
            sessions = loader.discover_sessions(Path("/fake"))
        assert sum(len(s['files']) for s in sessions) == 1

    def test_session_carries_its_settings(self, loader):
        session = self._run(loader, [_fingerprint("a", datetime(2026, 5, 2, 19, 0))])[0]
        assert session['repetition_mode'] == 'Repeat each position'
        assert session['settings']['data_points'] == 512
        assert session['settings']['modulation_time'] == '200ms'
        assert session['spec_mode'] == 'Map'


class TestSessionTag:
    """The short description that names a session's datasets."""

    def test_map_reports_its_grid(self):
        tag = NanosurfSTSEnhancedLoader.session_tag(
            {'spec_mode': 'Map', 'settings': {'map_dims': '8;8'}, 'files': [1] * 30})
        assert tag == "Map 8x8"

    def test_point_reports_its_count(self):
        tag = NanosurfSTSEnhancedLoader.session_tag(
            {'spec_mode': 'Point', 'settings': {}, 'files': [1] * 52})
        assert tag == "Point x52"


class TestSpectrumProvenance:
    """Per-spectrum metadata stamped onto a loaded session."""

    @pytest.fixture
    def spectral(self):
        from src.models.spectral_data import SpectralData, SpectralMetadata
        df = pd.DataFrame({
            "V": np.linspace(-1, 1, 5),
            **{f"Point_{i + 1:02d}": np.arange(5, dtype=float) for i in range(4)},
        })
        meta = SpectralMetadata(source_type='nanosurf_sts', dimensions=(2, 2),
                                scan_mode='sequential',
                                units={'independent': 'V', 'dependent': 'A'},
                                additional_info={})
        return SpectralData(df, meta)

    @pytest.fixture
    def geometry(self):
        return {'x_start': 0.0, 'y_start': 0.0,
                'x_end': 1e-9, 'y_end': 1e-9, 'nx': 2, 'ny': 2}

    def test_entries_are_keyed_by_column(self, spectral, geometry):
        NanosurfSTSEnhancedLoader._stamp_spectrum_meta(
            spectral, None, {}, geometry, 'Map')
        meta = spectral.metadata.additional_info['spectrum_meta']
        assert [e['column'] for e in meta] == list(spectral.spectra.columns)

    def test_positions_are_in_metres(self, spectral, geometry):
        NanosurfSTSEnhancedLoader._stamp_spectrum_meta(
            spectral, None, {}, geometry, 'Map')
        meta = spectral.metadata.additional_info['spectrum_meta']
        assert meta[0]['location_m'] == [0.0, 0.0]
        assert meta[-1]['location_m'] == pytest.approx([1e-9, 1e-9])

    def test_file_and_timestamp_are_recorded(self, spectral, geometry):
        column_files = {'Point_01': Path('/fake/first.nid')}
        NanosurfSTSEnhancedLoader._stamp_spectrum_meta(
            spectral, column_files, {'first.nid': '2026-05-02T19:00:00'},
            geometry, 'Map')
        entry = spectral.metadata.additional_info['spectrum_meta'][0]
        assert entry['file'] == 'first.nid'
        assert entry['timestamp'] == '2026-05-02T19:00:00'

    def test_no_geometry_means_no_invented_positions(self, spectral):
        NanosurfSTSEnhancedLoader._stamp_spectrum_meta(
            spectral, None, {}, None, 'Point')
        meta = spectral.metadata.additional_info['spectrum_meta']
        assert all('location_m' not in e for e in meta)
        assert 'spatial_layout' not in spectral.metadata.additional_info

    def test_one_cell_wide_map_is_a_line(self, spectral):
        NanosurfSTSEnhancedLoader._stamp_spectrum_meta(
            spectral, None, {},
            {'x_start': 0.0, 'y_start': 0.0, 'x_end': 0.0, 'y_end': 3e-9,
             'nx': 1, 'ny': 4}, 'Map')
        assert spectral.metadata.additional_info['spatial_layout'] == 'line'


class TestSessionInfo:
    """Acquisition settings carried onto the dataset."""

    def test_records_timing_and_settings(self):
        session = {
            'label': '2026May02-190000',
            'started': datetime(2026, 5, 2, 19, 0),
            'ended': datetime(2026, 5, 2, 19, 10),
            'repetition_mode': 'Repeat each position',
            'settings': {'data_points': 512, 'modulation_time': '200ms',
                         'mod_output': 'Tip voltage', 'map_dims': '8;8'},
        }
        info = NanosurfSTSEnhancedLoader._session_info(session, [Path('/f/a.nid')])
        assert info['session_label'] == '2026May02-190000'
        assert info['session_duration_s'] == 600.0
        assert info['data_points'] == 512
        assert info['mod_output'] == 'Tip voltage'
        assert info['session_files'] == ['a.nid']

    def test_empty_session_adds_nothing(self):
        assert NanosurfSTSEnhancedLoader._session_info({}, []) == {}
