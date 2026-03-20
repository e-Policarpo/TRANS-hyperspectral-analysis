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
