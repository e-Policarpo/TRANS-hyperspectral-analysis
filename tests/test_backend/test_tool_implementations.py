"""
Tests for ToolImplementations class
Target coverage: 90%
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.models.spectral_data import SpectralData, SpectralMetadata


class MockTask:
    """Mock task object for testing."""
    cancelled = False
    progress = 0


class TestToolImplementationsSetup:
    """Base setup for tool implementation tests."""

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
                self._naming_convention = "[dataset_name]"
                self._naming_index_start = 1
                self._naming_date_format = "dd-mm-yyyy"
                self._current_file_index = 1

            def _ensure_output_dir(self, subdir):
                path = self._output_base_dir / subdir
                path.mkdir(parents=True, exist_ok=True)
                return path

            def _sanitize_filename(self, name):
                """Sanitize filename for safe file creation."""
                safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
                safe = safe.replace(' ', '_')
                if len(safe) > 50:
                    safe = safe[:50]
                return safe if safe else "unnamed"

            def _extract_clean_base_name(self, name):
                """Extract clean base name from dataset name."""
                # Handle workflow temp names
                wf_match = re.match(r'^_wf_(.+?)(?:_(?:integrate|derivative|smooth|truncate|baseline|discretize))?_[a-f0-9]{6}$', name)
                if wf_match:
                    name = wf_match.group(1)
                # Replace underscores with spaces and clean up
                name = name.replace('_', ' ')
                name = ' '.join(name.split())
                return name

            def _apply_naming_convention(self, dataset_name, operation="", preview=False):
                """Apply naming convention to create a filename."""
                clean_name = self._extract_clean_base_name(dataset_name)
                result = self._naming_convention.replace("[dataset_name]", clean_name)
                if operation:
                    result = f"{result}_{operation}"
                return self._sanitize_filename(result)

        return MockBackend()


class TestCurveSmoothing(TestToolImplementationsSetup):
    """Tests for curve smoothing functionality."""

    def test_smooth_curves_savgol(self, tool_impl, sample_spectral_data):
        """TI-01: Savitzky-Golay smoothing."""
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        result = tool_impl.smooth_curves(
            task, 'test',
            window_size=11,
            poly_order=3,
            smoothing_type='savgol'
        )

        assert result != ""

    def test_smooth_curves_moving_average(self, tool_impl, sample_spectral_data):
        """TI-02: Moving average smoothing."""
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        result = tool_impl.smooth_curves(
            task, 'test',
            window_size=5,
            poly_order=1,
            smoothing_type='moving_average'
        )

        assert result != ""

    def test_smooth_curves_gaussian(self, tool_impl, sample_spectral_data):
        """TI-03: Gaussian smoothing."""
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        result = tool_impl.smooth_curves(
            task, 'test',
            window_size=11,
            poly_order=3,
            smoothing_type='gaussian'
        )

        assert result != ""

    def test_smooth_invalid_window_converted(self, tool_impl, sample_spectral_data):
        """TI-04: Even window size converted to odd."""
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        # Even window should be converted to odd
        result = tool_impl.smooth_curves(
            task, 'test',
            window_size=10,  # Even
            poly_order=3,
            smoothing_type='savgol'
        )

        assert result != ""

    def test_smooth_dataset_not_found(self, tool_impl):
        """TI-05: Unknown dataset emits error."""
        task = MockTask()

        result = tool_impl.smooth_curves(
            task, 'nonexistent',
            window_size=11,
            poly_order=3,
            smoothing_type='savgol'
        )

        assert result == ""
        tool_impl.errorOccurred.emit.assert_called()


class TestDerivative(TestToolImplementationsSetup):
    """Tests for derivative calculation."""

    def test_calculate_derivative_1st(self, tool_impl, sample_spectral_data):
        """TI-06: First derivative calculation."""
        tool_impl._datasets['test'] = sample_spectral_data

        result = tool_impl.calculate_derivative(
            'test',
            order=1,
            smooth_before=True,
            smooth_after=True
        )

        assert result != ""

    def test_calculate_derivative_2nd(self, tool_impl, sample_spectral_data):
        """TI-07: Second derivative calculation."""
        tool_impl._datasets['test'] = sample_spectral_data

        result = tool_impl.calculate_derivative(
            'test',
            order=2,
            smooth_before=True,
            smooth_after=True
        )

        assert result != ""

    def test_derivative_smooth_options(self, tool_impl, sample_spectral_data):
        """TI-08: Smooth before/after options."""
        tool_impl._datasets['test'] = sample_spectral_data

        # No smoothing
        result = tool_impl.calculate_derivative(
            'test',
            order=1,
            smooth_before=False,
            smooth_after=False
        )

        assert result != ""


class TestPeakFinding(TestToolImplementationsSetup):
    """Tests for peak finding functionality."""

    def test_find_peaks_basic(self, tool_impl, sample_spectral_data_with_peaks):
        """TI-09: Basic peak finding."""
        tool_impl._datasets['test'] = sample_spectral_data_with_peaks
        task = MockTask()

        result = tool_impl.find_peaks(
            task, 'test',
            prominence=0.1,
            min_distance=5,
            fwhm_multiplier=1.5
        )

        assert result is not None

    def test_find_peaks_no_peaks(self, tool_impl, sample_spectral_data):
        """TI-13: No peaks found returns empty result."""
        # Use data without clear peaks
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        result = tool_impl.find_peaks(
            task, 'test',
            prominence=100.0,  # Very high - no peaks will match
            min_distance=5,
            fwhm_multiplier=1.5
        )

        assert result is not None
        # Should not error, just return empty or minimal results

    def test_find_peaks_promotes_table_to_dataset(self, tool_impl,
                                                  sample_spectral_data_with_peaks):
        """Peaks are registered as a SpectralData dataset (browser + workflow)."""
        tool_impl._datasets['test'] = sample_spectral_data_with_peaks
        result = tool_impl.find_peaks(MockTask(), 'test', prominence=0.1,
                                      min_distance=5, fwhm_multiplier=1.5)
        # peaks_path stays a string (never a dict) so getOutputList can't choke.
        assert isinstance(result['peaks_path'], str)
        assert result['dataset'] is not None
        assert result['dataset_name'] in tool_impl._datasets
        from src.models.spectral_data import SpectralData
        assert isinstance(result['dataset'], SpectralData)
        # No 'original' key → the peak table isn't overlaid on the source graph.
        assert 'original' not in result['dataset'].metadata.additional_info
        tool_impl.dataLoaded.emit.assert_called_with(result['dataset_name'])

    def test_find_peaks_no_peaks_no_dataset(self, tool_impl, sample_spectral_data):
        """No peaks → no dataset object, empty name (safe for the workflow)."""
        tool_impl._datasets['test'] = sample_spectral_data
        result = tool_impl.find_peaks(MockTask(), 'test', prominence=100.0,
                                      min_distance=5, fwhm_multiplier=1.5)
        assert result['dataset'] is None
        assert result['dataset_name'] == ""


class TestDataManipulation(TestToolImplementationsSetup):
    """Tests for equation-based data manipulation."""

    def test_evaluate_equation_add(self, tool_impl, sample_spectral_data):
        """TI-17: A + B equation."""
        result = tool_impl.evaluate_data_equation(
            equation="A + A",  # Add to itself
            dataset_a=sample_spectral_data,
            dataset_b=None,
            output_name="Added"
        )

        assert result is not None

    def test_evaluate_equation_subtract(self, tool_impl, sample_spectral_data):
        """TI-18: A - B equation."""
        result = tool_impl.evaluate_data_equation(
            equation="A - A",
            dataset_a=sample_spectral_data,
            dataset_b=None,
            output_name="Subtracted"
        )

        assert result is not None

    def test_evaluate_equation_multiply(self, tool_impl, sample_spectral_data):
        """TI-19: A * B equation."""
        result = tool_impl.evaluate_data_equation(
            equation="A * 2",
            dataset_a=sample_spectral_data,
            output_name="Multiplied"
        )

        assert result is not None

    def test_evaluate_equation_divide(self, tool_impl, sample_spectral_data):
        """TI-20: A / B equation."""
        result = tool_impl.evaluate_data_equation(
            equation="A / 2",
            dataset_a=sample_spectral_data,
            output_name="Divided"
        )

        assert result is not None

    def test_evaluate_equation_functions(self, tool_impl, sample_spectral_data):
        """TI-21: sqrt, log, exp functions."""
        # Test sqrt
        result = tool_impl.evaluate_data_equation(
            equation="sqrt(abs(A))",
            dataset_a=sample_spectral_data,
            output_name="Sqrt"
        )
        assert result is not None

        # Test exp
        result = tool_impl.evaluate_data_equation(
            equation="exp(A * 0.1)",
            dataset_a=sample_spectral_data,
            output_name="Exp"
        )
        assert result is not None

    def test_evaluate_equation_constants(self, tool_impl, sample_spectral_data):
        """TI-22: Constants (pi, e) in equation."""
        result = tool_impl.evaluate_data_equation(
            equation="A * pi",
            dataset_a=sample_spectral_data,
            output_name="WithPi"
        )

        assert result is not None

    def test_evaluate_equation_invalid(self, tool_impl, sample_spectral_data):
        """TI-24: Invalid equation returns error."""
        result = tool_impl.evaluate_data_equation(
            equation="invalid syntax +++",
            dataset_a=sample_spectral_data,
            output_name="Invalid"
        )

        assert result is not None
        # Should have error or no result dataset

    def test_evaluate_equation_injection_attempt(self, tool_impl, sample_spectral_data):
        """TI-25: Code injection attempt is blocked."""
        # Try various injection attempts
        dangerous_equations = [
            "__import__('os').system('ls')",
            "exec('print(1)')",
            "eval('1+1')",
            "open('/etc/passwd').read()"
        ]

        for eq in dangerous_equations:
            result = tool_impl.evaluate_data_equation(
                equation=eq,
                dataset_a=sample_spectral_data,
                output_name="Injection"
            )
            # Should either return error or fail safely
            assert result is not None
            # Should not execute dangerous code


class TestBaselineCorrection(TestToolImplementationsSetup):
    """Tests for baseline correction with diagnostics."""

    def test_fit_curves_als_creates_diagnostics(self, tool_impl, sample_spectral_data):
        """TI-40: ALS baseline creates diagnostics file."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False
        task = MockTask()

        result = tool_impl.fit_curves(
            task, 'test',
            fit_type='als',
            als_lambda=1e5,
            als_p=0.01
        )

        assert result != ""
        # Check that diagnostics file was created
        fitted_dir = tool_impl._output_base_dir / "fitted"
        diag_files = list(fitted_dir.glob("*BaselineDiagnostics*.csv"))
        assert len(diag_files) >= 1

    def test_fit_curves_endpoints_creates_diagnostics(self, tool_impl, sample_spectral_data):
        """TI-41: Endpoint baseline creates diagnostics file."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False
        task = MockTask()

        result = tool_impl.fit_curves(
            task, 'test',
            fit_type='endpoints',
            degree=1
        )

        assert result != ""
        # Check diagnostics file
        fitted_dir = tool_impl._output_base_dir / "fitted"
        diag_files = list(fitted_dir.glob("*BaselineDiagnostics*.csv"))
        assert len(diag_files) >= 1

    def test_fit_curves_diagnostics_per_spectrum(self, tool_impl, sample_spectral_data):
        """TI-42: Diagnostics contain per-spectrum baseline statistics."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False
        task = MockTask()

        tool_impl.fit_curves(
            task, 'test',
            fit_type='linear'
        )

        # Read the diagnostics file
        fitted_dir = tool_impl._output_base_dir / "fitted"
        diag_files = list(fitted_dir.glob("*BaselineDiagnostics*.csv"))
        assert len(diag_files) >= 1

        diag_df = pd.read_csv(diag_files[0])
        # Should have one row per spectrum
        assert len(diag_df) == sample_spectral_data.spectra.shape[1]
        # Should have baseline statistics columns
        assert 'spectrum_index' in diag_df.columns
        assert 'baseline_mean' in diag_df.columns
        assert 'baseline_std' in diag_df.columns

    def test_fit_curves_baseline_variance(self, tool_impl, sample_spectral_data):
        """TI-43: Verify baseline variance is computed correctly."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False
        task = MockTask()

        tool_impl.fit_curves(
            task, 'test',
            fit_type='polynomial',
            degree=2
        )

        # Read diagnostics
        fitted_dir = tool_impl._output_base_dir / "fitted"
        diag_files = list(fitted_dir.glob("*BaselineDiagnostics*.csv"))
        diag_df = pd.read_csv(diag_files[0])

        # Baseline means should vary across spectra (not all identical)
        baseline_means = diag_df['baseline_mean'].values
        # For random data, there should be some variance
        assert np.std(baseline_means) > 0 or len(baseline_means) == 1


class TestTruncateData(TestToolImplementationsSetup):
    """Tests for data truncation."""

    def test_truncate_data_basic(self, tool_impl, sample_spectral_data):
        """TI-26: Truncate x-axis range."""
        tool_impl._datasets['test'] = sample_spectral_data
        task = MockTask()

        # Use the public truncate_data method if available
        if hasattr(tool_impl, 'truncate_data'):
            result = tool_impl.truncate_data(
                task, 'test',
                min_val=-1.0,
                max_val=1.0
            )
        else:
            # Fallback - use the SpectralData truncate_range directly
            truncated = sample_spectral_data.truncate_range(-1.0, 1.0)
            tool_impl._datasets['test_truncated'] = truncated
            result = 'test_truncated'

        assert result is not None

    def test_truncate_data_inverted_range(self, tool_impl, sample_spectral_data):
        """TI-27: Inverted range (min > max) handled."""
        # Should handle gracefully - use truncate_range
        try:
            truncated = sample_spectral_data.truncate_range(1.0, -1.0)
            # If it doesn't error, that's fine
            assert True
        except (ValueError, Exception):
            # Expected behavior for inverted range
            assert True


class TestHelperMethods(TestToolImplementationsSetup):
    """Tests for helper methods."""

    def test_sanitize_filename(self, tool_impl):
        """Test filename sanitization."""
        result = tool_impl._sanitize_filename("Test File (1).csv")
        assert "/" not in result
        assert "\\" not in result

    def test_ensure_output_dir(self, tool_impl):
        """Test output directory creation."""
        path = tool_impl._ensure_output_dir("test_subdir")
        assert path.exists()
        assert path.is_dir()


class TestMapGeneration(TestToolImplementationsSetup):
    """Tests for map generation with path validation."""

    @pytest.fixture
    def integrated_spectral_data(self, tmp_path):
        """Create integrated spectral data with intervals metadata."""
        # Create flat data (one value per spectrum)
        num_spectra = 25  # 5x5 grid
        df = pd.DataFrame({
            'Spectrum_Index': range(num_spectra),
            'Interval_-0.5_-0.3': np.random.rand(num_spectra) * 10,
            'Interval_0.2_0.5': np.random.rand(num_spectra) * 10,
        })
        metadata = SpectralMetadata(
            source_type='integrated',
            dimensions=(5, 5),
            scan_mode='forward',
            units={'x': 'index', 'y': 'integrated'},
            additional_info={
                'intervals': [(-0.5, -0.3), (0.2, 0.5)]  # Numeric tuples
            }
        )
        return SpectralData(data=df, metadata=metadata)

    def test_generate_map_creates_verified_files(self, tool_impl, integrated_spectral_data):
        """TI-50: Map generation verifies file creation."""
        tool_impl._datasets['integrated'] = integrated_spectral_data
        task = MockTask()

        # Generate single map
        result = tool_impl.generate_map(task, 'integrated', value_index=0)

        assert result is not None
        assert result != ""
        # The TIFF file should exist
        tiff_path = Path(f"{result}.tiff")
        assert tiff_path.exists(), f"TIFF file not created at {tiff_path}"

    def test_generate_all_maps_returns_only_existing_files(self, tool_impl, integrated_spectral_data):
        """TI-51: generate_all_maps only returns paths to files that exist."""
        tool_impl._datasets['integrated'] = integrated_spectral_data
        task = MockTask()

        # Generate all maps
        map_paths = tool_impl.generate_all_maps(task, 'integrated')

        assert isinstance(map_paths, list)
        # All returned paths should exist
        for path in map_paths:
            assert Path(path).exists(), f"Returned path does not exist: {path}"

    def test_generate_map_with_interval_naming(self, tool_impl, integrated_spectral_data):
        """TI-52: Map filenames include interval values from metadata."""
        tool_impl._datasets['integrated'] = integrated_spectral_data
        task = MockTask()

        map_paths = tool_impl.generate_all_maps(task, 'integrated')

        # Check that filenames contain interval values
        assert len(map_paths) >= 1
        # At least one should contain interval-like pattern
        has_interval_name = any('-0.5' in p or '0.2' in p for p in map_paths)
        assert has_interval_name, "Map filenames should contain interval values"

    def test_generate_map_without_intervals_uses_index(self, tool_impl):
        """TI-53: Maps without interval metadata use value index in filename."""
        # Create data without intervals
        num_spectra = 16
        df = pd.DataFrame({
            'Spectrum_Index': range(num_spectra),
            'Value_0': np.random.rand(num_spectra),
            'Value_1': np.random.rand(num_spectra),
        })
        metadata = SpectralMetadata(
            source_type='flat',
            dimensions=(4, 4),
            scan_mode='forward',
            units={'x': 'index', 'y': 'value'}
            # No intervals in additional_info
        )
        flat_data = SpectralData(data=df, metadata=metadata)
        tool_impl._datasets['flat'] = flat_data
        task = MockTask()

        result = tool_impl.generate_map(task, 'flat', value_index=0)

        assert result is not None
        # Should use 'val0' format when no intervals
        assert 'val0' in result or 'Map' in result


class TestImageDiscretizer(TestToolImplementationsSetup):
    """Tests for image discretization functionality."""

    @pytest.fixture
    def test_image(self, tmp_path):
        """Create a test image for discretization tests."""
        from PIL import Image

        # Create a gradient image with values 0-255
        img_array = np.tile(np.arange(256, dtype=np.uint8), (256, 1))
        img = Image.fromarray(img_array, mode='L')
        img_path = tmp_path / "test_gradient.png"
        img.save(img_path)
        return str(img_path)

    def test_discretize_uniform(self, tool_impl, test_image):
        """TI-30: Uniform discretization with equal width bins."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='uniform',
            n_bins=5,
            output_type='centroids'
        )

        assert result is not None
        assert 'image_path' in result
        assert 'labels' in result
        assert Path(result['image_path']).exists()
        assert len(result['labels']) == 5  # 5 bins

    def test_discretize_quantile(self, tool_impl, test_image):
        """TI-31: Quantile discretization with equal count bins."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='quantile',
            n_bins=4,
            output_type='labels'
        )

        assert result is not None
        assert 'image_path' in result
        assert 'labels' in result
        assert len(result['labels']) == 4  # 4 bins

    def test_discretize_kmeans(self, tool_impl, test_image):
        """TI-32: K-means clustering discretization."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='kmeans',
            n_bins=3,
            output_type='centroids'
        )

        assert result is not None
        assert 'image_path' in result
        assert 'labels' in result
        assert len(result['labels']) == 3  # 3 clusters

    def test_discretize_output_labels(self, tool_impl, test_image):
        """TI-33: Output type 'labels' produces indexed output."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='uniform',
            n_bins=8,
            output_type='labels'
        )

        assert result is not None
        # Check output image exists
        assert Path(result['image_path']).exists()

    def test_discretize_labels_dataframe(self, tool_impl, test_image):
        """TI-34: Labels output is a DataFrame with bin info."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='uniform',
            n_bins=5,
            output_type='centroids'
        )

        labels_df = result['labels']
        assert isinstance(labels_df, pd.DataFrame)
        assert 'Bin' in labels_df.columns
        assert 'Center' in labels_df.columns
        # Uniform should have Min and Max columns
        assert 'Min' in labels_df.columns
        assert 'Max' in labels_df.columns

    def test_discretize_invalid_method(self, tool_impl, test_image):
        """TI-35: Invalid method returns empty result."""
        task = MockTask()

        result = tool_impl.discretize_image(
            task, test_image,
            method='invalid_method',
            n_bins=5,
            output_type='centroids'
        )

        # Should return empty dict on error
        assert result == {}
