"""
Tests for graph export functionality (PNG, SVG, PDF, CSV).
Tests the export logic using pure matplotlib (headless, no QML dependency).
"""

import pytest
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class CurveData:
    """Minimal CurveData for testing."""
    curve_id: int
    label: str
    x: np.ndarray
    y: np.ndarray
    color: str = "#5BCEFA"
    linestyle: str = "-"
    linewidth: float = 2.0
    marker: str = ""
    alpha: float = 1.0
    visible: bool = True
    table_id: Optional[str] = None
    column_index: Optional[int] = None


class MockGraphCanvas:
    """
    Standalone mock that replicates the export methods from QMLGraphCanvas
    without requiring QQuickPaintedItem initialization.
    """

    def __init__(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        self._dpi = 100
        self.figure = Figure(facecolor='#1a1a1a', dpi=self._dpi)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasAgg(self.figure)
        self._curves = {}
        self._x_label = "X"
        self._y_label = "Y"
        self._title = "Test Graph"
        self._show_legend = True

        # Set figure size
        self.figure.set_size_inches(6, 4)

    def _render(self):
        self.axes.clear()
        self.axes.set_facecolor('#1a1a1a')
        for curve in self._curves.values():
            if curve.visible:
                self.axes.plot(curve.x, curve.y, label=curve.label, color=curve.color)
        self.axes.set_xlabel(self._x_label)
        self.axes.set_ylabel(self._y_label)
        self.axes.set_title(self._title)
        if self._show_legend and self._curves:
            self.axes.legend()
        self.figure.tight_layout()
        self.canvas.draw()

    def exportToPNG(self, filepath):
        try:
            self._render()
            self.figure.savefig(filepath, dpi=300, bbox_inches='tight',
                                facecolor=self.figure.get_facecolor())
            return True
        except Exception:
            return False

    def exportToSVG(self, filepath):
        try:
            self._render()
            self.figure.savefig(filepath, bbox_inches='tight', format='svg',
                                facecolor=self.figure.get_facecolor())
            return True
        except Exception:
            return False

    def exportToPDF(self, filepath):
        try:
            self._render()
            self.figure.savefig(filepath, bbox_inches='tight', format='pdf',
                                facecolor=self.figure.get_facecolor())
            return True
        except Exception:
            return False

    def exportToCSV(self, filepath):
        try:
            import csv
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                headers = []
                columns = []
                for curve in self._curves.values():
                    if not curve.visible:
                        continue
                    label = curve.label
                    headers.extend([f"{label}_X", f"{label}_Y"])
                    columns.extend([curve.x, curve.y])

                if not headers:
                    return False

                writer.writerow(headers)
                max_len = max(len(c) for c in columns)
                for i in range(max_len):
                    row = []
                    for col in columns:
                        row.append(col[i] if i < len(col) else '')
                    writer.writerow(row)
            return True
        except Exception:
            return False


class TestGraphExport:
    """Tests for graph export methods."""

    @pytest.fixture
    def graph_canvas(self):
        """Create a mock graph canvas with test data."""
        canvas = MockGraphCanvas()
        x = np.linspace(0, 10, 100)
        canvas._curves[0] = CurveData(
            curve_id=0, label="Sin", x=x, y=np.sin(x),
            color="#5BCEFA", visible=True
        )
        canvas._curves[1] = CurveData(
            curve_id=1, label="Cos", x=x, y=np.cos(x),
            color="#F5A9B8", visible=True
        )
        return canvas

    def test_export_png(self, graph_canvas, tmp_path):
        """GE-01: Export to PNG produces non-empty file."""
        filepath = str(tmp_path / "test_graph.png")
        result = graph_canvas.exportToPNG(filepath)
        assert result is True
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0

    def test_export_svg(self, graph_canvas, tmp_path):
        """GE-02: Export to SVG produces non-empty file."""
        filepath = str(tmp_path / "test_graph.svg")
        result = graph_canvas.exportToSVG(filepath)
        assert result is True
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0
        content = Path(filepath).read_text()
        assert '<svg' in content

    def test_export_pdf(self, graph_canvas, tmp_path):
        """GE-03: Export to PDF produces non-empty file."""
        filepath = str(tmp_path / "test_graph.pdf")
        result = graph_canvas.exportToPDF(filepath)
        assert result is True
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0
        with open(filepath, 'rb') as f:
            header = f.read(4)
        assert header == b'%PDF'

    def test_export_csv(self, graph_canvas, tmp_path):
        """GE-04: Export to CSV produces valid data file."""
        filepath = str(tmp_path / "test_graph.csv")
        result = graph_canvas.exportToCSV(filepath)
        assert result is True
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0

        import csv
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert len(headers) == 4
            assert 'Sin_X' in headers
            assert 'Sin_Y' in headers
            assert 'Cos_X' in headers
            assert 'Cos_Y' in headers
            rows = list(reader)
            assert len(rows) == 100

    def test_export_csv_no_visible_curves(self, graph_canvas, tmp_path):
        """GE-05: Export CSV with no visible curves returns False."""
        for curve in graph_canvas._curves.values():
            curve.visible = False
        filepath = str(tmp_path / "empty_graph.csv")
        result = graph_canvas.exportToCSV(filepath)
        assert result is False

    def test_export_png_invalid_path(self, graph_canvas):
        """GE-06: Export to invalid path returns False."""
        result = graph_canvas.exportToPNG("/nonexistent/dir/file.png")
        assert result is False
