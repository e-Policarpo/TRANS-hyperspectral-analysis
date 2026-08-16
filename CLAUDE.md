# TRANS — project conventions

## Exports MUST carry real physical quantities

**Rule: any feature that writes measurement data to disk encodes the real
physical dimensions and units whenever they are available.** A file described
as "666 × 666 pixels" is not an acceptable export — it must say 2.5 × 2.5 µm,
and the values must be the true physical ones (metres, amps, volts), not a
0–255 or 0–65535 normalisation.

This applies to every new export feature by default. Do not add a new
`tifffile.imwrite` / `PIL.Image.save` call for measurement data.

### How

Call **`src.utils.field_export.export_field()`** (or
`export_field_from_metadata()` when you hold a loader metadata dict). It is the
single enforced entry point and writes both formats below. If the scale is
genuinely unknown it still writes the file but logs a warning naming the call
site, so gaps surface instead of being silent.

| Layer | Module | Purpose |
|---|---|---|
| Policy | `src/utils/field_export.py` | `export_field()` — **use this** |
| Gwyddion, multi-channel | `src/utils/gwy_io.py` | `.gwy` — all channels in one file |
| Gwyddion, single field | `src/utils/gsf_io.py` | `.gsf` writer/reader |
| ImageJ/Fiji | `src/utils/tiff_io.py` | calibrated `.tiff` + `read_tiff_calibration()` |
| Conversion | `src/utils/units.py` | `to_nm`, `pixel_size_to_nm`, `scale_from_metadata` |

### Imported scan images → `.gwy`

Importing measurement data writes **one `.gwy` per scan, holding every channel**
(`AppBackend._save_image_to_gwy`), because Gwyddion is where this data is
analysed. It is gated on the import dialog's *"Extract images as .gwy"*
checkbox — **on by default**; when cleared, an import writes no image files at
all. `Export as .gwy…` in the project browser does the same on demand for any
image. Requires the pure-Python `gwyfile` package; `gwy_io.gwy_available()`
lets callers degrade instead of failing.

GSF is single-field by spec, so it cannot hold a multi-channel scan in one
file — that is why `.gwy` is the import format and `.gsf` the per-field one.

### Why several formats

**Gwyddion ignores TIFF resolution tags.** For generic image formats its pixmap
importer asks the user to type the dimensions in, and the values it pre-fills
are just the last ones used — nothing is read from the file. So a TIFF, however
carefully tagged, always lands in Gwyddion as bare pixels. `.gsf` (Gwyddion
Simple Field) carries `XReal`/`YReal`/`XYUnits`/`ZUnits` explicitly and is the
only format that opens correctly scaled there.

The `.tiff` is still written: Fiji/ImageJ *do* read its resolution tags, it
round-trips back into this app via `ImageData.from_file`, and it carries an
ImageJ display range so float data doesn't render all-black.

Reference: <https://gwyddion.net/documentation/user-guide-en/gsf.html>

### Don't

- Don't normalise data before writing a data export. Normalise only for a
  PNG/JPEG *preview* that sits alongside the real file.
- Don't invent a scale you don't have — leave it unset so the warning fires.
- Don't assume the lateral unit is µm; route through `src/utils/units.py`,
  which handles m/mm/µm/nm/Å/pm and returns `None` for non-length units.

## Other conventions

- QML properties use `Property()` (not `@Slot(result=...)`) so bindings update.
- Embedded windows go through signals (`openDatasetEmbedded`, …) — never OS
  windows.
- Dataset/spectrum indices are zero-padded via `src/utils/naming.py` so
  alphabetical order matches acquisition order.
- Imports are auto-filed into `<Type>/<session>` browser folders; the session
  label is derived in `AppBackend._group_label`, so new loaders inherit it.
