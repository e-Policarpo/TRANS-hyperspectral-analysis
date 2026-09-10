# T.R.A.N.S. — Reference

**Tools for Research and Analysis for Nano Spectroscopy.** A desktop
application for scanning-probe spectroscopy: it imports what the microscope
wrote, keeps the physical units attached to it, and runs the analysis that
turns a pile of dI/dV curves into a statement about a sample.

This document has three levels, each self-contained. Read the one that
matches what you are trying to do.

| level | for | answers |
|---|---|---|
| [1 — Surface](#level-1--surface) | using the program | what tools exist, what goes in, what comes out |
| [2 — Under the hood](#level-2--under-the-hood) | trusting the numbers | which libraries, which heuristics, which file formats, which quirks |
| [3 — Inside the engine](#level-3--inside-the-engine) | changing the code | what the classes are and how they talk to each other |

> **Where this starts, and why.** The spine of levels 2 and 3 is the path a
> measurement takes: **file → loader → `SpectralData` → tool → output → project
> file**. Every tool, every format and nearly every class hangs off that one
> path, so it is described first and referred back to throughout.

> **Status.** Levels 1 and 2 are complete. Level 3 gives the architecture and
> the load-bearing classes in full, plus a complete map of every module so
> nothing is invisible — the per-class depth is filled in where it earns its
> place. Older files in `docs/` (`API_REFERENCE.md`, `PROJECT_STRUCTURE.md`,
> and the `*_PLAN.md` documents) predate the Confinement, Map Generator,
> Filter Bad Data and Modeling work and describe a program that no longer
> exists; treat this file as the current one.

---

# Level 1 — Surface

## What the program is for

You have measurements from an STM, AFM or optical microscope: spectra taken
at points on a sample, scan images of the surface, or both. TRANS imports
them with their real physical dimensions intact, gives you tools to clean and
analyse them, and saves the whole state — datasets, images, maps, windows —
as one project file you can reopen.

## Getting started

1. **File → New Project**, or open an existing `.hrt`. Projects live in
   `~/Documents/TRANS_QML_Projects/` by default.
2. **File → Import Measurement**. Pick one file and the loader finds its
   siblings (*smart import*), or pick a folder to import everything in it.
3. Imported data appears in the **project browser** on the left, filed into
   `Spectral Data / <session>`, `Images / <session>`, `Maps / <session>`.
4. Open a tool from the **Tools** menu, pick a dataset, run it. Results appear
   in the browser beside their source and are written to the project's
   `<name>_outputs/` folder.

Three tabs across the top: **Spectral** (curves), **Hyperspectral** (maps and
line scans), **Modeling** (potential design and eigenstates).

## What it reads

| instrument | files | what you get |
|---|---|---|
| **Omicron MATRIX** | `.I(V)_mtrx` + `_0001.mtrx` header | spectra grouped by point and repetition, scan images as maps, per-spectrum timestamps and positions, line scans detected automatically |
| **Omicron flat** | `.Z_flat`, `.I_flat` | scan images |
| **Nanosurf** | `.nid` | STS grids and point sets, every measurement session in a folder, AFM/STM image channels |
| **Park Systems** | `.ps-ppt`, `.tiff` | PinPoint force/spectroscopy curves, property maps |
| **WITec** | `.wip` | PL/Raman spectra, optical previews, annotations |
| **NeaSpec SNOM** | `.txt`, `.dat` | multi-channel near-field data |

Plus plain `.csv` for anything TRANS itself wrote.

## The tools

> **Per-tool pages** — inputs, every parameter with its default, outputs and
> the method behind each — are in [`tools/`](tools/README.md). The tables
> below are the overview.


### Tools — one operation, one dataset (or several, in sequence)

| tool | does |
|---|---|
| **Curve Smoothing** | Savitzky–Golay, Gaussian or moving average |
| **Derivative Calculator** | dI/dV or d²I/dV², with smoothing before and after |
| **Integration Utility** | area under curves over bias intervals |
| **Curve Fitting** | polynomial fit; also emits the coefficients as a dataset |
| **Background Subtraction** | subtract one dataset from another |
| **Truncate Data** | cut the sweep to a bias window |
| **Average Curves** | one mean curve from a dataset |
| **Peak Indexing** | index and label peaks |
| **Curve Analysis** | per-curve summary statistics |
| **Filter Bad Data** | separate usable spectra from junk — see below |
| **Cosmic Ray Filter** | remove single-sample spikes |
| **Spectral Axis Converter** | nm ↔ eV ↔ cm⁻¹ |
| **1D FFT** | frequency content of a spectrum |
| **Gradient Filter** | gradient-based filtering |
| **Spatial Average** | average neighbouring positions |
| **Map Discretizer** | bin a map into blocks |
| **Map Processing** | operations on map channels |
| **Image Smoothing** | smooth an image channel |

### Composite tools — a whole analysis in one run

| tool | does |
|---|---|
| **Map Generator** | background removal + interval integration + map assembly in one pass; writes one calibrated map per bias interval plus a joined interval map |
| **Confinement Analysis** | peak finding and background in one pass; emits the occupancy table (which states exist at which bias) |
| **Confinement Dimensionality** | 0D/1D/2D from the *ratios* between levels at the band edge |
| **Confinement Designer** | search for the geometry whose eigenstates match your measured levels |
| **Line Scan Designer** | one confinement search per position along a line |
| **Quantum Well Solver** / **Quantum Dot Solver** | solve a 1D well / 0D dot directly |
| **Spectral Features** | per-spectrum feature table (gap, doping, metallicity) |
| **Multi-Peak Fitting** | Gaussian / Lorentzian / pseudo-Voigt multi-peak fit |
| **Detect Bandgap & Doping** | gap size and N/P/neutral per spectrum |
| **Dirac Point Estimator** | Dirac point from linear-slope intersections |

**Saved workflows** appear in the same menu: a workflow you built in the node
editor, saved as `.flow`, runs over a dataset selection like any other tool.

### Multi-dataset runs

Tools that support it use a multi-select list instead of a single combo box:
Ctrl/Cmd-click to toggle, Shift-click to extend, or drag rows from the project
browser onto the tool window. Datasets are processed **one after another,
never merged**, so each output traces back to exactly one input. With more
than one input, results are registered but windows are not opened — otherwise
twenty graphs bury the workspace.

## Worked example — cleaning a dI/dV overview

**Input.** A MATRIX session imported as `2026Jul21-143815 · overview`: 2082
columns named `P01R001`, `P01R002`, … — point, then repetition.

**Run Filter Bad Data** with outlier filtering on.

**Output** — four datasets and a report, in `<project>_outputs/curves/<name>_Filtered/`:

| output | contents |
|---|---|
| `… - Good Data` | the spectra that passed |
| `… - Bad Data` | the ones that did not, so you can look at them |
| `… - Outliers Removed` | **one curve per point**, each the average of that point's surviving repetitions |
| `… - FFT Spectra` | frequency content, for spotting periodic pickup |
| `…_filter_report.txt` | every spectrum's score, and why each rejection happened |

The report is the part worth reading:

```
 Index      Sat    Noise   Linear   Periodic    Partial   Featless   Combined      Trigger   Status      Ratio   Cohere       Sigma
     0    0.000    0.000    0.000      0.000      0.000      1.000      1.000  featureless      BAD       11.7    0.052   3.086e-12
     1    0.000    0.000    0.000      0.000      0.000      0.000      0.000            -     GOOD      412.9    0.487   9.900e-12

Outliers (compared within each point, 16 group(s), 8 intervals, z>3.5)
  point 9: Removed 1 offset outlier(s): P09R117.
  point 10: 58 curves look like bandgap outliers, more than the 5 allowed — that is
            a distribution of values, not a few odd curves. None removed; check them by eye.

Per-point averages ('… - Outliers Removed'): 13 point(s), 2014 curve(s) averaged,
  1 dropped as outliers, 67 already rejected by the per-spectrum tests.
```

### Reading Filter Bad Data's knobs

Six detectors, each with a weight; a spectrum is bad when its **highest**
weighted score reaches the threshold, so any one detector firing is enough.
Set a weight to 0 to switch that detector off.

- **Saturation** — the signal railed and the noise died with it.
- **Noise** — no signal above the noise.
- **Linear** — a straight line, i.e. a contact artifact.
- **Periodic** — a sharp line in the FFT (mains pickup, piezo resonance).
- **Partial noise** — part of the sweep broke down.
- **Featureless** — the curve carries no structure at all. This is the one
  that catches a dI/dV sitting flat above the noise floor, which passes every
  other test.

**Outliers** are separate and opt-in. An outlier is a curve that is sound on
its own but wrong to average in. Three kinds, each with its own checkbox and
its own limit:

- **Offset** — displaced across the whole sweep. Wrecks an average.
- **Band gap** — departs only over part of the sweep. May be real physics, so
  it is off by default.
- **Saturation** — covers far less bias range than the rest.

Find more than the limit and **nothing is removed**: that many is a
distribution, not a few odd curves, and the report says so.

> ⚠ Outlier filtering is for **overview datasets**, where the curves are
> repetitions of the same measurement. On a line scan, where every position is
> supposed to differ, it will report the ends of the line as outliers. The
> program lets you do it anyway.

## What it writes

Measurement data is always exported with its **real physical dimensions**, never
as pixel counts or a 0–255 normalisation.

| format | for |
|---|---|
| `.gwy` | Gwyddion, all channels of a scan in one file — this is what imports write |
| `.gsf` | Gwyddion Simple Field, one calibrated field per file |
| `.tiff` | ImageJ/Fiji, with resolution tags and a display range |
| `.csv` | spectra, tables, anything curve-shaped |
| `.hrt` | the project itself |

**Gwyddion ignores TIFF resolution tags.** Its pixmap importer asks you to type
the dimensions and pre-fills the last ones you used. `.gsf` carries
`XReal`/`YReal`/`XYUnits`/`ZUnits` explicitly and is the only format that opens
correctly scaled there.

## Projects, autosave and recovery

A project is one `.hrt` file plus an `<name>_outputs/` folder. **Save is
manual** (`⌘S`); an autosave writes `<name>.autosave.hrt` every five minutes
while there are unsaved changes. If the autosave is newer than the project on
open, the program offers to recover from it — **accept, then immediately Save
As under a new name.**

Logs go to `~/Library/Logs/TRANS/trans_qml.log` on macOS. Preferences, the
dock layout and the recent-projects list live in `~/.trans_qml/`.

---

# Level 2 — Under the hood

## The path a measurement takes

```
 file(s) on disk
   │
   ├─ loader                    per-format; produces SpectralData / ImageData /
   │                            MultiChannelMap, plus per-spectrum provenance
   ▼
 SpectralData                   a DataFrame whose first column is the shared
   │                            independent axis and whose others are spectra,
   │                            plus SpectralMetadata
   ├─ AppBackend._datasets      the live registry, keyed by dataset name
   ▼
 tool (on a worker thread)      reads a dataset, writes a new one
   │
   ├─ outputs/                  .csv / .gsf / .tiff / .gwy, physically calibrated
   ├─ browser                   auto-filed into <Type>/<session>
   ▼
 .hrt project file              everything, gzipped JSON behind an HRT2 magic
```

The whole design rests on one invariant: **a dataset knows its own physical
meaning.** Units, positions in metres, acquisition times and the identity of
each column travel with the data, so a tool three steps downstream can still
put a result on the sample in nanometres.

## Libraries

| library | used for |
|---|---|
| **PySide6** (Qt 6) | the entire UI — QML for layout, `QQuickPaintedItem` for canvases, `QThread` for workers |
| **NumPy** | every array |
| **pandas** | `DataFrame` is the in-memory shape of a dataset |
| **SciPy** | `signal` (Savitzky–Golay, `find_peaks`), `sparse.linalg.eigsh` (eigenstates), `optimize` (fits), `ndimage`, `interpolate` |
| **matplotlib** | plotting inside QML canvases, including 3-D via `mpl_toolkits.mplot3d` |
| **scikit-learn** | KMeans, for clustering |
| **h5py** | HDF5 |
| **tifffile** | calibrated TIFF read/write |
| **Pillow** | image handling and previews |
| **access2theMatrix** | the Omicron MATRIX binary parser |
| **gwyfile** | pure-Python `.gwy` writer — no Gwyddion install needed |
| **NSFopen** (vendored, `src/data_loaders/nsfopen/`) | Nanosurf `.nid` |
| **pyobjc** (macOS) | sets the menu-bar application name |

The WITec `.wip` parser is **written from scratch** in
`src/data_loaders/witec_wip/wip_parser.py` — the format is a tagged tree with
no public library.

## File formats and encodings

### `.hrt` — the project file

```
b'HRT2'  +  gzip stream  →  JSON
```

Four magic bytes then a gzip stream that inflates to one JSON document:
datasets (as records), maps, in-memory maps, images (base64 float32),
notes, browser tree, window geometry, naming convention.

Saves are **atomic**: write `<name>.hrt.tmp`, `fsync`, keep the previous file
as `<name>.hrt.bak`, then `os.replace()`. An interrupted save can no longer
destroy the project. Loads stream (`gzip.GzipFile` → `json.load`) instead of
holding the compressed bytes and the full text at once.

On a damaged file the load path tries, in order: `.hrt.bak`, then
`<stem>.autosave.hrt` **regardless of mtime** (an interrupted save leaves a
fresh mtime on an unusable file), then salvages the prefix — inflating as far
as possible and closing the JSON containers left open. A recovered load is
flagged and the user is told to save under a new name.

Autosaves use gzip level 0. Float64 spectra compress about 5% at *any* gzip
level, so the compression was pure cost.

### `.gsf` — Gwyddion Simple Field

Text header (`XRes`, `YRes`, `XReal`, `YReal`, `XYUnits`, `ZUnits`), NUL
padding to a 4-byte boundary, then little-endian float32 rows. The only format
Gwyddion reads dimensions from without asking.

### Omicron MATRIX

`<base>--<run>_<scan>.<channel>_mtrx` beside a `<base>_0001.mtrx` header.
**Run** is the physical point or experiment; **scan** is the repetition at it.
The header is a chain of tagged blocks describing every acquisition in the
session; the data files hold one curve each.

Two things are read directly from the bytes rather than through
access2theMatrix: the **acquisition timestamp** (`TLKB` block, uint64 Unix
seconds — the library keeps only a formatted string) and the raw values, so
**ADC rails can be masked to NaN before scaling** (exact codes
`-2147483648`, `2147418112`, `2147483647`).

### WITec `.wip`

A tagged tree (`WIT_PR06`). Spectra are `TDGraph` payloads; the spectral axis
is a polynomial in bin index (`TDSpectralTransformation`); pixel↔µm
calibration is a `TDSpaceTransformation` affine. Each acquisition has a
sibling `TDText` "Info" entry — id = data id + 1 — holding start time,
objective, stage position, integration time and accumulation count as RTF
text.

## Heuristics — where the numbers came from

Everything here was **measured against real data**, not chosen by taste.

### Peak detection (`CONFINEMENT_DEFAULTS`)

**arPLS background + a noise-relative threshold at 2σ.** Against planted
states ~1% of the band-edge height, ModPoly found **0%** at any threshold
while arPLS found **100%** with no false peaks: ModPoly cannot follow an
exponential band edge, so weak states are gone before the search runs. With
`height_mode='noise'`, `height` is a multiple of the spectrum's own noise σ,
estimated from the *raw* curve, never the smoothed one.

`MAP_DEFAULTS` differs deliberately: 3σ and a 1σ noise floor. Maps use 3σ
(same sensitivity, far more of the map's weight in real states); peak analysis
keeps 2σ (3σ costs ~8% of weak states). The floor is what stops a map reading
as a fit diagnostic — a bin with no state integrates pure noise, negative half
the time; flooring at 1σ zeroes 39% of cells while keeping 99.4% of the signal.

### Filter Bad Data

| detector | rule | calibration |
|---|---|---|
| Featureless | amplitude vs. noise **or** coherence (`span / total variation`) below threshold | on real STS the noise is 1/f, so dead spectra sit 10–30× above the white-noise expectation while holding no shape; coherence is the half that works. Kept curves min 0.091, rejected max 0.084 — no overlap |
| Saturation | longest run at a rail **whose scatter collapses below 0.25σ** | a gap floor is a plateau too; what a railed converter loses and a gap keeps is its own noise |
| Noise | smoothed peak-to-peak ÷ robust MAD σ | the raw peak-to-peak measures the noise twice over on a featureless curve |
| Periodic | power **concentration** — peaks' share of the analysed band ÷ their fair share | share alone saturates on any smooth spectrum; real STS measures 4.5–8.5×, a 1%-amplitude sine artifact 26–58× |
| Partial noise | a window with no structure **and** noise ≥3× the sweep's quietest stretch | both conditions needed, or every gapped spectrum is condemned |

### Outliers

Area per bias sub-interval, median/MAD z-scored **across the curves taken at
the same point**. Offset = departs in ≥75% of intervals; band gap = departs in
a contiguous run of ≥2; saturation = covers <0.8× the median bias range.
`min_run = 2` because a single departing interval flagged 3.6% of curves in
clean populations and two adjacent ones flag 0.0%.

### Line-scan detection

A line scan is a contiguous run of ≥4 points whose positions are straight
(perpendicular deviation <6 px), monotone and evenly spaced (max/min step <3).
Detection runs **within each repetition-count bucket**, so a parallel
single-sweep does not corrupt a multi-rep line. Buckets join counts within
25% — a position ending with 63 or 65 instead of 64 must not break its line,
while a 1-rep sweep beside a 64-rep scan stays separate.

### Negative LDOS is not a measurement

dI/dV is proportional to a density of states, which cannot be negative. Where
a corrected spectrum dips below zero it is noise or an over-subtracted
background. Two things therefore exclude it, both via
`src/processing/positivity.py`:

- **Model fits** take `positive_mask(y)` — finite and `>= 0`; zero is kept,
  being a real reading of "no states here". Peaks are still *detected* on the
  whole curve, because a detector needs a contiguous grid to measure width on.
- **Integrals** take `positive_integral(y, x)`. This is *not*
  `np.trapz(np.maximum(y, 0))`: clipping first moves a zero crossing to the
  end of its segment and over-counts the triangle beyond it, by a factor of
  two on a curve that swings evenly about zero. The crossing is solved for.

It does **not** apply to background fitting — arPLS, ALS and ModPoly work by
sitting below the data, and dropping the samples underneath them breaks the
asymmetry they are built on. Nor to signed quantities: current in an I(V)
sweep really is negative at negative bias.

## Concurrency

One **persistent worker thread** runs tools; a second runs I/O so a save never
blocks a tool. Work is submitted as named tasks; a duplicate name is dropped
rather than queued twice. Cancellation is cooperative — a tool polls
`task.cancelled` in its loop.

Qt paints on its own **scene-graph render thread**, and matplotlib runs inside
`QQuickPaintedItem.paint()`, i.e. on that thread. Secondary threads get a
512 KB stack on macOS, which is not enough for OpenBLAS's parallel LU: the
application therefore caps BLAS to one thread before NumPy is imported. At the
sizes this program works at that is free, and often faster — the thread-pool
overhead dominates.

## Quirks worth knowing

- **QML properties must be `Property()`**, not `@Slot(result=...)`, or
  bindings never update.
- **Unstyled Qt controls follow the OS, not the theme.** The app forces the
  `Basic` QtQuick style because it is the only one that honours `palette`; the
  native macOS style paints tool panels unreadably light.
- **`import QtQuick 2.15` hides `palette`** (it arrived in revision 6.0) and
  fails as a hard component load error, not a silent no-op.
- **Indices are zero-padded** (`src/utils/naming.py`, minimum width 2) so
  alphabetical order matches acquisition order: `P01R001`, not `P1R1`.
- **Embedded windows go through signals**, never OS windows.
- **A dataset's `intervals` key marks it as integrated values**, and the
  Hyperspectral tab skips those; interval maps use `interval_bounds` /
  `interval_midpoints` instead.
- **`~/Documents` is iCloud Drive on the development machine.** Un-downloaded
  placeholder files (`st_blocks == 0`) block reads at 0% CPU, which looks
  exactly like a hung import; the loader pre-flights for this. The same File
  Provider metadata makes `codesign` refuse a bundle built there.

---

# Level 3 — Inside the engine

## Shape of the codebase

~67,000 lines of Python plus 98 QML files.

| package | what lives there |
|---|---|
| `src/backend/` | the QML bridge, tools, workers, project and workflow machinery |
| `src/models/` | the data containers — everything else is built on these |
| `src/data_loaders/` | one module per instrument, plus the shared session conventions |
| `src/processing/` | pure algorithms on arrays; no Qt |
| `src/physics/` | eigenstates, potentials, level-ratio fitting; no Qt |
| `src/widgets/` | `QQuickPaintedItem` canvases and the pyqtgraph ports |
| `src/utils/` | naming, units, and the calibrated export writers |
| `src/qml/` | the interface |

`src/processing/` and `src/physics/` import no Qt at all, which is why they
are directly testable.

## The data containers (`src/models/`)

### `SpectralData` — the thing everything operates on

```python
SpectralData(data: pd.DataFrame, metadata: SpectralMetadata, topography=None)
```

The DataFrame's **first column is the shared independent axis** (bias, energy,
wavelength) and every other column is one spectrum. Key members:

- `independent_var` / `independent_var_name` — the axis and its column name
- `spectra` — the DataFrame minus the axis column
- `num_spectra`, `num_points`
- `correct_meander()` — reverses odd rows of a meander scan, **by column
  name**, so anything keyed on names survives the reorder
- `to_3d_cube()` — `(n_points, dim_v, dim_h)` for map work

`SpectralMetadata` carries `source_type`, `dimensions`, `scan_mode`, `units`
and an open `additional_info` dict. That dict is the extension point, and a
few of its keys are load-bearing:

| key | meaning |
|---|---|
| `spectrum_meta` | **list of dicts, one per data column**, each with at least `column`. Keyed by *name*, not position, so it survives a meander correction and a tool that keeps a subset |
| `position_m` | position per spectrum, in metres |
| `spatial_layout` | `area` / `line` / `point` |
| `session_label` | which acquisition session this came from — drives browser filing |
| `original` | the dataset this was derived from; makes results overlay onto the source's graph |
| `sweep_channels` | Forward / Backward / Mixed frames sharing one axis |

Other containers: **`ImageData`** (multi-channel image entity, one per scan
rather than one per channel, with `pixel_size_nm`), **`MultiChannelMap`** +
`MapChannel` (map data with per-channel processing history and
`MapMetadata.physical_size`), **`TopographyData`**, and **`TableDataModel`**
(a `QAbstractTableModel` with a spreadsheet `FormulaEngine`).

## The backend (`src/backend/`)

### `AppBackend` — the bridge

`class AppBackend(ToolImplementations, QObject)`, ~7,800 lines, 162 public
methods. It is the single object QML talks to. It owns:

- `_datasets` — an `_ObservableDict` of live datasets, name → `SpectralData`
- `maps`, `_maps_inmem`, `_images`, `_notes`, `output_files`
- `_browser_tree` — folders and placements
- the managers below

QML calls its `@Slot`s and binds to its `Property`s; it emits signals back
(`dataLoaded`, `mapCreated`, `browserTreeChanged`, `openDatasetEmbedded`, …).

`ToolImplementations` is a **mixin**, not a member: every tool is a method on
it, so tools reach `self._datasets` and `self.errorOccurred` directly while
living in their own 6,300-line module.

### Import and filing

`_do_load_file` / `_do_load_folder` run on the worker and return a result
dict; `_on_file_loaded` / `_on_folder_loaded` handle it on the main thread.
The result contract is loader-agnostic:

```python
{'datasets': {name: SpectralData},
 'active_dataset': name,
 'browser_folders': {'dataset:<name>': '<session label>'},   # optional
 'matrix_maps': [...]}                                        # optional
```

`_on_file_loaded` registers the datasets, absorbs any images/notes/maps their
metadata carries, and files everything into `<Type>/<session>`. The session
name comes from `browser_folders` when a loader set one, otherwise
`_group_label` derives it from `session_label`, `source_file` or
`source_directory` — so a **new loader inherits the convention without opting
in**. `_on_folder_loaded` delegates to `_on_file_loaded` whenever the result
carries session structure.

### Threading

`WorkerManager` owns two `PersistentWorker` threads (a general one and an I/O
one), each draining a queue of `Task` objects. `submit(name=…, operation=…,
on_finished=…)` returns False if a task of that name is already in flight.
`AutosaveManager` holds a `QTimer` and writes only when it has seen
`projectModifiedChanged(True)` since its last write — which is why **every
path that adds project state must call `AppBackend._mark_project_modified()`**.
Tool results once did not, and a whole session could exist only in memory.

### Projects

`ProjectManager` serialises and restores the `.hrt`. `save_project` is atomic
(tmp + fsync + `.bak` + replace); `load_project` streams, and falls back
`.bak` → autosave → `salvage_project_json`.

### Workflows

`workflow_engine.py` defines the node vocabulary: `PortType`, `Port`,
`WorkflowNode`, `Connection`, `Workflow`, and `TOOL_DEFINITIONS` — a dict
describing every node's inputs, outputs and parameters (44 nodes across
Processing, Image Processing, Analysis, Output, Input, Visualization,
Annotations). `WorkflowExecutor` runs nodes in topological order; with several
input datasets it runs the whole graph **once per dataset**.

### Multi-dataset runs

`batch_tools.py` is a registry: one `BatchToolSpec` per tool says which method
to call and how to coerce the parameter map. `AppBackend.runToolOnDatasets`
drives any registered tool over a selection as a single task. Adding a tool is
one registry entry plus swapping the QML combo for `DatasetMultiSelect` — no
new backend slot.

## Loaders (`src/data_loaders/`)

All subclass `BaseDataLoader`, which supplies `load_from_directory`,
`load_single_file`, `validate_directory`, `find_files`, `create_metadata`,
`concatenate_spectra` and `discover_sidecar_images`. A loader may also offer
`smart_load_from_file` — pick one file, get its whole session.

| loader | notes |
|---|---|
| `OmicronMatrixSTSLoader` | the richest. Sessions → points → repetitions; keys a batch by `(run, location)`; detects line scans; builds maps and pictures from scan images. Reads the header **once** and walks it with a shared cursor, because access2theMatrix re-parses up to 16 MB per file (16,494 files: hours → 17 s) |
| `NanosurfSTSEnhancedLoader` | fingerprints each `.nid` header (spec mode, repetition mode, data points, modulation, grid) and clusters by settings **and** time; `discover_sessions()` returns every session in a folder |
| `WitecWipLoader` | groups spectra by spectral axis; normalises counts by integration time × accumulations |
| `ParkAFMLoader` | `PsPptParser` for PinPoint, plus calibrated TIFF property maps |
| `NeaSpecSNOMLoader`, `OmicronFlatLoader` | text multi-channel, and flat scan images |

`session_organization.py` holds the shared conventions:
`format_session_label`, `disambiguate_labels` (drop the clock time only while
it stays unambiguous), `grid_positions_m` (grid → metres, row-major, `None`
rather than an invented scale) and `spatial_info`.

## Processing (`src/processing/`) — pure, testable

| module | contents |
|---|---|
| `peak_detection.py` | the engine behind Confinement Analysis and the Map Generator: `Params`, `Analysis`, `Peak`, plus baselines (`arpls_baseline`, `als_baseline`, `snip_baseline`, `rubberband_baseline`, …), `smooth`, `noise_sigma` |
| `positivity.py` | `positive_mask`, `positive_part`, `positive_integral` — the negative-LDOS rule, stated once |
| `curve_outliers.py` | `analyze_outliers`, `build_groups`, `analyze_grouped`, `select_outliers`, `select_grouped` |
| `edge_analysis.py` | band-edge fitting, Feenstra normalisation, the thermal slope ceiling |
| `spectral_features.py` | gap, doping, metallicity and confinement features per spectrum |
| `spatial_coherence.py` | whether one number describes every point's band tail |
| `discretization.py`, `derivatives.py`, `integration.py`, `background_subtraction.py`, `cosmic_ray.py`, `plane_correction.py`, `iv_processor.py` | one job each |

## Physics (`src/physics/`) — no Qt either

`solvers.py` is the core: `solve_well_1d/2d/3d`, the curved-coordinate
variants (`_polar`, `_cylindrical`, `_spherical`), `solve_dot`, and
`well_from_spec`/`dot_from_spec`. They assemble a finite-difference
Hamiltonian from `laplacian.py` and hand it to `scipy.sparse.linalg.eigsh`.

`features.py` defines the potential vocabulary — 16 shape classes from
`SegmentFeature1D` to `LensFeature3D`, each able to stamp itself into a grid;
`build_potential_from_features` composes them. `feature_specs.py` is the
serialisable table behind the interactive editor.

`designer.py` runs the inverse problem: given measured levels, search
geometries whose eigenvalues match. `level_patterns.py` and
`level_ratio_fit.py` do the dimensionality verdict from **ratios** between
levels, with `RatioVerdict` ranking every geometry and reporting when the
answer is ambiguous. `line_scan.py` applies that per position along a line.

## Widgets (`src/widgets/`)

Canvases are `QQuickPaintedItem` subclasses that render matplotlib figures:
`QMLMapCanvas`, `QMLGraphCanvas`, `QMLProfileCanvas`, `FigureCanvasItem`,
`DesignerCanvas`, `SolverCanvas`, `PotentialCanvas`, `StatesCanvas`. They are
registered as QML types under `TransQML 1.0` in `src/main.py`.

`_pyqtgraph_ports/` is a small, self-contained port of the pyqtgraph
interactions the program needs — `InfiniteLine`, `LinearRegionItem`,
`RectROI`, `TargetItem`, a legend, histogram LUT and curve-path helpers — each
with a JSON-serialisable `*State` so window state survives a project save.

> **Coordinate rule.** The matplotlib axes inside a native-rendered canvas is
> **not laid out**, so `ax.transData` is meaningless there. Use the canvas's
> own `_dataToPixel`.

## Utilities (`src/utils/`)

| module | contents |
|---|---|
| `field_export.py` | `export_field()` — **the single enforced entry point** for writing measurement data. Writes both `.gsf` and `.tiff`; if the scale is genuinely unknown it still writes but logs a warning naming the call site, so gaps surface instead of being silent |
| `gsf_io.py`, `gwy_io.py`, `tiff_io.py` | the format writers |
| `units.py` | `to_nm`, `pixel_size_to_nm`, `scale_from_metadata` — handles m/mm/µm/nm/Å/pm and returns `None` for non-length units |
| `naming.py` | `pad`, `padded_series`, `strip_acquisition_time` |
| `app_paths.py` | where things live, frozen or from source |
| `color_contrast.py` | the WCAG guard on colour schemes |

## Conventions for changing the code

- **Never add a bare `tifffile.imwrite` / `Image.save` for measurement data.**
  Call `export_field()`; it is the policy layer.
- **Carry spatial metadata across a tool.** `ToolImplementations._carry_spatial_info`
  copies `spectrum_meta`, `position_m`, `position_step_m` and `spatial_layout`;
  a tool keeping a subset of columns passes those names so the per-spectrum
  entries are filtered to match. Without it, a derivative of a line scan maps
  onto point indices instead of nanometres.
- **Mark the project modified** from any path that adds state, or the autosave
  will silently skip it.
- **Tool panels** use `ToolSection`, `ToolComboBox`, `ToolSpinBox`,
  `ToolCheckBox`, `ToolSlider` from `src/qml/components/`, which resolve the
  palette through `ToolTheme`. Do not rely on the native style.
- **Never `git stash` in this repository** — historically tracked `.pyc` files
  made `pop` conflict.

## Tests

`tests/` mirrors `src/`: ~3,870 passing. Four cosmic-ray tests are knowingly
red — the 5σ default on a median-filter residual flags about one noise sample
per thousand, so both the tests and the default are marginal. One multi-peak
timing test is a wall-clock bound and flips between runs.

Tests that build a real `AppBackend` must stub `_persist_imported_datasets`:
letting real I/O-worker tasks start and be garbage-collected mid-test
segfaults the suite.
