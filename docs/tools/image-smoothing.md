# Image Smoothing

Smooths an image or map channel.

**Menu** Tools → Image Smoothing · **Panel** `ImageSmoothingTool.qml` ·
**Method** `smooth_image()`

## Input

An image entity or map channel — a scan image, not a spectral dataset.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `filter_type` | gaussian | `gaussian`, `median`, `mean` |
| `kernel_size` | 3 | kernel width in pixels |

## Output

A smoothed image written under `<project>_outputs/smoothed/`, registered as a
new image entity.

## Method

`scipy.ndimage` filters. **Gaussian** for general noise, **median** for
salt-and-pepper (single bad pixels) since it removes them without blurring
edges, **mean** as the plain box filter.

## Notes

- Smoothing a topography channel changes measured heights. Do it for display,
  and keep the raw channel for anything quantitative.
- Physical calibration is preserved, so the result still exports with real
  dimensions.
