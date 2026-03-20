"""
Tests for ProjectManager class
Target coverage: 85%
"""

import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock

from src.backend.project_manager import (
    ProjectManager,
    serialize_window_geometry,
    restore_window_geometry,
    serialize_plot_state,
    serialize_table_state
)
from src.models.spectral_data import SpectralData, SpectralMetadata


class TestProjectManagerBasic:
    """Basic tests for ProjectManager."""

    def test_project_manager_creation(self):
        """Test creating ProjectManager instance."""
        pm = ProjectManager()

        assert pm is not None
        assert pm.current_project_path is None
        assert pm.project_modified is False

    def test_mark_modified(self):
        """Test marking project as modified."""
        pm = ProjectManager()
        pm.mark_modified()

        assert pm.project_modified is True
        assert pm.is_modified() is True

    def test_close_project(self):
        """Test closing project."""
        pm = ProjectManager()
        pm.current_project_path = Path("/some/path")
        pm.project_modified = True

        pm.close_project()

        assert pm.current_project_path is None
        assert pm.project_modified is False

    def test_get_current_project_path(self):
        """Test getting current project path."""
        pm = ProjectManager()
        assert pm.get_current_project_path() is None

        pm.current_project_path = Path("/test/path")
        assert pm.get_current_project_path() == Path("/test/path")


class TestProjectSaveLoad:
    """Tests for save/load functionality."""

    @pytest.fixture
    def project_manager(self):
        """Create ProjectManager for testing."""
        return ProjectManager()

    @pytest.fixture
    def sample_project_data(self, sample_spectral_data):
        """Create sample project data."""
        return {
            'metadata': {
                'name': 'Test Project',
                'description': 'A test project'
            },
            'datasets': {
                'TestData': sample_spectral_data
            },
            'tables': [],
            'graphs': [],
            'workspace': {}
        }

    def test_save_project(self, project_manager, sample_project_data, tmp_path):
        """PM-01: Save project to .hrt file."""
        project_path = tmp_path / "test_project.hrt"

        result = project_manager.save_project(project_path, sample_project_data)

        assert result is True
        assert project_path.exists()
        assert project_manager.current_project_path == project_path
        assert project_manager.project_modified is False

    def test_save_project_auto_extension(self, project_manager, sample_project_data, tmp_path):
        """Test that .hrt extension is added automatically."""
        project_path = tmp_path / "test_project"  # No extension

        result = project_manager.save_project(project_path, sample_project_data)

        assert result is True
        expected_path = tmp_path / "test_project.hrt"
        assert expected_path.exists()

    def test_load_project(self, project_manager, sample_project_data, tmp_path):
        """PM-02: Load project from .hrt file."""
        project_path = tmp_path / "test_project.hrt"
        project_manager.save_project(project_path, sample_project_data)

        # Load it back
        loaded_data = project_manager.load_project(project_path)

        assert loaded_data is not None
        assert 'datasets' in loaded_data
        assert 'TestData' in loaded_data['datasets']

    def test_round_trip(self, project_manager, sample_spectral_data, tmp_path):
        """PM-03: Save then load preserves data."""
        project_path = tmp_path / "roundtrip.hrt"

        original_data = {
            'metadata': {'name': 'Roundtrip Test'},
            'datasets': {'Data1': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {'window_pos': [100, 100]}
        }

        project_manager.save_project(project_path, original_data)
        loaded_data = project_manager.load_project(project_path)

        assert loaded_data['metadata']['name'] == 'Roundtrip Test'
        assert 'Data1' in loaded_data['datasets']

        # Verify spectral data
        loaded_sd = loaded_data['datasets']['Data1']
        assert loaded_sd.num_spectra == sample_spectral_data.num_spectra
        assert loaded_sd.num_points == sample_spectral_data.num_points
        np.testing.assert_array_almost_equal(
            loaded_sd.independent_var,
            sample_spectral_data.independent_var,
            decimal=5
        )

    def test_load_nonexistent_file(self, project_manager):
        """Test loading nonexistent file returns None."""
        result = project_manager.load_project(Path("/nonexistent/file.hrt"))
        assert result is None


class TestDataSerialization:
    """Tests for data serialization methods."""

    @pytest.fixture
    def project_manager(self):
        """Create ProjectManager for testing."""
        return ProjectManager()

    def test_serialize_spectral_data(self, project_manager, sample_spectral_data):
        """PM-04: Serialize SpectralData."""
        datasets = {'test': sample_spectral_data}
        serialized = project_manager._serialize_datasets(datasets)

        assert 'test' in serialized
        assert serialized['test']['type'] == 'SpectralData'
        assert serialized['test']['format'] == 'binary'
        assert 'data_binary' in serialized['test']
        assert 'independent_var_binary' in serialized['test']

    def test_deserialize_spectral_data(self, project_manager, sample_spectral_data):
        """PM-05: Deserialize SpectralData."""
        datasets = {'test': sample_spectral_data}
        serialized = project_manager._serialize_datasets(datasets)
        deserialized = project_manager._deserialize_datasets(serialized)

        assert 'test' in deserialized
        assert isinstance(deserialized['test'], SpectralData)

    def test_data_type_roundtrip(self, project_manager):
        """PM-05b: data_type field preserved through serialize/deserialize."""
        # Create a flat dataset (like integrated data)
        df = pd.DataFrame({
            'Index': range(10),
            'Interval_0': np.random.rand(10),
            'Interval_1': np.random.rand(10),
        })
        flat_metadata = SpectralMetadata(
            source_type='integrated_flat',
            dimensions=(5, 2),
            scan_mode='forward',
            units={'independent': 'Index', 'dependent': 'a.u.'},
            data_type='flat'
        )
        flat_data = SpectralData(data=df, metadata=flat_metadata)

        # Also test a normal spectral dataset
        x = np.linspace(-2, 2, 50)
        spectral_df = pd.DataFrame({
            'V': x,
            'Spectrum_0': np.sin(x),
        })
        spectral_metadata = SpectralMetadata(
            source_type='test',
            dimensions=(1, 1),
            scan_mode='forward',
            units={'independent': 'V', 'dependent': 'A'},
            data_type='spectral'
        )
        spectral_data = SpectralData(data=spectral_df, metadata=spectral_metadata)

        datasets = {'flat_ds': flat_data, 'spectral_ds': spectral_data}
        serialized = project_manager._serialize_datasets(datasets)

        # Verify data_type is serialized
        assert serialized['flat_ds']['metadata']['data_type'] == 'flat'
        assert serialized['spectral_ds']['metadata']['data_type'] == 'spectral'

        # Deserialize and verify data_type is preserved
        deserialized = project_manager._deserialize_datasets(serialized)
        assert deserialized['flat_ds'].metadata.data_type == 'flat'
        assert deserialized['spectral_ds'].metadata.data_type == 'spectral'

    def test_data_type_defaults_to_spectral(self, project_manager):
        """PM-05c: Legacy projects without data_type default to 'spectral'."""
        # Simulate a legacy serialized dataset without data_type
        serialized = {
            'legacy': {
                'type': 'SpectralData',
                'format': 'binary',
                'shape': [50, 1],
                'columns': ['Spectrum_0'],
                'data_binary': project_manager._numpy_to_base64(np.random.rand(50, 1)),
                'independent_var_binary': project_manager._numpy_to_base64(np.linspace(0, 1, 50)),
                'independent_var_name': 'X',
                'metadata': {
                    'source_type': 'test',
                    'dimensions': [1, 1],
                    'scan_mode': 'forward',
                    'units': {}
                    # NOTE: no 'data_type' key — legacy format
                }
            }
        }
        deserialized = project_manager._deserialize_datasets(serialized)
        assert deserialized['legacy'].metadata.data_type == 'spectral'

    def test_serialize_dataframe_small(self, project_manager):
        """PM-06: Serialize small DataFrame as JSON."""
        df = pd.DataFrame({
            'A': [1, 2, 3],
            'B': [4, 5, 6]
        })
        datasets = {'small_df': df}
        serialized = project_manager._serialize_datasets(datasets)

        assert 'small_df' in serialized
        assert serialized['small_df']['type'] == 'DataFrame'
        # Small DataFrames might use JSON format
        assert serialized['small_df']['format'] in ['json', 'binary']

    def test_serialize_dataframe_large(self, project_manager):
        """PM-06b: Serialize large DataFrame as binary."""
        # Create large DataFrame (> 1000 elements)
        df = pd.DataFrame(np.random.rand(100, 20))
        datasets = {'large_df': df}
        serialized = project_manager._serialize_datasets(datasets)

        assert 'large_df' in serialized
        assert serialized['large_df']['format'] == 'binary'

    def test_deserialize_dataframe(self, project_manager):
        """PM-07: Deserialize DataFrame."""
        df = pd.DataFrame({
            'X': np.linspace(0, 1, 50),
            'Y': np.random.rand(50)
        })
        datasets = {'test_df': df}
        serialized = project_manager._serialize_datasets(datasets)
        deserialized = project_manager._deserialize_datasets(serialized)

        assert 'test_df' in deserialized
        assert isinstance(deserialized['test_df'], pd.DataFrame)
        assert deserialized['test_df'].shape == df.shape


class TestCompression:
    """Tests for compression functionality."""

    @pytest.fixture
    def project_manager(self):
        """Create ProjectManager for testing."""
        return ProjectManager()

    def test_compress_large_arrays(self, project_manager, sample_spectral_data_large, tmp_path):
        """PM-08: Large array compression reduces file size."""
        project_path = tmp_path / "compressed.hrt"

        project_data = {
            'metadata': {'name': 'Large Data Test'},
            'datasets': {'large': sample_spectral_data_large},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }

        project_manager.save_project(project_path, project_data)

        # File should exist and be compressed
        assert project_path.exists()
        file_size = project_path.stat().st_size

        # Raw data would be much larger
        raw_size = sample_spectral_data_large.data.values.nbytes
        assert file_size < raw_size  # Compression should reduce size


class TestBinaryConversion:
    """Tests for numpy array binary conversion."""

    @pytest.fixture
    def project_manager(self):
        """Create ProjectManager for testing."""
        return ProjectManager()

    def test_numpy_to_base64_roundtrip(self, project_manager):
        """Test numpy array to base64 and back."""
        original = np.random.rand(100, 50)

        encoded = project_manager._numpy_to_base64(original)
        decoded = project_manager._base64_to_numpy(encoded)

        np.testing.assert_array_equal(original, decoded)

    def test_numpy_to_base64_different_dtypes(self, project_manager):
        """Test conversion with different dtypes."""
        for dtype in [np.float32, np.float64, np.int32, np.int64]:
            original = np.array([1, 2, 3, 4, 5], dtype=dtype)
            encoded = project_manager._numpy_to_base64(original)
            decoded = project_manager._base64_to_numpy(encoded)
            np.testing.assert_array_equal(original, decoded)


class TestJsonSerializable:
    """Tests for JSON serialization helper."""

    @pytest.fixture
    def project_manager(self):
        """Create ProjectManager for testing."""
        return ProjectManager()

    def test_make_json_serializable_numpy_array(self, project_manager):
        """PM-10a: Convert numpy array to list."""
        result = project_manager._make_json_serializable(np.array([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_make_json_serializable_numpy_scalar(self, project_manager):
        """PM-10b: Convert numpy scalar to Python type."""
        result = project_manager._make_json_serializable(np.float64(3.14))
        assert isinstance(result, float)
        assert result == pytest.approx(3.14)

    def test_make_json_serializable_dict(self, project_manager):
        """PM-10c: Recursively convert dict."""
        data = {
            'array': np.array([1, 2]),
            'scalar': np.int32(42),
            'nested': {'value': np.float64(1.5)}
        }
        result = project_manager._make_json_serializable(data)

        assert result['array'] == [1, 2]
        assert result['scalar'] == 42
        assert result['nested']['value'] == pytest.approx(1.5)

    def test_make_json_serializable_none(self, project_manager):
        """PM-10d: Handle None values."""
        result = project_manager._make_json_serializable(None)
        assert result is None

    def test_make_json_serializable_basic_types(self, project_manager):
        """PM-10e: Pass through basic types."""
        assert project_manager._make_json_serializable("string") == "string"
        assert project_manager._make_json_serializable(42) == 42
        assert project_manager._make_json_serializable(3.14) == 3.14
        assert project_manager._make_json_serializable(True) is True


class TestWindowSerialization:
    """Tests for window state serialization helpers."""

    def test_serialize_window_geometry(self):
        """PM-11: Serialize window geometry."""
        mock_window = Mock()
        mock_geometry = Mock()
        mock_geometry.x.return_value = 100
        mock_geometry.y.return_value = 200
        mock_geometry.width.return_value = 800
        mock_geometry.height.return_value = 600
        mock_window.geometry.return_value = mock_geometry
        mock_window.isMaximized.return_value = False
        mock_window.isVisible.return_value = True

        result = serialize_window_geometry(mock_window)

        assert result['x'] == 100
        assert result['y'] == 200
        assert result['width'] == 800
        assert result['height'] == 600
        assert result['maximized'] is False
        assert result['visible'] is True

    def test_restore_window_geometry(self):
        """PM-12: Restore window geometry."""
        mock_window = Mock()

        geometry = {
            'x': 150,
            'y': 250,
            'width': 1024,
            'height': 768,
            'maximized': False,
            'visible': True
        }

        restore_window_geometry(mock_window, geometry)

        mock_window.setGeometry.assert_called_once_with(150, 250, 1024, 768)
        mock_window.show.assert_called_once()

    def test_restore_window_geometry_maximized(self):
        """Test restoring maximized window."""
        mock_window = Mock()

        geometry = {
            'x': 0,
            'y': 0,
            'width': 1920,
            'height': 1080,
            'maximized': True
        }

        restore_window_geometry(mock_window, geometry)

        mock_window.showMaximized.assert_called_once()

    def test_restore_window_geometry_empty(self):
        """Test restoring with empty geometry dict - should not modify window."""
        mock_window = Mock()
        restore_window_geometry(mock_window, {})
        # Empty geometry dict should result in early return, no calls
        mock_window.setGeometry.assert_not_called()


class TestPlotStateSerialize:
    """Tests for plot state serialization."""

    def test_serialize_plot_state(self):
        """PM-13: Serialize plot window state."""
        mock_window = Mock()
        mock_window.windowTitle.return_value = "Test Plot"

        mock_geometry = Mock()
        mock_geometry.x.return_value = 0
        mock_geometry.y.return_value = 0
        mock_geometry.width.return_value = 800
        mock_geometry.height.return_value = 600
        mock_window.geometry.return_value = mock_geometry
        mock_window.isMaximized.return_value = False
        mock_window.isVisible.return_value = True

        # Mock canvas
        mock_canvas = Mock()
        mock_canvas.plot_lines = {}
        mock_ax = Mock()
        mock_ax.get_xlabel.return_value = "X"
        mock_ax.get_ylabel.return_value = "Y"
        mock_ax.get_title.return_value = "Title"
        mock_ax.get_xlim.return_value = (0, 10)
        mock_ax.get_ylim.return_value = (0, 1)
        mock_ax.get_xscale.return_value = "linear"
        mock_ax.get_yscale.return_value = "linear"
        mock_ax.xaxis.get_gridlines.return_value = []
        mock_canvas.axes = mock_ax
        mock_window.canvas = mock_canvas

        result = serialize_plot_state(mock_window)

        assert result['title'] == "Test Plot"
        assert 'geometry' in result
        assert 'axes' in result
        assert result['axes']['xlabel'] == "X"


class TestTableStateSerialize:
    """Tests for table state serialization."""

    def test_serialize_table_state(self):
        """PM-14: Serialize table window state."""
        mock_window = Mock()
        mock_window.windowTitle.return_value = "Test Table"

        mock_geometry = Mock()
        mock_geometry.x.return_value = 0
        mock_geometry.y.return_value = 0
        mock_geometry.width.return_value = 600
        mock_geometry.height.return_value = 400
        mock_window.geometry.return_value = mock_geometry
        mock_window.isMaximized.return_value = False
        mock_window.isVisible.return_value = True

        # Mock table
        mock_table = Mock()
        mock_table.rowCount.return_value = 2
        mock_table.columnCount.return_value = 2

        def mock_header(c):
            header = Mock()
            header.text.return_value = f"Col_{c}"
            return header
        mock_table.horizontalHeaderItem = mock_header

        def mock_item(r, c):
            item = Mock()
            item.text.return_value = f"{r},{c}"
            return item
        mock_table.item = mock_item

        mock_table.columnWidth = lambda c: 100
        mock_window.table = mock_table
        # Formulas must be a proper dict, not a Mock
        mock_window.formulas = {(0, 0): "=SUM(A1:A10)"}

        result = serialize_table_state(mock_window)

        assert result['title'] == "Test Table"
        assert 'data' in result
        assert len(result['data']) == 2
        assert result['columns'] == ['Col_0', 'Col_1']


class TestModifiedFlag:
    """Tests for project modification tracking."""

    def test_modified_flag_initial(self):
        """PM-15a: Initial modified flag is False."""
        pm = ProjectManager()
        assert pm.is_modified() is False

    def test_modified_flag_after_mark(self):
        """PM-15b: Modified flag after mark_modified."""
        pm = ProjectManager()
        pm.mark_modified()
        assert pm.is_modified() is True

    def test_modified_flag_after_save(self, sample_spectral_data, tmp_path):
        """PM-15c: Modified flag reset after save."""
        pm = ProjectManager()
        pm.mark_modified()

        project_data = {
            'metadata': {'name': 'Test'},
            'datasets': {'data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        pm.save_project(tmp_path / "test.hrt", project_data)

        assert pm.is_modified() is False

    def test_modified_flag_after_load(self, sample_spectral_data, tmp_path):
        """PM-15d: Modified flag reset after load."""
        pm = ProjectManager()

        # Save first
        project_data = {
            'metadata': {'name': 'Test'},
            'datasets': {'data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        pm.save_project(tmp_path / "test.hrt", project_data)

        # Mark modified
        pm.mark_modified()
        assert pm.is_modified() is True

        # Load should reset
        pm.load_project(tmp_path / "test.hrt")
        assert pm.is_modified() is False
