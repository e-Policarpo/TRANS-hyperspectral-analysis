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
import TransQML 1.0
import "../components"

// Confinement Designer: measured levels in, candidate geometries out.
//
// The inverse of every other tool here — instead of describing a spectrum it
// asks which well would produce one. Knobs on the left, the spectrum being
// fitted and the chosen candidate on the right.
Item {
    id: root
    property var closeWindow: null

    // Theme colours. Reading a colour the host window does not carry yields
    // `undefined` (an invalid QColor), so each one is resolved explicitly.
    property var parentWindow: Window.window
    function themeColor(name, fallback) {
        return (parentWindow && parentWindow[name] !== undefined
                && parentWindow[name] !== null) ? parentWindow[name] : fallback
    }
    property color bgDark: themeColor("bgDark", "#1a1a2e")
    property color bgMedium: themeColor("bgMedium", "#2a2a3e")
    property color bgLight: themeColor("bgLight", "#3a3a4e")
    property color accentPink: themeColor("accentPink", "#F5A9B8")
    property color accentBlue: themeColor("accentBlue", "#5BCEFA")
    property color accentPurple: themeColor("accentPurple", "#9B4F96")
    property color textLight: themeColor("textLight", "#ffffff")
    property color textMuted: themeColor("textMuted", "#cccccc")

    property bool running: false
    property int spectrumCount: 0
    property var candidates: []
    property int selectedCandidate: -1

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // ---------------------------------------------------------------------
    // The vocabulary. Keys are what the backend compares and stores; the
    // labels beside them are only ever displayed — the split is what makes a
    // saved project survive a change of wording.
    // ---------------------------------------------------------------------
    readonly property var ndimKeys: ["0D", "1D", "2D", "3D"]
    readonly property var ndimLabels: [
        "0D — quantum dot", "1D — well", "2D — well or disc", "3D — box or cylinder"
    ]

    readonly property var carrierKeys: ["electrons", "holes", "both"]
    readonly property var carrierLabels: [
        "Electrons (empty states, V > 0)",
        "Holes (filled states, V < 0)",
        "Electrons + holes (paired by geometry)"
    ]

    readonly property var matchKeys: ["absolute", "delta_e", "delta_e_ratios"]
    readonly property var matchLabels: [
        "Absolute energies", "Differences (ΔE)", "ΔE ratios"
    ]

    readonly property var priorityKeys: ["uniform", "ground_state", "low_quantum_numbers"]
    readonly property var priorityLabels: [
        "Uniform", "Ground state only", "Low quantum numbers"
    ]

    readonly property var sortKeys: ["rrmse", "rrmse_delta_e", "size_asc",
                                     "size_desc", "anisotropy", "ground_state"]
    readonly property var sortLabels: [
        "Error (RRMSE)", "Error in the spacings (ΔE)", "Size — smallest first",
        "Size — largest first", "Anisotropy — most symmetric", "E₁ (ground state)"
    ]

    // Which coordinate systems and symmetries a dimensionality allows. A 0D
    // geometry's `coords` names its model outright, which is why the dot
    // models appear here rather than in a list of their own.
    function coordsFor(ndim) {
        if (ndim === "0D") return {keys: ["spherical", "disc", "parabolic"],
                                   labels: ["Spherical", "Disc / lens", "Parabolic"]}
        if (ndim === "1D") return {keys: ["cartesian"], labels: ["Cartesian"]}
        if (ndim === "2D") return {keys: ["cartesian", "circular"],
                                   labels: ["Cartesian", "Circular (disc)"]}
        return {keys: ["cartesian", "cylindrical"], labels: ["Cartesian", "Cylindrical"]}
    }

    function symsFor(ndim, coords) {
        if (ndim === "2D" && coords === "cartesian")
            return {keys: ["square", "rectangular"], labels: ["Square (Lx = Ly)", "Rectangular"]}
        if (ndim === "3D" && coords === "cartesian")
            return {keys: ["cubic", "tetragonal", "orthorhombic"],
                    labels: ["Cubic (Lx = Ly = Lz)", "Tetragonal (Lx = Ly)", "Orthorhombic"]}
        return {keys: [""], labels: ["—"]}
    }

    function ndimKey() { return ndimKeys[Math.max(0, ndimCombo.currentIndex)] }
    function coordsKey() {
        var options = coordsFor(ndimKey())
        return options.keys[Math.max(0, Math.min(coordsCombo.currentIndex,
                                                 options.keys.length - 1))]
    }
    function symKey() {
        var options = symsFor(ndimKey(), coordsKey())
        return options.keys[Math.max(0, Math.min(symCombo.currentIndex,
                                                 options.keys.length - 1))]
    }

    // ---------------------------------------------------------------------
    // Parameters
    // ---------------------------------------------------------------------
    function searchParams() {
        return {
            "spectrum_index": spectrumSpin.value,
            "carrier": carrierKeys[Math.max(0, carrierCombo.currentIndex)],
            "meff_e": massElectronField.text,
            "meff_h": massHoleField.text,
            "ndim": ndimKey(),
            "coords": coordsKey(),
            "sym": symKey(),
            "Lmin": lminSpin.realValue,
            "Lmax": lmaxSpin.realValue,
            "tol": tolSpin.realValue,
            "maxsol": maxsolSpin.value,
            "match": matchKeys[Math.max(0, matchCombo.currentIndex)],
            "priority": priorityKeys[Math.max(0, priorityCombo.currentIndex)],
            "sort": sortKeys[Math.max(0, sortCombo.currentIndex)],
            "pair_tol_nm": pairTolSpin.realValue,
            "split_e": splitESpin.realValue,
            "split_h": splitHSpin.realValue,
            "min_abs_V": neutralSpin.realValue,
            "height": heightSpin.realValue,
            "baseline": "arpls"
        }
    }

    function datasetName() { return datasetCombo.currentText }

    function refreshDatasets() {
        var current = datasetCombo.currentText
        datasetCombo.model = backend.getDatasetList()
        var index = datasetCombo.model.indexOf(current)
        datasetCombo.currentIndex = index >= 0 ? index : 0
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
        var name = datasetName()
        if (!name) return
        root.running = true
        root.candidates = []
        root.selectedCandidate = -1
        candidateModel.clear()
        candidateCanvas.showMessage("Searching…")
        statusLabel.text = "Searching — a candidate is a global optimisation, " +
                           "so this takes seconds, not milliseconds."
        backend.runConfinementDesigner(name, searchParams())
    }

    function showCandidate(index) {
        if (index < 0 || index >= root.candidates.length) {
            candidateCanvas.showMessage("No candidate selected")
            return
        }
        root.selectedCandidate = index
        candidateCanvas.showCandidate(root.candidates[index])
    }

    function dimensionText(candidate) {
        var dims = candidate.dims_nm || []
        var unit = (candidate.ndim === "0D" && candidate.coords === "parabolic")
                   ? " meV" : " nm"
        var parts = []
        for (var i = 0; i < dims.length; i++) parts.push(dims[i].toFixed(3))
        return parts.join(" × ") + unit
    }

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }

        function onDesignerCompleted(result) {
            root.running = false
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
                    "paired": c.hole !== undefined
                })
            }
            if (root.candidates.length > 0) {
                showCandidate(0)
                var edges = result.edges
                statusLabel.text = root.candidates.length + " candidate(s)"
                    + (result.pairs > 0 ? ", " + result.pairs + " pair(s)" : "")
                    + (edges && edges.gap !== undefined && edges.gap !== null
                       ? " — gap " + edges.gap.toFixed(3) + " eV"
                       : (edges && edges.E_c !== undefined && edges.E_c !== null
                          ? " — E_c " + edges.E_c.toFixed(3) + " eV" : ""))
            } else {
                candidateCanvas.showMessage(result && result.error
                                            ? result.error : "No candidates")
                statusLabel.text = result && result.error ? result.error
                                                          : "No candidate fits."
            }
        }
    }

    ListModel { id: candidateModel }

    Component.onCompleted: {
        refreshDatasets()
        candidateCanvas.showMessage("Run a search to see candidates")
    }

    Component.onDestruction: {
        spectrumCanvas.cleanup()
        candidateCanvas.cleanup()
    }

    // =====================================================================
    // Layout: knobs left, pictures right
    // =====================================================================
    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        // ---------------- knobs ----------------
        ScrollView {
            Layout.preferredWidth: 360
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parent.width
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    text: "Which well would produce these levels? The peaks are found " +
                          "with the same engine Confinement Analysis uses, split into " +
                          "carriers by the sign of the bias, and each branch is searched " +
                          "for the geometry that reproduces its ladder."
                    wrapMode: Text.Wrap
                    color: accentPurple
                }

                ToolSection {
                    title: "Spectrum"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Dataset:"; color: textLight }
                        ToolComboBox {
                            id: datasetCombo
                            Layout.fillWidth: true
                            model: []
                            onCurrentTextChanged: updateDatasetInfo()
                        }

                        Label { text: "Spectrum:"; color: textLight }
                        ToolSpinBox {
                            id: spectrumSpin
                            from: 0; to: 0; value: 0
                            onValueChanged: schedulePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: root.spectrumCount > 0
                                  ? root.spectrumCount + " spectra — one is searched at a time"
                                  : "Pick a dataset of spectra"
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

                        Label { text: "Weighting:"; color: textLight }
                        ToolComboBox {
                            id: priorityCombo
                            Layout.fillWidth: true
                            model: priorityLabels
                        }

                        Label { text: "Max error (%):"; color: textLight }
                        ToolSpinBox {
                            id: tolSpin
                            from: 1; to: 10000; value: 500; stepSize: 50; decimals: 2
                        }

                        Label { text: "Candidates:"; color: textLight }
                        ToolSpinBox {
                            id: maxsolSpin
                            from: 1; to: 50; value: 6
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

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: running ? "Searching…" : "Find candidates"
                        enabled: !running && root.spectrumCount > 0
                        highlighted: true
                        onClicked: runSearch()
                    }
                    Button {
                        text: "Cancel"
                        enabled: running
                        onClicked: backend.cancelCurrentOperation()
                    }
                    Item { Layout.fillWidth: true }
                    Button {
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
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            DesignerCanvas {
                id: spectrumCanvas
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(160, root.height * 0.28)
                backgroundColor: root.bgDark
                foregroundColor: root.textMuted
            }

            DesignerCanvas {
                id: candidateCanvas
                Layout.fillWidth: true
                Layout.fillHeight: true
                backgroundColor: root.bgDark
                foregroundColor: root.textMuted
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

                    Label {
                        text: root.candidates.length > 0
                              ? "Candidates — the smallest well that explains the ladder " +
                                "is the primary one; the rest are its aliases and other masses"
                              : "No candidates yet"
                        color: textMuted
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
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
