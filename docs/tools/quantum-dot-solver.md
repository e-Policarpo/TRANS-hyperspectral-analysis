# Quantum Dot Solver

Solves a 0D quantum dot: levels, shells and addition energies.

**Menu** Tools → Composite tools → Quantum Dot Solver · **Panel**
`QuantumDotSolverTool.qml` · **Method** `solveQuantumDot()`, `solve_dot()`
and `src/physics/quantum_dot.py`

## Input

Numbers, or a `SolutionSpec` from the [Confinement
Designer](confinement-designer.md).

## Parameters

| parameter | default | meaning |
|---|---|---|
| `label` | — | name for the result |
| `model` | — | `spherical_dot`, `disc_dot` or `parabolic_dot` |
| `meff` | — | effective mass |
| `energy` | — | confinement energy scale |
| `n_per_channel` | — | states per channel |
| `channels` | — | which channels to include |
| `state_index` | — | which state to inspect |
| `holds` | — | occupancy |
| `targets` | — | measured levels to compare against |

## Output

The level spectrum with orbital labels, the shell table, and addition
energies.

## Method

Three models, because "quantum dot" is three different problems:

- **spherical** — a hard-walled sphere; levels are Bessel zeros.
- **disc** — a 2D disc, for a dot much wider than it is tall.
- **parabolic** — a harmonic confinement, the Fock–Darwin picture, which is
  what a gate-defined dot usually is.

`shell_table` fills the levels in order and `addition_energies` gives the
energy to add each successive electron — the quantity a Coulomb-blockade
measurement actually reports.

`hw_from_length` / `length_from_hw` convert between a confinement energy ħω
and a physical size, which is the translation you need to compare a solved dot
with a measured one.

## Notes

- `orbital_label` names states in the usual spectroscopic way, so the output
  can be read against a shell picture directly.
- Degeneracy matters: a level that looks single in the ladder may hold several
  states, and the addition energies are what expose that.
