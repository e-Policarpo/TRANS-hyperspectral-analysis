# Map Discretizer

Reduces a map's spatial resolution by averaging blocks of pixels.

**Menu** Tools → Map Discretizer · **Panel** `MapDiscretizerTool.qml` ·
**Method** `discretize_map()`

## Input

A map or image entity.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `target_x` | — | output width in pixels |
| `target_y` | — | output height |

## Output

A reduced map under `<project>_outputs/discretized/`, and it can be opened
straight into the map editor.

## Method

The source is tiled into blocks sized so the result comes out at
`target_x × target_y`, and each block is averaged.

The **physical extent is unchanged** — the map still covers the same area, so
the pixel size grows and the export stays correctly calibrated. That is the
difference between this and cropping.

## Notes

- Averaging blocks improves signal-to-noise by √(pixels per block).
- Useful for matching a scan image's grid to a spectral map's coarser grid so
  the two can be compared point for point.
