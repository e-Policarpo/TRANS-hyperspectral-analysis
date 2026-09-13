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
import "../map_editor/Fmt.js" as Fmt

// Multi-Peak Fitting: a sum of Gaussian / Lorentzian / pseudo-Voigt peaks
// plus a polynomial baseline, fitted to every spectrum of every selected
// dataset (batch key ``multi_peak_fit``).
//
// The preview fits ONE spectrum of the first selected dataset and draws
// data, fit, baseline and each component, so a wrong baseline degree or a
// runaway peak count is visible before 2000 spectra are fitted.
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    property bool datasetDropActive: false

    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color accentOrange: (parentWindow && parentWindow.accentOrange !== undefined) ? parentWindow.accentOrange : Theme.accentOrange
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    property int spectrumCount: 0
    property bool running: false

    // Map ComboBox label → backend shape string.
    readonly property var shapeOptions: [
        { label: "Gaussian",      value: "gaussian"     },
        { label: "Lorentzian",    value: "lorentzian"   },
        { label: "Pseudo-Voigt",  value: "pseudo_voigt" }
    ]

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // The native style paints these light, which is unreadable here.
    component Section: GroupBox {
        id: sectionRoot
        Layout.fillWidth: true
        topPadding: 28
        background: Rectangle {
            y: sectionRoot.topPadding - 24
            width: parent.width
            height: parent.height - sectionRoot.topPadding + 24
            color: root.bgMedium
            border.color: root.bgLight
            border.width: 1
            radius: 4
        }
        label: Text {
            text: sectionRoot.title
            color: root.accentPink
            font.bold: true
            font.pixelSize: 12
            padding: 4
        }
    }

    component FieldBox: SpinBox {
        editable: true
        contentItem: TextInput {
            leftPadding: 26; rightPadding: 26
            text: parent.textFromValue(parent.value, parent.locale)
            font: parent.font
            color: parent.enabled ? root.textLight : root.textMuted
            selectionColor: root.accentBlue
            horizontalAlignment: Qt.AlignHCenter
            verticalAlignment: Qt.AlignVCenter
            readOnly: !parent.editable
            validator: parent.validator
            inputMethodHints: Qt.ImhFormattedNumbersOnly
        }
        background: Rectangle {
            implicitWidth: 132
            color: root.bgDark
            border.color: parent.activeFocus ? root.accentBlue : root.bgLight
            border.width: 1
            radius: 4
        }
        up.indicator: Rectangle {
            x: parent.width - width; height: parent.height; implicitWidth: 24
            color: parent.up.pressed ? root.bgLight : root.bgMedium
            border.color: root.bgLight; radius: 4
            Text { text: "+"; color: parent.parent.enabled ? root.textLight : root.textMuted
                   anchors.centerIn: parent; font.pixelSize: 15 }
        }
        down.indicator: Rectangle {
            height: parent.height; implicitWidth: 24
            color: parent.down.pressed ? root.bgLight : root.bgMedium
            border.color: root.bgLight; radius: 4
            Text { text: "−"; color: parent.parent.enabled ? root.textLight : root.textMuted
                   anchors.centerIn: parent; font.pixelSize: 15 }
        }
    }

    // ---------------------------------------------------------------------

    function previewDataset() {
        var picks = datasetList.selectedDatasets
        return picks.length > 0 ? picks[0] : ""
    }

    Timer {
        id: previewTimer
        interval: 250
        repeat: false
        onTriggered: root.updatePreview()
    }
    function queuePreview() { previewTimer.restart() }

    function updatePreview() {
        var name = previewDataset()
        previewCanvas.clearCurves()
        previewCanvas.clearInfiniteLines()
        if (!name) {
            summaryArea.text = "Select a dataset to preview a fit."
            return
        }
        var shape = shapeOptions[shapeCombo.currentIndex].value
        var r = backend.multiPeakFit(name, shape, nPeaksSpin.value,
                                     baselineSpin.value, spectrumSpin.value)
        if (!r || !r.success) {
            summaryArea.text = "Fit failed: " + (r ? r.message : "no result")
            return
        }
        previewCanvas.addCurve("data", r.x, r.y, String(root.textLight), 1.4)
        previewCanvas.addCurve("fit", r.x, r.fitted, String(root.accentPink), 1.8)
        previewCanvas.addCurve("baseline", r.x, r.baseline, String(root.accentBlue), 1.0)
        for (var i = 0; i < r.components.length; i++) {
            var comp = r.components[i].slice()
            for (var j = 0; j < comp.length; j++) comp[j] += r.baseline[j]
            previewCanvas.addCurve("peak " + (i + 1), r.x, comp, String(root.accentPurple), 1.0)
            previewCanvas.addFixedInfiniteLine("pk" + i, "vertical", r.peaks[i].center,
                                               String(root.accentOrange), "")
        }
        summaryArea.text = formatSummary(name, r)
    }

    function formatSummary(name, r) {
        var lines = []
        lines.push(name + "  ·  spectrum " + spectrumSpin.value)
        lines.push("R² = " + r.rsq.toFixed(5) + "    RSS = " + r.rss.toExponential(3))
        lines.push("")
        lines.push("Peaks (" + r.peaks.length + "):")
        for (var i = 0; i < r.peaks.length; i++) {
            var p = r.peaks[i]
            var line = "  #" + (i + 1) +
                       "  center=" + Fmt.sci(p.center, 5) +
                       "  amp=" + p.amplitude.toExponential(3) +
                       "  FWHM=" + Fmt.sci(p.fwhm, 4)
            if (p.eta !== undefined && p.eta >= 0) line += "  η=" + p.eta.toFixed(3)
            lines.push(line)
        }
        if (r.baseline_coeffs && r.baseline_coeffs.length) {
            lines.push("")
            lines.push("Baseline (highest-order first): " + r.baseline_coeffs.map(function(c) {
                return Number(c).toExponential(3)
            }).join(", "))
        }
        return lines.join("\n")
    }

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
        updateSpectrumRange()
    }

    function updateSpectrumRange() {
        var name = previewDataset()
        if (!name) { spectrumCount = 0; return }
        var info = backend.getDatasetInfo(name)
        spectrumCount = (info && info.num_spectra) ? info.num_spectra : 1
        spectrumSpin.to = Math.max(0, spectrumCount - 1)
        if (spectrumSpin.value > spectrumSpin.to) spectrumSpin.value = spectrumSpin.to
        queuePreview()
    }

    function runFit() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        running = true
        statusLabel.text = datasets.length > 1
            ? "Fitting " + datasets.length + " datasets one after another..."
            : "Fitting all " + spectrumCount + " spectra..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("multi_peak_fit", datasets, {
            "peak_shape": shapeOptions[shapeCombo.currentIndex].value,
            "n_peaks_auto": nPeaksSpin.value,
            "baseline_degree": baselineSpin.value,
            "positive_only": positiveOnlyCheck.checked
        })
    }

    Component.onCompleted: refreshDatasets()

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }
        function onToolCompleted(toolName, path) {
            if (toolName === "Multi-Peak Fitting") {
                running = false
                root.runningTaskName = ""
                statusLabel.text = "Done — '- Peak Fit' table and '- Fitted' curves are in the " +
                                   "project browser. Every table column can be mapped with the Map Generator."
                statusLabel.color = accentBlue
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Multi-Peak") >= 0) {
                running = false
                root.runningTaskName = ""
                statusLabel.text = "Error: " + message
                statusLabel.color = accentMagenta
            }
        }
        // A cancelled fit reaches neither handler above, so without this the
        // Run button stays disabled and the button keeps reading "Running...".
        function onOperationCancelled(name) {
            if (name !== root.runningTaskName) return
            root.runningTaskName = ""
            running = false
            statusLabel.text = "Cancelled"
            statusLabel.color = textMuted
        }
    }

    // =====================================================================

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        ScrollView {
            id: paramsScroll
            SplitView.preferredWidth: 400
            SplitView.minimumWidth: 340
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: paramsScroll.availableWidth
                spacing: 8

                Label {
                    text: "Multi-Peak Fitting"
                    font.pixelSize: 18
                    font.bold: true
                    color: textLight
                }

                Label {
                    text: "Detect peaks and fit a sum of Gaussian / Lorentzian / pseudo-Voigt " +
                          "line shapes plus a polynomial baseline to every spectrum. Each " +
                          "dataset yields a per-spectrum peak table (a flat dataset — every " +
                          "column maps) and the fitted curves."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    color: accentPurple
                }

                Section {
                    title: "Datasets"
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        DatasetMultiSelect {
                            id: datasetList
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                            model: backend.getDatasetList()

                            bgColor: root.bgDark
                            borderColorNormal: root.datasetDropActive ? accentBlue : bgLight
                            borderColorFocus: accentPink
                            textColor: textLight
                            textMutedColor: textMuted
                            selectionColor: accentPink
                            onSelectionChanged: updateSpectrumRange()
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
                                text: root.datasetDropActive
                                      ? "Drop to add to the selection"
                                      : "…or drag datasets here from the project browser"
                                font.pixelSize: 10
                                color: root.datasetDropActive ? accentBlue : textMuted
                                elide: Text.ElideRight
                            }
                            ToolButton {
                                text: "Refresh list"
                                flat: true
                                font.pixelSize: 10
                                onClicked: root.refreshDatasets()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Preview spectrum:"; color: textLight }
                            FieldBox {
                                id: spectrumSpin
                                from: 0; to: 0; value: 0
                                onValueChanged: queuePreview()
                            }
                            Label { text: "of " + spectrumCount; color: textMuted }
                            Item { Layout.fillWidth: true }
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "The preview fits one spectrum of the first selected dataset."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Fit parameters"
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Peak shape:"; color: textLight }
                        ToolComboBox {
                            id: shapeCombo
                            Layout.fillWidth: true
                            model: shapeOptions.map(function(o) { return o.label })
                            onCurrentIndexChanged: queuePreview()
                        }

                        Label { text: "Max peaks (0 = auto):"; color: textLight }
                        FieldBox {
                            id: nPeaksSpin
                            from: 0; to: 50; value: 0
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Baseline degree:"; color: textLight }
                        FieldBox {
                            id: baselineSpin
                            from: -1; to: 6; value: 1
                            onValueChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "-1 = no baseline, 0 = constant, 1 = linear, … The baseline " +
                                  "is fitted simultaneously with the peaks, so the data need " +
                                  "not be flattened first."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "Fit above zero only:"; color: textLight }
                        CheckBox {
                            id: positiveOnlyCheck
                            text: "the LDOS cannot be negative"
                            checked: true
                            contentItem: Text {
                                text: positiveOnlyCheck.text
                                color: textMuted
                                font.pixelSize: 10
                                leftPadding: positiveOnlyCheck.indicator.width
                                             + positiveOnlyCheck.spacing
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Peaks are still detected on the whole curve; only the fit " +
                                  "ignores samples below zero. Turn off for a signed quantity " +
                                  "(current, a difference spectrum)."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Output"
                    Label {
                        Layout.fillWidth: true
                        text: "Per dataset:\n" +
                              "• <name> - Peak Fit — one row per spectrum: peak count, R², " +
                              "peak<k>_center / _amplitude / _fwhm\n" +
                              "• <name> - Fitted — the fitted curves on the source axis\n" +
                              "• <name>_PeakFit.csv — one row per peak, with shape, width, η\n\n" +
                              "Select several datasets to fit them one after another."
                        font.pixelSize: 10
                        color: textMuted
                        wrapMode: Text.Wrap
                    }
                }

                Item { Layout.preferredHeight: 4 }
            }
        }

        ColumnLayout {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 320
            spacing: 6

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: parent.height * 0.55
                color: bgDark
                border.color: bgLight
                border.width: 1
                radius: 4

                GraphCanvas {
                    id: previewCanvas
                    objectName: "previewCanvas"
                    anchors.fill: parent
                    anchors.margins: 2
                    showGrid: true
                    showLegend: true
                    autoScale: true
                    backgroundColor: root.bgDark
                    foregroundColor: root.textMuted
                    gridColor: root.borderColor

                    onCursorMoved: function(x, y) {
                        cursorReadout.text = "X " + Fmt.sci(x, 5) + "    Y " + Fmt.sci(y, 4)
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 8
                    width: cursorReadout.implicitWidth + 14
                    height: cursorReadout.implicitHeight + 8
                    radius: 4
                    color: Qt.rgba(0, 0, 0, 0.55)
                    border.color: bgLight
                    border.width: 1
                    visible: cursorReadout.text.length > 0
                    Text {
                        id: cursorReadout
                        anchors.centerIn: parent
                        text: ""
                        color: accentBlue
                        font.family: "Menlo, Consolas, monospace"
                        font.pixelSize: 11
                    }
                }
            }

            Label {
                text: "White: data.   Pink: fit.   Blue: baseline.   Purple: components.   Orange: peak centres."
                color: textMuted
                font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 150
                color: bgMedium
                border.color: bgLight
                border.width: 1
                radius: 4

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 4
                    clip: true
                    TextArea {
                        id: summaryArea
                        readOnly: true
                        text: "Select a dataset to preview a fit."
                        color: textLight
                        background: null
                        font.family: "Menlo, Consolas, monospace"
                        font.pixelSize: 11
                        wrapMode: TextArea.Wrap
                    }
                }
            }

            Label {
                id: statusLabel
                Layout.fillWidth: true
                text: ""
                color: textMuted
                wrapMode: Text.Wrap
                visible: text !== ""
            }

            RowLayout {
                Layout.fillWidth: true

                Button {
                    id: runButton
                    text: running ? "Running..."
                        : datasetList.selectedDatasets.length > 1
                          ? "Fit all (" + datasetList.selectedDatasets.length + " datasets)"
                          : "Fit all spectra"
                    enabled: !running && datasetList.selectedDatasets.length > 0
                    onClicked: runFit()
                    contentItem: Text {
                        text: runButton.text
                        color: runButton.enabled ? root.bgDark : root.textMuted
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 180
                        implicitHeight: 34
                        radius: 4
                        color: !runButton.enabled ? root.bgMedium
                             : runButton.pressed ? root.accentMagenta : accentPink
                        border.color: runButton.enabled ? accentPink : root.bgLight
                        border.width: 1
                    }
                }

                ToolButton {
                    text: "Cancel"
                    onClicked: backend.cancelCurrentOperation()
                }

                Item { Layout.fillWidth: true }

                Button {
                    id: closeButton
                    text: "Close"
                    contentItem: Text {
                        text: closeButton.text
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 90
                        implicitHeight: 34
                        radius: 4
                        color: closeButton.pressed ? bgLight : bgMedium
                        border.color: bgLight
                        border.width: 1
                    }
                    onClicked: {
                        if (root.closeWindow) { root.closeWindow() }
                        else { var win = Window.window; if (win) win.close() }
                    }
                }
            }
        }
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
