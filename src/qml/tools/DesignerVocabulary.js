/*
 * T.R.A.N.S. — the designer's vocabulary, shared by both designer panels.
 *
 * Keys are what the backend compares and what a saved project stores; the
 * labels beside them are only ever displayed. Two panels ask the same
 * questions — which carriers, which geometry, how to match — and keeping one
 * copy of the answers is what stops a mode being renamed in one place and
 * silently ignored in the other.
 */
.pragma library

var ndimKeys = ["0D", "1D", "2D", "3D"]
var ndimLabels = ["0D — quantum dot", "1D — well", "2D — well or disc",
                  "3D — box or cylinder"]

var carrierKeys = ["electrons", "holes", "both"]
var carrierLabels = ["Electrons (empty states, V > 0)",
                     "Holes (filled states, V < 0)",
                     "Electrons + holes (paired by geometry)"]

var matchKeys = ["absolute", "delta_e", "delta_e_ratios"]
var matchLabels = ["Absolute energies", "Differences (ΔE)", "ΔE ratios"]

var priorityKeys = ["uniform", "ground_state", "low_quantum_numbers"]
var priorityLabels = ["Uniform", "Ground state only", "Low quantum numbers"]

// Which model level each measured level is compared to. A DIFFERENT question
// from `priority`, which decides how much each target counts once that
// comparison is made — the two were one combo box for as long as only one of
// them was reachable, and they are not one question.
var assignKeys = ["energy", "sequential", "low_quantum_numbers", "mixed"]
var assignLabels = ["Nearest energy", "Sequential states",
                    "Lowest quantum numbers",
                    "Mixed (energy and quantum numbers)"]

var searchModeKeys = ["sample", "enumerate"]
var searchModeLabels = ["Sample (random restarts)",
                        "Enumerate (deterministic lattice)"]

var sortKeys = ["rrmse", "rrmse_delta_e", "size_asc", "size_desc",
                "anisotropy", "ground_state"]
var sortLabels = ["Error (RRMSE)", "Error in the spacings (ΔE)",
                  "Size — smallest first", "Size — largest first",
                  "Anisotropy — most symmetric", "E₁ (ground state)"]

// Which coordinate systems a dimensionality allows. A 0D geometry's `coords`
// names its model outright, which is why the dot models appear here rather
// than in a list of their own.
function coordsFor(ndim) {
    if (ndim === "0D") return {keys: ["spherical", "disc", "parabolic"],
                               labels: ["Spherical", "Disc / lens", "Parabolic"]}
    if (ndim === "1D") return {keys: ["cartesian"], labels: ["Cartesian"]}
    if (ndim === "2D") return {keys: ["cartesian", "circular"],
                               labels: ["Cartesian", "Circular (disc)"]}
    return {keys: ["cartesian", "cylindrical"],
            labels: ["Cartesian", "Cylindrical"]}
}

// Symmetry only constrains a Cartesian geometry: a disc or a cylinder has
// already said everything its shape says.
function symsFor(ndim, coords) {
    if (ndim === "2D" && coords === "cartesian")
        return {keys: ["square", "rectangular"],
                labels: ["Square (Lx = Ly)", "Rectangular"]}
    if (ndim === "3D" && coords === "cartesian")
        return {keys: ["cubic", "tetragonal", "orthorhombic"],
                labels: ["Cubic (Lx = Ly = Lz)", "Tetragonal (Lx = Ly)",
                         "Orthorhombic"]}
    return {keys: [""], labels: ["—"]}
}

// The dimensions a geometry actually has, in her terms rather than the
// engine's — {keys: ["d1", "d2"], labels: ["R", "L_z"]} for a lens. These are
// exactly the dimensions that can be pinned or given a range of their own: a
// square is ONE length filling two slots, and a tetragonal cell is d1 and d3
// with no d2, so the list is not simply "one per dimensionality".
//
// A mirror of ToolImplementations._designer_dim_names, which derives the same
// list from Designer.dim_keys. QML cannot import Python and the panel has to
// draw these controls before any search has run, so the table exists twice;
// keep the two in step.
function dimsFor(ndim, coords, sym) {
    if (ndim === "0D") {
        if (coords === "spherical") return {keys: ["d1"], labels: ["R"]}
        if (coords === "parabolic") return {keys: ["d1", "d2"],
                                            labels: ["l_xy", "l_z"]}
        return {keys: ["d1", "d2"], labels: ["R", "L_z"]}
    }
    if (ndim === "1D") return {keys: ["d1"], labels: ["L"]}
    if (ndim === "2D") {
        if (coords === "circular") return {keys: ["d1"], labels: ["R"]}
        if (sym === "square") return {keys: ["d1"], labels: ["L"]}
        return {keys: ["d1", "d2"], labels: ["Lx", "Ly"]}
    }
    if (coords === "cylindrical") return {keys: ["d1", "d2"],
                                          labels: ["R", "L_z"]}
    if (sym === "cubic") return {keys: ["d1"], labels: ["L"]}
    if (sym === "tetragonal") return {keys: ["d1", "d3"], labels: ["Lx", "Lz"]}
    return {keys: ["d1", "d2", "d3"], labels: ["Lx", "Ly", "Lz"]}
}

// Pick a key by combo index, clamped — a combo whose model was just replaced
// can report an index the new list does not have.
function keyAt(keys, index) {
    return keys[Math.max(0, Math.min(index, keys.length - 1))]
}

// The geometry as text, for a list row or a plot title.
function dimensionText(candidate) {
    var dims = candidate.dims_nm || []
    var unit = (candidate.ndim === "0D" && candidate.coords === "parabolic")
               ? " meV" : " nm"
    var parts = []
    for (var i = 0; i < dims.length; i++) parts.push(dims[i].toFixed(3))
    return parts.join(" × ") + unit
}
