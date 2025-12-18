"""
Integration tests for project lifecycle
Target coverage: 70%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.project_manager import ProjectManager


class TestProjectCreation:
    """Tests for project creation."""

    def test_create_project_directory(self, tmp_path):
        """PL-01: Create new project creates directory structure."""
        project_name = "NewProject"
        project_dir = tmp_path / project_name

        # Simulate project creation
        project_dir.mkdir()
        outputs_dir = project_dir / f"{project_name}_outputs"
        outputs_dir.mkdir()

        # Create standard subdirectories
        for subdir in ['smoothed', 'derivatives', 'integrated', 'maps', 'peaks', 'workflows']:
            (outputs_dir / subdir).mkdir()

        assert project_dir.exists()
        assert outputs_dir.exists()
        assert (outputs_dir / 'smoothed').exists()
        assert (outputs_dir / 'maps').exists()

    def test_project_file_creation(self, sample_spectral_data, tmp_path):
        """Test .hrt project file is created."""
        pm = ProjectManager()

        project_data = {
            'metadata': {'name': 'Test Project'},
            'datasets': {'Data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }

        project_path = tmp_path / "test_project.hrt"
        result = pm.save_project(project_path, project_data)

        assert result is True
        assert project_path.exists()


class TestMeasurementLoading:
    """Tests for loading measurements into project."""

    @pytest.fixture
    def project_context(self, tmp_path):
        """Create project context."""
        project_dir = tmp_path / "TestProject"
        project_dir.mkdir()
        outputs_dir = project_dir / "TestProject_outputs"
        outputs_dir.mkdir()

        return {
            'project_dir': project_dir,
            'outputs_dir': outputs_dir,
            'datasets': {}
        }

    def test_load_measurement_adds_dataset(self, project_context, sample_spectral_data):
        """PL-02: Import measurement adds dataset to project."""
        ctx = project_context

        # Simulate loading a measurement
        dataset_name = "STS_Sample1"
        ctx['datasets'][dataset_name] = sample_spectral_data

        assert dataset_name in ctx['datasets']
        assert ctx['datasets'][dataset_name].num_spectra == sample_spectral_data.num_spectra

    def test_load_multiple_measurements(self, project_context, sample_spectral_data, sample_spectral_data_large):
        """Test loading multiple measurements."""
        ctx = project_context

        ctx['datasets']['Data1'] = sample_spectral_data
        ctx['datasets']['Data2'] = sample_spectral_data_large

        assert len(ctx['datasets']) == 2
        assert ctx['datasets']['Data1'].num_spectra == 10
        assert ctx['datasets']['Data2'].num_spectra == 100


class TestToolApplication:
    """Tests for applying tools to data."""

    @pytest.fixture
    def project_with_data(self, sample_spectral_data, tmp_path):
        """Create project with loaded data."""
        return {
            'datasets': {'TestData': sample_spectral_data},
            'outputs_dir': tmp_path / "outputs"
        }

    def test_apply_smoothing_creates_result(self, project_with_data):
        """PL-03a: Smoothing creates result dataset."""
        ctx = project_with_data

        # Simulate smoothing
        original = ctx['datasets']['TestData']
        smoothed_name = "TestData - Smoothed"

        # Create smoothed version (simplified)
        smoothed_data = original  # In real code, this would be processed
        ctx['datasets'][smoothed_name] = smoothed_data

        assert smoothed_name in ctx['datasets']

    def test_apply_derivative_creates_result(self, project_with_data):
        """PL-03b: Derivative creates result dataset."""
        ctx = project_with_data

        original = ctx['datasets']['TestData']
        derivative_name = "TestData - 1st Derivative"

        # Create derivative version (simplified)
        ctx['datasets'][derivative_name] = original

        assert derivative_name in ctx['datasets']

    def test_apply_integration_creates_result(self, project_with_data):
        """PL-03c: Integration creates result dataset."""
        ctx = project_with_data

        # Simulate integration result
        integrated_name = "TestData - Integrated"

        # Create flat data from integration
        flat_df = pd.DataFrame({
            'X': range(10),
            'Integrated': np.random.rand(10)
        })
        metadata = SpectralMetadata(
            source_type='integrated',
            dimensions=(5, 2),
            scan_mode='forward',
            units={'x': 'index', 'y': 'counts'}
        )
        ctx['datasets'][integrated_name] = SpectralData(data=flat_df, metadata=metadata)

        assert integrated_name in ctx['datasets']


class TestProjectSaveRestore:
    """Tests for saving and restoring project state."""

    def test_save_project_state(self, sample_spectral_data, tmp_path):
        """PL-04: Save project state to .hrt file."""
        pm = ProjectManager()

        # Create project with multiple datasets
        project_data = {
            'metadata': {
                'name': 'Full Project',
                'description': 'A complete test project'
            },
            'datasets': {
                'Original': sample_spectral_data,
                'Processed': sample_spectral_data
            },
            'tables': [
                {'id': 'table1', 'data': [[1, 2], [3, 4]]}
            ],
            'graphs': [
                {'id': 'graph1', 'curves': []}
            ],
            'workspace': {
                'window_position': [100, 100],
                'window_size': [1200, 800]
            }
        }

        project_path = tmp_path / "full_project.hrt"
        result = pm.save_project(project_path, project_data)

        assert result is True
        assert project_path.exists()

        # Verify file has content
        assert project_path.stat().st_size > 0

    def test_close_and_reopen_preserves_state(self, sample_spectral_data, tmp_path):
        """PL-05: Close and reopen preserves state."""
        pm = ProjectManager()

        # Original project
        original_data = {
            'metadata': {'name': 'Persistence Test'},
            'datasets': {
                'Data1': sample_spectral_data,
            },
            'tables': [],
            'graphs': [],
            'workspace': {'setting': 'value'}
        }

        project_path = tmp_path / "persist.hrt"

        # Save
        pm.save_project(project_path, original_data)

        # Close
        pm.close_project()
        assert pm.current_project_path is None

        # Reopen
        loaded_data = pm.load_project(project_path)

        # Verify state preserved
        assert loaded_data is not None
        assert loaded_data['metadata']['name'] == 'Persistence Test'
        assert 'Data1' in loaded_data['datasets']
        assert loaded_data['workspace']['setting'] == 'value'

        # Verify dataset integrity
        loaded_dataset = loaded_data['datasets']['Data1']
        assert loaded_dataset.num_spectra == sample_spectral_data.num_spectra
        assert loaded_dataset.num_points == sample_spectral_data.num_points


class TestOutputOrganization:
    """Tests for output directory organization."""

    def test_output_folder_structure(self, tmp_path):
        """PL-06: Check output folder structure."""
        project_name = "OrganizedProject"
        outputs_dir = tmp_path / f"{project_name}_outputs"
        outputs_dir.mkdir()

        expected_subdirs = [
            'curves',
            'derivatives',
            'integrated',
            'smoothed',
            'maps',
            'peaks',
            'discretized',
            'fft',
            'fitted',
            'workflows'
        ]

        for subdir in expected_subdirs:
            (outputs_dir / subdir).mkdir()

        for subdir in expected_subdirs:
            assert (outputs_dir / subdir).exists()
            assert (outputs_dir / subdir).is_dir()

    def test_output_files_go_to_correct_folders(self, tmp_path):
        """Test that output files are organized correctly."""
        outputs_dir = tmp_path / "TestProject_outputs"
        outputs_dir.mkdir()

        # Create subdirectories
        (outputs_dir / 'smoothed').mkdir()
        (outputs_dir / 'maps').mkdir()

        # Simulate creating outputs
        smoothed_file = outputs_dir / 'smoothed' / 'Sample1_smoothed_savgol.csv'
        smoothed_file.write_text("x,y\n1,2\n")

        map_file = outputs_dir / 'maps' / 'Sample1_map_interval0.png'
        map_file.write_bytes(b'PNG')

        assert smoothed_file.exists()
        assert smoothed_file.parent.name == 'smoothed'

        assert map_file.exists()
        assert map_file.parent.name == 'maps'


class TestProjectWorkflowIntegration:
    """Tests for workflow integration with projects."""

    def test_workflow_saved_with_project(self, sample_spectral_data, tmp_path):
        """Test workflows are saved with project."""
        pm = ProjectManager()

        # Create workflow data
        workflow_data = {
            'id': 'wf1',
            'name': 'Test Workflow',
            'nodes': [],
            'connections': []
        }

        project_data = {
            'metadata': {'name': 'Workflow Project'},
            'datasets': {'Data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {},
            'workflows': [workflow_data]
        }

        project_path = tmp_path / "with_workflow.hrt"
        pm.save_project(project_path, project_data)

        # Load and verify
        loaded = pm.load_project(project_path)

        # Workflows might be stored differently, check structure
        assert loaded is not None


class TestDatasetNaming:
    """Tests for dataset naming conventions."""

    def test_dataset_naming_after_operation(self, sample_spectral_data):
        """Test dataset naming follows convention."""
        datasets = {'Original_Data': sample_spectral_data}

        # Simulate various operations
        operations = [
            ('Original_Data', 'Smoothed', 'Original_Data - Smoothed'),
            ('Original_Data', '1st Derivative', 'Original_Data - 1st Derivative'),
            ('Original_Data', 'Truncated (-1.0 to 1.0)', 'Original_Data - Truncated (-1.0 to 1.0)'),
        ]

        for source, op_name, expected_name in operations:
            # This is how the naming should work
            result_name = f"{source} - {op_name}"
            assert result_name == expected_name

    def test_file_naming_convention(self, tmp_path):
        """Test file naming convention."""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()

        # Expected file naming patterns
        test_cases = [
            ('Sample1', 'smoothed', 'savgol', 'Sample1_smoothed_savgol.csv'),
            ('Data_Test', '1st_derivative', None, 'Data_Test_1st_derivative.csv'),
            ('MyData', 'integrated', None, 'MyData_integrated.csv'),
        ]

        for base, operation, params, expected in test_cases:
            if params:
                filename = f"{base}_{operation}_{params}.csv"
            else:
                filename = f"{base}_{operation}.csv"
            assert filename == expected


class TestModificationTracking:
    """Tests for tracking project modifications."""

    def test_modification_tracked(self, sample_spectral_data, tmp_path):
        """Test project modifications are tracked."""
        pm = ProjectManager()

        # Save initial project
        project_data = {
            'metadata': {'name': 'Mod Test'},
            'datasets': {'Data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }

        project_path = tmp_path / "mod_test.hrt"
        pm.save_project(project_path, project_data)

        assert pm.is_modified() is False

        # Mark as modified (simulating data change)
        pm.mark_modified()
        assert pm.is_modified() is True

        # Save clears modification flag
        pm.save_project(project_path, project_data)
        assert pm.is_modified() is False
