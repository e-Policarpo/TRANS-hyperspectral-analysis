# Omicron Matrix File Format Specification

Comprehensive technical documentation for the Omicron (Scienta Omicron) Matrix
STM/STS binary file formats, reverse-engineered from real measurement data.

Based on previous work by Marek (matrixFileHandling.py, June 2022).
Updated with full header decoding: April 2026.

---

## Table of Contents

1. [Overview](#1-overview)
2. [File Naming Conventions](#2-file-naming-conventions)
3. [ONTMATRX0101 Format (Data Files)](#3-ontmatrx0101-format)
4. [Session Header Format (_0001.mtrx)](#4-session-header-format)
5. [FLAT0100 Format (Flat Files)](#5-flat0100-format)
6. [Transfer Function Scaling](#6-transfer-function-scaling)
7. [Forward/Backward Sweep Handling](#7-forwardbackward-sweep-handling)
8. [Smart Import](#8-smart-import)
9. [Data Loaders API](#9-data-loaders-api)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

### Instruments

The Matrix file format is produced by Scienta Omicron (formerly Omicron
NanoTechnology) MATRIX SPM control software, versions V3.x. The software controls
STM and AFM systems and writes binary data files during measurement sessions.

### File Types

| Extension | Type | Description |
|-----------|------|-------------|
| `.I(V)_mtrx` | Spectroscopy | Current vs. voltage (STS), forward + backward |
| `.Aux2(V)_mtrx` | Spectroscopy | Aux channel 2 vs. voltage, same structure |
| `.Aux1(V)_mtrx` | Spectroscopy | Aux channel 1 vs. voltage |
| `.I(Z)_mtrx` | Spectroscopy | Current vs. distance |
| `.Z(V)_mtrx` | Spectroscopy | Height vs. voltage |
| `.I_mtrx` | Scanning | Current image (line-by-line, variable length) |
| `.Z_mtrx` | Scanning | Z height (line-by-line, variable length) |
| `_0001.mtrx` | Header | Session header: parameters, transfer functions, file index |
| `.Z_flat` | Flat image | Processed (flattened) topography, self-contained |
| `.I_flat` | Flat image | Processed current image, self-contained |

### Session Structure

A measurement session produces one `_0001.mtrx` header and many data files:

```
default_2025Feb14-191224_STM-STM_Spectroscopy_0001.mtrx    ← session header
default_2025Feb14-191224_STM-STM_Spectroscopy--1_1.I(V)_mtrx
default_2025Feb14-191224_STM-STM_Spectroscopy--1_1.Aux2(V)_mtrx
default_2025Feb14-191224_STM-STM_Spectroscopy--1_1.I_mtrx
default_2025Feb14-191224_STM-STM_Spectroscopy--1_1.Z_mtrx
default_2025Feb14-191224_STM-STM_Spectroscopy--1_2.I(V)_mtrx
...
```

---

## 2. File Naming Conventions

```
<session>_<YYYY><Mon><DD>-<HHMMSS>_<instrument>-<experiment>--<grid>_<point>.<channel>_mtrx
└──────────────────────────────────────────────────────┘  └───┘ └───┘ └──────┘
                  Session base name                      Grid#  Pt#   Channel
```

- **Grid number** (`--N`): The spectroscopy grid index within the session
- **Point number** (`_M`): The spectrum index within the grid
- **Channel**: `I(V)`, `Aux2(V)`, `I`, `Z`, etc.

The header file uses `_0001.mtrx` instead of `--N_M.<channel>_mtrx`.

---

## 3. ONTMATRX0101 Format

All `.mtrx` and `_mtrx` data files share this format.

### Structure

```
Offset   Size     Description
─────────────────────────────────────
0x00     12       Magic: "ONTMATRX0101" (ASCII)
0x0C     ...      Sequential tagged blocks (TLKB, CSED, ATAD)
```

### Tag: TLKB (Timestamp)

```
Offset   Size   Type     Description
────────────────────────────────────
+0x00    4      ASCII    "TLKB"
+0x04    4      uint32   File size (unused)
+0x08    4      uint32   Unix timestamp
+0x0C    8      bytes    Padding (zeroes)
```

### Tag: CSED (Description)

```
Offset   Size   Type     Description
────────────────────────────────────
+0x00    4      ASCII    "CSED"
+0x04    4      int32    Block size N
+0x08    N      bytes    Description data (binary, opaque)
```

### Tag: ATAD (Data)

```
Offset   Size   Type     Description
────────────────────────────────────
+0x00    4      ASCII    "ATAD"
+0x04    4      int32    Data size in bytes (= n_points × 4)
+0x08    N      int32[]  Raw measurement data (signed 32-bit LE integers)
```

### Spectroscopy Data Layout

For spectroscopy files (`.I(V)_mtrx`, `.Aux2(V)_mtrx`, etc.), the ATAD block
contains `2 × N` points: the first N are the **forward sweep**, the second N
are the **backward sweep** (recorded in reverse voltage order).

```
[fwd[0], fwd[1], ..., fwd[N-1], bwd[0], bwd[1], ..., bwd[N-1]]
                                         └── reverse voltage order
```

### Scanning Data Layout

For scanning files (`.I_mtrx`, `.Z_mtrx`), the ATAD block contains one
continuous data stream of varying length (one scan line or partial line).

---

## 4. Session Header Format

### Block Layout

The `_0001.mtrx` header uses the same `ONTMATRX0101` magic but contains
different block types. **Every block** (including ATEM and DPXE) follows
the same layout:

```
Offset   Size   Type     Description
────────────────────────────────────
+0x00    4      ASCII    Tag (e.g. "APEE")
+0x04    4      uint32   Data size N
+0x08    4      uint32   Unix timestamp
+0x0C    4      uint32   Padding / flags
+0x10    N      bytes    Block data
```

Total block size: 16 + N bytes.

### Block Types

| Tag | Reversed | Count* | Description |
|-----|----------|--------|-------------|
| `ATEM` | META | 1 | Software version, session name, instrument |
| `DPXE` | EXPD | 1 | Experiment type, description, file paths |
| `APEE` | EEPA | 1 | Experiment parameters (29 groups, 300+ params) |
| `YSCC` | CCSY | 16 | Transfer functions (updated per spectrum) |
| `FERB` | BREF | 360 | File references (index of all data files) |
| `KRAM` | MARK | 39 | Annotations (sample name, dataset, recording flags) |
| `CORP` | PROC | 165 | Data processing pipeline definitions |
| `DOMP` | PMOD | 223 | Runtime parameter modifications |
| `WEIV` | VIEW | 35 | UI view configurations |
| `ICNI` | INCI | 58 | Increment counters |
| `QESF` | FSEQ | 1 | File sequence info |
| `SPXE` | EXPS | 1 | Experiment state |

*Counts from a real session (Feb 2025, ~150 spectra).

### APEE Block (Parameters)

Contains all measurement parameters organized in groups:

```
Data layout:
  uint32   padding (skip 4 bytes)
  uint32   num_groups
  For each group:
    string   group_name       (length-prefixed UTF-16LE)
    uint32   num_params
    For each parameter:
      string   param_name     (length-prefixed UTF-16LE)
      string   unit           (length-prefixed UTF-16LE)
      uint32   padding
      typed_value              (see below)
```

#### Key Parameter Groups

| Group | Key Parameters | Description |
|-------|---------------|-------------|
| `Spectroscopy` | `Device_1_Start`, `Device_1_End`, `Device_1_Points`, `Raster_Time_1`, `Device_1_Repetitions`, `Disable_Feedback_Loop` | Voltage sweep configuration |
| `Regulator` | `Setpoint_1`, `Loop_Gain_1_I`, `Loop_Gain_1_P`, `Feedback_Loop_Enabled` | Feedback loop settings |
| `GapVoltageControl` | `Voltage`, `Preamp_Range` | Gap voltage and preamp |
| `XYScanner` | `Width`, `Height`, `Points`, `Lines`, `X_Offset`, `Y_Offset`, `Raster_Time` | Scan area configuration |
| `I_V` | `Enable`, `Enable_Storing` | I(V) channel recording |
| `Aux2_V` | `Enable`, `Enable_Storing` | Aux2(V) channel recording |

#### Typed Values

| Tag | Type | Size | Python unpack |
|-----|------|------|--------------|
| `LOOB` | Boolean | 4 bytes | `unpack('<I', ...)` → bool |
| `GNOL` | Integer | 4 bytes | `unpack('<i', ...)` → int |
| `BUOD` | Double | 8 bytes | `unpack('<d', ...)` → float |
| `GRTS` | String | Variable | Length-prefixed UTF-16LE |

### YSCC Block (Transfer Functions)

Contains channel scaling configuration. Multiple YSCC blocks appear as the
transfer function is updated during the session (e.g., when preamp range changes).

```
Data layout:
  uint32   padding
  Repeated sub-blocks:
    ASCII(4)   sub_tag      ("REFX" for transfer functions)
    uint32     sub_size
    If REFX:
      uint32   padding
      uint32   group_number
      string   function_name  (e.g. "TFF_MultiLinear1D")
      string   unit           (e.g. "A")
      uint32   num_params
      For each param:
        string   param_name
        typed_value
```

### FERB Block (File References)

Each FERB block references one data file in the session:

```
Data layout:
  uint32   padding
  string   filename    (length-prefixed UTF-16LE)
```

Example: `"default_2025Feb14-191224_STM-STM_Spectroscopy--1_1.I(V)_mtrx"`

### KRAM Block (Annotations)

User-defined annotations in the format `MTRX$KEY-VALUE`:

```
Data layout:
  string   annotation    (length-prefixed UTF-16LE)
```

Key annotations:

| Key | Example | Description |
|-----|---------|-------------|
| `SAMPLE_NAME` | `MBT Duda` | Sample name entered by user |
| `DATA_SET_NAME` | `15/02/25` | Dataset/experiment name |
| `CREATION_COMMENT` | (empty) | User comment |
| `ENABLE_RECORDING` | `Aux2(V)` | Channel recording enabled |
| `DISABLE_RECORDING` | `Aux1` | Channel recording disabled |

---

## 5. FLAT0100 Format

Self-contained processed image files (`.Z_flat`, `.I_flat`).

### Structure

```
Offset   Size     Description
─────────────────────────────────────
0x00     8        Magic: "FLAT0100" (ASCII)
0x08     4        uint32: axis_count (typically 2)

─── For each axis ───
         4        uint32: string length N
         N×2      UTF-16LE: trigger name (e.g. "Default::XYScanner::X")
         4+N×2    UTF-16LE: mirror name (empty for non-mirrored axis)
         4+N×2    UTF-16LE: unit (e.g. "m")
         4        uint32: n_points (800 for X=fwd+bwd, 400 for Y)
         8        double: physical start coordinate
         8        double: physical increment (step size)
         8        double: physical end coordinate
         4        uint32: mirrored flag (1 = forward+backward, 0 = single)
         4        uint32: reserved (0)

─── Channel info ───
         4+N×2    UTF-16LE: channel name (e.g. "Z")
         4+N×2    UTF-16LE: transfer function name (e.g. "TFF_MultiLinear1D")
         4+N×2    UTF-16LE: channel unit (e.g. "m")
         4        uint32: num_xfer_params
         For each param:
           4+N×2  UTF-16LE: param name
           8      double: param value

─── Creation metadata ───
         4        uint32: field1 (typically 1)
         4        uint32: field2 (typically 3)
         4        uint32: Unix timestamp
         4        uint32: field4 (typically 0)
         4+N×2    UTF-16LE: comment string
                  Format: "Sample=<name>;DataSet=<date>;CreationComment=<text>"

─── Data ───
         4        uint32: data_count (e.g. 320000 = 800 × 400)
         4        uint32: data_count (repeated)
  data_count×4    int32[]: raw image data (signed 32-bit LE integers)

─── Footer ───
         ...      Experiment definition (strings: experiment name, version,
                  description, paths, software info, original result path)
```

### Image Data Layout

For a 400-line scan with forward+backward (X axis mirrored):

```
X axis: 800 points = 400 forward + 400 backward
Y axis: 400 lines

Data: 800 × 400 = 320,000 int32 values

Row layout (each of 400 rows):
  [fwd_px0, fwd_px1, ..., fwd_px399, bwd_px0, bwd_px1, ..., bwd_px399]

To extract forward-only image:
  image = data.reshape(400, 800)[:, :400]
```

### String Encoding

All strings in FLAT0100 use **length-prefixed UTF-16LE**:

```
uint32   N          (character count, NOT byte count)
N × 2    bytes      UTF-16LE encoded string
```

---

## 6. Transfer Function Scaling

### TFF_Linear1D

```
scaled = (raw - Offset) / Factor
```

| Parameter | Typical Value | Description |
|-----------|--------------|-------------|
| `Offset` | 0.0 | ADC zero offset |
| `Factor` | 2.148e8 | ADC counts per unit |

Used for: voltage channels.

### TFF_MultiLinear1D

```
scaled = (Raw_1 - PreOffset) × (raw - Offset) / (NeutralFactor × PreFactor)
```

| Parameter | Typical Value | Description |
|-----------|--------------|-------------|
| `NeutralFactor` | 6.449e15 or 2.4e15 | Neutral scaling (ADC + preamp) |
| `Offset` | 0.0 | ADC zero offset |
| `PreFactor` | 1.01 or 105.0 | Preamp gain factor |
| `PreOffset` | -0.01 or -105.0 | Preamp offset |
| `Raw_1` | 0.0 or 1.0 | Reference (toggles 0↔1 with preamp range) |

Used for: current channels (I, Aux), height (Z).

### YSCC Group Numbers

From a real session:

| XFER # | Function | Unit | Channel |
|--------|----------|------|---------|
| 7 | TFF_MultiLinear1D | A | Current (scanning) |
| 11 | TFF_Linear1D | V | Voltage |
| 20 | TFF_MultiLinear1D | A | Current (spectroscopy) |

---

## 7. Forward/Backward Sweep Handling

### Data Split

```python
# Raw data: 2N points (N forward + N backward)
n_total = datasize // 4
n_half = n_total // 2

forward = scaled[:n_half]
backward_raw = scaled[n_half:n_half * 2]

# Backward sweep goes V_end → V_start, so reverse to align
backward = backward_raw[::-1]

# Average
mixed = (forward + backward) / 2
```

### Voltage Array

Generated from header parameters:

```python
V = np.linspace(
    params['Spectroscopy.Device_1_Start'],  # e.g. -0.4 V
    params['Spectroscopy.Device_1_End'],    # e.g. +0.4 V
    n_half                                   # e.g. 150 points
)
```

---

## 8. Smart Import

### How It Works

1. User picks **one file** from a session (any data file or the `_0001.mtrx` header)
2. The loader finds the `_0001.mtrx` header in the same directory
3. Parses all **FERB blocks** to enumerate every data file in the session
4. Parses **APEE** for voltage range, scan parameters
5. Parses **YSCC** for transfer functions
6. Parses **KRAM** for sample name and dataset name
7. Loads all matching spectroscopy files from disk

### Supported Smart Import Sources

| File Type | How Header is Found |
|-----------|-------------------|
| `_0001.mtrx` | Direct — this IS the header |
| `.I(V)_mtrx` | Strip `--N_M.I(V)_mtrx`, append `_0001.mtrx` |
| `.Aux2(V)_mtrx` | Same pattern |
| Any `_mtrx` | Try `*_0001.mtrx` glob in same directory |

### Session File Discovery

From FERB blocks in a real session:

```
  .I(V)_mtrx       146 files    ← voltage spectroscopy
  .Aux2(V)_mtrx    146 files    ← aux channel 2 vs voltage
  .I_mtrx           34 files    ← scanning current (image lines)
  .Z_mtrx           34 files    ← scanning height (image lines)
```

---

## 9. Data Loaders API

### OmicronMatrixSTSLoader

**File**: `src/data_loaders/omicron_mtrx_loader.py`

```python
class OmicronMatrixSTSLoader(BaseDataLoader):
    """Comprehensive loader for Omicron Matrix STM data."""

    # Load all spectra from a directory
    def load_from_directory(self, directory, progress_callback=None)
        -> Tuple[SpectralData, Optional[TopographyData]]

    # Load a single spectroscopy file
    def load_single_file(self, filepath) -> SpectralData

    # Smart import from one file or header
    def smart_load_from_file(self, filepath, progress_callback=None)
        -> Tuple[SpectralData, Optional[TopographyData]]
```

### MatrixHeaderParser

**File**: `src/data_loaders/omicron_mtrx_loader.py`

```python
class MatrixHeaderParser:
    """Parser for _0001.mtrx session header files."""

    def parse(self)                          # Parse the full header
    def get_session_files() -> Dict[str, List[str]]  # FERB file groups by extension
    def get_voltage_range() -> Tuple[float, float]   # From Spectroscopy params
    def get_scan_dimensions() -> Tuple[int, int]     # XYScanner Points × Lines
    def get_sample_name() -> str                     # From KRAM annotations
    def get_dataset_name() -> str                    # From KRAM annotations

    # Accessible after parse():
    .parameters: Dict[str, Any]    # All APEE parameters
    .xfer: Dict[str, Any]          # All YSCC transfer functions
    .file_refs: List[str]          # All FERB file names
    .annotations: Dict[str, str]   # All KRAM key-value pairs
```

### OmicronFlatLoader

**File**: `src/data_loaders/omicron_flat_loader.py`

```python
class OmicronFlatLoader(BaseDataLoader):
    """Structural parser for FLAT0100 format."""

    def load_topography(self, filepath) -> TopographyData
    def load_single_file(self, filepath) -> SpectralData
    def load_from_directory(self, directory, progress_callback=None)
        -> Tuple[SpectralData, Optional[TopographyData]]
```

---

## 10. Troubleshooting

### No Transfer Function Found

```
Warning: No transfer function found, using default scaling (nA)
```

Ensure the `_0001.mtrx` header file is in the same directory as the data files.
The loader needs it to read YSCC blocks with scaling parameters.

### Odd Number of Points

```
Warning: Odd number of points (N), truncating last point
```

The spectroscopy file has a non-even data count, which means the measurement
may have been interrupted. The loader truncates the extra point.

### Smart Import Finds No Files

If FERB blocks reference files that don't exist on disk, the session data may
have been partially exported or moved. The loader only imports files it finds.

### FLAT Image Dimensions Wrong

The FLAT loader reads axis `n_points` directly from the header. If the X axis
is mirrored (forward+backward), the forward image is `n_points / 2` wide.

### Debug Logging

```python
import logging
logging.getLogger('src.data_loaders.omicron_mtrx_loader').setLevel(logging.DEBUG)
logging.getLogger('src.data_loaders.omicron_flat_loader').setLevel(logging.DEBUG)
```

---

*Omicron Matrix File Format Specification*
*Reverse-engineered from MATRIX V3.3.2 output (Scienta Omicron)*
*Based on original work by Marek (June 2022)*
*Updated: April 2026*
