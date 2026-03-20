# TRANS-QML API Reference

This document provides detailed API documentation for developers extending or maintaining TRANS-QML.

---

## Table of Contents

1. [Backend API](#1-backend-api)
2. [Models API](#2-models-api)
3. [Workflow API](#3-workflow-api)
4. [Data Loaders API](#4-data-loaders-api)
5. [QML-Python Interface](#5-qml-python-interface)

---

# 1. Backend API

## 1.1 AppBackend Class

**Location**: `src/backend/app_backend.py`

**Inheritance**: `QObject`, `ToolImplementations`

### Properties

```python
# Project State
projectReady: bool          # Read-only, notifies: projectReadyChanged
isBusy: bool               # Read-only, notifies: isBusyChanged
status: str                # Read-write, notifies: statusChanged

# Dataset State
activeDataset: str         # Read-only, notifies: activeDatasetChanged
datasetList: List[str]     # Read-only, notifies: datasetListChanged
```

### Signals

```python
# Project signals
projectLoaded(path: str)
projectReadyChanged(ready: bool)

# Data signals
dataLoaded(name: str)
datasetListChanged()
activeDatasetChanged()

# Status signals
isBusyChanged(busy: bool)
statusChanged(status: str)

# Tool signals
toolCompleted(toolName: str, resultPath: str)
errorOccurred(title: str, message: str)

# Window signals
openPlotWindow(datasetName: str)
openTableWindow(datasetName: str)
openMapWindow(path: str, windowId: str, title: str)

# Large dataset handling
largeDatasetConfirmation(datasetName: str, numSpectra: int, numPoints: int)
```

### Slots (QML-callable)

#### Project Management

```python
@Slot(str, str)
def createProject(project_path: str, project_name: str) -> None:
    """Create a new project at the specified path."""

@Slot(str, str)
def openProject(project_path: str, project_name: str) -> None:
    """Open an existing project folder."""

@Slot(str, result=bool)
def openProjectFile(file_path: str) -> bool:
    """Open a .hrt project file."""

@Slot(str)
def saveProjectFile(file_path: str) -> None:
    """Save project to .hrt file."""

@Slot()
def closeProject() -> None:
    """Close the current project."""
```

#### Dataset Management

```python
@Slot(str, str)
def loadMeasurement(file_path: str, data_format: str) -> None:
    """Load a measurement file into the project."""

@Slot(str)
def setActiveDataset(dataset_name: str) -> None:
    """Set the active dataset for operations."""

@Slot(str, result='QVariantMap')
def getDatasetInfo(dataset_name: str) -> Dict:
    """Get metadata about a dataset."""

@Slot(str)
def openDatasetInPlot(dataset_name: str) -> None:
    """Open dataset in plot window."""

@Slot(str)
def openDatasetInTable(dataset_name: str) -> None:
    """Open dataset in table window."""
```

#### Tool Execution

```python
@Slot(str, int, int, str)
def smoothCurves(dataset_name: str, window_size: int,
                 poly_order: int, smoothing_type: str) -> None:
    """Apply smoothing to curves."""

@Slot(str, int, bool, bool)
def calculateDerivative(dataset_name: str, order: int,
                        smooth_before: bool, smooth_after: bool) -> None:
    """Calculate numerical derivative."""

@Slot(str, 'QVariantList')
def integrate(dataset_name: str, intervals: List) -> None:
    """Integrate over specified intervals."""

@Slot(str, float, int, float)
def findPeaks(dataset_name: str, prominence: float,
              min_distance: int, fwhm_multiplier: float) -> None:
    """Find peaks in spectral data."""

@Slot(str, int, int)
def generateMap(dataset_name: str, column_index: int,
                colormap_index: int) -> None:
    """Generate spatial map from data column."""

@Slot(str)
def fft1D(dataset_name: str) -> None:
    """Perform 1D FFT on dataset."""

@Slot(str, int, int, bool, bool)
def spatialAverage(dataset_name: str, discrete_x: int, discrete_y: int,
                   ignore_empty: bool, save_intermediate: bool) -> None:
    """Perform spatial averaging."""

@Slot(str, float, float)
def truncateData(dataset_name: str, min_val: float, max_val: float) -> None:
    """Truncate data to x-axis range."""
```

#### Image Import (Map Editor)

```python
@Slot(str)
def importImage(file_path: str) -> None:
    """
    Import an image file and open in Map Editor (docked).

    Supported formats: TIFF, PNG, JPG, NPY, GSF (Gwyddion)

    Emits:
        imageImported(map_name, file_path, map_id): Opens Map Editor tab
    """

@Slot(result='QVariantMap')
def getImportedMapData() -> Dict:
    """
    Get the most recently imported map data.

    Returns:
        Dict with 'data', 'name', 'path', 'rows', 'cols'
        or {'error': 'No map data available'}
    """

@Slot()
def clearImportedMapData() -> None:
    """Clear imported map data after consumption."""
```

---

## 1.2 ToolImplementations Class

**Location**: `src/backend/tool_implementations.py`

**Purpose**: Mixin class with tool implementations (internal methods).

### Methods

```python
def smooth_curves(self, task, dataset_name: str, window_size: int,
                  poly_order: int, smoothing_type: str) -> str:
    """
    Smooth spectral curves.

    Parameters:
        task: Task object for cancellation
        dataset_name: Name of dataset to smooth
        window_size: Smoothing window size (must be odd)
        poly_order: Polynomial order for Savitzky-Golay
        smoothing_type: 'savgol', 'moving_average', or 'gaussian'

    Returns:
        Path to output file
    """

def calculate_derivative(self, dataset_name: str, order: int,
                         smooth_before: bool, smooth_after: bool) -> str:
    """
    Calculate numerical derivative.

    Parameters:
        dataset_name: Name of dataset
        order: Derivative order (1 or 2)
        smooth_before: Apply smoothing before differentiation
        smooth_after: Apply smoothing after differentiation

    Returns:
        Path to output file
    """

def find_peaks(self, task, dataset_name: str, prominence: float,
               min_distance: int, fwhm_multiplier: float) -> Dict:
    """
    Find peaks with FWHM-based intervals.

    Parameters:
        task: Task object for cancellation
        dataset_name: Name of dataset
        prominence: Minimum peak prominence
        min_distance: Minimum distance between peaks
        fwhm_multiplier: Interval width = FWHM × multiplier

    Returns:
        Dict with 'peaks_path' and 'intervals' keys
    """

def evaluate_data_equation(self, equation: str, dataset_a=None,
                           dataset_b=None, flat_a=None, flat_b=None,
                           output_name: str = "Manipulated") -> Dict:
    """
    Evaluate equation on datasets.

    Parameters:
        equation: Math expression (e.g., "A + B", "sqrt(A)")
        dataset_a: First dataset (referenced as 'A')
        dataset_b: Second dataset (referenced as 'B')
        flat_a: First flat data (referenced as 'A')
        flat_b: Second flat data (referenced as 'B')
        output_name: Label for output

    Returns:
        Dict with 'result_dataset', 'result_flat', 'error' keys

    Supported Operations:
        Arithmetic: +, -, *, /, ^ (power)
        Functions: sqrt, log, log10, exp, abs, sin, cos, tan
        Constants: pi, e
    """
```

---

## 1.3 WorkerManager Class

**Location**: `src/backend/worker.py`

### Methods

```python
def submit(self, name: str, operation: Callable,
           on_finished: Callable = None, on_error: Callable = None,
           **kwargs) -> Task:
    """
    Submit a task for background execution.

    Parameters:
        name: Display name for the task
        operation: Function to execute (receives 'task' as first arg)
        on_finished: Callback when task completes
        on_error: Callback on error
        **kwargs: Arguments passed to operation

    Returns:
        Task object for tracking/cancellation
    """

def cancel_all(self) -> None:
    """Cancel all pending tasks."""

def stop(self) -> None:
    """Stop the worker thread."""
```

---

## 1.4 MapEditorBackend Class

**Location**: `src/backend/map_editor_backend.py`

**Inheritance**: `QObject`

### Properties

```python
# Map State
hasMapData: bool              # Read-only, notifies: mapDataChanged
channelNames: List[str]       # Read-only, notifies: channelListChanged
activeChannelName: str        # Read-only, notifies: activeChannelChanged
mapRows: int                  # Read-only, notifies: mapDataChanged
mapCols: int                  # Read-only, notifies: mapDataChanged

# Spectral State
hasSpectralData: bool         # Read-only, notifies: spectralDataChanged
spectralPoints: int           # Read-only, notifies: spectralDataChanged
```

### Signals

```python
# Data signals
mapDataChanged()
channelListChanged()
activeChannelChanged(channelName: str)
spectralDataChanged()

# Processing signals
processingStarted(operation: str)
processingFinished(operation: str, success: bool, message: str)

# Selection signals
selectionChanged(blockCount: int)
statisticsUpdated(stats: Dict)
```

### Slots (QML-callable)

#### Data Loading

```python
@Slot(str)
def loadMapFromFile(file_path: str) -> None:
    """Load map from TIFF, PNG, NPY, or GSF file."""

@Slot(str)
def setActiveChannel(channel_name: str) -> None:
    """Set the active channel for display and processing."""

@Slot(str, result='QVariantMap')
def getChannelStatistics(channel_name: str) -> Dict:
    """Get statistics for a channel (min, max, mean, std, etc.)."""
```

#### Processing

```python
@Slot(str, 'QVariantMap')
def applyProcessing(operation: str, params: Dict) -> None:
    """
    Apply processing operation to active channel.

    Operations:
        - 'gaussian_filter': params={'sigma': float}
        - 'median_filter': params={'size': int}
        - 'plane_level': params={}
        - 'row_align': params={}
        - 'normalize': params={}
    """
```

#### Profile Extraction

```python
@Slot(int, int, int, int, result='QVariantMap')
def extractProfile(start_row: int, start_col: int,
                   end_row: int, end_col: int) -> Dict:
    """
    Extract line profile from active channel.

    Returns:
        Dict with 'distance', 'values', 'stats' keys
    """
```

#### Spectral-Spatial Reconstruction

```python
@Slot(int, int, result='QVariantMap')
def getSpectrumAt(row: int, col: int) -> Dict:
    """
    Get spectrum at spatial position (TRANS_v3 paradigm).

    Returns:
        Dict with 'x', 'y', 'x_name', 'y_name', 'title' keys
    """

@Slot(result='QVariantMap')
def getAverageSpectrumFromSelection() -> Dict:
    """Get average spectrum from selected blocks."""

@Slot(str, result='QVariantMap')
def computeIntegratedMap(range_str: str) -> Dict:
    """
    Compute integrated intensity map.

    Parameters:
        range_str: "start,end" string for integration range
    """
```

#### Selection

```python
@Slot()
def clearSelection() -> None:
    """Clear block selection."""

@Slot()
def selectAllBlocks() -> None:
    """Select all blocks."""

@Slot(result='QVariantList')
def getSelectedBlocks() -> List[Dict]:
    """Get list of selected blocks with values."""

@Slot(result=int)
def getSelectedBlockCount() -> int:
    """Get number of selected blocks."""
```

---

# 2. Models API

## 2.1 SpectralData Class

**Location**: `src/models/spectral_data.py`

### Constructor

```python
def __init__(self, data: pd.DataFrame,
             independent_var_name: str = None,
             metadata: SpectralMetadata = None,
             topography: np.ndarray = None):
    """
    Create a SpectralData object.

    Parameters:
        data: DataFrame with independent variable as first column
        independent_var_name: Name of x-axis column (auto-detected if None)
        metadata: SpectralMetadata object
        topography: Optional height map array
    """
```

### Properties

```python
@property
def spectra(self) -> pd.DataFrame:
    """Get spectra columns (excluding independent variable)."""

@property
def independent_var(self) -> np.ndarray:
    """Get independent variable values (x-axis)."""

@property
def independent_var_name(self) -> str:
    """Get name of independent variable column."""

@property
def num_spectra(self) -> int:
    """Number of spectra in dataset."""

@property
def num_points(self) -> int:
    """Number of points per spectrum."""

@property
def shape(self) -> Tuple[int, int]:
    """(num_points, num_spectra)."""
```

### Methods

```python
def truncate_range(self, min_val: float, max_val: float) -> 'SpectralData':
    """
    Return new SpectralData truncated to x-axis range.

    Parameters:
        min_val: Minimum x value
        max_val: Maximum x value

    Returns:
        New SpectralData with truncated range
    """

def get_spectrum(self, index: int) -> np.ndarray:
    """
    Get a single spectrum by column index.

    Parameters:
        index: Column index (0-based)

    Returns:
        1D array of spectrum values
    """

def save(self, path: str) -> None:
    """
    Save to CSV file.

    Parameters:
        path: Output file path
    """

@classmethod
def from_csv(cls, path: str, independent_var_name: str = None) -> 'SpectralData':
    """
    Load from CSV file.

    Parameters:
        path: Input file path
        independent_var_name: Name of x-axis column

    Returns:
        SpectralData object
    """
```

---

## 2.2 SpectralMetadata Class

**Location**: `src/models/spectral_data.py`

### Constructor

```python
@dataclass
class SpectralMetadata:
    source_file: str = ""           # Original file path
    source_type: str = "unknown"    # Data type identifier
    num_spectra: int = 0            # Number of spectra
    num_points: int = 0             # Points per spectrum
    dimensions: Tuple[int, int] = (1, 1)  # Spatial dimensions (H, V)
    scan_mode: str = "unknown"      # Acquisition mode
    units: Dict[str, str] = field(default_factory=dict)  # Unit labels
    additional_info: Dict = field(default_factory=dict)  # Extra metadata
```

---

## 2.3 Discretizer Class

**Location**: `src/models/discretizer.py`

### Methods

```python
def discretize_spectral_data(self, spectral_data: SpectralData,
                             block_h: int, block_v: int,
                             ignore_empty_blocks: bool = True,
                             data_type: str = 'spectral') -> Dict:
    """
    Spatially average spectral data.

    Parameters:
        spectral_data: Input SpectralData
        block_h: Horizontal block size
        block_v: Vertical block size
        ignore_empty_blocks: Skip blocks with no data
        data_type: Processing mode

    Returns:
        Dict with 'final' and 'intermediate' SpectralData objects
    """
```

---

## 2.4 MapChannel Class

**Location**: `src/models/map_channel.py`

### Constructor

```python
def __init__(self, data: np.ndarray,
             metadata: ChannelMetadata = None,
             mask: np.ndarray = None):
    """
    Create a MapChannel object.

    Parameters:
        data: 2D numpy array of map values
        metadata: ChannelMetadata object (auto-created if None)
        mask: Optional boolean mask (True = invalid)
    """
```

### Properties

```python
@property
def shape(self) -> Tuple[int, int]:
    """Map dimensions (rows, cols)."""

@property
def name(self) -> str:
    """Channel name."""

@property
def valid_data(self) -> np.ndarray:
    """Data with masked values set to NaN."""
```

### Methods

```python
def normalize(self, vmin=None, vmax=None, percentile=None) -> np.ndarray:
    """
    Normalize data to [0, 1] range.

    Parameters:
        vmin, vmax: Explicit range (optional)
        percentile: (low, high) percentile clipping

    Returns:
        Normalized 2D array
    """

def get_statistics(self, use_mask: bool = True) -> Dict:
    """
    Get channel statistics.

    Returns:
        Dict with min, max, mean, std, median, rms, range
    """

def extract_profile(self, start: Tuple, end: Tuple,
                    width: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract line profile between two points.

    Parameters:
        start: (row, col) start position
        end: (row, col) end position
        width: Averaging width perpendicular to line

    Returns:
        (distance, values) arrays
    """

def add_history(self, operation: str, parameters: Dict) -> None:
    """Record processing operation in history."""

def copy(self) -> 'MapChannel':
    """Create deep copy of channel."""
```

---

## 2.5 MultiChannelMap Class

**Location**: `src/models/map_channel.py`

### Constructor

```python
def __init__(self, metadata: MapMetadata = None):
    """
    Create a MultiChannelMap container.

    Parameters:
        metadata: MapMetadata object (optional)
    """
```

### Class Methods

```python
@classmethod
def from_arrays(cls, arrays: Dict[str, np.ndarray],
                physical_size: Tuple = None,
                units: str = "um") -> 'MultiChannelMap':
    """
    Create from dictionary of arrays.

    Parameters:
        arrays: {'channel_name': 2D_array, ...}
        physical_size: (width, height) in physical units
        units: Physical unit string
    """
```

### Properties

```python
@property
def shape(self) -> Tuple[int, int]:
    """Map dimensions (rows, cols)."""

@property
def channel_names(self) -> List[str]:
    """List of channel names."""

@property
def active_channel(self) -> MapChannel:
    """Currently active channel."""

@property
def has_spectral_link(self) -> bool:
    """Whether spectral data is linked."""

@property
def spectral_points(self) -> int:
    """Number of spectral points (0 if no link)."""
```

### Channel Management

```python
def add_channel(self, name: str, data: np.ndarray,
                channel_type: ChannelType = None,
                units: str = None,
                replace: bool = False) -> MapChannel:
    """Add or replace a channel."""

def remove_channel(self, name: str) -> None:
    """Remove a channel by name."""

def get_channel(self, name: str) -> MapChannel:
    """Get channel by name."""

def set_active_channel(self, name: str) -> None:
    """Set the active channel."""

def duplicate_channel(self, source: str, new_name: str) -> MapChannel:
    """Duplicate a channel with new name."""
```

### Spectral-Spatial Reconstruction

```python
def link_spectral_cube(self, cube: np.ndarray,
                       independent_var: np.ndarray,
                       var_name: str = "x") -> None:
    """
    Link spectral cube for spatial-spectral reconstruction.

    Parameters:
        cube: 3D array (n_spectral, rows, cols)
        independent_var: 1D array (wavenumber, voltage, etc.)
        var_name: Name for independent variable
    """

def unlink_spectral_data(self) -> None:
    """Remove spectral data link."""

def get_spectrum_at(self, row: int, col: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Get spectrum at spatial position.

    Returns:
        (x_values, y_values) tuple
    """

def get_spectra_in_region(self, row_start, row_end, col_start, col_end,
                          mode: str = 'average') -> Tuple:
    """
    Get spectra from rectangular region.

    Parameters:
        mode: 'average' or 'all'

    Returns:
        (x, y) where y is averaged or 2D array
    """

def compute_integrated_map(self, start_val=None, end_val=None,
                          start_idx=None, end_idx=None) -> MapChannel:
    """
    Compute integrated intensity map.

    Parameters:
        start_val, end_val: Integration range in physical units
        start_idx, end_idx: Integration range as indices

    Returns:
        New MapChannel with integrated values
    """
```

### Mask Management

```python
def add_mask(self, name: str, mask: np.ndarray) -> None:
    """Add a named mask."""

def remove_mask(self, name: str) -> None:
    """Remove a mask by name."""

def apply_mask_to_channel(self, mask_name: str, channel_name: str) -> None:
    """Apply a mask to a channel."""
```

### I/O

```python
def save_channel_image(self, channel_name: str, path: Path,
                       colormap: str = 'viridis') -> None:
    """Save channel as PNG image."""

def save_all_channels(self, directory: Path, prefix: str = "",
                      format: str = 'png') -> None:
    """Save all channels to directory."""
```

---

# 3. Workflow API

## 3.1 Workflow Classes

**Location**: `src/backend/workflow_engine.py`

### PortType Enum

```python
class PortType(Enum):
    DATASET = "dataset"         # Full spectral dataset
    FLAT_DATA = "flat_data"     # 2D data (integrated, etc.)
    IMAGE = "image"             # Image file path
    TABLE = "table"             # Tabular data
    NUMBER = "number"           # Single number
    STRING = "string"           # Text value
    INTERVAL_LIST = "intervals" # List of [start, end]
    ANY = "any"                 # Accepts any type
```

### Port Dataclass

```python
@dataclass
class Port:
    id: str                     # Unique identifier
    name: str                   # Display name
    port_type: PortType         # Data type
    is_input: bool              # True for inputs
    required: bool = True       # Connection required?
    default_value: Any = None   # Default if not connected
    description: str = ""       # Tooltip text
    multi_input: bool = False   # Allow multiple connections?
```

### WorkflowNode Dataclass

```python
@dataclass
class WorkflowNode:
    id: str                     # Unique node ID
    tool_name: str              # Tool identifier
    display_name: str           # Display name
    x: float                    # Canvas X position
    y: float                    # Canvas Y position
    inputs: List[Port]          # Input ports
    outputs: List[Port]         # Output ports
    parameters: Dict[str, Any]  # Tool parameters
```

### Connection Dataclass

```python
@dataclass
class Connection:
    id: str                     # Unique connection ID
    source_node_id: str         # Source node
    source_port_id: str         # Source port
    target_node_id: str         # Target node
    target_port_id: str         # Target port
```

### Workflow Class

```python
class Workflow:
    name: str
    nodes: List[WorkflowNode]
    connections: List[Connection]

    def add_node(self, node: WorkflowNode) -> None: ...
    def remove_node(self, node_id: str) -> None: ...
    def add_connection(self, connection: Connection) -> bool: ...
    def remove_connection(self, connection_id: str) -> None: ...
    def validate_connection(self, connection: Connection) -> bool: ...
    def validate(self) -> Tuple[bool, List[str]]: ...
    def get_execution_order(self) -> List[WorkflowNode]: ...
    def to_dict(self) -> Dict: ...
    def from_dict(cls, data: Dict) -> 'Workflow': ...
```

---

## 3.2 Tool Definitions

**Location**: `src/backend/workflow_engine.py` (`TOOL_DEFINITIONS` dict)

### Definition Structure

```python
TOOL_DEFINITIONS = {
    "ToolName": {
        "display_name": str,        # UI display name
        "category": str,            # Category for grouping
        "description": str,         # Tooltip/help text
        "inputs": [                 # Input port definitions
            {
                "id": str,          # Port identifier
                "name": str,        # Display name
                "port_type": str,   # PortType value
                "required": bool,   # Is connection required?
                "multi_input": bool,# Allow multiple connections?
                "description": str  # Tooltip
            }
        ],
        "outputs": [                # Output port definitions
            {
                "id": str,
                "name": str,
                "port_type": str,
                "description": str
            }
        ],
        "parameters": {             # Tool parameters
            "param_name": {
                "type": str,        # int, float, string, bool, select, etc.
                "label": str,       # Display label
                "default": Any,     # Default value
                "min": Number,      # Min value (for numeric)
                "max": Number,      # Max value (for numeric)
                "options": List,    # Options (for select)
                "description": str  # Tooltip
            }
        }
    }
}
```

### Available Tools

| Category | Tool Name | Description |
|----------|-----------|-------------|
| **Input** | `DatasetInput` | Load dataset into workflow |
| **Processing** | `CurveSmoothing` | Apply smoothing |
| | `Derivative` | Calculate derivative |
| | `BaselineCorrection` | Remove baseline |
| | `Integration` | Integrate over intervals |
| | `PeakFinder` | Find peaks with FWHM |
| | `FFT1D` | 1D Fourier transform |
| | `SpatialAverage` | Spatial discretization |
| | `TruncateData` | Limit x-axis range |
| | `DataManipulation` | Equation-based operations |
| **Visualization** | `MapGenerator` | Generate single map |
| | `MapGeneratorAll` | Generate all maps |
| **Output** | `DatasetOutput` | Save dataset result |
| | `MapOutput` | Display/save map |
| | `FlatDataOutput` | Save flat data |

---

## 3.3 WorkflowManager Class

**Location**: `src/backend/workflow_manager.py`

### Signals

```python
workflowCreated(workflowId: str, workflowName: str)
workflowLoaded(workflowId: str)
workflowSaved(workflowId: str)
workflowExecutionStarted(workflowName: str)
workflowExecutionProgress(current: int, total: int, message: str)
workflowExecutionCompleted(workflowName: str, success: bool, errors: List[str])
```

### Slots

```python
@Slot(str, result=str)
def createWorkflow(name: str) -> str:
    """Create new workflow, returns workflow ID."""

@Slot(str, str, float, float, result='QVariantMap')
def addNode(workflow_id: str, tool_name: str, x: float, y: float) -> Dict:
    """Add node to workflow, returns node data."""

@Slot(str, str)
def removeNode(workflow_id: str, node_id: str) -> None:
    """Remove node from workflow."""

@Slot(str, str, str, str, str, result=bool)
def addConnection(workflow_id: str, source_node: str, source_port: str,
                  target_node: str, target_port: str) -> bool:
    """Add connection between nodes."""

@Slot(str, str)
def removeConnection(workflow_id: str, connection_id: str) -> None:
    """Remove connection."""

@Slot(str, str, str, 'QVariant')
def setNodeParameter(workflow_id: str, node_id: str,
                     param_name: str, value: Any) -> None:
    """Set node parameter value."""

@Slot(str)
def executeWorkflow(workflow_id: str) -> None:
    """Execute workflow in background."""

@Slot(str, str)
def saveWorkflow(workflow_id: str, file_path: str) -> None:
    """Save workflow to JSON file."""

@Slot(str, result=str)
def loadWorkflow(file_path: str) -> str:
    """Load workflow from JSON, returns workflow ID."""

@Slot(str, str, result='QVariantList')
def getConnectedInputs(workflow_id: str, node_id: str) -> List[Dict]:
    """Get list of connected inputs for multi-input queue UI."""
```

---

# 4. Data Loaders API

The data loaders module provides standardized interfaces for loading spectroscopy and microscopy data from various instrument formats.

## 4.1 BaseDataLoader Class

**Location**: `src/data_loaders/base_loader.py`

**Purpose**: Abstract base class for all data loaders.

### Abstract Methods

```python
@abstractmethod
def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
    """Load data from a directory of measurement files."""

@abstractmethod
def load_single_file(self, filepath: Path) -> SpectralData:
    """Load data from a single file."""
```

### Utility Methods

```python
def validate_directory(self, directory: Path) -> bool:
    """Check if directory contains supported files."""

def find_files(self, directory: Path, pattern: str = None) -> List[Path]:
    """Find files matching supported extensions."""

def create_metadata(self, dimensions: Tuple, scan_mode: str, units: Dict, **kwargs) -> SpectralMetadata:
    """Create metadata object for loaded data."""

def concatenate_spectra(self, spectra: List[np.ndarray], x: np.ndarray, column_names: List[str] = None) -> pd.DataFrame:
    """Concatenate multiple spectra into a DataFrame."""

def apply_preprocessing(self, df: pd.DataFrame, smooth: bool = False, **kwargs) -> pd.DataFrame:
    """Apply optional preprocessing to loaded data."""

@staticmethod
def detect_data_type(filepath: Path) -> str:
    """Detect data type from filename (iv, didv, d2idv2, unknown)."""
```

---

## 4.2 NanosurfSTSLoader Class

**Location**: `src/data_loaders/nanosurf_sts_loader.py`

**Supported Formats**: `.nid` (Nanosurf STM files)

**Dependencies**: NSFopen (vendored in `src/data_loaders/nsfopen/`, MIT licensed by Nanosurf AG)

### Constructor

```python
def __init__(self):
    """Initialize Nanosurf STS loader."""
```

### Key Methods

```python
def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
    """
    Load STS data from directory of .nid files.

    Features:
        - Automatic meander correction
        - Forward/backward averaging
        - Topography extraction
        - Grid dimension inference
    """

def load_single_file(self, filepath: Path) -> SpectralData:
    """Load data from a single .nid file."""

def extract_dimensions_from_params(self, stm_nid) -> Optional[Tuple[int, int]]:
    """Extract grid dimensions from file parameters."""
```

---

## 4.3 NanosurfSTSEnhancedLoader Class

**Location**: `src/data_loaders/nanosurf_sts_enhanced.py`

**Inherits**: `NanosurfSTSLoader`

Enhanced loader with additional metadata parsing and channel support.

### Additional Features

```python
def parse_nid_metadata(self, stm_nid) -> Dict:
    """Extract comprehensive metadata from NID file."""

def _parse_map0_line(self, map0_str: str) -> Optional[Tuple[int, int]]:
    """Parse Map0 parameter for grid dimensions."""
```

### Channels

Returns data with multiple channels in metadata:
- `Forward`: Forward scan data
- `Backward`: Backward scan data
- `Mixed`: Average of Forward and Backward

---

## 4.4 NeaSpecSNOMLoader Class

**Location**: `src/data_loaders/neaspec_snom_loader.py`

**Supported Formats**: `.txt`, `.dat` (NeaSpec text files)

### Constructor

```python
def __init__(self):
    """Initialize NeaSpec SNOM loader."""
```

### Key Methods

```python
def parse_header(self, lines: List[str]) -> Dict:
    """
    Parse NeaSpec file header to extract metadata.

    Returns:
        Dict with project, description, date, scan_area,
        pixel_area, demodulation, parameters
    """

def parse_data_columns(self, header_line: str) -> List[str]:
    """Parse column names from data header line."""

def load_single_file(self, filepath: Path) -> SpectralData:
    """
    Load SNOM data from a single text file.

    Features:
        - Automatic harmonic channel detection (O0A, O0P, O1A, etc.)
        - Multi-channel data support
        - Grid reconstruction from Row/Column indices
    """

def extract_all_harmonics(self, spectral_data: SpectralData) -> Dict[str, SpectralData]:
    """
    Extract all harmonic channels as separate SpectralData objects.

    Returns:
        Dict mapping channel names to SpectralData objects
    """
```

---

## 4.5 OmicronMatrixSTSLoader Class

**Location**: `src/data_loaders/omicron_mtrx_loader.py`

**Supported Formats**: `.I(V)_mtrx` (Omicron Matrix STS files)

**Based on**: Previous work by Marek (matrixFileHandling.py)

> **See Also**: For comprehensive binary format specification, transfer function details, and troubleshooting, see [`OMICRON_MATRIX_FILE_HANDLING.md`](./OMICRON_MATRIX_FILE_HANDLING.md)

### File Format

- Magic number: `ONTMATRX0101` (12 bytes)
- Block tags: `TLKB` (timestamp), `CSED` (description), `ATAD` (data)
- Data: 32-bit signed integers requiring scaling
- **Important**: Each file contains concatenated forward and backward voltage sweeps

### Forward/Backward Sweep Handling

Each `.I(V)_mtrx` file contains both forward and backward voltage sweeps concatenated together:

| Data Section | Description |
|--------------|-------------|
| First half | Forward sweep (V goes from start to end) |
| Second half | Backward sweep (V goes from end to start) |

The loader automatically:
1. Splits the raw data into two halves
2. Reverses the backward data to align with the forward direction
3. Creates three channels: **Forward**, **Backward**, and **Mixed** (average)

### Constructor

```python
def __init__(self):
    """Initialize Omicron Matrix STS loader."""
```

### Key Methods

```python
def load_single_file(self, filepath: Path) -> SpectralData:
    """
    Load data from a single .I(V)_mtrx file.

    Returns SpectralData with:
    - Main DataFrame containing V, Forward, Backward, Mixed columns
    - sweep_channels dict in metadata with separate DataFrames for each channel
    """

def load_from_directory(self, directory: Path, progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
    """
    Load STS data from directory of .I(V)_mtrx files.

    Returns:
    - Mixed channel as main dataset
    - Forward/Backward/Mixed channels in metadata.sweep_channels
    """

def _parse_iv_file(self, filepath: Path) -> Dict[str, Any]:
    """
    Parse I(V)_mtrx file to extract voltage and current data.

    Returns dict with keys:
    - 'V': voltage array (for half-sweep)
    - 'forward': forward sweep current data
    - 'backward': backward sweep current data (reordered)
    - 'mixed': average of forward and backward
    - 'n_points': number of points per sweep
    """

def _find_header(self, filepath: Path) -> Optional[Path]:
    """Find the associated .mtrx header file."""

def _parse_header(self, header_path: Path, target_file: Path):
    """Parse .mtrx header file to extract parameters."""

def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
    """Scale raw data using transfer function parameters."""
```

### Accessing Sweep Channels

```python
# Load single file
loader = OmicronMatrixSTSLoader()
data = loader.load_single_file(path)

# Access main data (has all channels)
print(data.data.columns)  # ['V', 'Forward', 'Backward', 'Mixed']

# Access individual channels from metadata
sweep_channels = data.metadata.additional_info['sweep_channels']
forward_df = sweep_channels['Forward']
backward_df = sweep_channels['Backward']
mixed_df = sweep_channels['Mixed']
```

### Transfer Function Scaling

The loader supports both `TFF_Linear1D` and `TFF_MultiLinear1D` transfer functions:

```python
# TFF_Linear1D: (data - offset) / factor
# TFF_MultiLinear1D: (Raw_1 - PreOffset) * (data - Offset) / (NeutralFactor * PreFactor)
```

---

## 4.6 OmicronFlatLoader Class

**Location**: `src/data_loaders/omicron_flat_loader.py`

**Supported Formats**: `.Z_flat`, `.I_flat` (Omicron Matrix flat/image files)

**Based on**: Previous work by Marek (matrixFileHandling.py)

> **See Also**: For comprehensive binary format specification and troubleshooting, see [`OMICRON_MATRIX_FILE_HANDLING.md`](./OMICRON_MATRIX_FILE_HANDLING.md)

### File Format

- Magic number: `FLAT0100` (8 bytes)
- Self-contained metadata in UTF-16 format
- Transfer function for data scaling
- Image data as 32-bit signed integers

### Constructor

```python
def __init__(self):
    """Initialize Omicron Flat loader."""
```

### Key Methods

```python
def load_topography(self, filepath: Path) -> TopographyData:
    """Load topography directly from a .Z_flat file."""

def load_single_file(self, filepath: Path) -> SpectralData:
    """Load data (returns SpectralData with topography attached)."""

def _parse_flat_metadata(self, content: bytes):
    """Parse metadata from flat file content."""

def _get_image_dimensions(self, content: bytes) -> Tuple[int, int]:
    """Extract image dimensions from file content."""

def _extract_image_data(self, content: bytes, width: int, height: int) -> np.ndarray:
    """Extract raw image data from file content."""

def _scale_image_data(self, raw_data: np.ndarray) -> np.ndarray:
    """Apply transfer function scaling to raw image data."""
```

### Alias

```python
class OmicronImageLoader(OmicronFlatLoader):
    """Convenience alias for loading Omicron STM images."""
    pass
```

---

## 4.7 Adding a New Loader

### Step 1: Create the Loader Class

```python
from src.data_loaders.base_loader import BaseDataLoader
from src.models.spectral_data import SpectralData, SpectralMetadata
from src.models.topography_data import TopographyData

class MyNewLoader(BaseDataLoader):
    def __init__(self):
        super().__init__()
        self.supported_extensions = ['.myext']
        self.loader_type = 'my_loader'

    def load_from_directory(self, directory: Path, progress_callback=None):
        # Implementation
        pass

    def load_single_file(self, filepath: Path):
        # Implementation
        pass
```

### Step 2: Register in __init__.py

```python
# src/data_loaders/__init__.py
from .my_new_loader import MyNewLoader

__all__ = [
    # ... existing loaders
    'MyNewLoader',
]
```

### Step 3: Add to Backend

```python
# In app_backend.py __init__
from src.data_loaders.my_new_loader import MyNewLoader

try:
    self.my_loader = MyNewLoader()
except Exception as e:
    self.my_loader = None

# In _do_load_file method
elif filepath.suffix == '.myext':
    if not self.my_loader:
        raise RuntimeError("My loader not available")
    spectral_data = self.my_loader.load_single_file(filepath)
    # ... handle result
```

### Step 4: Update Import Dialog

```qml
// In ImportMeasurementDialog.qml
nameFilters: [
    "All Measurement Files (*.nid *.txt *.I(V)_mtrx *.Z_flat *.myext)",
    // ... existing filters
    "My Format Files (*.myext)",
]
```

---

# 5. QML-Python Interface

## 5.1 Context Properties

The following objects are available globally in QML:

| Property | Type | Description |
|----------|------|-------------|
| `backend` | AppBackend | Main backend interface |
| `workflowManager` | WorkflowManager | Workflow operations |
| `dockManager` | DockManager | Layout persistence |

## 5.2 Calling Python from QML

```qml
// Call a slot
backend.smoothCurves(datasetName, 11, 3, "savgol")

// Access a property
if (backend.projectReady) { ... }

// Connect to a signal
Connections {
    target: backend
    function onDataLoaded(name) {
        console.log("Loaded:", name)
    }
}
```

## 5.3 Python to QML Communication

```python
# Emit signal from Python
self.dataLoaded.emit(dataset_name)

# Update property (triggers QML binding update)
self.status = "Processing..."
```

---

# Appendix: Adding a New Tool

## Step 1: Define the Tool

Add to `TOOL_DEFINITIONS` in `workflow_engine.py`:

```python
"MyNewTool": {
    "display_name": "My New Tool",
    "category": "Processing",
    "description": "What the tool does",
    "inputs": [
        {"id": "dataset", "name": "Dataset", "port_type": "dataset", "required": True}
    ],
    "outputs": [
        {"id": "result", "name": "Result", "port_type": "dataset"}
    ],
    "parameters": {
        "param1": {"type": "int", "label": "Parameter", "default": 10}
    }
}
```

## Step 2: Implement the Logic

Add method to `ToolImplementations` in `tool_implementations.py`:

```python
def my_new_tool(self, task, dataset_name: str, param1: int) -> str:
    """Implementation details..."""
    pass
```

## Step 3: Add Executor Handler

Add case to `_execute_node()` in `workflow_manager.py`:

```python
elif tool_name == "MyNewTool":
    dataset = inputs.get('dataset')
    if dataset:
        # Call implementation
        result = self.app_backend.my_new_tool(...)
        outputs['result'] = result
```

## Step 4: Add QML Wrapper (Optional)

If the tool should be available outside workflows, add slot to `AppBackend`:

```python
@Slot(str, int)
def myNewTool(self, dataset_name: str, param1: int):
    self.worker_manager.submit(
        name=f"My New Tool {dataset_name}",
        operation=self._my_new_tool_impl,
        dataset_name=dataset_name,
        param1=param1
    )
```

---

# 6. QML Canvas Widgets API

## 6.1 QmlGraphCanvas Class

**Location**: `src/widgets/qml_graph_canvas.py`

**Inheritance**: `QQuickPaintedItem`

**Purpose**: Matplotlib-based graph rendering widget for QML with interactive features.

### Signals

```python
# Mouse interaction signals
cursorMoved = Signal(float, float, arguments=['x', 'y'])
pointClicked = Signal(float, float, arguments=['x', 'y'])
rangeSelected = Signal(float, float, arguments=['x1', 'x2'])

# Data change notification
dataChanged = Signal()
curvesChanged = Signal()

# Selection signals
curveSelected = Signal(int, arguments=['curveId'])
legendClicked = Signal(int, arguments=['curveId'])
```

### Slots

```python
@Slot(str, 'QVariantList', 'QVariantList', str, float, result=int)
def addCurve(self, label: str, x_data: list, y_data: list,
             color: str = "#5BCEFA", linewidth: float = 1.5) -> int:
    """
    Add a curve to the graph.

    Returns:
        int: Curve ID for future reference
    """

@Slot(int)
def removeCurve(self, curve_id: int) -> None:
    """Remove a curve by ID."""

@Slot()
def clearCurves(self) -> None:
    """Remove all curves."""

@Slot(int, str, 'QVariantMap', result='QVariantMap')
def applyCurveOperation(self, curve_id: int, operation: str,
                        params: dict) -> dict:
    """
    Apply mathematical operation to a curve.

    Operations:
        - 'derivative': Calculate numerical derivative
        - 'smooth': Apply smoothing (params: window_size, poly_order)
        - 'integrate': Calculate integral
        - 'fft': Fast Fourier Transform
        - 'normalize': Normalize to [0, 1]

    Returns:
        Dict with 'success', 'new_curve_id', 'message' keys
    """

@Slot()
def resetView(self) -> None:
    """Reset zoom and pan to show all data."""

@Slot(float)
def zoomIn(self, factor: float = 1.2) -> None:
    """Zoom in by factor."""

@Slot(float)
def zoomOut(self, factor: float = 1.2) -> None:
    """Zoom out by factor."""

@Slot()
def autoScale(self) -> None:
    """Auto-scale axes to fit all data."""

@Slot(str, str)
def setAxisLabels(self, x_label: str, y_label: str) -> None:
    """Set axis labels."""

@Slot(str)
def setTitle(self, title: str) -> None:
    """Set graph title."""

@Slot(bool)
def setLegendVisible(self, visible: bool) -> None:
    """Show or hide legend."""

@Slot(str, result=bool)
def exportImage(self, file_path: str) -> bool:
    """Export graph as PNG image."""
```

### Properties (QML-accessible)

```python
@Property(int)
def curveCount(self) -> int:
    """Number of curves in graph."""

@Property(bool)
def hasData(self) -> bool:
    """Whether any curves are present."""

@Property('QVariantList')
def curveLabels(self) -> list:
    """List of curve labels."""
```

---

## 6.2 QmlMapCanvas Class

**Location**: `src/widgets/qml_map_canvas.py`

**Inheritance**: `QQuickPaintedItem`

**Purpose**: Matplotlib-based 2D map/image rendering with TRANS_v3-style block selection.

### Signals

```python
# Click signals
pointClicked = Signal(float, float, int, int, float,
                      arguments=['x', 'y', 'row', 'col', 'value'])
profileDrawn = Signal(float, float, float, float,
                      arguments=['x1', 'y1', 'x2', 'y2'])

# Block selection (TRANS_v3 paradigm)
blockSelected = Signal(int, int, float, bool,
                       arguments=['blockRow', 'blockCol', 'value', 'isSelected'])
selectionChanged = Signal(int, arguments=['blockCount'])

# Cursor tracking
cursorMoved = Signal(float, float, float,
                     arguments=['x', 'y', 'value'])

# Data notification
dataChanged = Signal()
```

### Slots

```python
@Slot('QVariantList', int, int)
def setMapData(self, data: list, rows: int, cols: int) -> None:
    """Set 2D map data from flattened list."""

@Slot(str)
def setColormap(self, colormap_name: str) -> None:
    """Set colormap (viridis, plasma, inferno, magma, etc.)."""

@Slot(float, float)
def setColorRange(self, vmin: float, vmax: float) -> None:
    """Set color scale range."""

@Slot()
def autoColorRange(self) -> None:
    """Auto-scale color range to data min/max."""

@Slot(bool)
def setColorbarVisible(self, visible: bool) -> None:
    """Show or hide colorbar."""

@Slot(int, int, bool)
def selectBlock(self, row: int, col: int, selected: bool) -> None:
    """Select or deselect a block."""

@Slot()
def clearSelection(self) -> None:
    """Clear all block selections."""

@Slot()
def selectAll(self) -> None:
    """Select all blocks."""

@Slot(result='QVariantList')
def getSelectedBlocks(self) -> list:
    """Get list of selected block coordinates."""

@Slot(int, int, result='QVariantMap')
def getSpectrumAt(self, row: int, col: int) -> dict:
    """
    Get spectrum at spatial position (requires linked spectral cube).

    Returns:
        Dict with 'x', 'y', 'label' keys
    """

@Slot(str, result=bool)
def exportImage(self, file_path: str) -> bool:
    """Export map as PNG image."""
```

---

## 6.3 QmlProfileCanvas Class

**Location**: `src/widgets/qml_profile_canvas.py`

**Inheritance**: `QQuickPaintedItem`

**Purpose**: Lightweight 1D profile/spectrum plotting widget.

### Signals

```python
cursorMoved = Signal(float, float, arguments=['x', 'y'])
pointClicked = Signal(float, float, arguments=['x', 'y'])
rangeSelected = Signal(float, float, arguments=['x1', 'x2'])
dataChanged = Signal()
```

### Slots

```python
@Slot('QVariantList', 'QVariantList', str)
def setData(self, x_data: list, y_data: list, label: str = "") -> None:
    """Set profile data."""

@Slot(str, str)
def setAxisLabels(self, x_label: str, y_label: str) -> None:
    """Set axis labels."""

@Slot()
def clear(self) -> None:
    """Clear all data."""

@Slot()
def autoScale(self) -> None:
    """Auto-scale axes."""
```

---

# 7. Preferences and Settings API

## 7.1 PreferencesManager Class

**Location**: `src/backend/preferences_manager.py`

**Inheritance**: `QObject`

**Purpose**: Manages application preferences including color schemes and font settings.

### Signals

```python
colorSchemeChanged = Signal(str)  # scheme_name
preferencesLoaded = Signal()
preferencesSaved = Signal()
```

### Slots

```python
@Slot(result='QVariantMap')
def getCurrentScheme(self) -> dict:
    """
    Get current color scheme.

    Returns:
        Dict with 'name', 'colors', 'font' keys
        colors: {bgDark, bgDarker, bgMedium, bgLight,
                accentPrimary, accentSecondary, accentTertiary,
                textPrimary, textMuted, borderColor, error}
        font: {family, sizeSmall, sizeMedium, sizeLarge, sizeHeader, sizeTitle}
    """

@Slot(result=str)
def getCurrentSchemeName(self) -> str:
    """Get name of current color scheme."""

@Slot(str)
def setColorScheme(self, scheme_name: str) -> None:
    """
    Set color scheme by name.

    Available schemes:
        - "Trans Pride" (default)
        - "Dark Mode"
        - "Light Mode"
        - "High Contrast"
    """

@Slot(result='QVariantList')
def getAvailableSchemes(self) -> list:
    """Get list of available scheme names."""

@Slot()
def savePreferences(self) -> None:
    """Save preferences to disk."""

@Slot()
def loadPreferences(self) -> None:
    """Load preferences from disk."""
```

---

# 8. QML Component API

## 8.1 UnifiedWorkspace Component

**Location**: `src/qml/components/UnifiedWorkspace.qml`

**Purpose**: Main tileable workspace with dockable panels and floating entities.

### Properties

```qml
// Mode control
property string currentMode: "sts"  // "sts", "snom", "map", "workflow"

// Panel visibility
property bool showLeftPanel: true
property bool showRightPanel: false
property bool showTopPanel: false
property bool showBottomPanel: false

// Panel collapsed states
property bool leftCollapsed: false
property bool rightCollapsed: false
property bool topCollapsed: false
property bool bottomCollapsed: false

// Panel sizes
property real leftPanelWidth: 280
property real rightPanelWidth: 300
property real topPanelHeight: 200
property real bottomPanelHeight: 200

// Content components (set by parent)
property Component leftPanelContent: null
property Component rightPanelContent: null
property Component centerContent: null

// External references
property var backend: null
property var workflowManager: null
```

### Signals

```qml
signal modeChanged(string newMode)
signal layoutChanged()
signal floatingEntityAdded(var entity)
signal floatingEntityRemoved(string entityId)
```

### Functions

```javascript
// Mode management
function applyModePreset(mode) { ... }
function configurePanelsForMode(mode) { ... }

// Floating entity management
function addFloatingEntity(entityId, entityType, component, x, y, width, height, data) { ... }
function removeFloatingEntity(entityId) { ... }
function bringEntityToFront(entityId) { ... }
function clearFloatingEntities() { ... }

// Entity creation convenience functions
function createGraphEntity(title, x, y, width, height, curves, xLabel, yLabel) { ... }
function createTableEntity(title, x, y, width, height, tableData, columnHeaders) { ... }
function createMapEntity(title, x, y, width, height, mapData, mapWidth, mapHeight) { ... }

// Embedded window management
function openToolWindow(toolName, config) { ... }
function closeEmbeddedWindow(windowId) { ... }
function closeAllEmbeddedWindows() { ... }
function tileEmbeddedWindows() { ... }
function cascadeEmbeddedWindows() { ... }
function getEmbeddedWindowManager() { ... }

// Layout state
function getLayoutState() { ... }
function restoreLayoutState(state) { ... }
```

---

## 8.2 WindowManager Component

**Location**: `src/qml/components/WindowManager.qml`

**Purpose**: Manages embedded windows within the workspace canvas.

### Properties

```qml
property var backend: null
property int windowCount: 0
```

### Signals

```qml
signal windowClosed(string windowId)
signal windowActivated(string windowId)
signal windowMinimized(string windowId)
signal windowMaximized(string windowId)
```

### Functions

```javascript
// Window creation
function createToolWindow(toolName, component, config) { ... }
function createGraphWindow(title, component, config) { ... }
function createTableWindow(title, component, config) { ... }
function createImageWindow(title, component, config) { ... }

// Window management
function closeWindow(windowId) { ... }
function closeAllWindows() { ... }
function activateWindow(windowId) { ... }
function minimizeWindow(windowId) { ... }
function maximizeWindow(windowId) { ... }
function restoreWindow(windowId) { ... }

// Layout
function tileWindows() { ... }
function cascadeWindows() { ... }

// Query
function getWindowCount() { ... }
function getWindowIds() { ... }
```

---

## 8.3 WorkflowCanvas Component

**Location**: `src/qml/workflow/WorkflowCanvas.qml`

**Purpose**: Node-based workflow editor canvas.

### Properties

```qml
property string workflowId: ""
property var workflowManager: null
property var nodes: []
property var connections: []

// Canvas state
property real canvasScale: 1.0
property real canvasOffsetX: 0
property real canvasOffsetY: 0
property var selectedNode: null
property var selectedConnection: null

// Multi-selection
property var selectedNodes: []
property var clipboard: []
```

### Signals

```qml
signal nodeSelected(var node)
signal nodeDeselected()
signal connectionCreated(string sourceNode, string sourcePort,
                        string targetNode, string targetPort)
signal connectionRemoved(string connectionId)
signal nodeRemoved(string nodeId)
signal nodeAdded(string nodeId, string toolName, real x, real y)
signal statusMessage(string message, color messageColor)
signal nodeParameterChanged(string nodeId, string paramName, var value)
```

### Functions

```javascript
// Node management
function addNode(toolName, x, y) { ... }
function deleteNode(nodeId) { ... }
function deleteSelectedNodes() { ... }

// Connection management
function addConnection(sourceNode, sourcePort, targetNode, targetPort) { ... }
function removeConnection(connectionId) { ... }

// Selection
function selectAllNodes() { ... }
function clearSelection() { ... }
function copySelectedNodes() { ... }
function pasteNodes() { ... }

// View control
function resetView() { ... }
function refreshWorkflow() { ... }

// Port utilities
function getPortColor(portType) { ... }
function getNodeById(nodeId) { ... }
```

---

*API Reference for TRANS-QML*
*Last updated: December 2025*
