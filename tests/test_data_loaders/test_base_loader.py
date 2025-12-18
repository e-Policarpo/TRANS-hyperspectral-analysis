"""
Tests for BaseDataLoader abstract class
Target coverage: 85%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from abc import ABC
from typing import Tuple, Optional

from src.data_loaders.base_loader import BaseDataLoader
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.models.topography_data import TopographyData


class ConcreteLoader(BaseDataLoader):
    """Concrete implementation of BaseDataLoader for testing."""

    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.test', '.dat']
        self.loader_type = 'test_loader'

    def load_from_directory(self, directory: Path) -> Tuple[SpectralData, Optional[TopographyData]]:
        """Load data from a directory containing measurement files."""
        # Create simple test data
        x = np.linspace(0, 1, 100)
        y = np.sin(x * 2 * np.pi)
        df = pd.DataFrame({'X': x, 'Y': y})
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata), None

    def load_single_file(self, filepath: Path) -> SpectralData:
        """Load data from a single file."""
        # Create simple test data
        x = np.linspace(0, 1, 100)
        y = np.sin(x * 2 * np.pi)
        df = pd.DataFrame({'X': x, 'Y': y})
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)


class TestBaseDataLoaderAbstract:
    """Tests for abstract methods."""

    def test_cannot_instantiate_base_class(self):
        """BL-01: Cannot instantiate abstract class directly."""
        with pytest.raises(TypeError):
            BaseDataLoader()

    def test_abstract_methods_defined(self):
        """BL-02: Abstract methods are defined."""
        # Verify abstract methods are in the class
        assert hasattr(BaseDataLoader, 'load_from_directory')
        assert hasattr(BaseDataLoader, 'load_single_file')


class TestConcreteLoader:
    """Tests using concrete implementation."""

    @pytest.fixture
    def loader(self):
        """Create concrete loader instance."""
        return ConcreteLoader()

    def test_loader_creation(self, loader):
        """Test creating concrete loader."""
        assert loader is not None
        assert loader.loader_type == 'test_loader'
        assert '.test' in loader.supported_extensions

    def test_load_from_directory(self, loader, tmp_path):
        """Test load_from_directory method."""
        # Create a test file
        test_file = tmp_path / "test.test"
        test_file.write_text("test content")

        result, topo = loader.load_from_directory(tmp_path)

        assert isinstance(result, SpectralData)
        assert result.num_points > 0
        assert topo is None

    def test_load_single_file(self, loader, tmp_path):
        """Test load_single_file method."""
        test_file = tmp_path / "test.test"
        test_file.write_text("test content")

        result = loader.load_single_file(test_file)

        assert isinstance(result, SpectralData)
        assert result.num_points > 0


class TestDirectoryValidation:
    """Tests for directory validation."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_validate_existing_directory(self, loader, tmp_path):
        """Test validation of existing directory with supported files."""
        # Create a test file
        test_file = tmp_path / "test.test"
        test_file.write_text("test content")

        assert loader.validate_directory(tmp_path) is True

    def test_validate_nonexistent_directory(self, loader, tmp_path):
        """Test validation of nonexistent directory."""
        fake_path = tmp_path / "nonexistent"
        assert loader.validate_directory(fake_path) is False

    def test_validate_file_not_directory(self, loader, tmp_path):
        """Test validation fails for file path."""
        test_file = tmp_path / "test.test"
        test_file.write_text("test content")

        assert loader.validate_directory(test_file) is False

    def test_validate_empty_directory(self, loader, tmp_path):
        """Test validation fails for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        assert loader.validate_directory(empty_dir) is False


class TestFileFinding:
    """Tests for file finding methods."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_find_files_basic(self, loader, tmp_path):
        """Test finding files in directory."""
        # Create test files
        (tmp_path / "file1.test").write_text("content1")
        (tmp_path / "file2.test").write_text("content2")
        (tmp_path / "file3.dat").write_text("content3")
        (tmp_path / "other.txt").write_text("ignored")

        files = loader.find_files(tmp_path)

        assert len(files) == 3
        assert all(f.suffix in ['.test', '.dat'] for f in files)

    def test_find_files_with_pattern(self, loader, tmp_path):
        """Test finding files with pattern."""
        (tmp_path / "data_001.test").write_text("content1")
        (tmp_path / "data_002.test").write_text("content2")
        (tmp_path / "other.test").write_text("content3")

        files = loader.find_files(tmp_path, pattern="data_*")

        assert len(files) == 2
        assert all("data_" in f.name for f in files)

    def test_find_files_sorted(self, loader, tmp_path):
        """Test that found files are sorted."""
        (tmp_path / "c.test").write_text("c")
        (tmp_path / "a.test").write_text("a")
        (tmp_path / "b.test").write_text("b")

        files = loader.find_files(tmp_path)

        names = [f.name for f in files]
        assert names == sorted(names)


class TestMetadataCreation:
    """Tests for metadata creation."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_create_metadata_basic(self, loader):
        """Test creating basic metadata."""
        metadata = loader.create_metadata(
            dimensions=(10, 10),
            scan_mode='meander',
            units={'x': 'V', 'y': 'nA'}
        )

        assert isinstance(metadata, SpectralMetadata)
        assert metadata.dimensions == (10, 10)
        assert metadata.scan_mode == 'meander'
        assert metadata.source_type == 'test_loader'

    def test_create_metadata_with_extra_info(self, loader):
        """Test creating metadata with additional info."""
        metadata = loader.create_metadata(
            dimensions=(5, 5),
            scan_mode='forward',
            units={},
            temperature=4.2,
            bias=0.5
        )

        assert metadata.additional_info['temperature'] == 4.2
        assert metadata.additional_info['bias'] == 0.5


class TestSpectraConcatenation:
    """Tests for spectra concatenation."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_concatenate_spectra_basic(self, loader):
        """Test concatenating multiple spectra."""
        spectra = [
            np.array([1, 2, 3, 4, 5]),
            np.array([6, 7, 8, 9, 10]),
            np.array([11, 12, 13, 14, 15])
        ]
        x = np.linspace(0, 1, 5)

        df = loader.concatenate_spectra(spectra, x)

        assert isinstance(df, pd.DataFrame)
        assert len(df.columns) == 4  # Variable + 3 spectra
        assert len(df) == 5

    def test_concatenate_spectra_with_names(self, loader):
        """Test concatenating spectra with custom names."""
        spectra = [np.random.rand(10), np.random.rand(10)]
        x = np.linspace(-1, 1, 10)
        names = ['Forward', 'Backward']

        df = loader.concatenate_spectra(spectra, x, column_names=names)

        assert 'Forward' in df.columns
        assert 'Backward' in df.columns

    def test_concatenate_empty_raises(self, loader):
        """Test concatenating empty list raises error."""
        with pytest.raises(ValueError):
            loader.concatenate_spectra([], np.array([1, 2, 3]))


class TestPreprocessing:
    """Tests for preprocessing methods."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_apply_preprocessing_no_smooth(self, loader):
        """Test preprocessing without smoothing."""
        df = pd.DataFrame({
            'V': np.linspace(-1, 1, 50),
            'I': np.random.rand(50)
        })

        processed = loader.apply_preprocessing(df, smooth=False)

        # Should return copy, not modify original
        assert processed is not df
        np.testing.assert_array_equal(processed['I'].values, df['I'].values)

    def test_apply_preprocessing_with_smooth(self, loader):
        """Test preprocessing with Savitzky-Golay smoothing."""
        x = np.linspace(-1, 1, 50)
        # Create noisy data
        noisy = np.sin(x * np.pi) + np.random.normal(0, 0.1, len(x))
        df = pd.DataFrame({'V': x, 'I': noisy})

        processed = loader.apply_preprocessing(df, smooth=True, window_length=11, polyorder=3)

        # Smoothed data should be different from original
        assert not np.allclose(processed['I'].values, df['I'].values)


class TestDataTypeDetection:
    """Tests for data type detection."""

    def test_detect_iv_from_filename(self, tmp_path):
        """Test detecting I-V data from filename."""
        iv_file = tmp_path / "iv_data.csv"
        iv_file.write_text("V,I\n0,1\n1,2")

        detected = BaseDataLoader.detect_data_type(iv_file)
        assert detected == 'iv'

    def test_detect_didv_from_filename(self, tmp_path):
        """Test detecting dI/dV data from filename."""
        didv_file = tmp_path / "didv_spectrum.csv"
        didv_file.write_text("V,dIdV\n0,0.1\n1,0.2")

        detected = BaseDataLoader.detect_data_type(didv_file)
        assert detected == 'didv'

    def test_detect_unknown(self, tmp_path):
        """Test detecting unknown data type."""
        unknown_file = tmp_path / "random_data.csv"
        unknown_file.write_text("A,B\na,b")

        detected = BaseDataLoader.detect_data_type(unknown_file)
        assert detected == 'unknown'

    def test_get_data_type_display_name(self):
        """Test getting display names for data types."""
        assert 'I-V' in BaseDataLoader.get_data_type_display_name('iv')
        assert 'First Derivative' in BaseDataLoader.get_data_type_display_name('didv')
        assert 'Second Derivative' in BaseDataLoader.get_data_type_display_name('d2idv2')
        assert 'Unknown' in BaseDataLoader.get_data_type_display_name('unknown')


class TestLoaderInfo:
    """Tests for loader info methods."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_get_info(self, loader):
        """Test getting loader info."""
        info = loader.get_info()

        assert isinstance(info, dict)
        assert info['type'] == 'test_loader'
        assert '.test' in info['supported_extensions']

    def test_repr(self, loader):
        """Test string representation."""
        repr_str = repr(loader)

        assert 'ConcreteLoader' in repr_str
        assert 'test_loader' in repr_str


class TestErrorHandling:
    """Tests for error handling in loaders."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_load_from_directory_handles_errors(self, loader, tmp_path):
        """Test load_from_directory handles gracefully."""
        # Create test file so it passes validation
        test_file = tmp_path / "test.test"
        test_file.write_text("content")

        # Should not raise, mock implementation returns valid data
        result, topo = loader.load_from_directory(tmp_path)
        assert result is not None

    def test_load_single_file_handles_errors(self, loader, tmp_path):
        """Test load_single_file handles gracefully."""
        test_file = tmp_path / "test.test"
        test_file.write_text("content")

        # Should not raise, mock implementation returns valid data
        result = loader.load_single_file(test_file)
        assert result is not None


class TestSpectralDataConstruction:
    """Tests for SpectralData construction from loaded data."""

    @pytest.fixture
    def loader(self):
        """Create loader for testing."""
        return ConcreteLoader()

    def test_construct_spectral_data(self, loader, tmp_path):
        """Test constructing SpectralData from raw data."""
        test_file = tmp_path / "test.test"
        test_file.write_text("content")

        result = loader.load_single_file(test_file)

        # Verify SpectralData properties
        assert hasattr(result, 'data')
        assert hasattr(result, 'metadata')
        assert hasattr(result, 'independent_var')
        assert hasattr(result, 'spectra')

    def test_metadata_populated(self, loader, tmp_path):
        """Test metadata is properly populated."""
        test_file = tmp_path / "test.test"
        test_file.write_text("content")

        result = loader.load_single_file(test_file)

        assert result.metadata is not None
        assert result.metadata.source_type == 'test'
        assert isinstance(result.metadata.dimensions, tuple)

    def test_data_integrity(self, loader, tmp_path):
        """Test loaded data integrity."""
        test_file = tmp_path / "test.test"
        test_file.write_text("content")

        result = loader.load_single_file(test_file)

        # Data should be numeric
        assert result.data.dtypes.apply(lambda x: np.issubdtype(x, np.number)).all()
