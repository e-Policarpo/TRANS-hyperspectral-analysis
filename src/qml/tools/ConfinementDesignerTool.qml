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
import "DesignerVocabulary.js" as Vocab

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

    // The vocabulary lives in DesignerVocabulary.js — the line-scan panel
    // asks the same questions, and one copy of the answers is what stops a
    // mode being renamed in one place and silently ignored in the other.
    readonly property var ndimLabels: Vocab.ndimLabels
    readonly property var carrierLabels: Vocab.carrierLabels
    readonly property var matchLabels: Vocab.matchLabels
    readonly property var priorityLabels: Vocab.priorityLabels
    readonly property var sortLabels: Vocab.sortLabels

    function coordsFor(ndim) { return Vocab.coordsFor(ndim) }
    function symsFor(ndim, coords) { return Vocab.symsFor(ndim, coords) }

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
    function searchParams() {
        return {
            "spectrum_index": spectrumSpin.value,
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
        // Destruction order is not guaranteed: a canvas child can already be
        // gone when the panel's own handler runs.
        if (spectrumCanvas) spectrumCanvas.cleanup()
        if (candidateCanvas) candidateCanvas.cleanup()
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

                        Button {
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
