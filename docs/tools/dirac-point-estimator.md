# Dirac Point Estimator

Finds the Dirac point of a graphene-like spectrum by intersecting the two
linear branches either side of it.

**Menu** Tools → Composite tools → Dirac Point Estimator · **Panel**
`DiracPointEstimatorTool.qml` · **Method** `estimate_dirac_point()`,
`fit_dirac_point()` / `auto_detect_dirac_ranges()` in
`src/backend/sts_algorithms.py`

## Input

dI/dV spectra with a V-shaped conductance minimum.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `auto_detect` | false | choose the two fit ranges automatically |
| `left_min` / `left_max` | — | bias window for the left branch |
| `right_min` / `right_max` | — | bias window for the right branch |
| `smoothing` | — | smoothing strength |
| `smoothing_method` | `Savgol` | `Savgol`, `Moving Avg`, `None` |

## Output

| output | contents |
|---|---|
| `<dataset> - Dirac Point` | per spectrum: the Dirac voltage and conductance, both slopes, both R², both intercepts |
| files | `<project>_outputs/curves/` |

## Method

Fit a straight line to each branch and intersect them. The intersection is
the Dirac point; the slopes come out as a by-product and are what tell you
whether the fit meant anything.

With `auto_detect`, `auto_detect_dirac_ranges` picks the windows from the
curve itself, using `bandgap_delta` to stay clear of the flat minimum where a
linear fit is meaningless.

**Parallel branches have no intersection.** That case is detected and returns
`NaN` rather than a number produced by dividing by a near-zero slope
difference.

## Notes

- **Read the two R² values.** They are in the output because the Dirac point
  is only as trustworthy as the linearity of the branches, and a confident
  number from two badly fitted lines is the failure mode here.
- The fit windows matter more than the smoothing. Include the curved region
  near the minimum and the intersection is pulled off systematically.
