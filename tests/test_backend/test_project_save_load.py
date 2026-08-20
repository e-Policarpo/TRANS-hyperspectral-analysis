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


class TestConfinementAnalysisPersistence:
    """Confinement Analysis outputs must survive a .hrt round-trip.

    The occupancy tables are the fragile ones: they carry NaN for "no peak"
    and are float32 to keep a hyperspectral map affordable, and both are easy
    to lose in serialisation (NaN -> 0, float32 -> float64), which would turn
    a blank cell into a false negative.
    """

    @pytest.fixture
    def analysed(self, tmp_path):
        """Run the tool for real, then hand back its datasets."""
        import re
        import numpy as np
        import pandas as pd
        from unittest.mock import Mock
        from src.backend.tool_implementations import ToolImplementations
        from src.models.spectral_data import SpectralData, SpectralMetadata

        class Backend(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._output_base_dir = tmp_path / "outputs"
                self._output_base_dir.mkdir(exist_ok=True)
                self.errorOccurred = Mock()
                self.dataLoaded = Mock()
                self._workflow_mode = False

            def _ensure_output_dir(self, subdir):
                path = self._output_base_dir / subdir
                path.mkdir(parents=True, exist_ok=True)
                return path

            def _sanitize_filename(self, name):
                return re.sub(r'\W+', '_', name) or "unnamed"

            def _extract_clean_base_name(self, name):
                return name

            def _apply_naming_convention(self, dataset_name, operation="", preview=False):
                return self._sanitize_filename(f"{dataset_name}_{operation}")

        class MockTask:
            cancelled = False

        x = np.linspace(-0.6, 0.6, 512)
        y = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
        for c in (-0.25, -0.10, 0.08, 0.22):
            y = y + 1.2e-8 * np.exp(-0.5 * ((x - c) / 0.008) ** 2)

        backend = Backend()
        backend._datasets['STS'] = SpectralData(
            pd.DataFrame({"V": x, "P1": y, "P2": y * 1.1}),
            SpectralMetadata(source_type="sts", dimensions=(2, 1), scan_mode="line",
                             units={"x": "V"}, additional_info={}))
        backend.analyze_confinement(
            MockTask(), 'STS',
            params={'baseline': 'poly-iter', 'baseline_degree': 5, 'temperature_k': 94.0})
        return backend._datasets

    @pytest.mark.parametrize("fast", [False, True], ids=["save", "autosave"])
    def test_every_output_survives_the_roundtrip(self, analysed, tmp_path, fast):
        import numpy as np

        manager = ProjectManager()
        path = tmp_path / f"project_{int(fast)}.hrt"
        assert manager.save_project(path, {'datasets': dict(analysed)}, fast=fast) is True

        restored = manager.load_project(path)['datasets']
        assert set(restored) == set(analysed)

        for name, original in analysed.items():
            back = restored[name]
            np.testing.assert_allclose(back.independent_var, original.independent_var,
                                       equal_nan=True, err_msg=name)
            np.testing.assert_allclose(back.spectra.values, original.spectra.values,
                                       equal_nan=True, err_msg=name)
            assert list(back.spectra.columns) == list(original.spectra.columns), name
            assert back.independent_var_name == original.independent_var_name, name
            assert back.metadata.data_type == original.metadata.data_type, name
            assert back.metadata.additional_info == original.metadata.additional_info, name

    def test_blank_cells_stay_blank_and_stay_float32(self, analysed, tmp_path):
        """A NaN turning into 0 would silently invent 'no peak here' data."""
        import numpy as np

        original = analysed['STS - Peak Matrix (binned)']
        before = original.spectra.values
        assert before.dtype == np.float32
        assert np.isnan(before).sum() > 0, "fixture must actually contain blanks"
        assert np.nansum(before) > 0, "fixture must actually contain marks"

        manager = ProjectManager()
        path = tmp_path / "matrix.hrt"
        manager.save_project(path, {'datasets': dict(analysed)})
        after = manager.load_project(path)['datasets']['STS - Peak Matrix (binned)'].spectra.values

        assert after.dtype == np.float32
        assert np.isnan(after).sum() == np.isnan(before).sum()
        assert np.nansum(after) == np.nansum(before)
        assert set(np.unique(after[np.isfinite(after)])) == {1}

    def test_both_matrices_are_kept_separately(self, analysed, tmp_path):
        manager = ProjectManager()
        path = tmp_path / "both.hrt"
        manager.save_project(path, {'datasets': dict(analysed)})
        restored = manager.load_project(path)['datasets']

        raw = restored['STS - Peak Matrix']
        binned = restored['STS - Peak Matrix (binned)']
        assert len(raw.independent_var) == 512
        # Bins are kBT/2 wide, so ~300 of them across the sweep.
        assert len(binned.independent_var) < 400
        assert raw.metadata.additional_info['binned'] is False
        assert binned.metadata.additional_info['binned'] is True

    def test_flat_outputs_stay_mappable(self, analysed, tmp_path):
        """data_type='flat' and the Spectrum_Index axis are what let the Map
        Generator accept these after a reload."""
        manager = ProjectManager()
        path = tmp_path / "flat.hrt"
        manager.save_project(path, {'datasets': dict(analysed)})
        restored = manager.load_project(path)['datasets']

        for name in ('STS - Fit Coefficients', 'STS - Peak Count'):
            back = restored[name]
            assert back.metadata.data_type == 'flat', name
            assert back.independent_var_name == 'Spectrum_Index', name

    def test_temperature_settings_survive(self, analysed, tmp_path):
        manager = ProjectManager()
        path = tmp_path / "meta.hrt"
        manager.save_project(path, {'datasets': dict(analysed)})
        info = manager.load_project(path)['datasets'][
            'STS - Peak Matrix (binned)'].metadata.additional_info

        assert info['temperature_k'] == 94.0
        assert info['kbt'] == pytest.approx(8.1e-3, rel=1e-2)
        assert info['n_bins'] > 0
