# Confinement Designer

The inverse problem: given the levels you measured, search for a geometry
whose eigenstates match.

**Menu** Tools → Composite tools → Confinement Designer · **Panel**
`ConfinementDesignerTool.qml` · **Method** `runConfinementDesigner()`,
engine in `src/physics/designer.py`

## Input

Either a spectrum — whose peaks are found by the same engine as
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

## Output

A ranked list of candidate geometries with their predicted level ladders and
the error against your targets. `describeCandidate()` renders one in full, and
a candidate can be handed straight to the [Quantum Well](quantum-well-solver.md)
or [Quantum Dot](quantum-dot-solver.md) solver via `SolutionSpec`.

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
