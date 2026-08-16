# TRANS-QML Project Structure Documentation

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Directory Structure](#3-directory-structure)
4. [Module Documentation](#4-module-documentation)
5. [Component Reference](#5-component-reference)

---

# 1. Project Overview

## 1.1 Purpose

TRANS-QML is a desktop application for hyperspectral data analysis, designed for researchers working with:
- **STS (Scanning Tunneling Spectroscopy)** data from Nanosurf instruments
- **SNOM (Scanning Near-field Optical Microscopy)** data from neaspec instruments

The application provides tools for loading, processing, visualizing, and exporting spectroscopic data with spatial resolution.

## 1.2 Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **UI Framework** | PySide6/QML | Modern declarative UI with Qt Quick |
| **Backend** | Python 3.x | Data processing, file I/O, business logic |
| **Data Processing** | NumPy, SciPy, Pandas | Numerical computation and data manipulation |
| **Visualization** | Matplotlib, PIL | Plotting and image generation |
| **Project Files** | HDF5 (.hrt) | Compressed project storage |

## 1.3 Key Features

- **Project-based workflow**: Create/open projects to organize datasets and outputs
- **Multi-format data loading**: Support for various spectroscopic file formats
- **Interactive tools**: Smoothing, derivatives, integration, peak finding, FFT
- **Map generation**: Create spatial maps from spectral features
- **Visual workflow editor**: Node-based processing pipelines
- **Dockable UI**: Customizable workspace layout
- **Map Editor Workstation**: Gwyddion-style map editing with:
  - Multi-channel map support (Height, Amplitude, Phase, etc.)
  - Interactive tool palette (pointer, block select, line profile, etc.)
  - Spatial-spectral reconstruction (TRANS_v3 paradigm)
  - Data browser for channel/mask management
  - Line profile extraction and visualization
  - Point inspector with spectral data linking

## 1.4 File Conventions

| Extension | Description |
|-----------|-------------|
| `.hrt` | Project file (HDF5-based, contains datasets and metadata) |
| `.csv` | Exported spectral/tabular data |
| `.png/.tiff` | Generated maps and images |
| `.json` | Workflow definitions, interval data |

---

# 2. Architecture Overview

## 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        QML User Interface                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────────┐ │
│  │  Main   │  │  Tools  │  │ Dialogs │  │  Workflow Editor    │ │
│  │ Window  │  │ Panels  │  │         │  │  (Node-based)       │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └──────────┬──────────┘ │
└───────┼────────────┼───────────┼───────────────────┼────────────┘
        │            │           │                   │
        ▼            ▼           ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Python Backend Layer                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ AppBackend  │  │ WorkflowMgr  │  │    ProjectManager       │ │
│  │ (QObject)   │  │              │  │                         │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────┬────────────┘ │
│         │                │                       │              │
│         ▼                ▼                       ▼              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Tool Implementations (Mixin)                    ││
│  │  Smoothing, Derivatives, Integration, FFT, Maps, etc.       ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data & Processing Layer                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │   Models    │  │  Data Loaders │  │    Processing          │ │
│  │ SpectralData│  │  STS, SNOM   │  │ Discretization, etc.   │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Widget Layer (Hybrid)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ PlotWindow  │  │ TableWindow  │  │     MapWindow           │ │
│  │ (Matplotlib)│  │ (QTableView) │  │  (Image display)        │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 2.2 Communication Patterns

### QML ↔ Python Communication

```
QML Component                          Python Backend
     │                                      │
     │──── @Slot method call ──────────────►│
     │                                      │
     │◄─── Signal emission ─────────────────│
     │                                      │
     │──── Property binding ───────────────►│
     │◄─── Property notification ───────────│
```

### Background Task Execution

```
UI Thread                    Worker Thread
    │                             │
    │── submit(task) ────────────►│
    │                             │── execute task
    │                             │
    │◄── progress signal ─────────│
    │                             │
    │◄── finished signal ─────────│
```

## 2.3 Data Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  File    │───►│  Loader  │───►│ Spectral │───►│  Tool    │
│ (raw)    │    │          │    │   Data   │    │Processing│
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                     │
                     ┌───────────────────────────────┘
                     ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ Result   │───►│  Output  │───►│  File    │
              │ Dataset  │    │ Generator│    │ (csv/png)│
              └──────────┘    └──────────┘    └──────────┘
```

---

# 3. Directory Structure

```
TRANS_QML/
│
├── main.py                      # Application entry point
├── run.py                       # Equivalent launcher
├── requirements.txt             # Python dependencies
│
├── assets/                      # Static images
│   ├── icon.png                 # Application icon (loaded by src/main.py)
│   ├── Slide1.ico
│   └── LOGO TRANS/
│
├── archive/                     # Superseded versions & backups, gitignored
│                                # (see archive/README.md)
│
├── src/                         # Source code
│   ├── __init__.py
│   │
│   ├── backend/                 # Python backend modules
│   │   ├── __init__.py
│   │   ├── app_backend.py       # Main backend QObject (exposed to QML)
│   │   ├── tool_implementations.py  # Tool logic (mixin class)
│   │   ├── workflow_engine.py   # Workflow graph & node definitions
│   │   ├── workflow_manager.py  # Workflow execution & QML interface
│   │   ├── project_manager.py   # Project file save/load (HDF5)
│   │   ├── worker.py            # Background task threading
│   │   ├── dock_manager.py      # Layout persistence
│   │   └── map_editor_backend.py    # Map Editor backend (QML bridge)
│   │
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   ├── spectral_data.py     # SpectralData class
│   │   ├── topography_data.py   # TopographyData class
│   │   ├── discretizer.py       # Spatial discretization logic
│   │   └── map_channel.py       # MapChannel, MultiChannelMap classes
│   │
│   ├── data_loaders/            # File format parsers
│   │   ├── __init__.py
│   │   ├── base_loader.py       # Abstract base loader
│   │   ├── nanosurf_sts_loader.py
│   │   ├── nanosurf_sts_enhanced.py
│   │   ├── neaspec_snom_loader.py
│   │   └── neaspec_snom_enhanced.py
│   │
│   ├── processing/              # Data processing algorithms
│   │   ├── __init__.py
│   │   ├── derivatives.py
│   │   ├── discretization.py
│   │   ├── integration.py
│   │   ├── iv_processor.py
│   │   └── map_generator.py
│   │
│   ├── widgets/                 # Hybrid Qt widgets (Python)
│   │   ├── __init__.py
│   │   ├── enhanced_plot_window.py   # Matplotlib plot window
│   │   ├── enhanced_table_window.py  # Data table window
│   │   ├── map_window.py             # Map/image viewer
│   │   ├── plot_window.py            # Basic plot window
│   │   ├── table_window.py           # Basic table window
│   │   ├── qml_map_canvas.py         # QQuickPaintedItem for map rendering
│   │   └── qml_profile_canvas.py     # QQuickPaintedItem for profile plots
│   │
│   ├── qml/                     # QML UI components
│   │   ├── main/
│   │   │   └── Main.qml         # Main application window
│   │   │
│   │   ├── components/          # Reusable UI components
│   │   │   ├── ProjectBrowser.qml
│   │   │   ├── DockableWorkspace.qml
│   │   │   ├── DockArea.qml
│   │   │   ├── DraggableWindow.qml
│   │   │   └── DebugConsole.qml
│   │   │
│   │   ├── dialogs/             # Modal dialogs
│   │   │   ├── ProjectStartupDialog.qml
│   │   │   ├── ImportMeasurementDialog.qml
│   │   │   ├── LoadWorkflowDialog.qml
│   │   │   ├── SaveLayoutDialog.qml
│   │   │   └── LoadLayoutDialog.qml
│   │   │
│   │   ├── tools/               # Tool panels (dockable)
│   │   │   ├── ToolWindow.qml         # Base tool container
│   │   │   ├── CurveSmoothingTool.qml
│   │   │   ├── DerivativeTool.qml
│   │   │   ├── IntegrationTool.qml
│   │   │   ├── MapGeneratorTool.qml
│   │   │   ├── PeakIndexingTool.qml
│   │   │   ├── FFT1DTool.qml
│   │   │   ├── FFT2DTool.qml
│   │   │   ├── SpatialAverageTool.qml
│   │   │   ├── TruncateTool.qml
│   │   │   └── ...
│   │   │
│   │   ├── workflow/            # Workflow editor components
│   │   │   ├── WorkflowWindow.qml     # Workflow editor window
│   │   │   ├── WorkflowNode.qml       # Node visual representation
│   │   │   ├── NodeParameterEditor.qml # Node parameter panel
│   │   │   └── DraggableListItem.qml  # Reusable draggable list item
│   │   │
│   │   └── map_editor/          # Map Editor Workstation components
│   │       ├── MapEditorWorkstation.qml  # Main map editor layout
│   │       ├── ToolPalette.qml           # Tool selection buttons
│   │       ├── DataBrowser.qml           # Channel/mask browser
│   │       ├── ProfileViewer.qml         # Line profile display
│   │       ├── PointInspector.qml        # Point info panel
│   │       └── StatisticsPanel.qml       # Statistics display
│   │
│   ├── tools/                   # (Reserved for future tool plugins)
│   │   └── __init__.py
│   │
│   └── utils/                   # Utility functions
│       └── __init__.py
│
├── config/                      # Configuration files (reserved)
├── docs/                        # Documentation
├── tests/                       # Test suite (reserved)
├── workflows/                   # Saved workflow definitions (.json)
└── outputs/                     # Default output directory (legacy)
```

---

# 4. Module Documentation

## 4.1 Backend Modules

### 4.1.1 `app_backend.py` - Main Backend

**Purpose**: Central QObject that bridges QML UI with Python functionality.

**Inheritance**: `QObject` + `ToolImplementations` (mixin)

**Key Responsibilities**:
- Project management (create, open, save)
- Dataset management (load, store, retrieve)
- Tool execution coordination
- Signal/slot interface for QML
- Window management (plot, table, map windows)

**Exposed to QML as**: `backend`

**Key Properties** (QML-accessible):
| Property | Type | Description |
|----------|------|-------------|
| `projectReady` | bool | Whether a project is open |
| `isBusy` | bool | Whether a background task is running |
| `status` | string | Current status message |
| `activeDataset` | string | Currently selected dataset name |
| `datasetList` | list | List of loaded dataset names |

**Key Signals**:
| Signal | Parameters | Description |
|--------|------------|-------------|
| `projectLoaded` | path: string | Project opened successfully |
| `dataLoaded` | name: string | Dataset loaded/created |
| `errorOccurred` | title, message | Error notification |
| `toolCompleted` | toolName, resultPath | Tool finished processing |

**Key Slots** (callable from QML):
| Slot | Parameters | Description |
|------|------------|-------------|
| `createProject` | path, name | Create new project |
| `openProjectFile` | path | Open .hrt project file |
| `loadMeasurement` | path | Load data file into project |
| `smoothCurves` | dataset, params | Apply curve smoothing |
| `calculateDerivative` | dataset, order | Compute derivative |
| `integrate` | dataset, intervals | Perform integration |
| ... | ... | ... |

---

### 4.1.2 `tool_implementations.py` - Tool Logic

**Purpose**: Mixin class containing all tool implementations.

**Design Pattern**: Mixin (mixed into AppBackend)

**Key Methods**:
| Method | Description |
|--------|-------------|
| `smooth_curves()` | Apply smoothing algorithms |
| `calculate_derivative()` | Compute numerical derivatives |
| `find_peaks()` | Detect peaks with FWHM calculation |
| `evaluate_data_equation()` | Equation-based data manipulation |
| `discretize_map()` | Reduce map resolution |
| ... | ... |

---

### 4.1.3 `workflow_engine.py` - Workflow Graph

**Purpose**: Define workflow nodes, connections, and validation.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `Port` | Input/output port on a node |
| `WorkflowNode` | Single node in the workflow |
| `Connection` | Link between two ports |
| `Workflow` | Complete workflow graph |

**Port Types** (`PortType` enum):
| Type | Description |
|------|-------------|
| `DATASET` | Full spectral dataset |
| `FLAT_DATA` | 2D data (e.g., integrated values) |
| `IMAGE` | Image/map file path |
| `TABLE` | Tabular data |
| `NUMBER` | Single numeric value |
| `STRING` | Text value |
| `INTERVALS` | List of [start, end] ranges |
| `ANY` | Accepts any type |

**Node Definitions** (`TOOL_DEFINITIONS` dict):
- Each tool has: display_name, category, description, inputs, outputs, parameters

---

### 4.1.4 `workflow_manager.py` - Workflow Execution

**Purpose**: Execute workflows, manage workflow files, QML interface.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `WorkflowExecutor` | Executes workflow in topological order |
| `WorkflowManager` | QObject for QML, manages workflow lifecycle |

**Execution Flow**:
1. Topological sort of nodes
2. For each node: gather inputs → execute → store outputs
3. Emit progress signals
4. Return results

---

### 4.1.5 `project_manager.py` - Project Persistence

**Purpose**: Save/load projects to HDF5 (.hrt) files.

**File Format**:
```
project.hrt (HDF5)
├── metadata/           # Project metadata (JSON)
│   ├── name
│   ├── created
│   └── modified
├── datasets/           # Stored datasets
│   ├── dataset_name_1/
│   │   ├── data        # Numerical data array
│   │   ├── columns     # Column names
│   │   └── metadata    # Dataset metadata (JSON)
│   └── ...
└── workflows/          # Embedded workflows (optional)
```

---

### 4.1.6 `worker.py` - Background Threading

**Purpose**: Execute long-running tasks without freezing UI.

**Key Classes**:
| Class | Description |
|-------|-------------|
| `Task` | Single task with cancellation support |
| `PersistentWorker` | Thread that processes task queue |
| `WorkerManager` | Manages worker lifecycle and task submission |

**Thread Safety**: Uses `QMutex` for queue access, signals for result delivery.

---

## 4.2 Data Models

### 4.2.1 `spectral_data.py` - SpectralData Class

**Purpose**: Core data container for spectroscopic datasets.

**Key Attributes**:
| Attribute | Type | Description |
|-----------|------|-------------|
| `data` | DataFrame | Raw data (independent var + spectra) |
| `spectra` | DataFrame | Only spectral columns |
| `independent_var` | ndarray | X-axis values (energy, wavelength, etc.) |
| `metadata` | SpectralMetadata | Source info, dimensions, units |
| `topography` | ndarray | Optional height map |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `truncate_range()` | Limit x-axis range |
| `get_spectrum()` | Get single spectrum by index |
| `save()` | Export to CSV |
| `from_csv()` | Load from CSV |

---

### 4.2.2 `topography_data.py` - TopographyData Class

**Purpose**: Container for topography/height map data.

---

### 4.2.3 `discretizer.py` - Discretizer Class

**Purpose**: Spatial averaging/discretization of hyperspectral data.

---

## 4.3 Data Loaders

### 4.3.1 Base Loader Interface

**File**: `base_loader.py`

**Purpose**: Abstract interface for data loaders.

**Methods to Implement**:
| Method | Description |
|--------|-------------|
| `can_load()` | Check if file is supported |
| `load()` | Load file and return SpectralData |

---

### 4.3.2 Nanosurf STS Loader

**Files**: `nanosurf_sts_loader.py`, `nanosurf_sts_enhanced.py`

**Supported Formats**: Nanosurf .sxm, .dat files

---

### 4.3.3 neaspec SNOM Loader

**Files**: `neaspec_snom_loader.py`, `neaspec_snom_enhanced.py`

**Supported Formats**: neaspec .gsf, .txt files

---

## 4.4 Processing Modules

### 4.4.1 `derivatives.py`
**Purpose**: Numerical differentiation algorithms.

### 4.4.2 `discretization.py`
**Purpose**: Spatial discretization/binning.

### 4.4.3 `integration.py`
**Purpose**: Numerical integration over intervals.

### 4.4.4 `iv_processor.py`
**Purpose**: I-V curve specific processing.

### 4.4.5 `map_generator.py`
**Purpose**: Generate spatial maps from spectral features.

---

## 4.5 Widget Modules

### 4.5.1 `enhanced_plot_window.py`
**Purpose**: Matplotlib-based interactive plot window.
**Features**: Zoom, pan, cursor, spectrum selection, export.

### 4.5.2 `enhanced_table_window.py`
**Purpose**: Tabular data viewer with sorting/filtering.

### 4.5.3 `map_window.py`
**Purpose**: Image/map viewer with colormap controls.

### 4.5.4 `qml_map_canvas.py` - QMLMapCanvas
**Purpose**: QQuickPaintedItem for rendering maps in QML using matplotlib.

**Key Features**:
- Matplotlib figure rendering directly in QML scene graph
- Interactive tools: pointer, zoom, pan, line profile, block selection
- Overlay drawing (selection, crosshairs, profile lines)
- Spectral-spatial reconstruction support (TRANS_v3 paradigm)

**Signals**:
| Signal | Description |
|--------|-------------|
| `pointClicked(x, y, row, col, value)` | Click on map position |
| `profileDrawn(x1, y1, x2, y2)` | Line profile drawn |
| `regionSelected(x1, y1, x2, y2)` | Rectangle selection |
| `cursorMoved(x, y, row, col, value)` | Cursor position update |
| `blockSelectionChanged()` | Block selection modified |
| `spectralDataRequested(row, col)` | Spectrum requested at position |

**Statistics & Export Methods** (added for docked viewer):
| Method | Description |
|--------|-------------|
| `getStatistics()` | Returns dict with min, max, mean, std, median, rows, cols |
| `setColorLimits(vmin, vmax)` | Set color scale limits |
| `exportImage(path, format)` | Export map view as image (PNG/TIFF) |
| `exportCsv(path)` | Export map data as CSV |
| `saveMapData(path)` | Save map data (TIFF/NPY/CSV) |

### 4.5.5 `qml_profile_canvas.py` - QMLProfileCanvas
**Purpose**: QQuickPaintedItem for rendering line profiles and spectra in QML.

**Key Features**:
- Line plot rendering with matplotlib
- Dark theme styling
- Interactive cursor and range selection
- Multiple curve overlay support

---

## 4.6 Map Editor Backend

### 4.6.1 `map_editor_backend.py` - MapEditorBackend
**Purpose**: QObject bridge for Map Editor Workstation, connects QML to data model.

**Key Responsibilities**:
- Multi-channel map management
- Spectral-spatial reconstruction linking
- Block selection and averaging
- Processing operations (filters, leveling, etc.)
- Profile extraction

**Signals**:
| Signal | Description |
|--------|-------------|
| `mapDataChanged` | Map data updated |
| `channelListChanged` | Channel list modified |
| `activeChannelChanged(name)` | Active channel changed |
| `spectralDataChanged` | Spectral link updated |
| `processingStarted(operation)` | Processing began |
| `processingFinished(operation, success, message)` | Processing completed |
| `selectionChanged(count)` | Selection modified |

**Key Slots**:
| Slot | Description |
|------|-------------|
| `loadMapFromFile(path)` | Load map from TIFF/PNG/NPY |
| `setActiveChannel(name)` | Set active channel |
| `applyProcessing(operation, params)` | Apply filter/processing |
| `extractProfile(startRow, startCol, endRow, endCol)` | Extract line profile |
| `getSpectrumAt(row, col)` | Get spectrum at position |
| `computeIntegratedMap(rangeStr)` | Compute integrated intensity map |

---

## 4.7 Map Data Models

### 4.7.1 `map_channel.py` - MapChannel
**Purpose**: Single channel of map data with metadata.

**Key Attributes**:
| Attribute | Type | Description |
|-----------|------|-------------|
| `data` | ndarray | 2D map data |
| `metadata` | ChannelMetadata | Channel info (name, type, units) |
| `mask` | ndarray | Optional boolean mask |
| `history` | list | Processing history |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `normalize()` | Normalize data to [0, 1] |
| `get_statistics()` | Get min, max, mean, std, etc. |
| `extract_profile(start, end)` | Extract line profile |

### 4.7.2 `map_channel.py` - MultiChannelMap
**Purpose**: Container for multiple map channels with spectral linking.

**Key Features**:
- Multiple channels (Height, Amplitude, Phase, etc.)
- Mask management
- Spectral cube linking for spatial-spectral reconstruction
- Integrated map computation

**Key Methods**:
| Method | Description |
|--------|-------------|
| `add_channel(name, data)` | Add new channel |
| `link_spectral_cube(cube, x, name)` | Link spectral data |
| `get_spectrum_at(row, col)` | Get spectrum at position |
| `compute_integrated_map(start, end)` | Compute integrated intensity |

---

# 5. Component Reference

## 5.1 QML Components

### 5.1.1 Main Window (`Main.qml`)

**Purpose**: Application main window, orchestrates all UI.

**Key Responsibilities**:
- Menu bar and toolbar
- Dockable workspace management
- Dialog coordination
- Global keyboard shortcuts

**Key Properties**:
| Property | Description |
|----------|-------------|
| `openWorkflowWindows` | List of open workflow editor windows |
| `currentProject` | Currently open project info |

---

### 5.1.2 Project Browser (`ProjectBrowser.qml`)

**Purpose**: Tree view of project datasets and outputs.

**Features**:
- Dataset list with type icons
- Double-click to open in viewer
- Context menu for operations
- Drag-and-drop support

---

### 5.1.3 Dockable Workspace (`DockableWorkspace.qml`)

**Purpose**: Container for dockable tool panels.

**Features**:
- Dock areas (left, right, bottom)
- Drag to rearrange
- Save/load layouts

---

### 5.1.4 Tool Windows (`tools/*.qml`)

**Purpose**: Individual tool UI panels.

**Common Structure**:
```qml
ToolWindow {
    title: "Tool Name"

    // Parameter inputs
    ComboBox { /* dataset selection */ }
    SpinBox { /* numeric parameters */ }

    // Action button
    Button {
        text: "Apply"
        onClicked: backend.toolMethod(params)
    }
}
```

---

### 5.1.5 Workflow Editor (`workflow/*.qml`)

**Purpose**: Visual node-based workflow editor.

**Components**:
| Component | Description |
|-----------|-------------|
| `WorkflowWindow.qml` | Main editor window with canvas |
| `WorkflowNode.qml` | Visual node with ports |
| `NodeParameterEditor.qml` | Parameter editing panel |
| `DraggableListItem.qml` | Reusable draggable list item |

---

### 5.1.6 Map Editor Workstation (`map_editor/*.qml`)

**Purpose**: Gwyddion-style map editing interface with spatial-spectral reconstruction.

**Components**:
| Component | Description |
|-----------|-------------|
| `MapEditorWorkstation.qml` | Main layout integrating all panels |
| `ToolPalette.qml` | Left toolbar with tool buttons |
| `DataBrowser.qml` | Right panel for channel/mask management |
| `ProfileViewer.qml` | Bottom panel for line profile display |
| `PointInspector.qml` | Point info and spectral data panel |
| `StatisticsPanel.qml` | Channel/selection statistics display |

**ToolPalette Tools**:
| Tool | Key | Description |
|------|-----|-------------|
| Pointer | P | Click to view spectrum at position |
| Block Select | B | TRANS_v3 style block selection |
| Line Profile | L | Drag to draw and extract profile |
| Crosshair | + | Interactive position cursor |
| Point Inspector | i | Click for detailed point info |
| Zoom Rectangle | Z | Draw rectangle to zoom |
| Rectangle Select | R | Select rectangular region |
| Measure | M | Measure distances |

**Data Flow**:
```
MapEditorBackend (Python)
    │
    ├── MapCanvas (QQuickPaintedItem)
    │       └── Renders map, handles mouse events
    │
    ├── ToolPalette ──► setTool() ──► MapCanvas
    │
    ├── DataBrowser ──► setActiveChannel() ──► MapCanvas
    │
    ├── ProfileViewer ◄── extractProfile() ◄── MapCanvas
    │
    └── StatisticsPanel ◄── getChannelStatistics()
```

---

## 5.2 Dialog Components

### 5.2.1 Project Startup Dialog
**Purpose**: New project / Open project / Recent projects.

### 5.2.2 Import Measurement Dialog
**Purpose**: File browser for loading measurement data.

### 5.2.3 Workflow Dialogs
**Purpose**: Save/load workflow definitions.

### 5.2.4 Layout Dialogs
**Purpose**: Save/load workspace layouts.

---

# Appendix A: Output Directory Structure

When a project is created/opened, outputs are saved to:

```
{ProjectPath}/
├── {ProjectName}.hrt           # Project file
└── {ProjectName}_outputs/      # Output folder
    ├── curves/                 # Processed spectral data
    ├── derivatives/            # Derivative results
    ├── integrated/             # Integration results
    ├── smoothed/               # Smoothed data
    ├── maps/                   # Generated maps
    ├── peaks/                  # Peak finding results
    ├── discretized/            # Spatially averaged data
    ├── fft/                    # FFT results
    ├── fitted/                 # Curve fitting results
    └── workflows/              # Workflow outputs
```

---

# Appendix B: Naming Conventions

## File Naming
| Pattern | Example |
|---------|---------|
| `{dataset}_smoothed_{type}.csv` | `Sample1_smoothed_savgol.csv` |
| `{dataset}_1st_derivative.csv` | `Sample1_1st_derivative.csv` |
| `{dataset}_integrated.csv` | `Sample1_integrated.csv` |
| `{dataset}_peaks.csv` | `Sample1_peaks.csv` |
| `{dataset}_averaged_{NxM}.csv` | `Sample1_averaged_2x2.csv` |

## Dataset Naming (in Project Browser)
| Pattern | Example |
|---------|---------|
| `{source} - {operation}` | `Sample1 - Smoothed` |
| `{source} - {operation} ({params})` | `Sample1 - Truncated (-1.0 to 1.0)` |

---

# Appendix C: Theme Colors

The application uses a consistent dark theme:

| Color Name | Hex | Usage |
|------------|-----|-------|
| `bgDark` | `#1a1a1a` | Darkest backgrounds |
| `bgMedium` | `#2a2a2a` | Panel backgrounds |
| `bgLight` | `#3a3a3a` | Elevated elements |
| `accentPink` | `#ff66b2` | Primary accent, selection |
| `accentBlue` | `#66b3ff` | Secondary accent, links |
| `accentGreen` | `#66ff99` | Success, enabled |
| `accentOrange` | `#ffaa66` | Warnings, required |
| `textLight` | `#ffffff` | Primary text |
| `textMuted` | `#cccccc` | Secondary text |
| `borderColor` | `#555555` | Borders, dividers |

---

*Documentation generated for TRANS-QML project*
*Last updated: December 2024*
*Phase 2 (Map Editor Tools & Panels) completed*
