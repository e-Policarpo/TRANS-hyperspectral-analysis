# Confinement Designer

The inverse problem: given the levels you measured in **one spectrum**,
search for a geometry whose eigenstates match, and rank every candidate for
inspection. To run the same search at every position of a line scan and see
how the size varies along it, use the [Line Scan
Designer](line-scan-designer.md).

**Menu** Tools → Confinement → Confinement Designer · **Panel**
`ConfinementDesignerTool.qml` · **Method** `design_confinement()`,
engine in `src/physics/designer.py` · **Batch key** `confinement_designer`

## Input

A multi-dataset selection — every dataset is searched in turn with the
same settings and writes its own tables (named after the dataset and the
search settings); the preview and the candidate list are the first
selection's. Per dataset, either a spectrum — whose peaks are found by the same engine as
[Confinement Analysis](confinement-analysis.md), previewed live by
`previewDesignerTargets` — or target energies typed by hand.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `ndim` | — | 1, 2 or 3 |
| `coords` | — | cartesian, polar, cylindrical, spherical |
| `sym` | — | symmetry constraint on the box |
| `dims` | — | which dimensions are free to vary |
| `size` | — | size range to search |
| `meff`, `meff_e`, `meff_h` | — | effective mass; separate electron and hole masses when paired |
| `carrier` | — | electron, hole, or both |
| `paired` | — | fit electron and hole ladders together |
| `split_e` / `split_h` | — | branch split for each carrier |
| `pair_tol_nm` | — | how closely the two carriers' sizes must agree |
| `match` | — | matching criterion |
| `tol` | — | tolerance on a match |
| `rrmse` | — | relative RMS error accepted |
| `maxsol` | — | how many candidates to return |
| `priority`, `sort` | — | how candidates are ranked |
| `baseline`, `height` | as Confinement Analysis | the peak search feeding the targets |
| `spectrum_index` | 0 | which spectrum to read targets from |
| `all_spectra` | false | search every spectrum in the dataset in turn instead of just that one |

## Output

A ranked list of candidate geometries with their predicted level ladders and
the error against your targets. `describeCandidate()` renders one in full, and
a candidate can be handed straight to the [Quantum Well](quantum-well-solver.md)
or [Quantum Dot](quantum-dot-solver.md) solver via `SolutionSpec`.

Every run also writes two tables — datasets in the project and CSVs under
`<project>_outputs/confinement/` — because a list that only exists on screen
cannot be read after the window closes:

| table | contents |
|---|---|
| `<dataset> - Designer Candidates` | **one row per candidate**: `d1_nm`/`d2_nm`/`d3_nm`, `size_nm`, `meff`, `offset_eV`, `rrmse_pct`, `rrmse_de_pct`, the geometry (`ndim`, `coords`, `sym`), the branch edges it was fitted under, and the paired hole (`hole_size_nm`, `pair_mismatch_nm`, `hole_qn_*`) where there is one. On a paired run a row **is** an electron–hole pair and `carrier` reads `e+h`. `qn_min` / `qn_max` are the quantum numbers the measured levels were assigned to and `levels_skipped` how many predicted levels between them were *not* measured — five peaks matched to n = 8, 15, 17, 18, 20 skip eight levels the model says should be there, a weak match however low its RRMSE (the matcher pairs each measured level with the nearest predicted one and does not require consecutive levels). `group` / `group_size_nm` gap-cluster the sizes found anywhere in the run (`group_tol_nm`, the Line Scan Designer's rule): rows in one group describe the same well, numbered from the smallest. Every spectrum is searched **on its own** — its own peaks, its own search, its own candidates; nothing is fitted across spectra, and the grouping is the only step that looks at the run as a whole. On an all-spectra sweep every spectrum that found nothing gets a placeholder row (`candidate = -1`, its `n_peaks`, the `reason`), so the table says which positions converged and which did not |
| `<dataset> - Designer Levels` | **one row per level of each candidate**: `measured_eV` against `simulated_eV` with `error_pct`, plus `measured_V`/`simulated_V` — the same two energies put back on the bias axis |

Both carry `spectrum_index` and `column`, so a sweep's rows say which spectrum
they came from, and both have a fixed column order so two runs concatenate.

### Measured against simulated, and the branch edges

The energies fitted are measured **from the branch edge**, not from E_F:
`split_e` cuts the electron branch and `split_h` the hole branch, so a peak at
bias *V* becomes `V - split_e` for an electron and `split_h - V` for a hole.
The level table gives both readings — `measured_eV` is what was fitted,
`measured_V = measured_eV + split_e` (electrons) or `split_h - measured_eV`
(holes) is where to find it again on the curve — and repeats `split_e_V` /
`split_h_V` on every row, so the table means the same thing on its own as it
does next to the panel that produced it.

### Searching every spectrum

`all_spectra` turns the tool from one question into a sweep: each spectrum is
searched in turn, the tables collect every candidate from all of them, and the
panel's list shows one spectrum's — the one selected, or the first that found
anything when the selected one found nothing. A spectrum with too few peaks on
a branch is an ordinary outcome and does not end the run. Cancel stops it
between spectra.

Budget the time: a candidate is a global optimisation, so a search is seconds
and an overview of 62 spectra is minutes.

## Method

The search sweeps geometry and size, solves each candidate analytically where
a closed form exists (`src/physics/analytical.py`) and numerically otherwise,
and scores the predicted ladder against the targets.

**Paired** mode fits an electron and a hole ladder at once and requires the
two to agree on a size within `pair_tol_nm` — a much stronger constraint than
either alone, because a wrong geometry rarely fits both carriers at the same
size.

Reproduces the reference Tk implementation's candidates to 1e-8 nm.

## Notes

- Targets are only as good as the peak search that produced them. Preview the
  spectrum and check the peaks before trusting a candidate.
- A candidate is a **hypothesis**, not a measurement: several geometries can
  fit the same few levels. More levels discriminate far better than tighter
  tolerances.
