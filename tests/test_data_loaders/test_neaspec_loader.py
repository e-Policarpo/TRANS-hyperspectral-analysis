# ============================================================================
# T.R.A.N.S. version 1.0
# Tools for Research and Analysis for Nano Spectroscopy
#
# Created by Eduarda Policarpo, in November of 2025 with love.
#
# File: test_neaspec_loader.py
# Description: Tests for NeaSpec SNOM data loaders
# ============================================================================

"""
Tests for NeaSpec SNOM data loaders.
Tests cover both NeaSpecSNOMLoader and NeaSpecSNOMEnhancedLoader.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from src.data_loaders.neaspec_snom_loader import NeaSpecSNOMLoader
from src.models.spectral_data import SpectralData, SpectralMetadata


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def neaspec_loader():
    """Create NeaSpec SNOM loader instance."""
    return NeaSpecSNOMLoader()


@pytest.fixture
def sample_neaspec_file(tmp_path):
    """Create a sample NeaSpec formatted file for testing."""
    filepath = tmp_path / "test_snom.txt"

    # Create sample NeaSpec file content
    content = """# www.neaspec.com
# Project: Test Project
# Description: Test SNOM measurement
# Date: 2025-01-01 12:00:00
# Scan Area: [µm] 10.0 10.0 0.0
# Pixel Area: [px] 5 5 10
# Demodulation Mode: Fourier
#
Row\tColumn\tWavenumber\tO0A\tO0P\tO1A\tO1P
0\t0\t1000\t0.5\t0.1\t0.3\t0.2
0\t0\t1100\t0.6\t0.2\t0.4\t0.3
0\t0\t1200\t0.7\t0.3\t0.5\t0.4
0\t1\t1000\t0.4\t0.15\t0.25\t0.15
0\t1\t1100\t0.5\t0.25\t0.35\t0.25
0\t1\t1200\t0.6\t0.35\t0.45\t0.35
1\t0\t1000\t0.55\t0.12\t0.32\t0.22
1\t0\t1100\t0.65\t0.22\t0.42\t0.32
1\t0\t1200\t0.75\t0.32\t0.52\t0.42
1\t1\t1000\t0.45\t0.18\t0.28\t0.18
1\t1\t1100\t0.55\t0.28\t0.38\t0.28
1\t1\t1200\t0.65\t0.38\t0.48\t0.38
"""
    filepath.write_text(content)
    return filepath


@pytest.fixture
def minimal_neaspec_file(tmp_path):
    """Create a minimal NeaSpec file with just required columns."""
    filepath = tmp_path / "minimal_snom.txt"

    content = """# www.neaspec.com
Row\tColumn\tWavenumber\tO0A
0\t0\t1000\t0.5
0\t0\t1100\t0.6
0\t1\t1000\t0.4
0\t1\t1100\t0.5
"""
    filepath.write_text(content)
    return filepath


# =============================================================================
# NeaSpecSNOMLoader Basic Tests
# =============================================================================

class TestNeaSpecSNOMLoaderBasic:
    """Basic tests for NeaSpecSNOMLoader."""

    def test_loader_creation(self, neaspec_loader):
        """NEA-01: Can create loader instance."""
        assert neaspec_loader is not None
        assert neaspec_loader.loader_type == 'neaspec_snom'

    def test_supported_extensions(self, neaspec_loader):
        """NEA-02: Loader has correct supported extensions."""
        assert '.txt' in neaspec_loader.supported_extensions
        assert '.dat' in neaspec_loader.supported_extensions

    def test_loader_info(self, neaspec_loader):
        """NEA-03: Loader info returns correct structure."""
        info = neaspec_loader.get_info()

        assert isinstance(info, dict)
        assert info['type'] == 'neaspec_snom'
        assert '.txt' in info['supported_extensions']


# =============================================================================
# Header Parsing Tests
# =============================================================================

class TestNeaSpecHeaderParsing:
    """Tests for NeaSpec header parsing."""

    def test_parse_header_basic(self, neaspec_loader):
        """NEA-HDR-01: Can parse basic header."""
        header_lines = [
            "# www.neaspec.com",
            "# Project: Test Project",
            "# Description: Test measurement",
            "# Date: 2025-01-01"
        ]

        metadata = neaspec_loader.parse_header(header_lines)

        assert metadata['project'] == 'Test Project'
        assert metadata['description'] == 'Test measurement'
        assert metadata['date'] == '2025-01-01'

    def test_parse_header_scan_area(self, neaspec_loader):
        """NEA-HDR-02: Can parse scan area from header."""
        header_lines = [
            "# Scan Area: [µm] 10.5 20.3 5.0"
        ]

        metadata = neaspec_loader.parse_header(header_lines)

        assert metadata['scan_area'] is not None
        assert metadata['scan_area'] == pytest.approx((10.5, 20.3, 5.0))

    def test_parse_header_pixel_area(self, neaspec_loader):
        """NEA-HDR-03: Can parse pixel area from header."""
        header_lines = [
            "# Pixel Area: [px] 128 64 50"
        ]

        metadata = neaspec_loader.parse_header(header_lines)

        assert metadata['pixel_area'] is not None
        assert metadata['pixel_area'] == (128, 64, 50)

    def test_parse_header_demodulation(self, neaspec_loader):
        """NEA-HDR-04: Can parse demodulation mode."""
        header_lines = [
            "# Demodulation Mode: Pseudoheterodyne"
        ]

        metadata = neaspec_loader.parse_header(header_lines)

        assert metadata['demodulation'] == 'Pseudoheterodyne'

    def test_parse_header_empty(self, neaspec_loader):
        """NEA-HDR-05: Returns default metadata for empty header."""
        metadata = neaspec_loader.parse_header([])

        assert metadata['project'] == ''
        assert metadata['demodulation'] == 'Fourier'


# =============================================================================
# Column Parsing Tests
# =============================================================================

class TestNeaSpecColumnParsing:
    """Tests for column parsing."""

    def test_parse_data_columns(self, neaspec_loader):
        """NEA-COL-01: Can parse column header line."""
        header_line = "Row\tColumn\tWavenumber\tO0A\tO0P\tO1A\tO1P"

        columns = neaspec_loader.parse_data_columns(header_line)

        assert len(columns) == 7
        assert columns[0] == 'Row'
        assert columns[1] == 'Column'
        assert columns[2] == 'Wavenumber'
        assert 'O0A' in columns
        assert 'O1P' in columns

    def test_parse_data_columns_whitespace(self, neaspec_loader):
        """NEA-COL-02: Handles whitespace in column names."""
        header_line = "  Row  \t  Column  \t  Wavenumber  "

        columns = neaspec_loader.parse_data_columns(header_line)

        assert columns[0] == 'Row'
        assert columns[1] == 'Column'
        assert columns[2] == 'Wavenumber'


# =============================================================================
# File Loading Tests
# =============================================================================

class TestNeaSpecFileLoading:
    """Tests for file loading."""

    def test_load_single_file(self, neaspec_loader, sample_neaspec_file):
        """NEA-LOAD-01: Can load sample NeaSpec file."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        assert isinstance(result, SpectralData)
        assert result.num_spectra > 0
        assert result.num_points > 0

    def test_load_single_file_metadata(self, neaspec_loader, sample_neaspec_file):
        """NEA-LOAD-02: Loaded data has correct metadata."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        assert result.metadata.source_type == 'neaspec_snom'
        assert result.metadata.scan_mode == 'raster'
        assert 'cm^-1' in result.metadata.units.get('independent', '')

    def test_load_single_file_harmonics(self, neaspec_loader, sample_neaspec_file):
        """NEA-LOAD-03: Loaded data contains harmonic channels."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        # Check for harmonic channels in metadata
        assert 'harmonics' in result.metadata.additional_info or 'harmonic_channels' in result.metadata.additional_info

    def test_load_minimal_file(self, neaspec_loader, minimal_neaspec_file):
        """NEA-LOAD-04: Can load minimal NeaSpec file."""
        result = neaspec_loader.load_single_file(minimal_neaspec_file)

        assert isinstance(result, SpectralData)
        assert result.num_spectra == 2  # 2 positions
        assert result.num_points == 2  # 2 wavenumbers

    def test_load_nonexistent_file_raises(self, neaspec_loader, tmp_path):
        """NEA-LOAD-05: Loading nonexistent file raises error."""
        fake_path = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            neaspec_loader.load_single_file(fake_path)


# =============================================================================
# Directory Loading Tests
# =============================================================================

class TestNeaSpecDirectoryLoading:
    """Tests for directory loading."""

    def test_load_from_directory(self, neaspec_loader, sample_neaspec_file):
        """NEA-DIR-01: Can load from directory."""
        directory = sample_neaspec_file.parent

        result, topo = neaspec_loader.load_from_directory(directory)

        assert isinstance(result, SpectralData)
        assert topo is None  # NeaSpec doesn't include topography

    def test_load_from_empty_directory_raises(self, neaspec_loader, tmp_path):
        """NEA-DIR-02: Loading from empty directory raises error."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(ValueError):
            neaspec_loader.load_from_directory(empty_dir)

    def test_validate_directory_with_files(self, neaspec_loader, sample_neaspec_file):
        """NEA-DIR-03: Validates directory with supported files."""
        directory = sample_neaspec_file.parent

        assert neaspec_loader.validate_directory(directory) is True


# =============================================================================
# Harmonic Extraction Tests
# =============================================================================

class TestNeaSpecHarmonicExtraction:
    """Tests for harmonic channel extraction."""

    def test_extract_all_harmonics(self, neaspec_loader, sample_neaspec_file):
        """NEA-HARM-01: Can extract all harmonic channels."""
        spectral_data = neaspec_loader.load_single_file(sample_neaspec_file)

        harmonics = neaspec_loader.extract_all_harmonics(spectral_data)

        assert isinstance(harmonics, dict)
        assert len(harmonics) >= 1  # At least main channel

    def test_harmonic_data_shapes_match(self, neaspec_loader, sample_neaspec_file):
        """NEA-HARM-02: All harmonic channels have matching shapes."""
        spectral_data = neaspec_loader.load_single_file(sample_neaspec_file)
        harmonics = neaspec_loader.extract_all_harmonics(spectral_data)

        # All channels should have same number of points and spectra
        shapes = [(h.num_points, h.num_spectra) for h in harmonics.values()]
        assert len(set(shapes)) == 1  # All shapes are the same


# =============================================================================
# Data Validation Tests
# =============================================================================

class TestNeaSpecDataValidation:
    """Tests for data validation."""

    def test_wavenumber_ordering(self, neaspec_loader, sample_neaspec_file):
        """NEA-VAL-01: Wavenumbers are properly sorted."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        wavenumbers = result.independent_var

        # Check wavenumbers are sorted
        assert np.all(np.diff(wavenumbers) >= 0) or np.all(np.diff(wavenumbers) <= 0)

    def test_data_numeric(self, neaspec_loader, sample_neaspec_file):
        """NEA-VAL-02: All data is numeric."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        # All columns should be numeric
        assert result.data.dtypes.apply(lambda x: np.issubdtype(x, np.number)).all()

    def test_no_nan_values(self, neaspec_loader, sample_neaspec_file):
        """NEA-VAL-03: No NaN values in loaded data."""
        result = neaspec_loader.load_single_file(sample_neaspec_file)

        assert not result.data.isna().any().any()


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestNeaSpecErrorHandling:
    """Tests for error handling."""

    def test_file_without_header_marker(self, neaspec_loader, tmp_path):
        """NEA-ERR-01: Handles file without column header."""
        filepath = tmp_path / "no_header.txt"
        filepath.write_text("1 2 3\n4 5 6")

        with pytest.raises(ValueError, match="column header"):
            neaspec_loader.load_single_file(filepath)

    def test_file_without_harmonics(self, neaspec_loader, tmp_path):
        """NEA-ERR-02: Handles file without harmonic columns."""
        filepath = tmp_path / "no_harmonics.txt"
        content = """# www.neaspec.com
Row\tColumn\tWavenumber\tData
0\t0\t1000\t0.5
"""
        filepath.write_text(content)

        with pytest.raises(ValueError, match="harmonic"):
            neaspec_loader.load_single_file(filepath)


# =============================================================================
# Enhanced Loader Tests
# =============================================================================

class TestNeaSpecSNOMEnhancedLoader:
    """Tests for NeaSpecSNOMEnhancedLoader."""

    @pytest.fixture
    def enhanced_loader(self):
        """Create enhanced loader instance."""
        from src.data_loaders.neaspec_snom_enhanced import NeaSpecSNOMEnhancedLoader
        return NeaSpecSNOMEnhancedLoader()

    def test_enhanced_loader_creation(self, enhanced_loader):
        """NEA-ENH-01: Can create enhanced loader instance."""
        assert enhanced_loader is not None
        assert enhanced_loader.loader_type == 'neaspec_snom'

    def test_enhanced_loader_inherits_base(self, enhanced_loader):
        """NEA-ENH-02: Enhanced loader has base loader methods."""
        assert hasattr(enhanced_loader, 'load_single_file')
        assert hasattr(enhanced_loader, 'load_from_directory')


# =============================================================================
# Integration Tests
# =============================================================================

class TestNeaSpecIntegration:
    """Integration tests for NeaSpec loaders."""

    def test_full_workflow(self, neaspec_loader, sample_neaspec_file):
        """NEA-INT-01: Full workflow from loading to harmonic extraction."""
        # Load file
        spectral_data = neaspec_loader.load_single_file(sample_neaspec_file)

        # Extract harmonics
        harmonics = neaspec_loader.extract_all_harmonics(spectral_data)

        # Verify all harmonics are valid SpectralData
        for name, data in harmonics.items():
            assert isinstance(data, SpectralData)
            assert data.num_points > 0
            assert data.num_spectra > 0

    def test_progress_callback(self, neaspec_loader, sample_neaspec_file):
        """NEA-INT-02: Progress callback is called during loading."""
        progress_calls = []

        def callback(current, total, message):
            progress_calls.append((current, total, message))

        directory = sample_neaspec_file.parent
        neaspec_loader.load_from_directory(directory, progress_callback=callback)

        assert len(progress_calls) > 0
        # Final call should show completion
        assert progress_calls[-1][0] == progress_calls[-1][1]
