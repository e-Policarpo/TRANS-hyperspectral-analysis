# Omicron Matrix File Handling Documentation

This document provides comprehensive technical documentation for the Omicron Matrix STM/STS file format handling in TRANS-QML, based on previous work by Marek (matrixFileHandling.py, June 2022).

---

## Table of Contents

1. [Overview](#1-overview)
2. [File Formats](#2-file-formats)
3. [Binary Format Specification](#3-binary-format-specification)
4. [Data Loaders API](#4-data-loaders-api)
5. [Forward/Backward Sweep Handling](#5-forwardbackward-sweep-handling)
6. [Transfer Function Scaling](#6-transfer-function-scaling)
7. [Usage Examples](#7-usage-examples)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Overview

### Background

The Omicron Matrix file format is a proprietary binary format used by Omicron (now Scienta Omicron) Matrix STM/STS systems. TRANS-QML includes loaders for:

- **I(V)_mtrx**: Scanning Tunneling Spectroscopy (STS) current-voltage curves
- **I(Z)_mtrx**: Current-distance spectroscopy
- **Z(V)_mtrx**: Height-voltage spectroscopy
- **Z_flat**: Processed (flattened) topography images
- **I_flat**: Current channel images

### Credits

Based on previous work by Marek (June 2022):
- Original implementation: `matrixFileHandling.py`
- Reverse-engineered file format specification
- Transfer function scaling algorithms

### File Locations

| File | Location | Purpose |
|------|----------|---------|
| `omicron_mtrx_loader.py` | `src/data_loaders/` | STS spectroscopy files |
| `omicron_flat_loader.py` | `src/data_loaders/` | Flat/image files |

---

## 2. File Formats

### 2.1 I(V)_mtrx Files (STS Spectroscopy)

**Purpose**: Contains current-voltage (I-V) spectroscopy data from single point or grid measurements.

**File naming convention**:
```
<experiment>--<index>_<point>.I(V)_mtrx
Example: MnBi2Te4_2024-01-15--1_1.I(V)_mtrx
```

**Data structure**:
- Each file contains **both forward AND backward** voltage sweeps concatenated
- First half: Forward sweep (V increases from V_start to V_end)
- Second half: Backward sweep (V decreases from V_end to V_start)
- Data stored as 32-bit signed integers

### 2.2 Z_flat Files (Topography)

**Purpose**: Contains processed (plane-leveled, flattened) STM topography images.

**File naming convention**:
```
<experiment>--<index>_<channel>.Z_flat
Example: MnBi2Te4_2024-01-15--1_1.Z_flat
```

**Data structure**:
- Self-contained metadata in UTF-16 format
- Transfer function parameters embedded
- Image data as 32-bit signed integers

### 2.3 Associated Header Files

**mtrx files**: Parameter files containing voltage ranges, scaling factors, and metadata.

**File naming convention**:
```
<experiment>_0001.mtrx
```

---

## 3. Binary Format Specification

### 3.1 I(V)_mtrx Format

```
Offset    Size    Description
────────────────────────────────────────────────────────
0x00      12      Magic number: "ONTMATRX0101"
0x0C      4       Tag: "TLKB" (timestamp block)
0x10      4       File size
0x14      4       Unix timestamp
0x18      8       Padding
0x20      4       Tag: "CSED" (description block)
0x24      4       Block size
0x28      N       Description data
...       4       Tag: "ATAD" (data block)
...       4       Data size in bytes
...       N       Raw data (32-bit signed integers)
```

### 3.2 Tag Types

| Tag | Name | Description |
|-----|------|-------------|
| `TLKB` | Timestamp | Unix timestamp of measurement |
| `CSED` | Description | Text description block |
| `ATAD` | Data | Raw measurement data |
| `APEE` | Parameters | Measurement parameters |
| `YSCC` | Channel Config | Channel/transfer function configuration |
| `FERB` | File Reference | Reference to data file |

### 3.3 Z_flat Format

```
Offset    Size    Description
────────────────────────────────────────────────────────
0x00      8       Magic number: "FLAT0100"
0x08      N       Metadata (UTF-16 strings, variable length)
...       ...     Transfer function parameters
...       ...     Axis information
END-N*4   N*4     Image data (N = width × height, 32-bit integers)
```

### 3.4 Header File (mtrx) Format

```
Offset    Size    Description
────────────────────────────────────────────────────────
0x00      12      Magic number: "ONTMATRX0101"
...       ...     APEE blocks (parameters)
...       ...     YSCC blocks (channel config)
...       ...     FERB blocks (file references)
```

---

## 4. Data Loaders API

### 4.1 OmicronMatrixSTSLoader

**Class**: `src/data_loaders/omicron_mtrx_loader.py`

```python
class OmicronMatrixSTSLoader(BaseDataLoader):
    """Loader for Omicron Matrix STS data."""

    MAGIC_NUMBER = b'ONTMATRX0101'

    def __init__(self):
        self.supported_extensions = ['.I(V)_mtrx']
        self.loader_type = 'omicron_matrix_sts'
```

#### Key Methods

```python
def load_from_directory(self, directory: Path,
                        progress_callback=None) -> Tuple[SpectralData, Optional[TopographyData]]:
    """
    Load STS data from directory of .I(V)_mtrx files.

    Returns:
        SpectralData with Mixed channel as main data
        Forward/Backward/Mixed channels in metadata.sweep_channels
    """

def load_single_file(self, filepath: Path) -> SpectralData:
    """
    Load single .I(V)_mtrx file.

    Returns SpectralData with columns:
        - V: Voltage array
        - Forward: Forward sweep current
        - Backward: Backward sweep current
        - Mixed: Average of Forward and Backward
    """

def _parse_iv_file(self, filepath: Path) -> Dict[str, Any]:
    """
    Parse I(V)_mtrx file.

    Returns:
        {
            'V': voltage array (half-sweep length),
            'forward': forward current data,
            'backward': backward current data (reordered),
            'mixed': average of forward and backward,
            'n_points': points per sweep
        }
    """

def _parse_header(self, header_path: Path, target_file: Path):
    """Parse .mtrx header file for voltage range and scaling."""

def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
    """Apply transfer function scaling to raw data."""

def _get_voltage_array(self, current_data: np.ndarray) -> np.ndarray:
    """Get voltage array from parameters or use default."""
```

### 4.2 OmicronFlatLoader

**Class**: `src/data_loaders/omicron_flat_loader.py`

```python
class OmicronFlatLoader(BaseDataLoader):
    """Loader for Omicron Matrix Flat STM images."""

    MAGIC_NUMBER = b'FLAT0100'

    def __init__(self):
        self.supported_extensions = ['.Z_flat', '.I_flat']
        self.loader_type = 'omicron_flat'
```

#### Key Methods

```python
def load_topography(self, filepath: Path) -> TopographyData:
    """
    Load topography directly from .Z_flat file.

    Returns:
        TopographyData with scaled height values
    """

def _load_flat_file(self, filepath: Path) -> Optional[TopographyData]:
    """
    Load and parse a .Z_flat or .I_flat file.

    Steps:
        1. Verify magic number
        2. Parse metadata and transfer function
        3. Extract image dimensions
        4. Extract raw image data
        5. Apply transfer function scaling
    """

def _parse_flat_metadata(self, content: bytes):
    """Parse UTF-16 encoded metadata from file."""

def _parse_transfer_function(self, content: bytes, start_pos: int):
    """Extract transfer function parameters (NeutralFactor, Offset, etc.)."""

def _get_image_dimensions(self, content: bytes) -> Tuple[Optional[int], Optional[int]]:
    """Extract image width and height from metadata."""

def _extract_image_data(self, content: bytes, width: int, height: int) -> Optional[np.ndarray]:
    """Extract raw 32-bit integer image data."""

def _scale_image_data(self, raw_data: np.ndarray) -> np.ndarray:
    """Apply transfer function to convert raw integers to physical units."""
```

---

## 5. Forward/Backward Sweep Handling

### 5.1 Data Layout

Each `.I(V)_mtrx` file contains both sweep directions concatenated:

```
┌─────────────────────────────────────────────────────────┐
│              Raw Data in File (2N points)               │
├─────────────────────────┬───────────────────────────────┤
│     Forward Sweep       │      Backward Sweep           │
│     (N points)          │      (N points)               │
│                         │                               │
│  V: start → end         │  V: end → start               │
│  I[0], I[1], ..., I[N-1]│  I[N], I[N+1], ..., I[2N-1]  │
└─────────────────────────┴───────────────────────────────┘
```

### 5.2 Processing Steps

```python
# 1. Read raw data (2N points)
n_points_total = datasize // 4
raw_data = np.array(unpack(f'<{n_points_total}i', data), dtype=np.float64)

# 2. Apply scaling
scaled_data = self._scale_data(raw_data)

# 3. Split into forward and backward
n_points = n_points_total // 2
forward_data = scaled_data[:n_points]
backward_data_raw = scaled_data[n_points:n_points * 2]

# 4. Reverse backward to align with forward direction
backward_data = backward_data_raw[::-1]

# 5. Calculate mixed (average)
mixed_data = (forward_data + backward_data) / 2
```

### 5.3 Why Reverse Backward Data?

The backward sweep is recorded as voltage decreases (V_end → V_start), so the data indices are reversed compared to the forward sweep. By reversing the backward data, both arrays align to the same voltage points:

```
Forward:   V[0]=V_start,  V[1],  ...,  V[N-1]=V_end
Backward:  V[0]=V_start,  V[1],  ...,  V[N-1]=V_end  (after reversal)
```

### 5.4 Channel Access

```python
# Load single file
loader = OmicronMatrixSTSLoader()
data = loader.load_single_file(filepath)

# Main DataFrame has all channels
print(data.data.columns)
# Output: ['V', 'Forward', 'Backward', 'Mixed']

# Access individual channels
V = data.data['V'].values
forward = data.data['Forward'].values
backward = data.data['Backward'].values
mixed = data.data['Mixed'].values

# Or from metadata (for directory loading)
sweep_channels = data.metadata.additional_info.get('sweep_channels', {})
forward_df = sweep_channels.get('Forward')
backward_df = sweep_channels.get('Backward')
mixed_df = sweep_channels.get('Mixed')
```

---

## 6. Transfer Function Scaling

### 6.1 Transfer Function Types

#### TFF_Linear1D

Simple linear scaling:

```
scaled = (raw_data - Offset) / Factor
```

Parameters:
- `Offset`: Zero-point offset
- `Factor`: Scaling factor (ADC counts per unit)

#### TFF_MultiLinear1D

Multi-parameter linear scaling:

```
scaled = (Raw_1 - PreOffset) × (raw_data - Offset) / (NeutralFactor × PreFactor)
```

Parameters:
- `Raw_1`: Reference raw value
- `PreOffset`: Pre-amplifier offset
- `Offset`: ADC offset
- `NeutralFactor`: Neutral scaling factor
- `PreFactor`: Pre-amplifier gain factor

### 6.2 Parameter Extraction

Parameters are extracted from the `.mtrx` header file:

```python
def _parse_apee_block(self, apee: bytes):
    """
    Parse APEE (parameter) block.

    Structure:
        - num_groups: int32
        - For each group:
            - groupname: length-prefixed UTF-16
            - num_params: int32
            - For each parameter:
                - param_name: length-prefixed UTF-16
                - unit: length-prefixed UTF-16
                - value: typed value (LOOB, GNOL, BUOD, GRTS)
    """
```

### 6.3 Value Types

| Tag | Type | Size | Description |
|-----|------|------|-------------|
| `LOOB` | Boolean | 4 bytes | True/False |
| `GNOL` | Long | 4 bytes | 32-bit signed integer |
| `BUOD` | Double | 8 bytes | 64-bit float |
| `GRTS` | String | Variable | Length-prefixed UTF-16 |

### 6.4 Scaling Implementation

```python
def _scale_data(self, raw_data: np.ndarray) -> np.ndarray:
    """Scale raw data using transfer function parameters."""

    for key in self.parameter.get('XFER', {}):
        xfer = self.parameter['XFER'][key]
        xfer_params = xfer[2]  # Parameter dictionary

        if xfer[0] == 'TFF_Linear1D':
            # Linear scaling
            offset = xfer_params.get('Offset', [0])[0]
            factor = xfer_params.get('Factor', [1])[0]
            return (raw_data - offset) / factor

        else:
            # MultiLinear scaling
            raw_1 = xfer_params.get('Raw_1', [1])[0]
            pre_offset = xfer_params.get('PreOffset', [0])[0]
            offset = xfer_params.get('Offset', [0])[0]
            neutral_factor = xfer_params.get('NeutralFactor', [1])[0]
            pre_factor = xfer_params.get('PreFactor', [1])[0]

            return (raw_1 - pre_offset) * (raw_data - offset) / (neutral_factor * pre_factor)

    # Default: assume nA scale
    return raw_data * 1e-9
```

---

## 7. Usage Examples

### 7.1 Load Single STS File

```python
from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader

loader = OmicronMatrixSTSLoader()
data = loader.load_single_file("path/to/spectrum.I(V)_mtrx")

# Access data
V = data.data['V'].values
I_forward = data.data['Forward'].values
I_backward = data.data['Backward'].values
I_mixed = data.data['Mixed'].values

# Plot
import matplotlib.pyplot as plt
plt.figure(figsize=(10, 6))
plt.plot(V, I_forward * 1e9, label='Forward', alpha=0.7)
plt.plot(V, I_backward * 1e9, label='Backward', alpha=0.7)
plt.plot(V, I_mixed * 1e9, label='Mixed', linewidth=2)
plt.xlabel('Voltage (V)')
plt.ylabel('Current (nA)')
plt.legend()
plt.title('STS I-V Curve')
plt.show()
```

### 7.2 Load STS Grid from Directory

```python
from src.data_loaders.omicron_mtrx_loader import OmicronMatrixSTSLoader
from pathlib import Path

loader = OmicronMatrixSTSLoader()

def progress(current, total, message):
    print(f"[{current}/{total}] {message}")

spectral_data, topography = loader.load_from_directory(
    Path("path/to/sts_grid/"),
    progress_callback=progress
)

print(f"Loaded {spectral_data.num_spectra} spectra with {spectral_data.num_points} points each")
print(f"Grid dimensions: {spectral_data.metadata.dimensions}")

# Access sweep channels
sweep_channels = spectral_data.metadata.additional_info.get('sweep_channels', {})
forward_df = sweep_channels['Forward']
backward_df = sweep_channels['Backward']
mixed_df = sweep_channels['Mixed']
```

### 7.3 Load Topography Image

```python
from src.data_loaders.omicron_flat_loader import OmicronFlatLoader

loader = OmicronFlatLoader()
topography = loader.load_topography("path/to/image.Z_flat")

# Access data
z_data = topography.data  # 2D numpy array in meters
print(f"Image size: {z_data.shape}")
print(f"Height range: {z_data.min()*1e12:.2f} pm to {z_data.max()*1e12:.2f} pm")

# Plot
import matplotlib.pyplot as plt
plt.figure(figsize=(8, 8))
plt.imshow(z_data * 1e12, cmap='afmhot', origin='lower')
plt.colorbar(label='Height (pm)')
plt.title('STM Topography')
plt.show()
```

### 7.4 Integration with TRANS-QML Backend

```python
# In app_backend.py

@Slot(str, str)
def loadMeasurement(self, file_path: str, data_format: str):
    """Load measurement file."""

    filepath = Path(file_path)

    if filepath.suffix == '.I(V)_mtrx' or data_format == 'omicron_sts':
        if self.omicron_sts_loader is None:
            raise RuntimeError("Omicron STS loader not available")

        # Single file
        spectral_data = self.omicron_sts_loader.load_single_file(filepath)

    elif filepath.suffix in ['.Z_flat', '.I_flat'] or data_format == 'omicron_flat':
        if self.omicron_flat_loader is None:
            raise RuntimeError("Omicron Flat loader not available")

        topography = self.omicron_flat_loader.load_topography(filepath)
        # Handle topography...
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Invalid Magic Number

```
Error: Invalid magic number in <file>
```

**Cause**: File is corrupted or not an Omicron Matrix file.

**Solution**: Verify file integrity, check if it's the correct file type.

#### No Transfer Function Found

```
Warning: No transfer function found, using default scaling
```

**Cause**: Header file not found or couldn't parse transfer function.

**Solution**:
1. Ensure the `_0001.mtrx` header file is in the same directory
2. Check file permissions
3. Data will still load with default scaling (nA for current, pm for height)

#### Odd Number of Points

```
Warning: Odd number of points (N), truncating last point
```

**Cause**: File has an odd number of data points (should be even for forward+backward).

**Solution**: This is handled automatically by truncating. May indicate incomplete measurement.

#### Could Not Load Topography

```
Warning: Could not load flat topography: <error>
```

**Cause**: Z_flat file is corrupted or has unexpected format.

**Solution**: Check file integrity, try loading standalone with `load_topography()`.

### 8.2 Debugging

Enable debug logging to see detailed parsing information:

```python
import logging
logging.getLogger('src.data_loaders.omicron_mtrx_loader').setLevel(logging.DEBUG)
logging.getLogger('src.data_loaders.omicron_flat_loader').setLevel(logging.DEBUG)
```

### 8.3 File Format Variations

Different Omicron Matrix software versions may produce slightly different file formats:

| Version | Magic Number | Notes |
|---------|--------------|-------|
| Standard | `ONTMATRX0101` | Main format supported |
| Flat | `FLAT0100` | For processed images |

If you encounter files that don't load, check the magic number first:

```python
with open(filepath, 'rb') as f:
    magic = f.read(12)
    print(f"Magic number: {magic}")
```

---

## Appendix A: Block Tag Reference

### I(V)_mtrx Tags

| Tag | Full Name | Description |
|-----|-----------|-------------|
| `ONTMATRX0101` | Magic | File format identifier |
| `TLKB` | Timestamp Block | Measurement timestamp |
| `CSED` | Description | Text metadata |
| `ATAD` | Data | Raw measurement data |

### Header (.mtrx) Tags

| Tag | Full Name | Description |
|-----|-----------|-------------|
| `APEE` | Parameters | Measurement parameters |
| `YSCC` | Channel Config | Transfer function and channel settings |
| `FERB` | File Reference | Links to data files |
| `REFX` | Transfer Function | Transfer function definition |

---

## Appendix B: Unit Conversions

| Measurement | Raw Unit | Physical Unit | Typical Range |
|-------------|----------|---------------|---------------|
| Current (I) | ADC counts | Amperes (A) | 1e-12 to 1e-9 |
| Voltage (V) | Volts | Volts (V) | -3 to +3 |
| Height (Z) | ADC counts | Meters (m) | 1e-12 to 1e-9 |
| Distance | pm | nm | 0.1 to 100 |

---

*Omicron Matrix File Handling Documentation*
*Based on work by Marek (June 2022)*
*Updated for TRANS-QML: December 2025*
