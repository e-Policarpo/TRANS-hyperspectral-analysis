"""
Tests for filter_bad_data in ToolImplementations.
Covers: normal filtering, all-good / all-bad scenarios, cancellation,
missing dataset, periodic correction, FFT output, report generation.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock

from src.models.spectral_data import SpectralData, SpectralMetadata


class MockTask:
    """Mock task object for testing."""
    cancelled = False
    progress = 0


class TestFilterBadDataSetup:
    """Base setup for filter_bad_data tests."""

    @pytest.fixture
    def tool_impl(self, tmp_path):
        """Create a mock ToolImplementations instance."""
        from src.backend.tool_implementations import ToolImplementations
        import re

        class MockBackend(ToolImplementations):
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
                safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
                safe = safe.replace(' ', '_')
                if len(safe) > 50:
                    safe = safe[:50]
                return safe if safe else "unnamed"

            def _extract_clean_base_name(self, name):
                wf_match = re.match(
                    r'^_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline|discretize))?_[a-f0-9]{6}$',
                    name
                )
                if wf_match:
                    name = wf_match.group(1)
                name = name.replace('_', ' ')
                name = ' '.join(name.split())
                return name

        return MockBackend()

    @pytest.fixture
    def normal_dataset(self):
        """Dataset with a mix of good and intentionally bad spectra."""
        np.random.seed(42)
        x = np.linspace(-2, 2, 100)
        spectra = []
        # 5 good spectra: smooth sine waves
        for i in range(5):
            spectra.append(np.sin(x * (i + 1)) + np.random.normal(0, 0.01, len(x)))
        # 3 bad spectra: perfectly linear (contact artifact)
        for i in range(3):
            spectra.append((2.0 + i * 0.5) * x + 1.0)
        # 2 bad spectra: heavily saturated (clipped)
        for i in range(2):
            s = np.linspace(-5, 5, len(x))
            spectra.append(np.clip(s, -0.5, 0.5))

        all_spectra = np.column_stack(spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(10)]
        df = pd.DataFrame(np.column_stack([x, all_spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(5, 2),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)

    @pytest.fixture
    def clean_dataset(self, sample_spectral_data):
        """Dataset where all spectra are good (sine waves + tiny noise)."""
        return sample_spectral_data

    @pytest.fixture
    def all_bad_dataset(self):
        """Dataset where all spectra are perfectly linear (high linear score)."""
        x = np.linspace(-2, 2, 100)
        spectra = []
        for i in range(5):
            spectra.append((i + 1.0) * x + 0.5)
        all_spectra = np.column_stack(spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(5)]
        df = pd.DataFrame(np.column_stack([x, all_spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(5, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)


class TestFilterBadData(TestFilterBadDataSetup):
    """Tests for filter_bad_data method."""

    def test_dataset_not_found(self, tool_impl):
        """Missing dataset emits error and returns empty string."""
        task = MockTask()
        result = tool_impl.filter_bad_data(task, 'nonexistent')
        assert result == ""
        tool_impl.errorOccurred.emit.assert_called_once()

    def test_normal_filtering(self, tool_impl, normal_dataset):
        """Mixed dataset produces both Good and Bad output datasets."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'TestData',
            weight_saturation=1.0,
            weight_noise=1.0,
            weight_linear=1.0,
            weight_periodic=1.0,
            threshold=0.3
        )

        assert result != ""
        assert Path(result).exists()
        # At least one of good/bad should be created
        has_good = 'TestData - Good Data' in tool_impl._datasets
        has_bad = 'TestData - Bad Data' in tool_impl._datasets
        assert has_good or has_bad

    def test_report_file_created(self, tool_impl, normal_dataset):
        """Report file is written with expected content."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'TestData')

        assert result != ""
        report_path = Path(result)
        assert report_path.exists()
        content = report_path.read_text()
        assert "Filter Bad Data Report" in content
        assert "Good spectra:" in content
        assert "Bad spectra:" in content

    def test_all_good_no_bad_dataset(self, tool_impl):
        """When all spectra are good, Bad Data dataset is not created."""
        # Use cubic polynomial spectra that are clearly nonlinear and well-distributed
        np.random.seed(42)
        x = np.linspace(-2, 2, 100)
        spectra = []
        for i in range(10):
            spectra.append(x**3 + (i + 1) * x**2 + np.random.normal(0, 0.05, len(x)))
        all_spectra = np.column_stack(spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(10)]
        df = pd.DataFrame(np.column_stack([x, all_spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test', dimensions=(5, 2),
            scan_mode='forward', units={'x': 'V', 'y': 'nA'}
        )
        tool_impl._datasets['CleanData'] = SpectralData(data=df, metadata=metadata)
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'CleanData',
            threshold=0.99  # Very high threshold — nothing flagged
        )

        assert result != ""
        assert 'CleanData - Good Data' in tool_impl._datasets
        assert 'CleanData - Bad Data' not in tool_impl._datasets
        # Report should mention this
        content = Path(result).read_text()
        assert "not created" in content.lower() or "Bad spectra: 0" in content

    def test_all_bad_no_good_dataset(self, tool_impl, all_bad_dataset):
        """When all spectra are bad, Good Data dataset is not created."""
        tool_impl._datasets['BadData'] = all_bad_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'BadData',
            weight_linear=1.0,
            weight_saturation=0.0,
            weight_noise=0.0,
            weight_periodic=0.0,
            weight_partial_noise=0.0,
            threshold=0.01  # Very low threshold — everything flagged
        )

        assert result != ""
        assert 'BadData - Bad Data' in tool_impl._datasets
        assert 'BadData - Good Data' not in tool_impl._datasets

    def test_cancellation(self, tool_impl, normal_dataset):
        """Cancelled task returns empty string immediately."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()
        task.cancelled = True

        result = tool_impl.filter_bad_data(task, 'TestData')
        assert result == ""

    def test_fft_dataset_created(self, tool_impl, normal_dataset):
        """FFT Spectra output dataset is created."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData')

        assert 'TestData - FFT Spectra' in tool_impl._datasets
        fft_data = tool_impl._datasets['TestData - FFT Spectra']
        assert 'Frequency' in fft_data.data.columns

    def test_fft_no_nan_columns(self, tool_impl, normal_dataset):
        """FFT output should not contain all-NaN columns."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData')

        fft_data = tool_impl._datasets['TestData - FFT Spectra']
        for col in fft_data.data.columns:
            assert not fft_data.data[col].isna().all(), f"Column {col} is all NaN"

    def test_good_dataset_shape(self, tool_impl, normal_dataset):
        """Good dataset has correct number of spectra columns."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'TestData',
            threshold=0.3
        )

        if 'TestData - Good Data' in tool_impl._datasets:
            good = tool_impl._datasets['TestData - Good Data']
            # Should have independent var column + spectrum columns
            assert good.data.shape[1] >= 2
            # Same number of rows as original
            assert good.data.shape[0] == normal_dataset.data.shape[0]

    def test_bad_dataset_shape(self, tool_impl, normal_dataset):
        """Bad dataset has correct number of spectra columns."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'TestData',
            threshold=0.3
        )

        if 'TestData - Bad Data' in tool_impl._datasets:
            bad = tool_impl._datasets['TestData - Bad Data']
            assert bad.data.shape[1] >= 2
            assert bad.data.shape[0] == normal_dataset.data.shape[0]

    def test_good_plus_bad_equals_total(self, tool_impl, normal_dataset):
        """Sum of good + bad spectra equals total spectra count."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        total = normal_dataset.data.shape[1] - 1  # minus independent var
        good_count = 0
        bad_count = 0
        if 'TestData - Good Data' in tool_impl._datasets:
            good_count = tool_impl._datasets['TestData - Good Data'].data.shape[1] - 1
        if 'TestData - Bad Data' in tool_impl._datasets:
            bad_count = tool_impl._datasets['TestData - Bad Data'].data.shape[1] - 1
        assert good_count + bad_count == total

    def test_data_loaded_emitted(self, tool_impl, normal_dataset):
        """dataLoaded signal is emitted for each created dataset."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        # Should have been called at least once (for good/bad/fft datasets)
        assert tool_impl.dataLoaded.emit.call_count >= 1

    def test_workflow_mode_no_emit(self, tool_impl, normal_dataset):
        """In workflow mode, dataLoaded is not emitted."""
        tool_impl._datasets['TestData'] = normal_dataset
        tool_impl._workflow_mode = True
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        tool_impl.dataLoaded.emit.assert_not_called()

    def test_progress_updated(self, tool_impl, normal_dataset):
        """Task progress is updated during filtering."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData')

        # After processing all spectra, progress should be near 1
        assert task.progress > 0

    def test_zero_weights(self, tool_impl, normal_dataset):
        """All weights zero means combined score is always 0 — all good."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'TestData',
            weight_saturation=0.0,
            weight_noise=0.0,
            weight_linear=0.0,
            weight_periodic=0.0,
            weight_partial_noise=0.0,
            threshold=0.5
        )

        assert result != ""
        # With zero weights, everything should be good
        assert 'TestData - Good Data' in tool_impl._datasets
        good = tool_impl._datasets['TestData - Good Data']
        # All 10 spectra should be good
        assert good.data.shape[1] - 1 == 10

    def test_metadata_preserved(self, tool_impl, normal_dataset):
        """Output datasets preserve metadata from original."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        if 'TestData - Good Data' in tool_impl._datasets:
            good_meta = tool_impl._datasets['TestData - Good Data'].metadata
            assert good_meta.source_type == normal_dataset.metadata.source_type
            assert good_meta.additional_info['original'] == 'TestData'
            assert good_meta.additional_info['filter'] == 'good'

    def test_single_detector_triggers(self, tool_impl):
        """One high score (linear) should flag as BAD even when others are 0."""
        x = np.linspace(-2, 2, 100)
        # Perfectly linear spectrum — linear detector should fire
        spectrum = 3.0 * x + 1.0
        df = pd.DataFrame({'V': x, 'Spectrum_0': spectrum})
        metadata = SpectralMetadata(
            source_type='test', dimensions=(1, 1),
            scan_mode='forward', units={'x': 'V', 'y': 'nA'}
        )
        tool_impl._datasets['LinearOnly'] = SpectralData(data=df, metadata=metadata)
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'LinearOnly',
            weight_saturation=1.0,
            weight_noise=1.0,
            weight_linear=1.0,
            weight_periodic=1.0,
            weight_partial_noise=1.0,
            threshold=0.5
        )

        assert result != ""
        # With max logic, the linear score alone should flag this
        assert 'LinearOnly - Bad Data' in tool_impl._datasets

    def test_max_combination_logic(self, tool_impl):
        """Combined score = max(weighted scores), not average."""
        # Use a dataset with a heavily clipped spectrum
        x = np.linspace(-2, 2, 100)
        spectrum = np.clip(np.linspace(-5, 5, 100), -0.5, 0.5)
        df = pd.DataFrame({'V': x, 'Spectrum_0': spectrum})
        metadata = SpectralMetadata(
            source_type='test', dimensions=(1, 1),
            scan_mode='forward', units={'x': 'V', 'y': 'nA'}
        )
        tool_impl._datasets['ClipTest'] = SpectralData(data=df, metadata=metadata)
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'ClipTest',
            weight_saturation=1.0,
            weight_noise=0.0,
            weight_linear=0.0,
            weight_periodic=0.0,
            weight_partial_noise=0.0,
            threshold=0.5
        )

        # With only saturation enabled, the combined score equals sat_score
        # (not sat_score / 5 as in the old average logic)
        assert result != ""
        content = Path(result).read_text()
        # Should be flagged as BAD since saturation score > 0.5
        assert 'ClipTest - Bad Data' in tool_impl._datasets

    def test_report_includes_trigger_column(self, tool_impl, normal_dataset):
        """Report includes the Trigger column showing which detector dominated."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        content = Path(result).read_text()
        assert "Trigger" in content
        assert "Partial" in content


class TestFilterBadDataPeriodicCorrection(TestFilterBadDataSetup):
    """Tests for periodic noise correction in filter_bad_data."""

    @pytest.fixture
    def periodic_dataset(self):
        """Dataset with spectra that have periodic noise artifacts."""
        np.random.seed(99)
        x = np.linspace(-2, 2, 256)
        spectra = []
        for i in range(5):
            base = np.sin(x * (i + 1))
            # Add periodic noise at high frequency
            artifact = 0.3 * np.sin(2 * np.pi * 30 * np.linspace(0, 1, len(x)))
            spectra.append(base + artifact + np.random.normal(0, 0.01, len(x)))
        all_spectra = np.column_stack(spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(5)]
        df = pd.DataFrame(np.column_stack([x, all_spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test',
            dimensions=(5, 1),
            scan_mode='forward',
            units={'x': 'V', 'y': 'nA'}
        )
        return SpectralData(data=df, metadata=metadata)

    def test_periodic_correction_enabled(self, tool_impl, periodic_dataset):
        """With correct_periodic=True, report mentions correction count."""
        tool_impl._datasets['PData'] = periodic_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'PData',
            correct_periodic=True,
            threshold=0.99  # high threshold so all are "good"
        )

        assert result != ""
        content = Path(result).read_text()
        assert "periodic correction" in content.lower()

    def test_periodic_correction_disabled(self, tool_impl, periodic_dataset):
        """With correct_periodic=False, no correction line in report."""
        tool_impl._datasets['PData'] = periodic_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'PData',
            correct_periodic=False,
            threshold=0.99
        )

        assert result != ""
        content = Path(result).read_text()
        assert "periodic correction applied" not in content.lower()


class TestFilterBadDataEdgeCases(TestFilterBadDataSetup):
    """Edge case tests for filter_bad_data."""

    def test_single_spectrum(self, tool_impl):
        """Dataset with a single spectrum should work."""
        x = np.linspace(-2, 2, 100)
        spectrum = np.sin(x)
        df = pd.DataFrame({'V': x, 'Spectrum_0': spectrum})
        metadata = SpectralMetadata(
            source_type='test', dimensions=(1, 1),
            scan_mode='forward', units={'x': 'V', 'y': 'nA'}
        )
        tool_impl._datasets['Single'] = SpectralData(data=df, metadata=metadata)
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'Single')
        assert result != ""

    def test_dataset_with_nan_values(self, tool_impl):
        """Dataset containing NaN values should not crash."""
        x = np.linspace(-2, 2, 100)
        spectra = []
        for i in range(5):
            s = np.sin(x * (i + 1))
            s[::20] = np.nan  # Sprinkle some NaN
            spectra.append(s)
        all_spectra = np.column_stack(spectra)
        columns = ['V'] + [f'Spectrum_{i}' for i in range(5)]
        df = pd.DataFrame(np.column_stack([x, all_spectra]), columns=columns)
        metadata = SpectralMetadata(
            source_type='test', dimensions=(5, 1),
            scan_mode='forward', units={'x': 'V', 'y': 'nA'}
        )
        tool_impl._datasets['NanData'] = SpectralData(data=df, metadata=metadata)
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'NanData')
        assert result != ""
        # Should not crash and report should exist
        assert Path(result).exists()
