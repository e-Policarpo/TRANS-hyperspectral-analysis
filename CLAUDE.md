# TRANS — project conventions

## Exports MUST carry real physical quantities

**Rule: any feature that writes measurement data to disk encodes the real
physical dimensions and units whenever they are available.** A file described
as "666 × 666 pixels" is not an acceptable export — it must say 2.5 × 2.5 µm,
and the values must be the true physical ones (metres, amps, volts), not a
0–255 or 0–65535 normalisation.

This applies to every new export feature by default. Do not add a new
`tifffile.imwrite` / `PIL.Image.save` call for measurement data.

### How

Call **`src.utils.field_export.export_field()`** (or
`export_field_from_metadata()` when you hold a loader metadata dict). It is the
single enforced entry point and writes both formats below. If the scale is
genuinely unknown it still writes the file but logs a warning naming the call
site, so gaps surface instead of being silent.

| Layer | Module | Purpose |
|---|---|---|
| Policy | `src/utils/field_export.py` | `export_field()` — **use this** |
| Gwyddion, multi-channel | `src/utils/gwy_io.py` | `.gwy` — all channels in one file |
| Gwyddion, single field | `src/utils/gsf_io.py` | `.gsf` writer/reader |
| ImageJ/Fiji | `src/utils/tiff_io.py` | calibrated `.tiff` + `read_tiff_calibration()` |
| Conversion | `src/utils/units.py` | `to_nm`, `pixel_size_to_nm`, `scale_from_metadata` |

### Imported scan images → `.gwy`

Importing measurement data writes **one `.gwy` per scan, holding every channel**
(`AppBackend._save_image_to_gwy`), because Gwyddion is where this data is
analysed. It is gated on the import dialog's *"Extract images as .gwy"*
checkbox — **on by default**; when cleared, an import writes no image files at
all. `Export as .gwy…` in the project browser does the same on demand for any
image. Requires the pure-Python `gwyfile` package; `gwy_io.gwy_available()`
lets callers degrade instead of failing.

GSF is single-field by spec, so it cannot hold a multi-channel scan in one
file — that is why `.gwy` is the import format and `.gsf` the per-field one.

### Why several formats

**Gwyddion ignores TIFF resolution tags.** For generic image formats its pixmap
importer asks the user to type the dimensions in, and the values it pre-fills
are just the last ones used — nothing is read from the file. So a TIFF, however
carefully tagged, always lands in Gwyddion as bare pixels. `.gsf` (Gwyddion
Simple Field) carries `XReal`/`YReal`/`XYUnits`/`ZUnits` explicitly and is the
only format that opens correctly scaled there.

The `.tiff` is still written: Fiji/ImageJ *do* read its resolution tags, it
round-trips back into this app via `ImageData.from_file`, and it carries an
ImageJ display range so float data doesn't render all-black.

Reference: <https://gwyddion.net/documentation/user-guide-en/gsf.html>

### Don't

- Don't normalise data before writing a data export. Normalise only for a
  PNG/JPEG *preview* that sits alongside the real file.
- Don't invent a scale you don't have — leave it unset so the warning fires.
- Don't assume the lateral unit is µm; route through `src/utils/units.py`,
  which handles m/mm/µm/nm/Å/pm and returns `None` for non-length units.

## Other conventions

- QML properties use `Property()` (not `@Slot(result=...)`) so bindings update.
- Embedded windows go through signals (`openDatasetEmbedded`, …) — never OS
  windows.
- Dataset/spectrum indices are zero-padded via `src/utils/naming.py` so
  alphabetical order matches acquisition order.
- Imports are auto-filed into `<Type>/<session>` browser folders; the session
  label is derived in `AppBackend._group_label`, so new loaders inherit it.

## Tool UI style

Tool panels follow the Confinement Analysis look: `ToolSection`,
`ToolComboBox`, `ToolSpinBox`, `ToolCheckBox` in `src/qml/components/`, which
resolve the palette through `ToolTheme` (`win: <id>.Window.window` — the
attached property only works on an Item, so it cannot be read inside the
QtObject itself). Do not rely on the native style: it paints GroupBox and the
editable controls light, which is unreadable against this palette.

## Map Generator

The Map Generator takes **spectra**, not a hand-corrected flat dataset: it
removes the background and integrates over bias intervals in one pass
(`generate_maps_from_spectra`), reusing the Confinement Analysis engine.
Intervals come from a fresh peak search, from a previous analysis's datasets
(`dataset_intervals`, published as `integration_intervals`), or typed by hand
— never from a JSON file any more. Outputs are filed as
`maps/<dataset>/<format>/` (gsf, tiff, csv), and a run over several intervals
also writes a **joined interval map** — position across, interval up, indexed
by midpoint — registered as a line-scan dataset (`<base> - Interval Map`) so
the Hyperspectral tab opens it as a kymograph. Only that joined map is
opened on completion — the per-interval maps are registered in the browser
but not shown, since dozens of windows lock the workspace up
(`_on_maps_completed(..., open_paths=...)`). Its metadata must NOT use the
`intervals` key: that marks a dataset as integrated values, which that tab
skips (`interval_bounds` / `interval_midpoints` instead). A detected run's intervals are the
**occupied bins**, binned at the coarser of k_B*T/2 and the sweep's own step —
the same grid Confinement Analysis reports on, so both tools find the same
states; `min_spectra_per_bin` drops thinly-populated bins without widening the
rest. There is deliberately no FWHM-merging fallback: it fused everything into
two or three bands tens of mV wide (2 intervals where 216 states were
detected), which is what "the map generator finds almost no peaks" was. A scan-type combo picks the layout:
`map_meander` reverses alternate rows, `map_raster` doesn't, `line` produces a
single row, `auto` reads the dataset's metadata. Outputs are unchanged: one
calibrated `.tiff` (+ `.gsf`/`.csv`) per interval.

## Peak detection defaults

`CONFINEMENT_DEFAULTS` (shared by Confinement Analysis and the Map Generator)
is **arPLS + a noise-relative threshold at 2σ**, measured rather than guessed:
against planted states ~1% of the band-edge height, ModPoly found 0% at any
threshold while arPLS found 100% with no false peaks. ModPoly cannot follow an
exponential band edge, so weak states are gone before the search runs. With
`height_mode='noise'`, `height` is a multiple of the spectrum's own noise σ
(estimated from the raw curve, never the smoothed one), not a percentage —
`range` and `prominence` scale with the curve's span, which the band edges set.

## Spatial metadata must survive a tool

A tool returning one output column per input spectrum carries the source's
spatial keys across (`ToolImplementations._carry_spatial_info`:
`spectrum_meta`, `position_m`, `position_step_m`, `spatial_layout`) — a
derivative of a line scan is still that line scan's spectra, and without them
its maps fall back to point indices instead of nanometres. Tools that keep a
SUBSET of the columns pass those column names so the per-spectrum entries are
filtered to match. As a backstop, `_line_positions_m` follows a dataset's
recorded `original`/`source_dataset` when it carries none itself (bounded, and
only when the spectrum counts agree).

## Map Generator defaults

`MAP_DEFAULTS` (on top of `CONFINEMENT_DEFAULTS`) is measured, not guessed —
arPLS background, `noise` threshold at **3σ**, `noise_floor` **1σ**,
`min_spectra_per_bin` **1**. Maps and peak analysis differ deliberately: maps
use 3σ (same sensitivity, far more of the map's weight in real states), peak
analysis keeps 2σ (3σ costs ~8% of weak states). The noise floor is what stops
a map reading as a fit diagnostic: a bin with no state integrates pure noise,
negative half the time — flooring at 1σ zeroes 39% of cells while keeping
99.4% of the signal.

## Multi-dataset tools

A tool can be run over several datasets at once. They are always processed
**one after another**, never merged, so each output traces back to exactly one
input and can be named after it.

- **Tool widgets**: use `components/DatasetMultiSelect.qml` (Ctrl/Cmd-click
  toggles, Shift-click extends) instead of `DatasetComboBox`, and call
  `backend.runToolOnDatasets(<key>, list, {params})`. Enabling this for another
  tool is one entry in `BATCH_TOOLS` (`src/backend/batch_tools.py`) plus that
  QML swap — no new backend slot. A tool whose knobs are a map rather than
  keyword arguments sets `params_as_dict`; one returning more than a path sets
  `completion` to the backend method that registers its results (the Map
  Generator does both).
- **Drag & drop**: the project browser supports Ctrl/Cmd- and Shift-click
  multi-selection, and dragging any selected row drags the whole selection.
  Releasing over a tool window calls that tool's `acceptDatasetDrop(names)` —
  declaring that function (plus `property bool datasetDropActive` for the
  hover highlight) is all a tool needs to become a drop target. Delivery is
  a global-coordinate hit test in `WindowManager.deliverDatasetDrop`; there
  are deliberately no `DropArea`s (see the browser-tree notes).
- **No auto-open with several inputs**: `AppBackend._suppress_auto_open` is
  set while a multi-input run is in flight (a tool batch, a multi-dataset
  workflow run). Results are still registered in the browser, but
  `_route_derived_datasets` and `_open_map_window` stay quiet — one graph and
  one map window per input would bury the workspace. A single input behaves
  exactly as before.
- **Workflows**: a `DatasetInput` node holds `dataset_names` (full selection)
  and `dataset_name` (first pick, kept for older workflows and validation).
  `WorkflowExecutor` runs the whole graph once per dataset; output names come
  from `_format_output_name`, which uses that pass's source dataset.
