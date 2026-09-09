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
            weight_featureless=0.0,
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


class TestFilterBadDataExports(TestFilterBadDataSetup):
    """Every output of a run is written into one folder per filtered dataset."""

    def test_all_outputs_written_to_one_folder(self, tool_impl, normal_dataset):
        """Good, bad, FFT and report land in curves/<dataset>_Filtered/."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)

        assert result != ""
        folder = Path(result).parent
        assert folder.name == 'TestData_Filtered'
        assert folder.parent.name == 'curves'

        names = sorted(p.name for p in folder.iterdir())
        assert 'TestData_filter_report.txt' in names
        assert 'TestData_Good_Data.csv' in names
        assert 'TestData_Bad_Data.csv' in names
        assert 'TestData_FFT_Spectra.csv' in names

    def test_exported_csv_matches_dataset(self, tool_impl, normal_dataset):
        """The exported CSV holds the same curves as the in-memory dataset."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)
        good = tool_impl._datasets['TestData - Good Data']

        exported = pd.read_csv(Path(result).parent / 'TestData_Good_Data.csv')
        assert list(exported.columns) == list(good.data.columns)
        np.testing.assert_allclose(exported.values, good.data.values,
                                   rtol=1e-6, equal_nan=True)

    def test_report_lists_exported_files(self, tool_impl, normal_dataset):
        """The report names the folder and the files written next to it."""
        tool_impl._datasets['TestData'] = normal_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(task, 'TestData', threshold=0.3)
        content = Path(result).read_text()

        assert "Output folder:" in content
        assert "TestData_Good_Data.csv" in content

    def test_missing_side_is_not_exported(self, tool_impl, all_bad_dataset):
        """No Good Data dataset means no Good Data CSV."""
        tool_impl._datasets['BadData'] = all_bad_dataset
        task = MockTask()

        result = tool_impl.filter_bad_data(
            task, 'BadData',
            weight_linear=1.0, weight_saturation=0.0, weight_noise=0.0,
            weight_periodic=0.0, weight_partial_noise=0.0,
            threshold=0.01
        )

        folder = Path(result).parent
        names = sorted(p.name for p in folder.iterdir())
        assert 'BadData_Bad_Data.csv' in names
        assert 'BadData_Good_Data.csv' not in names


class TestEmptyAndFeaturelessSpectra(TestFilterBadDataSetup):
    """The reported defect, at tool level.

    Two ways a useless dI/dV curve used to reach 'Good Data': an all-NaN
    column, which every detector scores 0 because it cannot be measured, and a
    curve that is flat above the noise floor, which no detector asked about.
    On the real calibration dataset 103 of 167 "good" spectra were entirely
    empty.
    """

    @staticmethod
    def _pink_noise(n, rng):
        """1/f noise — the correlated noise a dead STS channel actually shows.

        White noise would be caught by ``detect_noise`` on its own; what makes
        the featureless test necessary is that real dead spectra wander far
        above the white-noise sigma while holding no shape.
        """
        freqs = np.fft.rfftfreq(n)
        freqs[0] = freqs[1]
        spectrum = (rng.normal(size=freqs.size)
                    + 1j * rng.normal(size=freqs.size)) / np.sqrt(freqs)
        spectrum[0] = 0
        noise = np.fft.irfft(spectrum, n=n)
        return noise / noise.std()

    @pytest.fixture
    def mixed_dataset(self):
        """Real band edges, flat 1/f noise, and empty columns in one dataset."""
        rng = np.random.default_rng(27)
        v = np.linspace(-1.5, 1.5, 256)
        edges = (np.exp((v - 0.8) / 0.08) / (1 + np.exp((v - 0.8) / 0.08))
                 + np.exp(-(v + 0.7) / 0.08) / (1 + np.exp(-(v + 0.7) / 0.08)))
        columns, spectra = [], []
        # Flat above the noise floor, with the correlated noise real dead
        # spectra carry: the plain-noise detectors do not see these, which is
        # exactly why the featureless test had to be added.
        for i in range(4):
            columns.append(f'flat_{i}')
            spectra.append(0.5 + 0.01 * self._pink_noise(len(v), rng)
                           + rng.normal(0, 0.002, len(v)))
        for i in range(4):                       # real spectra
            columns.append(f'real_{i}')
            spectra.append(edges + rng.normal(0, 0.01, len(v)))
        for i in range(2):                       # empty
            columns.append(f'empty_{i}')
            spectra.append(np.full(len(v), np.nan))
        df = pd.DataFrame(np.column_stack([v] + spectra), columns=['V'] + columns)
        metadata = SpectralMetadata(
            source_type='test', dimensions=(10, 1), scan_mode='forward',
            units={'independent': 'V', 'dependent': 'A/V'})
        return SpectralData(data=df, metadata=metadata)

    def test_empty_spectra_are_rejected(self, tool_impl, mixed_dataset):
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed')

        good = tool_impl._datasets['Mixed - Good Data']
        assert not any(c.startswith('empty') for c in good.spectra.columns)
        bad = tool_impl._datasets['Mixed - Bad Data']
        assert all(f'empty_{i}' in bad.spectra.columns for i in range(2))

    def test_no_all_nan_column_survives(self, tool_impl, mixed_dataset):
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed')

        values = tool_impl._datasets['Mixed - Good Data'].spectra.values
        assert np.isfinite(values).sum(axis=0).min() > 0

    def test_flat_spectra_are_rejected(self, tool_impl, mixed_dataset):
        """The reported defect: flat above the noise floor is not good data."""
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed')

        good = tool_impl._datasets['Mixed - Good Data']
        assert not any(c.startswith('flat') for c in good.spectra.columns)

    def test_real_spectra_survive(self, tool_impl, mixed_dataset):
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed')

        good = tool_impl._datasets['Mixed - Good Data']
        assert sorted(good.spectra.columns) == [f'real_{i}' for i in range(4)]

    def test_featureless_weight_zero_disables_the_check(self, tool_impl, mixed_dataset):
        """Turning the detector off brings the flat spectra back — but never
        the empty ones, which are rejected before any weight is consulted."""
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed', weight_featureless=0.0)

        good = tool_impl._datasets['Mixed - Good Data'].spectra.columns
        assert any(c.startswith('flat') for c in good)
        assert not any(c.startswith('empty') for c in good)

    def test_report_records_the_new_columns(self, tool_impl, mixed_dataset):
        tool_impl._datasets['Mixed'] = mixed_dataset
        report = Path(tool_impl.filter_bad_data(MockTask(), 'Mixed')).read_text()

        assert 'Featless' in report
        assert 'Cohere' in report
        assert 'rejected as empty' in report
        assert 'featureless' in report

    def test_min_coherence_is_tunable(self, tool_impl, mixed_dataset):
        """Demanding more coherence than a real spectrum has flags everything."""
        tool_impl._datasets['Mixed'] = mixed_dataset
        tool_impl.filter_bad_data(MockTask(), 'Mixed', min_coherence=0.95)

        assert 'Mixed - Good Data' not in tool_impl._datasets

    def test_batch_spec_is_registered(self):
        """The tool is available to a multi-dataset selection."""
        from src.backend.batch_tools import get_spec

        spec = get_spec('filter_bad_data')
        assert spec is not None
        assert spec.method == 'filter_bad_data'
        assert spec.takes_task
        assert 'weight_featureless' in spec.defaults
        coerced = spec.coerce({'weight_featureless': '0.0', 'correct_periodic': 'true'})
        assert coerced['weight_featureless'] == 0.0
        assert coerced['correct_periodic'] is True


class TestOutlierRemoval(TestFilterBadDataSetup):
    """Outliers at tool level.

    Every other detector judges a curve on its own. An outlier may be a sound
    measurement and still be wrong to average in, so it is opt-in, decided
    per kind, and capped — past the cap what has been found is a distribution
    rather than a few odd curves, and nothing is removed.
    """

    @staticmethod
    def _edge(v, gap_hi=0.8):
        return (np.exp((v - gap_hi) / 0.06) / (1 + np.exp((v - gap_hi) / 0.06))
                + np.exp(-(v + 0.7) / 0.06) / (1 + np.exp(-(v + 0.7) / 0.06)))

    def _overview(self, n_offset=1, points=(1, 2), reps=20, with_meta=True):
        """An overview dataset: two points, `reps` repetitions each."""
        rng = np.random.default_rng(21)
        v = np.linspace(-1.5, 1.5, 128)
        columns, meta, data = [], [], {}
        for point in points:
            for rep in range(1, reps + 1):
                name = f"P{point:02d}R{rep:02d}"
                columns.append(name)
                meta.append({'column': name, 'point_index': point, 'rep': rep})
                curve = self._edge(v, 0.8 if point == 1 else 0.5)
                curve = curve + rng.normal(0, 0.01, v.size)
                if point == 2 and rep <= n_offset:
                    curve = curve * 400
                data[name] = curve
        df = pd.DataFrame({'V': v, **data})
        metadata = SpectralMetadata(
            source_type='test', dimensions=(len(columns), 1), scan_mode='point',
            units={'independent': 'V', 'dependent': 'A/V'},
            additional_info={'spectrum_meta': meta} if with_meta else {})
        return SpectralData(df, metadata)

    def test_off_by_default(self, tool_impl):
        """Removing sound curves must never be something that just happens."""
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV')
        good = tool_impl._datasets['OV - Good Data'].spectra.columns
        assert 'P02R01' in good

    def test_offset_outlier_is_removed_when_asked(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)
        good = tool_impl._datasets['OV - Good Data'].spectra.columns
        assert 'P02R01' not in good
        assert 'P02R02' in good

    def test_removed_outliers_land_in_bad_data(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)
        assert 'P02R01' in tool_impl._datasets['OV - Bad Data'].spectra.columns

    def test_beyond_the_limit_nothing_goes(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview(n_offset=8)
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True,
            max_offset_outliers=5)).read_text()

        good = tool_impl._datasets['OV - Good Data'].spectra.columns
        assert all(f'P02R{i:02d}' in good for i in range(1, 9))
        assert 'distribution' in report
        assert 'check them by eye' in report

    def test_points_are_compared_separately(self, tool_impl):
        """Two points with different gaps must not be outliers of each other."""
        tool_impl._datasets['OV'] = self._overview(n_offset=0)
        tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True,
            filter_bandgap_outliers=True)
        good = tool_impl._datasets['OV - Good Data'].spectra.columns
        assert any(c.startswith('P01') for c in good)
        assert any(c.startswith('P02') for c in good)

    def test_whole_dataset_grouping_is_available(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True,
            outlier_group_by='dataset')).read_text()
        assert 'the whole dataset' in report

    def test_a_dataset_without_metadata_is_warned_about(self, tool_impl):
        """It still runs — the user may know what they are doing — but the
        report says every curve was compared against every other."""
        tool_impl._datasets['OV'] = self._overview(with_meta=False)
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True)).read_text()
        assert 'records no per-spectrum point index' in report

    def test_report_names_the_kind_and_the_curve(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True)).read_text()
        assert 'Removed 1 offset outlier(s): P02R01.' in report
        assert 'P02R01 (offset)' in report

    def test_kinds_are_independent(self, tool_impl):
        """Asking for saturation must not remove an offset outlier."""
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_saturation_outliers=True,
            filter_offset_outliers=False)
        assert 'P02R01' in tool_impl._datasets['OV - Good Data'].spectra.columns

    def test_batch_spec_exposes_the_new_knobs(self):
        from src.backend.batch_tools import get_spec

        coerced = get_spec('filter_bad_data').coerce({
            'filter_offset_outliers': 'true', 'max_offset_outliers': '3',
            'outlier_group_by': 'dataset', 'outlier_intervals': '12'})
        assert coerced['filter_offset_outliers'] is True
        assert coerced['max_offset_outliers'] == 3
        assert coerced['outlier_group_by'] == 'dataset'
        assert coerced['outlier_intervals'] == 12
        assert coerced['filter_bandgap_outliers'] is False


class TestPerPointAverages(TestOutlierRemoval):
    """The dataset the outlier pass exists to produce.

    An overview holds every repetition at every point; what the analysis
    wants is one curve per point, and that average is only worth taking once
    the curves that would drag it are gone.
    """

    def test_written_when_outliers_are_filtered(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)
        assert 'OV - Outliers Removed' in tool_impl._datasets

    def test_not_written_when_outlier_filtering_is_off(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV')
        assert 'OV - Outliers Removed' not in tool_impl._datasets

    def test_one_column_per_point(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview(points=(1, 2, 3), reps=15)
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)
        averaged = tool_impl._datasets['OV - Outliers Removed']
        assert list(averaged.spectra.columns) == ['P01', 'P02', 'P03']

    def test_the_average_excludes_the_outlier(self, tool_impl):
        """The whole point: one curve at 400x must not drag the mean."""
        tool_impl._datasets['OV'] = self._overview(n_offset=1)
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)

        averaged = tool_impl._datasets['OV - Outliers Removed']
        good = tool_impl._datasets['OV - Good Data'].spectra
        survivors = [c for c in good.columns if c.startswith('P02')]
        np.testing.assert_allclose(
            averaged.spectra['P02'].values,
            np.nanmean(good[survivors].values, axis=1), equal_nan=True)

    def test_the_counts_are_fully_accounted_for(self, tool_impl):
        """"13 averaged" alone is ambiguous — say how many the input held,
        how many the tests took, and how many the outlier pass took."""
        tool_impl._datasets['OV'] = self._overview(n_offset=1, reps=20)
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)

        for entry in (tool_impl._datasets['OV - Outliers Removed']
                      .metadata.additional_info['spectrum_meta']):
            assert entry['n_input'] == 20
            assert (entry['n_averaged'] + entry['n_outliers_removed']
                    + entry['n_rejected_by_tests']) == entry['n_input']

    def test_a_point_keeps_its_position(self, tool_impl):
        """Without this the averages map onto point indices, not nanometres."""
        dataset = self._overview()
        for entry in dataset.metadata.additional_info['spectrum_meta']:
            entry['location_m'] = [entry['point_index'] * 1e-9, 0.0]
        tool_impl._datasets['OV'] = dataset
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)

        meta = (tool_impl._datasets['OV - Outliers Removed']
                .metadata.additional_info['spectrum_meta'])
        assert [e['location_m'] for e in meta] == [[1e-9, 0.0], [2e-9, 0.0]]

    def test_it_records_where_it_came_from(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)
        info = tool_impl._datasets['OV - Outliers Removed'].metadata.additional_info
        assert info['original'] == 'OV'
        assert info['averaged_over_reps'] is True
        assert info['filter'] == 'outliers_removed'

    def test_a_csv_is_written_beside_the_others(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True))
        written = {f.name for f in report.parent.glob('*.csv')}
        assert any('Outliers_Removed' in name for name in written), written

    def test_the_report_says_what_was_averaged(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        report = Path(tool_impl.filter_bad_data(
            MockTask(), 'OV', filter_offset_outliers=True)).read_text()
        assert 'Per-point averages' in report

    def test_a_point_whose_curves_all_failed_is_skipped(self, tool_impl):
        """No column rather than a column of NaN."""
        dataset = self._overview(points=(1, 2), reps=20)
        values = dataset.data
        for column in [c for c in values.columns if c.startswith('P01')]:
            values[column] = np.nan
        tool_impl._datasets['OV'] = SpectralData(values, dataset.metadata)
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True)

        averaged = tool_impl._datasets['OV - Outliers Removed']
        assert list(averaged.spectra.columns) == ['P02']

    def test_whole_dataset_grouping_gives_one_average(self, tool_impl):
        tool_impl._datasets['OV'] = self._overview()
        tool_impl.filter_bad_data(MockTask(), 'OV', filter_offset_outliers=True,
                                  outlier_group_by='dataset')
        averaged = tool_impl._datasets['OV - Outliers Removed']
        assert averaged.num_spectra == 1
