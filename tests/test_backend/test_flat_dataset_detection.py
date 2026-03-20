"""
Tests for flat dataset detection and source_type generalization.
Verifies that getFlatDatasetList() returns only data_type=='flat' datasets
and that tools produce generic source_type values.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock
import re

from src.models.spectral_data import SpectralData, SpectralMetadata


class TestFlatDatasetDetection:
    """Tests for getFlatDatasetList() backend method."""

    @pytest.fixture
    def mock_backend(self, tmp_path):
        """Create a minimal mock backend with getFlatDatasetList."""
        from src.backend.app_backend import AppBackend

        class MinimalBackend:
            def __init__(self):
                self._datasets = {}

            def getFlatDatasetList(self):
                flat_datasets = []
                for name, data in self._datasets.items():
                    if hasattr(data, 'metadata') and getattr(data.metadata, 'data_type', 'spectral') == 'flat':
                        flat_datasets.append(name)
                return flat_datasets

        return MinimalBackend()

    @pytest.fixture
    def spectral_dataset(self):
        """Regular spectral dataset (not flat)."""
        x = np.linspace(-2, 2, 50)
        spectra = np.column_stack([np.sin(x * i) for i in range(1, 6)])
        columns = ['V'] + [f'Spectrum_{i}' for i in range(5)]
        df = pd.DataFrame(np.column_stack([x, spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='nanosurf_sts',
            dimensions=(5, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)

    @pytest.fixture
    def flat_dataset(self):
        """Flat/integrated dataset."""
        df = pd.DataFrame({
            'Spectrum_Index': range(10),
            'Interval_0': np.random.rand(10),
            'Interval_1': np.random.rand(10)
        })
        metadata = SpectralMetadata(
            source_type='integrated_flat',
            dimensions=(5, 2),
            scan_mode='forward',
            units={'independent': 'Index', 'dependent': 'Integrated Value'},
            data_type='flat'
        )
        return SpectralData(data=df, metadata=metadata)

    @pytest.fixture
    def bandgap_dataset(self):
        """Bandgap flat dataset."""
        df = pd.DataFrame({
            'Spectrum Index': range(10),
            'Bandgap (eV)': np.random.rand(10)
        })
        metadata = SpectralMetadata(
            source_type='bandgap_flat',
            dimensions=(5, 2),
            scan_mode='forward',
            units={'independent': 'Index', 'dependent': 'eV'},
            data_type='flat'
        )
        return SpectralData(data=df, metadata=metadata)

    def test_empty_datasets(self, mock_backend):
        """FD-01: No datasets returns empty list."""
        result = mock_backend.getFlatDatasetList()
        assert result == []

    def test_only_spectral_datasets(self, mock_backend, spectral_dataset):
        """FD-02: Only spectral datasets returns empty list."""
        mock_backend._datasets['STS Data'] = spectral_dataset
        result = mock_backend.getFlatDatasetList()
        assert result == []

    def test_only_flat_datasets(self, mock_backend, flat_dataset):
        """FD-03: Only flat datasets returns all."""
        mock_backend._datasets['Integrated Data'] = flat_dataset
        result = mock_backend.getFlatDatasetList()
        assert result == ['Integrated Data']

    def test_mixed_datasets(self, mock_backend, spectral_dataset, flat_dataset, bandgap_dataset):
        """FD-04: Mixed datasets returns only flat ones."""
        mock_backend._datasets['STS Data'] = spectral_dataset
        mock_backend._datasets['Integrated Data'] = flat_dataset
        mock_backend._datasets['Bandgap Data'] = bandgap_dataset

        result = mock_backend.getFlatDatasetList()
        assert len(result) == 2
        assert 'Integrated Data' in result
        assert 'Bandgap Data' in result
        assert 'STS Data' not in result

    def test_flat_detection_uses_metadata_not_name(self, mock_backend, spectral_dataset, flat_dataset):
        """FD-05: Detection uses metadata.data_type, not dataset name prefix."""
        # Dataset with "Integrated" in name but spectral data_type
        mock_backend._datasets['Integrated_fake'] = spectral_dataset
        # Dataset with friendly name but flat data_type
        mock_backend._datasets['STS hyperspec - Integrated'] = flat_dataset

        result = mock_backend.getFlatDatasetList()
        assert 'Integrated_fake' not in result
        assert 'STS hyperspec - Integrated' in result


class TestSourceTypeGeneralization:
    """Tests for generic source_type values."""

    @pytest.fixture
    def tool_impl(self, tmp_path):
        """Create a mock ToolImplementations instance."""
        from src.backend.tool_implementations import ToolImplementations

        class MockBackend(ToolImplementations):
            def __init__(self):
                self._datasets = {}
                self._output_base_dir = tmp_path / "outputs"
                self._output_base_dir.mkdir(exist_ok=True)
                self.errorOccurred = Mock()
                self.dataLoaded = Mock()
                self._workflow_mode = False
                self._naming_convention = "[dataset_name]"
                self._naming_index_start = 1
                self._naming_date_format = "dd-mm-yyyy"
                self._current_file_index = 1

            def _ensure_output_dir(self, subdir):
                path = self._output_base_dir / subdir
                path.mkdir(parents=True, exist_ok=True)
                return path

            def _sanitize_filename(self, name):
                safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
                safe = safe.replace(' ', '_')
                if len(safe) > 50:
                    safe = safe[:50]
                return safe if safe else "unnamed"

            def _extract_clean_base_name(self, name):
                wf_match = re.match(r'^_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline|discretize))?_[a-f0-9]{6}$', name)
                if wf_match:
                    name = wf_match.group(1)
                name = name.replace('_', ' ')
                name = ' '.join(name.split())
                return name

            def _apply_naming_convention(self, dataset_name, operation="", preview=False):
                clean_name = self._extract_clean_base_name(dataset_name)
                result = self._naming_convention.replace("[dataset_name]", clean_name)
                if operation:
                    result = f"{result}_{operation}"
                return self._sanitize_filename(result)

        return MockBackend()

    def test_bandgap_source_type(self, tool_impl, sample_spectral_data):
        """ST-01: Bandgap creates source_type='bandgap_flat'."""
        tool_impl._datasets['test'] = sample_spectral_data
        from unittest.mock import MagicMock
        task = MagicMock()
        task.cancelled = False

        result = tool_impl.detect_bandgap_doping(
            task, 'test', smoothing=11, delta=0.01, resolution=0.001
        )

        # Find the bandgap dataset
        bandgap_ds = None
        for name, ds in tool_impl._datasets.items():
            if 'Bandgap' in name and name != 'test':
                bandgap_ds = ds
                break

        assert bandgap_ds is not None
        assert bandgap_ds.metadata.source_type == 'bandgap_flat'
        assert 'original_source_type' in bandgap_ds.metadata.additional_info

    def test_doping_source_type(self, tool_impl, sample_spectral_data):
        """ST-02: Doping creates source_type='doping_flat'."""
        tool_impl._datasets['test'] = sample_spectral_data
        from unittest.mock import MagicMock
        task = MagicMock()
        task.cancelled = False

        tool_impl.detect_bandgap_doping(
            task, 'test', smoothing=11, delta=0.01, resolution=0.001
        )

        doping_ds = None
        for name, ds in tool_impl._datasets.items():
            if 'Doping' in name and name != 'test':
                doping_ds = ds
                break

        assert doping_ds is not None
        assert doping_ds.metadata.source_type == 'doping_flat'
        assert 'original_source_type' in doping_ds.metadata.additional_info

    def test_original_source_type_preserved(self, tool_impl, sample_spectral_data):
        """ST-03: Original source_type is preserved in additional_info."""
        tool_impl._datasets['test'] = sample_spectral_data
        from unittest.mock import MagicMock
        task = MagicMock()
        task.cancelled = False

        tool_impl.detect_bandgap_doping(
            task, 'test', smoothing=11, delta=0.01, resolution=0.001
        )

        for name, ds in tool_impl._datasets.items():
            if name != 'test' and hasattr(ds, 'metadata'):
                info = ds.metadata.additional_info
                if 'original_source_type' in info:
                    assert info['original_source_type'] == 'test'
