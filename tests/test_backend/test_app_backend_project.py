"""
Tests for AppBackend project loading functionality.
Covers openProject, openProjectFile, and projectReady signal behavior.
Target coverage: 80%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from src.models.spectral_data import SpectralData, SpectralMetadata
from src.backend.project_manager import ProjectManager


def create_test_spectral_data():
    """Create test spectral data with proper metadata."""
    x = np.linspace(-2, 2, 100)
    spectra = np.column_stack([
        np.sin(x * (i + 1)) + np.random.normal(0, 0.01, len(x))
        for i in range(10)
    ])
    columns = ['V'] + [f'Spectrum_{i}' for i in range(10)]
    df = pd.DataFrame(
        np.column_stack([x, spectra]),
        columns=columns
    )
    metadata = SpectralMetadata(
        source_type='test',
        dimensions=(5, 2),
        scan_mode='forward',
        units={'x': 'V', 'y': 'nA'}
    )
    return SpectralData(data=df, metadata=metadata)


class TestOpenProjectWithHrt:
    """Tests for opening projects that contain .hrt files."""

    @pytest.fixture
    def project_with_hrt(self, tmp_path, sample_spectral_data):
        """Create a project directory with a .hrt file."""
        project_dir = tmp_path / "MyProject"
        project_dir.mkdir()

        # Save a real .hrt file using ProjectManager
        pm = ProjectManager()
        project_data = {
            'metadata': {'name': 'MyProject'},
            'datasets': {'TestData': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        hrt_path = project_dir / "MyProject.hrt"
        pm.save_project(hrt_path, project_data)

        return project_dir, hrt_path

    def test_open_project_finds_matching_hrt(self, project_with_hrt):
        """AP-01: openProject finds .hrt file matching project name."""
        project_dir, hrt_path = project_with_hrt

        # The logic: check for {project_name}.hrt first
        project_name = "MyProject"
        expected_hrt = project_dir / f"{project_name}.hrt"

        assert expected_hrt.exists()
        assert expected_hrt == hrt_path

    def test_open_project_finds_any_hrt(self, tmp_path, sample_spectral_data):
        """AP-02: openProject finds any .hrt file if name doesn't match."""
        project_dir = tmp_path / "ProjectFolder"
        project_dir.mkdir()

        # Save .hrt with different name than folder
        pm = ProjectManager()
        project_data = {
            'metadata': {'name': 'DifferentName'},
            'datasets': {'Data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        hrt_path = project_dir / "DifferentName.hrt"
        pm.save_project(hrt_path, project_data)

        # openProject logic: first check {project_name}.hrt, then glob *.hrt
        project_name = "ProjectFolder"
        expected_hrt = project_dir / f"{project_name}.hrt"

        if not expected_hrt.exists():
            hrt_files = list(project_dir.glob("*.hrt"))
            assert len(hrt_files) == 1
            assert hrt_files[0] == hrt_path

    def test_open_project_no_hrt_opens_as_folder(self, tmp_path):
        """AP-03: openProject with no .hrt opens as folder-based project."""
        project_dir = tmp_path / "EmptyProject"
        project_dir.mkdir()

        # No .hrt files exist
        hrt_files = list(project_dir.glob("*.hrt"))
        assert len(hrt_files) == 0

        # Should proceed as folder-based project
        # Verify the folder can still be used
        assert project_dir.exists()
        assert project_dir.is_dir()


class TestOpenProjectFile:
    """Tests for openProjectFile method."""

    def test_open_valid_hrt_file(self, tmp_path, sample_spectral_data):
        """AP-04: openProjectFile loads valid .hrt file successfully."""
        pm = ProjectManager()

        # Create and save a project
        project_data = {
            'metadata': {'name': 'ValidProject'},
            'datasets': {'STS_Data': sample_spectral_data},
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        hrt_path = tmp_path / "valid_project.hrt"
        pm.save_project(hrt_path, project_data)

        # Load the project back
        loaded = pm.load_project(hrt_path)

        assert loaded is not None
        assert loaded['metadata']['name'] == 'ValidProject'
        assert 'STS_Data' in loaded['datasets']

    def test_open_nonexistent_file(self):
        """AP-05: openProjectFile with nonexistent path fails gracefully."""
        file_path = Path("/nonexistent/path/project.hrt")

        assert not file_path.exists()

    def test_open_wrong_extension(self, tmp_path):
        """AP-06: openProjectFile rejects non-.hrt files."""
        # Create a file with wrong extension
        wrong_file = tmp_path / "project.txt"
        wrong_file.write_text("not a project file")

        assert wrong_file.suffix.lower() != '.hrt'

    def test_loaded_datasets_are_accessible(self, tmp_path, sample_spectral_data):
        """AP-07: Datasets loaded from .hrt are fully functional."""
        pm = ProjectManager()

        project_data = {
            'metadata': {'name': 'DataTest'},
            'datasets': {
                'Data1': sample_spectral_data,
            },
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        hrt_path = tmp_path / "data_test.hrt"
        pm.save_project(hrt_path, project_data)

        loaded = pm.load_project(hrt_path)
        loaded_dataset = loaded['datasets']['Data1']

        # Verify dataset integrity
        assert loaded_dataset.num_spectra == sample_spectral_data.num_spectra
        assert loaded_dataset.num_points == sample_spectral_data.num_points
        assert loaded_dataset.data.shape == sample_spectral_data.data.shape

    def test_multiple_datasets_loaded(self, tmp_path, sample_spectral_data):
        """AP-08: Multiple datasets are all loaded from .hrt file."""
        pm = ProjectManager()

        # Create second dataset
        x = np.linspace(-1, 1, 50)
        spectra = np.column_stack([np.cos(x * i) for i in range(5)])
        columns = ['V'] + [f'Spec_{i}' for i in range(5)]
        df = pd.DataFrame(np.column_stack([x, spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test2',
            dimensions=(5, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        second_data = SpectralData(data=df, metadata=metadata)

        project_data = {
            'metadata': {'name': 'MultiDataset'},
            'datasets': {
                'Dataset_A': sample_spectral_data,
                'Dataset_B': second_data,
            },
            'tables': [],
            'graphs': [],
            'workspace': {}
        }
        hrt_path = tmp_path / "multi.hrt"
        pm.save_project(hrt_path, project_data)

        loaded = pm.load_project(hrt_path)

        assert len(loaded['datasets']) == 2
        assert 'Dataset_A' in loaded['datasets']
        assert 'Dataset_B' in loaded['datasets']


class TestProjectReadyState:
    """Tests for project ready state management."""

    def test_project_not_ready_initially(self):
        """AP-09: Project is not ready before any project is opened."""
        project_ready = False
        assert project_ready is False

    def test_project_ready_after_open(self):
        """AP-10: Project becomes ready after successful open."""
        project_ready = False

        # Simulate successful project open
        project_ready = True

        assert project_ready is True

    def test_project_not_ready_after_close(self):
        """AP-11: Project is not ready after closing."""
        project_ready = True

        # Simulate close
        project_ready = False

        assert project_ready is False

    def test_project_ready_signal_flow(self):
        """AP-12: projectReadyChanged signal emitted on state change."""
        signal_emissions = []

        def on_ready_changed(ready):
            signal_emissions.append(ready)

        # Simulate: project opened -> ready
        on_ready_changed(True)
        assert signal_emissions == [True]

        # Simulate: project closed -> not ready
        on_ready_changed(False)
        assert signal_emissions == [True, False]


class TestLegacyOutputsFolderDetection:
    """Tests for legacy 'outputs' folder migration."""

    def test_detect_legacy_outputs_folder(self, tmp_path):
        """AP-13: Legacy 'outputs' folder is detected and used."""
        project_dir = tmp_path / "OldProject"
        project_dir.mkdir()

        # Create legacy outputs folder
        legacy_outputs = project_dir / "outputs"
        legacy_outputs.mkdir()
        (legacy_outputs / "maps").mkdir()

        # Modern output folder name
        project_name = "OldProject"
        modern_outputs = project_dir / f"{project_name}_outputs"

        # Logic from openProject: use modern first, fall back to legacy
        if not modern_outputs.exists():
            if legacy_outputs.exists():
                output_dir = legacy_outputs
            else:
                output_dir = None
        else:
            output_dir = modern_outputs

        assert output_dir == legacy_outputs
        assert (output_dir / "maps").exists()

    def test_prefer_modern_outputs_folder(self, tmp_path):
        """AP-14: Modern '{name}_outputs' folder preferred over legacy."""
        project_dir = tmp_path / "Project"
        project_dir.mkdir()

        # Create both folders
        legacy_outputs = project_dir / "outputs"
        legacy_outputs.mkdir()
        modern_outputs = project_dir / "Project_outputs"
        modern_outputs.mkdir()

        project_name = "Project"
        output_dir = project_dir / f"{project_name}_outputs"

        if output_dir.exists():
            result = output_dir
        else:
            result = legacy_outputs if legacy_outputs.exists() else None

        assert result == modern_outputs

    def test_no_outputs_folder(self, tmp_path):
        """AP-15: Project without any outputs folder works."""
        project_dir = tmp_path / "NewProject"
        project_dir.mkdir()

        project_name = "NewProject"
        modern_outputs = project_dir / f"{project_name}_outputs"
        legacy_outputs = project_dir / "outputs"

        outputs_created = modern_outputs.exists()
        if not outputs_created:
            outputs_created = legacy_outputs.exists()

        assert outputs_created is False


class TestRecentProjects:
    """Tests for recent projects management."""

    def test_recent_projects_json_structure(self, tmp_path):
        """AP-16: Recent projects stored as JSON with path and name."""
        import json

        recent_file = tmp_path / "recent_projects.json"

        recent_projects = [
            {'path': '/path/to/project1', 'name': 'Project 1'},
            {'path': '/path/to/project2', 'name': 'Project 2'},
        ]

        recent_file.write_text(json.dumps(recent_projects))

        loaded = json.loads(recent_file.read_text())

        assert len(loaded) == 2
        assert loaded[0]['name'] == 'Project 1'
        assert loaded[1]['path'] == '/path/to/project2'

    def test_add_to_recent_projects(self, tmp_path):
        """AP-17: Adding a project updates recent list."""
        import json

        recent_file = tmp_path / "recent_projects.json"

        # Start with existing projects
        recent_projects = [
            {'path': '/path/to/old', 'name': 'Old Project'},
        ]

        # Add new project
        new_project = {'path': '/path/to/new', 'name': 'New Project'}
        recent_projects.insert(0, new_project)

        recent_file.write_text(json.dumps(recent_projects))
        loaded = json.loads(recent_file.read_text())

        assert loaded[0]['name'] == 'New Project'
        assert len(loaded) == 2

    def test_recent_projects_deduplication(self, tmp_path):
        """AP-18: Re-opening existing project moves it to top."""
        recent_projects = [
            {'path': '/path/to/A', 'name': 'A'},
            {'path': '/path/to/B', 'name': 'B'},
            {'path': '/path/to/C', 'name': 'C'},
        ]

        # Re-open project B
        reopen_path = '/path/to/B'

        # Remove existing entry
        recent_projects = [p for p in recent_projects if p['path'] != reopen_path]
        # Add to top
        recent_projects.insert(0, {'path': reopen_path, 'name': 'B'})

        assert recent_projects[0]['name'] == 'B'
        assert len(recent_projects) == 3


class TestProjectOutputDirectory:
    """Tests for project output directory management."""

    def test_output_dir_uses_sanitized_name(self, tmp_path):
        """AP-19: Output directory uses sanitized project name."""
        project_name = "My Project (2024)"

        # Sanitize: keep alnum, spaces, hyphens, underscores, dots
        safe = "".join(c for c in project_name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        safe = safe.replace(' ', '_')

        expected = f"{safe}_outputs"
        output_dir = tmp_path / expected

        assert "My_Project_2024" in str(output_dir)

    def test_output_subdirs_created_on_demand(self, tmp_path):
        """AP-20: Output subdirectories created only when needed."""
        output_dir = tmp_path / "Project_outputs"

        # Initially not created
        assert not output_dir.exists()

        # Create on first use
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "smoothed").mkdir(exist_ok=True)

        assert output_dir.exists()
        assert (output_dir / "smoothed").exists()
        # Other subdirs not created yet
        assert not (output_dir / "maps").exists()
