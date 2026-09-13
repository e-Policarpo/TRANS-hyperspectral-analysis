# Workflow system inventory — tools vs. nodes

**Status (2026-09-12, same day): items 1–11 of the change list below are
implemented; 12 is implemented in its executor half (`_run_batch_tool`, used
by every new node and by FFT), 13 is a convention now followed by the new
nodes and by FFT / Map Generator but not yet retrofitted onto the older
branches.** The tables are kept as the record of what was found; each
"gap" cell now describes the state that was fixed. Verified by
`tests/test_backend/test_workflow_rework_nodes.py`.

Taken 2026-09-12, after the tool rework (list selection everywhere, Unit
Converter, Multi-Peak Fitting over datasets, Dirac point in Spectral
Features, spatial averaging and integration inside the Map Generator, five
tools sunset). The question: **does every tool in the palette have a
workflow node that reproduces it, with the same knobs and the same
outputs?** Below, the answer per tool, then the list of changes the
workflow system needs, ranked.

Node definitions: `src/backend/workflow_engine.py` (44 node types).
Execution: `WorkflowExecutor._execute_node` in `src/backend/workflow_manager.py`
(one `elif tool_name == …` per node). Palette: `src/qml/workflow/WorkflowToolPalette.qml`,
sectioned by the node's `category`.

## Coverage, tool by tool

Legend — ✅ node reproduces the tool · ⚠️ node exists but lags the tool ·
❌ no node · — a node makes no sense (viewer / solver with no dataset in).

### Prepare (basic)

| tool | node | status | gap |
|---|---|---|---|
| Unit Converter | — | ❌ | No node for any of its three modes. *Relabel* is an in-place metadata edit and belongs in a workflow as a `SetUnits` node (stamp units/names on the dataset flowing through). *Convert axis* → `AxisConvert` node over `convert_axis_dataset`. *Set values* → `SetValues` node over `apply_formula_dataset` (x/y formulas). `DataManipulation` ("Math Operation") is the closest thing but works on A/B whole-dataset operands, not on x and y separately, and has no unit stamping. |
| Truncate Data | `TruncateData` | ✅ | — |
| Curve Smoothing | `CurveSmoothing` | ✅ | — |
| Cosmic Ray Filter | `CosmicRayFilter` | ✅ | — |
| Subtract Detector Background | `BackgroundSubtraction` | ⚠️ | Engine matches (`subtract_background_datasets`). Display name still "Background Subtraction"; rename to match the tool. |
| Filter Bad Data | `FilterBadData` | ✅ | — |
| Average Curves | — | ❌ | `average_curves` has no node. Trivial to add (dataset in, dataset out, no parameters). |

### Transform (basic)

| tool | node | status | gap |
|---|---|---|---|
| Derivative Calculator | `Derivative` | ✅ | — |
| Curve Background Flattening | `CurveFitting` ("Baseline") | ⚠️ | Engine matches (`fit_curves`). Display name "Baseline" collides with `BaselineEstimate`; rename to "Background Flattening". |
| Integration Utility | `Integration` | ✅ | — (also see Map Generator below) |
| 1D FFT | `FFT1D` | ⚠️ | **Three problems.** (1) The node declares an `output_type` parameter (magnitude / phase / complex) that the executor never reads. (2) The executor calls `_do_fft1D(task, name)` with none of the tool's new parameters (`window`, `detrend`, `one_sided`, `power_spectrum`). (3) Its `fft_result` port is typed `dataset` but carries the **CSV path string** the method returns, not a dataset — a downstream node receives a string. Fix: expose the four parameters, and emit two dataset ports (`magnitude`, `phase`) taken from `_datasets` after the call. |

### View (basic)

| tool | node | status | gap |
|---|---|---|---|
| Curve Plotting | — | — | A viewer; `DatasetOutput` is the workflow's way to see a result. Nothing to add. |

### Fit and features (intermediate)

| tool | node | status | gap |
|---|---|---|---|
| Multi-Peak Fitting | — | ❌ | No node. Add `MultiPeakFit` over `fit_multipeak_dataset` (params `peak_shape`, `n_peaks_auto`, `baseline_degree`, `positive_only`; ports: `peak_table` flat_data, `fitted` dataset). This is the natural successor of `PeakFinder` for anything that needs widths and amplitudes. |
| Spectral Features | `SpectralFeatures` | ⚠️ | Engine matches, but the node's parameter list predates the Dirac group: `dirac_mode`, `dirac_edge_trim`, `dirac_left_min/max`, `dirac_right_min/max` are missing, so a workflow always runs the default (`auto`) and cannot switch it off or set manual windows. Add the six parameters (they pass straight through `_feature_config`). |

### Maps (intermediate)

| tool | node | status | gap |
|---|---|---|---|
| Map Generator | `MapGenerator` | ⚠️ **major** | The node is the **pre-rework Map Generator**: it takes a `flat_data` input and calls the old flat-values path (`generate_all_maps`), i.e. it maps numbers that were already integrated. The tool takes **spectra** and runs `generate_maps_from_spectra` — background removal, interval detection (peaks / previous analysis / manual), spatial averaging, integration with the noise floor, per-interval maps, the joined interval map, the `- Map Values` dataset and the integrated CSV. None of that is reachable from a workflow; the `Integration` → `MapAssembly` pair is the closest chain and lacks the background, the detection and the averaging. Rework the node: `dataset` input, the tool's parameter map (`scan_type`, `baseline`, `height`, `noise_floor`, `min_spectra_per_bin`, `bin_x`, `bin_y`, interval source + manual intervals), outputs `maps`, `interval_map`, `values` (flat_data), `intervals`, `binned` (dataset). Keep `MapAssembly` as the flat-values path. |
| Map Discretizer | `ImageDiscretizer` | ❌ (misleading) | Different operation: the tool bins **space** (`discretize_map`, target X×Y), the node bins **values** (`discretize_image`, n bins by uniform/quantile/kmeans). Add a `MapDiscretizer` node over `discretize_map`; keep `ImageDiscretizer` (it is its own useful thing). |
| Map Processing | `MapGaussianFilter`, `MapMedianFilter`, `MapPlaneLevel`, `MapRowAlign`, `MapNormalize`, `MapPolynomialBGRemoval` | ✅ | One node per operation. |
| Gradient Filter | `GradientFilter` | ✅ | Takes a path; `apply_gradient_filter` now also accepts `map:`/`image:` refs and writes a calibrated `.tiff` (was a 0–255 PNG). The node's `gradient` port (type `image`) gets the `.tiff` path — downstream image nodes read it fine. Optionally accept a map ref from `MapInput`. |

### Confinement (advanced)

| tool | node | status | gap |
|---|---|---|---|
| Confinement Analysis | `ConfinementAnalysis` | ✅ | — |
| Confinement Dimensionality | — | ❌ | `analyze_confinement_dimensionality` has no node (dataset in → table flat_data + whole-set verdict). |
| Confinement Designer (one spectrum) | — | ❌ | Not covered: the node called `ConfinementDesign` is the **Line Scan Designer** (it runs `design_line_scan`, "every position of a line scan"). A single-spectrum designer node would run `design_confinement` and emit the ranked candidate table. |
| Line Scan Designer | `ConfinementDesign` | ⚠️ | Engine matches, name doesn't: rename the display to "Line Scan Designer" (keep the key for saved `.flow` files). |
| Quantum Well Solver / Quantum Dot Solver | — | — | Solvers take a geometry, not a dataset. A node would only make sense fed by a designer's candidate (size + mass → levels) — possible later as `SolveWell` / `SolveDot` consuming the designer table, not needed for parity. |

### Sunset tools (still nodes)

| former tool | node | recommendation |
|---|---|---|
| Image Smoothing | `ImageSmoothing` | keep (asked for). Also duplicated by `MapGaussianFilter` / `MapMedianFilter` on maps. |
| Peak Indexing | `PeakFinder` | keep — it feeds `EnergyBinning` and `OccupancyMatrix`. |
| Spatial Average | `SpatialAverage` | keep as a standalone step; the Map Generator node should ALSO get `bin_x`/`bin_y` (above) so a workflow can do it inline. |
| Detect Bandgap & Doping | `DetectBandgapDoping` | **deprecate**: hide from the workflow palette, keep executable so saved flows run. `SpectralFeatures` emits the same gap/doping columns. |
| Dirac Point Estimator | `DiracPointEstimator` | **deprecate** the same way; the Dirac group of `SpectralFeatures` replaces it. |

## Structural gaps (independent of any one tool)

1. **Node parameters are declared twice.** Every node repeats its parameters in
   `workflow_engine.py` and its executor branch re-reads them by hand in
   `workflow_manager.py`. The tool panels already have a third copy in QML,
   and `BATCH_TOOLS` a fourth (`params` + `defaults`, with casts). `FFT1D` is
   what that costs: a parameter declared, never read. A batch-backed node
   type — "run `BATCH_TOOLS[key]` on the input dataset" — would give every
   list-enabled tool a node from its spec alone, with the spec's casts and
   defaults, and remove nine executor branches (`TruncateData`,
   `CurveSmoothing`, `Derivative`, `CurveFitting`, `FFT1D`, `FilterBadData`,
   `CosmicRayFilter`, and the new `AverageCurves`, `MultiPeakFit`,
   `AxisConvert`, `SetValues`).
2. **Path-vs-dataset ports.** Several executors hand a *file path* down a port
   typed `dataset` (`FFT1D`; `CurveFitting` returns the CSV path and the
   executor fishes the dataset back out by name). The convention should be:
   a `dataset` port carries a `SpectralData`, a `map`/`image` port a path or
   id. A helper that resolves "the dataset a tool just registered" would
   make that uniform.
3. **Palette categories don't match the tool sections.** The workflow
   palette groups by `Input / Output / Processing / Analysis / Visualization /
   Image Processing / Annotations`. The tool palette and menu now use
   `Prepare / Transform / View / Fit and features / Maps / Confinement`,
   ordered by complexity. Aligning the node `category` values (and keeping
   `Input`, `Output`, `Annotations`) lets a user find a node where they found
   the tool. One-line change per node definition; the palette is already
   built from `category`.
4. **No multi-dataset semantics inside a graph.** `DatasetInput` holds a
   selection and the executor runs the whole graph once per dataset (see
   CLAUDE.md), which matches "processed one after another" — but nodes that
   take several datasets at once (`BackgroundSubtraction` signals,
   `SpatialAverage` queue) reinvent a queue UI each. A shared multi-input
   port widget would replace both.
5. **Sunset nodes are visible.** There is no `deprecated` flag on a node
   definition; `DetectBandgapDoping` and `DiracPointEstimator` sit in the
   palette beside the tool that replaced them. Add `"deprecated": True` →
   hidden from the palette, still loadable and executable.

## Change list, ranked

Effort: S = one definition + one executor branch (or a spec entry), M = a
day, L = more.

| # | change | effort | why first | done |
|---|---|---|---|---|
| 1 | `MapGenerator` node → spectra input, the tool's engine and parameters (incl. `bin_x`/`bin_y`), outputs maps / interval map / values / intervals / binned | M | The main analysis path is not reproducible in a workflow at all | ✅ `MapGenerator` takes `dataset` (+ optional `intervals` port); `flat_data` kept as the old path |
| 2 | `FFT1D`: read the parameters, emit magnitude + phase **datasets** | S | Declared parameter silently ignored; port carries a string | ✅ |
| 3 | `SpectralFeatures`: add the six Dirac parameters | S | Only default Dirac behaviour reachable | ✅ |
| 4 | New `MultiPeakFit` node | S | New tool with no node; successor to PeakFinder for widths | ✅ `MultiPeakFit` |
| 5 | New `AverageCurves` node | S | Trivial, missing | ✅ `AverageCurves` |
| 6 | New `AxisConvert` and `SetValues` (+ `SetUnits`) nodes | S–M | Unit Converter has no node; unit stamping is needed before an axis conversion in a graph | ✅ `AxisConvert`, `SetValues`, `SetUnits` (a relabelled copy) |
| 7 | New `ConfinementDimensionality` node | S | Missing | ✅ `ConfinementDimensionality` |
| 8 | New single-spectrum `ConfinementDesigner` node; rename `ConfinementDesign` display to "Line Scan Designer" | S+S | The one that exists is misnamed; the other is missing | ✅ `ConfinementDesigner`; display renamed |
| 9 | New `MapDiscretizer` (spatial) node | S | `ImageDiscretizer` is a different operation | ✅ `MapDiscretizer` |
| 10 | Deprecate `DetectBandgapDoping`, `DiracPointEstimator` (hidden, still executable); rename `BackgroundSubtraction`, `CurveFitting` displays | S | Palette parity with the sunset | ✅ `deprecated` key; displays renamed |
| 11 | Align node categories with the tool sections | S | Same map in both palettes | ✅ Prepare / Transform / Fit and features / Maps / Confinement |
| 12 | Batch-backed node type driven by `BATCH_TOOLS` | M | Removes the four-fold parameter duplication that produced #2; makes 4–7 near-free | ◐ `WorkflowExecutor._run_batch_tool` + `_stage_dataset` + `_derived`; older branches not yet migrated |
| 13 | Path-vs-dataset port convention + resolver | M | Silent type mismatches on ports | ◐ new nodes and FFT / Map Generator follow it |

Items 2, 3, 5, 10 and 11 are safe to do immediately; 1 and 12 change how
workflows are authored and should be done together, since 12 is the cheap
way to do most of 4–9.
