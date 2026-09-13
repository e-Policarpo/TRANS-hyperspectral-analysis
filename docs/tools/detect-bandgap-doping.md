# Detect Bandgap & Doping — sunset

Removed from the Tools menu in the tool rework: [Spectral
Features](spectral-features.md) had computed the same quantities since it
was written — `gap_width`, `gap_left`, `gap_right` from the same `delta`
threshold (`gap_delta`), and `doping_offset` / `doping_argmin` /
`doping_disagreement`, which is the gap centre relative to zero bias — as
part of a table that also carries metallicity, confined states and the
Dirac point. Two tools measuring the same gap with different knobs could
disagree, and there was no reason to keep both.

The engine (`detect_bandgap()` / `classify_doping()` in
`src/backend/sts_algorithms.py`, `detect_bandgap_doping()` in the backend)
is unchanged and still drives the **Detect Bandgap & Doping workflow node**,
so saved workflows keep running.

Use: Tools → Fit and features → Spectral Features → *Gap and doping*.
