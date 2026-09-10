# Derivative Calculator

Numerical derivative of each spectrum — dI/dV from an I(V) sweep, or
d²I/dV². Accepts a **multi-dataset selection** and processes them one after
another.

**Menu** Tools → Derivative Calculator · **Panel** `DerivativeTool.qml` ·
**Method** `calculate_derivative()` · **Batch key** `derivative`

## Input

Any spectral dataset; typically raw I(V). Drag datasets from the project
browser onto the window, or Ctrl/Cmd-click in the list.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `order` | 1 | 1 = dI/dV, 2 = d²I/dV² |
| `smooth_before` | true | smooth before differentiating |
| `smooth_after` | true | smooth the result |

## Output

| output | where |
|---|---|
| `<dataset>_1st_Derivative` (or `2nd`) | browser, one per input dataset |
| `<name>_1st_Derivative.csv` | `<project>_outputs/derivatives/` |

## Method

Central differences on the shared axis. Both smoothing passes are on by
default because differentiation multiplies high-frequency noise by the
frequency — a clean-looking I(V) routinely gives an unusable raw derivative.

The pipeline is **smooth → gradient → smooth**, which is about `0.55 × window`
wide overall. That figure is recorded in the result's metadata as the
differentiation window, so tools that need the energy resolution (Confinement
Dimensionality, the edge analysis) can read it instead of asking you to
remember.

## Notes

- Spatial metadata is carried across: a derivative of a line scan is still
  that line scan's spectra, so its maps still come out in nanometres.
- With several inputs selected, results are registered but not opened — one
  graph window per dataset would bury the workspace.
