# Spatial Average — sunset

Folded into the [Map Generator](map-generator.md) in the tool rework as its
**Spatial averaging** step: block width × height, applied before the
background and the integration, laid out along the scan path the *Scan
type* combo names so a meander is not scrambled. The averaged spectra are
still registered as `<name> - Spatially Averaged (AxB)`, so what was mapped
stays inspectable.

The engine (`_do_spatial_average()`, `src/models/discretizer.py`) is
unchanged and still drives the **Spatial Average workflow node**.

Use: Tools → Maps → Map Generator → *Spatial averaging*.
