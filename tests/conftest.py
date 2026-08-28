"""
TRANS-QML Test Configuration and Fixtures
Shared fixtures for all test modules
"""

import os

# The app sets this before it creates its QGuiApplication (`main.py`), and a
# QML test that does not measures a different set of controls than the one
# that ships: the macOS style sizes a Button from its text, the Basic style
# gives every one of them an implicit width of 100 px. A layout that fits
# under the first and clips under the second passed for months.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import pytest
import numpy as np
import pandas as pd
import weakref
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.spectral_data import SpectralData, SpectralMetadata


# =============================================================================
# Worker threads
# =============================================================================

#: Every worker thread built during the session, weakly held so a test that
#: does tidy up after itself is not kept alive by this.
_LIVE_WORKERS = weakref.WeakSet()


@pytest.fixture(scope="session", autouse=True)
def _track_worker_threads():
    """Record every worker thread as it is constructed.

    A ``WorkerManager`` owns two QThreads that keep spinning unless
    ``shutdown()`` is called. Tests build backends a dozen different ways and
    drop them, so the threads pile up: the session used to end by tearing
    down objects whose threads were still alive (SIGABRT *after* the summary,
    exit 134), and once enough of them accumulated — a hundred, on a full
    run — the process aborted mid-run instead, at a different test each time.

    Wrapping the constructor rather than sweeping the heap: `gc.get_objects()`
    per test is far too slow over a suite this size, and the set has to be
    exact or the crash comes back.
    """
    try:
        from src.backend.worker import PersistentWorker
    except Exception:                       # PySide6 not importable: nothing to do
        yield
        return

    original = PersistentWorker.__init__

    def tracked(self, *args, **kwargs):
        original(self, *args, **kwargs)
        _LIVE_WORKERS.add(self)

    PersistentWorker.__init__ = tracked
    try:
        yield
    finally:
        PersistentWorker.__init__ = original
        _stop_worker_threads()


@pytest.fixture(autouse=True)
def _stop_worker_threads_after_each_test():
    """Stop the threads this test started, before the next one runs.

    Per test and not per session: it is the accumulation that kills the run,
    so cleaning up at the end would be too late to help.
    """
    yield
    _stop_worker_threads()


def _stop_worker_threads():
    for worker in list(_LIVE_WORKERS):
        try:
            if worker.isRunning():
                worker.stop()
                worker.wait(2000)
        except Exception:
            # Teardown is best-effort: a half-built object is not worth
            # failing a test over.
            pass


# =============================================================================
# SpectralData Fixtures
# =============================================================================

@pytest.fixture
def sample_metadata():
    """Create sample metadata."""
    return SpectralMetadata(
        source_type='test',
        dimensions=(5, 2),
        scan_mode='forward',
        units={'x': 'V', 'y': 'nA'}
    )


@pytest.fixture
def sample_spectral_data(sample_metadata):
    """Create sample spectral data for testing (10 spectra, 100 points)."""
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
    return SpectralData(data=df, metadata=sample_metadata)


@pytest.fixture
def sample_spectral_data_large():
    """Create larger spectral data (100 spectra, 500 points) for 10x10 grid."""
    x = np.linspace(-3, 3, 500)
    spectra = np.column_stack([
        np.sin(x * ((i % 10) + 1)) * np.exp(-x**2 / 2)
        for i in range(100)
    ])
    columns = ['Energy'] + [f'Spectrum_{i}' for i in range(100)]
    df = pd.DataFrame(
        np.column_stack([x, spectra]),
        columns=columns
    )
    metadata = SpectralMetadata(
        source_type='test_large',
        dimensions=(10, 10),
        scan_mode='meander',
        units={'x': 'eV', 'y': 'counts'}
    )
    return SpectralData(data=df, metadata=metadata)


@pytest.fixture
def sample_spectral_data_with_peaks():
    """Create spectral data with clear peaks for peak finding tests."""
    x = np.linspace(-5, 5, 200)
    # Create spectra with peaks at different positions
    spectra = []
    for i in range(10):
        # Gaussian peaks at different positions
        peak1 = np.exp(-((x - (-2 + i * 0.1)) ** 2) / 0.1) * 5
        peak2 = np.exp(-((x - (1 + i * 0.05)) ** 2) / 0.2) * 3
        peak3 = np.exp(-((x - 3) ** 2) / 0.3) * 2
        spectrum = peak1 + peak2 + peak3 + np.random.normal(0, 0.05, len(x))
        spectra.append(spectrum)

    spectra = np.column_stack(spectra)
    columns = ['V'] + [f'Spectrum_{i}' for i in range(10)]
    df = pd.DataFrame(
        np.column_stack([x, spectra]),
        columns=columns
    )
    metadata = SpectralMetadata(
        source_type='test_peaks',
        dimensions=(5, 2),
        scan_mode='forward',
        units={'x': 'V', 'y': 'nA'}
    )
    return SpectralData(data=df, metadata=metadata)


@pytest.fixture
def sample_flat_data():
    """Create sample flat/integrated data."""
    x = np.arange(10)
    values = np.array([1.5, 2.3, 1.8, 2.1, 1.9, 2.5, 2.2, 1.7, 2.0, 2.4])
    df = pd.DataFrame({
        'X': x,
        'Integrated_0': values,
        'Integrated_1': values * 1.2,
        'Integrated_2': values * 0.8
    })
    metadata = SpectralMetadata(
        source_type='integrated',
        dimensions=(5, 2),
        scan_mode='forward',
        units={'x': 'index', 'y': 'counts'}
    )
    return SpectralData(data=df, metadata=metadata)


# =============================================================================
# Project and Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir(tmp_path):
    """Create temporary project directory."""
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    (project_dir / "TestProject_outputs").mkdir()
    return project_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary output directory."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    for subdir in ['smoothed', 'derivatives', 'integrated', 'maps', 'peaks']:
        (output_dir / subdir).mkdir()
    return output_dir


@pytest.fixture
def sample_csv_file(tmp_path, sample_spectral_data):
    """Create a sample CSV file for loading tests."""
    csv_path = tmp_path / "sample_data.csv"
    sample_spectral_data.data.to_csv(csv_path, index=False)
    return csv_path


# =============================================================================
# Workflow Fixtures
# =============================================================================

@pytest.fixture
def sample_workflow_dict():
    """Create sample workflow dictionary for serialization tests."""
    return {
        'id': 'wf_test_001',
        'name': 'Test Workflow',
        'description': 'A test workflow',
        'nodes': [
            {
                'id': 'node_001',
                'tool_name': 'DatasetInput',
                'display_name': 'Dataset Input',
                'x': 100,
                'y': 100,
                'inputs': [],
                'outputs': [
                    {'id': 'dataset', 'name': 'Dataset', 'port_type': 'dataset',
                     'is_input': False, 'required': False, 'multi_input': False}
                ],
                'parameters': {'dataset_name': 'TestData'}
            },
            {
                'id': 'node_002',
                'tool_name': 'CurveSmoothing',
                'display_name': 'Curve Smoothing',
                'x': 300,
                'y': 100,
                'inputs': [
                    {'id': 'dataset', 'name': 'Dataset', 'port_type': 'dataset',
                     'is_input': True, 'required': True, 'multi_input': False}
                ],
                'outputs': [
                    {'id': 'smoothed', 'name': 'Smoothed', 'port_type': 'dataset',
                     'is_input': False, 'required': False, 'multi_input': False}
                ],
                'parameters': {'window_size': 11, 'poly_order': 3, 'smoothing_type': 'savgol'}
            }
        ],
        'connections': [
            {
                'id': 'conn_001',
                'source_node_id': 'node_001',
                'source_port_id': 'dataset',
                'target_node_id': 'node_002',
                'target_port_id': 'dataset'
            }
        ],
        'created': '2024-01-01T00:00:00',
        'modified': '2024-01-01T00:00:00'
    }


# =============================================================================
# Mock Backend Fixture
# =============================================================================

@pytest.fixture
def mock_datasets(sample_spectral_data, sample_spectral_data_with_peaks, sample_flat_data):
    """Create mock dataset dictionary."""
    return {
        'TestData': sample_spectral_data,
        'PeakData': sample_spectral_data_with_peaks,
        'FlatData': sample_flat_data
    }


# =============================================================================
# Utility Functions for Tests
# =============================================================================

def arrays_almost_equal(arr1, arr2, rtol=1e-5, atol=1e-8):
    """Check if two arrays are almost equal."""
    return np.allclose(arr1, arr2, rtol=rtol, atol=atol)


def dataframes_equal(df1, df2, check_dtypes=False):
    """Check if two DataFrames are equal."""
    if df1.shape != df2.shape:
        return False
    if list(df1.columns) != list(df2.columns):
        return False
    return np.allclose(df1.values, df2.values, equal_nan=True)


# =============================================================================
# Pytest Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "critical: marks tests as critical for CI")
    config.addinivalue_line("markers", "integration: marks integration tests")


# =============================================================================
# Map Editor Fixtures
# =============================================================================

@pytest.fixture
def sample_map_2d():
    """Create sample 2D map data (50x50)"""
    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    X, Y = np.meshgrid(x, y)
    # Create synthetic height map with Gaussian features
    data = np.exp(-X**2/4 - Y**2/4) * 50 + np.random.normal(0, 0.5, (50, 50))
    return data


@pytest.fixture
def sample_map_small():
    """Create small 2D map data (10x10) for fast tests"""
    return np.random.rand(10, 10) * 100


@pytest.fixture
def sample_spectral_cube():
    """Create sample spectral cube (100 points, 10x10 spatial)"""
    # 100 spectral points, 10x10 spatial grid
    cube = np.random.rand(100, 10, 10)
    independent_var = np.linspace(800, 1800, 100)  # Wavenumbers
    return cube, independent_var


@pytest.fixture
def sample_tiff_file(tmp_path, sample_map_small):
    """Create a sample TIFF file for loading tests"""
    import tifffile
    tiff_path = tmp_path / "sample_map.tif"
    tifffile.imwrite(str(tiff_path), sample_map_small.astype(np.float32))
    return tiff_path


@pytest.fixture
def sample_npy_file(tmp_path, sample_map_small):
    """Create a sample NPY file for loading tests"""
    npy_path = tmp_path / "sample_map.npy"
    np.save(str(npy_path), sample_map_small)
    return npy_path
