"""
QML Map Canvas - QQuickPaintedItem for matplotlib rendering in QML
Enables seamless integration of matplotlib maps into QML UI with
interactive tools for spatial-spectral reconstruction.
T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
Contact: eduardapolicarpo.fisica@gmail.com
Date: December 2025
License: GPL
"""

import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from enum import Enum
import logging

from PySide6.QtCore import (
    Qt, Signal, Slot, Property, QPointF, QRectF, QObject, QTimer
)
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QCursor
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class MapTool(Enum):
    """Available map editing tools"""
    POINTER = "pointer"
    ZOOM_RECT = "zoom_rect"
    PAN = "pan"
    LINE_PROFILE = "line_profile"
    POINT_INSPECTOR = "point_inspector"
    RECT_SELECT = "rect_select"
    MEASURE = "measure"
    CROSSHAIR = "crosshair"
    BLOCK_SELECT = "block_select"  # For discretized block selection (TRANS_v3 style)


class QMLMapCanvas(QQuickPaintedItem):
    """
    Matplotlib canvas that renders directly in QML scene graph.

    This QQuickPaintedItem renders matplotlib figures and handles mouse
    events for interactive tools like point inspection, line profiles,
    and region selection.

    Signals:
        pointClicked(x, y, row, col, value): Emitted when clicking on map
        profileDrawn(x1, y1, x2, y2): Emitted after drawing line profile
        regionSelected(x1, y1, x2, y2): Emitted after rect selection
        cursorMoved(x, y, row, col, value): Emitted on cursor movement
        toolChanged(toolName): Emitted when tool changes
        mapUpdated(): Emitted after map data changes
    """

    # Signals to QML
    pointClicked = Signal(float, float, int, int, float, arguments=['x', 'y', 'row', 'col', 'value'])
    profileDrawn = Signal(float, float, float, float, arguments=['x1', 'y1', 'x2', 'y2'])
    regionSelected = Signal(float, float, float, float, arguments=['x1', 'y1', 'x2', 'y2'])
    cursorMoved = Signal(float, float, int, int, float, arguments=['x', 'y', 'row', 'col', 'value'])
    toolChanged = Signal(str, arguments=['toolName'])
    mapUpdated = Signal()
    spectralDataRequested = Signal(int, int, arguments=['row', 'col'])

    # Block selection signals (TRANS_v3 style)
    blockSelected = Signal(int, int, float, bool, arguments=['blockRow', 'blockCol', 'value', 'isSelected'])
    blockSelectionChanged = Signal(arguments=[])  # Emitted when selection set changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)

        # Matplotlib setup
        self._dpi = 100
        self.figure = Figure(facecolor='#1a1a1a', dpi=self._dpi)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasAgg(self.figure)

        # Configure axes style
        self.axes.set_facecolor('#1a1a1a')
        self.axes.tick_params(colors='#888888')
        for spine in self.axes.spines.values():
            spine.set_color('#444444')

        # Map data
        self._map_data: Optional[np.ndarray] = None
        self._colormap: str = 'viridis'
        self._vmin: Optional[float] = None
        self._vmax: Optional[float] = None
        self._percentile_clip: Tuple[float, float] = (2, 98)
        self._image_handle = None

        # Tool state
        self._current_tool: MapTool = MapTool.POINTER
        self._is_dragging: bool = False
        self._drag_start: Optional[QPointF] = None
        self._drag_current: Optional[QPointF] = None

        # Overlay elements
        self._show_crosshair: bool = False
        self._crosshair_pos: Optional[Tuple[int, int]] = None
        self._profile_line: Optional[Tuple[QPointF, QPointF]] = None
        self._selection_rect: Optional[QRectF] = None

        # Coordinate transform cache
        self._data_to_pixel: Optional[Dict] = None

        # Render cache
        self._cached_image: Optional[QImage] = None
        self._needs_redraw: bool = True

        # Resize debounce timer — avoids re-rendering matplotlib on every pixel
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)  # ms
        self._resize_timer.timeout.connect(self._onResizeFinished)

        # Block selection state (TRANS_v3 style)
        # For discretized data where each cell represents a spatial block
        self._selected_blocks: set = set()  # Set of (row, col) tuples
        self._block_mode: bool = False  # True when displaying discretized blocks
        self._discretized_data: Optional[np.ndarray] = None  # Discretized (averaged) data
        self._block_size: Optional[Tuple[int, int]] = None  # (block_v, block_h) in original pixels

        # Grid overlay state for discretization
        self._show_grid_overlay: bool = False
        self._grid_block_h: int = 1  # Horizontal block size in pixels
        self._grid_block_v: int = 1  # Vertical block size in pixels
        self._hover_block: Optional[Tuple[int, int]] = None  # Grid block under cursor

        # STS grid region overlay (topography with spectral grid position)
        self._sts_region_rect: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1) in fractional coords

        # Spectral cube link for reconstruction
        self._spectral_cube: Optional[np.ndarray] = None  # Shape: (n_spectral_pts, rows, cols)
        self._independent_var: Optional[np.ndarray] = None  # Wavenumber/voltage axis
        self._independent_var_name: str = "x"

    @Slot()
    def cleanup(self):
        """Release matplotlib resources to prevent memory leaks."""
        try:
            if hasattr(self, '_resize_timer'):
                self._resize_timer.stop()
            if hasattr(self, 'figure') and self.figure is not None:
                self.figure.clear()
                plt.close(self.figure)
                self.figure = None
                self.axes = None
                self.canvas = None
            self._cached_image = None
            logger.debug("MapCanvas cleaned up matplotlib resources")
        except Exception as e:
            logger.warning(f"Error during MapCanvas cleanup: {e}")

    # =========================================================================
    # Properties exposed to QML
    # =========================================================================

    @Property(str, notify=toolChanged)
    def currentTool(self) -> str:
        return self._current_tool.value

    @Property(str)
    def colormap(self) -> str:
        return self._colormap

    @colormap.setter
    def colormap(self, value: str):
        if value != self._colormap:
            self._colormap = value
            self._needs_redraw = True
            self.update()

    @Property(bool)
    def showCrosshair(self) -> bool:
        return self._show_crosshair

    @showCrosshair.setter
    def showCrosshair(self, value: bool):
        self._show_crosshair = value
        self.update()

    @Property(bool)
    def hasData(self) -> bool:
        return self._map_data is not None

    @Property(int)
    def dataRows(self) -> int:
        return self._map_data.shape[0] if self._map_data is not None else 0

    @Property(int)
    def dataCols(self) -> int:
        return self._map_data.shape[1] if self._map_data is not None else 0

    # =========================================================================
    # Slots callable from QML
    # =========================================================================

    @Slot(str)
    def setTool(self, tool_name: str):
        """Set the current active tool"""
        try:
            self._current_tool = MapTool(tool_name)
            self.toolChanged.emit(tool_name)
            self._updateCursor()
            self.update()
        except ValueError:
            logger.warning(f"Unknown tool: {tool_name}")

    @Slot(str)
    def setColormap(self, colormap: str):
        """Set the colormap for the map display"""
        self._colormap = colormap
        self._needs_redraw = True
        self.update()

    @Slot(float, float)
    def setValueRange(self, vmin: float, vmax: float):
        """Set explicit value range for colormap"""
        self._vmin = vmin
        self._vmax = vmax
        self._needs_redraw = True
        self.update()

    @Slot()
    def autoScale(self):
        """Auto-scale using percentile clipping"""
        self._vmin = None
        self._vmax = None
        self._needs_redraw = True
        self.update()

    @Slot()
    def clearOverlays(self):
        """Clear all overlay elements"""
        self._profile_line = None
        self._selection_rect = None
        self._crosshair_pos = None
        self.update()

    @Slot(result='QVariantList')
    def getValueRange(self) -> List[float]:
        """Get current value range [min, max]"""
        if self._map_data is None:
            return [0.0, 1.0]
        if self._vmin is not None and self._vmax is not None:
            return [self._vmin, self._vmax]
        return [
            float(np.nanpercentile(self._map_data, self._percentile_clip[0])),
            float(np.nanpercentile(self._map_data, self._percentile_clip[1]))
        ]

    # =========================================================================
    # Block selection methods (TRANS_v3 style)
    # =========================================================================

    @Slot(int, int)
    def toggleBlockSelection(self, row: int, col: int):
        """Toggle selection state of a block"""
        key = (row, col)
        if key in self._selected_blocks:
            self._selected_blocks.remove(key)
            is_selected = False
        else:
            self._selected_blocks.add(key)
            is_selected = True

        value = self.getValueAt(row, col)
        self.blockSelected.emit(row, col, value, is_selected)
        self.blockSelectionChanged.emit()
        self.update()

    @Slot()
    def clearBlockSelection(self):
        """Clear all block selections"""
        self._selected_blocks.clear()
        self.blockSelectionChanged.emit()
        self.update()

    @Slot()
    def selectAllBlocks(self):
        """Select all blocks"""
        if self._map_data is None:
            return
        for row in range(self._map_data.shape[0]):
            for col in range(self._map_data.shape[1]):
                self._selected_blocks.add((row, col))
        self.blockSelectionChanged.emit()
        self.update()

    @Slot(result=int)
    def getSelectedBlockCount(self) -> int:
        """Get number of selected blocks"""
        return len(self._selected_blocks)

    @Slot(result='QVariantList')
    def getSelectedBlocks(self) -> List[Dict]:
        """Get list of selected blocks with their values"""
        result = []
        for row, col in sorted(self._selected_blocks):
            value = self.getValueAt(row, col)
            result.append({'row': row, 'col': col, 'value': value})
        return result

    def getSelectionMask(self) -> np.ndarray:
        """
        Get 2D boolean mask from selected blocks.
        If in block mode with discretization, expands to original dimensions.
        """
        if self._map_data is None:
            return np.array([])

        rows, cols = self._map_data.shape
        mask = np.zeros((rows, cols), dtype=bool)

        for row, col in self._selected_blocks:
            if 0 <= row < rows and 0 <= col < cols:
                mask[row, col] = True

        # If we have block size info, expand mask to original dimensions
        if self._block_size is not None and self._block_mode:
            block_v, block_h = self._block_size
            orig_rows = rows * block_v
            orig_cols = cols * block_h
            expanded_mask = np.zeros((orig_rows, orig_cols), dtype=bool)

            for row, col in self._selected_blocks:
                r0 = row * block_v
                r1 = min((row + 1) * block_v, orig_rows)
                c0 = col * block_h
                c1 = min((col + 1) * block_h, orig_cols)
                expanded_mask[r0:r1, c0:c1] = True

            return expanded_mask

        return mask

    # =========================================================================
    # Grid Overlay for Discretization
    # =========================================================================

    @Slot(int, int)
    def setGridBlockSize(self, block_h: int, block_v: int):
        """Set grid block size and enable grid overlay."""
        self._grid_block_h = max(1, block_h)
        self._grid_block_v = max(1, block_v)
        self._show_grid_overlay = True
        self._selected_blocks.clear()
        self._hover_block = None
        self._needs_redraw = True
        self.blockSelectionChanged.emit()
        self.update()
        logger.info(f"Grid overlay enabled: block_h={block_h}, block_v={block_v}")

    @Slot(bool)
    def setGridOverlayVisible(self, visible: bool):
        """Show or hide the grid overlay."""
        self._show_grid_overlay = visible
        self.update()

    def setStsRegionRect(self, x0: float, y0: float, x1: float, y1: float):
        """
        Set the STS grid region rectangle overlay in fractional coordinates.

        (x0, y0) and (x1, y1) are opposite corners, each in [0,1] range
        relative to the map data extents.
        """
        self._sts_region_rect = (x0, y0, x1, y1)
        self._needs_redraw = True
        self.update()

    def clearStsRegionRect(self):
        """Remove the STS grid region rectangle overlay."""
        self._sts_region_rect = None
        self.update()

    @Slot()
    def clearGridOverlay(self):
        """Remove grid overlay and reset grid state."""
        self._show_grid_overlay = False
        self._grid_block_h = 1
        self._grid_block_v = 1
        self._hover_block = None
        self._selected_blocks.clear()
        self.blockSelectionChanged.emit()
        self.update()

    def _pixelToGridBlock(self, x: float, y: float) -> Tuple[int, int]:
        """Convert pixel coordinates to grid block (grid_row, grid_col)."""
        row, col = self._pixelToData(x, y)
        if self._grid_block_h > 1 or self._grid_block_v > 1:
            grid_col = col // self._grid_block_h
            grid_row = row // self._grid_block_v
            return grid_row, grid_col
        return row, col

    # =========================================================================
    # Spectral-Spatial Reconstruction (TRANS_v3 core feature)
    # =========================================================================

    def linkSpectralCube(self,
                         cube: np.ndarray,
                         independent_var: np.ndarray,
                         independent_var_name: str = "x"):
        """
        Link a spectral cube for spatial-spectral reconstruction.
        Clicking on a position will retrieve the spectrum at that location.

        Parameters:
            cube: 3D array with shape (n_spectral_points, rows, cols)
            independent_var: 1D array (e.g., wavenumber, voltage)
            independent_var_name: Label for independent variable
        """
        if cube.ndim != 3:
            raise ValueError(f"Spectral cube must be 3D, got {cube.ndim}D")

        self._spectral_cube = cube
        self._independent_var = independent_var
        self._independent_var_name = independent_var_name
        logger.info(f"Linked spectral cube: {cube.shape}")

    def unlinkSpectralCube(self):
        """Remove spectral cube link"""
        self._spectral_cube = None
        self._independent_var = None

    @Slot(int, int, result='QVariantMap')
    def getSpectrumAt(self, row: int, col: int) -> Dict:
        """
        Get spectrum at a specific spatial position.
        This is the core spatial-spectral reconstruction feature from TRANS_v3.

        Parameters:
            row: Row index
            col: Column index

        Returns:
            Dict with 'x' (independent var), 'y' (values), 'name' labels
        """
        if self._spectral_cube is None:
            return {'error': 'No spectral data linked'}

        n_pts, n_rows, n_cols = self._spectral_cube.shape

        if not (0 <= row < n_rows and 0 <= col < n_cols):
            return {'error': f'Position ({row}, {col}) out of bounds'}

        values = self._spectral_cube[:, row, col]

        return {
            'x': self._independent_var.tolist() if self._independent_var is not None else list(range(n_pts)),
            'y': values.tolist(),
            'x_name': self._independent_var_name,
            'y_name': 'Intensity',
            'title': f'Spectrum at ({row}, {col})'
        }

    @Slot(result='QVariantMap')
    def getAverageSpectrumFromSelection(self) -> Dict:
        """
        Get average spectrum from all selected blocks.
        Key feature for discretized spatial averaging.
        """
        if self._spectral_cube is None:
            return {'error': 'No spectral data linked'}

        if not self._selected_blocks:
            return {'error': 'No blocks selected'}

        n_pts = self._spectral_cube.shape[0]
        accumulated = np.zeros(n_pts)
        count = 0

        for row, col in self._selected_blocks:
            if 0 <= row < self._spectral_cube.shape[1] and 0 <= col < self._spectral_cube.shape[2]:
                accumulated += self._spectral_cube[:, row, col]
                count += 1

        if count == 0:
            return {'error': 'No valid blocks in selection'}

        averaged = accumulated / count

        return {
            'x': self._independent_var.tolist() if self._independent_var is not None else list(range(n_pts)),
            'y': averaged.tolist(),
            'x_name': self._independent_var_name,
            'y_name': 'Intensity',
            'title': f'Average spectrum ({count} blocks)',
            'block_count': count
        }

    @Property(bool)
    def hasSpectralLink(self) -> bool:
        """Check if spectral data is linked"""
        return self._spectral_cube is not None

    @Property(int)
    def spectralPoints(self) -> int:
        """Get number of spectral points"""
        return self._spectral_cube.shape[0] if self._spectral_cube is not None else 0

    # =========================================================================
    # Data management (called from Python backend)
    # =========================================================================

    def setMapData(self, data: np.ndarray, colormap: str = None):
        """
        Set the map data to display.

        Parameters:
            data: 2D numpy array
            colormap: Optional colormap name
        """
        if data.ndim != 2:
            raise ValueError(f"Map data must be 2D, got {data.ndim}D")

        self._map_data = data.astype(np.float64)
        if colormap:
            self._colormap = colormap

        self._needs_redraw = True
        self._data_to_pixel = None  # Invalidate transform cache
        self.mapUpdated.emit()
        self.update()

    def getMapData(self) -> Optional[np.ndarray]:
        """Get the current map data"""
        return self._map_data

    def getValueAt(self, row: int, col: int) -> float:
        """Get map value at specific position"""
        if self._map_data is None:
            return np.nan
        if 0 <= row < self._map_data.shape[0] and 0 <= col < self._map_data.shape[1]:
            return float(self._map_data[row, col])
        return np.nan

    # =========================================================================
    # Painting
    # =========================================================================

    def paint(self, painter: QPainter):
        """Render matplotlib figure and overlays to QML"""
        if self._needs_redraw:
            self._renderMatplotlib()
            self._needs_redraw = False

        if self._cached_image is not None:
            # Draw the matplotlib image
            target_rect = QRectF(0, 0, self.width(), self.height())
            painter.drawImage(target_rect, self._cached_image)

            # Draw overlays on top
            self._drawOverlays(painter)

    def _renderMatplotlib(self):
        """Render matplotlib figure to cached QImage"""
        if self._map_data is None:
            self._cached_image = None
            return

        # Resize figure to match item size
        w, h = int(self.width()), int(self.height())
        if w <= 0 or h <= 0:
            return

        self.figure.set_size_inches(w / self._dpi, h / self._dpi)

        # Clear and redraw
        self.axes.clear()
        self.axes.set_facecolor('#1a1a1a')

        # Compute value range
        if self._vmin is not None and self._vmax is not None:
            vmin, vmax = self._vmin, self._vmax
        else:
            vmin = np.nanpercentile(self._map_data, self._percentile_clip[0])
            vmax = np.nanpercentile(self._map_data, self._percentile_clip[1])

        # Display image
        self._image_handle = self.axes.imshow(
            self._map_data,
            cmap=self._colormap,
            vmin=vmin,
            vmax=vmax,
            aspect='equal',
            origin='upper',
            interpolation='nearest'
        )

        # Style axes
        self.axes.tick_params(colors='#888888', labelsize=8)
        for spine in self.axes.spines.values():
            spine.set_color('#444444')

        # Tight layout
        self.figure.tight_layout(pad=0.5)

        # Render to buffer
        self.canvas.draw()
        buf = self.canvas.buffer_rgba()
        w_fig, h_fig = self.canvas.get_width_height()

        # Convert to QImage
        self._cached_image = QImage(
            buf, w_fig, h_fig, QImage.Format_RGBA8888
        ).copy()  # Make a copy since buffer may be reused

        # Update coordinate transform
        self._updateCoordinateTransform()

    def _updateCoordinateTransform(self):
        """Update pixel-to-data coordinate transformation"""
        if self._map_data is None or self._image_handle is None:
            self._data_to_pixel = None
            return

        # Get axes position in figure coordinates
        bbox = self.axes.get_position()
        fig_w, fig_h = self.canvas.get_width_height()

        # Axes bounds in pixels
        ax_left = bbox.x0 * fig_w
        ax_right = bbox.x1 * fig_w
        ax_top = (1 - bbox.y1) * fig_h
        ax_bottom = (1 - bbox.y0) * fig_h

        self._data_to_pixel = {
            'ax_left': ax_left,
            'ax_right': ax_right,
            'ax_top': ax_top,
            'ax_bottom': ax_bottom,
            'data_rows': self._map_data.shape[0],
            'data_cols': self._map_data.shape[1]
        }

    def _pixelToData(self, x: float, y: float) -> Tuple[int, int]:
        """Convert pixel coordinates to data row, col"""
        if self._data_to_pixel is None:
            return -1, -1

        d = self._data_to_pixel
        ax_width = d['ax_right'] - d['ax_left']
        ax_height = d['ax_bottom'] - d['ax_top']

        # Normalize to [0, 1] within axes
        norm_x = (x - d['ax_left']) / ax_width
        norm_y = (y - d['ax_top']) / ax_height

        # Convert to data coordinates
        col = int(norm_x * d['data_cols'])
        row = int(norm_y * d['data_rows'])

        # Clamp to valid range
        row = max(0, min(row, d['data_rows'] - 1))
        col = max(0, min(col, d['data_cols'] - 1))

        return row, col

    def _dataToPixel(self, row: int, col: int) -> Tuple[float, float]:
        """Convert data row, col to pixel coordinates"""
        if self._data_to_pixel is None:
            return 0, 0

        d = self._data_to_pixel
        ax_width = d['ax_right'] - d['ax_left']
        ax_height = d['ax_bottom'] - d['ax_top']

        x = d['ax_left'] + (col + 0.5) / d['data_cols'] * ax_width
        y = d['ax_top'] + (row + 0.5) / d['data_rows'] * ax_height

        return x, y

    def _drawOverlays(self, painter: QPainter):
        """Draw interactive overlay elements"""
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw STS grid region rectangle overlay
        if self._sts_region_rect and self._data_to_pixel is not None:
            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']
            x0, y0, x1, y1 = self._sts_region_rect

            # Convert fractional coords to pixel coords
            px_left = d['ax_left'] + min(x0, x1) * ax_width
            px_right = d['ax_left'] + max(x0, x1) * ax_width
            px_top = d['ax_top'] + min(y0, y1) * ax_height
            px_bottom = d['ax_top'] + max(y0, y1) * ax_height

            # Semi-transparent red fill
            painter.setBrush(QColor(245, 169, 184, 50))
            pen = QPen(QColor(245, 169, 184, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(
                int(px_left), int(px_top),
                int(px_right - px_left), int(px_bottom - px_top)
            )

        # Draw grid overlay for discretization
        if self._show_grid_overlay and self._data_to_pixel is not None and self._map_data is not None:
            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']
            data_rows, data_cols = d['data_rows'], d['data_cols']

            # Draw semi-transparent white grid lines
            pen = QPen(QColor(255, 255, 255, 100))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            # Vertical grid lines
            for gc in range(1, (data_cols // self._grid_block_h) + 1):
                px = gc * self._grid_block_h
                if px < data_cols:
                    x = d['ax_left'] + (px / data_cols) * ax_width
                    painter.drawLine(int(x), int(d['ax_top']), int(x), int(d['ax_bottom']))

            # Horizontal grid lines
            for gr in range(1, (data_rows // self._grid_block_v) + 1):
                py = gr * self._grid_block_v
                if py < data_rows:
                    y = d['ax_top'] + (py / data_rows) * ax_height
                    painter.drawLine(int(d['ax_left']), int(y), int(d['ax_right']), int(y))

            # Draw hover highlight on grid block
            if self._hover_block is not None and self._current_tool == MapTool.BLOCK_SELECT:
                hr, hc = self._hover_block
                cell_w = (self._grid_block_h / data_cols) * ax_width
                cell_h = (self._grid_block_v / data_rows) * ax_height
                rect_x = d['ax_left'] + hc * self._grid_block_h / data_cols * ax_width
                rect_y = d['ax_top'] + hr * self._grid_block_v / data_rows * ax_height
                painter.setPen(QPen(QColor(245, 169, 184, 180)))  # Pink hover
                painter.setBrush(QBrush(QColor(245, 169, 184, 50)))
                painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))

        # Draw selected blocks (TRANS_v3 style blue highlight)
        if self._selected_blocks and self._data_to_pixel is not None:
            pen = QPen(QColor(31, 119, 180, 200))  # Blue from TRANS_v3 (#1f77b4)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(31, 119, 180, 80)))

            d = self._data_to_pixel
            ax_width = d['ax_right'] - d['ax_left']
            ax_height = d['ax_bottom'] - d['ax_top']

            if self._show_grid_overlay and (self._grid_block_h > 1 or self._grid_block_v > 1):
                # Grid-snapped block selection
                cell_w = (self._grid_block_h / d['data_cols']) * ax_width
                cell_h = (self._grid_block_v / d['data_rows']) * ax_height
                for row, col in self._selected_blocks:
                    rect_x = d['ax_left'] + col * self._grid_block_h / d['data_cols'] * ax_width
                    rect_y = d['ax_top'] + row * self._grid_block_v / d['data_rows'] * ax_height
                    painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))
            else:
                # Per-pixel block selection
                cell_w = ax_width / d['data_cols']
                cell_h = ax_height / d['data_rows']
                for row, col in self._selected_blocks:
                    rect_x = d['ax_left'] + col * cell_w
                    rect_y = d['ax_top'] + row * cell_h
                    painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))

        # Draw crosshair
        if self._show_crosshair and self._crosshair_pos is not None:
            row, col = self._crosshair_pos
            x, y = self._dataToPixel(row, col)

            pen = QPen(QColor(255, 255, 0, 180))
            pen.setWidth(1)
            painter.setPen(pen)

            # Vertical line
            painter.drawLine(int(x), 0, int(x), int(self.height()))
            # Horizontal line
            painter.drawLine(0, int(y), int(self.width()), int(y))

        # Draw profile line
        if self._profile_line is not None:
            start, end = self._profile_line
            pen = QPen(QColor(255, 100, 100, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(start, end)

            # Draw endpoints
            painter.setBrush(QBrush(QColor(255, 100, 100)))
            painter.drawEllipse(start, 4, 4)
            painter.drawEllipse(end, 4, 4)

        # Draw selection rectangle
        if self._selection_rect is not None:
            pen = QPen(QColor(100, 200, 255, 200))
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(100, 200, 255, 50)))
            painter.drawRect(self._selection_rect)

        # Draw drag preview for current tool
        if self._is_dragging and self._drag_start and self._drag_current:
            if self._current_tool == MapTool.LINE_PROFILE:
                pen = QPen(QColor(255, 200, 100, 200))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(self._drag_start, self._drag_current)
            elif self._current_tool in (MapTool.RECT_SELECT, MapTool.ZOOM_RECT):
                rect = QRectF(self._drag_start, self._drag_current).normalized()
                pen = QPen(QColor(100, 255, 100, 200))
                pen.setWidth(1)
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(100, 255, 100, 30)))
                painter.drawRect(rect)

    def _updateCursor(self):
        """Update cursor based on current tool"""
        cursor_map = {
            MapTool.POINTER: Qt.ArrowCursor,
            MapTool.ZOOM_RECT: Qt.CrossCursor,
            MapTool.PAN: Qt.OpenHandCursor,
            MapTool.LINE_PROFILE: Qt.CrossCursor,
            MapTool.POINT_INSPECTOR: Qt.CrossCursor,
            MapTool.RECT_SELECT: Qt.CrossCursor,
            MapTool.MEASURE: Qt.CrossCursor,
            MapTool.CROSSHAIR: Qt.BlankCursor,
            MapTool.BLOCK_SELECT: Qt.PointingHandCursor,
        }
        self.setCursor(QCursor(cursor_map.get(self._current_tool, Qt.ArrowCursor)))

    # =========================================================================
    # Mouse event handling
    # =========================================================================

    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if self._map_data is None:
            return

        pos = event.position()
        self._drag_start = pos
        self._is_dragging = True

        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        if self._current_tool == MapTool.POINT_INSPECTOR:
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)
            self._crosshair_pos = (row, col)
            self.update()

        elif self._current_tool == MapTool.CROSSHAIR:
            self._crosshair_pos = (row, col)
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.update()

        elif self._current_tool == MapTool.BLOCK_SELECT:
            # TRANS_v3 style block selection - toggle on click
            # Snap to grid if grid overlay is active
            if self._show_grid_overlay and (self._grid_block_h > 1 or self._grid_block_v > 1):
                grid_row, grid_col = self._pixelToGridBlock(pos.x(), pos.y())
                self.toggleBlockSelection(grid_row, grid_col)
            else:
                self.toggleBlockSelection(row, col)
            # Also emit point clicked for spectrum display
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)

        elif self._current_tool == MapTool.POINTER:
            # Default pointer: emit click and show spectrum
            self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
            self.spectralDataRequested.emit(row, col)

    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        if self._map_data is None:
            return

        pos = event.position()
        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        # Emit cursor position
        self.cursorMoved.emit(pos.x(), pos.y(), row, col, value)

        if self._is_dragging:
            self._drag_current = pos

            if self._current_tool == MapTool.CROSSHAIR:
                self._crosshair_pos = (row, col)
                self.pointClicked.emit(pos.x(), pos.y(), row, col, value)

            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        if not self._is_dragging or self._drag_start is None:
            return

        pos = event.position()
        self._is_dragging = False

        if self._current_tool == MapTool.LINE_PROFILE:
            # Store profile line for display
            self._profile_line = (self._drag_start, pos)
            self.profileDrawn.emit(
                self._drag_start.x(), self._drag_start.y(),
                pos.x(), pos.y()
            )

        elif self._current_tool in (MapTool.RECT_SELECT, MapTool.ZOOM_RECT):
            rect = QRectF(self._drag_start, pos).normalized()
            if self._current_tool == MapTool.RECT_SELECT:
                self._selection_rect = rect
            self.regionSelected.emit(rect.x(), rect.y(),
                                    rect.x() + rect.width(),
                                    rect.y() + rect.height())

        self._drag_start = None
        self._drag_current = None
        self.update()

    def hoverMoveEvent(self, event):
        """Handle hover move events (when not pressing)"""
        if self._map_data is None:
            return

        pos = event.position()
        row, col = self._pixelToData(pos.x(), pos.y())
        value = self.getValueAt(row, col)

        self.cursorMoved.emit(pos.x(), pos.y(), row, col, value)

        if self._current_tool == MapTool.CROSSHAIR:
            self._crosshair_pos = (row, col)
            self.update()

        # Track hover block for grid overlay highlight
        if self._show_grid_overlay and self._current_tool == MapTool.BLOCK_SELECT:
            new_hover = self._pixelToGridBlock(pos.x(), pos.y())
            if new_hover != self._hover_block:
                self._hover_block = new_hover
                self.update()

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        # TODO: Implement zoom
        pass

    # =========================================================================
    # Geometry change handling
    # =========================================================================

    def geometryChange(self, newGeometry, oldGeometry):
        """Handle resize with debouncing — scale cached image during drag, re-render when done."""
        super().geometryChange(newGeometry, oldGeometry)
        if newGeometry.size() != oldGeometry.size():
            # During resize: just repaint with the existing cached image (scaled by Qt)
            self.update()
            # Restart debounce timer — full re-render happens when resizing stops
            self._resize_timer.start()

    def _onResizeFinished(self):
        """Called after resize stops (debounce). Triggers full matplotlib re-render."""
        self._needs_redraw = True
        self.update()

    # =========================================================================
    # Statistics and Export (for docked viewer)
    # =========================================================================

    @Slot(result='QVariantMap')
    def getStatistics(self) -> Dict:
        """Get statistics of the current map data"""
        if self._map_data is None:
            return {}

        data = self._map_data
        return {
            'min': float(np.nanmin(data)),
            'max': float(np.nanmax(data)),
            'mean': float(np.nanmean(data)),
            'std': float(np.nanstd(data)),
            'median': float(np.nanmedian(data)),
            'rows': data.shape[0],
            'cols': data.shape[1]
        }

    @Slot(float, float)
    def setColorLimits(self, vmin: float, vmax: float):
        """Set color scale limits"""
        self._vmin = vmin
        self._vmax = vmax
        self._needs_redraw = True
        self.update()

    @Slot(str, str, result=bool)
    def exportImage(self, path: str, format: str = 'png') -> bool:
        """Export the current map view as an image"""
        try:
            if self._cached_image is None:
                return False

            # Export matplotlib figure
            self.figure.savefig(
                path,
                dpi=300,
                bbox_inches='tight',
                facecolor='#0d0d0d',
                edgecolor='none'
            )
            logger.info(f"Map exported to: {path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting map image: {e}")
            return False

    @Slot(str, result=bool)
    def exportCsv(self, path: str) -> bool:
        """Export the map data as CSV"""
        try:
            if self._map_data is None:
                return False

            import pandas as pd
            df = pd.DataFrame(self._map_data)
            df.to_csv(path, index=False, header=False)
            logger.info(f"Map data exported to CSV: {path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return False

    @Slot(str, result=bool)
    def saveMapData(self, path: str) -> bool:
        """Save the current map data to file"""
        try:
            if self._map_data is None:
                return False

            from pathlib import Path
            p = Path(path)
            ext = p.suffix.lower()

            if ext in ['.tif', '.tiff']:
                import tifffile
                tifffile.imwrite(str(p), self._map_data.astype(np.float32))
            elif ext == '.npy':
                np.save(str(p), self._map_data)
            elif ext == '.csv':
                import pandas as pd
                df = pd.DataFrame(self._map_data)
                df.to_csv(str(p), index=False, header=False)
            else:
                # Default to numpy
                np.save(str(p.with_suffix('.npy')), self._map_data)

            logger.info(f"Map data saved to: {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving map data: {e}")
            return False
