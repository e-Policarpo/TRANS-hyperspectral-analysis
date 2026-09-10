> ## Start here: [`TRANS_REFERENCE.md`](TRANS_REFERENCE.md)
>
> The current reference, in three levels — **Surface** (tools, inputs and
> outputs), **Under the hood** (libraries, heuristics, formats, quirks) and
> **Inside the engine** (classes and how they interact).
>
> **The other files in this directory are out of date.** `API_REFERENCE.md`,
> `PROJECT_STRUCTURE.md` and the `*_PLAN.md` documents were written before the
> Confinement, Map Generator, Filter Bad Data and Modeling work and describe a
> program that no longer exists. They are kept for their history, not as
> guidance.

# TRANS-QML: Hyperspectral Data Analysis Platform

A modular, QML-based desktop application for analyzing hyperspectral data from scanning probe microscopy experiments (STS, SNOM).

## Features

### Data Loading
- **Nanosurf STS Loader**: Loads STS files with automatic zigzag correction
- **NeaSpec SNOM Loader**: Loads SNOM files with multi-channel support
- **Extensible Architecture**: Easy to add new data loaders

### Analysis Tools
- Curve Smoothing (Savitzky-Golay, Gaussian, Moving Average)
- Numerical Derivatives (1st and 2nd order)
- Integration with automatic FWHM-based intervals
- Peak Finding with prominence detection
- 1D/2D FFT Analysis
- Gradient Filters
- Curve Fitting
- Map Generation
- Spatial Averaging/Discretization
- Data Manipulation (equation-based operations)

### Visual Workflow Editor
- Node-based processing pipelines
- Drag-and-drop workflow creation
- Multi-input support with draggable queue
- Save/load workflow templates

### Map Editor Workstation (Gwyddion Paradigm)
- **Docked Map Viewer**: Maps open as tabs within the main window (not separate windows)
- **Non-Destructive Editing**: Changes tracked in session, save on close
- Interactive map canvas with matplotlib rendering
- Multi-channel support (Height, Amplitude, Phase, etc.)
- **Colormap Controls**: 18+ colormaps with invert option, manual/auto scaling
- **Statistics Panel**: Min, max, mean, std, median, RMS, range
- **Export Options**: PNG, TIFF, CSV export directly from UI
- Tool palette: Pointer, Block Select, Line Profile, Crosshair, Point Inspector, Zoom, Rectangle Select, Measure
- Data browser with channel/mask management
- Line profile extraction and display
- Point inspector with spectral data linking
- Spatial-spectral reconstruction (TRANS_v3 style)

### UI Features
- Project-based organization
- Dockable tool panels
- Customizable workspace layouts
- Dark theme interface

## Documentation

| Document | Description |
|----------|-------------|
| [Project Structure](docs/PROJECT_STRUCTURE.md) | Architecture and module documentation |
| [API Reference](docs/API_REFERENCE.md) | Detailed API documentation |
| [Quick Reference](docs/QUICK_REFERENCE.md) | Developer quick reference card |
| [Testing Guide](TESTING_GUIDE.md) | How to test the application |
| [Quickstart](QUICKSTART.md) | Getting started guide |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Project Structure

```
TRANS_QML/
├── main.py                 # Application entry point
├── src/
│   ├── backend/            # Python backend (QML bridge, tools, workflows)
│   │   ├── app_backend.py  # Main backend QObject
│   │   ├── map_editor_backend.py  # Map Editor backend
│   │   ├── workflow_engine.py     # Workflow node definitions
│   │   └── workflow_manager.py    # Workflow execution
│   ├── models/             # Data models
│   │   ├── spectral_data.py       # SpectralData class
│   │   └── map_channel.py         # MapChannel, MultiChannelMap classes
│   ├── data_loaders/       # File format parsers
│   ├── processing/         # Processing algorithms
│   ├── widgets/            # Hybrid Qt widgets
│   │   ├── qml_map_canvas.py      # QQuickPaintedItem for maps
│   │   └── qml_profile_canvas.py  # QQuickPaintedItem for profiles
│   └── qml/                # QML user interface
│       ├── main/           # Main window
│       ├── components/     # Reusable components
│       ├── tools/          # Tool panels
│       ├── dialogs/        # Modal dialogs
│       ├── workflow/       # Workflow editor
│       └── map_editor/     # Map Editor workstation
│           ├── MapEditorWorkstation.qml  # Main map editor with tabbed maps
│           ├── MapViewerPanel.qml        # Dockable map viewer with controls
│           ├── ToolPalette.qml           # Tool buttons
│           ├── DataBrowser.qml           # Channel/mask browser
│           ├── ProfileViewer.qml         # Line profile display
│           ├── PointInspector.qml        # Point info panel
│           └── StatisticsPanel.qml       # Statistics display
├── docs/                   # Documentation
├── tests/                  # Test suite
├── workflows/              # Saved workflow templates
└── outputs/                # Default output directory
```

## Dependencies

- Python 3.8+
- PySide6 (Qt for Python with QML)
- NumPy
- Pandas
- Matplotlib
- SciPy
- Pillow (PIL)
- h5py (for HDF5 project files)

## File Formats

| Extension | Description |
|-----------|-------------|
| `.hrt` | Project file (HDF5-based) |
| `.csv` | Exported spectral/tabular data |
| `.png/.tiff` | Generated maps and images |
| `.json` | Workflow definitions |

## License

Research software - Internal use
