/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Shared numeric formatting helpers for the map-editor readouts.
 * Made by Eduarda Policarpo, with love
 * License: GPL
 */
.pragma library

/*
 * Format a value for a read-out label with `sig` significant figures,
 * switching to scientific notation for very small / very large magnitudes.
 *
 * Fixes the "-0.000" problem: STM currents are ~1e-7, which .toFixed(3/4)
 * rounds to zero. Those now render as e.g. "-4.600e-7".
 */
function sci(v, sig) {
    if (v === undefined || v === null || (typeof v === "number" && isNaN(v)))
        return "--"
    v = Number(v)
    if (!isFinite(v)) return "--"
    if (v === 0) return "0"
    sig = sig || 4
    var a = Math.abs(v)
    // Tiny or huge → scientific (e.g. -4.600e-7, 1.234e+6).
    if (a < 1e-3 || a >= 1e5)
        return v.toExponential(Math.max(0, sig - 1))
    // Otherwise fixed, with enough decimals for `sig` significant figures.
    var decimals = sig - 1 - Math.floor(Math.log10(a))
    decimals = Math.max(0, Math.min(decimals, 8))
    return v.toFixed(decimals)
}
