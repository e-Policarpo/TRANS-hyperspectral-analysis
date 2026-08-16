# T.R.A.N.S. — Tools for Research and Analysis for Nano Spectroscopy

A modern, QML-based desktop application for analyzing hyperspectral data from scanning probe microscopy experiments.

Designed for **STS** (Scanning Tunneling Spectroscopy) and **SNOM** (Scanning Near-field Optical Microscopy) data, with support for Nanosurf, NeaSpec, and Omicron instruments.

![License: GPL](https://img.shields.io/badge/License-GPL-blue.svg)
![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![Qt 6 / QML](https://img.shields.io/badge/Qt-6%20%2F%20QML-green.svg)

---

## Features

### Data Loading
- **Nanosurf STS** (`.nid`) — automatic zigzag correction, multi-channel support
- **NeaSpec SNOM** (`.txt`) — multi-channel optical data
- **Omicron** (`.mtrx`, flat) — matrix and flat file formats
- Extensible loader architecture for adding new formats

### Analysis Tools (20+)

| Category | Tools |
|----------|-------|
| **Processing** | Curve Smoothing, Derivatives, Integration, Truncate, FFT, Curve Fitting, Math Operations, Filter Bad Data |
| **Analysis** | Peak Indexing, Bandgap & Doping Detection, Dirac Point Estimator |
| **Spatial** | Spatial Averaging, Map Generator, Map Discretizer |
| **Image** | Image Smoothing, Gradient Filter, Gaussian/Median Filters, Plane Leveling, Row Alignment, Normalization |
| **Visualization** | Map Generator, Average Curves |

### Visual Workflow Editor
- Node-based processing pipelines with typed ports
- Drag-and-drop workflow creation
- Multi-input support with draggable queue
- Save/load reusable workflow templates

### Map Editor Workstation
- Gwyddion-style docked map viewer with tabbed maps
- Interactive canvas tools: Pointer, Block Select, Line Profile, Crosshair, Point Inspector, Zoom, Rectangle Select, Measure
- 18+ colormaps with invert option and manual/auto scaling
- Statistics panel (min, max, mean, std, median, RMS, range)
- Channel/mask management and spatial-spectral reconstruction
- Export to PNG, TIFF, CSV

### Project Management
- HDF5-based project files (`.hrt`) for complete state persistence
- Recent projects list and startup dialog
- Project-organized output directories (curves, maps, derivatives, FFT, etc.)

### Interface
- Dark theme with trans pride accent colors
- Dockable tool panels and customizable workspace
- Global font scaling
- Cross-platform (macOS, Windows, Linux)

---

## Installation

```bash
git clone https://github.com/e-Policarpo/TRANS_QML.git
cd TRANS_QML
pip install -r requirements.txt
```

**macOS only** (optional, for proper menu bar name):
```bash
pip install pyobjc-framework-Cocoa
```

### Requirements

- Python 3.8+
- PySide6 >= 6.5.0
- NumPy, SciPy, Pandas, Matplotlib
- Pillow, scikit-image, h5py
- numba (optional, for JIT acceleration)

---

## Usage

```bash
python src/main.py
```

The application opens with a project startup dialog where you can:
1. **Create a new project** — choose a name and location
2. **Open a project folder** — browse to an existing project directory
3. **Open a `.hrt` file** — load a saved project with all datasets and state
4. **Open a recent project** — quick access to previously opened projects

### Supported Input Formats

| Extension | Instrument | Description |
|-----------|------------|-------------|
| `.nid` | Nanosurf | STS spectroscopy data |
| `.txt` | NeaSpec | SNOM optical spectroscopy data |
| `.mtrx` | Omicron | Matrix file format |

### Output Formats

| Extension | Description |
|-----------|-------------|
| `.hrt` | Project file (HDF5-based, complete state) |
| `.csv` | Exported spectral/tabular data |
| `.png` / `.tiff` | Generated maps and images |
| `.json` | Workflow definitions |

---

## Project Structure

```
TRANS_QML/
├── src/
│   ├── main.py                  # Application entry point
│   ├── backend/                 # Python backend (QML bridge, tools, workflows)
│   │   ├── app_backend.py       # Main AppBackend QObject
│   │   ├── tool_implementations.py  # All tool algorithms
│   │   ├── workflow_engine.py   # Workflow node definitions & DAG
│   │   ├── workflow_manager.py  # Workflow execution & management
│   │   ├── map_editor_backend.py    # Map editor logic
│   │   ├── project_manager.py   # .hrt project file handling
│   │   └── worker.py            # Multithreaded task execution
│   ├── models/                  # Data structures
│   │   ├── spectral_data.py     # SpectralData & SpectralMetadata
│   │   ├── map_channel.py       # MapChannel, MultiChannelMap
│   │   └── discretizer.py       # Spatial discretization
│   ├── data_loaders/            # File format parsers
│   │   ├── nanosurf_sts_loader.py
│   │   ├── neaspec_snom_loader.py
│   │   ├── omicron_mtrx_loader.py
│   │   └── nsfopen/             # Vendored NSFopen (MIT, Nanosurf AG)
│   ├── processing/              # Signal & image processing algorithms
│   ├── widgets/                 # QQuickPaintedItem widgets (map, profile, graph)
│   └── qml/                     # QML user interface
│       ├── main/                # Main application window
│       ├── components/          # Reusable UI components
│       ├── tools/               # Tool panels (20+)
│       ├── dialogs/             # Modal dialogs
│       ├── workflow/            # Node-based workflow editor
│       └── map_editor/          # Map Editor workstation
├── tests/                       # Test suite (pytest, 1900+ tests)
├── docs/                        # Documentation
├── tools/                       # Standalone CLI utilities (qtipeaks, …)
├── workflows/                   # Saved workflow templates
├── assets/                      # Icons, logos and other static images
├── archive/                     # Superseded versions & backups (gitignored)
├── main.py, run.py              # Launchers → src/main.py
├── run_tests.py, test.sh        # Test runners
└── requirements.txt
```

---

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov

# Run a specific module
pytest tests/test_backend/
pytest tests/test_models/
pytest tests/test_data_loaders/

# Using the test runner script
./test.sh                    # All tests
./test.sh --coverage         # With coverage report
./test.sh --module backend   # Specific module
./test.sh --failfast         # Stop on first failure
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Quickstart](docs/QUICKSTART.md) | Getting started guide |
| [Project Structure](docs/PROJECT_STRUCTURE.md) | Architecture documentation |
| [API Reference](docs/API_REFERENCE.md) | Detailed API docs |
| [Quick Reference](docs/QUICK_REFERENCE.md) | Developer reference card |

---

## License

GPL (GNU General Public License)

The vendored [NSFopen](src/data_loaders/nsfopen/) library is MIT licensed (Nanosurf AG).

---

## Author

**Eduarda Policarpo**
- Email: eduardapolicarpo.fisica@gmail.com
- GitHub: [e-Policarpo](https://github.com/e-Policarpo)
