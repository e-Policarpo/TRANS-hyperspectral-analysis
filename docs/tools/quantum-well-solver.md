# Quantum Well Solver

Solves a 1D quantum well directly: give it a box and a mass, get the levels
and the wavefunctions.

**Menu** Tools → Composite tools → Quantum Well Solver · **Panel**
`QuantumWellSolverTool.qml` · **Method** `solveQuantumWell()`,
`solve_well_1d()` in `src/physics/solvers.py`

## Input

Numbers, not a dataset. Optionally a `SolutionSpec` handed over from the
[Confinement Designer](confinement-designer.md) — "Simulate" runs a candidate
through this solver.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `label` | — | name for the result |
| `meff` | — | effective mass, in units of the free electron mass |
| `n_states` | — | how many levels to solve for |
| `bc` | — | boundary condition |
| `dirichlet` / `neumann` | — | the two available conditions: ψ = 0 at the wall, or dψ/dx = 0 |
| `energy` | — | well depth / energy scale |
| `targets` | — | measured levels to compare against |

## Output

The level ladder, the wavefunctions, and — when `targets` are given — the
comparison against them (`compare_with_targets`).

## Method

Finite-difference Hamiltonian on a 1D grid (`lap1d` from
`src/physics/laplacian.py`), solved with `scipy.sparse.linalg.eigsh`.

The boundary condition is a physical choice, not a numerical detail:
**Dirichlet** (ψ = 0 at the wall) is an infinite barrier; **Neumann**
(dψ/dx = 0) is a reflecting one. They give different ladders, and which is
right depends on what the well is made of.

## Notes

- `states_needed()` works out how many eigenvalues to ask for so the ones you
  want are converged — asking for exactly *n* tends to give a poor last one.
- For a closed-form answer where one exists, `src/physics/analytical.py` has
  `box_energies_1d` and friends; the numerical solver exists for the cases
  that have no closed form.
