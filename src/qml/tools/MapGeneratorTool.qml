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
import "../components"

// Map Generator: background correction + integration over V intervals in one
// pass, then one map per interval. The intervals come from the same peak
// search Confinement Analysis uses — or straight from a previous analysis —
// so no peak-interval JSON has to be exported and loaded back, and nothing
// has to be background-corrected by hand first.
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

    // The joined interval map from the last run (position x interval), if any.
    property string intervalMapName: ""

    // The tool inherits whatever is behind it otherwise, and the native style
    // then draws light panels under light text.
    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // ---------------------------------------------------------------------
    // Scan path. "Auto" reads the dataset's own metadata; the explicit
    // choices exist because a line scan and a meandering 2-D map are laid
    // out differently and guessing wrong silently scrambles the map.
    // ---------------------------------------------------------------------
    readonly property var scanTypeKeys: ["auto", "map_meander", "map_raster", "line"]
    readonly property var scanTypeLabels: [
        "Auto (from the dataset)",
        "2D map — meander (every other row reversed)",
        "2D map — raster (rows all left-to-right)",
        "1D line scan (single row)"
    ]

    readonly property var intervalSourceKeys: ["detect", "dataset", "manual"]
    readonly property var intervalSourceLabels: [
        "Detect peaks in this dataset",
        "Take from an analysis result",
        "Enter by hand"
    ]

    function scanTypeKey() { return scanTypeKeys[Math.max(0, scanCombo.currentIndex)] }
    function intervalSource() {
        return intervalSourceKeys[Math.max(0, sourceCombo.currentIndex)]
    }

    // Detection knobs, named exactly as Confinement Analysis names them, so
    // both tools drive the same engine with the same meaning.
    function detectionParams() {
        return {
            "baseline": backgroundCombo.currentText,
            "baseline_degree": degreeSpin.value,
            "baseline_basis": basisCombo.currentText,
            "baseline_iterations": iterationsSpin.value,
            "direction": directionCombo.currentText,
            "height": heightSpin.realValue,
            "height_mode": heightModeCombo.currentText,
            "smooth_type": smoothTypeCombo.currentText,
            "smooth_points": smoothSpin.value,
            "min_distance": minDistanceSpin.realValue,
            "temperature_k": temperatureSpin.realValue,
            "x_energy_unit": energyUnitCombo.currentText,
            "min_spectra_per_bin": occupancySpin.value
        }
    }

    // kʙT and the bin width, so the map resolution is never a mystery.
    function kbtLabel() {
        var t = temperatureSpin.realValue
        if (t <= 0)
            return "no temperature — one bin per sweep step (the finest the data resolves)"
        var meV = 8.617333262e-2 * t   // k_B in meV/K
        var unit = energyUnitCombo.currentText
        var inAxis = (unit === "meV") ? meV : meV / 1000.0
        return "kʙT = " + meV.toFixed(3) + " meV — one map per occupied bin of " +
               (inAxis / 2).toPrecision(3) + " " + unit +
               " (kʙT/2, or the sweep step if that is coarser)"
    }

    function collectParams() {
        var p = detectionParams()
        p["scan_type"] = scanTypeKey()
        p["interval_source"] = intervalSource()
        p["noise_floor"] = noiseFloorSpin.realValue
        p["intervals"] = currentIntervals()
        if (intervalSource() === "dataset")
            p["intervals_from"] = intervalDatasetCombo.currentText
        return p
    }

    function currentIntervals() {
        var out = []
        for (var i = 0; i < intervalModel.count; i++) {
            var iv = intervalModel.get(i)
            out.push([iv.lower, iv.upper])
        }
        return out
    }

    function setIntervals(list) {
        intervalModel.clear()
        for (var i = 0; i < (list ? list.length : 0); i++) {
            intervalModel.append({"lower": Number(list[i][0]),
                                  "upper": Number(list[i][1])})
        }
    }

    // Datasets dropped from the project browser join the selection; the tool
    // never consumes them. See WindowManager.deliverDatasetDrop.
    property bool datasetDropActive: false

    function acceptDatasetDrop(names) {
        refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    // The dataset every single-dataset action works on: the first picked.
    function primaryDataset() {
        return datasetList.selectedDatasets.length > 0
               ? datasetList.selectedDatasets[0] : ""
    }

    function refreshDatasets() {
        var all = backend.getDatasetList()
        datasetList.model = all.length > 0 ? all : []
        datasetList.pruneSelection()
        var withIntervals = backend.getIntervalDatasets()
        intervalDatasetCombo.model = withIntervals.length > 0
                                     ? withIntervals : ["No analysis results yet"]
        updateDatasetInfo()
    }

    function updateDatasetInfo() {
        var name = primaryDataset()
        if (!name) { spectrumCount = 0; return }
        var info = backend.getDatasetInfo ? backend.getDatasetInfo(name) : null
        spectrumCount = (info && info.num_spectra) ? info.num_spectra : 0
        autoScanKey = backend.suggestedScanType(name)
    }

    property string autoScanKey: "map_raster"

    function autoScanLabel() {
        var idx = scanTypeKeys.indexOf(autoScanKey)
        return idx > 0 ? scanTypeLabels[idx] : "2D map — raster"
    }

    function loadIntervalsFromAnalysis() {
        if (intervalDatasetCombo.currentIndex < 0) return
        var found = backend.getDatasetIntervals(intervalDatasetCombo.currentText)
        setIntervals(found)
        statusLabel.text = found.length + " interval(s) taken from " +
                           intervalDatasetCombo.currentText
        statusLabel.color = accentBlue
    }

    function detectIntervals() {
        // Detection runs on the first pick: the intervals it finds are then
        // used for every selected dataset, so they must come from one of them.
        var name = primaryDataset()
        if (!name) return
        running = true
        statusLabel.text = "Finding peaks across " + spectrumCount + " spectra in " + name + "..."
        statusLabel.color = accentBlue
        backend.detectMapIntervals(name, detectionParams())
    }

    function generateMaps() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) {
            statusLabel.text = "Select at least one dataset."
            statusLabel.color = accentPink
            return
        }
        if (intervalSource() === "manual" && intervalModel.count === 0) {
            statusLabel.text = "Add at least one interval first."
            statusLabel.color = accentPink
            return
        }
        running = true
        statusLabel.text = datasets.length > 1
                           ? "Generating maps for " + datasets.length + " datasets..."
                           : "Generating maps..."
        statusLabel.color = accentBlue
        // One batch task: the datasets are processed in the order they were
        // picked, each writing into its own folder.
        backend.runToolOnDatasets("map_generator", datasets, collectParams())
    }

    Component.onCompleted: refreshDatasets()

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }

        function onIntervalMapReady(name) {
            root.intervalMapName = name
        }

        function onMapIntervalsReady(intervals) {
            running = false
            if (intervals && intervals.length > 0) {
                setIntervals(intervals)
                statusLabel.text = intervals.length + " interval(s) ready — " +
                                   "edit them or generate the maps."
                statusLabel.color = accentBlue
            } else {
                statusLabel.text = "No peaks found. Lower the height threshold " +
                                   "or change the background."
                statusLabel.color = accentPink
            }
        }
    }

    ListModel { id: intervalModel }

    // =====================================================================
    // Layout
    // =====================================================================
    ScrollView {
        id: paramsScroll
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth      // never scroll sideways

        ColumnLayout {
            width: paramsScroll.availableWidth
            spacing: 8

            Label {
                text: "Map Generator"
                font.pixelSize: 18
                font.bold: true
                color: textLight
            }

            Label {
                text: "Integrates each spectrum over the chosen bias intervals and " +
                      "lays the result out as a map — one map per interval. The " +
                      "background comes off first, with the same fit Confinement " +
                      "Analysis uses."
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                color: accentPurple
            }

            ToolSection {
                title: "Datasets"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4

                    DatasetMultiSelect {
                        id: datasetList
                        Layout.fillWidth: true
                        Layout.preferredHeight: 132
                        visibleRows: 5
                        model: backend.getDatasetList()

                        bgColor: bgDark
                        borderColorNormal: root.datasetDropActive ? accentBlue : accentPurple
                        borderColorFocus: accentPink
                        textColor: textLight
                        textMutedColor: textMuted
                        selectionColor: accentPink

                        onSelectionChanged: updateDatasetInfo()
                    }

                    Label {
                        Layout.fillWidth: true
                        text: {
                            if (datasetList.selectedDatasets.length > 1)
                                return datasetList.selectedDatasets.length +
                                       " datasets — each is mapped in turn, into its own folder"
                            if (spectrumCount > 0)
                                return spectrumCount + " spectra — looks like: " + autoScanLabel()
                            return root.datasetDropActive
                                   ? "Drop to add to the selection"
                                   : "Pick the spectra to map (not a flat/integrated dataset) — " +
                                     "or drag them here from the project browser."
                        }
                        font.pixelSize: 10
                        color: root.datasetDropActive ? accentBlue : textMuted
                        wrapMode: Text.Wrap
                    }
                }
            }

            ToolSection {
                title: "Scan type"

                ColumnLayout {
                    anchors.fill: parent

                    ToolComboBox {
                        id: scanCombo
                        Layout.fillWidth: true
                        model: scanTypeLabels
                    }

                    Label {
                        text: "A meandering 2-D scan acquires every other row backwards, " +
                              "so those rows are reversed before the map is laid out. A " +
                              "line scan has no second axis and becomes a single row — " +
                              "picking it explicitly stops a line being folded into a grid."
                        font.pixelSize: 10
                        color: textMuted
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }
            }

            ToolSection {
                title: "Background"

                GridLayout {
                    anchors.fill: parent
                    columns: 2

                    Label { text: "Background:"; color: textLight }
                    ToolComboBox {
                        id: backgroundCombo
                        Layout.fillWidth: true
                        model: ["poly-iter", "poly", "arpls", "snip", "als", "rubberband", "endpoints", "none"]
                        // arPLS fits in log space, where a tunnelling band
                        // edge is nearly straight; ModPoly cannot follow it
                        // and loses states well below the edges.
                        currentIndex: 2
                    }

                    Label {
                        text: "Degree:"
                        color: backgroundCombo.currentText === "none" ? textMuted : textLight
                    }
                    ToolSpinBox {
                        id: degreeSpin
                        from: 0; to: 15; value: 5
                        enabled: backgroundCombo.currentText !== "none"
                    }

                    Label {
                        text: "Coefficient basis:"
                        color: backgroundCombo.currentText === "none" ? textMuted : textLight
                    }
                    ToolComboBox {
                        id: basisCombo
                        Layout.fillWidth: true
                        model: ["power", "legendre", "chebyshev"]
                        enabled: backgroundCombo.currentText !== "none"
                    }

                    Label {
                        text: "Iterations:"
                        color: backgroundCombo.currentText === "poly-iter" ? textLight : textMuted
                    }
                    ToolSpinBox {
                        id: iterationsSpin
                        from: 1; to: 500; value: 25
                        enabled: backgroundCombo.currentText === "poly-iter"
                    }

                    Label {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        text: "The integral has to measure the state, not the band edge " +
                              "under it — so the same corrected curve the peak search " +
                              "runs on is what gets integrated. No hand-corrected " +
                              "dataset needed."
                        font.pixelSize: 10
                        color: textMuted
                        wrapMode: Text.Wrap
                    }
                }
            }

            ToolSection {
                title: "Integration intervals"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    ToolComboBox {
                        id: sourceCombo
                        Layout.fillWidth: true
                        model: intervalSourceLabels
                    }

                    // --- from a previous analysis ---
                    RowLayout {
                        Layout.fillWidth: true
                        visible: intervalSource() === "dataset"

                        DatasetComboBox {
                            id: intervalDatasetCombo
                            Layout.fillWidth: true
                            placeholderText: "Analysis result..."
                        }
                        Button {
                            text: "Load"
                            onClicked: loadIntervalsFromAnalysis()
                        }
                    }

                    // --- detection knobs ---
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        visible: intervalSource() === "detect"

                        Label { text: "Peak direction:"; color: textLight }
                        ToolComboBox {
                            id: directionCombo
                            Layout.fillWidth: true
                            model: ["positive", "negative", "both"]
                        }

                        Label {
                            text: heightModeCombo.currentText === "noise"
                                  ? "Threshold (× noise σ):" : "Height threshold (%):"
                            color: textLight
                        }
                        ToolSpinBox {
                            id: heightSpin
                            // 3σ: measured to keep every state a 2σ threshold
                            // finds while carrying far more of the map's
                            // weight in the states themselves.
                            from: 0; to: 10000; value: 300
                            stepSize: 50
                            decimals: 2
                        }

                        Label { text: "Height mode:"; color: textLight }
                        ToolComboBox {
                            id: heightModeCombo
                            Layout.fillWidth: true
                            model: ["range", "prominence", "max", "noise"]
                            // 'noise' compares each peak with the spectrum's
                            // own noise, so the threshold means the same thing
                            // on every spectrum. 'range' and 'prominence'
                            // scale with the curve's span, which the band
                            // edges set — 5% of that rejects real states.
                            currentIndex: 3
                        }

                        Label { text: "Smoothing:"; color: textLight }
                        ToolComboBox {
                            id: smoothTypeCombo
                            Layout.fillWidth: true
                            model: ["average", "savgol", "none"]
                        }

                        Label { text: "Smoothing points:"; color: textLight }
                        ToolSpinBox {
                            id: smoothSpin
                            from: 0; to: 50; value: 2
                        }

                        Label { text: "Min. separation (X):"; color: textLight }
                        ToolSpinBox {
                            id: minDistanceSpin
                            from: 0; to: 100000; value: 0
                            stepSize: 100
                            decimals: 4
                        }

                        Button {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: running ? "Working..." : "Detect intervals"
                            enabled: !running && datasetList.selectedDatasets.length > 0
                            onClicked: detectIntervals()
                        }
                    }

                    // --- thermal binning: the interval grid ---
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        visible: intervalSource() === "detect"

                        Label { text: "Acquisition T (K):"; color: textLight }
                        ToolSpinBox {
                            id: temperatureSpin
                            from: 0; to: 500000        // 0.00–5000.00 K
                            value: 0
                            stepSize: 100
                            decimals: 2
                        }

                        Label { text: "X axis unit:"; color: textLight }
                        ToolComboBox {
                            id: energyUnitCombo
                            Layout.fillWidth: true
                            model: ["eV", "meV"]
                        }

                        Label {
                            text: "Min. spectra per bin:"
                            color: temperatureSpin.realValue > 0 ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: occupancySpin
                            from: 1; to: 10000; value: 1
                            enabled: temperatureSpin.realValue > 0
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: kbtLabel()
                            font.pixelSize: 11
                            font.bold: temperatureSpin.realValue > 0
                            color: temperatureSpin.realValue > 0 ? accentBlue : accentPink
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "With a temperature set, the intervals are the kʙT/2 bins " +
                                  "that hold a peak — the same grid Confinement Analysis " +
                                  "reports on, so both tools find the same states. Raising " +
                                  "the minimum drops bins seen in only a few spectra without " +
                                  "widening the ones that remain."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }

                    // --- the interval list, always editable ---
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 140
                        color: bgDark
                        border.color: bgLight
                        border.width: 1
                        radius: 4

                        ListView {
                            id: intervalList
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true
                            model: intervalModel
                            spacing: 2
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                            delegate: RowLayout {
                                width: ListView.view.width
                                spacing: 4

                                Label {
                                    text: (index + 1) + "."
                                    color: textMuted
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 22
                                }
                                TextField {
                                    Layout.fillWidth: true
                                    text: Number(model.lower).toFixed(4)
                                    color: textLight
                                    font.pixelSize: 11
                                    background: Rectangle { color: bgMedium; radius: 3 }
                                    onEditingFinished: {
                                        var v = parseFloat(text)
                                        if (!isNaN(v)) intervalModel.setProperty(index, "lower", v)
                                    }
                                }
                                Label { text: "to"; color: textMuted; font.pixelSize: 11 }
                                TextField {
                                    Layout.fillWidth: true
                                    text: Number(model.upper).toFixed(4)
                                    color: textLight
                                    font.pixelSize: 11
                                    background: Rectangle { color: bgMedium; radius: 3 }
                                    onEditingFinished: {
                                        var v = parseFloat(text)
                                        if (!isNaN(v)) intervalModel.setProperty(index, "upper", v)
                                    }
                                }
                                Button {
                                    text: "×"
                                    flat: true
                                    implicitWidth: 26
                                    onClicked: intervalModel.remove(index)
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: intervalModel.count === 0
                            text: "No intervals yet"
                            color: textMuted
                            font.pixelSize: 11
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Button {
                            text: "Add interval"
                            onClicked: intervalModel.append({"lower": 0.0, "upper": 0.1})
                        }
                        Button {
                            text: "Clear"
                            enabled: intervalModel.count > 0
                            onClicked: intervalModel.clear()
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: intervalModel.count + " interval(s) → " +
                                  intervalModel.count + " map(s)"
                            color: textMuted
                            font.pixelSize: 11
                        }
                    }
                }
            }

            ToolSection {
                title: "Integration"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true

                        Label { text: "Noise floor (× σ):"; color: textLight }
                        ToolSpinBox {
                            id: noiseFloorSpin
                            from: 0; to: 1000; value: 100
                            stepSize: 25
                            decimals: 2
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: "Only what stands above each spectrum's own noise is " +
                              "integrated. A bin holding no state otherwise integrates " +
                              "pure noise — negative half the time, and comparable in " +
                              "size to the real states, which is why maps looked like a " +
                              "diagnostic of the fit. At 1σ the states keep their weight " +
                              "and empty bins read ~0. Set 0 to integrate everything, " +
                              "signed, as measured."
                        font.pixelSize: 10
                        color: textMuted
                        wrapMode: Text.Wrap
                    }
                }
            }

            ToolSection {
                title: "Output"

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        text: "Filed under outputs/maps/<dataset>/, split by format " +
                              "(gsf/, tiff/, csv/): one calibrated map per interval, " +
                              "plus the integrals as a flat dataset you can inspect " +
                              "or re-map."
                        font.pixelSize: 11
                        color: textMuted
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    Label {
                        text: "With more than one interval you also get a joined map — " +
                              "position along the line across, interval up, indexed by " +
                              "its midpoint."
                        font.pixelSize: 11
                        color: textMuted
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    Button {
                        text: "Open interval map in Hyperspectral"
                        enabled: root.intervalMapName !== ""
                        visible: root.intervalMapName !== ""
                        Layout.fillWidth: true
                        onClicked: backend.openDatasetInHyperspectral(root.intervalMapName)
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
                    text: running ? "Working..."
                                  : (datasetList.selectedDatasets.length > 1
                                     ? "Generate maps (" + datasetList.selectedDatasets.length + " datasets)"
                                     : "Generate maps")
                    enabled: !running && datasetList.selectedDatasets.length > 0
                    highlighted: true
                    onClicked: generateMaps()
                }

                Button {
                    text: "Cancel"
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
}
