# Spectral Axis Converter

Converts the independent axis between spectroscopic units.

**Menu** Tools → Spectral Axis Converter · **Panel**
`SpectralAxisConvertTool.qml` · **Method** `convertDatasetAxis()`,
`src/backend/spectral_axis.py`

## Input

A dataset whose axis is a wavelength, energy or wavenumber — PL and Raman
data. The current unit is read from `metadata.units['independent']`.

## Parameters

| parameter | default | meaning |
|---|---|---|
| `target_unit` | — | `nm`, `eV`, `cm-1`, … see `AxisUnit` |
| `excitation_nm` | 0.0 | laser wavelength; **required** for a Raman shift, which is relative to it |
| `new_dataset_name` | derived | name for the result |

## Output

A new dataset with the converted axis, its column renamed to match the unit,
and `units['independent']` updated.

## Method

`parse_unit` normalises the unit string, then `convert_axis` applies the
conversion. nm ↔ eV is the reciprocal relation (`E = 1239.84 / λ`), so the
axis is **reversed** and no longer evenly spaced — which is correct, and worth
knowing before you feed it to something that assumes a uniform grid.

A Raman shift in cm⁻¹ is measured from the excitation line, so
`excitation_nm` must be right or the whole axis is offset.

## Notes

- The conversion is applied to the axis only. Intensities are not rescaled by
  the Jacobian, so peak *areas* are not preserved across a nm ↔ eV conversion.
