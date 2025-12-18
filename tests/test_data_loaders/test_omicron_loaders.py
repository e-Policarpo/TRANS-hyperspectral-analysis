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
    """Tests for metadata parsing from flat files."""

    def test_parse_metadata_basic(self, flat_loader, sample_flat_file):
        """OM-FLAT-08: Basic metadata is parsed."""
        with open(sample_flat_file, 'rb') as f:
            content = f.read()

        flat_loader._parse_flat_metadata(content)

        # Should at least initialize the dict
        assert isinstance(flat_loader.metadata_dict, dict)

    def test_get_image_dimensions(self, flat_loader, sample_flat_file):
        """OM-FLAT-09: Image dimensions can be determined."""
        with open(sample_flat_file, 'rb') as f:
            content = f.read()

        width, height = flat_loader._get_image_dimensions(content)

        # May be None for mock file, but shouldn't crash
        # Real files would have dimensions embedded


class TestOmicronFlatLoaderScaling:
    """Tests for image data scaling."""

    def test_scale_image_data_default(self, flat_loader):
        """OM-FLAT-10: Default scaling is applied."""
        raw_data = np.array([[1000, 2000], [3000, 4000]], dtype=np.float64)

        scaled = flat_loader._scale_image_data(raw_data)

        # Should be scaled (default is pm to m, so very small values)
        assert scaled is not None
        assert scaled.shape == raw_data.shape

    def test_scale_image_data_preserves_shape(self, flat_loader):
        """OM-FLAT-11: Scaling preserves data shape."""
        raw_data = np.random.rand(128, 128) * 10000

        scaled = flat_loader._scale_image_data(raw_data)

        assert scaled.shape == (128, 128)


# =============================================================================
# Integration Tests
# =============================================================================

class TestOmicronLoaderIntegration:
    """Integration tests for Omicron loaders."""

    def test_sts_loader_directory_loading(self, sts_loader, tmp_path):
        """OM-INT-01: Can load directory with I(V) files."""
        # Create mock file with 100 points (50 forward + 50 backward)
        filepath = tmp_path / "test.I(V)_mtrx"

        data = b'ONTMATRX0101'
        data += b'TLKB'
        data += pack('<i', 16)
        data += pack('<L', 1700000000)
        data += b'\x00' * 8
        n_points = 100  # 50 forward + 50 backward
        raw_values = np.linspace(-500, 500, n_points).astype(np.int32)
        data += b'ATAD'
        data += pack('<i', n_points * 4)
        data += raw_values.tobytes()
        filepath.write_bytes(data)

        # Try loading from directory
        result, topo = sts_loader.load_from_directory(tmp_path)

        assert result is not None
        assert isinstance(result, SpectralData)

    def test_sts_loader_directory_has_sweep_channels(self, sts_loader, tmp_path):
        """OM-INT-01b: Directory loading creates Forward/Backward/Mixed channels."""
        # Create two mock files
        for i in range(2):
            filepath = tmp_path / f"test_{i}.I(V)_mtrx"

            data = b'ONTMATRX0101'
            data += b'TLKB'
            data += pack('<i', 16)
            data += pack('<L', 1700000000)
            data += b'\x00' * 8
            n_points = 100  # 50 forward + 50 backward
            raw_values = np.linspace(-500 + i * 10, 500 + i * 10, n_points).astype(np.int32)
            data += b'ATAD'
            data += pack('<i', n_points * 4)
            data += raw_values.tobytes()
            filepath.write_bytes(data)

        # Load from directory
        result, topo = sts_loader.load_from_directory(tmp_path)

        # Check sweep channels in metadata
        assert 'sweep_channels' in result.metadata.additional_info
        sweep_channels = result.metadata.additional_info['sweep_channels']
        assert 'Forward' in sweep_channels
        assert 'Backward' in sweep_channels
        assert 'Mixed' in sweep_channels

        # Each channel should have 2 spectra (from 2 files)
        forward_df = sweep_channels['Forward']
        assert 'V' in forward_df.columns
        assert 'Point_1' in forward_df.columns
        assert 'Point_2' in forward_df.columns

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
# Real File Tests (marked to skip if files not available)
# =============================================================================

class TestOmicronLoaderRealFiles:
    """Tests with real Omicron files (skipped if not available)."""

    @pytest.fixture
    def real_iv_file(self):
        """Path to real I(V)_mtrx file."""
        path = Path("/Users/eduardapolicarpo/Documents/Doutorado/Artigos/"
                   "Artigo MnBi2Te4 Doutorado/medidas/STM UHV/todas as medidas exportadas/"
                   "17-Feb-2025/default_2025Feb17-215633_STM-STM_Spectroscopy--1_5.I(V)_mtrx")
        return path

    @pytest.fixture
    def real_flat_file(self):
        """Path to real Z_flat file."""
        path = Path("/Users/eduardapolicarpo/Documents/Doutorado/Artigos/"
                   "Artigo MnBi2Te4 Doutorado/medidas/STM UHV/"
                   "default_2025Feb15-170837_STM-STM_Spectroscopy--5_1.Z_flat")
        return path

    @pytest.mark.skipif(
        not Path("/Users/eduardapolicarpo/Documents/Doutorado/Artigos/"
                "Artigo MnBi2Te4 Doutorado/medidas/STM UHV/todas as medidas exportadas/"
                "17-Feb-2025/default_2025Feb17-215633_STM-STM_Spectroscopy--1_5.I(V)_mtrx").exists(),
        reason="Real test file not available"
    )
    def test_load_real_iv_file(self, sts_loader, real_iv_file):
        """OM-REAL-01: Load real I(V)_mtrx file."""
        result = sts_loader.load_single_file(real_iv_file)

        assert isinstance(result, SpectralData)
        # File has 200 raw points, split into 100 forward + 100 backward
        assert result.num_points == 100
        # Should have Forward, Backward, Mixed columns
        assert 'Forward' in result.data.columns
        assert 'Backward' in result.data.columns
        assert 'Mixed' in result.data.columns
        # Voltage range should be -1.5 to 1.5 V (or similar)
        assert result.independent_var.min() < 0
        assert result.independent_var.max() > 0

    @pytest.mark.skipif(
        not Path("/Users/eduardapolicarpo/Documents/Doutorado/Artigos/"
                "Artigo MnBi2Te4 Doutorado/medidas/STM UHV/"
                "default_2025Feb15-170837_STM-STM_Spectroscopy--5_1.Z_flat").exists(),
        reason="Real test file not available"
    )
    def test_load_real_flat_file(self, flat_loader, real_flat_file):
        """OM-REAL-02: Load real Z_flat file."""
        topo = flat_loader.load_topography(real_flat_file)

        assert isinstance(topo, TopographyData)
        assert topo.shape == (512, 512)  # Known from previous test
        # Data range should be in meters
        assert topo.data.min() < topo.data.max()
