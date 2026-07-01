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
from datetime import datetime

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
        assert _session_label(
            "default_2026Jun15-203637_STM-STM_Spectroscopy") == "2026Jun15-203637"
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
        assert list(ds.data.columns) == ['V', 'P1R1', 'P1R2', 'P2R1']
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
        assert list(ds.data.columns) == ['V', 'Rep_1', 'Rep_2']
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
        assert 'Z' in m['channels'] or 'I' in m['channels']
        assert m['width_m'] > 0 and m['height_m'] > 0
        loc = m['locations'][0]
        assert loc['px'] is not None and 'point_index' in loc

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
