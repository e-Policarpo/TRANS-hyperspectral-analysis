"""
Tests for project save/load completeness.
Verifies that all project state is properly serialized and restored.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.backend.project_manager import ProjectManager


class TestProjectSaveLoad:
    """Tests for project save/load roundtrip completeness."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def sample_project_data(self):
        """A complete project data dict with all fields."""
        return {
            'created': datetime.now().isoformat(),
            'metadata': {
                'name': 'test_project',
                'description': 'TRANS-QML Project'
            },
            'datasets': {},
            'tables': [
                {
                    'id': 'table_1',
                    'title': 'Test Table',
                    'columns': ['X', 'Y'],
                    'data': [[1, 2], [3, 4]]
                }
            ],
            'graphs': [
                {
                    'id': 'graph_1',
                    'title': 'Test Graph',
                    'curves': [],
                    'xLabel': 'X',
                    'yLabel': 'Y'
                }
            ],
            'workspace': {
                'active_dataset': None,
                'current_tab': 1,
                'window_counter': 5
            },
            'output_files': [
                {
                    'id': 'output_1',
                    'tool': 'Derivative Calculator',
                    'path': '/tmp/output.csv',
                    'timestamp': '2025-01-01 12:00:00'
                }
            ],
            'maps': [
                {
                    'id': 'map_1',
                    'title': 'Test Map',
                    'path': '/tmp/map.png',
                    'timestamp': '2025-01-01 12:00:00'
                }
            ],
            'naming_convention': '[dataset_name]_[index]',
        }

    def test_save_and_load_roundtrip(self, project_manager, sample_project_data, tmp_path):
        """Test that saving and loading preserves all project data."""
        project_file = tmp_path / "test.hrt"

        # Save
        success = project_manager.save_project(project_file, sample_project_data)
        assert success
        assert project_file.exists()

        # Load
        loaded = project_manager.load_project(project_file)
        assert loaded is not None

        # Verify metadata
        assert loaded['metadata']['name'] == 'test_project'

        # Verify tables
        assert len(loaded.get('tables', [])) == 1
        assert loaded['tables'][0]['title'] == 'Test Table'
        assert loaded['tables'][0]['columns'] == ['X', 'Y']

        # Verify graphs
        assert len(loaded.get('graphs', [])) == 1
        assert loaded['graphs'][0]['title'] == 'Test Graph'

        # Verify workspace
        workspace = loaded.get('workspace', {})
        assert workspace.get('current_tab') == 1
        assert workspace.get('window_counter') == 5

        # Verify output_files
        outputs = loaded.get('output_files', [])
        assert len(outputs) == 1
        assert outputs[0]['tool'] == 'Derivative Calculator'

        # Verify maps
        maps = loaded.get('maps', [])
        assert len(maps) == 1
        assert maps[0]['title'] == 'Test Map'

        # Verify naming_convention
        assert loaded.get('naming_convention') == '[dataset_name]_[index]'

    def test_load_project_with_missing_fields(self, project_manager, tmp_path):
        """Test loading a project file that lacks newer fields (backward compat)."""
        project_file = tmp_path / "old_project.hrt"

        # Minimal old-format project data
        old_data = {
            'metadata': {
                'name': 'old_project',
                'description': 'Old format'
            },
            'datasets': {}
        }

        success = project_manager.save_project(project_file, old_data)
        assert success

        loaded = project_manager.load_project(project_file)
        assert loaded is not None

        # Should gracefully return empty lists for missing fields
        assert loaded.get('tables', []) == []
        assert loaded.get('graphs', []) == []
        assert loaded.get('workspace', {}) == {}
        assert loaded.get('output_files', []) == []
        assert loaded.get('maps', []) == []
        assert loaded.get('naming_convention') is None

    def test_save_project_creates_file(self, project_manager, tmp_path):
        """Test that save creates the .hrt file."""
        project_file = tmp_path / "new_project.hrt"
        assert not project_file.exists()

        data = {
            'metadata': {'name': 'new', 'description': ''},
            'datasets': {}
        }
        success = project_manager.save_project(project_file, data)
        assert success
        assert project_file.exists()

    def test_load_nonexistent_file(self, project_manager, tmp_path):
        """Test loading a file that doesn't exist."""
        result = project_manager.load_project(tmp_path / "nonexistent.hrt")
        assert result is None
