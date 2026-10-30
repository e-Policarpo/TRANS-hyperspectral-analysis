/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtQuick.Dialogs
import TransQML 1.0
import "../components"
import "DesignerVocabulary.js" as Vocab

// Confinement Designer: measured levels in, candidate geometries out.
//
// The inverse of every other tool here — instead of describing a spectrum it
// asks which well would produce one. Knobs on the left, the spectrum being
// fitted and the chosen candidate on the right.
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    // Set by WindowManager while a browser drag hovers this tool.
    property bool datasetDropActive: false

    // Dropped datasets join the selection — see WindowManager.deliverDatasetDrop.
    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    // How many of a multi-dataset run have reported back, and their headlines.
    property int batchExpected: 0
    property var batchHeadlines: []

    property var parentWindow: Window.window
    // Each colour is resolved explicitly, and the property is named as a
    // literal rather than looked up by string.
    //
    // That distinction is the whole point. This used to read
    // parentWindow[name] inside a themeColor() helper, and a subscript is
    // something QML cannot register as a binding dependency — so the binding
    // was evaluated once and never again. Measured: switching the scheme from
    // "Just Dark Mode" to a light one moved the window's own bgDark from
    // #1a1a1a to #f5f0f8 while this tool's bgDark stayed #1a1a1a, and the
    // canvases under it stayed dark inside a light window. Naming the
    // property directly makes it a real dependency, so a scheme change
    // arrives here the moment the window sees it.
    //
    // The `!== undefined` guard stays: reading a colour the host does not
    // carry yields undefined, which lands as an invalid QColor and paints
    // text black-on-black. Theme is the fallback — a singleton nothing has to
    // locate, so it cannot be missing.
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    // The rule colour. Declared because the canvas below binds gridColor to
    // it — undeclared, that binding assigns `undefined`, which QML reports
    // once at load and then leaves the canvas on its default grid forever.
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    property bool running: false
    property int spectrumCount: 0
    property var candidates: []
    property int selectedCandidate: -1

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // The vocabulary lives in DesignerVocabulary.js — the line-scan panel
    // asks the same questions, and one copy of the answers is what stops a
    // mode being renamed in one place and silently ignored in the other.
    readonly property var ndimLabels: Vocab.ndimLabels
    readonly property var carrierLabels: Vocab.carrierLabels
    readonly property var matchLabels: Vocab.matchLabels
    readonly property var priorityLabels: Vocab.priorityLabels
    readonly property var assignLabels: Vocab.assignLabels
    readonly property var searchModeLabels: Vocab.searchModeLabels
    readonly property var sortLabels: Vocab.sortLabels

    // The dimensions the chosen geometry actually has — {keys, labels} — and
    // so the rows of the per-dimension controls. Not readonly: it is
    // recomputed whenever the geometry combos move, because a disc has R and
    // L_z where a cube has one L, and a control labelled d2 would be a
    // control about an array index rather than about her sample.
    property var dimList: Vocab.dimsFor("1D", "cartesian", "")

    // What the per-dimension controls currently say, keyed by dimension:
    // {"d2": {"pinned": true, "pin": 5.0, "lo": 0, "hi": 0}}. Held here
    // rather than read back off the delegates when the search is submitted:
    // a Repeater destroys and rebuilds its delegates whenever the geometry
    // changes, and a value that only exists inside one of them is a value
    // that can be read after it has stopped existing.
    property var dimLimits: ({})

    function setDimLimit(key, entry) {
        // A new object every time — QML only notices a `var` property
        // changing when it is ASSIGNED, so mutating the map in place would
        // update nothing that reads it.
        var next = {}
        for (var k in root.dimLimits) next[k] = root.dimLimits[k]
        next[key] = entry
        root.dimLimits = next
    }

    // ---------------------------------------------------------------------
    // The resolution window, live
    // ---------------------------------------------------------------------
    // How far apart two model levels have to be for this measurement to have
    // seen both. It never enters the score — it is the yardstick 'n_tied' is
    // counted in and 'unresolvable' is decided against, and those are the two
    // columns that say whether a lower error means anything at all.
    //
    // It has to be asked for rather than derived. Half the smallest gap the
    // spectrum itself resolved is a LOWER BOUND on the resolution, not the
    // resolution: on the 4 x 5 nm lens's six targets it is 6.07 meV, and at
    // that window every runaway geometry — (3.75, 5.0), (3.2, 10.0),
    // (2.9, 14.5), (2.1, 18.0) nm, whose levels are 26.3, 21.5, 16.9 and
    // 25.8 meV apart — was reported as RESOLVED. At the thermal window all
    // four are unresolvable, which is the honest answer and the whole point
    // of the column.
    readonly property real kBoltzEv: 8.617333262e-5
    // FWHM of -df/dE is 4 ln(1 + sqrt 2) k_B T, the number usually quoted as
    // "3.5 k_B T". Written out exactly so it is the same constant as in
    // ConfinementDimensionalityTool and in ToolImplementations rather than a
    // rounded copy of it.
    readonly property real thermalFwhmKt: 3.5254943480781717
    readonly property real temperatureK: tempSpin.realValue
    readonly property real thermalWindowMeV: temperatureK > 0
        ? thermalFwhmKt * kBoltzEv * temperatureK * 1000 : NaN
    // What the run will actually use, by the same order of precedence the
    // backend applies: a number typed in beats a temperature, a temperature
    // beats the engine's data-derived bound.
    readonly property real resolutionMeV: resolutionSpin.realValue > 0
        ? resolutionSpin.realValue
        : (temperatureK > 0 ? thermalWindowMeV : NaN)

    // The window AND where it came from, together, every time it is shown:
    // a tie count in a window nobody can name is a number without units.
    function resolutionBasisText() {
        if (resolutionSpin.realValue > 0)
            return resolutionSpin.realValue.toFixed(1) + " meV as typed"
        if (temperatureK > 0)
            return thermalWindowMeV.toFixed(1) + " meV — 3.5·k_B·T at "
                   + temperatureK.toFixed(0) + " K"
        return "not set — the tie count and the 'unresolvable' verdict "
               + "stay empty until this measurement's resolution is given. "
               + "A guess derived from the peak list reads as a clean bill "
               + "of health on geometries it cannot actually separate."
    }

    // ---------------------------------------------------------------------
    // What the run will cost
    // ---------------------------------------------------------------------
    // Measured on an M1 Pro, 0D disc under ΔE, six targets, two free
    // dimensions, 1 to 18 nm, one mass: 9.5-9.8 s per spectrum per mass
    // enumerated at the default lattice, and 13.1 to 73.8 s sampled — five
    // seeds on the SAME spectrum, median 16.3 s, a 5.6x spread. The sampled
    // path stops at maxsol, so its cost depends on how quickly the quota
    // happens to fill; the enumerated one has no RNG and costs what it costs.
    // An estimate for the sampled path is therefore a range, not a number.
    // The panel used to say "seconds each", which for a 300-spectrum sweep is
    // off by two orders of magnitude.
    //
    // The enumerated cost is NOT one number: it grows with the lattice,
    // which the nodes-per-octave control moves by two orders of magnitude on
    // its own. Measured at 8 / 16 / 24 / 32 nodes per octave over her box —
    // 1,156 / 4,489 / 10,201 / 17,956 nodes — 9.91 / 16.76 / 20.24 / 24.28 s,
    // so a flat 10.6 s understates the top of that control by 2.4x, the same
    // factor the old "seconds each" understated the sweep by. The line below
    // is the one that stays ABOVE all four measurements (slope 0.79 ms per
    // node, from the 1,156-to-17,956 span): it reads ~14 s where the run
    // takes 10, and ~2.9 min at the 200,000-node cap where the run takes
    // about 2.5. An estimate that is too low is worse than one that is too
    // high, because it is the one that gets a sweep started.
    function enumSecondsFor(nodes) {
        return Math.max(10.6, 13.4 + 0.00079 * nodes)
    }

    readonly property real enumSecondsPerSearch:
        root.enumSecondsFor(root.latticeNodeCount)

    readonly property real secondsPerSearch: searchModeCombo.currentIndex === 1
                                             ? root.enumSecondsPerSearch : 25.9

    function massCount(text) {
        var parts = String(text).split(/[,;\s]+/)
        var n = 0
        for (var i = 0; i < parts.length; i++) if (parts[i] !== "") n++
        return Math.max(1, n)
    }

    // Every mass of every carrier is its own search: the same energy with a
    // heavier carrier asks for a different well.
    readonly property int searchesPerSpectrum: {
        var key = Vocab.keyAt(Vocab.carrierKeys, carrierCombo.currentIndex)
        var n = 0
        if (key === "electrons" || key === "both") n += massCount(massElectronField.text)
        if (key === "holes" || key === "both") n += massCount(massHoleField.text)
        return Math.max(1, n)
    }

    readonly property int spectraThisRun: allSpectraCheck.checked
        ? Math.max(1, root.spectrumCount) : 1

    readonly property real estimatedSeconds:
        secondsPerSearch * spectraThisRun * searchesPerSpectrum
        * Math.max(1, datasetList.selectedDatasets.length)

    function durationText(seconds) {
        if (!(seconds > 0)) return "—"
        if (seconds < 90) return Math.round(seconds) + " s"
        if (seconds < 5400) return (seconds / 60).toFixed(0) + " min"
        return (seconds / 3600).toFixed(1) + " h"
    }

    function estimateText() {
        var n = datasetList.selectedDatasets.length
        return "≈ " + durationText(root.estimatedSeconds) + " — "
               + root.spectraThisRun + " spectrum(s) × "
               + root.searchesPerSpectrum + " mass(es)"
               + (n > 1 ? " × " + n + " datasets" : "")
               + " × " + root.secondsPerSearch.toFixed(1) + " s, the measured "
               + (searchModeCombo.currentIndex === 1 ? "enumerated" : "sampled")
               + " rate on an M1 Pro for a two-dimensional 0D search over "
               + "1–18 nm with six targets"
               + (searchModeCombo.currentIndex === 1
                  ? ", scaled to this lattice of "
                    + root.thousands(root.latticeNodeCount) + " nodes — the "
                    + "enumerated cost follows the node count, and the nodes "
                    + "per octave move it by a factor of 20 on their own"
                  : "")
               + ". A different geometry or a wider range scales it."
    }

    // How big the enumeration's lattice is, and how many of its nodes get
    // refined. Both are shown because they are what the nesting claim rests
    // on: the lattice nests by construction, and the candidate LIST inherits
    // that because the budget is a DENSITY over the box rather than an
    // absolute top-N. Mirrors Designer.lattice and Designer.polish_budget —
    // QML cannot import Python, and these have to be readable before a run.
    function dimRange(key) {
        var entry = root.dimLimits[key]
        return [(entry && entry.lo > 0) ? entry.lo : lminSpin.realValue,
                (entry && entry.hi > 0) ? entry.hi : lmaxSpin.realValue]
    }

    function freeDimKeys() {
        var keys = root.dimList.keys
        var free = []
        for (var i = 0; i < keys.length; i++) {
            var entry = root.dimLimits[keys[i]]
            if (entry && entry.pinned) continue
            free.push(keys[i])
        }
        return free
    }

    function latticeNodes() {
        var keys = root.freeDimKeys()
        var perOctave = Math.max(1, enumPerOctaveSpin.value)
        var total = 1
        for (var i = 0; i < keys.length; i++) {
            var r = root.dimRange(keys[i])
            if (!(r[0] > 0) || !(r[1] >= r[0])) return 0
            total *= Math.floor(Math.log(r[1] / r[0]) / Math.LN2 * perOctave
                                + 1e-9) + 1
        }
        return keys.length > 0 ? total : 1
    }

    // Designer.POLISH_REFERENCE_OCTAVES / POLISH_ALL_BELOW /
    // POLISH_MAX_FACTOR, mirrored value for value. A number invented here
    // instead of copied is a number the panel prints and the engine does not
    // use: this mirror carried an absolute floor of 8 after the engine had
    // replaced it with an EXHAUSTIVE floor, and on a 2-8 nm by 4-6 nm box at
    // 4 nodes per octave it printed "refining 8 of 27" where the engine
    // refines all 27.
    readonly property real polishReferenceOctaves: Math.log(18.0) / Math.LN2
    readonly property int polishAllBelow: 32
    readonly property int polishMaxFactor: 10

    // `totalNodes` is the lattice this budget is for. A lattice of at most
    // `polishAllBelow` nodes is refined IN FULL — a narrow box has few
    // basins and density alone can send it to a single descent — so the
    // budget is not a pure density and cannot be shown as one.
    function polishBudget(totalNodes) {
        var want = enumPolishSpin.value
        if (want <= 0) return 0
        var keys = root.freeDimKeys()
        var volume = 1.0
        for (var i = 0; i < keys.length; i++) {
            var r = root.dimRange(keys[i])
            if (!(r[0] > 0) || !(r[1] > r[0])) continue
            volume *= (Math.log(r[1] / r[0]) / Math.LN2)
                      / root.polishReferenceOctaves
        }
        var budget = Math.ceil(want * volume)
        if (totalNodes > 0 && totalNodes <= root.polishAllBelow)
            budget = Math.max(budget, totalNodes)
        return Math.min(Math.max(1, budget), root.polishMaxFactor * want)
    }

    // The two numbers the enumeration's explainer is about, as properties so
    // they follow the ranges and the spin boxes live — and so that the
    // panel's arithmetic can be checked against Designer.lattice and
    // Designer.polish_budget in a test. The mirror drifted once already, and
    // it drifted silently because nothing compared the two.
    readonly property int latticeNodeCount: root.latticeNodes()
    readonly property int polishBudgetCount: root.polishBudget(root.latticeNodeCount)

    // The lattice size the enumeration refuses at. The engine reads
    // `enum_max_nodes` and falls back to 200,000 on 0 or null, so the spin
    // box's 0 is the engine's own default and not a cap of zero. Mirrored
    // here because the lattice size is printed beside the control and has to
    // be compared against the cap the run will actually use, not against a
    // number frozen into the text.
    readonly property int nodeCap: enumMaxNodesSpin.value > 0
                                   ? enumMaxNodesSpin.value : 200000

    function thousands(n) {
        var s = String(Math.round(n)), out = "", c = 0
        for (var i = s.length - 1; i >= 0; i--) {
            out = s.charAt(i) + out
            if (++c % 3 === 0 && i > 0) out = "," + out
        }
        return out
    }

    function coordsFor(ndim) { return Vocab.coordsFor(ndim) }
    function symsFor(ndim, coords) { return Vocab.symsFor(ndim, coords) }

    function refreshDims() {
        root.dimList = Vocab.dimsFor(ndimKey(), coordsKey(), symKey())
    }

    function ndimKey() { return Vocab.keyAt(Vocab.ndimKeys, ndimCombo.currentIndex) }
    function coordsKey() {
        return Vocab.keyAt(Vocab.coordsFor(ndimKey()).keys, coordsCombo.currentIndex)
    }
    function symKey() {
        return Vocab.keyAt(Vocab.symsFor(ndimKey(), coordsKey()).keys,
                           symCombo.currentIndex)
    }

    // ---------------------------------------------------------------------
    // Parameters
    // ---------------------------------------------------------------------
    // The per-dimension controls as the engine wants them.
    // Returns {fixed: {...}, box: {...}} holding ONLY what the user actually
    // set: an untouched panel returns two empty maps, and the backend reads
    // an empty map as the single shared (Lmin, Lmax) it has always used. A 0
    // is "unset" rather than a range end, because no dimension of a real well
    // is 0 nm wide.
    function dimensionLimits() {
        var fixed = {}
        var box = {}
        // Only the dimensions the CURRENT geometry has. A pin set on a disc
        // and left behind when she switches to a cube is a pin on a
        // dimension that no longer exists, and sending it would pin a slot
        // the search does not read.
        var keys = root.dimList.keys
        for (var i = 0; i < keys.length; i++) {
            var entry = root.dimLimits[keys[i]]
            if (!entry) continue
            if (entry.pinned) {
                fixed[keys[i]] = entry.pin
                continue
            }
            if (entry.lo > 0 || entry.hi > 0) {
                // null, not 0, for an end left blank: the backend resolves a
                // null end to the shared range rather than to a 0 nm bound.
                box[keys[i]] = [entry.lo > 0 ? entry.lo : null,
                                entry.hi > 0 ? entry.hi : null]
            }
        }
        return {"fixed": fixed, "box": box}
    }

    // The per-dimension ranges whose ends are the wrong way round, named as
    // she typed them.
    //
    // "From 10, to 3" for R used to be dropped and logged at INFO, and the
    // search then ran over the whole shared range — the OPPOSITE of the
    // request, in the one control whose purpose is to stop a dimension
    // wandering, with nothing on screen saying so. Nothing is submitted while
    // this list is non-empty; the row says so in place, and so does the
    // status line.
    function rangeProblems() {
        var problems = []
        var keys = root.dimList.keys
        for (var i = 0; i < keys.length; i++) {
            var entry = root.dimLimits[keys[i]]
            if (!entry || entry.pinned) continue
            if (entry.lo > 0 && entry.hi > 0 && entry.hi < entry.lo) {
                var label = i < root.dimList.labels.length
                            ? root.dimList.labels[i] : keys[i]
                problems.push(label + ": from " + entry.lo.toFixed(2)
                              + " to " + entry.hi.toFixed(2) + " nm")
            }
        }
        return problems
    }

    function rangeIsBackwards(key) {
        var entry = root.dimLimits[key]
        return !!(entry && !entry.pinned && entry.lo > 0 && entry.hi > 0
                  && entry.hi < entry.lo)
    }

    function searchParams() {
        var limits = dimensionLimits()
        return {
            "fixed": limits.fixed,
            "box": limits.box,
            "assign": Vocab.keyAt(Vocab.assignKeys, assignCombo.currentIndex),
            "search_mode": Vocab.keyAt(Vocab.searchModeKeys,
                                       searchModeCombo.currentIndex),
            "enum_per_octave": enumPerOctaveSpin.value,
            "enum_polish": enumPolishSpin.value,
            // Two engine knobs that used to be read by the search and set by
            // nothing. null, not 0, for both: the engine's own defaults are
            // the 200,000-node cap and the absolute 0.1 nm duplicate test,
            // and sending 0 for either would be a claim rather than a
            // fallback. A percentage on screen, a fraction on the wire —
            // Designer.is_duplicate's `rel` is a fraction of the size.
            "enum_max_nodes": enumMaxNodesSpin.value > 0
                              ? enumMaxNodesSpin.value : null,
            "dup_rel": dupRelSpin.realValue > 0
                       ? dupRelSpin.realValue / 100.0 : null,
            // null, not 0: a blank field is not "0 meV of resolution", it
            // is "derive it" — from the temperature below. With neither
            // given the diagnostic columns stay EMPTY rather than being
            // filled from the peak list, which is a lower bound on the
            // resolution and fired on none of the runaway geometries.
            "resolution_meV": resolutionSpin.realValue > 0
                              ? resolutionSpin.realValue : null,
            // 0 means "not known", and then n_tied / unresolvable come back
            // empty — the honest answer, since nothing in the peak list
            // determines how finely this spectrum resolves.
            "temperature_K": tempSpin.realValue,
            "spectrum_index": spectrumSpin.value,
            "all_spectra": allSpectraCheck.checked,
            "group_tol_nm": groupTolSpin.realValue,
            "carrier": Vocab.keyAt(Vocab.carrierKeys, carrierCombo.currentIndex),
            "meff_e": massElectronField.text,
            "meff_h": massHoleField.text,
            "ndim": ndimKey(),
            "coords": coordsKey(),
            "sym": symKey(),
            "Lmin": lminSpin.realValue,
            "Lmax": lmaxSpin.realValue,
            "tol": tolSpin.realValue,
            "maxsol": maxsolSpin.value,
            "match": Vocab.keyAt(Vocab.matchKeys, matchCombo.currentIndex),
            "priority": Vocab.keyAt(Vocab.priorityKeys, priorityCombo.currentIndex),
            "sort": Vocab.keyAt(Vocab.sortKeys, sortCombo.currentIndex),
            "pair_tol_nm": pairTolSpin.realValue,
            "split_e": splitESpin.realValue,
            "split_h": splitHSpin.realValue,
            "min_abs_V": neutralSpin.realValue,
            "height": heightSpin.realValue,
            // -1 asks the engine to decide from the threshold.
            "smooth_points": [-1, 0, 1, 2, 4][smoothCombo.currentIndex],
            "baseline": "arpls",
            "admissible_abs_pct": admissibleAbsSpin.realValue,
            "admissible_rel": admissibleRelSpin.realValue,
            "min_support_frac": minSupportSpin.realValue,
            // null, not "", so the backend's Designer(seed=…) sees None.
            "seed": seedField.text === "" ? null : parseInt(seedField.text),
            // 0 = every core but one; 1 = one spectrum at a time.
            "workers": workersSpin.value
        }
    }

    // The preview and the candidate list are one dataset's: the first one
    // picked. The search runs over every one, in the order they were picked.
    function datasetName() {
        var picks = datasetList.selectedDatasets
        return picks.length > 0 ? picks[0] : ""
    }

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
        updateDatasetInfo()
    }

    function updateDatasetInfo() {
        var name = datasetName()
        if (!name) { root.spectrumCount = 0; return }
        var info = backend.getDatasetInfo(name)
        root.spectrumCount = (info && info.num_spectra) ? info.num_spectra : 0
        spectrumSpin.to = Math.max(0, root.spectrumCount - 1)
        schedulePreview()
    }

    // ---------------------------------------------------------------------
    // Preview. Finding the peaks is milliseconds where the search is
    // seconds, so what the search will be given is shown while the knobs are
    // still moving — debounced, because a spin box fires per keystroke.
    // ---------------------------------------------------------------------
    Timer {
        id: previewTimer
        interval: 200
        onTriggered: root.refreshPreview()
    }

    function schedulePreview() { previewTimer.restart() }

    function refreshPreview() {
        var name = datasetName()
        if (!name) { spectrumCanvas.showMessage("Pick a dataset"); return }
        var preview = backend.previewDesignerTargets(name, spectrumSpin.value,
                                                     searchParams())
        spectrumCanvas.showSpectrum(preview)
        if (!preview || !preview.ok) {
            targetsLabel.text = preview && preview.error ? preview.error : "No preview"
            return
        }
        targetsLabel.text = preview.electron_eV.length + " electron target(s), " +
                            preview.hole_eV.length + " hole target(s)" +
                            (preview.in_gap_V.length > 0
                             ? ", " + preview.in_gap_V.length + " between the boundaries"
                             : "")
    }

    // ---------------------------------------------------------------------
    // Run
    // ---------------------------------------------------------------------
    function runSearch() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return

        // A range whose ends are the wrong way round is refused HERE, where
        // it can be pointed at. Submitting it would search the whole shared
        // range — the opposite of the request — and say nothing.
        var problems = rangeProblems()
        if (problems.length > 0) {
            statusLabel.text = "Nothing searched: the ends are the wrong way "
                + "round — " + problems.join("; ") + ". Swap them. Searching "
                + "the shared range instead would search the opposite of what "
                + "you asked for."
            return
        }

        // A run of more than ten minutes is committed to, not stumbled into:
        // a 300-spectrum sweep over two masses is over two hours, and the
        // panel used to describe it as "seconds each".
        if (root.estimatedSeconds > 600 && !longRunDialog.confirmed) {
            longRunDialog.open()
            return
        }
        longRunDialog.confirmed = false
        startSearch(datasets)
    }

    function startSearch(datasets) {
        root.running = true
        progressBar.reset()
        root.candidates = []
        root.selectedCandidate = -1
        root.batchExpected = datasets.length
        root.batchHeadlines = []
        candidateModel.clear()
        candidateCanvas.showMessage("Searching…")
        var several = datasets.length > 1 ? " × " + datasets.length + " datasets, one after another" : ""
        statusLabel.text = (allSpectraCheck.checked
            ? "Searching all " + root.spectrumCount + " spectra" + several + ", each on its own: "
              + "every spectrum gets its own peaks, its own search and its own candidates. "
              + "Cancel stops it between spectra. "
            : "Searching this spectrum" + several + ". ")
            + root.estimateText()
            + "  ·  resolution window " + root.resolutionBasisText()
        // One batch task; each dataset's result arrives through
        // designerCompleted and writes its own tables, named after the
        // dataset and the search settings.
        root.runningTaskName = backend.runToolOnDatasets("confinement_designer",
                                                         datasets, searchParams())
    }

    function showCandidate(index) {
        if (index < 0 || index >= root.candidates.length) {
            candidateCanvas.showMessage("No candidate selected")
            return
        }
        root.selectedCandidate = index
        candidateCanvas.showCandidate(root.candidates[index])
    }

    function dimensionText(candidate) { return Vocab.dimensionText(candidate) }

    // "Simulate": hand the selected candidate to whichever solver builds its
    // geometry. The designer matched energies analytically; the solver says
    // what the well it found really gives, which is how a real solution is
    // told from an alias of the arithmetic.
    function simulateSelected() {
        if (root.selectedCandidate < 0
                || root.selectedCandidate >= root.candidates.length) return
        var description = backend.describeCandidate(
            root.candidates[root.selectedCandidate])
        if (!description || !description.ok) {
            statusLabel.text = description && description.error
                               ? description.error
                               : "That candidate cannot be simulated here."
            return
        }
        if (parentWindow && parentWindow.openSolverForSpec) {
            parentWindow.openSolverForSpec(description)
            statusLabel.text = "Simulating " + description.label + " numerically…"
        }
    }

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }

        function onDesignerCompleted(result) {
            var heads = root.batchHeadlines.slice()
            heads.push((result && result.dataset ? result.dataset + ": " : "")
                       + (result && result.candidates_total ? result.candidates_total + " candidate(s)"
                                                            : (result && result.error ? result.error : "none"))
                       // The run's one seed — drawn when the field was blank
                       // — so a good run can be repeated exactly.
                       + (result && result.seed !== undefined && result.seed !== null
                          ? " · seed " + result.seed : ""))
            root.batchHeadlines = heads
            root.running = heads.length < root.batchExpected
            root.candidates = (result && result.candidates) ? result.candidates : []
            candidateModel.clear()
            for (var i = 0; i < root.candidates.length; i++) {
                var c = root.candidates[i]
                candidateModel.append({
                    "rowIndex": i,
                    "dims": dimensionText(c),
                    "size": c.size_nm.toFixed(3),
                    "rrmse": c.rrmse.toFixed(3),
                    "meff": c.meff.toFixed(4),
                    "carrier": c.carrier === "h" ? "h⁺" : "e⁻",
                    "paired": c.hole !== undefined,
                    // What the fit could NOT see, beside what it found. A
                    // dimension the objective is insensitive to is printed
                    // to three decimals like every other one, and without
                    // this the row gives no hint that the number is one
                    // arbitrary point of a plateau.
                    "flat": (c.flat_dims && c.flat_dims.length > 0)
                            ? c.flat_dims.join("+") + " free" : "",
                    // How many model levels the measurement cannot tell the
                    // matched one apart from: 1 is a resolved ladder.
                    "tied": (c.n_tied === undefined || isNaN(c.n_tied))
                            ? "" : "×" + c.n_tied.toFixed(0)
                })
            }
            if (root.candidates.length > 0) {
                showCandidate(0)
                var edges = result.edges
                // A sweep's headline is the whole run; the list under it is
                // one spectrum's, so say which one it is showing.
                var swept = result.all_spectra === true
                var head = swept
                    ? result.candidates_total + " candidate(s) over "
                      + result.spectra_with_candidates + "/"
                      + result.spectra_searched + " spectra — showing "
                      + (result.column ? result.column
                                       : "spectrum " + result.spectrum_index)
                    : root.candidates.length + " candidate(s)"
                // The window every 'tied' badge in the list below was
                // counted in, taken off the candidates themselves rather
                // than off the panel's controls: the rows on screen were
                // produced by the run that finished, not by whatever the
                // knobs say now.
                var basis = (root.candidates.length > 0
                             && root.candidates[0].resolution_basis)
                            ? root.candidates[0].resolution_basis : ""
                var window = (root.candidates.length > 0
                              && !isNaN(root.candidates[0].resolution_meV))
                             ? root.candidates[0].resolution_meV.toFixed(1) + " meV" : ""
                statusLabel.text = (root.batchExpected > 1 ? "[" + result.dataset + "] " : "")
                    + head
                    + (window !== ""
                       ? "  ·  tied within " + window
                         + (basis !== "" ? " (" + basis + ")" : "") : "")
                    + (result.pairs > 0 ? ", " + result.pairs + " pair(s)" : "")
                    + (edges && edges.gap !== undefined && edges.gap !== null
                       ? " — gap " + edges.gap.toFixed(3) + " eV"
                       : (edges && edges.E_c !== undefined && edges.E_c !== null
                          ? " — E_c " + edges.E_c.toFixed(3) + " eV" : ""))
                    + (result.tables && result.tables.length
                       ? " · tables: " + result.tables.join(", ") : "")
            } else {
                candidateCanvas.showMessage(result && result.error
                                            ? result.error : "No candidates")
                statusLabel.text = (root.batchExpected > 1 ? "[" + result.dataset + "] " : "")
                    + (result && result.error ? result.error : "No candidate fits.")
            }
            if (root.batchExpected > 1 && !root.running) {
                statusLabel.text = root.batchHeadlines.length + " datasets searched — "
                    + root.batchHeadlines.join(" · ")
                    + ". The list shows the last one's candidates; every dataset's tables are in the browser."
            }
            if (!root.running) root.runningTaskName = ""
        }

        // A cancelled batch never reaches designerCompleted again, so the
        // panel has to come out of its running state here. The batch counters
        // go with it: left half-counted, the next run's first result would be
        // read as the tail of this one and the headline would be nonsense.
        function onOperationCancelled(name) {
            if (name !== root.runningTaskName) return
            root.runningTaskName = ""
            root.running = false
            root.batchExpected = 0
            root.batchHeadlines = []
            candidateCanvas.showMessage("Cancelled")
            statusLabel.text = "Cancelled — nothing was written for the datasets "
                             + "that had not finished."
        }
    }

    ListModel { id: candidateModel }

    // The file is presumed to follow the dataset convention (bias in V down
    // the first column, one dI/dV spectrum per further column) — no
    // detection, so a wrong file is a dataset with wrong numbers, not an
    // error. The new dataset becomes the selection, so the preview shows it
    // at once.
    FileDialog {
        id: didvCsvDialog
        title: "Import a CSV as dI/dV spectra"
        nameFilters: ["CSV files (*.csv)", "All files (*)"]
        onAccepted: {
            var name = backend.importDidvCsv(selectedFile.toString())
            if (!name) return
            refreshDatasets()
            datasetList.setSelection([name])
            statusLabel.text = "Imported " + name + " — taken as dI/dV as it is."
        }
    }

    // A run the panel has costed at more than ten minutes asks first. The
    // quoted cost used to be "seconds each", which for a 300-spectrum sweep
    // over two masses is out by a factor of hundreds — and the tool's own
    // Cancel only stops it BETWEEN spectra, so the cheapest place to find out
    // is before it starts.
    Dialog {
        id: longRunDialog
        property bool confirmed: false
        title: "This will take a while"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: Math.min(460, root.width - 40)

        contentItem: ColumnLayout {
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: root.estimateText()
                color: root.textLight
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: "Cancel stops the sweep between spectra, not inside one, "
                      + "so the shortest way out once it is running is one "
                      + "spectrum long. Every spectrum searched before a cancel "
                      + "is discarded — nothing is written until the run ends."
                      + (root.searchesPerSpectrum > 1
                         ? " Each effective mass is its own search: dropping one "
                           + "from the mass list is the cheapest way to halve this."
                         : "")
                font.pixelSize: 10
                color: root.textMuted
                wrapMode: Text.Wrap
            }
        }

        onAccepted: {
            longRunDialog.confirmed = true
            root.runSearch()
        }
        onRejected: longRunDialog.confirmed = false
    }

    Component.onCompleted: {
        // The placeholders first: if the dataset refresh throws, the rest of
        // this handler never runs, and a blank canvas with no message reads
        // as a broken tool rather than an empty one.
        candidateCanvas.showMessage("Run a search to see candidates")
        spectrumCanvas.showMessage("Pick a dataset and a spectrum")
        refreshDatasets()
    }

    Component.onDestruction: {
        // Destruction order is not guaranteed: a canvas child can already be
        // gone when the panel's own handler runs.
        if (spectrumCanvas) spectrumCanvas.cleanup()
        if (candidateCanvas) candidateCanvas.cleanup()
        // A search whose panel has closed has nowhere to put its candidates,
        // and it is minutes of worker time. cancelOperation only fires when
        // the named task is the one running, so a stale name is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }

    // =====================================================================
    // Layout: knobs left, pictures right
    // =====================================================================
    // A SplitView, not a RowLayout: dataset names are longer than any pane
    // that also leaves room for the pictures, so the divider is draggable and
    // the reading of a name is the user's call, not a fixed 360 px.
    SplitView {
        anchors.fill: parent
        anchors.margins: 10
        orientation: Qt.Horizontal

        // A wide grab area with a thin rule drawn down the middle of it: 2 px
        // is what the divider should look like, and 10 px is what it has to be
        // to catch a mouse. SplitHandle attaches to the delegate's own root,
        // so the rule reads the state off `splitHandle`, not off itself.
        handle: Rectangle {
            id: splitHandle
            implicitWidth: 10
            color: "transparent"

            Rectangle {
                anchors.centerIn: parent
                width: 2
                height: parent.height
                radius: 1
                color: splitHandle.SplitHandle.pressed ? root.accentPink
                       : (splitHandle.SplitHandle.hovered ? root.accentPurple
                                                          : root.bgLight)
            }
        }

        // ---------------- knobs ----------------
        ScrollView {
            id: paramsScroll
            SplitView.preferredWidth: 360
            SplitView.minimumWidth: 280
            SplitView.maximumWidth: 900
            clip: true
            // Pin the content to the viewport: a ScrollView's child
            // otherwise takes its own implicit width — the widest
            // unwrapped label — and everything past the edge is clipped.
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: paramsScroll.availableWidth
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Which well would produce these levels? One spectrum (or " +
                          "typed-in energies): the peaks are found with the same engine " +
                          "Confinement Analysis uses, split into carriers by the sign of " +
                          "the bias, and each branch is searched for the geometry that " +
                          "reproduces its ladder — every candidate ranked, for you to " +
                          "inspect. To run this search at every position of a line scan " +
                          "and see how the size varies along it, use the Line Scan Designer."
                    wrapMode: Text.Wrap
                    color: accentPurple
                }

                ToolSection {
                    title: "Spectrum"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        // A curve from outside the project, taken as dI/dV as
                        // it is: the way to refine a simulation against a
                        // spectrum that never went through the pipeline.
                        ToolButton {
                            Layout.columnSpan: 2
                            text: "Import CSV as dI/dV…"
                            onClicked: didvCsvDialog.open()
                        }

                        DatasetMultiSelect {
                            id: datasetList
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            Layout.preferredHeight: 140
                            model: backend.getDatasetList()

                            bgColor: root.bgDark
                            borderColorNormal: root.datasetDropActive ? accentBlue : bgLight
                            borderColorFocus: accentPink
                            textColor: textLight
                            textMutedColor: textMuted
                            selectionColor: accentPink
                            onSelectionChanged: updateDatasetInfo()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: root.datasetDropActive
                                  ? "Drop to add to the selection"
                                  : (datasetList.selectedDatasets.length > 1
                                     ? datasetList.selectedDatasets.length + " datasets — searched one after another; "
                                       + "the preview and the list are the first one's"
                                     : "…or drag datasets here from the project browser")
                            font.pixelSize: 10
                            color: root.datasetDropActive ? accentBlue : textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Spectrum:"; color: textLight }
                        ToolSpinBox {
                            id: spectrumSpin
                            from: 0; to: 0; value: 0
                            // Still the spectrum the preview draws and the
                            // panel lists candidates for, even in a sweep.
                            enabled: !allSpectraCheck.checked
                            onValueChanged: schedulePreview()
                        }

                        ToolCheckBox {
                            id: allSpectraCheck
                            Layout.columnSpan: 2
                            text: root.spectrumCount > 1
                                  ? "Search all " + root.spectrumCount + " spectra"
                                  : "Search all spectra"
                            checked: false
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: root.spectrumCount <= 0
                                  ? "Pick a dataset of spectra"
                                  : (allSpectraCheck.checked
                                     ? "Every spectrum is searched in turn, and a search is "
                                       + "tens of seconds, not seconds: " + root.estimateText()
                                       + " The tables hold every spectrum's candidates, each "
                                       + "found on its own, with the sizes grouped; the list "
                                       + "shows one spectrum's."
                                     : root.spectrumCount + " spectra — one is searched at a time, "
                                       + root.estimateText())
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Branches"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Peak threshold (× σ):"; color: textLight }
                        ToolSpinBox {
                            id: heightSpin
                            from: 50; to: 2000; value: 300; stepSize: 25; decimals: 2
                            onValueChanged: schedulePreview()
                        }

                        // Pre-smoothing exists only to keep noise maxima under
                        // the threshold; "auto" derives the window from the
                        // threshold (none from 7σ up, 3 samples at 5σ, 5 at 3σ
                        // and below), and what a window merges is recovered
                        // from the raw curve when it is far beyond any noise.
                        Label { text: "Smoothing:"; color: textLight }
                        ToolComboBox {
                            id: smoothCombo
                            Layout.fillWidth: true
                            model: ["auto (from threshold)", "none", "3 samples", "5 samples", "9 samples"]
                            currentIndex: 0
                            onCurrentIndexChanged: schedulePreview()
                        }

                        Label { text: "Electron edge (V):"; color: textLight }
                        ToolSpinBox {
                            id: splitESpin
                            from: -50000; to: 50000; value: 0; stepSize: 50; decimals: 4
                            onValueChanged: schedulePreview()
                        }

                        Label { text: "Hole edge (V):"; color: textLight }
                        ToolSpinBox {
                            id: splitHSpin
                            from: -50000; to: 50000; value: 0; stepSize: 50; decimals: 4
                            onValueChanged: schedulePreview()
                        }

                        Label { text: "Neutral band (V):"; color: textLight }
                        ToolSpinBox {
                            id: neutralSpin
                            from: 0; to: 10000; value: 0; stepSize: 50; decimals: 4
                            onValueChanged: schedulePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "The boundary that matters is the band edge, not E_F. In " +
                                  "a doped well the lowest electron levels are filled, so " +
                                  "they appear at negative bias — a split at 0 V tears that " +
                                  "ladder in half and sends part of it to the hole search, " +
                                  "where it fits nicely and lies. Leave both at 0 for the " +
                                  "plain sign-of-bias rule."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label {
                            id: targetsLabel
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: ""
                            font.pixelSize: 10
                            color: accentBlue
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Carriers"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Search:"; color: textLight }
                        ToolComboBox {
                            id: carrierCombo
                            Layout.fillWidth: true
                            model: carrierLabels
                        }

                        Label { text: "m*  electron:"; color: textLight }
                        TextField {
                            id: massElectronField
                            Layout.fillWidth: true
                            text: "0.067"
                            color: textLight
                            background: Rectangle {
                                color: bgDark
                                border.color: bgLight
                                radius: 4
                            }
                        }

                        Label {
                            text: "m*  hole:"
                            color: carrierCombo.currentIndex === 0 ? textMuted : textLight
                        }
                        TextField {
                            id: massHoleField
                            Layout.fillWidth: true
                            text: "0.45"
                            enabled: carrierCombo.currentIndex !== 0
                            color: enabled ? textLight : textMuted
                            background: Rectangle {
                                color: bgDark
                                border.color: bgLight
                                radius: 4
                            }
                        }

                        Label {
                            text: "Pair tolerance (nm):"
                            color: carrierCombo.currentIndex === 2 ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: pairTolSpin
                            from: 1; to: 10000; value: 100; stepSize: 25; decimals: 2
                            enabled: carrierCombo.currentIndex === 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "A list of masses is a list of searches: the same energies " +
                                  "with a heavier carrier ask for a different well, and the " +
                                  "mass is usually the least known number in the problem. " +
                                  "With both carriers, the candidates are paired by the " +
                                  "geometry they agree on — it is one well confining both."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Geometry"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Dimensions:"; color: textLight }
                        ToolComboBox {
                            id: ndimCombo
                            Layout.fillWidth: true
                            model: ndimLabels
                            currentIndex: 1
                            onCurrentIndexChanged: {
                                coordsCombo.model = coordsFor(ndimKey()).labels
                                coordsCombo.currentIndex = 0
                                // Also from here: assigning an index that is
                                // already 0 emits nothing, so the chain
                                // through the other two combos cannot be
                                // relied on to fire.
                                root.refreshDims()
                            }
                        }

                        Label { text: "Shape:"; color: textLight }
                        ToolComboBox {
                            id: coordsCombo
                            Layout.fillWidth: true
                            model: coordsFor("1D").labels
                            onCurrentIndexChanged: {
                                symCombo.model = symsFor(ndimKey(), coordsKey()).labels
                                symCombo.currentIndex = 0
                                root.refreshDims()
                            }
                        }

                        Label {
                            text: "Symmetry:"
                            color: symCombo.enabled ? textLight : textMuted
                        }
                        ToolComboBox {
                            id: symCombo
                            Layout.fillWidth: true
                            model: symsFor("1D", "cartesian").labels
                            enabled: model.length > 1
                            // A square has one length where a rectangle has
                            // two, so the symmetry changes the rows below.
                            onCurrentIndexChanged: root.refreshDims()
                        }

                        Label { text: "Smallest (nm):"; color: textLight }
                        ToolSpinBox {
                            id: lminSpin
                            from: 1; to: 100000; value: 100; stepSize: 50; decimals: 2
                        }

                        Label { text: "Largest (nm):"; color: textLight }
                        ToolSpinBox {
                            id: lmaxSpin
                            from: 1; to: 100000; value: 2000; stepSize: 100; decimals: 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "The search runs in nanometres in every model, the " +
                                  "parabolic dot included — its ħω is derived from the " +
                                  "confinement length, because a size is something you can " +
                                  "estimate and a ħω is not."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                // One range for every dimension is only right when the
                // dimensions are equally determined, and on a lens matched
                // by level SPACINGS they are not: R is pinned to about a
                // hundred picometres by the data, and L_z is not measured at
                // all — in ΔE the energy origin cancels and the axial ladder
                // goes with it. Sharing one pair of sliders therefore lets
                // L_z wander to whatever ceiling was picked for R, which is
                // exactly what "it converges at 13 nm but diverges at 18"
                // is. Every control here starts at the shared range, so a
                // panel nobody touches searches what it always searched.
                ToolSection {
                    title: "Each dimension on its own"
                    visible: root.dimList.keys.length > 0

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        Label {
                            Layout.fillWidth: true
                            text: "Blank (0) means the shared range above. Pinning a " +
                                  "dimension takes it out of the search entirely — the " +
                                  "right move for a length the data does not determine, " +
                                  "because a pinned L_z returns one candidate instead of " +
                                  "a podium that is redrawn on every run."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Repeater {
                            id: dimRepeater
                            model: root.dimList.keys

                            delegate: ColumnLayout {
                                id: dimRow
                                Layout.fillWidth: true
                                spacing: 2

                                property string dimKey: modelData
                                property string dimLabel:
                                    index < root.dimList.labels.length
                                    ? root.dimList.labels[index] : modelData
                                property bool pinned: pinCheck.checked

                                // The controls are the input; root.dimLimits
                                // is the record. Published on every change
                                // and once on creation, so a freshly rebuilt
                                // row resets its dimension to "not pinned,
                                // shared range" — which is what a geometry
                                // change should mean.
                                function publish() {
                                    root.setDimLimit(dimRow.dimKey, {
                                        "pinned": pinCheck.checked,
                                        "pin": pinSpin.realValue,
                                        "lo": loSpin.realValue,
                                        "hi": hiSpin.realValue})
                                }
                                Component.onCompleted: dimRow.publish()

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Label {
                                        text: dimRow.dimLabel
                                        color: textLight
                                        font.bold: true
                                    }
                                    Item { Layout.fillWidth: true }
                                    ToolCheckBox {
                                        id: pinCheck
                                        text: "Pin (do not search)"
                                        checked: false
                                        onCheckedChanged: dimRow.publish()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    visible: dimRow.pinned

                                    Label {
                                        text: "at (nm):"
                                        color: textMuted
                                        font.pixelSize: 11
                                    }
                                    ToolSpinBox {
                                        id: pinSpin
                                        Layout.fillWidth: true
                                        from: 1; to: 100000; value: 500
                                        stepSize: 25; decimals: 2
                                        onValueChanged: dimRow.publish()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    visible: !dimRow.pinned

                                    Label {
                                        text: "from:"
                                        color: textMuted
                                        font.pixelSize: 11
                                    }
                                    ToolSpinBox {
                                        id: loSpin
                                        Layout.fillWidth: true
                                        from: 0; to: 100000; value: 0
                                        stepSize: 25; decimals: 2
                                        onValueChanged: dimRow.publish()
                                    }
                                    Label {
                                        text: "to:"
                                        color: textMuted
                                        font.pixelSize: 11
                                    }
                                    ToolSpinBox {
                                        id: hiSpin
                                        Layout.fillWidth: true
                                        from: 0; to: 100000; value: 0
                                        stepSize: 25; decimals: 2
                                        onValueChanged: dimRow.publish()
                                    }
                                }

                                // Refused, not quietly widened. Dropping the
                                // entry and searching [smallest, largest]
                                // instead is the OPPOSITE of "keep this
                                // dimension between these two", and it used
                                // to happen with nothing on screen saying so.
                                Label {
                                    Layout.fillWidth: true
                                    visible: root.rangeIsBackwards(dimRow.dimKey)
                                    text: "⚠ " + dimRow.dimLabel + ": “from” is above "
                                          + "“to”. Swap them — nothing will be searched "
                                          + "until you do, because falling back to the "
                                          + "shared range would search the whole of it."
                                    font.pixelSize: 10
                                    color: accentPink
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }

                ToolSection {
                    title: "Fit"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Match by:"; color: textLight }
                        ToolComboBox {
                            id: matchCombo
                            Layout.fillWidth: true
                            model: matchLabels
                            currentIndex: 1
                        }

                        Label { text: "Assign levels by:"; color: textLight }
                        ToolComboBox {
                            id: assignCombo
                            Layout.fillWidth: true
                            model: assignLabels
                        }

                        Label { text: "Weighting:"; color: textLight }
                        ToolComboBox {
                            id: priorityCombo
                            Layout.fillWidth: true
                            model: priorityLabels
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Two different questions. Assignment decides WHICH model " +
                                  "level each measured one is compared to; weighting decides " +
                                  "how much each measured level counts once that is settled. " +
                                  "Nearest energy is what the search has always done — the " +
                                  "others are there to ask whether the answer survives being " +
                                  "assigned another way, which on this disc it does to within " +
                                  "0.4 pp of error while R moves by a factor of 1.9."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Search by:"; color: textLight }
                        ToolComboBox {
                            id: searchModeCombo
                            Layout.fillWidth: true
                            model: searchModeLabels
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: searchModeCombo.currentIndex === 1
                                  ? "Enumerating walks a fixed lattice anchored at the " +
                                    "smallest size, so it has no random seed and widening " +
                                    "the range ADDS candidates without moving the ones " +
                                    "already found. Both halves of that are real: the " +
                                    "lattice at 13 nm is a strict subset of the one at 18 " +
                                    "(node for node, bit for bit), and the number of nodes " +
                                    "refined scales with the range, so a node ranked inside " +
                                    "the budget at 13 nm is still inside it at 18 and at " +
                                    "25 — measured, 21 → 23 → 24 candidates with every " +
                                    "earlier geometry reproduced exactly. It reports the " +
                                    "whole population rather than the best few, so " +
                                    "'Candidates per spectrum' does not cap it and the " +
                                    "tables are longer."
                                  : "Sampling restarts a global optimiser a few times and " +
                                    "keeps the best that come in under tolerance. When many " +
                                    "geometries fit equally well, which few it keeps is a " +
                                    "draw — enumerating answers 'how many are there' instead."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        // The enumeration's budget. Hidden while sampling,
                        // because they describe a lattice that is not being
                        // walked. Nodes per octave rather than nodes per
                        // range: E goes as 1/L², so equal RATIOS of L are
                        // equal steps in the quantity being fitted, and a
                        // count per octave is the one that does not change
                        // meaning when the range moves.
                        Label {
                            text: "Lattice nodes per octave:"
                            color: textLight
                            visible: searchModeCombo.currentIndex === 1
                        }
                        ToolSpinBox {
                            id: enumPerOctaveSpin
                            from: 1; to: 64; value: 8
                            visible: searchModeCombo.currentIndex === 1
                        }

                        Label {
                            text: "Nodes refined:"
                            color: textLight
                            visible: searchModeCombo.currentIndex === 1
                        }
                        ToolSpinBox {
                            id: enumPolishSpin
                            from: 1; to: 500; value: 40; stepSize: 10
                            visible: searchModeCombo.currentIndex === 1
                        }

                        // The size the enumeration refuses at. It existed in
                        // the engine and nothing set it, so a lattice the
                        // settings made too big was a refusal with no control
                        // to answer it — the only way out was to coarsen the
                        // survey. 0 is the engine's own 200,000.
                        Label {
                            text: "Refuse a lattice over (nodes, 0 = 200,000):"
                            color: textLight
                            visible: searchModeCombo.currentIndex === 1
                        }
                        ToolSpinBox {
                            id: enumMaxNodesSpin
                            from: 0; to: 2000000; value: 0; stepSize: 50000
                            visible: searchModeCombo.currentIndex === 1
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: searchModeCombo.currentIndex === 1
                            text: "A lattice node is far too coarse to BE an answer — the " +
                                  "acceptable intervals along R are 26 to 108 pm wide and " +
                                  "the nodes are about a nanometre apart — so the nodes only " +
                                  "rank the range, and the best few are refined properly. " +
                                  "More nodes is a finer survey; more refinements is more " +
                                  "candidates reported. Both cost time linearly.\n\n" +
                                  "'Nodes refined' is a DENSITY, not a count: it is the " +
                                  "budget for a 1—18 nm box per free dimension, scaled by " +
                                  "how many such boxes the range you picked is — 32 / 40 / " +
                                  "50 refinements at 13 / 18 / 25 nm. That is what makes " +
                                  "the nesting above true of the candidate LIST and not " +
                                  "only of the lattice: an absolute top-40 was a shrinking " +
                                  "share of a growing lattice, and R = 6.4681 nm used to " +
                                  "exist at 13 nm and be gone at 18. The scaling stops at " +
                                  "ten times the number typed here, and past that point " +
                                  "the guarantee lapses — as it does for a node within " +
                                  "one lattice step of the top of the range, whose cell " +
                                  "the ceiling clips. That last one is the range genuinely " +
                                  "ending rather than an artefact of the ranking.\n\n" +
                                  "A third lapse, at the other end: a lattice of " +
                                  root.polishAllBelow + " nodes or fewer is refined IN " +
                                  "FULL, because a tightly boxed " +
                                  "search has few basins and the density alone would send " +
                                  "it to one descent. Widening such a box past that " +
                                  "many nodes " +
                                  "hands the selection back to the density, which can " +
                                  "refine FEWER nodes than the small box did — 27 of 27 " +
                                  "over 2–8 by 4–6 nm at 4 per octave, 4 of 33 once R " +
                                  "reaches 13 nm. The line below always says which rule " +
                                  "is in force."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        // The two numbers the paragraph above is about, for
                        // the range and geometry actually selected.
                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: searchModeCombo.currentIndex === 1
                            text: {
                                var nodes = root.latticeNodeCount
                                if (!(nodes > 0))
                                    return "The lattice is empty — check the sizes."
                                var budget = Math.min(nodes, root.polishBudgetCount)
                                var capped = root.polishBudgetCount
                                             >= root.polishMaxFactor * enumPolishSpin.value
                                var exhaustive = nodes <= root.polishAllBelow
                                                 && budget >= nodes
                                return "Lattice " + root.thousands(nodes)
                                       + " nodes, refining "
                                       + budget + " of them ("
                                       + (100.0 * budget / nodes).toFixed(1) + "%)"
                                       + (nodes > root.nodeCap
                                          ? " — over the " + root.thousands(root.nodeCap)
                                            + "-node cap: the search "
                                            + "refuses rather than running for a quarter of "
                                            + "an hour. Lower the nodes per octave, or raise "
                                            + "the cap and budget the time first."
                                          : (exhaustive
                                             ? " — a lattice of " + root.polishAllBelow
                                               + " nodes or fewer is refined IN FULL, so "
                                               + "nothing here is being ranked. Widening "
                                               + "past that many nodes hands the selection "
                                               + "back to the density and can refine fewer "
                                               + "of the nodes you already have."
                                             : (capped
                                                ? " — the budget is at its ceiling of ten "
                                                  + "times the number above, so past here the "
                                                  + "selection is an absolute top-N again and "
                                                  + "widening the range can move a candidate."
                                                : " — scaled to this range, which is what "
                                                  + "makes widening it add candidates instead "
                                                  + "of reshuffling them.")))
                            }
                            font.pixelSize: 10
                            color: root.latticeNodeCount > root.nodeCap ? accentPink : accentBlue
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Max error (%):"; color: textLight }
                        ToolSpinBox {
                            id: tolSpin
                            from: 1; to: 10000; value: 500; stepSize: 50; decimals: 2
                        }

                        Label { text: "Candidates per spectrum:"; color: textLight }
                        ToolSpinBox {
                            id: maxsolSpin
                            from: 1; to: 50; value: 6
                        }

                        // How close two geometries have to be to count as
                        // one candidate. The search has always asked the
                        // question absolutely — 0.1 nm per dimension — and
                        // nothing could ask it any other way. On this disc
                        // that is the wrong scale in both directions: the
                        // sub-tolerance intervals along R are 26 to 108 pm
                        // wide, so 0.1 nm merges minima that are genuinely
                        // distinct, while thirteen nodes strung along an
                        // unmeasurable L_z stay thirteen rows describing one
                        // well. It is also the wrong UNIT for a parabolic
                        // dot, whose dimensions are energies in meV. 0 keeps
                        // the absolute test every existing candidate list was
                        // deduplicated with.
                        Label {
                            text: "Merge candidates within (% of size, 0 = 0.1 nm):"
                            color: textLight
                        }
                        ToolSpinBox {
                            id: dupRelSpin
                            from: 0; to: 1000; value: 0; stepSize: 10; decimals: 1
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: dupRelSpin.realValue > 0
                                  ? "Two geometries within " + dupRelSpin.realValue.toFixed(1)
                                    + "% of each other on every dimension are one candidate. "
                                    + "Relative, so it means the same thing at 3 nm and at "
                                    + "18 — and it is the only form that means anything at "
                                    + "all for a parabolic dot, whose dimensions are "
                                    + "energies in meV."
                                  : "0 keeps the absolute 0.1 nm-per-dimension test every "
                                    + "candidate list so far was deduplicated with. Worth "
                                    + "raising on a plateau, where a row per lattice node "
                                    + "along a dimension the fit cannot see is a dozen rows "
                                    + "describing one well."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Measurement temperature (K):"; color: textLight }
                        ToolSpinBox {
                            id: tempSpin
                            // The temperature these spectra were taken at:
                            // the by-hand sheet they were checked against is
                            // labelled "T = 94 K, kbT = 8 meV", and the
                            // dI/dV resolution code reads the same 28.6 mV
                            // thermal kernel from it. A number this project
                            // measured, not one invented here — and never
                            // applied silently: the window it implies is
                            // printed under it, goes into the status line,
                            // and rides on every candidate row as
                            // `resolution_basis`. 0 means "not known", and
                            // hands the window back to the data-derived
                            // lower bound with the rows saying so.
                            from: 0; to: 100000; value: 9400
                            stepSize: 100; decimals: 2
                        }

                        Label { text: "Resolution (meV, 0 = from T):"; color: textLight }
                        ToolSpinBox {
                            id: resolutionSpin
                            from: 0; to: 100000; value: 0; stepSize: 5; decimals: 1
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Resolution window: " + root.resolutionBasisText()
                            font.pixelSize: 11
                            font.bold: true
                            color: (root.resolutionMeV > 0) ? accentBlue : accentPink
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "How far apart two model levels have to be for this " +
                                  "measurement to see both. It never enters the score — it " +
                                  "is what the 'n_tied' and 'unresolvable' columns are " +
                                  "counted against, i.e. how many assignments the data " +
                                  "cannot rule out. The honest number is the thermal " +
                                  "linewidth 3.5·k_B·T — 27 meV at 90 K, 28.6 at 94, " +
                                  "91 at 300 — so it is derived from the temperature and " +
                                  "the temperature is asked for. Type a resolution only " +
                                  "when you have measured one; it wins over the " +
                                  "temperature.\n\n" +
                                  "Leaving BOTH at 0 falls back to half the smallest gap " +
                                  "the spectrum itself resolved, which is a lower bound on " +
                                  "the resolution rather than the resolution: on the " +
                                  "4×5 nm lens it is 6.07 meV, four times finer than the " +
                                  "measurement, and at that window all four runaway " +
                                  "geometries — whose levels are 17 to 26 meV apart — " +
                                  "reported 'unresolvable = False'.\n\n" +
                                  "'n_tied' is counted inside a finite ladder (the model " +
                                  "is solved to max(3×levels, 20) states), so it reads " +
                                  "'at least this many': feed more peaks in and its " +
                                  "ceiling rises with them."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Mode bandwidth (nm, 0 = auto):"; color: textLight }
                        ToolSpinBox {
                            id: groupTolSpin
                            from: 0; to: 10000; value: 0; stepSize: 10; decimals: 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Every spectrum is searched on its own and reports its own " +
                                  "candidates; nothing is fitted across spectra. The run then " +
                                  "looks for the sizes the spectra agree on: each spectrum's " +
                                  "candidates within its admissible band count as equals, and " +
                                  "the modes of that pooled set are the wells (column 'group'). " +
                                  "The bandwidth smooths the pooled sizes; 0 lets it follow " +
                                  "the data."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Admissible band (pp of error):"; color: textLight }
                        ToolSpinBox {
                            id: admissibleAbsSpin
                            from: 0; to: 1000; value: 5; stepSize: 1; decimals: 2
                        }

                        Label { text: "Admissible band (× best error):"; color: textLight }
                        ToolSpinBox {
                            id: admissibleRelSpin
                            from: 0; to: 100; value: 10; stepSize: 5; decimals: 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "A spectrum's candidates count as equals when their ΔE error " +
                                  "is within the larger of these two of its best: the ranking " +
                                  "among near-ties is optimiser noise, not physics."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Min. support (fraction of spectra):"; color: textLight }
                        ToolSpinBox {
                            id: minSupportSpin
                            from: 0; to: 100; value: 15; stepSize: 5; decimals: 2
                        }

                        Label { text: "Seed (blank = random):"; color: textLight }
                        TextField {
                            id: seedField
                            Layout.fillWidth: true
                            text: ""
                            placeholderText: "e.g. 42"
                            validator: IntValidator { bottom: 0 }
                            color: textLight
                            background: Rectangle {
                                color: bgDark
                                border.color: bgLight
                                radius: 4
                            }
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "A mode backed by fewer spectra than this is not reported. " +
                                  "The seed fixes the search's random start so a run can be " +
                                  "reproduced exactly; leave it blank for a fresh draw."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Worker processes:"; color: textLight }
                        ToolSpinBox {
                            id: workersSpin
                            from: 0; to: 64; value: 0
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "A sweep over all spectra searches several at once, one " +
                                  "per process. 0 uses every core but one; 1 searches them " +
                                  "one after another. The rows are the same either way."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Order by:"; color: textLight }
                        ToolComboBox {
                            id: sortCombo
                            Layout.fillWidth: true
                            model: sortLabels
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "In STS the energies are read from E_F and the model " +
                                  "counts from the bottom of the well, so the origins " +
                                  "differ by an unknown offset — matching on differences " +
                                  "cancels it, and the offset it finds IS the band edge. " +
                                  "Absolute matching only makes sense when the origin is " +
                                  "already known."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Label {
                    id: statusLabel
                    Layout.fillWidth: true
                    text: "Ready"
                    color: textMuted
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }

                Label {
                    Layout.fillWidth: true
                    visible: !root.running
                    text: root.rangeProblems().length > 0
                          ? "⚠ Backwards range — " + root.rangeProblems().join("; ")
                            + ". Swap the ends; nothing will be searched until you do."
                          : root.estimateText()
                    font.pixelSize: 10
                    color: root.rangeProblems().length > 0 ? accentPink
                           : (root.estimatedSeconds > 600 ? accentPink : textMuted)
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true

                    ToolButton {
                        text: running ? "Searching…"
                            : datasetList.selectedDatasets.length > 1
                              ? "Find candidates (" + datasetList.selectedDatasets.length + ")"
                              : "Find candidates"
                        enabled: !running && root.spectrumCount > 0
                        primary: true
                        onClicked: runSearch()
                    }
                    ToolButton {
                        text: "Cancel"
                        enabled: running
                        onClicked: backend.cancelCurrentOperation()
                    }
                    Item { Layout.fillWidth: true }
                    ToolButton {
                        text: "Close"
                        onClicked: {
                            if (root.closeWindow) { root.closeWindow() }
                            else { var win = Window.window; if (win) win.close() }
                        }
                    }
                }
            }
        }

        // ---------------- pictures ----------------
        ColumnLayout {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 320
            spacing: 8

            // The run's own progress and time estimate (backend.toolProgress),
            // at the top of the plots where it is seen without scrolling the
            // parameter column.
            ToolProgressBar {
                id: progressBar
                toolName: "Confinement Designer"
                active: root.running
                Layout.fillWidth: true
            }

            DesignerCanvas {
                id: spectrumCanvas
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(160, root.height * 0.28)
                backgroundColor: root.bgDark
                foregroundColor: root.textMuted
                // gridColor draws the spines and the gridlines. borderColor —
                // which is what a rule IS in this scheme — and NOT bgLight.
                // bgLight was chosen to dodge the advisory borderColor pairing,
                // but measured on all 22 schemes bgLight-on-bgDark runs
                // 1.12:1 to 1.54:1, so the frame was fainter than either
                // candidate and the painted gridline came out at 1.02–1.08:1:
                // no visible box at all, on every scheme. borderColor is the
                // higher-contrast choice in 21 of the 22.
                gridColor: root.borderColor
                // The semantic scale. These four were added to FigureCanvasItem and
                // bound at no site at all, so every canvas painted the class defaults
                // (#5BCEFA / #2ECC71 / #FF9800 / #FF6B6B) whatever the scheme said —
                // dark-tuned marks at 1.6:1 to 2.6:1 on a light scheme's near-white
                // ground, and #5BCEFA is byte-identical to a series colour it is
                // meant to be read against.
                //
                // They bind to the Theme singleton directly rather than through the
                // host: these are meanings, not decoration, and no window overrides
                // them. The canvas guards them — if a scheme's three scale colours
                // are too close to tell apart it keeps the fixed triple instead.
                accentColor: Theme.accentPink
                successColor: Theme.successColor
                warningColor: Theme.warningColor
                errorColor: Theme.errorColor
            }

            DesignerCanvas {
                id: candidateCanvas
                Layout.fillWidth: true
                Layout.fillHeight: true
                backgroundColor: root.bgDark
                foregroundColor: root.textMuted
                // gridColor draws the spines and the gridlines. borderColor —
                // which is what a rule IS in this scheme — and NOT bgLight.
                // bgLight was chosen to dodge the advisory borderColor pairing,
                // but measured on all 22 schemes bgLight-on-bgDark runs
                // 1.12:1 to 1.54:1, so the frame was fainter than either
                // candidate and the painted gridline came out at 1.02–1.08:1:
                // no visible box at all, on every scheme. borderColor is the
                // higher-contrast choice in 21 of the 22.
                gridColor: root.borderColor
                // The semantic scale — see the first canvas in this file.
                accentColor: Theme.accentPink
                successColor: Theme.successColor
                warningColor: Theme.warningColor
                errorColor: Theme.errorColor
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 150
                color: bgMedium
                border.color: bgLight
                radius: 4

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Label {
                            text: root.candidates.length > 0
                                  ? "Candidates — the smallest well that explains the " +
                                    "ladder is the primary one; the rest are its aliases " +
                                    "and other masses"
                                  : "No candidates yet"
                            color: textMuted
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        ToolButton {
                            text: "Simulate"
                            enabled: root.selectedCandidate >= 0
                            onClicked: root.simulateSelected()
                        }
                    }

                    ListView {
                        id: candidateList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: candidateModel
                        currentIndex: root.selectedCandidate

                        delegate: Rectangle {
                            width: candidateList.width
                            height: 26
                            color: index === root.selectedCandidate ? root.accentPink
                                                                    : "transparent"
                            radius: 3

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 6
                                spacing: 8

                                Label {
                                    text: model.carrier + (model.paired ? " + h⁺" : "")
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : root.textMuted
                                    font.pixelSize: 11
                                }
                                Label {
                                    text: model.dims
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : root.textLight
                                    font.pixelSize: 11
                                    Layout.fillWidth: true
                                }
                                // The two honesty badges. Blank on a
                                // candidate that has nothing to confess, so
                                // the row stays as quiet as it used to be.
                                Label {
                                    text: model.flat
                                    visible: model.flat !== ""
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : Theme.warningColor
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: model.tied
                                    visible: model.tied !== "" && model.tied !== "×1"
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : Theme.warningColor
                                    font.pixelSize: 10
                                }
                                Label {
                                    text: "m* " + model.meff
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : root.textMuted
                                    font.pixelSize: 11
                                }
                                Label {
                                    text: model.rrmse + " %"
                                    color: index === root.selectedCandidate
                                           ? root.bgDark : root.accentBlue
                                    font.pixelSize: 11
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.showCandidate(index)
                            }
                        }
                    }
                }
            }
        }
    }
}
