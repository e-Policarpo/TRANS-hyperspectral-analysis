# WITec WIP Loader & Image Entity Support

Comprehensive technical documentation for the WITec Project (`.wip`) PL/Raman loader,
the new first-class **Image** entity type, the **Image Viewer** embedded window, and
the **Map ↔ Image conversion** model. Also documents the regression fix for the
project-browser map double-click and the retrofit that surfaces preview/optical
images previously discarded by the older loaders.

Reverse-engineered from a real WITec ControlFIVE 5.1.20.85 file
(`Sheffield - UFMG/Raman/DtBuTPZ series.wip`, 30 MB).
Initial implementation: May 2026 (branch `Unified-UI`).

---

## Table of Contents

1. [Overview](#1-overview)
2. [WIP Binary File Format](#2-wip-binary-file-format)
3. [Data Classes Used](#3-data-classes-used)
4. [Spectral Axis Reconstruction](#4-spectral-axis-reconstruction)
5. [Loader Behavior](#5-loader-behavior)
6. [Image Entity Model](#6-image-entity-model)
7. [Image Viewer Window](#7-image-viewer-window)
8. [Map ↔ Image Conversion](#8-map--image-conversion)
9. [Map Double-Click Fix](#9-map-double-click-fix)
10. [Retrofit: Surfacing Images from Older Loaders](#10-retrofit-surfacing-images-from-older-loaders)
11. [Project Persistence (`.hrt`)](#11-project-persistence-hrt)
12. [Tests](#12-tests)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Overview

### Instruments

WITec ControlFIVE / ControlFOUR / Project FOUR is the acquisition software shipped
with WITec confocal Raman / PL microscopes (alpha300 R/A/AR/RAS, alpha500, apyron).
A measurement session produces a single `.wip` file containing every spectrum,
hyperspectral map, optical preview, color profile, transformation, and label
gathered during the session.

### File extension

| Extension | Type | Description |
|-----------|------|-------------|
| `.wip`    | Project (binary) | Tagged-tree container holding all session data |

A sister `.wid` (data-only) format exists in some WITec exports and can be added
later by reusing the parser; for v1 only `.wip` is supported.

### What's inside

- **Spectra**: single-point Raman/PL spectra, stitched spectra, time-series.
- **Hyperspectral maps**: 2D rasters of spectra (`SizeX × SizeY > 1`).
- **Bitmaps**: optical microscope previews, video frames, thumbnails (Windows BMP DIB).
- **Transformations**: polynomial mappings from CCD pixel index → wavelength/wavenumber.
- **Interpretations**: axis labels and units (`"nm"`, `"cm-1"`, etc.).
- **Auxiliary**: cursors, color profiles, text labels, history lists.

---

## 2. WIP Binary File Format

The format is a **tagged tree**, little-endian, with a fixed magic header.

### File header

```
Offset 0x00:  8 bytes  "WIT_PR06"           — magic (project format version 06)
Offset 0x08:  4 bytes  uint32   name_len     — root tag's name length (= 13)
Offset 0x0c:  N bytes           name         — "WITec Project"
Offset 0x19:  4 bytes  uint32   type         — 0 (container)
Offset 0x1d:  8 bytes  uint64   data_start   — absolute byte offset where children begin
Offset 0x25:  8 bytes  uint64   data_end     — absolute byte offset where children end
```

### Generic tag layout

Every tag in the tree has the same shape:

```
+----------------+----------+----------------------------------------------+
| Field          |  Bytes   | Meaning                                      |
+----------------+----------+----------------------------------------------+
| name_len       |  4       | uint32 LE                                    |
| name           |  name_len| ASCII (no null terminator)                   |
| type           |  4       | uint32 LE — see "Type codes" below           |
| data_start     |  8       | uint64 LE — absolute file offset             |
| data_end       |  8       | uint64 LE — absolute file offset (exclusive) |
+----------------+----------+----------------------------------------------+
```

Header size = `4 + name_len + 20`. The tag's value sits in the byte range
`[data_start, data_end)`. Child tags inside a container occupy that range
contiguously: walk siblings by advancing the read pointer to the previous tag's
`data_end`.

### Type codes

Empirically determined; not all are used in every file.

| Code | Meaning      | Encoding                                                    |
|------|--------------|-------------------------------------------------------------|
| 0    | Container    | Data block holds a list of child tags.                      |
| 2    | Float64      | `<d`. Arrays = N × 8 bytes (`Polynom` is 3 doubles = 24 b). |
| 5    | Int32        | `<i`. Some entries declare 8 bytes — read by declared size. |
| 6    | List/Int64   | Often empty (size 0). Treat by sibling context.             |
| 7    | Raw blob     | Used for `GraphData.Data`. Numeric type from `DataType`.    |
| 8    | Bool         | 1 byte (`0` / `1`).                                         |
| 9    | String       | `uint32 length` + ASCII (no null terminator).               |

### Top-level project tree

```
WITec Project (0)
├─ Version (5)              — int (typically 7)
├─ SystemInformation (0)
│  ├─ LastApplicationSessionIDs (0)
│  ├─ ServiceID (0) / LicenseID (0) / SystemID (0)
│  └─ ApplicationVersions (0)
├─ NextDataID (5)           — next free integer ID
├─ ShellExtensionInfo (0)
│  └─ ThumbnailPreviewBitmap (0)   — Windows BMP DIB, 128×128 RGB (preview)
└─ Data (0)
   ├─ DataClassName 0  (9, string) — class label for index 0
   ├─ Data 0            (0)        — payload for index 0
   ├─ DataClassName 1  (9)
   ├─ Data 1            (0)
   ├─ ...
   └─ DataClassName N / Data N
```

`DataClassName N` tells the loader how to interpret `Data N`. The two are paired
by index.

---

## 3. Data Classes Used

Each `Data N` typically contains a `TData` child (universal metadata) plus one
class-specific block whose name matches the `DataClassName N` value.

### `TData` (present in every Data N)

| Child           | Type | Description                                  |
|-----------------|------|----------------------------------------------|
| `Version`       | 5    | Schema version (0)                           |
| `ID`            | 5    | Integer ID (used for cross-references)       |
| `ImageIndex`    | 5    | Display image index in the WITec UI          |
| `Caption`       | 9    | Human-readable label (e.g. spectrum name)    |
| `MetaData`      | 0    | Free-form key/value bag                      |
| `HistoryList`   | 0    | Processing history                           |

### `TDGraph` — the core class for spectral data

Holds one or more spectra arranged on a 2D spatial grid.

| Child                        | Type | Description                                                  |
|------------------------------|------|--------------------------------------------------------------|
| `Version`                    | 5    | (1)                                                          |
| `SizeX`                      | 5    | Spatial X dimension (`1` for single-point)                   |
| `SizeY`                      | 5    | Spatial Y dimension (`1` for single-point)                   |
| `SizeGraph`                  | 5    | Number of spectral channels (CCD bins)                       |
| `SpaceTransformationID`      | 5    | → `TDSpaceTransformation` for XY mapping                     |
| `SecondaryTransformationID`  | 5    | (often 0)                                                    |
| `XTransformationID`          | 5    | → `TDSpectralTransformation` for the wavelength axis         |
| `XInterpretationID`          | 5    | → `TDSpectralInterpretation` for the X-axis label/unit       |
| `ZInterpretationID`          | 5    | → `TDZInterpretation` for the intensity axis label/unit      |
| `GraphData`                  | 0    | Subtree below                                                |
| `DataFieldInverted`          | 8    | Whether values are inverted (rare)                           |
| `LineChanged` / `LineValid`  | 8    | Modification flags                                           |

### `TDGraph.GraphData`

| Child       | Type | Description                                                       |
|-------------|------|-------------------------------------------------------------------|
| `Dimension` | 5    | (2)                                                               |
| `DataType`  | 5    | Sample type code: **`9` ⇒ float32 little-endian** (verified).     |
| `Ranges`    | 5    | Packed range info (size 8)                                        |
| `Data`      | 7    | Raw blob: `SizeX × SizeY × SizeGraph × bytes_per_sample` bytes    |

Sample storage order is row-major over the spatial grid — for each pixel,
`SizeGraph` consecutive samples form one spectrum.

### `TDSpectralTransformation` — spectral axis

Type-0 polynomial transformations encode the CCD pixel-to-wavelength mapping.

| Child                          | Type | Description                                              |
|--------------------------------|------|----------------------------------------------------------|
| `SpectralTransformationType`   | 5    | `0` = polynomial; other types not yet observed           |
| `Polynom`                      | 2    | 24 bytes = 3 doubles `[c0, c1, c2]`                      |
| `nC`, `LambdaC`, `Gamma`, `Delta`, `m`, `d`, `x`, `f` | 2 | Spectrograph-geometry coefficients (often 0 when polynomial type is in use) |
| `FreePolynomOrder`             | 5    | Polynomial order override (usually `-1`)                 |
| `FreePolynomStartBin`          | 2    | Bin range start                                          |
| `FreePolynomStopBin`           | 2    | Bin range end                                            |

Sibling `TDTransformation` block:

| Child            | Type | Description                                       |
|------------------|------|---------------------------------------------------|
| `StandardUnit`   | 9    | Unit string (e.g. `"nm"`, `"cm-1"`)               |
| `UnitKind`       | 5    | Unit category (2 = wavelength, etc.)              |
| `IsCalibrated`   | 8    | Calibration flag                                  |

### `TDBitmap` — embedded Windows DIB images

Includes optical microscope previews, video frames, the project thumbnail. The
embedded blob is a literal Windows `BITMAPINFOHEADER` + pixel rows — pass it to
`PIL.Image.open(BytesIO(blob))` and it decodes directly. Pixel sizes carried in
the BMP headers; orientation is bottom-up per BMP convention.

### Other classes (consumed for completeness, mostly forwarded as-is)

- `TDText` — captions and annotations.
- `TDSpaceTransformation` / `TDSpaceInterpretation` — XY mapping for hyperspec maps.
- `TDSpectralInterpretation` / `TDZInterpretation` — axis label/unit metadata.
- `TDColorProfile`, `TDSpaceCursor`, `TDSpectralCursor` — UI display state, ignored.

### Cross-references

When `TDGraph.XTransformationID == 64`, the loader scans every `Data N` for the
one whose `TData.ID == 64` **and** whose class is `TDSpectralTransformation`.
Same pattern for the other `*ID` fields.

---

## 4. Spectral Axis Reconstruction

Given `SpectralTransformationType == 0` and `Polynom = [c0, c1, c2]`:

```python
import numpy as np
bins = np.arange(size_graph)
axis = c0 + c1 * bins + c2 * bins**2     # in StandardUnit (e.g. "nm")
```

If `FreePolynomOrder >= 0`, that overrides the polynomial degree and the
loader reads `FreePolynomOrder + 1` coefficients from `Polynom`. The test
file uses fixed degree-2 (the default).

For wavenumber output (Raman shift in cm⁻¹) the user supplies an excitation
wavelength in the import dialog and the loader applies
`Δν̃[cm⁻¹] = 1e7 × (1/λ_ex[nm] − 1/λ[nm])`. v1 keeps native units (`nm`) and
defers wavenumber conversion to a downstream tool.

---

## 5. Loader Behavior

### Module layout

```
src/data_loaders/
├─ witec_wip_loader.py        ← WitecWipLoader(BaseDataLoader)
└─ witec_wip/
   ├─ __init__.py
   └─ wip_parser.py            ← Pure binary parser (no app dependencies)
```

### `WitecWipLoader` API

| Method                                            | Returns                                  | When |
|---------------------------------------------------|------------------------------------------|------|
| `load_single_file(filepath)`                      | `SpectralData`                           | Standard import |
| `load_from_directory(dir)`                        | `Tuple[SpectralData, Optional[TopographyData]]` | Folder import |
| `smart_load_from_file(filepath)`                  | `Tuple[SpectralData, Optional[TopographyData]]` | Smart import dialog path |

- `loader_type = "witec_pl_raman"`
- `supported_extensions = [".wip"]`

### Spectrum grouping

Multiple `TDGraph` entries can share the same wavelength axis but have
different captions. The loader groups spectra by the **numeric value of their
resolved spectral axis** (rounded to 6 sig figs to absorb float jitter):

- Spectra with identical axes → columns of one DataFrame; first column is the
  shared axis (named after `StandardUnit`, e.g. `"Wavelength_nm"`).
- Spectra with differing axes → returned as separate `SpectralData` siblings
  via `metadata.additional_info['channels']` (same convention as
  `park_afm_loader.py`). The backend's smart-import unpacks each channel as
  its own dataset.

Column names come from `TData.Caption`. Duplicate captions are de-duplicated by
suffixing `" (2)"`, `" (3)"`, …

### Hyperspectral maps (`SizeX × SizeY > 1`)

For non-trivial spatial dimensions the loader builds a `MultiChannelMap` from
`src/models/map_channel.py` and stashes it in
`metadata.additional_info['map_geometry']` so the existing topography-overlay
path at `app_backend.py` picks it up and routes the data into
`MapEditorWorkstation`. The test file contains no such graphs — a skip-marked
test exercises the path once a map-flavored `.wip` becomes available.

### Bitmap surfacing

Every `TDBitmap` plus the project's `ThumbnailPreviewBitmap` becomes an
`ImageData` instance and is appended to `metadata.additional_info['images']`
as `(name, ImageData)` tuples. Dataset import unpacks these into the global
image registry — see [§6](#6-image-entity-model) and [§10](#10-retrofit-surfacing-images-from-older-loaders).

---

## 6. Image Entity Model

`src/models/image_data.py` introduces a first-class `ImageData` model that lives
alongside `SpectralData` and `TopographyData`.

### Modes

```python
class ImageMode(Enum):
    RGB           = "rgb"            # uint8 H×W×3
    RGBA          = "rgba"           # uint8 H×W×4
    GRAY_U8       = "gray_u8"        # uint8 H×W
    GRAY_U16      = "gray_u16"       # uint16 H×W
    SINGLE_FLOAT  = "single_float"   # float32 H×W (e.g. map channel)
```

### Construction

| Factory                              | Source                                                         |
|--------------------------------------|----------------------------------------------------------------|
| `ImageData.from_file(path)`          | PIL/`tifffile` decode; original bytes retained for round-trip  |
| `ImageData.from_array(arr, mode, …)` | Already-decoded numpy array (e.g. WITec TDBitmap, RGB preview) |
| `ImageData.from_bmp_blob(blob)`      | Windows BMP DIB blob (used by `WipBitmap`)                     |
| `ImageData.from_map_channel(ch)`     | Map → Image conversion; copies float32 array                   |

### Methods

- `crop(x0, y0, x1, y1) -> ImageData` — non-destructive, returns new `ImageData`.
- `histogram(bins=256) -> (counts, edges)` — per-channel for RGB(A), single for gray.
- `to_bytes(format="png")` — encode for `.hrt` persistence (PNG for RGB(A)/uint,
  raw little-endian buffer for `SINGLE_FLOAT`).
- `to_qimage()` — convert to `QImage` for the canvas (cached).

### Identity

Each `ImageData` carries a stable `id: str` (UUID-shortened) and a
`name: str` (defaults to the source filename or caption). Both are mutable
through `AppBackend.renameImage`.

---

## 7. Image Viewer Window

A new embedded-window type joins the existing graph and table windows.

### Components

- `src/widgets/qml_image_canvas.py` — `QMLImageCanvas(QQuickPaintedItem)`,
  ~400 lines. Renders via `QPainter.drawImage(QImage)`.
- `src/qml/components/ImageWindowContent.qml` — content for the embedded
  window: canvas + side panel (histogram, range sliders, colormap combo,
  crop toolbar).

The existing `EmbeddedWindow.qml` already declares `windowType: "image"`
and the matching "I" header icon, and `WindowManager.qml` already exposes
`createImageWindow()` — both were stubs prior to this work.

### Tools (v1)

| Tool             | UI                                              | Implementation                                   |
|------------------|-------------------------------------------------|--------------------------------------------------|
| Pan / zoom       | Mouse drag / wheel; "Fit", "1:1" buttons        | Standard viewport transform                      |
| Crop             | Modifier-drag on canvas → rectangle             | `ImageData.crop`; result becomes new entity      |
| Histogram        | Side-panel sparkline                            | `ImageData.histogram`                            |
| Intensity range  | Min/max sliders below histogram                 | Display-only LUT remap; original data untouched  |
| Colormap         | ComboBox: `viridis`, `gray`, `hot`, `magma`, `inferno`, `plasma`, `cividis` | `matplotlib.cm.get_cmap` rendered into a 256-entry palette and applied to single-channel images. RGB images bypass colormap controls. |

### Backend signal

```python
openImageEmbedded = Signal(str, str)   # (title, image_id)
```

QML's `WindowManager` handles the signal, creates an embedded window of type
`"image"`, and instantiates `ImageWindowContent.qml` with `imageId` set to the
emitted id. The canvas pulls the actual `QImage` via a registered
`QQuickImageProvider` under the URL scheme `image://trans/<image_id>` —
no payload travels through Qt signals.

---

## 8. Map ↔ Image Conversion

Convention enforced project-wide:

- **Maps** are TIFF files (single- or multi-channel; float32 or integer).
- **Images** are anything PIL/`tifffile` can decode (PNG, JPG, BMP, single-page TIFF), plus synthesized in-memory data.

### Map → Image (right-click "Convert to Image (raw)")

The currently active channel of the map is copied as a single-channel
`SINGLE_FLOAT` `ImageData`. **No colormap baking** — the image-viewer's
colormap and range tools drive display, preserving the raw data. The new
entity is named `"<map_name> · <channel> (raw)"`. Spatial pixel size
(`pixel_size_nm`) is propagated via metadata.

### Image → Map (right-click "Convert to Map (TIFF)")

Only valid for single-channel images (`SINGLE_FLOAT`, `GRAY_U8`, `GRAY_U16`).
The backend writes the array to `<project_dir>/_converted_maps/<image_id>.tiff`
via `tifffile.imwrite`, registers it in `self.maps`, and emits the standard
load signals so the new map appears in the browser and double-click opens
it in the map editor.

### Round-trip guarantees

Map → Image → Map is **bit-identical** for `SINGLE_FLOAT` images: the float32
array travels untouched through both conversions.

---

## 9. Map Double-Click Fix

Before this work, double-clicking a map in the browser was broken whenever the
map had been imported in-memory (e.g. via Park's TIFF reader, or any future
loader producing a `MultiChannelMap` directly).

### Root cause

`AppBackend.openMap(map_id)` resolved `map_info['path']` and probed for
`.tiff`/`.tif`/`.png`/`.gsf` siblings. In-memory maps had no real on-disk file,
so every probe failed and the slot returned silently with only a
`logger.warning`. The user saw no error.

### Fix

- New in-memory map registry: `AppBackend._maps_inmem: Dict[str, MultiChannelMap]`.
- New backend signal `loadMapInEditorById(str)` paralleling the old path-based
  one.
- New `MapEditorBackend.loadMapById(map_id)` slot that consumes a stored
  `MultiChannelMap` directly without touching disk; falls back to
  `loadMapFromFile` only when the map is purely on-disk.
- `Main.qml` adds `onLoadMapInEditorById` mirroring the existing pending-load
  protection at `Main.qml` line ~1105 (the `_pendingMapLoad` mechanism).
- `openMap` now emits `errorOccurred` when nothing matches, replacing the
  silent `logger.warning` so the user gets a toast.

### Regression test

`tests/test_backend/test_map_open.py::test_openMap_inmem_path` simulates an
in-memory map (no disk file) and asserts that `openMap` emits
`loadMapInEditorById` with the correct id rather than failing silently.

---

## 10. Retrofit: Surfacing Images from Older Loaders

Each existing loader's smart-import path now populates
`metadata.additional_info['images']` so previously-discarded preview imagery
shows up in the Images browser category.

| Loader               | What's surfaced                                              |
|----------------------|--------------------------------------------------------------|
| Park AFM             | The 8-bit colormapped TIFF thumbnail (the visible "preview" inside the same `.tiff` that holds the float32 data) |
| Nanosurf STS         | NSFopen frame data — only frames flagged as image-type; Z-axis still becomes topography as before |
| Omicron Matrix       | Sidecar `*.png`/`*.jpg`/`*.tiff` files in the session directory |
| Omicron Flat         | Standard TIFF preview (8-bit) decoded via PIL; raw float data still becomes the dataset |
| NeaSpec SNOM         | No image data inside the text format; sidecar discovery deferred to v2 |
| WITec WIP            | All `TDBitmap` entries plus `ThumbnailPreviewBitmap` |

---

## 11. Project Persistence (`.hrt`)

`ProjectManager` is extended to round-trip image entities and image windows.

### Save

- `images` array entries: `{id, name, mode, shape, dtype, bytes_b64, metadata}`.
  - `RGB`/`RGBA`/`GRAY_U8`/`GRAY_U16`: `bytes_b64` is the PNG-encoded image (lossless).
  - `SINGLE_FLOAT`: `bytes_b64` is the raw float32 buffer (LE), and the loader uses `shape` + `dtype` to reconstruct the array.
- `image_windows` array: same shape as `graphs`/`tables`, plus the active `image_id`, displayMin/Max, colormap, and crop rect for state restoration.

### Load

- `projectStateRestored` is extended to include `image_windows`.
- Image entities are restored before windows so that window restoration can look them up by id.

Projects remain self-contained — no external image files are required after
save.

---

## 12. Tests

| Test file                                              | What it verifies                                            |
|--------------------------------------------------------|-------------------------------------------------------------|
| `tests/test_data_loaders/test_witec_wip_parser.py`     | Tag walk + type decode against synthetic and real .wip data |
| `tests/test_data_loaders/test_witec_wip_loader.py`     | End-to-end loader behavior, real-file skip-if-missing test  |
| `tests/test_models/test_image_data.py`                 | ImageData factories, crop, histogram, to_bytes round-trip   |
| `tests/test_backend/test_image_entity.py`              | Backend storage, signals, image-provider URL resolution     |
| `tests/test_backend/test_map_image_conversion.py`      | Map → Image and Image → Map round-trip, bit-identical check |
| `tests/test_backend/test_map_open.py`                  | `openMap` in-memory path regression (the double-click fix)  |
| `tests/test_widgets/test_qml_image_canvas.py`          | Canvas LUT, crop, histogram extraction (headless, no QML)   |

The full suite (947 + new tests) must remain green. Run with:

```bash
python3 -m pytest tests/ -x -v
```

---

## 13. Spectral-axis unit conversion

`src/backend/spectral_axis.py` provides four canonical units and converts
between them:

- **Wavelength** (nm) — `λ`
- **Energy** (eV) — `E = 1239.841984 / λ_nm`
- **Wavenumber** (cm⁻¹, absolute) — `ν̃ = 10⁷ / λ_nm`
- **Raman shift** (cm⁻¹, relative to laser excitation) — `Δν̃ = 10⁷/λ_ex − 10⁷/λ`

`AppBackend.convertDatasetAxis(dataset, target_unit, excitation_nm,
new_dataset_name)` applies the conversion to a dataset's first column,
renames it (`Wavelength_nm` / `Energy_eV` / `Wavenumber_cm-1` /
`Raman_Shift_cm-1`), and reverses row order when the conversion flips
monotonicity (e.g. nm → eV) so the resulting plot stays ascending.
Source unit is inferred from `metadata.units['x']` /
`metadata.additional_info['axis_unit']` / column-name heuristic.

A QML tool (`SpectralAxisConvertTool.qml`, registered as **Spectral
Axis Converter** in the Spectral tool palette) wraps the slot with a
target-unit ComboBox, an excitation-wavelength field (enabled only for
Raman shift, defaulting to 532 nm), and an optional output-name field.

Excitation wavelength is user-supplied for now — the WITec metadata
blocks in the tested file don't carry it. A future iteration could
auto-extract it from a different WITec acquisition (where `MetaData`
sub-entries are populated).

## 14. Multi-peak fitting

`src/backend/peak_fitting.py` provides peak detection and multi-peak
fitting on top of a polynomial baseline. Three line shapes are supported:

- **Gaussian**: `A · exp(−(x−μ)² / 2σ²)` (FWHM = `2·√(2 ln 2)·σ`)
- **Lorentzian**: `A · γ² / ((x−μ)² + γ²)` (FWHM = `2γ`)
- **Pseudo-Voigt**: `η·Lorentz(γ) + (1−η)·Gauss(σ = γ/√(2 ln 2))`,
  the linear-combination form

`detect_peaks(x, y, prominence, n_max)` wraps `scipy.signal.find_peaks`
to yield `(center, height, width_x)` seeds sorted by descending
prominence. `fit_multipeak(x, y, initial_peaks, shape, baseline_degree,
n_peaks_auto, auto_prominence)` constructs the model

```
y(x) = polyval(baseline, x) + Σ_i shape(amplitude_i, center_i, width_i, [eta_i])
```

and runs `scipy.optimize.least_squares` with bounds (centers clamped to
the data range, widths positive, `η` ∈ [0, 1]). Returns a
`MultiPeakFitResult` with the fitted curve, individual components,
residuals, baseline coefficients, and R² / RSS metrics.

`AppBackend.multiPeakFit(dataset, peak_shape, n_peaks_auto,
baseline_degree, spectrum_index)` exposes the math to QML as a single
slot and creates a follow-up dataset (`<source> · fit (<shape>, N
peaks)`) with columns `Data`, `Fit`, `Baseline`, `Residuals`, `Peak
1…N` so the user can plot everything overlaid.

`MultiPeakFitTool.qml` (registered as **Multi-Peak Fitting** in the
Spectral tool palette) provides the UI: source dataset and spectrum
index, peak shape, max-peaks cap, baseline degree, and a monospace
summary panel listing each peak's `center / amplitude / width / FWHM /
η` along with the global R² and baseline coefficients.

## 15. Troubleshooting

### "No spectra found in WIP file"

The `Data` container is empty or the file is a `.wid` (data-only) sidecar
rather than a full `.wip`. Open the original `.wip` from the WITec acquisition
software.

### "Unsupported SpectralTransformationType"

v1 only handles type 0 (polynomial). Other types (interferometric, lookup-table)
are rare; report the source file so the parser can be extended.

### Spectra group oddly when their axes look identical

The loader compares wavelength axes after rounding to 6 significant figures.
If hardware-induced jitter is larger than that (e.g. on uncalibrated systems),
adjust `WitecWipLoader._axis_signature` in `src/data_loaders/witec_wip_loader.py`.

### Map double-click does nothing

If the regression returns, check `AppBackend.openMap` logs — it now emits
`errorOccurred` rather than failing silently. Confirm `_maps_inmem` is being
populated by your loader's smart-import path.

### Image viewer shows a black screen for single-channel data

The display range may be set to `[0, 0]` for a flat array. Click "Auto-range"
in the image-window side panel to recalibrate min/max from the current crop.

### TDBitmap decoding fails

WITec stores BMP DIBs without the standard `BITMAPFILEHEADER` (no `"BM"`
prefix and no file-size field). The loader synthesizes the missing header
before handing the blob to PIL. If decoding still fails, inspect the BMP header
fields (`biBitCount`, `biCompression`); compressed BMPs (`BI_JPEG`,
`BI_PNG`) are uncommon but possible.
