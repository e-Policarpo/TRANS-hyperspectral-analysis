# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: test_omicron_loaders.py
# Description: Tests for Omicron Matrix data loaders
# ============================================================================

"""
Tests for Omicron Matrix data loaders.
Tests cover both I(V)_mtrx STS files and Z_flat/I_flat image files.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from struct import pack
from typing import Optional
from datetime import datetime, timedelta

from src.data_loaders.omicron_mtrx_loader import (  # noqa: F401
    _session_label, _session_labels)
from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader
from src.data_loaders.omicron_flat_loader import OmicronFlatLoader, OmicronImageLoader
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.models.topography_data import TopographyData


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sts_loader():
    """Create Omicron STS loader instance."""
    return OmicronMatrixSTSLoader()


@pytest.fixture
def flat_loader():
    """Create Omicron Flat loader instance."""
    return OmicronFlatLoader()


@pytest.fixture
def sample_mtrx_file(tmp_path):
    """Create a minimal mock I(V)_mtrx file for testing."""
    filepath = tmp_path / "test.I(V)_mtrx"

    # Create minimal ONTMATRX format
    data = b'ONTMATRX0101'  # Magic number

    # TLKB block (timestamp)
    data += b'TLKB'
    data += pack('<i', 16)  # size
    data += pack('<L', 1700000000)  # timestamp
    data += b'\x00' * 8  # padding

    # ATAD block (data)
    n_points = 100
    raw_values = np.linspace(-1000, 1000, n_points).astype(np.int32)
    data += b'ATAD'
    data += pack('<i', n_points * 4)  # size
    data += raw_values.tobytes()

    filepath.write_bytes(data)
    return filepath


@pytest.fixture
def sample_flat_file(tmp_path):
    """Create a minimal mock Z_flat file for testing.

    Note: The flat file format is complex. For mock testing, we create
    a simplified structure. For full integration tests, use real files.
    """
    filepath = tmp_path / "test.Z_flat"

    # Create minimal FLAT format
    data = b'FLAT0100'  # Magic number

    # Add image dimensions info (simplified - real files have more complex metadata)
    width, height = 64, 64

    # Add metadata padding with some dimension hints
    # Insert dimension values at expected offsets
    metadata = bytearray(2000)
    # Insert dimensions at offset ~100 as 32-bit integers
    metadata[100:104] = pack('<I', width)
    metadata[104:108] = pack('<I', height)
    data += bytes(metadata)

    # Add image data at the end
    image_data = np.random.randint(-1000, 1000, (height, width)).astype(np.int32)
    data += image_data.tobytes()

    filepath.write_bytes(data)
    return filepath


# =============================================================================
# OmicronMatrixSTSLoader Tests
# =============================================================================

class TestOmicronMatrixSTSLoaderBasic:
    """Basic tests for OmicronMatrixSTSLoader."""

    def test_loader_creation(self, sts_loader):
        """OM-STS-01: Can create loader instance."""
        assert sts_loader is not None
        assert sts_loader.loader_type == 'omicron_matrix_sts'

    def test_supported_extensions(self, sts_loader):
        """OM-STS-02: Loader has correct supported extensions."""
        assert '.I(V)_mtrx' in sts_loader.supported_extensions

    def test_magic_number_defined(self, sts_loader):
        """OM-STS-03: Magic number is correctly defined."""
        assert sts_loader.MAGIC_NUMBER == b'ONTMATRX0101'


class TestOmicronMatrixSTSLoaderParsing:
    """Tests for I(V)_mtrx file parsing."""

    def test_parse_valid_file(self, sts_loader, sample_mtrx_file):
        """OM-STS-04: Can parse valid I(V)_mtrx file."""
        parsed = sts_loader._parse_iv_file(sample_mtrx_file)

        assert parsed is not None
        assert 'V' in parsed
        assert 'forward' in parsed
        assert 'backward' in parsed
        assert 'mixed' in parsed
        assert len(parsed['V']) == len(parsed['forward'])
        assert len(parsed['V']) == len(parsed['backward'])
        assert len(parsed['V']) == len(parsed['mixed'])

    def test_parse_extracts_data(self, sts_loader, sample_mtrx_file):
        """OM-STS-05: Parsing extracts correct data shape (splits into halves)."""
        parsed = sts_loader._parse_iv_file(sample_mtrx_file)

        # 100 total points split into 50 forward + 50 backward
        assert parsed['n_points'] == 50
        assert len(parsed['forward']) == 50
        assert len(parsed['backward']) == 50
        assert len(parsed['mixed']) == 50
        assert len(parsed['V']) == 50

    def test_parse_forward_backward_mixed(self, sts_loader, sample_mtrx_file):
        """OM-STS-05b: Mixed is average of forward and backward."""
        parsed = sts_loader._parse_iv_file(sample_mtrx_file)

        # Mixed should be (forward + backward) / 2
        expected_mixed = (parsed['forward'] + parsed['backward']) / 2
        np.testing.assert_array_almost_equal(parsed['mixed'], expected_mixed)

    def test_parse_backward_is_reversed(self, sts_loader, tmp_path):
        """OM-STS-05c: Backward data is properly reversed from raw."""
        # Create file with known data pattern
        filepath = tmp_path / "test_pattern.I(V)_mtrx"

        data = b'ONTMATRX0101'
        data += b'TLKB'
        data += pack('<i', 16)
        data += pack('<L', 1700000000)
        data += b'\x00' * 8

        # Create 20 points: forward [0,1,2,3,4,5,6,7,8,9], backward [10,11,12,13,14,15,16,17,18,19]
        n_points = 20
        raw_values = np.arange(n_points).astype(np.int32)
        data += b'ATAD'
        data += pack('<i', n_points * 4)
        data += raw_values.tobytes()
        filepath.write_bytes(data)

        parsed = sts_loader._parse_iv_file(filepath)

        # After reversal, backward should be [19,18,17,16,15,14,13,12,11,10] scaled
        # The backward raw was [10,11,12,13,14,15,16,17,18,19], reversed to [19,18,17,16,15,14,13,12,11,10]
        # With default nA scaling (1e-9), check the order
        backward_scaled = parsed['backward']
        # Should be descending from 19e-9 to 10e-9
        assert backward_scaled[0] > backward_scaled[-1], "Backward should be reversed (high to low)"

    def test_mask_adc_rails_sets_saturation_to_nan(self, sts_loader):
        """OM-STS-05d: ADC saturation-rail codes are masked to NaN; real
        samples (including near-rail values) are left untouched."""
        raw = np.array([
            -2147483648.0,   # negative rail (0x80000000)
            2147418112.0,    # positive rail (0x7FFF0000)
            2147483647.0,    # int32 max rail (0x7FFFFFFF)
            -2104000000.0,   # near-rail but NOT a rail code → real
            12345.0,         # ordinary real sample
        ])
        masked = sts_loader._mask_adc_rails(raw)
        assert np.isnan(masked[0]) and np.isnan(masked[1]) and np.isnan(masked[2])
        assert masked[3] == -2104000000.0
        assert masked[4] == 12345.0
        # Input array is not mutated in place.
        assert raw[0] == -2147483648.0

    def test_parse_masks_saturated_samples(self, sts_loader, tmp_path):
        """OM-STS-05e: A spectroscopy file with railed samples comes back
        with NaN at the saturated positions after scaling."""
        filepath = tmp_path / "saturated.I(V)_mtrx"
        data = b'ONTMATRX0101'
        data += b'TLKB' + pack('<i', 16) + pack('<L', 1700000000) + b'\x00' * 8
        # 8 points: two railed at each end, real in the middle.
        raw_values = np.array(
            [-2147483648, -2147483648, 1000, 2000,
             3000, 4000, 2147418112, 2147418112], dtype=np.int32)
        data += b'ATAD' + pack('<i', raw_values.size * 4) + raw_values.tobytes()
        filepath.write_bytes(data)

        parsed = sts_loader._parse_iv_file(filepath)
        forward = parsed['forward']   # first half = [rail, rail, 1000, 2000]
        assert np.isnan(forward[0]) and np.isnan(forward[1])
        assert not np.isnan(forward[2]) and not np.isnan(forward[3])

    def test_parse_invalid_magic_returns_none(self, sts_loader, tmp_path):
        """OM-STS-06: Invalid magic number returns None."""
        invalid_file = tmp_path / "invalid.I(V)_mtrx"
        invalid_file.write_bytes(b'INVALIDMAGIC')

        parsed = sts_loader._parse_iv_file(invalid_file)

        assert parsed is None


class TestOmicronMatrixSTSLoaderLoading:
    """Tests for loading single files and directories."""

    def test_load_single_file(self, sts_loader, sample_mtrx_file):
        """OM-STS-07: Can load single I(V)_mtrx file."""
        result = sts_loader.load_single_file(sample_mtrx_file)

        assert isinstance(result, SpectralData)
        assert result.num_points > 0

    def test_load_single_file_has_channels(self, sts_loader, sample_mtrx_file):
        """OM-STS-07b: Single file has Forward, Backward, Mixed columns."""
        result = sts_loader.load_single_file(sample_mtrx_file)

        # Main dataframe should have V, Forward, Backward, Mixed
        assert 'V' in result.data.columns
        assert 'Forward' in result.data.columns
        assert 'Backward' in result.data.columns
        assert 'Mixed' in result.data.columns

    def test_load_single_file_sweep_channels_in_metadata(self, sts_loader, sample_mtrx_file):
        """OM-STS-07c: Sweep channels stored in metadata."""
        result = sts_loader.load_single_file(sample_mtrx_file)

        assert 'sweep_channels' in result.metadata.additional_info
        sweep_channels = result.metadata.additional_info['sweep_channels']
        assert 'Forward' in sweep_channels
        assert 'Backward' in sweep_channels
        assert 'Mixed' in sweep_channels

    def test_load_single_file_metadata(self, sts_loader, sample_mtrx_file):
        """OM-STS-08: Loaded data has correct metadata."""
        result = sts_loader.load_single_file(sample_mtrx_file)

        assert result.metadata.source_type == 'omicron_matrix_sts'
        assert 'V' in result.metadata.units.get('independent', 'V')

    def test_load_nonexistent_file_raises(self, sts_loader, tmp_path):
        """OM-STS-09: Loading nonexistent file raises error."""
        fake_path = tmp_path / "nonexistent.I(V)_mtrx"

        with pytest.raises(FileNotFoundError):
            sts_loader.load_single_file(fake_path)

    def test_load_wrong_extension_raises(self, sts_loader, tmp_path):
        """OM-STS-10: Loading wrong extension raises error."""
        wrong_file = tmp_path / "test.txt"
        wrong_file.write_text("not an I(V) file")

        with pytest.raises(ValueError):
            sts_loader.load_single_file(wrong_file)


class TestOmicronMatrixSTSLoaderScaling:
    """Tests for data scaling."""

    def test_scale_data_default(self, sts_loader):
        """OM-STS-11: Default scaling is applied when no transfer function."""
        raw_data = np.array([1000, 2000, 3000], dtype=np.float64)

        scaled = sts_loader._scale_data(raw_data)

        # Should be scaled to nA range by default
        assert np.all(np.abs(scaled) < 1e-5)  # In Amperes

    def test_get_voltage_array_default(self, sts_loader):
        """OM-STS-12: Default voltage array is generated."""
        current = np.zeros(100)

        V = sts_loader._get_voltage_array(current)

        assert len(V) == 100
        # Default is -1 to 1 V
        assert V[0] == pytest.approx(-1.0)
        assert V[-1] == pytest.approx(1.0)


class TestOmicronMatrixSTSLoaderHeaderParsing:
    """Tests for header file parsing."""

    def test_find_header_returns_none_if_missing(self, sts_loader, tmp_path):
        """OM-STS-13: Returns None if header file not found."""
        data_file = tmp_path / "test--1_1.I(V)_mtrx"
        data_file.write_bytes(b'test')

        header = sts_loader._find_header(data_file)

        # No header file exists
        assert header is None

    def test_find_header_constructs_correct_name(self, sts_loader, tmp_path):
        """OM-STS-14: Header filename is constructed correctly."""
        # Create data file and corresponding header
        data_file = tmp_path / "default_2025--1_1.I(V)_mtrx"
        data_file.write_bytes(b'test')

        header_file = tmp_path / "default_2025_0001.mtrx"
        header_file.write_bytes(b'ONTMATRX0101' + b'\x00' * 100)

        header = sts_loader._find_header(data_file)

        assert header is not None
        assert header.name == "default_2025_0001.mtrx"


# =============================================================================
# OmicronFlatLoader Tests
# =============================================================================

class TestOmicronFlatLoaderBasic:
    """Basic tests for OmicronFlatLoader."""

    def test_loader_creation(self, flat_loader):
        """OM-FLAT-01: Can create loader instance."""
        assert flat_loader is not None
        assert flat_loader.loader_type == 'omicron_flat'

    def test_supported_extensions(self, flat_loader):
        """OM-FLAT-02: Loader has correct supported extensions."""
        assert '.Z_flat' in flat_loader.supported_extensions
        assert '.I_flat' in flat_loader.supported_extensions

    def test_magic_number_defined(self, flat_loader):
        """OM-FLAT-03: Magic number is correctly defined."""
        assert flat_loader.MAGIC_NUMBER == b'FLAT0100'

    def test_alias_class_exists(self):
        """OM-FLAT-04: OmicronImageLoader alias exists."""
        loader = OmicronImageLoader()
        assert isinstance(loader, OmicronFlatLoader)


class TestOmicronFlatLoaderLoading:
    """Tests for loading flat files."""

    @pytest.mark.xfail(reason="Mock flat file may not have valid structure")
    def test_load_topography_valid_file(self, flat_loader, sample_flat_file):
        """OM-FLAT-05: Can load topography from valid file.

        Note: This test may fail with mock files due to complex file format.
        Use real file tests (TestOmicronLoaderRealFiles) for full validation.
        """
        topo = flat_loader.load_topography(sample_flat_file)

        assert isinstance(topo, TopographyData)
        assert topo.data is not None
        assert topo.shape[0] > 0
        assert topo.shape[1] > 0

    def test_load_topography_nonexistent_raises(self, flat_loader, tmp_path):
        """OM-FLAT-06: Loading nonexistent file raises error."""
        fake_path = tmp_path / "nonexistent.Z_flat"

        with pytest.raises(FileNotFoundError):
            flat_loader.load_topography(fake_path)

    @pytest.mark.xfail(reason="Mock flat file may not have valid structure")
    def test_load_single_file_returns_spectral_data(self, flat_loader, sample_flat_file):
        """OM-FLAT-07: load_single_file returns SpectralData with topography.

        Note: This test may fail with mock files due to complex file format.
        Use real file tests (TestOmicronLoaderRealFiles) for full validation.
        """
        result = flat_loader.load_single_file(sample_flat_file)

        assert isinstance(result, SpectralData)
        assert result.topography is not None


class TestOmicronFlatLoaderMetadata:
    """Tests for header parsing from flat files."""

    @pytest.mark.xfail(reason="Mock flat file does not have valid FLAT0100 structure")
    def test_parse_header_basic(self, flat_loader, sample_flat_file):
        """OM-FLAT-08: Basic header is parsed from valid file."""
        with open(sample_flat_file, 'rb') as f:
            content = f.read()

        result = flat_loader._parse_flat_header(content)

        assert result is not None
        assert 'axes' in result
        assert 'data_offset' in result
        assert 'data_count' in result

    def test_load_flat_file_invalid_magic(self, flat_loader, tmp_path):
        """OM-FLAT-09: Invalid magic number returns None from _load_flat_file."""
        bad_file = tmp_path / "bad.Z_flat"
        bad_file.write_bytes(b'BADMAGIC' + b'\x00' * 200)

        result = flat_loader._load_flat_file(bad_file)

        assert result is None


class TestOmicronFlatLoaderScaling:
    """Tests for transfer function scaling."""

    def test_apply_transfer_linear1d(self, flat_loader):
        """OM-FLAT-10: TFF_Linear1D scaling is applied correctly."""
        raw_data = np.array([1000, 2000, 3000, 4000], dtype=np.float64)
        xfer = {
            'name': 'TFF_Linear1D',
            'unit': 'm',
            'params': {'Offset': 0.0, 'Factor': 1e12},
        }

        scaled = flat_loader._apply_transfer_function(raw_data, xfer)

        assert scaled is not None
        assert scaled.shape == raw_data.shape
        np.testing.assert_allclose(scaled, raw_data / 1e12)

    def test_apply_transfer_multilinear1d(self, flat_loader):
        """OM-FLAT-11: TFF_MultiLinear1D scaling is applied correctly."""
        raw_data = np.array([100, 200, 300], dtype=np.float64)
        xfer = {
            'name': 'TFF_MultiLinear1D',
            'unit': 'm',
            'params': {
                'Raw_1': 1.0,
                'PreOffset': 0.0,
                'Offset': 0.0,
                'NeutralFactor': 1.0,
                'PreFactor': 2.0,
            },
        }

        scaled = flat_loader._apply_transfer_function(raw_data, xfer)

        assert scaled is not None
        assert scaled.shape == raw_data.shape
        # (1.0 - 0.0) * (raw - 0.0) / (1.0 * 2.0) = raw / 2
        np.testing.assert_allclose(scaled, raw_data / 2.0)


# =============================================================================
# Integration Tests
# =============================================================================

class TestOmicronLoaderIntegration:
    """Integration tests for Omicron loaders."""

    def test_directory_without_header_raises(self, sts_loader, tmp_path):
        """OM-INT-01: Directory import now requires a session header.

        The session-based redesign enumerates files from the ``_0001.mtrx``
        header (and scales via access2theMatrix). A directory with only loose
        data files and no header is rejected rather than silently guessed.
        """
        filepath = tmp_path / "test.I(V)_mtrx"
        data = b'ONTMATRX0101' + b'TLKB' + pack('<i', 16) + pack('<L', 1700000000)
        data += b'\x00' * 8
        raw_values = np.linspace(-500, 500, 100).astype(np.int32)
        data += b'ATAD' + pack('<i', 100 * 4) + raw_values.tobytes()
        filepath.write_bytes(data)

        with pytest.raises(ValueError):
            sts_loader.load_from_directory(tmp_path)

    @pytest.mark.xfail(reason="Mock flat file may not have valid structure")
    def test_flat_loader_directory_loading(self, flat_loader, tmp_path):
        """OM-INT-02: Can load directory with flat files.

        Note: This test may fail with mock files due to complex file format.
        Use real file tests (TestOmicronLoaderRealFiles) for full validation.
        """
        # Create mock file
        filepath = tmp_path / "test.Z_flat"

        data = b'FLAT0100'
        data += b'\x00' * 1000
        image_data = np.random.randint(-1000, 1000, (32, 32)).astype(np.int32)
        data += image_data.tobytes()
        filepath.write_bytes(data)

        # Try loading from directory
        result, topo = flat_loader.load_from_directory(tmp_path)

        # For flat files, topo should be loaded
        assert topo is not None


# =============================================================================
# Pure helper tests (no access2theMatrix / no real data needed)
# =============================================================================

class TestOmicronHelpers:
    """Unit tests for the module-level parsing helpers."""

    def test_parse_run_scan(self):
        from src.data_loaders.omicron_mtrx_loader import _parse_run_scan
        assert _parse_run_scan(
            "default_2026Jun15-203637_STM-STM_Spectroscopy--12_5.I(V)_mtrx") == (12, 5)
        assert _parse_run_scan("default--1_1.Z_mtrx") == (1, 1)
        assert _parse_run_scan("garbage_no_marker") == (0, 0)

    def test_session_label(self):
        from src.data_loaders.omicron_mtrx_loader import _session_label
        # The acquisition time is dropped — see TestOmicronSessionLabels for
        # the date-collision case where it is kept.
        assert _session_label(
            "default_2026Jun15-203637_STM-STM_Spectroscopy") == "2026Jun15"
        assert _session_label(
            "default_2026Jun15-203637_STM-STM_Spectroscopy",
            keep_time=True) == "2026Jun15-203637"
        # Falls back to the whole base name when the convention doesn't match.
        assert _session_label("oddname") == "oddname"

    def test_read_tlkb_seconds(self, tmp_path):
        from src.data_loaders.omicron_mtrx_loader import _read_tlkb_seconds
        p = tmp_path / "ts.I(V)_mtrx"
        # TLKB block: tag(4) + size(4) + Unix seconds (uint64 LE)
        p.write_bytes(b'ONTMATRX0101' + b'TLKB' + pack('<i', 16)
                      + pack('<Q', 1781569727) + b'\x00' * 8)
        ts = _read_tlkb_seconds(p)
        assert ts is not None and ts.year == 2026

    def test_read_tlkb_seconds_missing(self, tmp_path):
        from src.data_loaders.omicron_mtrx_loader import _read_tlkb_seconds
        p = tmp_path / "no_tlkb.I(V)_mtrx"
        p.write_bytes(b'ONTMATRX0101' + b'\x00' * 32)
        assert _read_tlkb_seconds(p) is None

    def test_apply_rail_mask(self, sts_loader):
        scaled = np.array([1.0, 2.0, 3.0, 4.0])
        raw = np.array([-2147483648.0, 100.0, 2147418112.0, 200.0])
        out = sts_loader._apply_rail_mask(scaled, raw)
        assert np.isnan(out[0]) and np.isnan(out[2])
        assert out[1] == 2.0 and out[3] == 4.0
        # Length mismatch is a no-op (returns input untouched).
        assert sts_loader._apply_rail_mask(scaled, raw[:2]) is scaled


# =============================================================================
# Session / batch dataset builders (synthetic sessions, no real data needed)
# =============================================================================

class TestOmicronSessionBuilders:
    """Tests for build_overview_dataset / build_point_dataset."""

    @staticmethod
    def _fake_session(extra_odd_point=False):
        V = np.linspace(-1.0, 1.0, 10)

        def spec(o):
            return np.linspace(o, o + 1, 10)

        batch1 = {
            'location_px': (10, 20), 'location_m': (1e-6, 2e-6),
            'parent_image': 'scan--1_1.Z_mtrx', 'channel': 'I(V)', 'V': V,
            'first_run': 1, 'point_index': 1,
            'forward': [spec(0.0), spec(1.0)],
            'backward': [spec(0.5), spec(1.5)],
            'mixed': [spec(0.25), spec(1.25)],
            'rep_timestamps': [datetime(2026, 6, 15, 21, 0, 0),
                               datetime(2026, 6, 15, 21, 1, 0)],
            'rep_files': ['a--1_1.I(V)_mtrx', 'a--1_2.I(V)_mtrx'],
            'rep_runscan': [(1, 1), (1, 2)],
            'first_timestamp': datetime(2026, 6, 15, 21, 0, 0),
        }
        batch2 = {
            'location_px': (30, 40), 'location_m': (3e-6, 4e-6),
            'parent_image': 'scan--2_1.Z_mtrx', 'channel': 'I(V)', 'V': V,
            'first_run': 2, 'point_index': 2,
            'forward': [spec(2.0)], 'backward': [spec(2.5)], 'mixed': [spec(2.25)],
            'rep_timestamps': [datetime(2026, 6, 15, 22, 0, 0)],
            'rep_files': ['a--2_1.I(V)_mtrx'], 'rep_runscan': [(2, 1)],
            'first_timestamp': datetime(2026, 6, 15, 22, 0, 0),
        }
        batches = [batch1, batch2]
        if extra_odd_point:
            oddV = np.linspace(-2.0, 2.0, 7)
            batches.append({
                'location_px': (50, 60), 'location_m': (5e-6, 6e-6),
                'parent_image': None, 'channel': 'I(V)', 'V': oddV,
                'first_run': 3, 'point_index': 3,
                'forward': [np.zeros(7)], 'backward': [np.zeros(7)],
                'mixed': [np.zeros(7)],
                'rep_timestamps': [None], 'rep_files': ['a--3_1.I(V)_mtrx'],
                'rep_runscan': [(3, 1)], 'first_timestamp': None,
            })
        return {
            'label': 'sess1', 'base': 'b', 'header': 'h', 'source_dir': '/d',
            'sample_name': 'Sample', 'dataset_name': 'DS', 'channel': 'I(V)',
            'channels_present': ['I(V)'], 'spatial_layout': 'line',
            'batches': batches, 'maps': [], 'images': [],
        }

    def test_overview_dataset(self, sts_loader):
        """OM-SESS-01: Overview overlays every (point, rep) spectrum."""
        ds = sts_loader.build_overview_dataset(self._fake_session(), 'ov')
        assert isinstance(ds, SpectralData)
        # 2 reps at pt1 + 1 rep at pt2 = 3 spectra
        assert ds.num_spectra == 3
        # Column indices are zero-padded so alphabetical ordering (tables,
        # legends, browser) matches acquisition order.
        assert list(ds.data.columns) == ['V', 'P01R01', 'P01R02', 'P02R01']
        sm = ds.metadata.additional_info['spectrum_meta']
        assert len(sm) == 3
        assert sm[0]['point_index'] == 1 and sm[0]['rep'] == 1
        assert sm[0]['location_px'] == [10, 20]
        assert sm[0]['timestamp'] is not None
        sweeps = ds.metadata.additional_info['sweep_channels']
        assert set(sweeps) == {'Forward', 'Backward', 'Mixed'}

    def test_overview_modal_length_excludes_odd_point(self, sts_loader):
        """OM-SESS-02: A point with a different point count is excluded from the
        single-axis overview (still available as its own dataset)."""
        ds = sts_loader.build_overview_dataset(
            self._fake_session(extra_odd_point=True), 'ov')
        assert ds.num_points == 10        # modal length wins
        assert ds.num_spectra == 3        # odd 7-point spectrum excluded

    def test_point_dataset(self, sts_loader):
        """OM-SESS-03: A per-point dataset holds the repetitions at one point."""
        sess = self._fake_session()
        ds = sts_loader.build_point_dataset(sess, sess['batches'][0], 'pt1')
        assert ds.num_spectra == 2  # two repetitions
        assert list(ds.data.columns) == ['V', 'Rep_01', 'Rep_02']
        assert ds.metadata.scan_mode == 'point'
        ai = ds.metadata.additional_info
        assert ai['location_px'] == [10, 20]
        assert ai['point_index'] == 1
        assert len(ai['rep_timestamps']) == 2

    def test_point_dataset_unequal_reps(self, sts_loader):
        """OM-SESS-04: A point whose repetitions differ in length keeps the
        dominant-length reps (no 'arrays must be same length' crash)."""
        sess = self._fake_session()
        b = sess['batches'][0]
        # Inject a short repetition (aborted sweep) — must not crash, must drop.
        b['mixed'].append(np.zeros(6))
        b['forward'].append(np.zeros(6))
        b['backward'].append(np.zeros(6))
        b['rep_V'] = [b['V'], b['V'], np.linspace(-1, 1, 6)]
        b['rep_timestamps'].append(None)
        b['rep_files'].append('a--1_3.I(V)_mtrx')
        ds = sts_loader.build_point_dataset(sess, b, 'pt1')
        assert ds.num_spectra == 2          # the 6-point rep is dropped
        assert ds.num_points == 10


# =============================================================================
# Real-data session tests (skipped when the data directory is absent)
# =============================================================================

# =============================================================================
# Line-scan detection (synthetic points, no real data needed)
# =============================================================================

class TestOmicronLineScanDetection:
    """Tests for _detect_line_scans / _is_line."""

    @staticmethod
    def _pt(idx, px, reps, m=None):
        return {'point_index': idx, 'location_px': px,
                'location_m': m or [px[0] * 1e-9, px[1] * 1e-9],
                'mixed': [None] * reps}

    def test_detects_straight_even_line(self, sts_loader):
        pts = [self._pt(i + 1, (10 + i * 5, 20), 3) for i in range(6)]
        ls = sts_loader._detect_line_scans(pts)
        assert len(ls) == 1
        assert ls[0]['n_points'] == 6 and ls[0]['reps'] == 3
        assert ls[0]['px_start'] == [10, 20] and ls[0]['px_end'] == [35, 20]
        assert all(p['line_scan_id'] == 1 for p in pts)
        assert [p['line_pos'] for p in pts] == [0, 1, 2, 3, 4, 5]

    def test_ignores_scattered_points(self, sts_loader):
        pts = [self._pt(i + 1, p, 3) for i, p in enumerate(
            [(10, 20), (300, 5), (150, 200), (50, 180), (280, 90)])]
        ls = sts_loader._detect_line_scans(pts)
        assert ls == []
        assert all(p['line_scan_id'] is None for p in pts)

    def test_short_runs_below_threshold_not_a_line(self, sts_loader):
        # 3 collinear points < _LINE_MIN_POINTS (4) → not flagged
        pts = [self._pt(i + 1, (10 + i * 5, 20), 3) for i in range(3)]
        assert sts_loader._detect_line_scans(pts) == []

    def test_same_spot_repeats_are_not_a_line(self, sts_loader):
        pts = [self._pt(i + 1, (42, 65), 10) for i in range(5)]
        assert sts_loader._detect_line_scans(pts) == []  # zero-length steps

    def test_interleaved_parallel_lines_split_by_rep_count(self, sts_loader):
        # A 63-rep line and a 1-rep pre-sweep interleave point-for-point in
        # acquisition order (the dia 30-06 pattern); detection per rep-count
        # must recover both as separate lines.
        pts = []
        idx = 1
        for i in range(5):
            pts.append(self._pt(idx, (100 - i * 3, 50), 63)); idx += 1
            pts.append(self._pt(idx, (98 - i * 3, 50), 1)); idx += 1
        ls = sts_loader._detect_line_scans(pts)
        assert len(ls) == 2
        assert {l['reps'] for l in ls} == {1, 63}
        assert all(l['n_points'] == 5 for l in ls)

    def test_grid_splits_into_one_line_per_row(self, sts_loader):
        # Two parallel rows (a tiny grid) become two separate line scans.
        pts = []
        idx = 1
        for y in (20, 60):
            for x in range(0, 50, 5):
                pts.append(self._pt(idx, (x, y), 4)); idx += 1
        ls = sts_loader._detect_line_scans(pts)
        assert len(ls) == 2
        assert all(l['n_points'] == 10 for l in ls)


class TestOmicronLineScanOverviewDataset:
    """build_line_scan_overview_dataset — every repetition, not their mean.

    The averaged line dataset is the kymograph; this is the raw material
    behind it, so a drifting or unstable repetition at a position can be seen
    instead of being averaged away.
    """

    @pytest.fixture
    def session_and_line(self):
        V = np.linspace(-1.0, 1.0, 6)

        def pt(pi, px, fwd, bwd, mix, pos):
            return {'point_index': pi, 'location_px': px, 'location_m': [pi, 0],
                    'V': V, 'forward': fwd, 'backward': bwd, 'mixed': mix,
                    'rep_V': [V] * len(mix), 'first_timestamp': None,
                    'line_pos': pos, 'rep_timestamps': [None] * len(mix),
                    'rep_files': [f"f{pi}_{r}" for r in range(len(mix))]}

        batches = [
            pt(1, (0, 0), [np.full(6, 1.0), np.full(6, 3.0)],
                          [np.full(6, 9.0), np.full(6, 11.0)],
                          [np.full(6, 5.0), np.full(6, 7.0)], 0),
            pt(2, (5, 0), [np.full(6, 2.0), np.full(6, 4.0)],
                          [np.full(6, 8.0), np.full(6, 10.0)],
                          [np.full(6, 5.0), np.full(6, 9.0)], 1),
        ]
        session = {'batches': batches, 'source_dir': '/d', 'sample_name': 'S',
                   'dataset_name': 'D', 'label': 'L'}
        ls = {'id': 1, 'reps': 2, 'n_points': 2, 'point_indices': [1, 2]}
        return session, ls

    def test_one_column_per_position_and_repetition(self, session_and_line):
        session, ls = session_and_line
        ds = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(session, ls, 'ov')
        assert list(ds.data.columns) == ['V', 'P01R01', 'P01R02', 'P02R01', 'P02R02']
        assert ds.num_spectra == 4

    def test_repetitions_are_not_averaged(self, session_and_line):
        session, ls = session_and_line
        ds = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(session, ls, 'ov')
        assert np.allclose(ds.data['P01R01'], 5.0)
        assert np.allclose(ds.data['P01R02'], 7.0)

    def test_matches_the_averaged_dataset(self, session_and_line):
        """Each averaged column must be the mean of its own repetitions."""
        session, ls = session_and_line
        loader = OmicronMatrixSTSLoader()
        avg = loader.build_line_scan_dataset(session, ls, 'avg')
        ov = loader.build_line_scan_overview_dataset(session, ls, 'ov')
        assert np.allclose(avg.data['P1'],
                           np.nanmean(ov.data[['P01R01', 'P01R02']].values, axis=1))

    def test_sweeps_select_the_right_curves(self, session_and_line):
        session, ls = session_and_line
        loader = OmicronMatrixSTSLoader()
        f = loader.build_line_scan_overview_dataset(session, ls, 'o', 'Forward')
        b = loader.build_line_scan_overview_dataset(session, ls, 'o', 'Backward')
        m = loader.build_line_scan_overview_dataset(session, ls, 'o', 'Mixed')
        assert np.allclose(f.data['P01R01'], 1.0)
        assert np.allclose(b.data['P01R01'], 9.0)
        assert np.allclose(m.data['P01R01'], 5.0)
        assert f.metadata.additional_info['sweep_direction'] == 'Forward'

    def test_columns_are_numbered_along_the_line(self, session_and_line):
        """P1 is where the line starts, whatever the session-wide indices."""
        session, ls = session_and_line
        session['batches'][0]['point_index'] = 42
        session['batches'][1]['point_index'] = 7
        session['batches'][0]['line_pos'] = 0
        session['batches'][1]['line_pos'] = 1
        ls['point_indices'] = [42, 7]
        ds = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(session, ls, 'ov')
        assert list(ds.data.columns)[1] == 'P01R01'
        meta = ds.metadata.additional_info['spectrum_meta']
        assert meta[0]['point_index'] == 42      # the real index is kept
        assert meta[0]['line_pos'] == 0

    def test_metadata_marks_it_unaveraged(self, session_and_line):
        session, ls = session_and_line
        ai = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(
            session, ls, 'ov').metadata.additional_info
        assert ai['matrix_kind'] == 'line_scan_overview'
        assert ai['averaged_over_reps'] is False
        assert ai['line_scan_id'] == 1
        assert ai['line_scan_points'] == 2
        assert len(ai['spectrum_meta']) == 4

    def test_spectrum_meta_records_position_rep_and_file(self, session_and_line):
        session, ls = session_and_line
        meta = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(
            session, ls, 'ov').metadata.additional_info['spectrum_meta']
        second = meta[1]
        assert second['column'] == 'P01R02'
        assert second['rep'] == 2
        assert second['line_pos'] == 0
        assert second['file'] == 'f1_1'

    def test_odd_length_repetitions_are_dropped(self, session_and_line):
        """A shorter aborted sweep cannot share the frame's V axis."""
        session, ls = session_and_line
        session['batches'][0]['mixed'][1] = np.full(3, 99.0)
        ds = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(session, ls, 'ov')
        assert 'P01R02' not in ds.data.columns
        assert 'P01R01' in ds.data.columns

    def test_batches_without_per_rep_files_still_build(self, session_and_line):
        session, ls = session_and_line
        for b in session['batches']:
            b.pop('rep_files'); b.pop('rep_timestamps')
        ds = OmicronMatrixSTSLoader().build_line_scan_overview_dataset(session, ls, 'ov')
        assert ds.num_spectra == 4
        assert ds.metadata.additional_info['spectrum_meta'][0]['file'] is None


class TestOmicronLineScanDataset:
    """Tests for build_line_scan_dataset (one column per position = rep mean)."""

    def test_columns_are_per_position_rep_averages(self, sts_loader):
        V = np.linspace(-1.0, 1.0, 8)

        def pt(pi, px, mixeds, pos):
            return {'point_index': pi, 'location_px': px, 'location_m': [0, 0],
                    'V': V, 'forward': mixeds, 'backward': mixeds,
                    'mixed': mixeds, 'rep_V': [V] * len(mixeds),
                    'first_timestamp': None, 'line_pos': pos}

        batches = [
            pt(1, (0, 0), [np.full(8, 2.0), np.full(8, 4.0)], 0),    # mean 3
            pt(2, (5, 0), [np.full(8, 10.0), np.full(8, 20.0)], 1),  # mean 15
            pt(3, (10, 0), [np.full(8, 1.0), np.full(8, 3.0)], 2),   # mean 2
        ]
        session = {'batches': batches, 'source_dir': '/d', 'sample_name': 'S',
                   'dataset_name': 'D', 'label': 'L'}
        ls = {'id': 1, 'reps': 2, 'n_points': 3, 'point_indices': [1, 2, 3]}
        ds = sts_loader.build_line_scan_dataset(session, ls, 'line')
        assert list(ds.data.columns) == ['V', 'P1', 'P2', 'P3']  # one col / position
        assert np.allclose(ds.data['P1'], 3.0)
        assert np.allclose(ds.data['P2'], 15.0)
        assert np.allclose(ds.data['P3'], 2.0)
        ai = ds.metadata.additional_info
        assert ai['matrix_kind'] == 'line_scan'
        assert ai['averaged_over_reps'] is True
        assert ai['spectrum_meta'][1]['point_index'] == 2

    def test_sweep_selects_forward_backward_mixed(self, sts_loader):
        V = np.linspace(-1.0, 1.0, 4)
        fwd = [np.full(4, 1.0), np.full(4, 3.0)]     # mean 2
        bwd = [np.full(4, 10.0), np.full(4, 20.0)]   # mean 15
        mix = [np.full(4, 5.0), np.full(4, 7.0)]     # mean 6
        pt = {'point_index': 1, 'location_px': (0, 0), 'location_m': [0, 0],
              'V': V, 'forward': fwd, 'backward': bwd, 'mixed': mix,
              'rep_V': [V, V], 'first_timestamp': None, 'line_pos': 0}
        pt2 = dict(pt); pt2['point_index'] = 2; pt2['location_px'] = (5, 0)
        pt2['line_pos'] = 1
        session = {'batches': [pt, pt2], 'source_dir': '/d', 'sample_name': '',
                   'dataset_name': '', 'label': 'L'}
        ls = {'id': 1, 'reps': 2, 'n_points': 2, 'point_indices': [1, 2]}
        dF = sts_loader.build_line_scan_dataset(session, ls, 'F', 'Forward')
        dB = sts_loader.build_line_scan_dataset(session, ls, 'B', 'Backward')
        dM = sts_loader.build_line_scan_dataset(session, ls, 'M', 'Mixed')
        assert np.allclose(dF.data['P1'], 2.0)
        assert np.allclose(dB.data['P1'], 15.0)
        assert np.allclose(dM.data['P1'], 6.0)
        assert dF.metadata.additional_info['sweep_direction'] == 'Forward'
        assert dB.metadata.additional_info['sweep_direction'] == 'Backward'

    def test_nan_reps_are_ignored_in_average(self, sts_loader):
        V = np.linspace(-1.0, 1.0, 5)
        a = np.array([1.0, np.nan, 3.0, np.nan, 5.0])
        b = np.array([3.0, 2.0, np.nan, np.nan, 7.0])
        pt = {'point_index': 1, 'location_px': (0, 0), 'location_m': [0, 0],
              'V': V, 'forward': [a, b], 'backward': [a, b], 'mixed': [a, b],
              'rep_V': [V, V], 'first_timestamp': None, 'line_pos': 0}
        pt2 = dict(pt); pt2['point_index'] = 2; pt2['location_px'] = (5, 0)
        pt2['line_pos'] = 1
        session = {'batches': [pt, pt2], 'source_dir': '/d', 'sample_name': '',
                   'dataset_name': '', 'label': 'L'}
        ls = {'id': 1, 'reps': 2, 'n_points': 2, 'point_indices': [1, 2]}
        ds = sts_loader.build_line_scan_dataset(session, ls, 'line')
        # NaN-aware mean: [mean(1,3)=2, 2, 3, nan, mean(5,7)=6]
        np.testing.assert_allclose(ds.data['P1'].values,
                                   [2.0, 2.0, 3.0, np.nan, 6.0])


class TestOmicronAreaBinding:
    """Spectrum → scan-map binding by acquisition time + scan area."""

    @staticmethod
    def _geom(w=1e-8, h=1e-8, x=0.0, y=0.0, angle=0.0, ts=None):
        return {'width_m': w, 'height_m': h, 'x_offset_m': x,
                'y_offset_m': y, 'angle': angle, 'timestamp': ts}

    @staticmethod
    def _groups(*specs):
        """specs: (run, scan, geom) → the {(run,scan): {chan: (path, info)}}
        shape _build_images passes in."""
        return {(r, s): {'Z': (Path(f'x--{r}_{s}.Z_mtrx'), g)}
                for r, s, g in specs}

    @staticmethod
    def _batch(idx, ts=None, run=None):
        return {'point_index': idx, 'first_timestamp': ts, 'parent_run': run}

    def test_rescans_of_one_area_share_their_spectra(self, sts_loader):
        """Re-scanning the same spot creates a new (run, scan) but the same
        physical area — the spectra must show on every one of those maps."""
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups(
            (5, 1, self._geom(x=1e-9, y=2e-9, ts=t)),
            (11, 1, self._geom(x=1.1e-9, y=2.1e-9,
                               ts=t + timedelta(minutes=10))),
        )
        b = self._batch(1, ts=t + timedelta(minutes=1), run=5)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [b])
        # Both scans landed in one area...
        assert area_of_rs[(5, 1)] == area_of_rs[(11, 1)]
        # ...and the spectrum shows on it.
        assert by_area[area_of_rs[(5, 1)]] == [b]

    def test_spectra_never_leak_onto_a_different_area(self, sts_loader):
        """The Run-Cycle bug: a later scan of a *different* area in the same
        run cycle used to inherit the spectra."""
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups(
            (12, 1, self._geom(w=8e-6, h=8e-6, ts=t)),
            # Same run cycle, but a much smaller window somewhere else.
            (12, 6, self._geom(w=2.34e-6, h=1.56e-6, x=-2.8e-6, y=1.4e-6,
                               ts=t + timedelta(minutes=30))),
        )
        b = self._batch(2, ts=t + timedelta(minutes=1), run=12)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [b])
        assert area_of_rs[(12, 1)] != area_of_rs[(12, 6)]
        assert by_area.get(area_of_rs[(12, 1)]) == [b]
        assert by_area.get(area_of_rs[(12, 6)]) is None

    def test_the_recorded_run_cycle_beats_the_timestamp(self, sts_loader):
        """MATRIX states which scan a spectrum belongs to; the timestamp is
        only a guess, and a wrong one whenever the spectrum was taken during
        a scan (see test_spectra_taken_during_a_scan_stay_on_it)."""
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups(
            (1, 1, self._geom(x=0.0, ts=t)),
            (2, 1, self._geom(x=5e-7, ts=t + timedelta(minutes=10))),
        )
        late = self._batch(1, ts=t + timedelta(minutes=20), run=1)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [late])
        assert by_area[area_of_rs[(1, 1)]] == [late]
        assert area_of_rs[(2, 1)] not in by_area

    def test_spectra_taken_during_a_scan_stay_on_it(self, sts_loader):
        """The 21-Jul bug, in miniature.

        A scan image is stamped when it FINISHES, so a line scan measured
        while run 3 was in progress is timestamped before run 3's image and
        after run 2's. Binding by "the last scan before this spectrum" put it
        on run 2 — often a 6-row strip its pixel coordinates could not fit on.
        """
        t = datetime(2026, 7, 21, 14, 47, 32)
        groups = self._groups(
            (2, 1, self._geom(w=4e-6, h=7.1e-7, ts=t)),
            (3, 1, self._geom(w=4e-6, h=6.1e-7, x=4e-8,
                              ts=t + timedelta(minutes=35))),
        )
        # Measured during run 3, i.e. before run 3's image was written.
        line = [self._batch(i, ts=t + timedelta(minutes=20), run=3)
                for i in range(26)]
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, line)

        assert by_area[area_of_rs[(3, 1)]] == line
        assert area_of_rs[(2, 1)] not in by_area

    def test_a_reference_to_a_missing_scan_falls_back_to_the_timestamp(self, sts_loader):
        """The referenced scan's images may not have been exported; the
        spectrum still has to land somewhere."""
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups((1, 1, self._geom(ts=t)))
        orphan = self._batch(1, ts=t + timedelta(minutes=5), run=99)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [orphan])
        assert by_area[area_of_rs[(1, 1)]] == [orphan]

    def test_a_spectrum_is_never_placed_twice(self, sts_loader):
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups(
            (1, 1, self._geom(ts=t)),
            (2, 1, self._geom(x=5e-7, ts=t + timedelta(minutes=10))),
        )
        b = self._batch(1, ts=t + timedelta(minutes=20), run=1)
        _, by_area = sts_loader._assign_spectra_to_areas(groups, [b])
        assert sum(len(v) for v in by_area.values()) == 1

    def test_spectrum_before_any_scan_attaches_to_the_first(self, sts_loader):
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups((1, 1, self._geom(ts=t)))
        early = self._batch(1, ts=t - timedelta(minutes=5), run=1)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [early])
        assert by_area[area_of_rs[(1, 1)]] == [early]

    def test_falls_back_to_run_cycle_without_timestamps(self, sts_loader):
        """Older exports / borrowed headers have no scan timestamps; binding
        must degrade to the legacy Run-Cycle behaviour, not vanish."""
        groups = self._groups(
            (5, 1, self._geom(ts=None)),
            (9, 1, self._geom(x=5e-7, ts=None)),
        )
        b = self._batch(1, ts=None, run=9)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(groups, [b])
        assert area_of_rs[(9, 1)] == (9, 1)
        assert by_area[(9, 1)] == [b]
        assert (5, 1) not in by_area

    def test_untimestamped_spectrum_falls_back_per_item(self, sts_loader):
        """One spectrum missing a timestamp must not push the whole session
        onto the legacy path."""
        t = datetime(2026, 6, 15, 20, 0, 0)
        groups = self._groups(
            (5, 1, self._geom(ts=t)),
            (9, 1, self._geom(x=5e-7, ts=t + timedelta(minutes=10))),
        )
        timed = self._batch(1, ts=t + timedelta(minutes=1), run=5)
        untimed = self._batch(2, ts=None, run=9)
        area_of_rs, by_area = sts_loader._assign_spectra_to_areas(
            groups, [timed, untimed])
        assert timed in by_area[area_of_rs[(5, 1)]]
        assert untimed in by_area[area_of_rs[(9, 1)]]

    @pytest.mark.parametrize("g2,same", [
        ({}, True),                                    # identical
        ({'x': 1e-10}, True),                          # sub-nm drift
        ({'w': 1.02e-8, 'h': 1.02e-8}, True),          # 2 % size wobble
        ({'w': 2e-8, 'h': 2e-8}, False),               # 2x zoom
        ({'x': 5e-7}, False),                          # moved far away
        ({'angle': 0.5}, True),                        # within angle tol
        ({'angle': 30.0}, False),                      # rotated scan frame
    ])
    def test_same_area_tolerances(self, sts_loader, g2, same):
        base = self._geom()
        other = dict(base)
        for k, v in g2.items():
            other[{'w': 'width_m', 'h': 'height_m', 'x': 'x_offset_m',
                   'y': 'y_offset_m', 'angle': 'angle'}[k]] = v
        assert sts_loader._same_area(base, other) is same

    def test_degenerate_geometry_is_not_an_area(self, sts_loader):
        assert sts_loader._same_area(
            self._geom(w=0.0), self._geom(w=0.0)) is False


class TestOmicronHeaderResolution:
    """Session identity + header borrowing for header-less sessions."""

    @pytest.mark.parametrize("name,expected", [
        ("default_2026Jun15-203637_STM-STM_Spectroscopy--3_1.I(V)_mtrx",
         "default_2026Jun15-203637_STM-STM_Spectroscopy"),
        ("default_2026Jun15-203637_STM-STM_Spectroscopy--12_4.Z_mtrx",
         "default_2026Jun15-203637_STM-STM_Spectroscopy"),
        # A header maps to the same base as its data files.
        ("default_2026Jun15-203637_STM-STM_Spectroscopy_0001.mtrx",
         "default_2026Jun15-203637_STM-STM_Spectroscopy"),
    ])
    def test_session_base_identifies_session(self, name, expected):
        assert OmicronMatrixSTSLoader._session_base(Path(name)) == expected

    def test_discover_sessions_from_data_files_not_headers(self, sts_loader,
                                                           tmp_path):
        """A directory with no header at all must still enumerate its
        sessions — that is what makes a header-less folder loadable."""
        for n in ["A_STM-STM_Spectroscopy--1_1.I(V)_mtrx",
                  "A_STM-STM_Spectroscopy--2_1.I(V)_mtrx",
                  "B_STM-STM_Spectroscopy--1_1.Z_mtrx",
                  "notes.txt"]:
            (tmp_path / n).write_bytes(b"")
        assert sts_loader._discover_session_bases(tmp_path) == [
            "A_STM-STM_Spectroscopy", "B_STM-STM_Spectroscopy"]

    def test_image_only_sessions_are_flagged(self, sts_loader, tmp_path):
        """An aborted run leaves a session with scan images but no curves. It
        must be told apart from a real one so it can be dropped *before* the
        labels are chosen — see
        :meth:`test_a_stub_session_does_not_force_its_neighbour_to_keep_time`.
        """
        for n in ["A_STM-STM_Spectroscopy--1_1.I(V)_mtrx",
                  "A_STM-STM_Spectroscopy--1_1.Z_mtrx",
                  "B_STM-STM_Spectroscopy--1_1.Z_mtrx",
                  "B_STM-STM_Spectroscopy--1_1.I_mtrx",
                  "B_STM-STM_Spectroscopy_0001.mtrx"]:
            (tmp_path / n).write_bytes(b"")
        assert sts_loader._scan_session_bases(tmp_path) == {
            "A_STM-STM_Spectroscopy": True,
            "B_STM-STM_Spectroscopy": False,
        }

    def test_own_header_is_preferred(self, sts_loader, tmp_path):
        (tmp_path / "A_0001.mtrx").write_bytes(b"")
        (tmp_path / "B_0001.mtrx").write_bytes(b"")
        header, is_own = sts_loader._resolve_header("A", tmp_path)
        assert header == tmp_path / "A_0001.mtrx"
        assert is_own is True

    def test_borrows_from_same_folder(self, sts_loader, tmp_path):
        (tmp_path / "B_0001.mtrx").write_bytes(b"")
        header, is_own = sts_loader._resolve_header("A", tmp_path)
        assert header == tmp_path / "B_0001.mtrx"
        assert is_own is False

    def test_borrows_from_sibling_folder(self, sts_loader, tmp_path):
        day1 = tmp_path / "29-Jun-2026"
        day2 = tmp_path / "30-Jun-2026"
        day1.mkdir()
        day2.mkdir()
        (day2 / "B_0001.mtrx").write_bytes(b"")
        header, is_own = sts_loader._resolve_header("A", day1)
        assert header == day2 / "B_0001.mtrx"
        assert is_own is False

    def test_no_header_anywhere_returns_none(self, sts_loader, tmp_path):
        d = tmp_path / "lonely"
        d.mkdir()
        assert sts_loader._resolve_header("A", d) == (None, False)

    def test_borrowed_curve_drops_the_foreign_location(self, sts_loader,
                                                       monkeypatch):
        """The borrowed header carries ITS OWN session's STS location. Passing
        it on would put the spectrum at a plausible but wrong coordinate, so it
        must be cleared rather than inherited."""
        foreign = {'location_px': (253, 17), 'location_m': (1e-9, 2e-9),
                   'parent_image': 'other--1_1.Z_mtrx', 'V': np.zeros(3),
                   'forward': np.zeros(3), 'backward': np.zeros(3),
                   'mixed': np.zeros(3)}
        monkeypatch.setattr(sts_loader, '_open_injected_data',
                            lambda *a, **k: True)
        monkeypatch.setattr(sts_loader, '_extract_curve',
                            lambda md, f: dict(foreign))
        tpl = {'raw_param': b'', 'param': {}, 'channel_id': {}}
        curve = sts_loader._curve_borrowed(tpl, Path("A--1_1.I(V)_mtrx"))
        assert curve['location_px'] is None
        assert curve['location_m'] is None
        assert curve['parent_image'] is None
        # ...and the curve is flagged, because absolute I may be mis-scaled by
        # a preamp-gain factor that nothing in the bricklet reveals.
        assert curve['scaling_borrowed'] is True


class TestOmicronTraceChannels:
    """Scan-direction handling, without needing a real session on disk."""

    def test_trace_labels_cover_all_four_a2m_directions(self):
        """The label map must stay in step with access2theMatrix; an unmapped
        direction would silently leak its raw name into the channel list."""
        a2m = pytest.importorskip("access2thematrix.access2thematrix")
        assert set(OmicronMatrixSTSLoader._TRACE_LABELS) == \
            set(a2m.MtrxData.ALL_2D_TRACES)

    @pytest.mark.parametrize("names,expected", [
        (['I fwd/up', 'Z fwd/up', 'Z bwd/up'], 'Z fwd/up'),   # prefer Z fwd/up
        (['I', 'Z'], 'Z'),                                     # single-pass scan
        (['I fwd/up', 'Z bwd/down'], 'Z bwd/down'),            # any Z beats I
        (['I fwd/up', 'I bwd/up'], 'I fwd/up'),                # no Z at all
        ([], None),
    ])
    def test_pick_active_channel(self, names, expected):
        assert OmicronMatrixSTSLoader._pick_active_channel(names) == expected

    def test_single_trace_scan_keeps_bare_channel_name(self, sts_loader,
                                                       monkeypatch):
        """A scan with only one direction must not be renamed to 'Z fwd/up' —
        that would break existing projects and the default-channel lookup."""
        info = {'traces': {'fwd/up': np.zeros((4, 4))}, 'data': np.zeros((4, 4)),
                'channel_name': 'Z', 'unit': 'm', 'width_m': 1e-8,
                'height_m': 1e-8, 'x_offset_m': 0.0, 'y_offset_m': 0.0,
                'angle': 0.0, 'timestamp': None}
        maps = self._build(sts_loader, monkeypatch, info)
        assert list(maps[0]['channels']) == ['Z']
        assert maps[0]['active_channel'] == 'Z'

    def test_multi_trace_scan_suffixes_every_channel(self, sts_loader,
                                                     monkeypatch):
        info = {'traces': {'fwd/up': np.zeros((4, 4)), 'bwd/up': np.ones((4, 4))},
                'data': np.zeros((4, 4)), 'channel_name': 'Z', 'unit': 'm',
                'width_m': 1e-8, 'height_m': 1e-8, 'x_offset_m': 0.0,
                'y_offset_m': 0.0, 'angle': 0.0, 'timestamp': None}
        maps = self._build(sts_loader, monkeypatch, info)
        assert set(maps[0]['channels']) == {'Z fwd/up', 'Z bwd/up'}
        assert maps[0]['channel_units'] == {'Z fwd/up': 'm', 'Z bwd/up': 'm'}

    @staticmethod
    def _build(loader, monkeypatch, info):
        """Run _build_images over one fake scan file returning ``info``."""
        monkeypatch.setattr(loader, '_image_via_a2m',
                            lambda md, f: dict(info))
        return loader._build_images(
            None, [Path('default_2026Jun15-203637--1_1.Z_mtrx')], 'L', [])[0]


class TestOmicronSessionLabels:
    """Session labels drop the acquisition time so browser rows and exported
    filenames stay readable — unless the date alone would be ambiguous."""

    _B1 = 'default_2026Jun29-203950_STM-STM_Spectroscopy'
    _B2 = 'default_2026Jun29-214512_STM-STM_Spectroscopy'
    _B3 = 'default_2026Jul02-101500_STM-STM_Spectroscopy'

    def test_time_is_dropped(self):
        assert _session_label(self._B1) == '2026Jun29'

    def test_time_can_be_kept_explicitly(self):
        assert _session_label(self._B1, keep_time=True) == '2026Jun29-203950'

    def test_distinct_dates_all_lose_their_times(self):
        labels = _session_labels([self._B1, self._B3])
        assert set(labels.values()) == {'2026Jun29', '2026Jul02'}

    def test_same_date_keeps_times_so_sessions_stay_distinct(self):
        """Two sessions on one day would otherwise merge into a single browser
        folder and collide their scan names."""
        labels = _session_labels([self._B1, self._B2])
        assert set(labels.values()) == {'2026Jun29-203950', '2026Jun29-214512'}
        assert len(set(labels.values())) == 2

    def test_unconventional_base_falls_back_to_itself(self):
        assert _session_label('random_name') == 'random_name'

    def test_a_stub_session_does_not_force_its_neighbour_to_keep_time(
            self, sts_loader, tmp_path):
        """Real regression: a same-day session holding only scan images made
        the day's real session keep its acquisition time, so the browser showed
        "2026Jun24-124501" next to plain "2026Jun16" — a clash with a folder
        that is never created, because the stub carries no data to file."""
        stub = 'default_2026Jun24-115533_STM-STM_Spectroscopy'
        real = 'default_2026Jun24-124501_STM-STM_Spectroscopy'
        for n in [f"{stub}--1_1.Z_mtrx", f"{stub}--1_1.I_mtrx",
                  f"{real}--1_1.I(V)_mtrx", f"{real}--1_1.Z_mtrx"]:
            (tmp_path / n).write_bytes(b"")
        found = sts_loader._scan_session_bases(tmp_path)
        bases = sorted(b for b, has_spectra in found.items() if has_spectra)
        assert bases == [real]
        assert _session_labels(bases) == {real: '2026Jun24'}


class TestOmicronScanImages:
    """One image entity per physical scan, carrying every channel × trace.

    Previously each channel became its own browser entry ("… Z", "… I"),
    which filled the project browser with near-identical rows. Now the
    channels ride inside one image and the viewer offers a selector.
    """

    @staticmethod
    def _images(loader, monkeypatch, info, files=None):
        monkeypatch.setattr(loader, '_image_via_a2m',
                            lambda md, f: dict(info))
        files = files or [Path('default_2026Jun15-203637--1_1.Z_mtrx')]
        return loader._build_images(None, files, 'L', [])[1]

    @staticmethod
    def _info(**over):
        base = {'traces': {'fwd/up': np.zeros((4, 5)),
                           'bwd/up': np.ones((4, 5))},
                'data': np.zeros((4, 5)), 'channel_name': 'Z', 'unit': 'm',
                'width_m': 2e-8, 'height_m': 1e-8, 'x_offset_m': 0.0,
                'y_offset_m': 0.0, 'angle': 0.0, 'timestamp': None}
        base.update(over)
        return base

    def test_one_image_per_scan_not_one_per_channel(self, sts_loader,
                                                    monkeypatch):
        images = self._images(sts_loader, monkeypatch, self._info())
        assert len(images) == 1
        name, img = images[0]
        assert img.is_multichannel
        assert set(img.channel_names) == {'Z fwd/up', 'Z bwd/up'}

    def test_image_name_has_no_channel_suffix(self, sts_loader, monkeypatch):
        """The entity is the scan, so its name is the scan title."""
        images = self._images(sts_loader, monkeypatch, self._info())
        name, img = images[0]
        assert name == img.name
        assert not name.endswith(' Z')

    def test_scan_title_is_zero_padded(self, sts_loader, monkeypatch):
        images = self._images(sts_loader, monkeypatch, self._info())
        assert images[0][0] == 'L 01_01'

    def test_default_channel_is_z_forward_up(self, sts_loader, monkeypatch):
        _, img = self._images(sts_loader, monkeypatch, self._info())[0]
        assert img.active_channel_name == 'Z fwd/up'

    def test_channel_data_is_kept_distinct(self, sts_loader, monkeypatch):
        _, img = self._images(sts_loader, monkeypatch, self._info())[0]
        assert np.allclose(img.get_channel('Z fwd/up'), 0.0)
        assert np.allclose(img.get_channel('Z bwd/up'), 1.0)

    def test_pixel_size_is_derived_from_scan_geometry(self, sts_loader,
                                                      monkeypatch):
        """20 nm over 5 columns = 4 nm/px in x; 10 nm over 4 rows = 2.5 in y."""
        _, img = self._images(sts_loader, monkeypatch, self._info())[0]
        dy, dx = img.metadata.pixel_size_nm
        assert dx == pytest.approx(4.0)
        assert dy == pytest.approx(2.5)

    def test_missing_geometry_leaves_pixel_size_unset(self, sts_loader,
                                                      monkeypatch):
        info = self._info(width_m=0.0, height_m=0.0)
        _, img = self._images(sts_loader, monkeypatch, info)[0]
        assert img.metadata.pixel_size_nm is None

    def test_channel_units_are_carried(self, sts_loader, monkeypatch):
        _, img = self._images(sts_loader, monkeypatch, self._info())[0]
        units = img.metadata.additional_info['channel_units']
        assert units == {'Z fwd/up': 'm', 'Z bwd/up': 'm'}

    def test_single_trace_scan_still_produces_an_image(self, sts_loader,
                                                       monkeypatch):
        info = self._info(traces={'fwd/up': np.zeros((4, 5))})
        images = self._images(sts_loader, monkeypatch, info)
        assert len(images) == 1
        assert images[0][1].channel_names == ['Z']


# A complete real MATRIX session (header + spectra + scan images). Smart import
# needs the whole session (access2theMatrix reads the _0001.mtrx header chain),
# so these run against a real on-disk session rather than synthetic fixtures.
_REAL_SESSION = Path(
    "/Users/eduardapolicarpo/Documents/Doutorado/Colab UFV/Artigo MnBi2Te4/"
    "STM UHV/15-Jun-2026/default_2026Jun15-203637_STM-STM_Spectroscopy_0001.mtrx")


@pytest.mark.skipif(not _REAL_SESSION.exists(),
                    reason="Real MATRIX session not available")
class TestOmicronLoaderRealSession:
    """End-to-end smart import against a real session (203637: 2 points × 5)."""

    @pytest.fixture
    def session(self, sts_loader):
        sd, _ = sts_loader.smart_load_from_file(_REAL_SESSION)
        return sd.metadata.additional_info['sessions'][0]

    def test_batches_by_location(self, session):
        """OM-REAL-01: Spectra are grouped into batches by STS location."""
        assert session['spatial_layout'] == 'line'
        assert len(session['batches']) == 2
        for b in session['batches']:
            assert len(b['mixed']) == 5            # 5 repetitions per point
            assert b['location_px'] is not None
            # The parent scan is identified by Run Cycle (exact filename is
            # skipped for speed); used to tag the scan image with this point.
            assert b['parent_run'] is not None

    def test_per_spectrum_timestamps(self, session):
        """OM-REAL-02: Each repetition carries an acquisition timestamp."""
        ts = session['batches'][0]['rep_timestamps']
        assert len(ts) == 5
        assert all(t is not None for t in ts)
        # Repetitions are acquired in sequence (monotonic non-decreasing).
        assert ts == sorted(ts)

    def test_maps_have_channels_and_locations(self, session):
        """OM-REAL-03: Scan images become multi-channel maps; the maps the
        spectra were taken on are tagged with their STS locations."""
        assert session['maps']
        tagged = [m for m in session['maps'] if m['locations']]
        assert tagged, "expected at least one map tagged with spectrum locations"
        m = tagged[0]
        # Channels are per scan direction (see OM-REAL-05); the base signal
        # name is still Z / I.
        bases = {n.split()[0] for n in m['channels']}
        assert 'Z' in bases or 'I' in bases
        assert m['width_m'] > 0 and m['height_m'] > 0
        loc = m['locations'][0]
        assert loc['px'] is not None and 'point_index' in loc

    def test_all_scan_directions_become_channels(self, session):
        """OM-REAL-05: Each acquired scan direction (trace/retrace × up/down)
        is exposed as its own map channel, not just the primary pass."""
        m = session['maps'][0]
        names = set(m['channels'])
        # This session runs X-retrace but not Y-retrace → fwd/up + bwd/up.
        assert {'Z fwd/up', 'Z bwd/up', 'I fwd/up', 'I bwd/up'} <= names
        # Forward and backward are genuinely different data, not a duplicate.
        assert not np.array_equal(m['channels']['Z fwd/up'],
                                  m['channels']['Z bwd/up'])
        # Every channel shares one pixel grid so they can live on one map.
        shapes = {v.shape for v in m['channels'].values()}
        assert len(shapes) == 1
        assert m['channel_units']['Z fwd/up'] == m['channel_units']['Z bwd/up']

    def test_default_channel_is_z_forward_up(self, session):
        """OM-REAL-06: Topography's forward/up pass is what opens by default,
        regardless of which channel the files happen to enumerate first."""
        for m in session['maps']:
            assert m['active_channel'] == 'Z fwd/up'
            assert m['active_channel'] in m['channels']

    def test_overview_and_point_datasets(self, sts_loader, session):
        """OM-REAL-04: Builders produce an overview + one dataset per point."""
        overview = sts_loader.build_overview_dataset(session, 'ov')
        assert overview.num_spectra == 10        # 2 points × 5 reps
        for b in session['batches']:
            pt = sts_loader.build_point_dataset(session, b, 'pt')
            assert pt.num_spectra == 5


_REAL_FLAT = Path(
    "/Users/eduardapolicarpo/Documents/Doutorado/Colab UFV/Artigo MnBi2Te4/"
    "STM UHV/default_2025Feb15-170837_STM-STM_Spectroscopy--5_1.Z_flat")


class TestOmicronLoaderRealFiles:
    """Tests with real Omicron flat files (skipped if not available)."""

    @pytest.mark.skipif(not _REAL_FLAT.exists(),
                        reason="Real test file not available")
    def test_load_real_flat_file(self, flat_loader):
        """OM-REAL-FLAT: Load real Z_flat file."""
        topo = flat_loader.load_topography(_REAL_FLAT)
        assert isinstance(topo, TopographyData)
        assert topo.data.min() < topo.data.max()


class TestOmicronLineOverlays:
    """Per-map line-scan outlines, used to tag lines on the scan image."""

    @staticmethod
    def _loc(idx, px, lid, pos, reps=3):
        return {'point_index': idx, 'px': list(px), 'reps': reps,
                'line_scan_id': lid, 'line_pos': pos}

    def test_groups_points_into_one_outline_per_line(self, sts_loader):
        locs = ([self._loc(20 + i, (10 + i * 5, 30), 1, i) for i in range(4)]
                + [self._loc(40 + i, (12, 60 + i * 4), 2, i) for i in range(5)])
        overlays = sts_loader._line_overlays(locs)

        assert [o['id'] for o in overlays] == [1, 2]
        assert overlays[0]['n_points'] == 4 and overlays[1]['n_points'] == 5
        assert overlays[0]['point_first'] == 20 and overlays[0]['point_last'] == 23

    def test_path_follows_the_acquisition_order(self, sts_loader):
        # Given out of order; the outline must still run pos 0 → pos 3.
        locs = [self._loc(23, (25, 30), 1, 3), self._loc(20, (10, 30), 1, 0),
                self._loc(22, (20, 30), 1, 2), self._loc(21, (15, 30), 1, 1)]
        overlay = sts_loader._line_overlays(locs)[0]

        assert overlay['px_path'] == [[10, 30], [15, 30], [20, 30], [25, 30]]
        assert overlay['px_start'] == [10, 30] and overlay['px_end'] == [25, 30]

    def test_isolated_points_are_not_outlined(self, sts_loader):
        locs = [{'point_index': 1, 'px': [3, 3], 'line_scan_id': None,
                 'line_pos': None, 'reps': 1}]
        assert sts_loader._line_overlays(locs) == []

    def test_points_without_pixels_are_skipped(self, sts_loader):
        locs = [self._loc(1, (0, 0), 1, 0), {'point_index': 2, 'px': None,
                                             'line_scan_id': 1, 'line_pos': 1}]
        # Only one usable point left → nothing to outline, but no crash.
        overlays = sts_loader._line_overlays(locs)
        assert overlays[0]['n_points'] == 1

    def test_reps_are_carried_for_the_tag(self, sts_loader):
        locs = [self._loc(5 + i, (i, 0), 1, i, reps=7) for i in range(4)]
        assert sts_loader._line_overlays(locs)[0]['reps'] == 7


class TestLineScanDatasetNaming:
    """A line scan's dataset name says how many positions it holds, how many
    repetitions each, and which point indices it spans."""

    @staticmethod
    def _expand(sessions):
        """Run the real expansion with a stub loader and backend."""
        from types import SimpleNamespace
        from src.backend.app_backend import AppBackend

        def _ds():
            return SimpleNamespace(metadata=SimpleNamespace(additional_info={}))

        loader = SimpleNamespace(
            build_line_scan_dataset=lambda session, ls, name, sweep: _ds(),
            build_line_scan_overview_dataset=lambda session, ls, name, sweep: _ds(),
            build_point_dataset=lambda session, batch, name: _ds(),
            build_overview_dataset=lambda session, name: _ds(),
        )
        backend = SimpleNamespace(omicron_sts_loader=loader)
        spectral = SimpleNamespace(
            metadata=SimpleNamespace(additional_info={'sessions': sessions}))
        return AppBackend._matrix_result_from_spectral(backend, spectral)

    @staticmethod
    def _session(line_scans):
        return {'label': 'dia30', 'batches': [], 'maps': [], 'images': [],
                'line_scans': line_scans}

    def test_name_carries_points_reps_and_span(self):
        result = self._expand([self._session([
            {'id': 1, 'n_points': 57, 'reps': 3,
             'point_indices': list(range(20, 77))}])])

        names = list(result['datasets'])
        assert any("line1 (57pts_3reps_pt20->pt76)" in n for n in names), names
        # Per sweep direction: the per-position averages, and the overview
        # holding every repetition behind them.
        line_names = [n for n in names if "line1" in n]
        assert len(line_names) == 6, line_names
        for sweep in ('Mixed', 'Forward', 'Backward'):
            assert any(n.endswith(f"· {sweep}") and "overview" not in n
                       for n in line_names), sweep
            assert any(n.endswith(f"· overview · {sweep}")
                       for n in line_names), sweep

    def test_averaged_line_stays_the_active_dataset(self):
        """The kymograph is what the user works with; the overview is extra."""
        result = self._expand([self._session([
            {'id': 1, 'n_points': 4, 'reps': 2, 'point_indices': [1, 2, 3, 4]}])])

        assert "overview" not in result['active_dataset']
        assert result['active_dataset'].endswith("· Mixed")

    def test_each_line_gets_its_own_span(self):
        result = self._expand([self._session([
            {'id': 1, 'n_points': 4, 'reps': 2, 'point_indices': [1, 2, 3, 4]},
            {'id': 2, 'n_points': 6, 'reps': 5, 'point_indices': [9, 10, 11, 12, 13, 14]},
        ])])

        names = " ".join(result['datasets'])
        assert "line1 (4pts_2reps_pt1->pt4)" in names
        assert "line2 (6pts_5reps_pt9->pt14)" in names

    def test_a_session_without_lines_still_yields_an_overview(self):
        result = self._expand([self._session([])])
        assert any("overview" in n for n in result['datasets'])


class TestPresweepLinesHidden:
    """MATRIX interleaves a one-sweep pass with the real averaged measurement
    over the same positions; only the real one is outlined on the map."""

    @staticmethod
    def _loc(idx, px, lid, pos, reps):
        return {'point_index': idx, 'px': list(px), 'reps': reps,
                'line_scan_id': lid, 'line_pos': pos}

    def _interleaved(self, reps_a=511, reps_b=1, n=8):
        """Two lines over the same path, acquired point-for-point together."""
        locs = []
        for i in range(n):
            locs.append(self._loc(2 * i + 1, (10 + i * 5, 30), 1, i, reps_a))
            locs.append(self._loc(2 * i + 2, (10 + i * 5, 30), 2, i, reps_b))
        return locs

    def test_the_single_sweep_line_is_not_outlined(self, sts_loader):
        overlays = sts_loader._line_overlays(self._interleaved())
        assert [o['id'] for o in overlays] == [1]

    def test_the_surviving_line_counts_the_hidden_sweep(self, sts_loader):
        overlays = sts_loader._line_overlays(self._interleaved())
        assert overlays[0]['presweeps'] == 1
        assert overlays[0]['reps'] == 511

    def test_a_lone_single_sweep_line_is_still_shown(self, sts_loader):
        """Nothing to hide behind — it is the only measurement there."""
        locs = [self._loc(i + 1, (10 + i * 5, 80), 3, i, 1) for i in range(6)]
        overlays = sts_loader._line_overlays(locs)
        assert [o['id'] for o in overlays] == [3]

    def test_a_single_sweep_elsewhere_is_kept(self, sts_loader):
        locs = self._interleaved()
        locs += [self._loc(100 + i, (200, 10 + i * 5), 3, i, 1) for i in range(6)]
        overlays = sts_loader._line_overlays(locs)
        assert sorted(o['id'] for o in overlays) == [1, 3]

    def test_two_multi_rep_lines_on_one_path_both_stay(self, sts_loader):
        """Only a *single* sweep is treated as a pre-sweep; two real
        measurements over the same path are both real."""
        overlays = sts_loader._line_overlays(self._interleaved(reps_a=511, reps_b=64))
        assert sorted(o['id'] for o in overlays) == [1, 2]

    def test_the_hidden_sweep_keeps_its_datasets(self, sts_loader):
        """Hiding is a map-view decision: detection still reports both lines,
        which is what the datasets are built from."""
        pts = []
        for i in range(8):
            pts.append({'point_index': 2 * i + 1, 'location_px': (10 + i * 5, 30),
                        'location_m': [0.0, 0.0], 'mixed': [None] * 5})
            pts.append({'point_index': 2 * i + 2, 'location_px': (10 + i * 5, 30),
                        'location_m': [0.0, 0.0], 'mixed': [None]})
        lines = sts_loader._detect_line_scans(pts)
        assert len(lines) == 2


class TestLocationsOnGrid:
    """Loader-side validation: a spectrum recorded against a different scan
    must not place a point outside this one."""

    @staticmethod
    def _loc(idx, px):
        return {'point_index': idx, 'px': list(px) if px else None}

    def test_points_outside_the_grid_are_dropped(self, sts_loader):
        kept = sts_loader._locations_on_grid(
            [self._loc(1, (10, 10)), self._loc(2, (300, 10)),
             self._loc(3, (10, -5))], (64, 64), 'scan')
        assert [k['point_index'] for k in kept] == [1]

    def test_the_boundary_pixels_are_inside(self, sts_loader):
        kept = sts_loader._locations_on_grid(
            [self._loc(1, (0, 0)), self._loc(2, (63, 63))], (64, 64))
        assert len(kept) == 2

    def test_a_rectangular_grid_uses_the_right_axis_for_each_coordinate(self, sts_loader):
        # 100 rows x 20 cols: x is the column, y is the row.
        kept = sts_loader._locations_on_grid(
            [self._loc(1, (19, 99)),      # inside
             self._loc(2, (99, 19))],     # x past the 20 columns
            (100, 20))
        assert [k['point_index'] for k in kept] == [1]

    def test_points_without_a_position_are_kept(self, sts_loader):
        kept = sts_loader._locations_on_grid([self._loc(1, None)], (64, 64))
        assert len(kept) == 1

    def test_an_unknown_grid_drops_nothing(self, sts_loader):
        locs = [self._loc(1, (500, 500))]
        assert sts_loader._locations_on_grid(locs, None) == locs
        assert sts_loader._locations_on_grid(locs, (0, 0)) == locs


class TestLockInSettings:
    """The modulation amplitude out of the MATRIX parameter tree.

    The whole tree is parsed into ``md.param`` already and only the STS
    location was ever read from it. Resolution needs the modulation as much as
    it needs the temperature -- the lock-in convolves dI/dV with a semi-ellipse
    of FWHM sqrt(3)*V_mod -- so a spectrum whose amplitude nobody carried
    across cannot have its resolution stated at all.
    """

    @staticmethod
    def _extract(param):
        from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader
        return OmicronMatrixSTSLoader._lockin_settings(param)

    def test_the_amplitude_and_its_source_key_are_both_recorded(self):
        """The key is recorded because the device name is not fixed across
        MATRIX versions: without it there is no way to check that the number
        came from the right parameter."""
        got = self._extract({'LockIn.Amplitude': (0.012, 'V'),
                             'LockIn.Frequency': 731.0,
                             'XYScanner.Width': 2.5e-8})

        assert got['v_mod'] == pytest.approx(0.012)
        assert got['v_mod_source_key'] == 'LockIn.Amplitude'
        assert got['lockin_frequency_hz'] == pytest.approx(731.0)

    def test_the_convention_is_flagged_as_an_assumption(self):
        """MATRIX does not say whether its amplitude is zero-to-peak, RMS or
        peak-to-peak, and the three imply resolutions differing by up to 40%.
        Recording the guess as a fact would be worse than not recording it."""
        got = self._extract({'LockIn.Amplitude': 0.010})

        assert got['v_mod_convention'] == 'zero_to_peak'
        assert got['v_mod_convention_assumed'] is True

    @pytest.mark.parametrize("key", [
        'LockIn.Amplitude', 'Lock-In.Amplitude', 'Lock_In.Ampl',
        'Spectroscopy.Modulation_Amplitude', 'LOCKIN.DEVIATION',
    ])
    def test_the_device_name_is_matched_on_fragments_not_hard_coded(self, key):
        assert self._extract({key: 0.008})['v_mod'] == pytest.approx(0.008)

    @pytest.mark.parametrize("value,expected", [
        (0.012, 0.012), ((0.012, 'V'), 0.012), ([0.012], 0.012),
        ('0.012', 0.012), ('0.012 V', 0.012),
    ])
    def test_the_value_shapes_matrix_actually_uses_are_all_read(self, value, expected):
        assert self._extract({'LockIn.Amplitude': value})['v_mod'] == pytest.approx(expected)

    def test_nothing_recorded_gives_nothing_back_rather_than_zero(self):
        """A zero would read as 'no modulation was applied', which is a
        measurement. 'Not recorded' is not."""
        for param in ({'XYScanner.Width': 2.5e-8}, {}, None, "not a dict"):
            assert self._extract(param) == {}

    def test_an_unparseable_value_is_skipped_not_guessed(self):
        assert self._extract({'LockIn.Amplitude': 'off'}) == {}
        assert self._extract({'LockIn.Enabled': True}) == {}
