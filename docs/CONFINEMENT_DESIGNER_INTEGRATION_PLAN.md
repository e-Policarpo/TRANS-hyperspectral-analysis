# Bringing the eigenstate calculator into TRANS

Plan for folding `calculadora_autoestados` — the inverse designer *and* the
direct confinement solvers — into this repository, translated to English, as
first-class TRANS tools.

Status: written 2026-08-22, decisions locked the same day (§10).
**Phases 0 and 1 are built and tested** (§9):

- Phase 0 — `src/physics/` holds the whole solver core, the branch splitting,
  the line-scan loop and the extracted inverse designer, in English, with no
  UI toolkit anywhere in `src/`. 173 tests in `tests/test_physics/`.
- Phase 1 — `BaselineEstimate`, `EnergyBinning`, `OccupancyMatrix` and
  `MapAssembly` are workflow nodes, and a hand-wired chain reproduces both
  Confinement Analysis's occupancy tables and a Map Generator interval map
  (`tests/test_backend/test_composite_decomposition.py`).

Nothing has been deleted from the Tk app, and no designer tool exists in the
UI yet — that is phase 2.

---

## 1. What exists today

`~/Documents/Doutorado/Programas importantes/calculadora_autoestados` is a
Tkinter app, not a git repository, with 209 passing tests. It splits cleanly
in two:

| Layer | Lines | Depends on | Portability |
|---|---:|---|---|
| `core/` — physics, 12 modules | ~2 600 | numpy, scipy | **moves as-is** (translate only) |
| `gui/` — 6 Tk modules | ~6 400 | tkinter, matplotlib | must be rehosted |
| `tests/` — 209 tests | ~1 500 | pytest (+ Tk for GUI tests) | mostly moves |

`core/` is already free of Tk *and* of Qt. It contains:

- `analytical.py`, `quantum_dot.py` — closed-form levels for boxes, discs,
  cylinders, spherical/disc/parabolic dots.
- `laplacian.py`, `eigensolver.py`, `potentials.py`, `features.py` — the
  finite-difference solvers for arbitrary 1D/2D/3D potentials.
- `tunneling.py` — barrier transmission.
- `solution_spec.py` — the geometry interchange format between modules.
- `pairing.py` — electron–hole pairing and band edges from fit offsets.
- `line_scan.py` — one confinement search per spectrum, grouping, segments.
- `didv_import.py` — CSV reading + branch splitting.
- `trans_bridge.py` — loads *this repo's* `peak_detection.py` by file path.
- `debug_log.py` — logging.

Two of those exist only because the calculator lives outside TRANS and
**disappear on integration**: `trans_bridge.py` (it can just import) and the
CSV half of `didv_import.py` (datasets come from the project, not from disk).

---

## 2. The architectural call: embed Python, don't port to QML

**TRANS already does this.** `src/widgets/qml_graph_canvas.py` and
`src/widgets/qml_map_canvas.py` are `QQuickPaintedItem`s that own a
matplotlib `Figure`, render it with `FigureCanvasAgg`, and blit
`canvas.buffer_rgba()` in `paint()`. The calculator's `gui/plotting.py`
builds the same `Figure` and hands it to `FigureCanvasTkAgg`.

So the seam is exactly one function. Every `ax.plot(...)`, every colorbar,
every `pcolormesh` in the calculator's 6 400 lines of GUI is **host-agnostic
matplotlib** and ports unchanged. What changes is who owns the canvas.

### The one new component

`src/widgets/qml_figure_canvas.py` — `FigureCanvasItem(QQuickPaintedItem)`:

- owns a `Figure` + `FigureCanvasAgg`, exposes `figure` to Python callers;
- `paint()` blits the RGBA buffer (copy `qml_graph_canvas.paint`, minus the
  curve machinery);
- `@Slot() redraw()` re-renders after a caller mutates the figure;
- resize → debounced re-render (the existing 150 ms QTimer idiom);
- HiDPI: set figure DPI from `window.devicePixelRatio`, and render at device
  resolution — see `graph-canvas-native-coords` notes; getting this wrong is
  the "blurry on Retina" bug already fixed once in this repo;
- `@Slot() cleanup()` — `plt.close(figure)`, stop timers, per the convention.

That component is ~150 lines and is the *whole* of the porting infrastructure.
It is also independently useful: any future tool that wants a real matplotlib
plot (3D surfaces, colorbars, `mplot3d`) gets one for free, instead of
reimplementing it in QPainter.

### What still gets written in QML

Only the control panels — combos, spin boxes, check boxes — using the
existing `ToolSection` / `ToolComboBox` / `ToolSpinBox` / `ToolCheckBox`
components (see `docs/TOOL_THEMING.md` and the project `CLAUDE.md`). Those
are cheap, they inherit theming for free, and they are what makes the tool
look like the rest of TRANS. A designer panel is perhaps 250 lines of QML
against 2 096 lines of Python it drives.

**Rule of thumb for the port:** if it draws data, it stays Python behind a
`FigureCanvasItem`. If it is a knob, it becomes QML.

---

## 3. Where things land

```
src/physics/                     NEW — the calculator's core/, in English
    analytical.py                closed-form levels
    quantum_dot.py               0D models, shells, addition energies
    laplacian.py  eigensolver.py  potentials.py  features.py
    tunneling.py
    solution_spec.py             geometry interchange
    designer.py                  the inverse search (from gui/tab_inverse.py)
    pairing.py                   electron–hole pairing, band edges
    line_scan.py                 per-spectrum mapping, grouping
    branches.py                  dI/dV branch splitting (from didv_import.py)

src/widgets/qml_figure_canvas.py NEW — the matplotlib host
src/backend/tool_implementations.py   + 3 methods (see §4)
src/qml/tools/ConfinementDesignerTool.qml   NEW
src/qml/tools/LineScanDesignerTool.qml      NEW
src/qml/tools/QuantumWellSolverTool.qml     NEW (phase 3)
tests/test_physics/…             the ported tests
```

**The search itself must leave the GUI class.** `gui/tab_inverse.py` is 2 096
lines, of which roughly 1 100 are the search (`_find_solutions`, `_objective`,
`_match_and_score`, `_primary_alias`, the sorting keys). Those move to
`src/physics/designer.py` as a plain class with no widgets. This is not
optional tidying: without it the search cannot run on the worker thread, and
it cannot be tested without Tk. It is also the bulk of the port's real work.

---

## 4. The five integration surfaces

Adding a tool to TRANS touches exactly these, in this order:

1. **Menu + tool map** — a `MenuItem` in `src/qml/main/Main.qml` (~line 515,
   gated by `currentTabIndex`) and an entry in the `toolMap` dictionary
   (~line 1700) pointing at the QML file.
2. **Backend method** — a method on `ToolImplementations` taking
   `(self, task, dataset_name, params)` and returning a path or a dict, plus
   an `AppBackend` `@Slot` that submits it via `worker_manager.submit(...)`
   with `on_finished=lambda r: self._on_tool_completed("<Name>", …)`.
   Hand `_on_tool_completed` a **path string**, never a dict — a dict on a
   `Signal(str)` arrives as `""` (recorded in `peak-finder-dataset`).
3. **`BATCH_TOOLS`** — one `BatchToolSpec` entry in
   `src/backend/batch_tools.py` and a `DatasetMultiSelect` in the QML, and
   the tool runs over many datasets with no new slot.
4. **Workflow node** — an entry in `src/backend/workflow_engine.py`
   (`display_name`, `category`, `inputs`, `outputs`, `parameters`) plus the
   dispatch branch in `workflow_manager.py`. Model it on `SpectralFeatures`,
   which is the closest analogue: one dataset in, one flat table out.
5. **Exports** — any field written to disk goes through
   `src.utils.field_export.export_field()`. This is a hard rule in the
   project `CLAUDE.md`: the confinement-vs-position map is a 1×N field with a
   real position step, so it must carry metres, not pixels.

---

## 5. Simple tools, composite tools, and the workflow in between

The designer is not one operation, it is a chain: find peaks → split the
branches → search geometries per carrier → pair them → reduce aliases →
group → assemble a map. TRANS already has several tools shaped like that,
and they are currently indistinguishable from one-operation tools in the
menu. That is the thing to fix while adding two more of them.

### 5.1 The taxonomy

- **Simple tool** — one operation, no internal branching. Its backend method
  maps 1:1 onto a workflow node. *Smoothing, Derivative, Integration,
  Truncate, Cosmic Ray Filter, FFT, Gradient, Map filters.*
- **Composite tool** — several operations in one pass, with decisions
  between them. *Map Generator, Confinement Analysis, Spectral Features,
  Multi-Peak Fitting, Detect Bandgap & Doping, Dirac Point Estimator,* and
  the two designer tools this plan adds.
- **Saved workflow** — a user-built chain, saved as `.flow`, re-runnable.
  Functionally a composite tool that nobody had to write code for.

**The governing principle: every composite tool should be expressible as a
workflow of simple nodes.** Where it is not, that is a missing node — and
the missing node is almost always the genuinely reusable piece hiding inside
the composite (§5.4). This gives a decomposition target that is testable
rather than aesthetic: *can the user rebuild this tool from the palette?*

### 5.2 The division in the palette

Two places show tools, and both need the split:

**Tools menu (`Main.qml`).** Three labelled groups separated by
`MenuSeparator` (already used elsewhere in these menus):

```
Tools
    1D FFT, Curve Smoothing, Derivative, Integration, …
─────────────────────────
Composite tools
    Map Generator, Confinement Analysis, Spectral Features,
    Confinement Designer, Line Scan Designer, …
─────────────────────────
Saved workflows
    (from workflowManager.getSavedWorkflows(), one entry each)
```

The header rows are disabled `MenuItem`s styled like the existing delegate,
not new menus: keeping one flat list preserves the `currentTabIndex` gating
that already hides tools that do not apply to the active tab.

**Workflow node palette (`WorkflowToolPalette.qml`).** It already sections a
`ListView` by `category` via `workflowManager.getToolCategories()`. Do **not**
move composite nodes into a "Composite" category — the category is about
domain (Analysis, Processing, Image Processing) and compositeness is
orthogonal to it. Instead add `"composite": True` to the node definition in
`workflow_engine.py`, surface it through `getToolCategories()`, and let the
palette draw a small badge on those entries. One flag, both consumers.

### 5.3 The lifecycle: prototype, save, promote

The intended path, and the reason the decomposition matters:

1. **Prototype** a new analysis by wiring simple nodes in the workflow
   editor. No code.
2. **Save** it as `.flow`. It appears under *Saved workflows* and runs over
   any dataset — `WorkflowExecutor` already runs a whole graph once per
   dataset, and `getSavedWorkflows()` already lists them.
3. **Promote** to a coded composite tool only when one of these is true:
   - it needs a **preview** — a plot that responds while you turn a knob
     (Confinement Analysis and the designer both live or die by this);
   - it needs **one pass over the data**. A workflow materialises an
     intermediate dataset per node; Confinement Analysis subtracts the
     background and finds the peaks in a single pass per spectrum. On a
     hyperspectral run that difference is not cosmetic;
   - it needs **decisions between steps** that no edge can express — the
     designer's alias reduction and the fixed-point boundary refinement are
     loops, not a DAG;
   - it is used often enough that wiring it each time is friction.

Anything else stays a saved workflow. That is the point of building the
missing nodes: to make "stays a saved workflow" a real option.

**Minimum viable *Saved workflows* entry (v1):** clicking one opens a small
runner window with a `DatasetMultiSelect` and a Run button; the workflow runs
with the parameters it was saved with. **Exposed parameters** — letting a
saved workflow declare which node knobs surface in its runner — is a real
feature but a separate one; do not let it block v1.

### 5.4 What is missing to decompose today's composites

Chains below use existing node names; **bold** marks a node that does not
exist yet.

| Composite tool | Chain | Gap |
|---|---|---|
| **Confinement Analysis** | **BaselineEstimate** → CurveSmoothing → PeakFinder → **EnergyBinning** → **OccupancyMatrix** | 3 |
| **Map Generator** | **BaselineEstimate** → PeakFinder → **EnergyBinning** → Integration → **MapAssembly** | 3 (2 shared) |
| **Spectral Features** | **Normalize** → **GapFeatures** → CurveFitting(`coefficients`) → PeakFinder(windowed) → **TableMerge** | 3 |
| **Multi-Peak Fitting** | PeakFinder → **MultiPeakFit** | 1 |
| **Line Scan Designer** (new) | PeakFinder → **BranchSplit** → **InverseDesign** ×2 → **CarrierPairing** → **Grouping** → **TableMerge** → **MapAssembly** | 5 new + 2 shared |

Which collapses to **nine missing nodes**, ranked by how much they unlock:

1. **`MapAssembly`** — per-spectrum scalars + spatial layout → map. Wanted by
   the Map Generator *and* the line-scan designer, and it is the generic
   answer to "I have one number per spectrum, show me where". Highest value
   of anything in this list.
2. **`BaselineEstimate`** — the whole `estimate_baseline` family (arpls, als,
   snip, rubberband, endpoint, poly-iter) with `baseline` **and** `corrected`
   outputs. Today no workflow can do arPLS at all: the `CurveFitting` node
   ("Baseline") is polynomial-only, and `BackgroundSubtraction` subtracts a
   *reference dataset*, which is a different operation entirely.
3. **`EnergyBinning`** — peaks → occupied-bin intervals at the coarser of
   k_B·T/2 and the sweep step, with `min_spectra_per_bin`. Note this is
   **not** `PeakFinder.intervals`, which are FWHM-based; the difference is
   deliberate and documented in `CLAUDE.md`, so the node has to expose the
   rule rather than reuse the existing port.
4. **`Grouping`** — 1-D gap clustering (sort, split where neighbours differ
   by more than a tolerance). Used by the designer for confinement sizes and
   by anything that needs "which of these values are the same value".
5. **`TableMerge`** — join per-spectrum columns into one flat table. The
   plumbing every feature-extraction chain ends with.
6. **`OccupancyMatrix`** — peaks (+ optional bin edges) → the 1/0 table.
7. **`Normalize`** — per-spectrum max / band-edge / area / none.
8. **`InverseDesign`** — target energies + mass list → candidate geometries.
   The designer's core; also the one node that is worth having even if the
   full tool is never used from a workflow.
9. **`BranchSplit`**, **`CarrierPairing`**, **`GapFeatures`**,
   **`MultiPeakFit`** — narrower, build with their parent tool.

Sequencing note: 1–3 are worth building **before** the designer tools,
because the designer needs `MapAssembly` anyway and the other two make the
two existing composites decomposable at the same time. That is one week that
pays into three tools instead of one.

---

## 6. What integration actually buys

The calculator currently reads CSVs and draws its own map. Inside TRANS,
none of that is necessary — and the results become data the rest of the app
already knows how to handle:

- **Input**: a `DatasetComboBox` over `SpectralData` instead of
  `filedialog`. Line scans are already first-class here — `spatial_layout`,
  `position_m`, `position_step_m` — so the position axis comes in metres
  from the loader instead of a typed-in step (see `hyperspectral-line-scan`).
- **Peak finding**: import `src.processing.peak_detection` directly with
  `CONFINEMENT_DEFAULTS`. Same engine the Confinement Analysis tool uses, so
  both tools agree by construction rather than by a copied dictionary.
- **Output**: a derived `SpectralData` flat table (§10.4) that the Map
  Generator can map, the Hyperspectral tab can open, and the project file
  keeps — all for free.
- **Batch**: `runToolOnDatasets` runs the designer over every line scan in a
  session in one go, with `_suppress_auto_open` already handling the "don't
  open 40 windows" problem.

That last point is why this is worth doing rather than keeping the two apps
side by side: the designer stops being a destination and becomes a step.

---

## 7. Threading and cancellation

Measured on the current code: **~250 ms per spectrum** at 1 candidate/point,
**~1.1 s** at 3 (the default). A 1 000-point line scan is 4–18 minutes.

- The line-scan run **must** go through `worker_manager.submit`. Never on the
  GUI thread — TRANS already has the pattern, and `large-dataset-performance`
  records what happens when long work blocks it.
- `analyze_line_scan` already takes a `progress(i, total) -> bool` callback
  that stops the run when it returns False. Wire it to the task's
  `cancelled` flag, exactly as `extract_spectral_features` does with
  `should_cancel`.
- Progress goes out as `self.status = …` / the existing progress signal, not
  as `txt.update()`.
- Never `QThread.terminate()` a running search — see `shutdown-crash-on-save`.

---

## 8. Translation

The move is the only cheap moment to do this, because nothing in a `.hrt`
project references these names yet. Once a designer result is saved into a
project file, the strings become a compatibility surface.

**Locked (§10.3): keys and labels are separate.** Every enumerated value
becomes an English `snake_case` key; the human-readable string lives in one
`LABELS` dict per module and is the only thing the UI reads. Splitting them
is worth doing on its own merits — it is also what makes a future
translation possible without touching logic.

```python
# src/physics/designer.py
MATCH_ABSOLUTE = "absolute"          # keys: snake_case, stable, persisted
MATCH_GAPS     = "delta_e"
MATCH_RATIOS   = "delta_e_ratios"

MATCH_LABELS = {                     # labels: display only, never compared
    MATCH_ABSOLUTE: "Absolute energies",
    MATCH_GAPS:     "Differences (ΔE)",
    MATCH_RATIOS:   "ΔE ratios",
}
```

The values that must be converted this way, because they are compared with
`==` or used as dict keys today: `coords` (`"Circular"`, `"Cilíndrico"`,
`"Esférico"`, `"Disco / lente"`, `"Parabólico"`), `sym` (`"Cúbico"`,
`"Tetragonal"`, `"Ortorrômbico"`, `"Quadrado"`, `"Retangular"`), the three
`MATCH_*` constants, the `_DOT_MODELS` map, the sort modes, the carrier
modes, and the `line_scan` reason codes (`"sem picos"` → `no_peaks`, …).

Docstrings and comments carry the reasoning this codebase is written around
("ΔE matching is not a convenience", the k_B·T/2 binning, why 3σ and not 2σ).
Translate them properly; do not drop them. They are why the code can be
re-read a year later.

Glossary to fix up front and use consistently:

| pt | en |
|---|---|
| poço | well |
| ponto quântico | quantum dot |
| alvo / energias-alvo | target / target energies |
| candidata | candidate |
| casamento (por ΔE) | matching (by ΔE) |
| deslocamento (de origem) | offset |
| borda de banda | band edge |
| fronteira (entre ramos) | branch boundary |
| confinamento | confinement |
| varredura de linha | line scan |
| massa efetiva | effective mass |
| escada (de níveis) | ladder |
| par / emparelhamento | pair / pairing |
| sem confinamento | no confinement |

---

## 9. Phases

Each phase leaves the repository working and tested. Nothing is deleted from
the Tk app until phase 6.

### Phase 0 — the physics package (no UI) ✅ **done**
Move `core/` → `src/physics/`, translated with keys split from labels, with
`trans_bridge` deleted and `peak_detection` imported directly. Extract the
search from `gui/tab_inverse.py` into `src/physics/designer.py`. Port the
tests that do not need Tk (~150 of 209).
*Done when:* `pytest tests/test_physics` is green and nothing in `src/`
imports tkinter. No user-visible change.

Landed as 13 modules / ~3 600 lines under `src/physics/`, with 173 tests.
Four things worth recording:

- **`CONFINEMENT_DEFAULTS` moved down** into
  `src/processing/peak_detection.py`, the engine it was measured against, and
  is re-exported from `tool_implementations` where callers have always found
  it. It had to: the physics package cannot import the Qt backend, and
  copying the dict is exactly what `trans_bridge` did and what made the two
  able to drift.
- **The boundary refinement came across too.** `on_refine_edges` was a
  fixed-point loop buried in the tab; it is now
  `pairing.refine_boundaries(peaks, run_search, …)` with the search injected,
  the same shape `line_scan.analyze_line_scan` already used. `current_edges`
  became `pairing.edges_from_solutions`.
- **The dot models and the 0D coordinate systems are now the same keys**
  (`spherical` / `disc` / `parabolic`), so the lookup table that used to map
  a Portuguese combo label to a model name is gone rather than translated.
- **The search is seedable.** `Designer(seed=…)` pins the global
  optimisation, which is what makes a candidate-level test possible at all;
  unseeded it behaves exactly as before.

What did NOT come across, because it belongs to the tool rather than the
physics: filling the entry fields from an imported curve (`_apply_didv`), the
Find button's orchestration of both carriers, and the plotting. Those are
phase 2/3 work and their tests were dropped rather than rewritten against a
UI that does not exist yet.

### Phase 1 — the three shared nodes ✅ **done**
`MapAssembly`, `BaselineEstimate`, `EnergyBinning` (§5.4), plus
`OccupancyMatrix`, which the Confinement Analysis chain needs at its end.
Each is a workflow node plus a `ToolImplementations` method, and each makes
an existing composite decomposable on the way past.
*Done when:* a hand-wired workflow reproduces Confinement Analysis's peak
matrix, and another reproduces a Map Generator interval map.

Both are executed as tests in
`tests/test_backend/test_composite_decomposition.py`: a real `Workflow` run
through `WorkflowExecutor`, compared against the composite it decomposes.
Two things that came out of writing them and are worth keeping in mind for
the phases below:

- **Equality is claimed from the composite's own peaks.** The `PeakFinder`
  node is scipy's prominence search, not the confinement engine, so a chain
  that goes through it finds its own peaks and cannot be identical by
  construction. The nodes rebuild the *tables* exactly; the search is the
  part still only the composite has. A `PeakSearch` node on the confinement
  engine would close that gap — a tenth missing node, not yet in §5.4's list.
- **A port carries whatever the node upstream had.** `Integration` passes
  hand-typed intervals through as `{'lower': …, 'upper': …}` dicts, which
  crashed `assemble_maps`; every method that takes intervals from a port now
  goes through `_clean_intervals`. Worth checking on each new node.

### Phase 2 — `FigureCanvasItem` + the single-spectrum designer
Build the matplotlib host, then the **Confinement Designer** tool: dataset
combo, spectrum index, carrier mode, mass list, tolerance, matching mode →
candidate list + the two existing plots.
*Done when:* a candidate found in TRANS matches one found in the Tk app for
the same spectrum. This phase proves the embedding pattern; if it is wrong,
it is wrong here, cheaply.

### Phase 3 — the line-scan designer
The tool of real value. Dataset in → per-position search on the worker →
flat-table dataset out (§10.4) → colour-strip map in a `FigureCanvasItem`.
Add the `BATCH_TOOLS` entry, the workflow node, and `export_field` for the
map.
*Done when:* a MATRIX line scan produces a confinement table in the project
browser that the Map Generator can map and the Hyperspectral tab can open.

### Phase 4 — palette division and saved workflows
The three-group Tools menu, the `composite` flag and its badge in the node
palette, and the v1 *Saved workflows* runner (§5.2, §5.3).
*Done when:* a `.flow` saved from the editor runs from the Tools menu over a
multi-dataset selection.

### Phase 5 — the direct solvers
"Quantum Well Solver" (1D) and "Quantum Dot Solver" (0D) as composite tools.
These are `tab_1d.py` (595 lines) and `tab_quantum_dot.py` (482) — modest UI,
and the `accept_solution` bridge already exists, so a candidate from the
designer can be simulated numerically inside TRANS exactly as it is today.
*Done when:* "Simulate in ▸" works across two TRANS tool windows.

### Phase 6 — the 2D/3D feature editors *(decide later)*
`tab_2d_features.py` (1 045), `tab_multi_well_3d.py` (1 264) and
`interactive_canvas.py` (879) — the interactive potential editor with
draggable features. This is the expensive third of the port and the least
connected to STS data. Recommendation: **defer, and revisit only if the
2D/3D solvers turn out to be used on real data.** If they come, they belong
in a third tab ("Modeling") next to Spectral and Hyperspectral, not in a
tool window — they are a workstation, like the Map Editor.

### Phase 7 — retirement
Delete the Tk app once phases 0–5 are in use, or archive it under
`archive/` (already gitignored).

---

## 10. Decisions — locked 2026-08-22

1. **Package name** — `src/physics/`.
2. **Tool or tab** — **tool windows**, following the Confinement Analysis and
   Map Generator design ethos (`ToolSection` / `ToolComboBox` / `ToolSpinBox`
   / `ToolCheckBox` through `ToolTheme`; a live preview panel driven by the
   same engine that does the full run). They are *composite* tools and the
   palette says so (§5). The 2D/3D editors, if phase 6 happens, are a tab.
3. **Naming** — English `snake_case` keys, split from display labels (§8).
4. **Line-scan output shape** — a **flat table**, one row per position:

   | column | type | notes |
   |---|---|---|
   | `position_m` | float | metres, from the source's spatial metadata |
   | `point_index` | int | position along the line |
   | `size_nm` | float | confinement size, **NaN where none** |
   | `rrmse_pct` | float | fit error, NaN where none |
   | `group` | **int** | group id, **numeric so it can be plotted/mapped**; NaN where none |
   | `meff` | float | the mass that produced this geometry |
   | `n_peaks` | int | peaks found at this position |
   | `dim_1_nm`, `dim_2_nm`, … | float | the geometry itself |
   | `hole_size_nm`, `mismatch_nm` | float | paired mode only |
   | `reason` | str | why there is no confinement; empty when there is one |

   Flat because the Map Generator consumes flat data, so every one of those
   columns is immediately a map. `group` is an integer column and not a
   label for the same reason: a categorical string cannot be mapped or
   plotted, an integer can.

5. **"No confinement"** — `NaN` in every numeric column, **never 0**. A zero
   would map as a very small well and read as a real measurement. NaN writes
   as an **empty cell** in CSV, is skipped by plots, and is masked by the
   colour strip. The `reason` column carries what happened; it is the only
   place a string appears.

Two smaller ones follow from the above and are recorded here so they are not
re-litigated: the `composite` flag lives in the node definition rather than
in a new category (§5.2), and exposed parameters for saved workflows are
explicitly **out of scope for v1** (§5.3).

---

## 11. What not to port

- `gui/app_shell.py` — TRANS has `WindowManager`.
- `gui/plotting.py: embed_figure` — replaced by `FigureCanvasItem`.
- `core/trans_bridge.py` — an import, once inside.
- The CSV reader in `core/didv_import.py` — datasets come from loaders.
  Keep only the branch-splitting logic (`split_peaks`, the boundary
  arithmetic, `band_edges`), which is physics.
- `core/debug_log.py` — TRANS uses `logging.getLogger(__name__)` throughout;
  the `--debug` file handler is a launcher concern here.

---

## 12. Effort, honestly

| Phase | Scope | Estimate |
|---|---|---|
| 0 | physics package + designer extraction + tests | ~~2–3 days~~ **done** |
| 1 | `MapAssembly`, `BaselineEstimate`, `EnergyBinning` | ~~3–4 days~~ **done** |
| 2 | `FigureCanvasItem` + single-spectrum tool | 2 days |
| 3 | line-scan tool, worker, dataset output, workflow | 3–4 days |
| 4 | palette division + saved-workflow runner | 2 days |
| 5 | 1D and 0D solver tools | 3 days |
| 6 | 2D/3D editors *(deferred)* | 1–2 weeks |

Phases 0–3 are the ones that pay: they put the designer where the data is,
and phase 1 pays into two existing tools on the way. Phase 4 is what makes
the composite/simple distinction real to the user. Phase 5 is comfort.
Phase 6 is a project of its own and should be justified by use, not by
completeness.
