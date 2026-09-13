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
            "baseline": "arpls",
            "admissible_abs_pct": admissibleAbsSpin.realValue,
            "admissible_rel": admissibleRelSpin.realValue,
            "min_support_frac": minSupportSpin.realValue,
            // null, not "", so the backend's Designer(seed=…) sees None.
            "seed": seedField.text === "" ? null : parseInt(seedField.text)
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
        root.running = true
        progressBar.reset()
        root.candidates = []
        root.selectedCandidate = -1
        root.batchExpected = datasets.length
        root.batchHeadlines = []
        candidateModel.clear()
        candidateCanvas.showMessage("Searching…")
        var several = datasets.length > 1 ? " × " + datasets.length + " datasets, one after another" : ""
        statusLabel.text = allSpectraCheck.checked
            ? "Searching all " + root.spectrumCount + " spectra" + several + ", each on its own: "
              + "every spectrum gets its own peaks, its own search and its own candidates "
              + "(seconds each, so this is minutes). Cancel stops it between spectra."
            : "Searching this spectrum" + several + " — each candidate is an optimisation over "
              + "the well size for this one spectrum, so it takes seconds, not milliseconds."
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
                                                            : (result && result.error ? result.error : "none")))
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
                    "paired": c.hole !== undefined
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
                statusLabel.text = (root.batchExpected > 1 ? "[" + result.dataset + "] " : "")
                    + head
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
                                     ? "Every spectrum is searched in turn — seconds each, so "
                                       + root.spectrumCount + " of them is a wait. The tables hold "
                                       + "every spectrum's candidates, each found on its own, with the "
                                       + "sizes grouped; the list shows one spectrum's."
                                     : root.spectrumCount + " spectra — one is searched at a time")
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

                        Label { text: "Candidates per spectrum:"; color: textLight }
                        ToolSpinBox {
                            id: maxsolSpin
                            from: 1; to: 50; value: 6
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
