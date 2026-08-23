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

// Line Scan Designer: one confinement search per position along a line.
//
// The single-spectrum question repeated point by point — and not converging
// is an answer. Most positions of an arbitrary scan fall outside the
// confining structure, and a map where every point has a size is a map that
// lies, so those come back grey with the reason recorded.
Item {
    id: root
    property var closeWindow: null

    // Dropping datasets from the project browser onto the window adds them
    // to the selection; declaring these two makes it a drop target.
    property bool datasetDropActive: false
    function acceptDatasetDrop(names) {
        datasetList.addToSelection(names)
        updateDatasetInfo()
    }

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
    property string tableName: ""

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    readonly property var ndimLabels: Vocab.ndimLabels
    readonly property var carrierLabels: Vocab.carrierLabels
    readonly property var matchLabels: Vocab.matchLabels
    readonly property var priorityLabels: Vocab.priorityLabels

    function ndimKey() { return Vocab.keyAt(Vocab.ndimKeys, ndimCombo.currentIndex) }
    function coordsKey() {
        return Vocab.keyAt(Vocab.coordsFor(ndimKey()).keys, coordsCombo.currentIndex)
    }
    function symKey() {
        return Vocab.keyAt(Vocab.symsFor(ndimKey(), coordsKey()).keys,
                           symCombo.currentIndex)
    }

    function searchParams() {
        return {
            "carrier": Vocab.keyAt(Vocab.carrierKeys, carrierCombo.currentIndex),
            "meff_e": massElectronField.text,
            "meff_h": massHoleField.text,
            "ndim": ndimKey(),
            "coords": coordsKey(),
            "sym": symKey(),
            "Lmin": lminSpin.realValue,
            "Lmax": lmaxSpin.realValue,
            "match": Vocab.keyAt(Vocab.matchKeys, matchCombo.currentIndex),
            "priority": Vocab.keyAt(Vocab.priorityKeys, priorityCombo.currentIndex),
            "max_rrmse": maxErrorSpin.realValue,
            "maxsol": perPointSpin.value,
            "group_tol_nm": groupTolSpin.realValue,
            "pair_tol_nm": pairTolSpin.realValue,
            "split_e": splitESpin.realValue,
            "split_h": splitHSpin.realValue,
            "min_abs_V": neutralSpin.realValue,
            "height": heightSpin.realValue,
            "baseline": "arpls"
        }
    }

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        updateDatasetInfo()
    }

    function updateDatasetInfo() {
        var picked = datasetList.selectedDatasets
        if (!picked || picked.length === 0) { root.spectrumCount = 0; return }
        var info = backend.getDatasetInfo(picked[0])
        root.spectrumCount = (info && info.num_spectra) ? info.num_spectra : 0
    }

    function estimateText() {
        if (root.spectrumCount <= 0) return ""
        // Measured on the engine this drives: roughly a quarter of a second
        // per candidate per position. Saying so up front is the difference
        // between a wait and a hang.
        var seconds = root.spectrumCount * perPointSpin.value * 0.25
        if (seconds < 90) return "about " + Math.round(seconds) + " s"
        return "about " + Math.round(seconds / 60) + " min"
    }

    function runSearch() {
        var picked = datasetList.selectedDatasets
        if (!picked || picked.length === 0) return
        root.running = true
        root.tableName = ""
        stripCanvas.showMessage("Searching every position…")
        statusLabel.text = "Searching " + root.spectrumCount + " position(s) — "
                         + estimateText()
        if (picked.length > 1) {
            backend.runToolOnDatasets("line_scan_designer", picked, searchParams())
        } else {
            backend.runLineScanDesigner(picked[0], searchParams())
        }
    }

    Connections {
        target: backend
        function onDataLoaded(name) { datasetList.model = backend.getDatasetList() }

        function onLineScanDesignCompleted(result) {
            root.running = false
            if (!result || !result.ok) {
                stripCanvas.showMessage(result && result.error
                                        ? result.error : "Nothing found")
                statusLabel.text = result && result.error ? result.error
                                                          : "Nothing found"
                return
            }
            root.tableName = result.dataset || ""
            stripCanvas.showLineScan({
                "points": result.points,
                "groups": result.groups,
                "segments": result.segments,
                "position_label": "Position (nm)"
            })

            var summary = result.summary || {}
            var reasons = summary.reasons || {}
            var parts = []
            for (var key in reasons) parts.push(reasons[key] + "× " + key)
            statusLabel.text = (summary.converged || 0) + " of "
                + (summary.total || 0) + " position(s) converged, "
                + (result.groups ? result.groups.length : 0) + " size group(s)"
                + (parts.length > 0 ? " — " + parts.join(", ") : "")
        }
    }

    Component.onCompleted: {
        refreshDatasets()
        stripCanvas.showMessage("Pick a line scan and run the search")
    }

    Component.onDestruction: stripCanvas.cleanup()

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

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
                    text: "Searches every position for the well that produces its " +
                          "ladder of levels. Positions with no confinement come back " +
                          "empty with the reason — they are not given a size."
                    wrapMode: Text.Wrap
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
                            Layout.preferredHeight: 118
                            visibleRows: 4
                            model: []

                            bgColor: bgDark
                            borderColorNormal: root.datasetDropActive ? accentBlue
                                                                      : accentPurple
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
                                           " line scans — searched one after another"
                                if (root.spectrumCount > 0)
                                    return root.spectrumCount + " positions — " +
                                           estimateText() + " at " +
                                           perPointSpin.value + " candidate(s) each"
                                return root.datasetDropActive
                                       ? "Drop to add to the selection"
                                       : "Pick a line scan — or drag one here from " +
                                         "the project browser"
                            }
                            font.pixelSize: 10
                            color: root.datasetDropActive ? accentBlue : textMuted
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
                        }

                        Label { text: "Electron edge (V):"; color: textLight }
                        ToolSpinBox {
                            id: splitESpin
                            from: -50000; to: 50000; value: 0; stepSize: 50; decimals: 4
                        }

                        Label { text: "Hole edge (V):"; color: textLight }
                        ToolSpinBox {
                            id: splitHSpin
                            from: -50000; to: 50000; value: 0; stepSize: 50; decimals: 4
                        }

                        Label { text: "Neutral band (V):"; color: textLight }
                        ToolSpinBox {
                            id: neutralSpin
                            from: 0; to: 10000; value: 0; stepSize: 50; decimals: 4
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "The same boundaries as the single-spectrum designer, " +
                                  "applied at every position. Set them from a spectrum " +
                                  "you understand before running the whole line."
                            font.pixelSize: 10
                            color: textMuted
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
                                color: bgDark; border.color: bgLight; radius: 4
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
                                color: bgDark; border.color: bgLight; radius: 4
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
                            text: "With both carriers a position only counts when the " +
                                  "two close on the same well — the pair's requirement, " +
                                  "point by point. It costs two searches per position."
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
                                coordsCombo.model = Vocab.coordsFor(ndimKey()).labels
                                coordsCombo.currentIndex = 0
                            }
                        }

                        Label { text: "Shape:"; color: textLight }
                        ToolComboBox {
                            id: coordsCombo
                            Layout.fillWidth: true
                            model: Vocab.coordsFor("1D").labels
                            onCurrentIndexChanged: {
                                symCombo.model = Vocab.symsFor(ndimKey(), coordsKey()).labels
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
                            model: Vocab.symsFor("1D", "cartesian").labels
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
                    }
                }

                ToolSection {
                    title: "Along the line"

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
                            id: maxErrorSpin
                            from: 1; to: 10000; value: 500; stepSize: 50; decimals: 2
                        }

                        Label { text: "Candidates / point:"; color: textLight }
                        ToolSpinBox {
                            id: perPointSpin
                            from: 1; to: 10; value: 1
                        }

                        Label { text: "Group tolerance (nm):"; color: textLight }
                        ToolSpinBox {
                            id: groupTolSpin
                            from: 1; to: 10000; value: 100; stepSize: 25; decimals: 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "A position whose best candidate is worse than the " +
                                  "limit is reported as having no confinement rather " +
                                  "than being given a number that does not fit. Each " +
                                  "extra candidate per point is another global " +
                                  "optimisation — one is what a long line wants."
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
                            Layout.fillWidth: true
                            text: "A table with one row per position — size, error, " +
                                  "group, geometry, and the reason where there is none " +
                                  "— plus the size laid out along the line in metres. " +
                                  "Every column of the table is a map away: send it to " +
                                  "Map Assembly."
                            font.pixelSize: 11
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: root.tableName !== ""
                            text: "Registered as: " + root.tableName
                            font.pixelSize: 11
                            color: accentBlue
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
                        text: running ? "Searching…"
                                      : (datasetList.selectedDatasets.length > 1
                                         ? "Map " + datasetList.selectedDatasets.length + " lines"
                                         : "Map the line")
                        enabled: !running && datasetList.selectedDatasets.length > 0
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

        DesignerCanvas {
            id: stripCanvas
            Layout.fillWidth: true
            Layout.fillHeight: true
            backgroundColor: root.bgDark
            foregroundColor: root.textMuted
        }
    }
}
