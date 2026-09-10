# Gradient Filter

Edge-detection filters on an image — makes steps and terraces visible that a
height colour scale hides.

**Menu** Tools → Gradient Filter · **Panel** `GradientTool.qml` ·
**Method** `apply_gradient_filter()`

## Input

An image entity or map channel.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `method` | `sobel` | the gradient operator |

## Output

A filtered image under `<project>_outputs/maps/`, registered as a new entity.

## Method

A gradient operator (Sobel by default) applied to the pixel array. The result
is a **derivative of height**, so its values are slopes, not heights — the
colour scale no longer means nanometres.

## Notes

- This is a **display transform**. Do not measure step heights on the result;
  go back to the raw channel for that.
- Gradient filters amplify noise, being derivatives. Smoothing first
  ([Image Smoothing](image-smoothing.md)) usually gives a cleaner picture.
