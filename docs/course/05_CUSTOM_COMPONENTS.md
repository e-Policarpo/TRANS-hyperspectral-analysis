# Module 5: Custom QML Components with Python

## Building High-Performance Visualization Widgets

In this module, you'll learn how to create custom QML components using Python's `QQuickPaintedItem`. This is essential for scientific applications that need to render complex visualizations like graphs, maps, and spectral data that QML's built-in components can't handle efficiently.

---

## Learning Objectives

By the end of this module, you will be able to:
- Create custom QML items using `QQuickPaintedItem`
- Integrate matplotlib with QML for publication-quality rendering
- Handle mouse events and implement coordinate transformations
- Build interactive visualization widgets with overlays
- Manage render caching for smooth performance

---

## 5.1 Understanding QQuickPaintedItem

### Why Custom Components?

QML provides excellent built-in components for UI elements, but scientific applications often need:
- **Complex 2D plots** with multiple curves, axes, legends
- **Image displays** with colormaps and overlays
- **Interactive tools** like zoom, pan, selection
- **Publication-quality** rendering with matplotlib

`QQuickPaintedItem` solves this by allowing you to paint arbitrary content using QPainter, which integrates seamlessly with matplotlib's Agg backend.

### The Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    QML Scene Graph                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────────────────────────────────────────────┐  │
│   │           QQuickPaintedItem (Python)             │  │
│   │  ┌────────────────────────────────────────────┐  │  │
│   │  │            Matplotlib Figure              │  │  │
│   │  │  ┌──────────────────────────────────────┐  │  │  │
│   │  │  │        FigureCanvasAgg               │  │  │  │
│   │  │  │     (Renders to RGBA buffer)         │  │  │  │
│   │  │  └──────────────────────────────────────┘  │  │  │
│   │  └────────────────────────────────────────────┘  │  │
│   │                     ↓                            │  │
│   │           QImage (cached frame)                  │  │
│   │                     ↓                            │  │
│   │   paint(QPainter) → drawImage() + overlays       │  │
│   └──────────────────────────────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Basic Structure

```python
from PySide6.QtCore import Qt, Signal, Slot, Property
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickPaintedItem

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg


class MyCustomCanvas(QQuickPaintedItem):
    """Base pattern for matplotlib-QML integration"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Enable mouse events
        self.setAcceptedMouseButtons(Qt.AllButtons)
        self.setAcceptHoverEvents(True)
        self.setFlag(QQuickPaintedItem.ItemHasContents, True)

        # 2. Create matplotlib figure
        self._dpi = 100
        self.figure = Figure(facecolor='#1a1a1a', dpi=self._dpi)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasAgg(self.figure)

        # 3. Render cache
        self._cached_image = None
        self._needs_redraw = True
        self._component_complete = False

    def componentComplete(self):
        """Called when QML component is fully constructed"""
        super().componentComplete()
        self._component_complete = True
        self._needs_redraw = True
        self.update()

    def paint(self, painter):
        """Main paint method - called by QML"""
        if not self._component_complete:
            return

        if self._needs_redraw:
            self._renderMatplotlib()
            self._needs_redraw = False

        if self._cached_image is not None:
            painter.drawImage(0, 0, self._cached_image)
```

**Key Points:**
1. **ItemHasContents flag** - Required for custom painting
2. **componentComplete()** - Wait until QML finishes construction
3. **Render cache** - Avoid re-rendering unless data changes
4. **update()** - Schedules a repaint

---

## 5.2 The Render Pipeline

### Step 1: Rendering to Buffer

```python
def _renderMatplotlib(self):
    """Render matplotlib figure to cached QImage"""
    w, h = int(self.width()), int(self.height())
    if w <= 0 or h <= 0:
        return

    # Match figure size to widget size
    # figure_size_inches * dpi = pixels
    self.figure.set_size_inches(w / self._dpi, h / self._dpi)

    # Clear and draw
    self.axes.clear()
    self._setupAxesStyle()
    self._drawContent()  # Your custom drawing code

    self.figure.tight_layout(pad=0.5)

    # Render to RGBA buffer
    self.canvas.draw()
    buf = self.canvas.buffer_rgba()
    w_fig, h_fig = self.canvas.get_width_height()

    # Convert to QImage (MUST copy - buffer is reused)
    self._cached_image = QImage(
        buf, w_fig, h_fig, QImage.Format_RGBA8888
    ).copy()
```

**Critical:** Always call `.copy()` on the QImage - matplotlib reuses the buffer!

### Step 2: Painting with Overlays

```python
def paint(self, painter):
    """Render cached image plus interactive overlays"""
    if not self._component_complete:
        return

    if self._needs_redraw:
        self._renderMatplotlib()
        self._needs_redraw = False

    if self._cached_image is not None:
        # Draw the matplotlib rendering
        target_rect = QRectF(0, 0, self.width(), self.height())
        painter.drawImage(target_rect, self._cached_image)

        # Draw interactive overlays on top
        self._drawOverlays(painter)
```

### Step 3: Drawing Overlays

Overlays are drawn in screen coordinates, on top of the matplotlib image:

```python
def _drawOverlays(self, painter):
    """Draw interactive elements like cursors and selections"""
    painter.setRenderHint(QPainter.Antialiasing, True)

    # Example: Draw crosshair cursor
    if self._show_crosshair and self._cursor_pos:
        pen = QPen(QColor(255, 255, 0, 180))
        pen.setWidth(1)
        painter.setPen(pen)

        x, y = self._cursor_pos
        painter.drawLine(int(x), 0, int(x), int(self.height()))
        painter.drawLine(0, int(y), int(self.width()), int(y))

    # Example: Draw selection rectangle
    if self._selection_rect:
        pen = QPen(QColor(100, 200, 255, 200))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(100, 200, 255, 50)))
        painter.drawRect(self._selection_rect)
```

---

## 5.3 Real-World Example: QMLProfileCanvas

Let's examine `src/widgets/qml_profile_canvas.py`, a line-plotting widget:

### Class Definition and Initialization

```python
class QMLProfileCanvas(QQuickPaintedItem):
    """
    Matplotlib canvas for plotting line profiles and spectra in QML.

    Signals:
        cursorMoved(x, y): Emitted when cursor moves over plot
        pointClicked(x, y): Emitted on click
        rangeSelected(x1, x2): Emitted after range selection
    """

    # Signals to QML
    cursorMoved = Signal(float, float, arguments=['x', 'y'])
    pointClicked = Signal(float, float, arguments=['x', 'y'])
    rangeSelected = Signal(float, float, arguments=['x1', 'x2'])
    dataChanged = Signal()

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

        # Style axes
        self._setupAxesStyle()

        # Data storage
        self._x_data = None
        self._y_data = None
        self._x_label = "Distance"
        self._y_label = "Value"

        # Multiple curves support
        self._curves = []

        # Display options
        self._line_color = '#ff6b6b'
        self._show_grid = True

        # Render cache
        self._cached_image = None
        self._needs_redraw = True
```

### Properties for QML Binding

```python
@Property(str)
def lineColor(self) -> str:
    return self._line_color

@lineColor.setter
def lineColor(self, value: str):
    if value != self._line_color:
        self._line_color = value
        self._needs_redraw = True  # Mark for redraw
        self.update()              # Schedule repaint

@Property(bool)
def hasData(self) -> bool:
    return self._x_data is not None and self._y_data is not None
```

### Slots for QML Interaction

```python
@Slot(list, list)
def setProfileData(self, x_data, y_data):
    """Set profile data from QML"""
    self._x_data = np.array(x_data, dtype=np.float64)
    self._y_data = np.array(y_data, dtype=np.float64)
    self._needs_redraw = True
    self.dataChanged.emit()
    self.update()

@Slot(str, list, list, str)
def addCurve(self, name, x_data, y_data, color=""):
    """Add overlay curve"""
    curve = {
        'name': name,
        'x': np.array(x_data, dtype=np.float64),
        'y': np.array(y_data, dtype=np.float64),
        'color': color or self._getNextColor(len(self._curves))
    }
    self._curves.append(curve)
    self._needs_redraw = True
    self.update()
```

### Rendering the Plot

```python
def _renderMatplotlib(self):
    """Render matplotlib figure to cached QImage"""
    w, h = int(self.width()), int(self.height())
    if w <= 0 or h <= 0:
        return

    self.figure.set_size_inches(w / self._dpi, h / self._dpi)

    # Clear and configure
    self.axes.clear()
    self._setupAxesStyle()

    # Plot main data
    if self._x_data is not None and self._y_data is not None:
        self.axes.plot(
            self._x_data, self._y_data,
            color=self._line_color,
            linewidth=1.5,
            label='Profile'
        )

    # Plot additional curves
    for curve in self._curves:
        self.axes.plot(
            curve['x'], curve['y'],
            color=curve['color'],
            linewidth=1.5,
            label=curve['name'],
            alpha=0.8
        )

    # Configure axes
    if self._show_grid:
        self.axes.grid(True, color='#333333', alpha=0.5)

    self.axes.set_xlabel(self._x_label, fontsize=9)
    self.axes.set_ylabel(self._y_label, fontsize=9)

    # Legend if multiple curves
    if self._curves:
        self.axes.legend(loc='upper right', fontsize=8,
                        facecolor='#2a2a2a', labelcolor='#cccccc')

    self.figure.tight_layout(pad=0.5)

    # Render to buffer
    self.canvas.draw()
    buf = self.canvas.buffer_rgba()
    w_fig, h_fig = self.canvas.get_width_height()

    self._cached_image = QImage(
        buf, w_fig, h_fig, QImage.Format_RGBA8888
    ).copy()
```

---

## 5.4 Coordinate Transformations

A critical skill for interactive widgets is converting between:
- **Pixel coordinates** (mouse position)
- **Data coordinates** (the values you're plotting)

### Building the Transform

After rendering, cache the coordinate mapping:

```python
def _updateDataBounds(self):
    """Update pixel-to-data coordinate mapping"""
    if self._x_data is None:
        self._data_bounds = None
        return

    # Get axes bounding box in figure coordinates
    bbox = self.axes.get_position()
    fig_w, fig_h = self.canvas.get_width_height()

    # Get data limits
    xlim = self.axes.get_xlim()
    ylim = self.axes.get_ylim()

    # Store mapping info
    self._data_bounds = {
        'ax_left': bbox.x0 * fig_w,      # Axes left edge in pixels
        'ax_right': bbox.x1 * fig_w,     # Axes right edge in pixels
        'ax_top': (1 - bbox.y1) * fig_h, # Axes top (inverted)
        'ax_bottom': (1 - bbox.y0) * fig_h,
        'x_min': xlim[0],  # Data x minimum
        'x_max': xlim[1],  # Data x maximum
        'y_min': ylim[0],  # Data y minimum
        'y_max': ylim[1]   # Data y maximum
    }
```

### Pixel to Data Conversion

```python
def _pixelToData(self, px, py):
    """Convert pixel coordinates to data coordinates"""
    if self._data_bounds is None:
        return 0, 0

    d = self._data_bounds
    ax_width = d['ax_right'] - d['ax_left']
    ax_height = d['ax_bottom'] - d['ax_top']

    # Normalize to [0, 1] within axes area
    norm_x = (px - d['ax_left']) / ax_width
    norm_y = (py - d['ax_top']) / ax_height

    # Map to data coordinates
    x = d['x_min'] + norm_x * (d['x_max'] - d['x_min'])
    y = d['y_max'] - norm_y * (d['y_max'] - d['y_min'])  # Y inverted

    return x, y
```

### Data to Pixel Conversion

```python
def _dataToPixel(self, data_x, data_y):
    """Convert data coordinates to pixel coordinates"""
    if self._data_bounds is None:
        return 0, 0

    d = self._data_bounds
    ax_width = d['ax_right'] - d['ax_left']
    ax_height = d['ax_bottom'] - d['ax_top']

    # Normalize data to [0, 1]
    norm_x = (data_x - d['x_min']) / (d['x_max'] - d['x_min'])
    norm_y = (d['y_max'] - data_y) / (d['y_max'] - d['y_min'])

    # Map to pixel coordinates
    px = d['ax_left'] + norm_x * ax_width
    py = d['ax_top'] + norm_y * ax_height

    return px, py
```

### Diagram: Coordinate Systems

```
Pixel Coordinates (origin top-left)    Data Coordinates (axes system)

(0,0)───────────────► X                     ▲ Y
  │                                         │
  │  ┌──────────────────┐                   │
  │  │ ax_top           │                   │ y_max
  │  │   ┌──────────┐   │                   │   ┌──────────┐
  │  │   │  AXES    │   │    ←→             │   │  AXES    │
  │  │   │  AREA    │   │                   │   │  AREA    │
  │  │   └──────────┘   │                   │   └──────────┘
  │  │ ax_bottom        │                   │ y_min
  │  └──────────────────┘                   │
  ▼                                         └────────────────► X
  Y                                        x_min          x_max
```

---

## 5.5 Mouse Event Handling

### Event Types

`QQuickPaintedItem` provides these mouse-related methods:

| Method | Description |
|--------|-------------|
| `mousePressEvent` | Button pressed |
| `mouseMoveEvent` | Mouse moved while button pressed |
| `mouseReleaseEvent` | Button released |
| `hoverMoveEvent` | Mouse moved without button |
| `hoverEnterEvent` | Mouse entered widget |
| `hoverLeaveEvent` | Mouse left widget |
| `wheelEvent` | Scroll wheel |

### Implementation Pattern

```python
def mousePressEvent(self, event):
    """Handle mouse press"""
    pos = event.position()  # QPointF
    x, y = self._pixelToData(pos.x(), pos.y())

    if event.button() == Qt.LeftButton:
        self.pointClicked.emit(x, y)

        # Start range selection
        self._is_selecting = True
        self._selection_start = x
        self._selection_end = x

    elif event.button() == Qt.RightButton:
        # Context action (e.g., reset zoom)
        self._resetView()

def mouseMoveEvent(self, event):
    """Handle mouse move (while pressing)"""
    pos = event.position()
    x, y = self._pixelToData(pos.x(), pos.y())

    self.cursorMoved.emit(x, y)
    self._cursor_x = x

    if self._is_selecting:
        self._selection_end = x
        self.update()  # Redraw to show selection

def mouseReleaseEvent(self, event):
    """Handle mouse release"""
    if self._is_selecting:
        if self._selection_start != self._selection_end:
            x1 = min(self._selection_start, self._selection_end)
            x2 = max(self._selection_start, self._selection_end)
            self.rangeSelected.emit(x1, x2)

        self._is_selecting = False
        self._selection_start = None
        self._selection_end = None
        self.update()

def hoverMoveEvent(self, event):
    """Handle hover (no button pressed)"""
    pos = event.position()
    x, y = self._pixelToData(pos.x(), pos.y())

    self.cursorMoved.emit(x, y)
    self._cursor_x = x
    self._show_cursor = True
    self.update()

def hoverLeaveEvent(self, event):
    """Handle mouse leaving widget"""
    self._show_cursor = False
    self.update()
```

### Zoom with Wheel

```python
def wheelEvent(self, event):
    """Handle scroll wheel for zoom"""
    delta = event.angleDelta().y()
    factor = 1.1 if delta > 0 else 0.9

    # Get mouse position in data coords
    pos = event.position()
    center_x, center_y = self._pixelToData(pos.x(), pos.y())

    # Zoom around mouse position
    self._zoomAroundPoint(center_x, center_y, factor)

    self._needs_redraw = True
    self.update()
```

---

## 5.6 Advanced Example: QMLMapCanvas

`src/widgets/qml_map_canvas.py` demonstrates a complete 2D map visualization with tools:

### Tool System

```python
from enum import Enum

class MapTool(Enum):
    """Available map editing tools"""
    POINTER = "pointer"
    ZOOM_RECT = "zoom_rect"
    PAN = "pan"
    LINE_PROFILE = "line_profile"
    POINT_INSPECTOR = "point_inspector"
    RECT_SELECT = "rect_select"
    BLOCK_SELECT = "block_select"  # For discretized data
```

### Tool Selection from QML

```python
@Slot(str)
def setTool(self, tool_name):
    """Set the current active tool"""
    try:
        self._current_tool = MapTool(tool_name)
        self.toolChanged.emit(tool_name)
        self._updateCursor()
        self.update()
    except ValueError:
        logger.warning(f"Unknown tool: {tool_name}")

def _updateCursor(self):
    """Update cursor based on current tool"""
    cursor_map = {
        MapTool.POINTER: Qt.ArrowCursor,
        MapTool.ZOOM_RECT: Qt.CrossCursor,
        MapTool.PAN: Qt.OpenHandCursor,
        MapTool.LINE_PROFILE: Qt.CrossCursor,
        MapTool.POINT_INSPECTOR: Qt.CrossCursor,
        MapTool.BLOCK_SELECT: Qt.PointingHandCursor,
    }
    self.setCursor(QCursor(cursor_map.get(self._current_tool, Qt.ArrowCursor)))
```

### Tool-Specific Mouse Handling

```python
def mousePressEvent(self, event):
    """Handle mouse press based on current tool"""
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

    elif self._current_tool == MapTool.BLOCK_SELECT:
        # Toggle block selection (for discretized maps)
        self.toggleBlockSelection(row, col)
        self.spectralDataRequested.emit(row, col)

    elif self._current_tool == MapTool.POINTER:
        self.pointClicked.emit(pos.x(), pos.y(), row, col, value)
        self.spectralDataRequested.emit(row, col)
```

### Block Selection (Scientific Feature)

For discretized hyperspectral maps, users select spatial blocks to average spectra:

```python
@Slot(int, int)
def toggleBlockSelection(self, row, col):
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

@Slot(result='QVariantMap')
def getAverageSpectrumFromSelection(self):
    """Get average spectrum from all selected blocks"""
    if self._spectral_cube is None:
        return {'error': 'No spectral data linked'}

    if not self._selected_blocks:
        return {'error': 'No blocks selected'}

    n_pts = self._spectral_cube.shape[0]
    accumulated = np.zeros(n_pts)
    count = 0

    for row, col in self._selected_blocks:
        accumulated += self._spectral_cube[:, row, col]
        count += 1

    averaged = accumulated / count

    return {
        'x': self._independent_var.tolist(),
        'y': averaged.tolist(),
        'title': f'Average spectrum ({count} blocks)',
    }
```

### Drawing Selected Blocks

```python
def _drawOverlays(self, painter):
    """Draw interactive overlay elements"""
    painter.setRenderHint(QPainter.Antialiasing, True)

    # Draw selected blocks with blue highlight
    if self._selected_blocks and self._data_to_pixel is not None:
        pen = QPen(QColor(31, 119, 180, 200))  # Blue
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(31, 119, 180, 80)))

        for row, col in self._selected_blocks:
            d = self._data_to_pixel
            cell_w = (d['ax_right'] - d['ax_left']) / d['data_cols']
            cell_h = (d['ax_bottom'] - d['ax_top']) / d['data_rows']

            rect_x = d['ax_left'] + col * cell_w
            rect_y = d['ax_top'] + row * cell_h

            painter.drawRect(QRectF(rect_x, rect_y, cell_w, cell_h))
```

---

## 5.7 Geometry Changes and Performance

### Handling Resize

```python
def geometryChange(self, newGeometry, oldGeometry):
    """Handle size changes"""
    super().geometryChange(newGeometry, oldGeometry)
    if newGeometry.size() != oldGeometry.size():
        self._needs_redraw = True  # Invalidate cache
        self.update()
```

### Performance Tips

1. **Cache aggressively** - Only redraw when data or size changes
2. **Separate static and dynamic content** - Draw matplotlib once, overlays every frame
3. **Use overlays for interactions** - Cursors, selections don't need full redraws
4. **Defer updates** - Use `update()` which batches repaints

```python
# GOOD: Mark dirty and let Qt batch updates
self._needs_redraw = True
self.update()

# BAD: Force immediate repaint
self.repaint()  # Don't do this!
```

---

## 5.8 Using Custom Components in QML

### Registration in Python

```python
# In main.py
from PySide6.QtQml import qmlRegisterType
from widgets.qml_profile_canvas import QMLProfileCanvas
from widgets.qml_map_canvas import QMLMapCanvas

# Register as "TransWidgets" module, version 1.0
qmlRegisterType(QMLProfileCanvas, "TransWidgets", 1, 0, "ProfileCanvas")
qmlRegisterType(QMLMapCanvas, "TransWidgets", 1, 0, "MapCanvas")
```

### Usage in QML

```qml
import QtQuick 2.15
import TransWidgets 1.0

Item {
    id: root

    ProfileCanvas {
        id: profilePlot
        anchors.fill: parent

        lineColor: "#5BCEFA"
        showGrid: true

        onPointClicked: (x, y) => {
            console.log("Clicked at:", x, y)
        }

        onCursorMoved: (x, y) => {
            cursorLabel.text = `X: ${x.toFixed(2)}, Y: ${y.toFixed(2)}`
        }

        onRangeSelected: (x1, x2) => {
            console.log("Selected range:", x1, "to", x2)
            // Zoom to selection
            profilePlot.setViewRange(x1, x2)
        }
    }

    Label {
        id: cursorLabel
        anchors.top: parent.top
        anchors.right: parent.right
        color: "#ffffff"
    }

    // Set data from backend connection
    Connections {
        target: backend
        function onSpectrumDataReady(x, y, label) {
            profilePlot.setProfileData(x, y)
            profilePlot.setLabels("Wavenumber (cm⁻¹)", "Intensity")
        }
    }
}
```

### Map Canvas with Tools

```qml
import TransWidgets 1.0

Item {
    MapCanvas {
        id: mapView
        anchors.fill: parent

        colormap: "viridis"
        showCrosshair: toolButton.checked

        onPointClicked: (x, y, row, col, value) => {
            statusBar.text = `Position: (${row}, ${col}), Value: ${value.toFixed(3)}`
        }

        onSpectralDataRequested: (row, col) => {
            // Backend will load spectrum at this position
            backend.loadSpectrumAt(row, col)
        }

        onBlockSelected: (row, col, value, isSelected) => {
            selectionCount.text = `${mapView.getSelectedBlockCount()} blocks`
        }
    }

    Row {
        id: toolBar
        Button {
            text: "Pointer"
            onClicked: mapView.setTool("pointer")
        }
        Button {
            text: "Select"
            onClicked: mapView.setTool("block_select")
        }
        Button {
            text: "Profile"
            onClicked: mapView.setTool("line_profile")
        }
    }

    Button {
        text: "Average Spectrum"
        onClicked: {
            var result = mapView.getAverageSpectrumFromSelection()
            if (!result.error) {
                spectrumPlot.setProfileData(result.x, result.y)
            }
        }
    }
}
```

---

## 5.9 Complete Example: Graph Canvas with Curve Operations

`src/widgets/qml_graph_canvas.py` demonstrates advanced features:

### Curve Data Structure

```python
from dataclasses import dataclass

@dataclass
class CurveData:
    """Data class for curve properties"""
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
    # Link to table for processing
    table_id: Optional[str] = None
    column_index: Optional[int] = None
```

### Math Operations

```python
@Slot(int, str, 'QVariantMap', result=int)
def applyCurveOperation(self, curve_id, operation, params=None):
    """
    Apply mathematical operation to curve, add result as new curve.

    Operations: derivative, smooth, integrate, normalize, baseline, fft
    """
    if curve_id not in self._curves:
        return -1

    curve = self._curves[curve_id]
    x = curve.x.copy()
    y = curve.y.copy()

    if operation == "derivative":
        order = params.get('order', 1)
        y_new = np.gradient(y, x)
        if order == 2:
            y_new = np.gradient(y_new, x)
        label = f"{curve.label} (d{order})"

    elif operation == "smooth":
        method = params.get('method', 'savgol')
        window = params.get('window', 11)
        if method == 'savgol':
            from scipy import signal
            y_new = signal.savgol_filter(y, window, 3)
        label = f"{curve.label} (smooth)"

    elif operation == "integrate":
        y_new = np.cumsum(y) * np.gradient(x).mean()
        label = f"{curve.label} (integral)"

    elif operation == "fft":
        n = len(y)
        freq = np.fft.fftfreq(n, d=(x[1] - x[0]))
        fft_vals = np.fft.fft(y)
        y_new = np.abs(fft_vals[:n // 2])
        x = freq[:n // 2]
        label = f"{curve.label} (FFT)"

    # Add as new curve
    new_id = self.addCurve(label, x.tolist(), y_new.tolist())
    self.curveProcessed.emit(curve_id, operation, new_id)
    return new_id
```

### QML Usage for Curve Processing

```qml
GraphCanvas {
    id: graphPlot

    onCurveSelected: (curveId) => {
        operationsMenu.currentCurve = curveId
    }
}

Menu {
    id: operationsMenu
    property int currentCurve: -1

    MenuItem {
        text: "Derivative"
        onTriggered: {
            graphPlot.applyCurveOperation(
                operationsMenu.currentCurve,
                "derivative",
                {"order": 1}
            )
        }
    }
    MenuItem {
        text: "Smooth (Savitzky-Golay)"
        onTriggered: {
            graphPlot.applyCurveOperation(
                operationsMenu.currentCurve,
                "smooth",
                {"method": "savgol", "window": 11}
            )
        }
    }
    MenuItem {
        text: "FFT"
        onTriggered: {
            graphPlot.applyCurveOperation(
                operationsMenu.currentCurve,
                "fft",
                {}
            )
        }
    }
}
```

---

## 5.10 Summary and Best Practices

### Key Patterns

1. **Lazy rendering** - Only redraw when necessary
2. **Coordinate caching** - Store transform after render
3. **Overlay separation** - Static content + dynamic overlays
4. **Signal-based communication** - Emit events to QML
5. **Tool abstraction** - Encapsulate tool behavior

### Best Practices

| Do | Don't |
|----|-------|
| Cache the rendered image | Re-render on every paint() |
| Use update() for batched repaints | Use repaint() for immediate |
| Store coordinate transforms | Calculate transforms per-frame |
| Emit signals for QML interaction | Directly manipulate QML objects |
| Copy QImage from buffer | Use buffer directly (it's reused) |

### Common Pitfalls

1. **Buffer reuse** - Always `.copy()` the QImage
2. **Missing componentComplete** - Wait for QML construction
3. **Wrong coordinate system** - Y is inverted between systems
4. **Performance** - Don't redraw matplotlib for cursor moves

---

## Exercises

### Exercise 5.1: Simple Plot Widget
Create a basic QQuickPaintedItem that plots a sine wave. Add a frequency property that updates the plot.

### Exercise 5.2: Interactive Crosshairs
Add crosshair display that follows the mouse and shows X/Y values in data coordinates.

### Exercise 5.3: Zoom Rectangle
Implement a zoom tool that lets users draw a rectangle to zoom into that region.

### Exercise 5.4: Multiple Curve Support
Extend your widget to support multiple curves with different colors and a legend.

### Exercise 5.5: Export Feature
Add a method to export the current plot as PNG, PDF, or SVG.

---

## Next Steps

In **Module 6: Scientific Computing Integration**, you'll learn:
- Data models for tables (QAbstractTableModel)
- NumPy/Pandas integration with Qt
- Building spreadsheet-like interfaces
- Formula engines and cell references

---

*Module 5 of 8 | TRANS-QML Course*
