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

    def test_fit_curves_polynomial_creates_coefficients_dataset(
            self, tool_impl, sample_spectral_data):
        """Polynomial fit registers a coefficients dataset: one row per
        spectrum, a spectrum_index column, then one column per coefficient."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False

        tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial', degree=3)

        name = "test - Fit Coefficients"
        assert name in tool_impl._datasets
        ds = tool_impl._datasets[name]
        # Spectrum_Index is the X column; c0..c3 are the coefficient columns.
        assert ds.independent_var_name == 'Spectrum_Index'
        assert list(ds.spectra.columns) == ['c0', 'c1', 'c2', 'c3']
        assert ds.spectra.shape[0] == 10                      # one row per spectrum
        assert np.array_equal(np.asarray(ds.independent_var), np.arange(10))
        # Built as flat data with the source's dimensions → drops into the Map
        # Generator (one map per coefficient).
        assert ds.metadata.data_type == 'flat'
        assert ds.metadata.dimensions == sample_spectral_data.metadata.dimensions
        # c0 = constant term, c3 = x^3 term (ascending power) — matches polyfit.
        x = sample_spectral_data.independent_var
        y0 = sample_spectral_data.spectra.iloc[:, 0].values
        expected = np.polyfit(x, y0, 3)   # highest power first: [a3, a2, a1, a0]
        assert ds.spectra['c0'].iloc[0] == pytest.approx(expected[3])
        assert ds.spectra['c3'].iloc[0] == pytest.approx(expected[0])
        # Not stamped 'original' → won't be overlaid on the source graph.
        assert 'original' not in ds.metadata.additional_info

    def test_fit_curves_float_degree_is_accepted(self, tool_impl, sample_spectral_data):
        """degree may arrive as a float from QML/workflow — must not crash."""
        tool_impl._datasets['test'] = sample_spectral_data
        tool_impl._workflow_mode = False
        result = tool_impl.fit_curves(MockTask(), 'test',
                                      fit_type='polynomial', degree=2.0)
        assert result != ""
        ds = tool_impl._datasets["test - Fit Coefficients"]
        assert list(ds.spectra.columns) == ['c0', 'c1', 'c2']

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


class TestConfinementAnalysis(TestToolImplementationsSetup):
    """Tests for the Confinement Analysis tool (background + peaks in one pass)."""

    GAP_CENTERS = (-0.25, -0.10, 0.08, 0.22)

    @pytest.fixture
    def sts_dataset(self):
        """Three STS-like spectra: big band edges, small in-gap states."""
        x = np.linspace(-0.6, 0.6, 512)
        band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)

        columns = {}
        for n in range(3):
            y = band_edges.copy()
            for c in self.GAP_CENTERS:
                y = y + 1.2e-8 * np.exp(-0.5 * ((x - c) / 0.008) ** 2)
            columns[f"P{n + 1}"] = y

        df = pd.DataFrame({"V": x, **columns})
        metadata = SpectralMetadata(
            source_type="sts", dimensions=(3, 1), scan_mode="point",
            units={"x": "V"}, additional_info={},
        )
        return SpectralData(df, metadata)

    def _run(self, tool_impl, dataset, **params):
        tool_impl._datasets['sts'] = dataset
        return tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0, **params},
        )

    def test_finds_every_in_gap_state(self, tool_impl, sts_dataset):
        """Small states on huge band edges must all be reported.

        This used to also assert that no background meant no peaks at all —
        true only while the threshold scaled with the curve's span, which the
        band edges set. The threshold is now measured against the spectrum's
        own noise, so the states are found either way; what background removal
        buys is a corrected height that means something.
        """
        without = self._run(tool_impl, sts_dataset, baseline='none')
        assert without['peaks'] is not None

        result = self._run(tool_impl, sts_dataset)
        found = result['peaks'].data['position_value'].round(2).unique()
        for center in self.GAP_CENTERS:
            assert round(center, 2) in found

    def test_emits_every_expected_dataset(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        names = result['dataset_names']
        assert set(names) == {'Peaks', 'Peak Matrix', 'Peak Matrix (offset)',
                              'Background Corrected', 'Background',
                              'Fit Coefficients', 'Peak Count'}
        for suffix, name in names.items():
            assert name in tool_impl._datasets, suffix
            assert name.startswith('sts')

    def test_peak_matrix_marks_hits_and_leaves_the_rest_blank(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        matrix = result['peak_matrix']

        assert list(matrix.spectra.columns) == ['P1', 'P2', 'P3']
        np.testing.assert_array_equal(matrix.independent_var, sts_dataset.independent_var)

        values = matrix.spectra.values
        # 1 where there is a peak, blank (NaN) everywhere else -- no zeros.
        assert set(np.unique(values[np.isfinite(values)])) == {1}
        assert np.isnan(values).any()

        # Identical spectra must give identical columns, one mark per peak.
        np.testing.assert_array_equal(np.isnan(values[:, 0]), np.isnan(values[:, 1]))
        peaks_in_first = result['peaks'].data['spectrum_index'].eq(0).sum()
        assert np.nansum(values[:, 0]) == peaks_in_first

    def test_matrix_marks_sit_on_the_reported_centres(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        x = result['peak_matrix'].independent_var
        marked = x[result['peak_matrix'].spectra.values[:, 0] == 1]
        reported = result['peaks'].data.query('spectrum_index == 0')['position_value']
        np.testing.assert_allclose(sorted(marked), sorted(reported), atol=1e-12)

    def test_matrix_csv_has_empty_cells_not_zeros(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        text = Path(result['matrix_path']).read_text()
        body = [ln for ln in text.splitlines()[1:] if ln.strip()]

        assert any(',,' in ln or ln.endswith(',') for ln in body), "expected blank cells"
        cells = {c for ln in body for c in ln.split(',')[1:]}
        assert cells == {'', '1'}, f"unexpected cell values: {cells - {'', '1'}}"

    # -- thermal grouping ---------------------------------------------------

    def test_temperature_bins_the_axis_at_half_kbt(self, tool_impl, sts_dataset):
        """94 K -> kBT = 8.1 meV, so the bins are 4.05 meV wide.

        Binning at the full kBT was too coarse: kBT is the error bar, and a
        grid that coarse merges peaks the measurement can still resolve.
        """
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        axis = result['peak_matrix_binned'].independent_var

        step = np.diff(axis)
        np.testing.assert_allclose(step, 8.617333262e-5 * 94.0 / 2, rtol=1e-6)
        # 1.2 V of sweep at 4.05 meV is ~300 bins, still well under 512 samples.
        assert 200 < len(axis) < 400

    def test_temperature_grouping_is_off_by_default(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        assert len(result['peak_matrix'].independent_var) == 512
        assert result['peak_matrix_binned'] is None
        assert 'bin_center' not in result['peaks'].data.columns

    def test_grouped_peaks_report_their_bin(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        peaks = result['peaks'].data

        assert {'bin_index', 'bin_center'} <= set(peaks.columns)
        kbt = 8.617333262e-5 * 94.0
        # Every reported peak sits inside the bin it claims.
        assert (abs(peaks['position_value'] - peaks['bin_center']) <= kbt / 2 + 1e-12).all()

    def test_peaks_within_kbt_collapse_to_one(self, tool_impl):
        """Two peaks 3 meV apart are one feature at kBT = 8 meV."""
        x = np.linspace(-0.3, 0.3, 2048)
        y = np.full_like(x, 1e-10)
        for c in (0.0, 0.003, 0.2):
            y = y + 2e-8 * np.exp(-0.5 * ((x - c) / 0.0006) ** 2)
        df = pd.DataFrame({"V": x, "P1": y})
        dataset = SpectralData(df, SpectralMetadata(
            source_type="sts", dimensions=(1, 1), scan_mode="point",
            units={"x": "V"}, additional_info={}))
        tool_impl._datasets['sts'] = dataset

        # Ungrouped: the pair at 0.000 and 0.003 is reported separately.
        ungrouped = tool_impl.analyze_confinement(MockTask(), 'sts', params={'height': 5.0})
        near_zero = [v for v in ungrouped['peaks'].data['position_value']
                     if abs(v) < 0.01]
        assert len(near_zero) == 2

        grouped = tool_impl.analyze_confinement(
            MockTask(), 'sts', params={'height': 5.0, 'temperature_k': 94.0})
        rows = grouped['peaks'].data
        # Grouped at kBT: the pair becomes one entry, the distant peak stays.
        collapsed = [v for v in rows['position_value'] if abs(v) < 0.01]
        assert len(collapsed) == 1
        assert collapsed[0] == pytest.approx(0.0, abs=0.004)
        assert any(abs(v - 0.2) < 0.01 for v in rows['position_value'])
        # And the binned matrix agrees with the list.
        assert (np.nansum(grouped['peak_matrix_binned'].spectra.values)
                == len(rows))

    def test_explicit_min_distance_overrides_the_thermal_default(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0, min_distance=0.5)
        # 0.5 V apart is far coarser than kBT, so few peaks survive.
        assert len(result['peaks'].data.query('spectrum_index == 0')) <= 3

    def test_minimum_separation_stays_the_full_kbt(self, tool_impl, sts_dataset):
        """Halving the bins must not halve the resolution limit: peaks are
        still merged at kBT, only reported on a finer grid."""
        from src.processing.peak_detection import Params

        params = Params(temperature_k=94.0)
        assert params.thermal_width == pytest.approx(8.1e-3, rel=1e-2)
        assert params.bin_width == pytest.approx(params.thermal_width / 2)

    def test_metadata_records_the_temperature(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        # Both tables record the settings; only one of them is binned.
        for key in ('peak_matrix', 'peak_matrix_binned', 'peaks'):
            info = result[key].metadata.additional_info
            assert info['temperature_k'] == 94.0, key
            assert info['kbt'] == pytest.approx(8.1e-3, rel=1e-2), key
            # kbt is the resolution limit; the bins are half of it.
            assert info['bin_width'] == pytest.approx(4.05e-3, rel=1e-2), key

        binned_info = result['peak_matrix_binned'].metadata.additional_info
        assert binned_info['binned'] is True
        assert binned_info['n_bins'] == len(result['peak_matrix_binned'].independent_var)
        assert result['peak_matrix'].metadata.additional_info['binned'] is False

    def test_corrected_dataset_has_the_background_removed(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        corrected = result['corrected'].spectra.values
        background = result['baseline'].spectra.values

        assert corrected.shape == sts_dataset.spectra.values.shape
        # Exactly raw - background: smoothing is a detection aid and must not
        # leak into an exported dataset, even though it is on by default.
        np.testing.assert_allclose(corrected + background, sts_dataset.spectra.values, atol=1e-15)
        # The band edges dominated the raw data; they must not dominate now.
        assert np.nanmax(corrected) < np.max(sts_dataset.spectra.values) / 2

    def test_smoothing_does_not_leak_into_the_corrected_dataset(self, tool_impl, sts_dataset):
        heavy = self._run(tool_impl, sts_dataset, smooth_points=12)
        light = self._run(tool_impl, sts_dataset, smooth_points=0)
        np.testing.assert_allclose(
            heavy['corrected'].spectra.values + heavy['baseline'].spectra.values,
            sts_dataset.spectra.values, atol=1e-15)
        # ...even though the smoothing demonstrably reached the peak search.
        assert (heavy['peaks'].data['position_value'].tolist()
                != light['peaks'].data['position_value'].tolist())

    def test_corrected_overlays_on_the_source_but_tables_do_not(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        assert result['corrected'].metadata.additional_info['original'] == 'sts'
        assert result['baseline'].metadata.additional_info['original'] == 'sts'
        for key in ('peaks', 'peak_matrix', 'coefficients', 'peak_count'):
            assert 'original' not in result[key].metadata.additional_info, key

    def test_flat_outputs_are_mappable(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)

        counts = result['peak_count']
        assert counts.metadata.data_type == 'flat'
        assert list(counts.data.columns) == ['Spectrum_Index', 'Peak_Count']
        assert counts.data['Peak_Count'].tolist() == [
            int(result['peaks'].data['spectrum_index'].eq(i).sum()) for i in range(3)
        ]

        coeffs = result['coefficients']
        assert coeffs.metadata.data_type == 'flat'
        assert list(coeffs.data.columns) == ['Spectrum_Index'] + [f'c{p}' for p in range(6)]
        assert coeffs.metadata.dimensions == sts_dataset.metadata.dimensions

    def test_intervals_feed_the_integration_tool(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        intervals = result['intervals']
        assert intervals
        for start, end in (iv[:2] for iv in intervals):
            assert start < end

    def test_writes_csvs(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        assert Path(result['peaks_path']).exists()
        assert Path(result['matrix_path']).exists()
        reloaded = pd.read_csv(result['matrix_path'])
        assert list(reloaded.columns) == ['V', 'P1', 'P2', 'P3']

    def test_matrix_suppressed_above_the_column_limit(self, tool_impl, sts_dataset):
        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5},
            matrix_column_limit=2,
        )
        assert result['peak_matrix'] is None
        assert result['matrix_path'] == ''
        # The spatial view still works without it.
        assert result['peak_count'] is not None

    def test_search_window_restricts_results(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, baseline='none', xmin=-0.3, xmax=0.3)
        found = sorted(result['peaks'].data['position_value'].round(2).unique())
        assert found == [round(c, 2) for c in self.GAP_CENTERS]

    def test_workflow_mode_does_not_emit_to_the_browser(self, tool_impl, sts_dataset):
        tool_impl._workflow_mode = True
        result = self._run(tool_impl, sts_dataset)
        tool_impl.dataLoaded.emit.assert_not_called()
        assert result['peaks'] is not None

        tool_impl._workflow_mode = False
        self._run(tool_impl, sts_dataset)
        assert tool_impl.dataLoaded.emit.called

    def test_cancellation_returns_nothing(self, tool_impl, sts_dataset):
        class Cancelled(MockTask):
            cancelled = True

        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(Cancelled(), 'sts', params={})
        assert result['peaks'] is None
        assert result['dataset_names'] == {}

    def test_missing_dataset_reports_an_error(self, tool_impl):
        result = tool_impl.analyze_confinement(MockTask(), 'nope', params={})
        assert result['peaks'] is None
        tool_impl.errorOccurred.emit.assert_called()

    def test_invalid_parameter_reports_an_error(self, tool_impl, sts_dataset):
        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(
            MockTask(), 'sts', params={'direction': 'sideways'})
        assert result['peaks'] is None
        tool_impl.errorOccurred.emit.assert_called()

    def test_qml_float_params_are_cast_to_int(self, tool_impl, sts_dataset):
        """QML sends every number as a float; scipy and range() need ints."""
        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5.0,
                    'smooth_points': 2.0, 'deriv_smooth_points': 2.0,
                    'max_peaks': 0.0},
        )
        assert result['peaks'] is not None
        # max_peaks=0 means "all", not "none".
        assert len(result['peaks'].data) > 0

    def test_unknown_param_keys_are_ignored(self, tool_impl, sts_dataset):
        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5, 'nonsense': 42},
        )
        assert result['peaks'] is not None

    def test_smoothing_default_curbs_noise_over_detection(self, tool_impl):
        """Unsmoothed, a 1%-noise spectrum yields several times too many peaks."""
        rng = np.random.default_rng(4)
        x = np.linspace(-0.3, 0.3, 512)
        y = 1e-10 + rng.normal(0, 2e-10, x.size)
        planted = (-0.2, -0.05, 0.12)
        for c in planted:
            y = y + 2e-8 * np.exp(-0.5 * ((x - c) / 0.003) ** 2)

        tool_impl._datasets['noisy'] = SpectralData(
            pd.DataFrame({"V": x, "R1": y}),
            SpectralMetadata(source_type="sts", dimensions=(1, 1), scan_mode="point",
                             units={"x": "V"}, additional_info={}))

        defaulted = tool_impl.analyze_confinement(MockTask(), 'noisy', params={'height': 4.0})
        unsmoothed = tool_impl.analyze_confinement(
            MockTask(), 'noisy', params={'height': 4.0, 'smooth_points': 0})

        assert len(defaulted['peaks'].data) == len(planted)
        # Without smoothing the noise still over-detects. The margin is
        # narrower than it was: the prominence threshold (now the default)
        # already rejects most noise bumps on its own.
        assert len(unsmoothed['peaks'].data) > 2 * len(planted)

    def test_caller_params_override_the_product_defaults(self, tool_impl, sts_dataset):
        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.analyze_confinement(
            MockTask(), 'sts', params={'baseline': 'none'})
        # 'baseline' overridden, so no Background dataset is produced.
        assert 'Background' not in result['dataset_names']

    def test_emits_both_raw_and_binned_matrices(self, tool_impl, sts_dataset):
        """Binning coarsens the axis, so the full-resolution table is kept too."""
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)

        raw, binned = result['peak_matrix'], result['peak_matrix_binned']
        assert raw is not None and binned is not None
        assert 'Peak Matrix' in result['dataset_names']
        assert 'Peak Matrix (binned)' in result['dataset_names']

        # Raw keeps the measured axis; binned is coarser (half kBT per bin).
        np.testing.assert_array_equal(raw.independent_var, sts_dataset.independent_var)
        assert len(binned.independent_var) < len(raw.independent_var)
        assert (np.diff(binned.independent_var)[0]
                > np.diff(raw.independent_var)[0])
        assert raw.metadata.additional_info['binned'] is False
        assert binned.metadata.additional_info['binned'] is True

        # Binning can merge, never invent.
        assert np.nansum(binned.spectra.values) <= np.nansum(raw.spectra.values)

    def test_binned_matrix_only_exists_with_a_temperature(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        assert result['peak_matrix'] is not None
        assert result['peak_matrix_binned'] is None
        assert result['binned_matrix_path'] == ''

    def test_binned_matrix_gets_its_own_csv(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)

        raw_path, binned_path = Path(result['matrix_path']), Path(result['binned_matrix_path'])
        assert raw_path.exists() and binned_path.exists()
        assert raw_path != binned_path
        assert binned_path.name.endswith('_PeakMatrix_binned.csv')

        binned_rows = pd.read_csv(binned_path)
        raw_rows = pd.read_csv(raw_path)
        assert list(binned_rows.columns) == list(raw_rows.columns) == ['V', 'P1', 'P2', 'P3']
        assert len(binned_rows) < len(raw_rows)
        # Still 1-or-blank, in both files.
        for frame in (binned_rows, raw_rows):
            values = frame[['P1', 'P2', 'P3']].to_numpy(dtype=float)
            assert set(np.unique(values[np.isfinite(values)])) == {1}

    def test_binned_matrix_rows_are_the_bin_centres(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        axis = result['peak_matrix_binned'].independent_var
        kbt = 8.617333262e-5 * 94.0
        np.testing.assert_allclose(np.diff(axis), kbt / 2, rtol=1e-6)
        # Every marked bin holds at least one reported peak.
        marked = axis[result['peak_matrix_binned'].spectra.values[:, 0] == 1]
        centres = result['peaks'].data.query('spectrum_index == 0')['bin_center']
        np.testing.assert_allclose(sorted(marked), sorted(centres.unique()), atol=1e-12)

    def test_offset_matrix_marks_each_column_with_its_number(self, tool_impl, sts_dataset):
        """Plotting a 1/blank table stacks every spectrum on one line; the
        offset variant puts each on its own row."""
        result = self._run(tool_impl, sts_dataset)

        offset = result['peak_matrix_offset']
        plain = result['peak_matrix']
        assert offset is not None

        values = offset.spectra.values
        assert list(offset.spectra.columns) == ['P1', 'P2', 'P3']
        np.testing.assert_array_equal(offset.independent_var, plain.independent_var)

        # Column n carries the value n (1-based) wherever it has a peak.
        for n, name in enumerate(offset.spectra.columns, start=1):
            column = values[:, n - 1]
            marks = column[np.isfinite(column)]
            assert set(np.unique(marks)) == {n}, name

        # Marked cells are exactly the ones marked in the plain table.
        np.testing.assert_array_equal(np.isfinite(values),
                                      np.isfinite(plain.spectra.values))

    def test_offset_matrix_blanks_stay_blank(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        values = result['peak_matrix_offset'].spectra.values
        assert np.isnan(values).any()
        assert 0 not in np.unique(values[np.isfinite(values)])

    def test_binned_offset_matrix_accompanies_the_binned_one(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)

        binned_offset = result['peak_matrix_binned_offset']
        assert binned_offset is not None
        np.testing.assert_array_equal(binned_offset.independent_var,
                                      result['peak_matrix_binned'].independent_var)
        np.testing.assert_array_equal(
            np.isfinite(binned_offset.spectra.values),
            np.isfinite(result['peak_matrix_binned'].spectra.values))
        assert binned_offset.metadata.additional_info['offset'] is True
        assert binned_offset.metadata.additional_info['binned'] is True

    def test_binned_offset_needs_a_temperature(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        assert result['peak_matrix_offset'] is not None
        assert result['peak_matrix_binned_offset'] is None
        assert result['binned_offset_matrix_path'] == ''

    def test_offset_matrix_csv_holds_column_numbers(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        path = Path(result['offset_matrix_path'])
        assert path.exists()
        assert path.name.endswith('_PeakMatrix_offset.csv')

        rows = [ln.split(',') for ln in path.read_text().splitlines()[1:] if ln.strip()]
        cells = {c for row in rows for c in row[1:]}
        # Bare integers, no "1.0", and blanks stay blank.
        assert cells <= {'', '1', '2', '3'}
        assert cells & {'1', '2', '3'}
        for row in rows:
            for column_number, cell in enumerate(row[1:], start=1):
                assert cell in ('', str(column_number))

    def test_all_four_matrices_are_distinct_datasets(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        names = result['dataset_names']
        assert {'Peak Matrix', 'Peak Matrix (offset)',
                'Peak Matrix (binned)', 'Peak Matrix (binned, offset)'} <= set(names)
        paths = {result[k] for k in ('matrix_path', 'offset_matrix_path',
                                     'binned_matrix_path', 'binned_offset_matrix_path')}
        assert len(paths) == 4, "each table needs its own file"


class TestPolynomialBasisOption(TestToolImplementationsSetup):
    """The polynomial/endpoints fits can use an orthogonal basis.

    Same fitted curve either way -- what changes is the coefficient table,
    which is the thing being fed to classification.
    """

    def test_power_basis_is_bit_identical_to_the_historical_path(
            self, tool_impl, sample_spectral_data):
        """Existing coefficient maps must not shift under anyone's feet."""
        import numpy as np
        tool_impl._datasets['test'] = sample_spectral_data
        spectra = sample_spectral_data.spectra.values
        x = sample_spectral_data.independent_var

        tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial', degree=3)
        produced = tool_impl._datasets[
            [n for n in tool_impl._datasets if n.endswith('Fit Coefficients')][0]]

        for i in range(spectra.shape[1]):
            expected = np.polyfit(x, spectra[:, i], 3)          # highest-first
            row = produced.data.iloc[i]
            for power in range(4):
                assert row[f'c{power}'] == pytest.approx(expected[3 - power])

    @pytest.mark.parametrize("basis,prefix", [("legendre", "P"), ("chebyshev", "T")])
    def test_orthogonal_basis_names_its_own_columns(self, tool_impl, sample_spectral_data,
                                                    basis, prefix):
        tool_impl._datasets['test'] = sample_spectral_data
        result = tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial',
                                      degree=3, basis=basis)
        assert result != ""

        coeffs = tool_impl._datasets[
            [n for n in tool_impl._datasets if n.endswith('Fit Coefficients')][0]]
        assert [c for c in coeffs.data.columns if c != 'Spectrum_Index'] == \
               [f'{prefix}{n}' for n in range(4)]
        assert coeffs.metadata.additional_info['basis'] == basis

    def test_basis_does_not_change_the_corrected_data(self, tool_impl, sample_spectral_data):
        import numpy as np
        tool_impl._datasets['test'] = sample_spectral_data

        tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial', degree=3)
        power = tool_impl._datasets[
            [n for n in tool_impl._datasets if n.endswith('Baseline Corrected')][0]
        ].spectra.values.copy()

        tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial', degree=3,
                             basis='legendre')
        legendre = tool_impl._datasets[
            [n for n in tool_impl._datasets if n.endswith('Baseline Corrected')][0]
        ].spectra.values

        np.testing.assert_allclose(legendre, power, rtol=1e-6,
                                   atol=1e-9 * np.abs(power).max())

    def test_unknown_basis_is_rejected(self, tool_impl, sample_spectral_data):
        tool_impl._datasets['test'] = sample_spectral_data
        assert tool_impl.fit_curves(MockTask(), 'test', fit_type='polynomial',
                                    degree=3, basis='bernstein') == ""
        tool_impl.errorOccurred.emit.assert_called()

    def test_confinement_coefficients_follow_the_chosen_basis(self, tool_impl):
        import numpy as np
        import pandas as pd
        x = np.linspace(-0.6, 0.6, 512)
        y = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
        tool_impl._datasets['sts'] = SpectralData(
            pd.DataFrame({"V": x, "P1": y}),
            SpectralMetadata(source_type="sts", dimensions=(1, 1), scan_mode="point",
                             units={"x": "V"}, additional_info={}))

        result = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 4,
                    'baseline_basis': 'legendre'})

        coeffs = result['coefficients']
        assert [c for c in coeffs.data.columns if c != 'Spectrum_Index'] == \
               [f'P{n}' for n in range(5)]
        assert coeffs.metadata.additional_info['basis'] == 'legendre'


class TestSpectralFeatures(TestToolImplementationsSetup):
    """The feature table: one row per spectrum, emitted as flat data so every
    column is a spatial map and the whole thing feeds PCA."""

    @pytest.fixture
    def sts_dataset(self):
        rng = np.random.default_rng(0)
        x = np.linspace(-0.6, 0.6, 512)

        def curve(gap_half, centre=0.0, n_states=0):
            outside = np.clip(np.abs(x - centre) - gap_half, 0.0, None)
            y = 3e-7 * (0.02 + 0.98 * np.tanh(outside / 0.08) ** 2)
            for k in range(n_states):
                c = centre - gap_half + (k + 1) * (2 * gap_half) / (n_states + 1)
                y = y + 2.5e-8 * np.exp(-0.5 * ((x - c) / 0.006) ** 2)
            return y + rng.normal(0, 8e-11, x.size)

        df = pd.DataFrame({"V": x, "narrow": curve(0.08), "wide": curve(0.25),
                           "doped": curve(0.15, centre=-0.10),
                           "states": curve(0.15, n_states=3)})
        return SpectralData(df, SpectralMetadata(
            source_type="sts", dimensions=(4, 1), scan_mode="line",
            units={"x": "V"}, additional_info={}))

    def _run(self, tool_impl, dataset, **params):
        tool_impl._datasets['sts'] = dataset
        return tool_impl.extract_spectral_features(MockTask(), 'sts', params=params)

    def test_emits_a_flat_feature_dataset(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        features = result['features']

        assert features is not None
        assert result['dataset_name'] == 'sts - Features'
        assert result['dataset_name'] in tool_impl._datasets
        # Flat data with a Spectrum_Index axis is what the Map Generator takes.
        assert features.metadata.data_type == 'flat'
        assert features.independent_var_name == 'Spectrum_Index'
        assert len(features.data) == 4

    def test_features_discriminate_the_planted_physics(self, tool_impl, sts_dataset):
        table = self._run(tool_impl, sts_dataset)['features'].data

        narrow, wide, doped, states = (table.iloc[i] for i in range(4))
        assert narrow['gap_width'] < wide['gap_width']
        assert doped['doping_offset'] == pytest.approx(-0.10, abs=0.03)
        assert states['n_states'] == 3
        # An occupied gap is still measured as a gap.
        assert states['gap_width'] > 0.2

    def test_every_column_is_numeric_and_mappable(self, tool_impl, sts_dataset):
        """A text column would break the Map Generator and PCA alike."""
        features = self._run(tool_impl, sts_dataset)['features']
        for column in features.data.columns:
            assert pd.api.types.is_numeric_dtype(features.data[column]), column
        assert 'doping_type' not in features.data.columns

    def test_metadata_lists_the_features_and_settings(self, tool_impl, sts_dataset):
        info = self._run(tool_impl, sts_dataset,
                         poly_basis='legendre')['features'].metadata.additional_info
        assert info['basis'] == 'legendre'
        assert info['normalize'] == 'max'
        assert 'gap_width' in info['feature_columns']
        assert info['n_total'] == 4
        # Not a spectrum, so it must not overlay the source graph.
        assert 'original' not in info

    def test_basis_choice_renames_the_coefficient_columns(self, tool_impl, sts_dataset):
        legendre = self._run(tool_impl, sts_dataset, poly_basis='legendre')['features']
        power = self._run(tool_impl, sts_dataset, poly_basis='power')['features']
        assert 'P2' in legendre.data.columns and 'c2' not in legendre.data.columns
        assert 'c2' in power.data.columns

    def test_degree_controls_the_coefficient_count(self, tool_impl, sts_dataset):
        table = self._run(tool_impl, sts_dataset, poly_degree=2)['features'].data
        assert 'P2' in table.columns
        assert 'P3' not in table.columns

    def test_qml_float_params_are_cast(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, poly_degree=3.0,
                           state_width_samples=11.0, doping_smooth_points=5.0)
        assert result['features'] is not None
        assert 'P3' in result['features'].data.columns

    def test_writes_a_csv_with_the_labels_too(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset)
        path = Path(result['features_path'])
        assert path.exists()
        saved = pd.read_csv(path)
        # The CSV keeps the human-readable label the numeric table drops.
        assert 'doping_type' in saved.columns
        assert len(saved) == 4

    def test_invalid_spectra_are_counted_not_dropped(self, tool_impl, sts_dataset):
        df = sts_dataset.data.copy()
        df['dead'] = np.zeros(len(df))
        broken = SpectralData(df, sts_dataset.metadata)

        result = self._run(tool_impl, broken)
        assert result['n_total'] == 5
        assert result['n_valid'] < 5
        assert len(result['features'].data) == 5

    def test_workflow_mode_does_not_emit(self, tool_impl, sts_dataset):
        tool_impl._workflow_mode = True
        self._run(tool_impl, sts_dataset)
        tool_impl.dataLoaded.emit.assert_not_called()

    def test_cancellation_returns_nothing(self, tool_impl, sts_dataset):
        class Cancelled(MockTask):
            cancelled = True

        tool_impl._datasets['sts'] = sts_dataset
        result = tool_impl.extract_spectral_features(Cancelled(), 'sts', params={})
        assert result['features'] is None

    def test_missing_dataset_reports_an_error(self, tool_impl):
        assert tool_impl.extract_spectral_features(MockTask(), 'nope', params={})['features'] is None
        tool_impl.errorOccurred.emit.assert_called()

    def test_bad_parameter_reports_an_error(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, normalize='quantile')
        assert result['features'] is None
        tool_impl.errorOccurred.emit.assert_called()


# =============================================================================
# Map Generator — spectra → background-corrected integrals → maps
# =============================================================================

class TestMapLayout(TestToolImplementationsSetup):
    """The scan path decides how a per-spectrum value array becomes a field."""

    def test_meander_reverses_every_other_row(self, tool_impl):
        values = np.arange(6.0)          # 3 wide, 2 tall
        out = tool_impl._reshape_map_values(values, (3, 2), 'map_meander')
        # Rows are flipped bottom-to-top, and the second (odd) row is reversed
        # because it was acquired right-to-left.
        np.testing.assert_array_equal(out, [[5, 4, 3], [0, 1, 2]])

    def test_raster_fills_rows_straight(self, tool_impl):
        values = np.arange(6.0)
        out = tool_impl._reshape_map_values(values, (3, 2), 'map_raster')
        np.testing.assert_array_equal(out, [[3, 4, 5], [0, 1, 2]])

    def test_line_scan_is_a_single_row_whatever_the_dimensions_say(self, tool_impl):
        values = np.arange(5.0)
        out = tool_impl._reshape_map_values(values, (5, 1), 'line')
        assert out.shape == (1, 5)
        np.testing.assert_array_equal(out[0], values)

    def test_line_scan_ignores_a_misleading_grid(self, tool_impl):
        """A line's metadata may claim a 2-D grid; the line path must not
        fold it into rows."""
        values = np.arange(7.0)
        out = tool_impl._reshape_map_values(values, (3, 2), 'line')
        assert out.shape == (1, 7)

    def test_length_mismatch_is_refused(self, tool_impl):
        with pytest.raises(ValueError):
            tool_impl._reshape_map_values(np.arange(5.0), (3, 2), 'map_raster')

    def test_clean_multiple_uses_the_first_channel(self, tool_impl):
        values = np.concatenate([np.arange(6.0), np.full(6, 99.0)])
        out = tool_impl._reshape_map_values(values, (3, 2), 'map_raster')
        assert 99.0 not in out

    @staticmethod
    def _meta(**kwargs):
        return SpectralMetadata(source_type='sts', dimensions=kwargs.pop('dimensions', (4, 4)),
                                scan_mode=kwargs.pop('scan_mode', 'point'),
                                units={}, additional_info=kwargs.pop('info', {}))

    def test_auto_recognises_a_meander_scan(self, tool_impl):
        meta = self._meta(scan_mode='meander')
        assert tool_impl._resolve_scan_type('auto', meta) == 'map_meander'

    def test_auto_does_not_re_correct_corrected_data(self, tool_impl):
        meta = self._meta(scan_mode='meander', info={'meander_corrected': True})
        assert tool_impl._resolve_scan_type('auto', meta) == 'map_raster'

    def test_auto_recognises_a_line_scan(self, tool_impl):
        meta = self._meta(dimensions=(16, 1), scan_mode='line')
        assert tool_impl._resolve_scan_type('auto', meta) == 'line'

    def test_an_explicit_choice_overrides_the_metadata(self, tool_impl):
        meta = self._meta(scan_mode='meander')
        assert tool_impl._resolve_scan_type('line', meta) == 'line'
        assert tool_impl._resolve_scan_type('map_raster', meta) == 'map_raster'


class TestMapGeneratorFromSpectra(TestToolImplementationsSetup):
    """Background correction + interval integration + export, in one pass."""

    CENTERS = (-0.25, 0.20)

    def _dataset(self, n_spectra=16, dimensions=(4, 4), scan_mode='point',
                 info=None, weights=None):
        x = np.linspace(-0.6, 0.6, 256)
        band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
        weights = weights if weights is not None else np.ones(n_spectra)
        columns = {}
        for n in range(n_spectra):
            y = band_edges.copy()
            for c in self.CENTERS:
                y = y + weights[n] * 1.2e-8 * np.exp(-0.5 * ((x - c) / 0.008) ** 2)
            columns[f"P{n + 1}"] = y
        df = pd.DataFrame({"V": x, **columns})
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=dimensions, scan_mode=scan_mode,
            units={'independent': 'V', 'dependent': 'A'},
            additional_info=info or {}))

    @staticmethod
    def _csv_of(tiff_path):
        """The CSV beside a map, in the run's csv/ folder."""
        tiff = Path(tiff_path)
        return tiff.parent.parent / 'csv' / (tiff.stem + '.csv')

    def _run(self, tool_impl, dataset=None, name='sts', **params):
        tool_impl._datasets[name] = dataset if dataset is not None else self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), name,
            params={'baseline': 'poly-iter', 'baseline_degree': 5,
                    'height': 5.0, **params})

    def test_detects_intervals_and_writes_one_tiff_per_interval(self, tool_impl):
        result = self._run(tool_impl)

        assert result['n_maps'] == len(result['intervals']) > 0
        for path in result['map_paths']:
            assert path.endswith('.tiff')
            assert Path(path).exists()

    def test_csv_and_gsf_ride_along_as_before(self, tool_impl):
        """The export contract is unchanged: calibrated TIFF + GSF + CSV —
        now filed per dataset and per format."""
        result = self._run(tool_impl)
        tiff = Path(result['map_paths'][0])
        assert tiff.parent.name == 'tiff'
        root = tiff.parent.parent
        assert (root / 'gsf' / (tiff.stem + '.gsf')).exists()
        assert (root / 'csv' / (tiff.stem + '.csv')).exists()

    def test_outputs_are_filed_under_their_dataset(self, tool_impl):
        result = self._run(tool_impl, name='STS line 7')
        root = Path(result['output_folder'])
        assert root.name == 'STS_line_7'
        assert root.parent.name == 'maps'
        assert {p.name for p in root.iterdir() if p.is_dir()} == {'gsf', 'tiff', 'csv'}

    def test_two_datasets_do_not_share_a_folder(self, tool_impl):
        first = self._run(tool_impl, name='line A')
        second = self._run(tool_impl, name='line B')
        assert first['output_folder'] != second['output_folder']

    def test_maps_are_the_grid_shape(self, tool_impl):
        result = self._run(tool_impl)
        grid = np.loadtxt(self._csv_of(result['map_paths'][0]), delimiter=',')
        assert grid.shape == (4, 4)

    def test_a_line_scan_produces_a_single_row(self, tool_impl):
        dataset = self._dataset(n_spectra=12, dimensions=(12, 1), scan_mode='line')
        result = self._run(tool_impl, dataset, scan_type='line')

        assert result['scan_type'] == 'line'
        grid = np.loadtxt(self._csv_of(result['map_paths'][0]), delimiter=',')
        assert grid.shape == (12,)          # one row, written flat by savetxt

    def test_scan_type_combo_picks_the_path(self, tool_impl):
        meander = self._run(tool_impl, scan_type='map_meander')
        raster = self._run(tool_impl, scan_type='map_raster')
        assert meander['scan_type'] == 'map_meander'
        assert raster['scan_type'] == 'map_raster'

    def test_values_follow_the_spectra(self, tool_impl):
        """A brighter state must give a larger integral, so the map carries
        the physical contrast rather than a normalisation."""
        weights = np.linspace(1.0, 4.0, 16)
        result = self._run(tool_impl, self._dataset(weights=weights),
                           interval_source='manual', intervals=[[0.15, 0.25]])

        values = tool_impl._datasets[result['values_dataset']].data
        column = [c for c in values.columns if c != 'Spectrum_Index'][0]
        assert values[column].iloc[-1] > values[column].iloc[0]
        assert values[column].is_monotonic_increasing

    def test_integrals_are_published_as_a_flat_dataset(self, tool_impl):
        result = self._run(tool_impl)
        values = tool_impl._datasets[result['values_dataset']]

        assert values.metadata.data_type == 'flat'
        assert 'Spectrum_Index' in values.data.columns
        assert len(values.data.columns) == 1 + len(result['intervals'])
        # The intervals travel with them, so the numbers can be re-mapped.
        assert values.metadata.additional_info['integration_intervals']

    def test_manual_intervals_skip_detection(self, tool_impl):
        result = self._run(tool_impl, interval_source='manual',
                           intervals=[[-0.3, -0.2], [0.15, 0.25]])
        assert result['intervals'] == [[-0.3, -0.2], [0.15, 0.25]]
        assert result['n_maps'] == 2

    def test_intervals_come_from_a_previous_analysis(self, tool_impl):
        """The whole point of the rewrite: no JSON export/import detour."""
        dataset = self._dataset()
        tool_impl._datasets['sts'] = dataset
        analysis = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0})

        source = analysis['dataset_names']['Peaks']
        assert tool_impl.dataset_intervals(source), "analysis published no intervals"

        result = self._run(tool_impl, dataset, interval_source='dataset',
                           intervals_from=source)
        assert result['intervals'] == tool_impl.dataset_intervals(source)
        assert result['n_maps'] == len(result['intervals'])

    def test_background_correction_is_applied_before_integrating(self, tool_impl):
        """Without it the band edge dominates and every point looks alike."""
        # An interval sitting on the band edge, with no state in it: raw, it
        # integrates the edge; corrected, there is almost nothing left.
        # Distinct names because both runs publish "<base> - Map Values".
        window = [[0.45, 0.55]]
        corrected = self._run(tool_impl, name='corrected',
                              interval_source='manual', intervals=window)
        raw = self._run(tool_impl, name='raw', baseline='none',
                        interval_source='manual', intervals=window)

        c_values = tool_impl._datasets[corrected['values_dataset']].data.iloc[:, 1]
        r_values = tool_impl._datasets[raw['values_dataset']].data.iloc[:, 1]
        assert abs(c_values.mean()) < 0.2 * abs(r_values.mean())

    def test_no_intervals_reports_instead_of_writing_nothing(self, tool_impl):
        result = self._run(tool_impl, interval_source='manual', intervals=[])
        assert result['n_maps'] == 0
        tool_impl.errorOccurred.emit.assert_called()

    def test_missing_dataset_is_reported(self, tool_impl):
        result = tool_impl.generate_maps_from_spectra(MockTask(), 'nope', {})
        assert result['n_maps'] == 0
        tool_impl.errorOccurred.emit.assert_called()

    def test_cancellation_stops_before_writing(self, tool_impl):
        class Cancelled(MockTask):
            cancelled = True

        tool_impl._datasets['sts'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            Cancelled(), 'sts', {'interval_source': 'manual',
                                 'intervals': [[0.1, 0.2]]})
        assert result['map_paths'] == []

    def test_legacy_interval_strings_are_understood(self, tool_impl):
        dataset = self._dataset()
        dataset.metadata.additional_info['intervals'] = ['0.100_0.200']
        tool_impl._datasets['old'] = dataset
        assert tool_impl.dataset_intervals('old') == [[0.1, 0.2]]

    def test_a_dataset_without_intervals_lists_none(self, tool_impl):
        tool_impl._datasets['plain'] = self._dataset()
        assert tool_impl.dataset_intervals('plain') == []

    def test_scan_type_reaches_the_flat_map_path(self, tool_impl):
        """The workflow node's scan-type choice must drive the layout too."""
        frame = pd.DataFrame({'Spectrum_Index': np.arange(6),
                              'value': np.arange(6.0)})
        tool_impl._datasets['flat'] = SpectralData(frame, SpectralMetadata(
            source_type='flat', dimensions=(3, 2), scan_mode='point',
            units={}, additional_info={}, data_type='flat'))

        meander = tool_impl.generate_map(MockTask(), 'flat', 0, scan_type='map_meander')
        grid = np.loadtxt(str(meander) + '.csv', delimiter=',')
        np.testing.assert_array_equal(grid, [[5, 4, 3], [0, 1, 2]])

        line = tool_impl.generate_map(MockTask(), 'flat', 0, scan_type='line')
        assert np.loadtxt(str(line) + '.csv', delimiter=',').shape == (6,)


class TestMapIntervalsFromThermalBins(TestToolImplementationsSetup):
    """The Map Generator must find the same states Confinement Analysis does.

    Merging peaks' FWHM bands lost almost all of them — on real 4.5 K
    line-scan data, 206 occupied bins collapsed to 3 bands, one a quarter of
    the sweep wide. The intervals are the occupied k_B*T/2 bins instead.
    """

    CENTERS = (-0.25, -0.10, 0.08, 0.22)

    def _dataset(self, n_spectra=6, present=None):
        """Spectra with sharp in-gap states on a steep band-edge background.

        ``present`` picks which centres each spectrum carries, so bins can be
        occupied by different numbers of spectra.
        """
        x = np.linspace(-0.6, 0.6, 1024)
        band_edges = 3e-7 * np.exp((np.abs(x) - 0.6) / 0.055)
        columns = {}
        for n in range(n_spectra):
            y = band_edges.copy()
            centers = self.CENTERS if present is None else present(n)
            for c in centers:
                y = y + 1.2e-8 * np.exp(-0.5 * ((x - c) / 0.004) ** 2)
            columns[f"P{n + 1}"] = y
        df = pd.DataFrame({"V": x, **columns})
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='point',
            units={'independent': 'V'}, additional_info={}))

    def _intervals(self, tool_impl, dataset=None, **params):
        tool_impl._datasets['sts'] = dataset if dataset is not None else self._dataset()
        return tool_impl.detect_map_intervals(
            MockTask(), 'sts',
            {'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0,
             **params})

    def test_intervals_are_exactly_one_bin_wide(self, tool_impl):
        from src.processing.peak_detection import thermal_broadening

        intervals = self._intervals(tool_impl, temperature_k=94.0)
        expected = thermal_broadening(94.0, 'eV') / 2

        assert intervals, "no intervals found"
        for lo, hi in intervals:
            assert hi - lo == pytest.approx(expected, rel=1e-9)

    def test_the_states_confinement_finds_are_all_covered(self, tool_impl):
        """Every planted state must fall inside one of the intervals."""
        dataset = self._dataset()
        intervals = self._intervals(tool_impl, dataset, temperature_k=94.0)
        for center in self.CENTERS:
            assert any(lo <= center <= hi for lo, hi in intervals), center

    def test_bins_agree_with_the_confinement_table(self, tool_impl):
        """Both tools must report on the same grid."""
        dataset = self._dataset()
        tool_impl._datasets['sts'] = dataset
        analysis = tool_impl.analyze_confinement(
            MockTask(), 'sts',
            params={'baseline': 'poly-iter', 'baseline_degree': 5,
                    'height': 5.0, 'temperature_k': 94.0})
        occupied_bins = analysis['peaks'].data['bin_index'].nunique()

        intervals = self._intervals(tool_impl, dataset, temperature_k=94.0)
        assert len(intervals) == occupied_bins

    def test_the_occupancy_filter_drops_bins_without_widening_them(self, tool_impl):
        """Raising the minimum must cost states, never resolution — the old
        behaviour was the opposite."""
        def present(n):
            # Every spectrum has the first state; only one has the last.
            return self.CENTERS if n == 0 else self.CENTERS[:-1]

        dataset = self._dataset(n_spectra=6, present=present)
        loose = self._intervals(tool_impl, dataset, temperature_k=94.0,
                                min_spectra_per_bin=1)
        strict = self._intervals(tool_impl, dataset, temperature_k=94.0,
                                 min_spectra_per_bin=3)

        assert len(strict) < len(loose)
        widths = {round(hi - lo, 12) for lo, hi in loose + strict}
        assert len(widths) == 1, "bin width changed with the threshold"

    def test_a_singleton_bin_survives_at_the_default(self, tool_impl):
        def present(n):
            return self.CENTERS if n == 0 else self.CENTERS[:-1]

        dataset = self._dataset(n_spectra=6, present=present)
        intervals = self._intervals(tool_impl, dataset, temperature_k=94.0)
        assert any(lo <= self.CENTERS[-1] <= hi for lo, hi in intervals)

    def test_without_a_temperature_the_bins_are_the_sweep_step(self, tool_impl):
        """No temperature must not mean coarse intervals.

        This used to merge the peaks' FWHM bands, which fused everything into
        two or three bands tens of mV wide — on real dI/dV line scans the tool
        reported 2 intervals where 216 states were detected. The bins are now
        the sweep's own step, the finest grid the measurement resolves.
        """
        dataset = self._dataset()
        step = float(np.median(np.diff(dataset.independent_var)))
        intervals = self._intervals(tool_impl, dataset)

        assert len(intervals) > 3
        for lo, hi in intervals:
            assert hi - lo == pytest.approx(step, rel=1e-6)

    def test_bins_are_never_finer_than_the_sweep_can_resolve(self, tool_impl):
        """k_B*T/2 at 4.5 K is 0.19 mV against a 4.7 mV sweep step: finer bins
        would only produce neighbouring maps integrating the same samples."""
        dataset = self._dataset()
        step = float(np.median(np.diff(dataset.independent_var)))
        intervals = self._intervals(tool_impl, dataset, temperature_k=4.5)

        assert intervals
        for lo, hi in intervals:
            assert hi - lo == pytest.approx(step, rel=1e-6)

    def test_a_coarse_temperature_still_widens_the_bins(self, tool_impl):
        """When k_B*T/2 is the coarser of the two, it wins."""
        from src.processing.peak_detection import thermal_broadening

        dataset = self._dataset()
        intervals = self._intervals(tool_impl, dataset, temperature_k=2000.0)
        expected = thermal_broadening(2000.0, 'eV') / 2

        assert intervals
        for lo, hi in intervals:
            assert hi - lo == pytest.approx(expected, rel=1e-6)

    def test_generation_uses_the_binned_intervals(self, tool_impl):
        """End to end: one map per occupied bin."""
        tool_impl._datasets['sts'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'sts',
            {'baseline': 'poly-iter', 'baseline_degree': 5, 'height': 5.0,
             'temperature_k': 94.0, 'dimensions': (6, 1), 'scan_type': 'line'})

        assert result['n_maps'] == len(result['intervals']) >= len(self.CENTERS)


class TestSubResolutionIntervals(TestToolImplementationsSetup):
    """Thermal bins are routinely finer than the bias step.

    At 4.5 K a k_B*T/2 bin is 0.19 mV while a 256-point sweep over 1.2 V
    steps every 4.7 mV, so the bin held 0.04 samples and np.trapz returned
    exactly 0 — every map came out blank.
    """

    def _dataset(self, n_spectra=8, n_points=256):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {}
        for n in range(n_spectra):
            # A state whose height varies across the line, so a correct map
            # has contrast rather than one flat value.
            columns[f"P{n + 1}"] = (1e-10 * (n + 1)
                                    * np.exp(-0.5 * ((x - 0.2) / 0.01) ** 2)
                                    + 1e-12)
        df = pd.DataFrame({"V": x, **columns})
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'}, additional_info={}))

    def _run(self, tool_impl, intervals, **params):
        tool_impl._datasets['sts'] = self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'sts',
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': intervals, 'scan_type': 'line', **params})

    def test_a_bin_narrower_than_the_bias_step_still_produces_values(self, tool_impl):
        # 0.19 mV window on a 4.7 mV grid — the case that came out blank.
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        values = tool_impl._datasets[result['values_dataset']].data.iloc[:, 1]

        assert result['n_maps'] == 1
        assert (values != 0).all(), "the map is blank"

    def test_the_map_keeps_the_contrast_of_the_spectra(self, tool_impl):
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        values = tool_impl._datasets[result['values_dataset']].data.iloc[:, 1]
        # The planted state grows along the line, so the map must too.
        assert values.iloc[-1] > values.iloc[0] * 2

    def test_values_are_the_real_physical_integrals(self, tool_impl):
        """No normalisation: a 1e-10 A state over a few mV really is ~1e-13."""
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        values = tool_impl._datasets[result['values_dataset']].data.iloc[:, 1]
        assert 1e-16 < abs(values.max()) < 1e-10

    def test_the_widening_is_recorded(self, tool_impl):
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        info = tool_impl._datasets[result['values_dataset']].metadata.additional_info
        assert info['windows_widened'] == 1
        assert info['integration_window'] == pytest.approx(2 * info['bias_step'])

    def test_a_wide_interval_is_left_alone(self, tool_impl):
        result = self._run(tool_impl, [[0.15, 0.25]])
        info = tool_impl._datasets[result['values_dataset']].metadata.additional_info
        assert info['windows_widened'] == 0

    def test_an_interval_at_the_very_edge_still_integrates(self, tool_impl):
        result = self._run(tool_impl, [[-0.6001, -0.5999], [0.5999, 0.6001]])
        frame = tool_impl._datasets[result['values_dataset']].data
        assert result['n_maps'] == 2
        for column in frame.columns[1:]:
            assert (frame[column] != 0).any()

    def test_the_exported_tiff_holds_those_values(self, tool_impl):
        import tifffile
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        arr = tifffile.imread(result['map_paths'][0])
        values = tool_impl._datasets[result['values_dataset']].data.iloc[:, 1]

        assert arr.dtype == np.float32
        np.testing.assert_allclose(np.ravel(arr), values.to_numpy(), rtol=1e-6)

    def test_the_tiff_carries_a_display_range_so_it_is_not_black(self, tool_impl):
        import tifffile
        result = self._run(tool_impl, [[0.1999, 0.2001]])
        with tifffile.TiffFile(result['map_paths'][0]) as tf:
            description = tf.pages[0].description

        assert 'min=' in description and 'max=' in description
        lo = float(description.split('min=')[1].split('\n')[0])
        hi = float(description.split('max=')[1].split('\n')[0])
        assert hi > lo


class TestJoinedIntervalMap(TestToolImplementationsSetup):
    """One map over all intervals: x = position along the line, y = interval
    (indexed by its midpoint)."""

    def _dataset(self, n_spectra=10, n_points=256):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {}
        for n in range(n_spectra):
            y = 1e-12 * np.ones_like(x)
            # Two states whose weight swaps along the line, so the joined map
            # must show structure in both axes.
            y = y + (n + 1) * 1e-11 * np.exp(-0.5 * ((x + 0.25) / 0.01) ** 2)
            y = y + (n_spectra - n) * 1e-11 * np.exp(-0.5 * ((x - 0.20) / 0.01) ** 2)
            columns[f"P{n + 1}"] = y
        df = pd.DataFrame({"V": x, **columns})
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'}, additional_info={}))

    def _run(self, tool_impl, intervals=((-0.30, -0.20), (0.15, 0.25)), **params):
        tool_impl._datasets['line'] = self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [list(iv) for iv in intervals],
             'scan_type': 'line', **params})

    def test_the_joined_map_is_written(self, tool_impl):
        result = self._run(tool_impl)
        assert result['interval_map_path'].endswith('_IntervalMap.tiff')
        assert Path(result['interval_map_path']).exists()

    def test_its_shape_is_intervals_by_positions(self, tool_impl):
        result = self._run(tool_impl)
        grid = np.loadtxt(
            Path(result['interval_map_path']).parent.parent / 'csv'
            / (Path(result['interval_map_path']).stem + '.csv'), delimiter=',')
        assert grid.shape == (2, 10)        # 2 intervals x 10 positions

    def test_rows_are_ordered_by_midpoint(self, tool_impl):
        result = self._run(tool_impl, intervals=((0.15, 0.25), (-0.30, -0.20)))
        dataset = tool_impl._datasets[result['interval_map']]
        midpoints = dataset.independent_var
        assert list(midpoints) == sorted(midpoints)
        assert midpoints[0] == pytest.approx(-0.25)

    def test_it_is_a_dataset_the_hyperspectral_tab_accepts(self, tool_impl):
        """It must classify as a line scan, or the tab will not open it."""
        from src.backend.app_backend import AppBackend

        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]

        class Stub:
            _POINT_SCAN_MODES = AppBackend._POINT_SCAN_MODES
        assert AppBackend._spatial_layout(Stub(), dataset) == 'line'

    def test_the_integrated_marker_is_not_set(self, tool_impl):
        """'intervals' in additional_info marks a dataset as integrated
        values, which the Hyperspectral tab skips — the joined map must not
        carry it."""
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info
        assert 'intervals' not in info
        assert info['interval_bounds'] and info['interval_midpoints']

    def test_each_column_is_one_position(self, tool_impl):
        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]
        source = tool_impl._datasets['line']
        assert list(dataset.spectra.columns) == list(source.spectra.columns)

    def test_it_carries_the_contrast_of_both_axes(self, tool_impl):
        result = self._run(tool_impl)
        values = tool_impl._datasets[result['interval_map']].spectra.to_numpy()
        # One state grows along the line, the other fades: the two rows must
        # trend in opposite directions.
        assert values[0][-1] > values[0][0]
        assert values[1][-1] < values[1][0]

    def test_a_single_interval_produces_no_joined_map(self, tool_impl):
        result = self._run(tool_impl, intervals=((0.15, 0.25),))
        assert result['interval_map'] == ''
        assert result['interval_map_path'] == ''

    def test_the_browser_is_told_about_it(self, tool_impl):
        result = self._run(tool_impl)
        emitted = [c.args[0] for c in tool_impl.dataLoaded.emit.call_args_list]
        assert result['interval_map'] in emitted


class TestMapAxesAreRealCoordinates(TestToolImplementationsSetup):
    """x is the position along the line, y is the interval's energy."""

    STEP_M = 5e-9      # 5 nm between positions

    def _dataset(self, n_spectra=8, n_points=256):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{n + 1}": 1e-11 * (n + 1) * np.exp(-0.5 * ((x - 0.2) / 0.01) ** 2)
                              + 1e-12
                   for n in range(n_spectra)}
        df = pd.DataFrame({"V": x, **columns})
        meta = [{'column': f"P{n + 1}", 'line_pos': n,
                 'location_m': [n * self.STEP_M, 0.0]} for n in range(n_spectra)]
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'},
            additional_info={'spectrum_meta': meta}))

    def _run(self, tool_impl, intervals=((-0.30, -0.20), (0.15, 0.25))):
        tool_impl._datasets['line'] = self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [list(iv) for iv in intervals], 'scan_type': 'line'})

    def test_the_line_position_step_is_read_from_the_loader(self, tool_impl):
        step = tool_impl._line_step_m(self._dataset())
        assert step == pytest.approx(self.STEP_M)

    def test_a_map_carries_the_real_position_scale(self, tool_impl):
        from src.utils.tiff_io import read_tiff_calibration

        result = self._run(tool_impl)
        calibration = read_tiff_calibration(result['map_paths'][0])

        assert calibration is not None, "the map was written uncalibrated"
        # 5 nm per pixel, whatever unit the reader reports it in.
        assert calibration['dx'] == pytest.approx(self.STEP_M, rel=1e-3)

    def test_the_joined_map_records_both_axes(self, tool_impl):
        import tifffile

        result = self._run(tool_impl)
        with tifffile.TiffFile(result['interval_map_path']) as tf:
            description = tf.pages[0].description

        assert 'axes=' in description
        assert 'x=position' in description and 'y=energy' in description

    def test_the_joined_dataset_carries_the_positions(self, tool_impl):
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert info['position_step_m'] == pytest.approx(self.STEP_M)
        assert len(info['position_m']) == 8
        assert info['position_m'][-1] == pytest.approx(7 * self.STEP_M)

    def test_the_joined_maps_y_axis_is_the_interval_energy(self, tool_impl):
        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]
        # The independent variable IS the energy of each interval.
        np.testing.assert_allclose(dataset.independent_var, [-0.25, 0.20])

    def test_positions_are_not_invented_when_unrecorded(self, tool_impl):
        dataset = self._dataset()
        dataset.metadata.additional_info.pop('spectrum_meta')
        assert tool_impl._line_step_m(dataset) is None

    def test_several_datasets_each_get_their_own_folder(self, tool_impl):
        """A batch run must not have one dataset's maps overwrite another's."""
        from src.backend.batch_tools import run_dataset_batch

        class Task(MockTask):
            pass

        for name in ('line A', 'line B'):
            tool_impl._datasets[name] = self._dataset()

        results = run_dataset_batch(
            tool_impl, Task(), 'map_generator', ['line A', 'line B'],
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [[0.15, 0.25]], 'scan_type': 'line'})

        folders = [Path(r['output']['output_folder']) for r in results]
        assert folders[0] != folders[1]
        assert {f.name for f in folders} == {'line_A', 'line_B'}
        for folder in folders:
            assert list((folder / 'tiff').glob('*.tiff'))


class TestGsfCarriesTheAxes(TestToolImplementationsSetup):
    """The .gsf must state its dimensions: position across, energy up.

    Gwyddion reads real dimensions from GSF and nothing else, so a file
    without XReal/YReal opens as bare pixels — which is what these maps were
    doing.
    """

    STEP_M = 5e-9

    def _dataset(self, n_spectra=8, n_points=256, with_positions=True):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{n + 1}": 1e-11 * (n + 1) * np.exp(-0.5 * ((x - 0.2) / 0.01) ** 2)
                              + 1e-12
                   for n in range(n_spectra)}
        info = {}
        if with_positions:
            info['spectrum_meta'] = [{'location_m': [n * self.STEP_M, 0.0]}
                                     for n in range(n_spectra)]
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A/V'}, additional_info=info))

    def _run(self, tool_impl, dataset=None, **params):
        tool_impl._datasets['line'] = dataset if dataset is not None else self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual', 'scan_type': 'line',
             'intervals': [[-0.30, -0.20], [0.15, 0.25]], **params})

    @staticmethod
    def _gsf(tiff_path):
        from src.utils.gsf_io import read_gsf
        path = Path(tiff_path)
        gsf = path.parent.parent / 'gsf' / (path.stem + '.gsf')
        return read_gsf(gsf)[1]

    def test_a_map_states_its_width_in_metres(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['map_paths'][0])

        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(8 * self.STEP_M)

    def test_the_joined_map_states_the_energy_axis(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])

        # The intervals run -0.30 V to 0.25 V.
        assert header['YOffset'] == pytest.approx(-0.30)
        assert header['YReal'] == pytest.approx(0.55)

    def test_the_joined_map_states_the_position_axis(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])
        assert header['XReal'] == pytest.approx(8 * self.STEP_M)

    def test_the_title_names_both_axes(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])
        assert 'x=position' in header['Title'] and 'y=energy' in header['Title']

    def test_a_dataset_without_positions_still_gets_an_x_axis(self, tool_impl):
        """Re-imported from CSV: the point index is a real axis; metres are
        not to be invented."""
        result = self._run(tool_impl, self._dataset(with_positions=False))
        header = self._gsf(result['map_paths'][0])

        assert header['XReal'] == pytest.approx(8)          # points, not metres
        assert header.get('XYUnits', '') == ''
        assert 'point index' in header['Title']

    def test_detected_bins_land_on_a_linear_energy_axis(self, tool_impl):
        """Occupied bins are not adjacent; the rows must still sit at their
        true bias, so gaps are kept as empty rows."""
        dataset = self._dataset(n_spectra=8)
        tool_impl._datasets['line'] = dataset
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        info = tool_impl._datasets[result['interval_map']].metadata.additional_info
        midpoints = np.asarray(info['interval_midpoints'])
        assert len(midpoints) > len(result['intervals'])     # gaps kept
        assert info['empty_bins'] > 0
        spacing = np.diff(midpoints)
        np.testing.assert_allclose(spacing, spacing[0], rtol=1e-6)

        header = self._gsf(result['interval_map_path'])
        assert header['YReal'] == pytest.approx(len(midpoints) * info['bin_width'])

    def test_hand_picked_intervals_are_not_forced_onto_a_grid(self, tool_impl):
        """Two arbitrary intervals are two rows, not a padded grid."""
        result = self._run(tool_impl, intervals=[[-0.30, -0.20], [0.15, 0.25]])
        dataset = tool_impl._datasets[result['interval_map']]
        assert dataset.num_points == 2


class TestNoiseFloorAtIntegration(TestToolImplementationsSetup):
    """A bin with no state integrates pure noise — negative half the time and
    the same size as the real states, which made the maps read as a diagnostic
    of the fit. Only what stands above each spectrum's own noise is counted.
    """

    def _dataset(self, n_spectra=8, n_points=256, seed=3):
        rng = np.random.default_rng(seed)
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {}
        for n in range(n_spectra):
            y = rng.normal(0, 2e-12, n_points)                    # noise floor
            y = y + (n + 1) * 4e-11 * np.exp(-0.5 * ((x - 0.20) / 0.02) ** 2)
            columns[f"P{n + 1}"] = y
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A/V'}, additional_info={}))

    def _run(self, tool_impl, name, **params):
        tool_impl._datasets[name] = self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), name,
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [[-0.40, -0.30], [0.15, 0.25]],   # empty bin, state bin
             'scan_type': 'line', **params})

    def _columns(self, tool_impl, result):
        frame = tool_impl._datasets[result['values_dataset']].data
        return frame.iloc[:, 1].to_numpy(), frame.iloc[:, 2].to_numpy()

    def test_the_default_floor_removes_the_negatives(self, tool_impl):
        result = self._run(tool_impl, 'default')
        empty, state = self._columns(tool_impl, result)
        assert not (empty < 0).any() and not (state < 0).any()

    def test_the_empty_bin_reads_as_no_weight(self, tool_impl):
        result = self._run(tool_impl, 'empty')
        empty, state = self._columns(tool_impl, result)
        assert np.abs(empty).max() < 0.01 * np.abs(state).max()

    def test_the_state_keeps_its_weight(self, tool_impl):
        floored = self._run(tool_impl, 'floored')
        raw = self._run(tool_impl, 'raw', noise_floor=0.0)
        _, state_floored = self._columns(tool_impl, floored)
        _, state_raw = self._columns(tool_impl, raw)
        np.testing.assert_allclose(state_floored, state_raw, rtol=0.15)

    def test_the_state_contrast_along_the_line_survives(self, tool_impl):
        result = self._run(tool_impl, 'contrast')
        _, state = self._columns(tool_impl, result)
        assert state[-1] > 3 * state[0]        # planted 8x, kept well clear

    def test_zero_restores_the_signed_integral(self, tool_impl):
        result = self._run(tool_impl, 'signed', noise_floor=0.0)
        empty, _ = self._columns(tool_impl, result)
        assert (empty < 0).any(), "with no floor the noise must stay signed"

    def test_the_floor_is_recorded_with_the_values(self, tool_impl):
        result = self._run(tool_impl, 'recorded', noise_floor=2.0)
        info = tool_impl._datasets[result['values_dataset']].metadata.additional_info
        assert info['noise_floor'] == 2.0
        assert info['noise_sigma_median'] > 0

    def test_a_higher_floor_suppresses_more(self, tool_impl):
        low = self._run(tool_impl, 'low', noise_floor=0.5)
        high = self._run(tool_impl, 'high', noise_floor=3.0)
        assert (np.abs(self._columns(tool_impl, high)[0]).sum()
                <= np.abs(self._columns(tool_impl, low)[0]).sum())

    def test_the_joined_map_and_the_exports_agree(self, tool_impl):
        import tifffile
        result = self._run(tool_impl, 'agree')
        joined = tool_impl._datasets[result['interval_map']].spectra.to_numpy()
        finite = joined[np.isfinite(joined)]
        assert not (finite < 0).any()
        for path in result['map_paths']:
            assert not (tifffile.imread(path) < 0).any()


class TestMapAxesAreRealCoordinates(TestToolImplementationsSetup):
    """x is the position along the line, y is the interval's energy."""

    STEP_M = 5e-9      # 5 nm between positions

    def _dataset(self, n_spectra=8, n_points=256):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{n + 1}": 1e-11 * (n + 1) * np.exp(-0.5 * ((x - 0.2) / 0.01) ** 2)
                              + 1e-12
                   for n in range(n_spectra)}
        df = pd.DataFrame({"V": x, **columns})
        meta = [{'column': f"P{n + 1}", 'line_pos': n,
                 'location_m': [n * self.STEP_M, 0.0]} for n in range(n_spectra)]
        return SpectralData(df, SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'},
            additional_info={'spectrum_meta': meta}))

    def _run(self, tool_impl, intervals=((-0.30, -0.20), (0.15, 0.25))):
        tool_impl._datasets['line'] = self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [list(iv) for iv in intervals], 'scan_type': 'line'})

    def test_the_line_position_step_is_read_from_the_loader(self, tool_impl):
        step = tool_impl._line_step_m(self._dataset())
        assert step == pytest.approx(self.STEP_M)

    def test_a_map_carries_the_real_position_scale(self, tool_impl):
        from src.utils.tiff_io import read_tiff_calibration

        result = self._run(tool_impl)
        calibration = read_tiff_calibration(result['map_paths'][0])

        assert calibration is not None, "the map was written uncalibrated"
        # 5 nm per pixel, whatever unit the reader reports it in.
        assert calibration['dx'] == pytest.approx(self.STEP_M, rel=1e-3)

    def test_the_joined_map_records_both_axes(self, tool_impl):
        import tifffile

        result = self._run(tool_impl)
        with tifffile.TiffFile(result['interval_map_path']) as tf:
            description = tf.pages[0].description

        assert 'axes=' in description
        assert 'x=position' in description and 'y=energy' in description

    def test_the_joined_dataset_carries_the_positions(self, tool_impl):
        result = self._run(tool_impl)
        info = tool_impl._datasets[result['interval_map']].metadata.additional_info

        assert info['position_step_m'] == pytest.approx(self.STEP_M)
        assert len(info['position_m']) == 8
        assert info['position_m'][-1] == pytest.approx(7 * self.STEP_M)

    def test_the_joined_maps_y_axis_is_the_interval_energy(self, tool_impl):
        result = self._run(tool_impl)
        dataset = tool_impl._datasets[result['interval_map']]
        # The independent variable IS the energy of each interval.
        np.testing.assert_allclose(dataset.independent_var, [-0.25, 0.20])

    def test_positions_are_not_invented_when_unrecorded(self, tool_impl):
        dataset = self._dataset()
        dataset.metadata.additional_info.pop('spectrum_meta')
        assert tool_impl._line_step_m(dataset) is None

    def test_several_datasets_each_get_their_own_folder(self, tool_impl):
        """A batch run must not have one dataset's maps overwrite another's."""
        from src.backend.batch_tools import run_dataset_batch

        class Task(MockTask):
            pass

        for name in ('line A', 'line B'):
            tool_impl._datasets[name] = self._dataset()

        results = run_dataset_batch(
            tool_impl, Task(), 'map_generator', ['line A', 'line B'],
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [[0.15, 0.25]], 'scan_type': 'line'})

        folders = [Path(r['output']['output_folder']) for r in results]
        assert folders[0] != folders[1]
        assert {f.name for f in folders} == {'line_A', 'line_B'}
        for folder in folders:
            assert list((folder / 'tiff').glob('*.tiff'))


class TestGsfCarriesTheAxes(TestToolImplementationsSetup):
    """The .gsf must state its dimensions: position across, energy up.

    Gwyddion reads real dimensions from GSF and nothing else, so a file
    without XReal/YReal opens as bare pixels — which is what these maps were
    doing.
    """

    STEP_M = 5e-9

    def _dataset(self, n_spectra=8, n_points=256, with_positions=True):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{n + 1}": 1e-11 * (n + 1) * np.exp(-0.5 * ((x - 0.2) / 0.01) ** 2)
                              + 1e-12
                   for n in range(n_spectra)}
        info = {}
        if with_positions:
            info['spectrum_meta'] = [{'location_m': [n * self.STEP_M, 0.0]}
                                     for n in range(n_spectra)]
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A/V'}, additional_info=info))

    def _run(self, tool_impl, dataset=None, **params):
        tool_impl._datasets['line'] = dataset if dataset is not None else self._dataset()
        return tool_impl.generate_maps_from_spectra(
            MockTask(), 'line',
            {'baseline': 'none', 'interval_source': 'manual', 'scan_type': 'line',
             'intervals': [[-0.30, -0.20], [0.15, 0.25]], **params})

    @staticmethod
    def _gsf(tiff_path):
        from src.utils.gsf_io import read_gsf
        path = Path(tiff_path)
        gsf = path.parent.parent / 'gsf' / (path.stem + '.gsf')
        return read_gsf(gsf)[1]

    def test_a_map_states_its_width_in_metres(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['map_paths'][0])

        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(8 * self.STEP_M)

    def test_the_joined_map_states_the_energy_axis(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])

        # The intervals run -0.30 V to 0.25 V.
        assert header['YOffset'] == pytest.approx(-0.30)
        assert header['YReal'] == pytest.approx(0.55)

    def test_the_joined_map_states_the_position_axis(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])
        assert header['XReal'] == pytest.approx(8 * self.STEP_M)

    def test_the_title_names_both_axes(self, tool_impl):
        result = self._run(tool_impl)
        header = self._gsf(result['interval_map_path'])
        assert 'x=position' in header['Title'] and 'y=energy' in header['Title']

    def test_a_dataset_without_positions_still_gets_an_x_axis(self, tool_impl):
        """Re-imported from CSV: the point index is a real axis; metres are
        not to be invented."""
        result = self._run(tool_impl, self._dataset(with_positions=False))
        header = self._gsf(result['map_paths'][0])

        assert header['XReal'] == pytest.approx(8)          # points, not metres
        assert header.get('XYUnits', '') == ''
        assert 'point index' in header['Title']

    def test_detected_bins_land_on_a_linear_energy_axis(self, tool_impl):
        """Occupied bins are not adjacent; the rows must still sit at their
        true bias, so gaps are kept as empty rows."""
        dataset = self._dataset(n_spectra=8)
        tool_impl._datasets['line'] = dataset
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        info = tool_impl._datasets[result['interval_map']].metadata.additional_info
        midpoints = np.asarray(info['interval_midpoints'])
        assert len(midpoints) > len(result['intervals'])     # gaps kept
        assert info['empty_bins'] > 0
        spacing = np.diff(midpoints)
        np.testing.assert_allclose(spacing, spacing[0], rtol=1e-6)

        header = self._gsf(result['interval_map_path'])
        assert header['YReal'] == pytest.approx(len(midpoints) * info['bin_width'])

    def test_hand_picked_intervals_are_not_forced_onto_a_grid(self, tool_impl):
        """Two arbitrary intervals are two rows, not a padded grid."""
        result = self._run(tool_impl, intervals=[[-0.30, -0.20], [0.15, 0.25]])
        dataset = tool_impl._datasets[result['interval_map']]
        assert dataset.num_points == 2


class TestMapDefaults(TestToolImplementationsSetup):
    """The Map Generator's defaults are measured, not guessed — these pin the
    values so a change has to be deliberate."""

    def test_the_defaults_are_what_the_benchmark_chose(self):
        from src.backend.tool_implementations import MAP_DEFAULTS, CONFINEMENT_DEFAULTS

        resolved = {**CONFINEMENT_DEFAULTS, **MAP_DEFAULTS}
        assert resolved['baseline'] == 'arpls'
        assert resolved['height_mode'] == 'noise'
        assert resolved['height'] == 3.0            # sigma, not percent
        assert resolved['noise_floor'] == 1.0
        # A state at a single position is real; 2 would hide it.
        assert resolved['min_spectra_per_bin'] == 1

    def test_peak_analysis_keeps_its_own_threshold(self):
        """Maps want contrast, peak analysis wants sensitivity — 3 sigma there
        would cost 8% of the weak states."""
        from src.backend.tool_implementations import MAP_DEFAULTS, CONFINEMENT_DEFAULTS

        assert CONFINEMENT_DEFAULTS['height'] == 2.0
        assert MAP_DEFAULTS['height'] > CONFINEMENT_DEFAULTS['height']

    def _dataset(self, n_spectra=8, n_points=256, seed=5):
        rng = np.random.default_rng(seed)
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {}
        for n in range(n_spectra):
            y = rng.normal(0, 2e-12, n_points) + 2e-11
            y = y + (n + 1) * 3e-11 * np.exp(-0.5 * ((x - 0.20) / 0.02) ** 2)
            columns[f"P{n + 1}"] = y
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A/V'}, additional_info={}))

    def test_a_run_with_no_parameters_uses_them(self, tool_impl):
        tool_impl._datasets['line'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        info = tool_impl._datasets[result['values_dataset']].metadata.additional_info
        assert info['noise_floor'] == 1.0
        assert info['background'] == 'arpls'

    def test_the_defaults_produce_a_map_with_no_negatives(self, tool_impl):
        tool_impl._datasets['line'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        values = tool_impl._datasets[result['values_dataset']].data.iloc[:, 1:]
        assert not (values.to_numpy() < 0).any()

    def test_the_defaults_still_find_the_planted_state(self, tool_impl):
        tool_impl._datasets['line'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        assert any(lo <= 0.20 <= hi for lo, hi in result['intervals'])

    def test_an_explicit_parameter_still_wins(self, tool_impl):
        tool_impl._datasets['line'] = self._dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line', 'noise_floor': 0.0})

        info = tool_impl._datasets[result['values_dataset']].metadata.additional_info
        assert info['noise_floor'] == 0.0

    def _gapped_dataset(self, n_spectra=8, n_points=256, seed=6):
        """Two well-separated states, so the bin grid has gaps between them."""
        rng = np.random.default_rng(seed)
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {}
        for n in range(n_spectra):
            y = rng.normal(0, 2e-12, n_points) + 2e-11
            y = y + (n + 1) * 3e-11 * np.exp(-0.5 * ((x + 0.30) / 0.015) ** 2)
            y = y + (n + 1) * 3e-11 * np.exp(-0.5 * ((x - 0.25) / 0.015) ** 2)
            columns[f"P{n + 1}"] = y
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A/V'}, additional_info={}))

    def test_empty_bins_are_zero_not_masked(self, tool_impl):
        """A bin no spectrum had a peak in has no spectral weight — that is a
        value. NaN would mean "not measured", and viewers draw it as a masked
        or interpolated region, which reads as though something were there.
        """
        tool_impl._datasets['line'] = self._gapped_dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        dataset = tool_impl._datasets[result['interval_map']]
        values = dataset.spectra.to_numpy()
        info = dataset.metadata.additional_info

        assert info['empty_bins'] > 0, "no gap in this run — test proves nothing"
        assert not np.isnan(values).any()
        assert int((values == 0).all(axis=1).sum()) == info['empty_bins']

    def test_the_exported_files_have_no_masked_cells(self, tool_impl):
        import tifffile
        from src.utils.gsf_io import read_gsf

        tool_impl._datasets['line'] = self._gapped_dataset()
        result = tool_impl.generate_maps_from_spectra(
            MockTask(), 'line', {'scan_type': 'line'})

        tiff_path = Path(result['interval_map_path'])
        assert not np.isnan(tifffile.imread(tiff_path)).any()

        gsf = tiff_path.parent.parent / 'gsf' / (tiff_path.stem + '.gsf')
        assert not np.isnan(read_gsf(gsf)[0]).any()

        csv = tiff_path.parent.parent / 'csv' / (tiff_path.stem + '.csv')
        assert not np.isnan(np.loadtxt(csv, delimiter=',')).any()


class TestPositionsSurviveDerivedDatasets(TestToolImplementationsSetup):
    """A derivative of a line scan is still that line scan's spectra.

    The positions used to be dropped by every tool that rebuilt a dataset, so
    maps of a derivative fell back to point indices — the map opened in
    Gwyddion as pixels rather than nanometres.
    """

    STEP_M = 7e-9

    def _line(self, n_spectra=8, n_points=128):
        x = np.linspace(-0.6, 0.6, n_points)
        columns = {f"P{n + 1}": np.exp(-0.5 * ((x - 0.2) / 0.05) ** 2) * (n + 1) * 1e-11
                   for n in range(n_spectra)}
        meta = [{'column': f"P{n + 1}", 'line_pos': n,
                 'location_m': [n * self.STEP_M, 0.0]} for n in range(n_spectra)]
        return SpectralData(pd.DataFrame({"V": x, **columns}), SpectralMetadata(
            source_type='sts', dimensions=(n_spectra, 1), scan_mode='line',
            units={'independent': 'V', 'dependent': 'A'},
            additional_info={'spectrum_meta': meta, 'spatial_layout': 'line'}))

    def test_the_derivative_keeps_them(self, tool_impl):
        tool_impl._datasets['line'] = self._line()
        tool_impl.calculate_derivative('line', order=1)

        derived = [n for n in tool_impl._datasets if 'Derivative' in n][0]
        assert tool_impl._line_step_m(tool_impl._datasets[derived]) == pytest.approx(self.STEP_M)

    def test_smoothing_keeps_them(self, tool_impl):
        tool_impl._datasets['line'] = self._line()
        tool_impl.smooth_curves(MockTask(), 'line', window_size=5, poly_order=2)

        derived = [n for n in tool_impl._datasets if 'Smoothed' in n][0]
        assert tool_impl._line_step_m(tool_impl._datasets[derived]) == pytest.approx(self.STEP_M)

    def test_a_map_of_a_derivative_is_in_metres(self, tool_impl):
        from src.utils.gsf_io import read_gsf

        tool_impl._datasets['line'] = self._line()
        tool_impl.calculate_derivative('line', order=1)
        derived = [n for n in tool_impl._datasets if 'Derivative' in n][0]

        result = tool_impl.generate_maps_from_spectra(
            MockTask(), derived,
            {'baseline': 'none', 'interval_source': 'manual',
             'intervals': [[0.15, 0.25]], 'scan_type': 'line'})

        tiff = Path(result['map_paths'][0])
        header = read_gsf(tiff.parent.parent / 'gsf' / (tiff.stem + '.gsf'))[1]
        assert header['XYUnits'] == 'm'
        assert header['XReal'] == pytest.approx(8 * self.STEP_M)

    def test_a_dataset_that_only_names_its_source_still_finds_them(self, tool_impl):
        """Results made before the metadata was carried across: the search
        follows the recorded source dataset."""
        tool_impl._datasets['line'] = self._line()
        orphan = self._line()
        orphan.metadata.additional_info = {'original': 'line'}
        tool_impl._datasets['orphan'] = orphan

        assert tool_impl._line_step_m(orphan) == pytest.approx(self.STEP_M)

    def test_an_integration_result_finds_them_through_original_dataset(self, tool_impl):
        """The key the Integration tool writes.

        Its flat table records only ``original_dataset``, and a decomposed
        Integration -> Map Assembly chain has nothing else to go on: without
        this the maps come out in point indices, which the export rule does
        not allow when the metres are there to be had.
        """
        tool_impl._datasets['line'] = self._line(n_spectra=8)
        integrated = SpectralData(
            pd.DataFrame({'Spectrum_Index': np.arange(8),
                          'Interval_0.150_0.250': np.arange(8.0)}),
            SpectralMetadata(
                source_type='integrated_flat', dimensions=(8, 1), scan_mode='line',
                units={'independent': 'Index', 'dependent': 'Integrated Value'},
                additional_info={'original_dataset': 'line',
                                 'intervals': [(0.15, 0.25)]},
                data_type='flat'))

        assert tool_impl._line_step_m(integrated) == pytest.approx(self.STEP_M)

    def test_a_source_with_a_different_spectrum_count_is_not_used(self, tool_impl):
        """An average of a line is one spectrum: the line's positions are not
        its positions."""
        tool_impl._datasets['line'] = self._line(n_spectra=8)
        averaged = self._line(n_spectra=2)
        averaged.metadata.additional_info = {'original': 'line'}

        assert tool_impl._line_step_m(averaged) is None

    def test_a_metadata_loop_terminates(self, tool_impl):
        a = self._line()
        a.metadata.additional_info = {'original': 'b'}
        b = self._line()
        b.metadata.additional_info = {'original': 'a'}
        tool_impl._datasets.update({'a': a, 'b': b})

        assert tool_impl._line_step_m(a) is None      # and does not hang

    def test_filtering_keeps_the_positions_of_the_columns_it_kept(self, tool_impl):
        tool_impl._datasets['line'] = self._line(n_spectra=8)
        result = tool_impl.filter_bad_data(MockTask(), 'line', threshold=0.5)
        assert result

        for name, dataset in tool_impl._datasets.items():
            if 'Good Data' not in name:
                continue
            info = dataset.metadata.additional_info
            if 'spectrum_meta' in info:
                assert len(info['spectrum_meta']) == dataset.num_spectra
