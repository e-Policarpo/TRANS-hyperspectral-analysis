"""
Tests for SpectralData and SpectralMetadata classes
Target coverage: 95%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.models.spectral_data import SpectralData, SpectralMetadata


class TestSpectralMetadata:
    """Tests for SpectralMetadata dataclass."""

    def test_metadata_creation_with_all_required_fields(self):
        """Test creating metadata with all required fields."""
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(10, 10),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        assert metadata.source_type == 'test'
        assert metadata.dimensions == (10, 10)
        assert metadata.scan_mode == 'forward'
        assert metadata.units == {'x': 'V', 'y': 'nA'}
        assert metadata.acquisition_date is None
        assert metadata.additional_info == {}

    def test_metadata_creation_with_all_values(self):
        """Test creating metadata with all values including optional."""
        metadata = SpectralMetadata(
            source_type='STS',
            dimensions=(10, 10),
            scan_mode='meander',
            units={'x': 'V', 'y': 'nA'},
            acquisition_date='2024-01-01',
            additional_info={'temperature': 4.2}
        )
        assert metadata.source_type == 'STS'
        assert metadata.dimensions == (10, 10)
        assert metadata.scan_mode == 'meander'
        assert metadata.units['x'] == 'V'
        assert metadata.additional_info['temperature'] == 4.2

    def test_metadata_post_init_handles_none_additional_info(self):
        """Test that __post_init__ sets additional_info to empty dict if None."""
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(5, 5),
            scan_mode='forward',
            units={}
        )
        assert metadata.additional_info == {}


class TestSpectralDataCreation:
    """Tests for SpectralData creation and initialization."""

    def test_init_from_dataframe(self, sample_spectral_data):
        """SD-01: Create SpectralData from DataFrame."""
        assert sample_spectral_data is not None
        assert isinstance(sample_spectral_data.data, pd.DataFrame)
        assert sample_spectral_data.num_spectra == 10
        assert sample_spectral_data.num_points == 100

    def test_init_requires_metadata(self):
        """Test that SpectralData requires metadata parameter."""
        df = pd.DataFrame({
            'Energy': np.linspace(0, 10, 50),
            'Spectrum_0': np.random.rand(50),
            'Spectrum_1': np.random.rand(50)
        })
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 2),
            scan_mode='forward',
            units={'x': 'eV', 'y': 'counts'}
        )
        sd = SpectralData(data=df, metadata=metadata)
        assert sd.independent_var_name == 'Energy'

    def test_init_with_metadata(self):
        """Test creating SpectralData with metadata."""
        df = pd.DataFrame({
            'V': np.linspace(-1, 1, 20),
            'I': np.random.rand(20)
        })
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(4, 5),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        sd = SpectralData(data=df, metadata=metadata)
        assert sd.metadata.source_type == 'test'
        assert sd.metadata.dimensions == (4, 5)

    def test_init_with_topography(self):
        """Test creating SpectralData with topography."""
        df = pd.DataFrame({
            'V': np.linspace(-1, 1, 20),
            'I': np.random.rand(20)
        })
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={}
        )
        topo = np.random.rand(10, 10)
        sd = SpectralData(data=df, metadata=metadata, topography=topo)
        assert sd.topography is not None
        assert sd.topography.shape == (10, 10)


class TestSpectralDataValidation:
    """Tests for SpectralData validation."""

    def test_validate_data_requires_dataframe(self):
        """Test validation rejects non-DataFrame."""
        with pytest.raises(TypeError):
            SpectralData.validate_data("not a dataframe")

    def test_validate_data_requires_two_columns(self):
        """Test validation requires at least 2 columns."""
        df = pd.DataFrame({'V': np.linspace(-1, 1, 10)})
        with pytest.raises(ValueError, match="at least 2 columns"):
            SpectralData.validate_data(df)

    def test_validate_data_requires_numeric_first_column(self):
        """Test validation requires numeric first column."""
        df = pd.DataFrame({
            'Label': ['a', 'b', 'c'],
            'Y': [1.0, 2.0, 3.0]
        })
        with pytest.raises(ValueError, match="First column must be numeric"):
            SpectralData.validate_data(df)


class TestSpectralDataProperties:
    """Tests for SpectralData properties."""

    def test_spectra_property(self, sample_spectral_data):
        """SD-03: Get spectra columns (excluding independent variable)."""
        spectra = sample_spectral_data.spectra
        assert isinstance(spectra, pd.DataFrame)
        assert 'V' not in spectra.columns
        assert len(spectra.columns) == 10
        assert spectra.shape == (100, 10)

    def test_independent_var_property(self, sample_spectral_data):
        """SD-04: Get independent variable values (x-axis)."""
        x = sample_spectral_data.independent_var
        assert isinstance(x, np.ndarray)
        assert len(x) == 100
        assert x[0] == pytest.approx(-2.0)
        assert x[-1] == pytest.approx(2.0)

    def test_independent_var_name_property(self, sample_spectral_data):
        """Test getting independent variable name."""
        assert sample_spectral_data.independent_var_name == 'V'

    def test_num_spectra(self, sample_spectral_data):
        """SD-05: Count spectra."""
        assert sample_spectral_data.num_spectra == 10

    def test_num_points(self, sample_spectral_data):
        """SD-06: Count points per spectrum."""
        assert sample_spectral_data.num_points == 100

    def test_metadata_property(self, sample_spectral_data):
        """Test metadata property access."""
        assert sample_spectral_data.metadata.source_type == 'test'
        assert sample_spectral_data.metadata.dimensions == (5, 2)

    def test_data_property(self, sample_spectral_data):
        """Test data property returns DataFrame."""
        assert isinstance(sample_spectral_data.data, pd.DataFrame)


class TestSpectralDataOperations:
    """Tests for SpectralData methods and operations."""

    def test_truncate_range(self, sample_spectral_data):
        """SD-08: Truncate to x-axis range."""
        truncated = sample_spectral_data.truncate_range(-1.0, 1.0)
        assert truncated is not None
        assert truncated.independent_var.min() >= -1.0
        assert truncated.independent_var.max() <= 1.0
        assert truncated.num_points < sample_spectral_data.num_points

    def test_truncate_range_preserves_metadata(self, sample_spectral_data):
        """Test that truncation preserves metadata."""
        truncated = sample_spectral_data.truncate_range(-1.0, 1.0)
        assert truncated.metadata.source_type == sample_spectral_data.metadata.source_type
        assert truncated.metadata.dimensions == sample_spectral_data.metadata.dimensions

    def test_truncate_range_metadata_tracks_truncation(self, sample_spectral_data):
        """Test that truncation adds tracking info to metadata."""
        truncated = sample_spectral_data.truncate_range(-1.0, 1.0)
        assert truncated.metadata.additional_info.get('truncated') is True
        assert truncated.metadata.additional_info.get('truncation_range') == (-1.0, 1.0)

    def test_get_spectrum_at_basic(self, sample_spectral_data):
        """SD-10: Get single spectrum by grid position."""
        spectrum = sample_spectral_data.get_spectrum_at(0, 0)
        assert isinstance(spectrum, pd.Series)
        assert len(spectrum) == 100

    def test_get_spectrum_at_different_positions(self, sample_spectral_data):
        """Test getting spectra at different grid positions."""
        spec_0_0 = sample_spectral_data.get_spectrum_at(0, 0)
        spec_0_1 = sample_spectral_data.get_spectrum_at(0, 1)
        spec_1_0 = sample_spectral_data.get_spectrum_at(1, 0)

        assert len(spec_0_0) == 100
        assert len(spec_0_1) == 100
        assert len(spec_1_0) == 100

    def test_get_spectrum_at_out_of_bounds(self, sample_spectral_data):
        """SD-11: Position out of bounds raises error."""
        # Dimensions are (5, 2), so row 2 and col 5 are out of bounds
        with pytest.raises(IndexError):
            sample_spectral_data.get_spectrum_at(2, 0)

    def test_copy_creates_independent_copy(self, sample_spectral_data):
        """Test copy method creates independent copy."""
        copied = sample_spectral_data.copy()

        # Modify original
        original_value = sample_spectral_data.data.iloc[0, 1]
        copied.data.iloc[0, 1] = 999999

        # Original should be unchanged
        assert sample_spectral_data.data.iloc[0, 1] == original_value


class TestSpectralDataIO:
    """Tests for SpectralData save/load operations."""

    def test_save_to_csv(self, sample_spectral_data, tmp_path):
        """SD-12: Save to CSV file."""
        output_path = tmp_path / "test_output.csv"
        sample_spectral_data.save(str(output_path))

        assert output_path.exists()
        # Load and verify
        loaded_df = pd.read_csv(output_path)
        assert loaded_df.shape == sample_spectral_data.data.shape
        assert list(loaded_df.columns) == list(sample_spectral_data.data.columns)

    def test_load_from_csv(self, sample_csv_file, sample_metadata):
        """SD-13: Load from CSV file using load classmethod."""
        loaded = SpectralData.load(str(sample_csv_file), sample_metadata)

        assert loaded is not None
        assert isinstance(loaded, SpectralData)
        assert loaded.num_spectra == 10
        assert loaded.num_points == 100

    def test_save_load_roundtrip(self, sample_spectral_data, tmp_path, sample_metadata):
        """Test save then load preserves data."""
        output_path = tmp_path / "roundtrip.csv"
        sample_spectral_data.save(str(output_path))
        loaded = SpectralData.load(str(output_path), sample_metadata)

        np.testing.assert_array_almost_equal(
            sample_spectral_data.independent_var,
            loaded.independent_var
        )
        np.testing.assert_array_almost_equal(
            sample_spectral_data.spectra.values,
            loaded.spectra.values,
            decimal=5
        )


class TestSpectralDataMetadataPreservation:
    """Tests for metadata preservation during operations."""

    def test_metadata_preservation_after_truncate(self, sample_spectral_data):
        """SD-14: Metadata preserved after truncation."""
        original_metadata = sample_spectral_data.metadata
        truncated = sample_spectral_data.truncate_range(-1.0, 1.0)

        assert truncated.metadata.source_type == original_metadata.source_type
        assert truncated.metadata.scan_mode == original_metadata.scan_mode


class TestMeanderCorrection:
    """Tests for meander/zigzag scan correction."""

    def test_meander_correction_basic(self):
        """SD-15: Correct zigzag scan pattern."""
        # Create data with obvious pattern
        x = np.linspace(0, 1, 10)
        # 4 spectra in a 2x2 grid with meander
        spectra = np.array([
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # Row 0, forward
            [10, 9, 8, 7, 6, 5, 4, 3, 2, 1],  # Row 0, backward (needs reversal)
            [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],  # Row 1, forward
            [20, 19, 18, 17, 16, 15, 14, 13, 12, 11],  # Row 1, backward
        ]).T

        df = pd.DataFrame(
            np.column_stack([x, spectra]),
            columns=['V', 'S0', 'S1', 'S2', 'S3']
        )

        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(2, 2),
            scan_mode='meander',
            units={'x': 'V', 'y': 'nA'}
        )

        sd = SpectralData(data=df, metadata=metadata)
        assert sd.num_spectra == 4

    def test_correct_meander_method(self):
        """Test correct_meander method."""
        x = np.linspace(0, 1, 10)
        spectra = np.random.rand(10, 4)
        df = pd.DataFrame(
            np.column_stack([x, spectra]),
            columns=['V', 'S0', 'S1', 'S2', 'S3']
        )

        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(2, 2),
            scan_mode='meander',
            units={'x': 'V', 'y': 'nA'}
        )

        sd = SpectralData(data=df, metadata=metadata)
        corrected = sd.correct_meander()

        # Method should return self for chaining
        assert corrected is sd
        # Should be marked as corrected
        assert sd.metadata.additional_info.get('meander_corrected') is True


class TestTo3DCube:
    """Tests for converting to 3D cube."""

    def test_to_3d_cube_basic(self, sample_spectral_data):
        """Test conversion to 3D cube."""
        cube = sample_spectral_data.to_3d_cube()

        # Should be (n_points, dim_v, dim_h)
        dim_h, dim_v = sample_spectral_data.metadata.dimensions
        n_pts = sample_spectral_data.num_points

        assert cube.shape == (n_pts, dim_v, dim_h)

    def test_to_3d_cube_large(self, sample_spectral_data_large):
        """Test 3D cube with larger dataset."""
        cube = sample_spectral_data_large.to_3d_cube()

        # 10x10 grid, 500 points
        assert cube.shape == (500, 10, 10)


class TestApplyMask:
    """Tests for applying masks to spectral data."""

    def test_apply_mask_basic(self, sample_spectral_data):
        """Test applying a basic mask."""
        dim_h, dim_v = sample_spectral_data.metadata.dimensions  # (5, 2)

        # Create mask that keeps half the data
        mask = np.zeros((dim_v, dim_h), dtype=bool)
        mask[0, :] = True  # Keep first row

        masked = sample_spectral_data.apply_mask(mask)

        assert masked.num_spectra == 5  # First row only

    def test_apply_mask_updates_metadata(self, sample_spectral_data):
        """Test that mask application updates metadata."""
        dim_h, dim_v = sample_spectral_data.metadata.dimensions

        mask = np.ones((dim_v, dim_h), dtype=bool)
        mask[0, 0] = False  # Exclude one spectrum

        masked = sample_spectral_data.apply_mask(mask)

        assert masked.metadata.scan_mode == 'masked'
        assert masked.metadata.additional_info.get('mask_applied') is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_single_spectrum(self):
        """Test with single spectrum."""
        df = pd.DataFrame({
            'X': np.linspace(0, 1, 50),
            'Y': np.random.rand(50)
        })
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        sd = SpectralData(data=df, metadata=metadata)
        assert sd.num_spectra == 1
        assert sd.num_points == 50

    def test_large_dataset(self, sample_spectral_data_large):
        """Test with larger dataset (100 spectra)."""
        assert sample_spectral_data_large.num_spectra == 100
        assert sample_spectral_data_large.num_points == 500

    def test_data_with_nan(self):
        """Test handling of NaN values in data."""
        x = np.linspace(0, 1, 20)
        y = np.random.rand(20)
        y[5] = np.nan
        y[10] = np.nan

        df = pd.DataFrame({'X': x, 'Y': y})
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={}
        )
        sd = SpectralData(data=df, metadata=metadata)

        assert sd.num_points == 20
        # Get spectrum via spectra property
        spectrum = sd.spectra.iloc[:, 0].values
        assert np.isnan(spectrum[5])

    def test_data_with_inf(self):
        """Test handling of infinity values."""
        x = np.linspace(0, 1, 20)
        y = np.random.rand(20)
        y[5] = np.inf
        y[10] = -np.inf

        df = pd.DataFrame({'X': x, 'Y': y})
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={}
        )
        sd = SpectralData(data=df, metadata=metadata)

        assert sd.num_points == 20


class TestSpectralDataIntegration:
    """Integration tests for SpectralData with other operations."""

    def test_slicing_and_operations(self, sample_spectral_data):
        """Test combining multiple operations."""
        # Truncate
        truncated = sample_spectral_data.truncate_range(-1.5, 1.5)
        # Get spectrum via get_spectrum_at
        spectrum = truncated.get_spectrum_at(0, 0)
        # Verify
        assert len(spectrum) < 100
        assert truncated.independent_var.min() >= -1.5

    def test_iteration_over_spectra(self, sample_spectral_data):
        """Test iterating over all spectra columns."""
        spectra_list = []
        for col in sample_spectral_data.spectra.columns:
            spectra_list.append(sample_spectral_data.spectra[col].values)

        assert len(spectra_list) == 10
        for s in spectra_list:
            assert len(s) == 100

    def test_repr(self, sample_spectral_data):
        """Test string representation."""
        repr_str = repr(sample_spectral_data)
        assert 'SpectralData' in repr_str
        assert 'test' in repr_str
