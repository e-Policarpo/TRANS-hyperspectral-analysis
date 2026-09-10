# Map Processing

Operations on map channels — levelling, arithmetic, channel manipulation.

**Menu** Tools → Map Processing · **Panel** `MapProcessingTool.qml` ·
**Method** `processMap()`

## Input

A map or image entity, named by path, with its type.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `input_path` | — | the map to operate on |
| `input_type` | — | which kind of entity it is |
| `operation` | — | the operation to apply |
| `params` | `{}` | operation-specific settings |

The operation set includes plane and polynomial levelling — see
`src/processing/plane_correction.py` (`polynomial_level`, `facet_level`,
`apply_leveling`).

## Output

A processed map registered in the browser and written under
`<project>_outputs/`.

## Method

Dispatches on `operation`. **Levelling** is the common one: a scan is almost
never perfectly flat relative to the scanner, so a plane or low-order
polynomial is fitted to the surface and subtracted. `facet_level` fits the
dominant facet instead, which is what you want when the surface has terraces
and a global plane would tilt them.

## Notes

- Levelling changes absolute heights but preserves relative ones. Step heights
  survive; an absolute z reference does not.
- The Z-plane levelling in the image viewer is a separate, in-place path with
  a raw-revert, for when you only want to *look* at the scan.
