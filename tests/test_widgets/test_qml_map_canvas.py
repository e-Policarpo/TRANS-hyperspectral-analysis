"""
Tests for QMLMapCanvas functionality.

Tests the QQuickPaintedItem-based map canvas used in the Map Editor workstation.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch


class TestQMLMapCanvasStatisticsAndExport:
    """Test statistics and export methods for QMLMapCanvas."""

    @pytest.fixture
    def sample_data(self):
        """Create sample map data."""
        np.random.seed(42)
        return np.random.rand(10, 10) * 100

    def test_get_statistics_returns_correct_values(self, sample_data):
        """Test that getStatistics returns correct min, max, mean, std."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(sample_data)

        stats = canvas.getStatistics()

        assert 'min' in stats
        assert 'max' in stats
        assert 'mean' in stats
        assert 'std' in stats
        assert 'rows' in stats
        assert 'cols' in stats

        assert abs(stats['min'] - np.nanmin(sample_data)) < 0.0001
        assert abs(stats['max'] - np.nanmax(sample_data)) < 0.0001
        assert abs(stats['mean'] - np.nanmean(sample_data)) < 0.0001
        assert abs(stats['std'] - np.nanstd(sample_data)) < 0.0001
        assert stats['rows'] == 10
        assert stats['cols'] == 10

    def test_get_statistics_no_data(self):
        """Test that getStatistics returns empty dict when no data loaded."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        stats = canvas.getStatistics()

        assert stats == {}

    def test_set_color_limits(self, sample_data):
        """Test setting color limits."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(sample_data)

        # Set custom limits
        canvas.setColorLimits(20.0, 80.0)

        assert canvas._vmin == 20.0
        assert canvas._vmax == 80.0
        assert canvas._needs_redraw is True

    def test_export_csv(self, sample_data, tmp_path):
        """Test exporting map data to CSV."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(sample_data)

        csv_path = tmp_path / "test_export.csv"
        result = canvas.exportCsv(str(csv_path))

        assert result is True
        assert csv_path.exists()

        # Verify content
        import pandas as pd
        df = pd.read_csv(csv_path, header=None)
        assert df.shape == (10, 10)

    def test_export_csv_no_data(self, tmp_path):
        """Test CSV export fails gracefully with no data."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        csv_path = tmp_path / "test_export.csv"
        result = canvas.exportCsv(str(csv_path))

        assert result is False

    def test_save_map_data_tiff(self, sample_data, tmp_path):
        """Test saving map data to TIFF."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(sample_data)

        tiff_path = tmp_path / "test_save.tiff"
        result = canvas.saveMapData(str(tiff_path))

        assert result is True
        assert tiff_path.exists()

    def test_save_map_data_npy(self, sample_data, tmp_path):
        """Test saving map data to NumPy format."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(sample_data)

        npy_path = tmp_path / "test_save.npy"
        result = canvas.saveMapData(str(npy_path))

        assert result is True
        assert npy_path.exists()

        # Verify data integrity
        loaded = np.load(npy_path)
        np.testing.assert_array_almost_equal(loaded, sample_data)


class TestQMLMapCanvasBlockSelection:
    """Test block selection functionality."""

    @pytest.fixture
    def canvas_with_data(self):
        """Create canvas with sample data."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        canvas.setMapData(np.random.rand(10, 10))
        return canvas

    def test_toggle_block_selection_add(self, canvas_with_data):
        """Test adding a block to selection."""
        canvas = canvas_with_data

        canvas.toggleBlockSelection(5, 5)

        assert (5, 5) in canvas._selected_blocks
        assert canvas.getSelectedBlockCount() == 1

    def test_toggle_block_selection_remove(self, canvas_with_data):
        """Test removing a block from selection."""
        canvas = canvas_with_data

        canvas.toggleBlockSelection(5, 5)  # Add
        canvas.toggleBlockSelection(5, 5)  # Remove

        assert (5, 5) not in canvas._selected_blocks
        assert canvas.getSelectedBlockCount() == 0

    def test_clear_block_selection(self, canvas_with_data):
        """Test clearing all selections."""
        canvas = canvas_with_data

        canvas.toggleBlockSelection(1, 1)
        canvas.toggleBlockSelection(2, 2)
        canvas.toggleBlockSelection(3, 3)

        assert canvas.getSelectedBlockCount() == 3

        canvas.clearBlockSelection()

        assert canvas.getSelectedBlockCount() == 0

    def test_select_all_blocks(self, canvas_with_data):
        """Test selecting all blocks."""
        canvas = canvas_with_data

        canvas.selectAllBlocks()

        assert canvas.getSelectedBlockCount() == 100  # 10x10 grid

    def test_get_selected_blocks_returns_dict_list(self, canvas_with_data):
        """Test that getSelectedBlocks returns proper format."""
        canvas = canvas_with_data

        canvas.toggleBlockSelection(2, 3)
        canvas.toggleBlockSelection(4, 5)

        blocks = canvas.getSelectedBlocks()

        assert len(blocks) == 2
        assert all('row' in b and 'col' in b and 'value' in b for b in blocks)


class TestQMLMapCanvasSpectralLink:
    """Test spectral data linking functionality."""

    @pytest.fixture
    def canvas_with_spectral_data(self):
        """Create canvas with linked spectral cube."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        canvas = QMLMapCanvas()
        map_data = np.random.rand(10, 10)
        canvas.setMapData(map_data)

        # Create spectral cube: 50 spectral points x 10 rows x 10 cols
        spectral_cube = np.random.rand(50, 10, 10)
        independent_var = np.linspace(0, 100, 50)

        canvas.linkSpectralCube(spectral_cube, independent_var, "Voltage")

        return canvas

    def test_link_spectral_cube(self, canvas_with_spectral_data):
        """Test linking spectral data."""
        canvas = canvas_with_spectral_data

        assert canvas.hasSpectralLink is True
        assert canvas.spectralPoints == 50

    def test_get_spectrum_at(self, canvas_with_spectral_data):
        """Test getting spectrum at a position."""
        canvas = canvas_with_spectral_data

        result = canvas.getSpectrumAt(5, 5)

        assert 'x' in result
        assert 'y' in result
        assert 'x_name' in result
        assert result['x_name'] == "Voltage"
        assert len(result['x']) == 50
        assert len(result['y']) == 50

    def test_get_spectrum_at_out_of_bounds(self, canvas_with_spectral_data):
        """Test spectrum retrieval with invalid position."""
        canvas = canvas_with_spectral_data

        result = canvas.getSpectrumAt(100, 100)

        assert 'error' in result

    def test_get_average_spectrum_from_selection(self, canvas_with_spectral_data):
        """Test getting averaged spectrum from selection."""
        canvas = canvas_with_spectral_data

        canvas.toggleBlockSelection(2, 2)
        canvas.toggleBlockSelection(3, 3)

        result = canvas.getAverageSpectrumFromSelection()

        assert 'x' in result
        assert 'y' in result
        assert 'block_count' in result
        assert result['block_count'] == 2

    def test_unlink_spectral_cube(self, canvas_with_spectral_data):
        """Test unlinking spectral data."""
        canvas = canvas_with_spectral_data

        canvas.unlinkSpectralCube()

        assert canvas.hasSpectralLink is False
        assert canvas.spectralPoints == 0


class TestAppBackendImageImport:
    """Test app backend image import functionality."""

    @pytest.fixture
    def mock_backend(self):
        """Create a mock backend with required attributes."""
        from src.backend.app_backend import AppBackend

        backend = AppBackend()
        backend._output_base_dir = None  # Skip file copying
        return backend

    def test_get_imported_map_data_no_data(self, mock_backend):
        """Test getImportedMapData returns error when no data."""
        result = mock_backend.getImportedMapData()

        assert 'error' in result

    def test_get_imported_map_data_with_data(self, mock_backend):
        """Test getImportedMapData returns data correctly."""
        mock_backend._imported_map_data = np.array([[1, 2], [3, 4]])
        mock_backend._imported_map_name = "TestMap"
        mock_backend._imported_map_path = "/path/to/map.tiff"

        result = mock_backend.getImportedMapData()

        assert result['name'] == "TestMap"
        assert result['path'] == "/path/to/map.tiff"
        assert result['rows'] == 2
        assert result['cols'] == 2
        assert result['data'] == [[1, 2], [3, 4]]

    def test_clear_imported_map_data(self, mock_backend):
        """Test clearing imported map data."""
        mock_backend._imported_map_data = np.array([[1, 2], [3, 4]])
        mock_backend._imported_map_name = "TestMap"
        mock_backend._imported_map_path = "/path/to/map.tiff"

        mock_backend.clearImportedMapData()

        assert mock_backend._imported_map_data is None
        assert mock_backend._imported_map_name == ""
        assert mock_backend._imported_map_path == ""


class TestQMLMapCanvasDisplayLevels:
    """Colour-level resolution, incl. the degenerate cases that used to
    paint the whole map white (all-NaN / empty / constant maps)."""

    def _canvas(self):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        return QMLMapCanvas()

    def test_normal_data_gives_finite_increasing_levels(self):
        canvas = self._canvas()
        canvas.setMapData(np.linspace(0, 100, 100).reshape(10, 10))
        lo, hi = canvas._compute_display_levels()
        assert np.isfinite(lo) and np.isfinite(hi)
        assert hi > lo

    def test_all_nan_map_falls_back_to_unit_range(self):
        """A map with no linked spectra is all-NaN; nanpercentile returns
        NaN there. Must NOT propagate NaN into the LUT (white map)."""
        canvas = self._canvas()
        canvas.setMapData(np.full((8, 8), np.nan))
        lo, hi = canvas._compute_display_levels()
        assert np.isfinite(lo) and np.isfinite(hi)
        assert hi > lo
        assert (lo, hi) == (0.0, 1.0)

    def test_constant_map_has_nonzero_span(self):
        canvas = self._canvas()
        canvas.setMapData(np.full((8, 8), 5.0))
        lo, hi = canvas._compute_display_levels()
        assert hi > lo

    def test_explicit_range_is_respected(self):
        canvas = self._canvas()
        canvas.setMapData(np.linspace(0, 100, 64).reshape(8, 8))
        canvas.setValueRange(10.0, 20.0)
        assert canvas._compute_display_levels() == (10.0, 20.0)

    def test_get_value_range_finite_for_all_nan(self):
        canvas = self._canvas()
        canvas.setMapData(np.full((8, 8), np.nan))
        rng = canvas.getValueRange()
        assert all(np.isfinite(v) for v in rng)
        assert rng[1] > rng[0]
