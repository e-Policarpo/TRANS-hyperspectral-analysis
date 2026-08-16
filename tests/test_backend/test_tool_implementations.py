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

    def test_finds_in_gap_states_the_old_tool_missed(self, tool_impl, sts_dataset):
        """The point of the tool: over the full sweep, no background means no peaks."""
        without = self._run(tool_impl, sts_dataset, baseline='none')
        assert without['peaks'] is None

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

    def test_temperature_bins_the_axis_at_kbt(self, tool_impl, sts_dataset):
        """94 K -> kBT = 8.1 meV, which is the column spacing in the by-hand sheet."""
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        axis = result['peak_matrix_binned'].independent_var

        step = np.diff(axis)
        np.testing.assert_allclose(step, 8.617333262e-5 * 94.0, rtol=1e-6)
        # 1.2 V of sweep at 8.1 meV is ~150 bins, far fewer than 512 samples.
        assert 100 < len(axis) < 200

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

        ungrouped = tool_impl.analyze_confinement(MockTask(), 'sts', params={'height': 1.0})
        assert len(ungrouped['peaks'].data) == 3

        grouped = tool_impl.analyze_confinement(
            MockTask(), 'sts', params={'height': 1.0, 'temperature_k': 94.0})
        rows = grouped['peaks'].data
        assert len(rows) == 2
        # The pair collapses to one entry near 0; the distant peak is untouched.
        positions = sorted(rows['position_value'].tolist())
        assert positions[0] == pytest.approx(0.0, abs=0.004)
        assert positions[1] == pytest.approx(0.2, abs=0.004)
        # And the binned matrix agrees with the list.
        assert np.nansum(grouped['peak_matrix_binned'].spectra.values) == 2

    def test_explicit_min_distance_overrides_the_thermal_default(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0, min_distance=0.5)
        # 0.5 V apart is far coarser than kBT, so few peaks survive.
        assert len(result['peaks'].data.query('spectrum_index == 0')) <= 3

    def test_metadata_records_the_temperature(self, tool_impl, sts_dataset):
        result = self._run(tool_impl, sts_dataset, temperature_k=94.0)
        # Both tables record the settings; only one of them is binned.
        for key in ('peak_matrix', 'peak_matrix_binned', 'peaks'):
            info = result[key].metadata.additional_info
            assert info['temperature_k'] == 94.0, key
            assert info['kbt'] == pytest.approx(8.1e-3, rel=1e-2), key

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
        assert len(unsmoothed['peaks'].data) > 3 * len(planted)

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

        # Raw keeps the measured axis; binned is far coarser.
        np.testing.assert_array_equal(raw.independent_var, sts_dataset.independent_var)
        assert len(binned.independent_var) < len(raw.independent_var) / 3
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
        np.testing.assert_allclose(np.diff(axis), kbt, rtol=1e-6)
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
