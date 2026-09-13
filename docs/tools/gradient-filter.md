# Gradient Filter

Gradient magnitude of a map or image — makes steps, terraces and edges
visible that a height colour scale hides.

**Menu** Tools → Maps → Gradient Filter · **Panel** `GradientTool.qml` ·
**Method** `apply_gradient_filter()`, `_resolve_field_source()` ·
**Batch key** `gradient_filter`

## Input

Maps and images **from the project browser** — the panel lists every
registered map (file-backed or in-memory, active channel) and image entity,
and a browser drag of maps or images lands on it. Several can be selected
and are filtered one after another. (The panel no longer takes a file path;
the workflow node still accepts one.)

## Parameters

| parameter | default | meaning |
|---|---|---|
| `method` | `sobel` | `sobel`, `prewitt` or `scharr` |

## Output

A **calibrated** gradient map, `Gradient_<method>_<title>.tiff` (+ `.gsf`,
`.csv`) under `<project>_outputs/maps/`, registered under *Maps* and opened.
Its values are the gradient of the real field — the source's value unit per
lateral unit (`nm/nm`, `A/nm`, …), or per pixel when the source carries no
scale — never a 0–255 normalisation; the lateral scale is carried across
from the source.

## Method

The kernel pair is applied to the float field and the magnitude
`sqrt(gx² + gy²)` is divided by the kernel's weight sum, so the value is a
difference per pixel, then by the pixel size, so it is a slope per lateral
unit. A colour image is reduced to luminance first; a single-channel float
image is taken as it is.

## Notes

- This is a **derivative**: do not measure step heights on the result; go
  back to the raw channel for that.
- Gradient filters amplify noise, being derivatives. Smoothing first
  ([Map Processing](map-processing.md)) usually gives a cleaner picture.
