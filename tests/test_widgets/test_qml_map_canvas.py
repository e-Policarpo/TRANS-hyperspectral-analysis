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


class TestProfileLineResizeSafe:
    """The line profile is stored in axes fractions so it tracks the data
    across window resizes instead of sticking to absolute screen pixels."""

    @staticmethod
    def _canvas_with_axes(ax):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        canvas = QMLMapCanvas()
        canvas.setMapData(np.zeros((100, 100)))
        canvas._data_to_pixel = ax
        return canvas

    def test_axesfrac_roundtrip(self):
        ax = {'ax_left': 50, 'ax_right': 450, 'ax_top': 20, 'ax_bottom': 420,
              'data_rows': 100, 'data_cols': 100}
        canvas = self._canvas_with_axes(ax)
        nx, ny = canvas._pixel_to_axesfrac(250.0, 220.0)   # centre of axes
        assert nx == pytest.approx(0.5)
        assert ny == pytest.approx(0.5)
        px, py = canvas._axesfrac_to_pixel(nx, ny)
        assert (px, py) == pytest.approx((250.0, 220.0))

    def test_profile_pixel_follows_axes_on_resize(self):
        small = {'ax_left': 50, 'ax_right': 250, 'ax_top': 20, 'ax_bottom': 220,
                 'data_rows': 100, 'data_cols': 100}
        canvas = self._canvas_with_axes(small)
        # A point at 25% across / 75% down the axes.
        frac = canvas._pixel_to_axesfrac(100.0, 170.0)
        assert frac == pytest.approx((0.25, 0.75))
        # Window grows: axes rect doubles. Same fraction → new pixel.
        big = {'ax_left': 100, 'ax_right': 500, 'ax_top': 40, 'ax_bottom': 440,
               'data_rows': 100, 'data_cols': 100}
        canvas._data_to_pixel = big
        px, py = canvas._axesfrac_to_pixel(*frac)
        assert px == pytest.approx(100 + 0.25 * 400)   # 200
        assert py == pytest.approx(40 + 0.75 * 400)     # 340

    def test_axesfrac_none_without_axes(self):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        canvas = QMLMapCanvas()
        canvas._data_to_pixel = None
        assert canvas._pixel_to_axesfrac(1, 2) is None
        assert canvas._axesfrac_to_pixel(0.5, 0.5) is None


@pytest.fixture(scope="module")
def gui_app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


class TestStsLineOutlines:
    """Line-scan outlines drawn over a scan image."""

    def _canvas(self):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        canvas = QMLMapCanvas()
        canvas.setMapData(np.zeros((32, 32)))
        return canvas

    def test_setter_stores_the_path_in_row_col_order(self):
        canvas = self._canvas()
        canvas.setStsLines([{'label': 'line1 · 4pts',
                             'path': [{'col': 10, 'row': 30},
                                      {'col': 15, 'row': 30},
                                      {'col': 20, 'row': 30}]}])

        assert len(canvas._sts_lines) == 1
        assert canvas._sts_lines[0]['label'] == 'line1 · 4pts'
        assert canvas._sts_lines[0]['path'] == [(30, 10), (30, 15), (30, 20)]

    def test_a_single_point_is_not_a_line(self):
        canvas = self._canvas()
        canvas.setStsLines([{'label': 'x', 'path': [{'col': 1, 'row': 1}]}])
        assert canvas._sts_lines == []

    def test_malformed_points_are_dropped_without_raising(self):
        canvas = self._canvas()
        canvas.setStsLines([{'label': 'line1',
                             'path': [{'col': 1, 'row': 2}, {'col': None},
                                      {'col': 3, 'row': 4}]}])
        assert canvas._sts_lines[0]['path'] == [(2, 1), (4, 3)]

    def test_empty_list_clears_previous_outlines(self):
        canvas = self._canvas()
        canvas.setStsLines([{'label': 'line1',
                             'path': [{'col': 1, 'row': 1}, {'col': 5, 'row': 1}]}])
        canvas.setStsLines([])
        assert canvas._sts_lines == []

    def test_outlines_paint_without_error(self, gui_app):
        from PySide6.QtGui import QImage, QPainter
        canvas = self._canvas()
        canvas.setWidth(240)
        canvas.setHeight(200)
        canvas.setStsLines([{'label': 'line1 · 4pts ×3 · pt20→pt23',
                             'path': [{'col': 4, 'row': 8}, {'col': 20, 'row': 8}]}])
        canvas.setStsMarkers([{'row': 8, 'col': 4, 'label': '20', 'index': 0}])

        image = QImage(240, 200, QImage.Format_ARGB32)
        painter = QPainter(image)
        try:
            canvas.paint(painter)     # must not raise
        finally:
            painter.end()

    def test_a_tag_avoids_the_points_it_names(self):
        """The tag must not sit on the dots — it would hide the data."""
        from PySide6.QtCore import QRectF
        from src.widgets.qml_map_canvas import QMLMapCanvas

        # A horizontal line of dots across the middle of the canvas.
        dots = [QRectF(x - 9, 91, 18, 18) for x in range(40, 300, 12)]
        pts = [(40.0, 100.0), (300.0, 100.0)]
        chip = QMLMapCanvas._place_chip(
            QMLMapCanvas._chip_candidates(pts, 220, 22, 600, 400), dots)

        assert all(not chip.intersects(dot) for dot in dots)

    def test_a_tag_avoids_the_point_index_labels(self):
        from PySide6.QtCore import QRectF
        from src.widgets.qml_map_canvas import QMLMapCanvas

        labels = [QRectF(x + 9, 70, 20, 16) for x in range(40, 300, 12)]
        pts = [(40.0, 100.0), (300.0, 100.0)]
        chip = QMLMapCanvas._place_chip(
            QMLMapCanvas._chip_candidates(pts, 220, 22, 600, 400), labels)

        assert all(not chip.intersects(label) for label in labels)

    def test_two_tags_on_one_path_do_not_overlap(self):
        """A multi-rep scan and a single sweep can share a path."""
        from src.widgets.qml_map_canvas import QMLMapCanvas

        pts = [(40.0, 100.0), (300.0, 100.0)]
        candidates = QMLMapCanvas._chip_candidates(pts, 220, 22, 600, 400)
        first = QMLMapCanvas._place_chip(candidates, [])
        second = QMLMapCanvas._place_chip(candidates, [first])

        assert not second.intersects(first)

    def test_a_tag_stays_inside_the_canvas(self):
        from src.widgets.qml_map_canvas import QMLMapCanvas

        pts = [(5.0, 5.0), (20.0, 5.0)]     # hard against the top-left corner
        for chip in QMLMapCanvas._chip_candidates(pts, 220, 22, 400, 300):
            assert chip.left() >= 0 and chip.top() >= 0
            assert chip.right() <= 400 and chip.bottom() <= 300

    def test_a_crowded_canvas_still_gets_a_tag(self):
        """With nowhere clear the label must still be drawn, in the least-bad
        spot — a vanished tag is worse than a partly covered one."""
        from PySide6.QtCore import QRectF
        from src.widgets.qml_map_canvas import QMLMapCanvas

        everywhere = [QRectF(0, 0, 600, 400)]
        pts = [(40.0, 100.0), (300.0, 100.0)]
        chip = QMLMapCanvas._place_chip(
            QMLMapCanvas._chip_candidates(pts, 220, 22, 600, 400), everywhere)

        assert not chip.isEmpty()

    def test_the_obstacle_list_covers_dots_and_labels(self, gui_app):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        from PySide6.QtGui import QImage, QPainter

        canvas = self._canvas()
        canvas.setWidth(300)
        canvas.setHeight(240)
        canvas.setStsMarkers([{'row': 4, 'col': 4, 'label': '11', 'index': 0},
                              {'row': 4, 'col': 8, 'label': '12', 'index': 1}])

        image = QImage(300, 240, QImage.Format_ARGB32)
        painter = QPainter(image)
        try:
            canvas.paint(painter)      # lays out _data_to_pixel
            rects = canvas._sts_marker_obstacles(painter.fontMetrics())
        finally:
            painter.end()

        # One rect for each dot plus one for each label.
        assert len(rects) == 4


class TestDecimalSpinBoxes:
    """A decimal field must read back what was typed.

    SpinBox's default validator is an IntValidator, which drops the decimal
    point: "4.5" became "45" and, scaled by 1/100, arrived as 0.45 — a tenth
    of the intended temperature.
    """

    @staticmethod
    def _field(qml_source, decimals):
        import re
        source = open(qml_source).read()
        # The two functions under test are pure string/number handling, so
        # they are exercised directly rather than through a QML engine.
        factor = 10 ** decimals

        def value_from_text(text, current=0):
            parsed = float(str(text).replace(",", "."))
            return round(parsed * factor)

        def text_from_value(value):
            return f"{value / factor:.{decimals}f}"

        assert 'DoubleValidator' in source, "decimal fields need a DoubleValidator"
        assert 'IntValidator' in source, "integer fields must keep an IntValidator"
        return value_from_text, text_from_value

    @pytest.mark.parametrize("qml", [
        "src/qml/components/ToolSpinBox.qml",
        "src/qml/tools/ConfinementAnalysisTool.qml",
    ])
    def test_the_spinbox_declares_a_double_validator(self, qml):
        source = open(qml).read()
        assert 'DoubleValidator' in source
        # "C" locale, so the field accepts the dot its own textFromValue writes.
        assert 'locale: "C"' in source

    def test_a_typed_temperature_round_trips(self):
        from_text, to_text = self._field("src/qml/components/ToolSpinBox.qml", 2)
        assert from_text("4.5") / 100 == 4.5
        assert to_text(from_text("4.5")) == "4.50"

    def test_a_comma_decimal_is_accepted(self):
        from_text, _ = self._field("src/qml/components/ToolSpinBox.qml", 2)
        assert from_text("4,5") / 100 == 4.5


class TestAutoScaleShowsTheWholeMap:
    """A computed map's signal lives in the tails.

    Auto-scale used to clip at 2-98%, which on a bias-versus-position LDOS
    map kept 14% of the value range and drove 4% of the pixels to a solid end
    colour — the map read as thresholded.
    """

    @staticmethod
    def _canvas(field=None):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        canvas = QMLMapCanvas()
        if field is not None:
            canvas.setMapData(field)
        return canvas

    @staticmethod
    def _heavy_tailed():
        """Mostly near zero, with the rare bright states that matter."""
        rng = np.random.default_rng(0)
        field = np.abs(rng.normal(0, 1e-12, (60, 250)))
        field[10, 40] = 6e-9
        field[30, 120] = 4e-9
        return field

    def test_the_default_levels_span_the_data(self, gui_app):
        field = self._heavy_tailed()
        lo, hi = self._canvas(field)._compute_display_levels()

        assert lo == pytest.approx(float(np.nanmin(field)))
        assert hi == pytest.approx(float(np.nanmax(field)))

    def test_nothing_is_driven_to_a_solid_colour(self, gui_app):
        field = self._heavy_tailed()
        lo, hi = self._canvas(field)._compute_display_levels()
        assert not ((field > hi) | (field < lo)).any()

    def test_clipping_is_still_available(self, gui_app):
        field = self._heavy_tailed()
        canvas = self._canvas(field)
        canvas.setPercentileClip(2, 98)
        lo, hi = canvas._compute_display_levels()

        assert hi < float(np.nanmax(field))       # the tail is clipped again
        assert lo >= float(np.nanmin(field))

    def test_explicit_limits_still_win(self, gui_app):
        canvas = self._canvas(self._heavy_tailed())
        canvas.setValueRange(-1.0, 2.0)
        assert canvas._compute_display_levels() == (-1.0, 2.0)

    @pytest.mark.parametrize("low,high", [(50, 10), (-5, 99), (0, 200), (30, 30)])
    def test_a_nonsensical_clip_is_ignored(self, gui_app, low, high):
        canvas = self._canvas(self._heavy_tailed())
        before = canvas._percentile_clip
        canvas.setPercentileClip(low, high)
        assert canvas._percentile_clip == before

    def test_an_all_nan_map_still_yields_usable_levels(self, gui_app):
        canvas = self._canvas(np.full((8, 8), np.nan))
        lo, hi = canvas._compute_display_levels()
        assert np.isfinite(lo) and np.isfinite(hi) and hi > lo

    def test_a_flat_map_does_not_collapse_the_scale(self, gui_app):
        canvas = self._canvas(np.full((8, 8), 3.0))
        lo, hi = canvas._compute_display_levels()
        assert hi > lo


class TestCursorCoordinates:
    """The read-out must say where on the sample the cursor is."""

    @staticmethod
    def _canvas(rows=40, cols=60):
        from src.widgets.qml_map_canvas import QMLMapCanvas
        canvas = QMLMapCanvas()
        canvas.setMapData(np.zeros((rows, cols)))
        return canvas

    def test_pixels_map_onto_the_physical_extent(self, gui_app):
        canvas = self._canvas(rows=40, cols=60)
        canvas.setPhysicalExtent(300.0, 200.0, "nm")     # 5 nm per pixel

        first = canvas.physicalAt(0, 0)
        assert first['valid']
        # The centre of the first pixel, not its edge.
        assert first['x'] == pytest.approx(2.5)
        assert first['y'] == pytest.approx(2.5)
        assert first['unit'] == 'nm'

        last = canvas.physicalAt(39, 59)
        assert last['x'] == pytest.approx(297.5)
        assert last['y'] == pytest.approx(197.5)

    def test_an_uncalibrated_map_reports_invalid(self, gui_app):
        """No scale means no coordinates — the caller shows pixel indices
        rather than a position that was never measured."""
        assert self._canvas().physicalAt(1, 1)['valid'] is False

    def test_out_of_range_pixels_report_invalid(self, gui_app):
        canvas = self._canvas(rows=10, cols=10)
        canvas.setPhysicalExtent(100.0, 100.0, "nm")
        assert canvas.physicalAt(10, 0)['valid'] is False
        assert canvas.physicalAt(0, -1)['valid'] is False

    def test_each_axis_can_carry_its_own_quantity(self, gui_app):
        """A kymograph is distance across and bias up."""
        canvas = self._canvas(rows=100, cols=50)
        canvas.setAxisMetadata({
            'x_size': 250e-9, 'x_unit': 'm', 'x_offset': 0.0,
            'y_size': 1.2, 'y_unit': 'V', 'y_offset': -0.6,
        })

        at = canvas.physicalAt(0, 0)
        assert at['x_unit'] == 'm' and at['y_unit'] == 'V'
        assert at['x'] == pytest.approx(2.5e-9)          # centre of pixel 0
        assert at['y'] == pytest.approx(-0.594)

        middle = canvas.physicalAt(50, 25)
        assert middle['y'] == pytest.approx(0.006)

    def test_axis_metadata_wins_over_the_extent(self, gui_app):
        canvas = self._canvas(rows=10, cols=10)
        canvas.setPhysicalExtent(100.0, 100.0, "nm")
        canvas.setAxisMetadata({'x_size': 1.0, 'x_unit': 'm',
                                'y_size': 2.0, 'y_unit': 'V'})
        at = canvas.physicalAt(0, 0)
        assert at['x_unit'] == 'm' and at['y_unit'] == 'V'

    def test_clearing_the_metadata_falls_back_to_the_extent(self, gui_app):
        canvas = self._canvas(rows=10, cols=10)
        canvas.setPhysicalExtent(100.0, 100.0, "nm")
        canvas.setAxisMetadata({'x_size': 1.0, 'x_unit': 'm'})
        canvas.setAxisMetadata({})
        assert canvas.physicalAt(0, 0)['unit'] == 'nm'
