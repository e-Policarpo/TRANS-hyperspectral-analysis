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

// Spectral Features: reduce every spectrum to a row of physical quantities
// (gap, doping, metallicity, confined states) for classification.
//
// The preview shows what the numbers were measured FROM -- the normalised
// curve with the detected gap edges and the counted states drawn on it. A
// gap edge in the wrong place is obvious on the plot and invisible in a
// table of 2000 rows.
Item {
    id: root
    property var closeWindow: null

    // See ConfinementAnalysisTool for why the fallbacks are explicit: the
    // tool is loaded into an embedded window, so a property the host does
    // not carry yields `undefined` rather than the ternary's else branch.
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
    property color accentMagenta: themeColor("accentMagenta", "#D60270")
    property color borderColor: themeColor("borderColor", "#9B4F96")

    property int spectrumCount: 0
    property bool running: false

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

    component FieldCombo: ComboBox {
        id: comboRoot
        contentItem: Text {
            leftPadding: 8; rightPadding: 26
            text: comboRoot.displayText
            font: comboRoot.font
            color: comboRoot.enabled ? root.textLight : root.textMuted
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            implicitHeight: 30
            color: root.bgDark
            border.color: comboRoot.activeFocus ? root.accentBlue : root.bgLight
            border.width: 1
            radius: 4
        }
        delegate: ItemDelegate {
            width: comboRoot.width
            contentItem: Text { text: modelData; color: root.textLight; verticalAlignment: Text.AlignVCenter }
            highlighted: comboRoot.highlightedIndex === index
            background: Rectangle { color: highlighted ? root.bgLight : root.bgMedium }
        }
        popup: Popup {
            y: comboRoot.height
            width: comboRoot.width
            implicitHeight: Math.min(contentItem.implicitHeight, 240)
            padding: 1
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: comboRoot.popup.visible ? comboRoot.delegateModel : null
                ScrollIndicator.vertical: ScrollIndicator { }
            }
            background: Rectangle {
                color: root.bgMedium; border.color: root.accentPurple; border.width: 1; radius: 4
            }
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

    function collectParams() {
        return {
            "normalize": normalizeCombo.currentText,
            "gap_delta": gapDeltaSpin.realValue,
            "poly_degree": degreeSpin.value,
            "poly_basis": basisCombo.currentText,
            "edge_fraction": edgeFractionSpin.realValue,
            "state_noise_sigmas": sigmaSpin.realValue,
            "state_width_samples": stateWidthSpin.value,
            "positive_only": positiveOnlyCheck.checked
        }
    }

    Timer {
        id: previewTimer
        interval: 200
        repeat: false
        onTriggered: root.updatePreview()
    }
    function queuePreview() { previewTimer.restart() }

    ListModel { id: readoutModel }

    function updatePreview() {
        if (datasetCombo.currentIndex < 0 || !datasetCombo.currentText) return

        var r = backend.previewSpectralFeatures(
            datasetCombo.currentText, spectrumSpin.value, collectParams())

        previewCanvas.clearCurves()
        previewCanvas.clearInfiniteLines()
        readoutModel.clear()

        if (!r || !r.ok) {
            statusLabel.text = r && r.error ? r.error : "Preview unavailable"
            statusLabel.color = accentPink
            return
        }

        previewCanvas.addCurve(r.name || "spectrum", r.x, r.y, String(root.textLight), 1.4)
        // The gap edges bound every other feature, so they are what to check.
        previewCanvas.addFixedInfiniteLine("gapL", "vertical", r.gapLeft, String(root.accentBlue), "")
        previewCanvas.addFixedInfiniteLine("gapR", "vertical", r.gapRight, String(root.accentBlue), "")
        for (var i = 0; i < r.stateX.length; i++) {
            previewCanvas.addFixedInfiniteLine("st" + i, "vertical", r.stateX[i],
                                               root.accentPink, "")
        }

        for (var k = 0; k < r.names.length; k++) {
            readoutModel.append({ "feature": r.names[k], "value": r.values[k] })
        }

        statusLabel.text = (r.valid ? "" : "FLAGGED INVALID — ") +
                           r.stateX.length + " in-gap state" +
                           (r.stateX.length === 1 ? "" : "s") +
                           ", gap " + Fmt.sci(r.gapRight - r.gapLeft, 3) +
                           "  in " + (r.name || "spectrum")
        statusLabel.color = r.valid ? textMuted : accentPink
    }

    function refreshDatasets() {
        var all = backend.getDatasetList()
        datasetCombo.model = all.length > 0 ? all : ["No datasets loaded"]
        updateSpectrumRange()
    }

    function updateSpectrumRange() {
        if (datasetCombo.currentIndex < 0) return
        var info = backend.getDatasetInfo ? backend.getDatasetInfo(datasetCombo.currentText) : null
        spectrumCount = (info && info.num_spectra) ? info.num_spectra : 1
        spectrumSpin.to = Math.max(0, spectrumCount - 1)
        queuePreview()
    }

    function runExtraction() {
        if (datasetCombo.currentIndex < 0) return
        running = true
        statusLabel.text = "Extracting features from all " + spectrumCount + " spectra..."
        statusLabel.color = accentBlue
        backend.extractSpectralFeatures(datasetCombo.currentText, collectParams())
    }

    Component.onCompleted: refreshDatasets()

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }
        function onToolCompleted(toolName, path) {
            if (toolName === "Spectral Features") {
                running = false
                statusLabel.text = "Done — the feature table is in the project browser. " +
                                   "Every column can be mapped with the Map Generator."
                statusLabel.color = accentBlue
            }
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
                    text: "Spectral Features"
                    font.pixelSize: 18
                    font.bold: true
                    color: textLight
                }

                Label {
                    text: "Reduces each spectrum to one row of physical quantities — gap, " +
                          "doping, band-edge steepness, confined states — as a flat table. " +
                          "Every column becomes a spatial map, and the table is the input " +
                          "to classification."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    color: accentPurple
                }

                Section {
                    title: "Dataset"
                    ColumnLayout {
                        anchors.fill: parent
                        DatasetComboBox {
                            id: datasetCombo
                            Layout.fillWidth: true
                            onCurrentTextChanged: updateSpectrumRange()
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
                    }
                }

                Section {
                    title: "Normalisation"
                    ColumnLayout {
                        anchors.fill: parent
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Method:"; color: textLight }
                            FieldCombo {
                                id: normalizeCombo
                                Layout.fillWidth: true
                                model: ["max", "band-edge", "area", "none"]
                                onCurrentTextChanged: queuePreview()
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "dI/dV scales with tip height and setpoint. Without a " +
                                  "per-spectrum normalisation the strongest signal in the " +
                                  "table is how close the tip was, not the sample."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Gap and doping"
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Gap threshold:"; color: textLight }
                        FieldBox {
                            id: gapDeltaSpin
                            from: 1; to: 500; value: 50
                            property real realValue: value / 1000.0
                            textFromValue: function(v) { return (v / 1000.0).toFixed(3) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 1000) }
                            onValueChanged: queuePreview()
                        }

                        Label { text: "State width (samples):"; color: textLight }
                        FieldBox {
                            id: stateWidthSpin
                            from: 3; to: 101; value: 11
                            onValueChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Features narrower than the state width are suppressed " +
                                  "before the gap search, so a confined state is not " +
                                  "mistaken for a band edge. Doping is the midpoint of the " +
                                  "two edges."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Metallicity"
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Degree:"; color: textLight }
                        FieldBox {
                            id: degreeSpin
                            from: 1; to: 10; value: 4
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Coefficient basis:"; color: textLight }
                        FieldCombo {
                            id: basisCombo
                            Layout.fillWidth: true
                            model: ["legendre", "chebyshev", "power"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label { text: "Band-edge fraction:"; color: textLight }
                        FieldBox {
                            id: edgeFractionSpin
                            from: 1; to: 49; value: 15
                            property real realValue: value / 100.0
                            textFromValue: function(v) { return (v / 100.0).toFixed(2) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 100) }
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Fit above zero only:"; color: textLight }
                        CheckBox {
                            id: positiveOnlyCheck
                            text: "the LDOS cannot be negative"
                            checked: true
                            onCheckedChanged: queuePreview()
                            // See IntegrationTool: the control sizes itself
                            // from its own `text`, so it has to be set there.
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
                            text: "Fitted outside the gap only. Legendre is the only basis " +
                                  "that decorrelates on a uniformly sampled sweep, which is " +
                                  "what makes the coefficients usable as features."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Confined states"
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Threshold (sigma):"; color: textLight }
                        FieldBox {
                            id: sigmaSpin
                            from: 5; to: 200; value: 40
                            property real realValue: value / 10.0
                            textFromValue: function(v) { return (v / 10.0).toFixed(1) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 10) }
                            onValueChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "States must clear this many noise sigmas. A percentage " +
                                  "threshold inside a flat gap counts noise, not states."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
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
                Layout.preferredHeight: parent.height * 0.5
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
                        objectName: "cursorReadout"
                        anchors.centerIn: parent
                        text: ""
                        color: accentBlue
                        font.family: "Menlo, Consolas, monospace"
                        font.pixelSize: 11
                    }
                }
            }

            Label {
                text: "Blue: detected gap edges.   Pink: counted in-gap states."
                color: textMuted
                font.pixelSize: 10
            }

            // The numbers this spectrum contributes to the table, so the plot
            // above can be checked against them.
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgMedium
                border.color: bgLight
                border.width: 1
                radius: 4

                ListView {
                    id: readoutView
                    objectName: "readoutView"
                    anchors.fill: parent
                    anchors.margins: 6
                    clip: true
                    model: readoutModel
                    delegate: RowLayout {
                        width: readoutView.width
                        spacing: 8
                        Text {
                            text: model.feature
                            color: textMuted
                            font.pixelSize: 11
                            Layout.preferredWidth: 170
                            elide: Text.ElideRight
                        }
                        Text {
                            text: model.value
                            color: textLight
                            font.family: "Menlo, Consolas, monospace"
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                    }
                    ScrollIndicator.vertical: ScrollIndicator { }
                }
            }

            Label {
                id: statusLabel
                objectName: "statusLabel"
                Layout.fillWidth: true
                text: "Select a dataset to preview."
                color: textMuted
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true

                Button {
                    id: runButton
                    text: running ? "Running..." : "Extract features"
                    enabled: !running && datasetCombo.currentIndex >= 0
                    onClicked: runExtraction()
                    contentItem: Text {
                        text: runButton.text
                        color: runButton.enabled ? root.bgDark : root.textMuted
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 160
                        implicitHeight: 34
                        radius: 4
                        color: !runButton.enabled ? root.bgMedium
                             : runButton.pressed ? root.accentMagenta : accentPink
                        border.color: runButton.enabled ? accentPink : root.bgLight
                        border.width: 1
                    }
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
}
