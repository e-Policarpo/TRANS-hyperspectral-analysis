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
import "../map_editor/Fmt.js" as Fmt  // shared sci-notation helper

// Confinement Analysis: polynomial background + peak detection in one pass,
// with a live preview of the selected spectrum. Parameters on the left, the
// curve on the right.
Item {
    id: root
    property var closeWindow: null

    // Theme colours.
    //
    // `host ? host.bgDark : fallback` is NOT safe here: the tool is loaded
    // into an embedded window, so Window.window is the application window,
    // and reading a property it does not carry yields `undefined` rather
    // than taking the ternary's else branch -- which lands as an invalid
    // QColor and paints text black-on-black or white-on-white. Resolve each
    // one explicitly and fall back to the palette in Main.qml.
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

    // The native style paints GroupBox and the editable controls light, which
    // is unreadable against this palette's text. Style them here rather than
    // relying on whatever the host provides.
    component Section: GroupBox {
        id: sectionRoot
        property color sectionBg: "#2a2a3e"
        property color sectionBorder: "#3a3a4e"
        property color sectionTitle: "#F5A9B8"
        Layout.fillWidth: true
        topPadding: 28
        background: Rectangle {
            y: sectionRoot.topPadding - 24
            width: parent.width
            height: parent.height - sectionRoot.topPadding + 24
            color: sectionRoot.sectionBg
            border.color: sectionRoot.sectionBorder
            border.width: 1
            radius: 4
        }
        label: Text {
            text: sectionRoot.title
            color: sectionRoot.sectionTitle
            font.bold: true
            font.pixelSize: 12
            padding: 4
        }
    }

    component FieldBox: SpinBox {
        editable: true
        contentItem: TextInput {
            leftPadding: 26
            rightPadding: 26
            text: parent.textFromValue(parent.value, parent.locale)
            font: parent.font
            color: parent.enabled ? "#ffffff" : "#888888"
            selectionColor: "#5BCEFA"
            horizontalAlignment: Qt.AlignHCenter
            verticalAlignment: Qt.AlignVCenter
            readOnly: !parent.editable
            validator: parent.validator
            inputMethodHints: Qt.ImhFormattedNumbersOnly
        }
        background: Rectangle {
            implicitWidth: 132
            color: "#1a1a2e"
            border.color: parent.activeFocus ? "#5BCEFA" : "#3a3a4e"
            border.width: 1
            radius: 4
        }
        up.indicator: Rectangle {
            x: parent.width - width
            height: parent.height
            implicitWidth: 24
            color: parent.up.pressed ? "#3a3a4e" : "#2a2a3e"
            border.color: "#3a3a4e"
            radius: 4
            Text {
                text: "+"
                color: parent.parent.enabled ? "#ffffff" : "#777777"
                anchors.centerIn: parent
                font.pixelSize: 15
            }
        }
        down.indicator: Rectangle {
            height: parent.height
            implicitWidth: 24
            color: parent.down.pressed ? "#3a3a4e" : "#2a2a3e"
            border.color: "#3a3a4e"
            radius: 4
            Text {
                text: "\u2212"
                color: parent.parent.enabled ? "#ffffff" : "#777777"
                anchors.centerIn: parent
                font.pixelSize: 15
            }
        }
    }

    component FieldCombo: ComboBox {
        id: comboRoot
        contentItem: Text {
            leftPadding: 8
            rightPadding: 26
            text: comboRoot.displayText
            font: comboRoot.font
            color: comboRoot.enabled ? "#ffffff" : "#888888"
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            implicitHeight: 30
            color: "#1a1a2e"
            border.color: comboRoot.activeFocus ? "#5BCEFA" : "#3a3a4e"
            border.width: 1
            radius: 4
        }
        delegate: ItemDelegate {
            width: comboRoot.width
            contentItem: Text {
                text: modelData
                color: "#ffffff"
                verticalAlignment: Text.AlignVCenter
            }
            highlighted: comboRoot.highlightedIndex === index
            background: Rectangle {
                color: highlighted ? "#3a3a4e" : "#2a2a3e"
            }
        }
        popup: Popup {
            y: comboRoot.height
            width: comboRoot.width
            implicitHeight: Math.min(contentItem.implicitHeight, 260)
            padding: 1
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: comboRoot.popup.visible ? comboRoot.delegateModel : null
                ScrollIndicator.vertical: ScrollIndicator { }
            }
            background: Rectangle {
                color: "#2a2a3e"
                border.color: "#9B4F96"
                border.width: 1
                radius: 4
            }
        }
    }

    component FieldCheck: CheckBox {
        id: checkRoot
        contentItem: Text {
            text: checkRoot.text
            color: "#ffffff"
            leftPadding: checkRoot.indicator.width + 6
            verticalAlignment: Text.AlignVCenter
        }
    }

    // Without this the tool inherits whatever is behind it; the native style
    // then draws light panels under light text.
    Rectangle {
        anchors.fill: parent
        color: root.bgDark
        z: -1
    }

    property int spectrumCount: 0
    property bool running: false

    // ---------------------------------------------------------------------
    // Parameter map -- the single source of truth handed to the backend, so
    // the preview and the run can never disagree about what was asked for.
    // ---------------------------------------------------------------------
    function collectParams() {
        var p = {
            "baseline": backgroundCombo.currentText,
            "baseline_degree": degreeSpin.value,
            "baseline_basis": basisCombo.currentText,
            "baseline_iterations": iterationsSpin.value,
            "temperature_k": temperatureSpin.realValue,
            "x_energy_unit": energyUnitCombo.currentText,
            "direction": directionCombo.currentText,
            "height": heightSpin.realValue,
            "height_mode": heightModeCombo.currentText,
            "smooth_type": smoothTypeCombo.currentText,
            "smooth_points": smoothSpin.value,
            "deriv_smooth_type": derivTypeCombo.currentText,
            "deriv_smooth_points": derivPointsSpin.value,
            "max_peaks": maxPeaksSpin.value,
            "min_distance": minDistanceSpin.realValue,
            "interpolate_center": interpolateCheck.checked
        }
        if (limitRangeCheck.checked) {
            p["xmin"] = xminSpin.realValue
            p["xmax"] = xmaxSpin.realValue
        }
        return p
    }

    // k_B*T shown back to the user so the bin width is never a mystery.
    function kbtLabel() {
        var t = temperatureSpin.realValue
        if (t <= 0) return "off — peaks stay on the raw energy axis"
        var meV = 8.617333262e-2 * t   // k_B in meV/K
        var unit = energyUnitCombo.currentText
        var inAxis = (unit === "meV") ? meV : meV / 1000.0
        return "kʙT = " + meV.toFixed(2) + " meV  (bin width " +
               inAxis.toPrecision(3) + " " + unit + ")"
    }

    Timer {
        id: previewTimer
        interval: 200          // project convention for spectrum updates
        repeat: false
        onTriggered: root.updatePreview()
    }

    function queuePreview() { previewTimer.restart() }

    function updatePreview() {
        if (datasetCombo.currentIndex < 0 || !datasetCombo.currentText) return

        var r = backend.previewConfinementAnalysis(
            datasetCombo.currentText, spectrumSpin.value, collectParams())

        previewCanvas.clearCurves()
        previewCanvas.clearInfiniteLines()

        if (!r || !r.ok) {
            statusLabel.text = r && r.error ? r.error : "Preview unavailable"
            statusLabel.color = accentPink
            return
        }

        var corrected = (backgroundCombo.currentText !== "none")
        if (corrected) {
            previewCanvas.addCurve("raw", r.x, r.raw, "#7f7f7f", 1.0)
            previewCanvas.addCurve("background", r.x, r.baseline, "#5BCEFA", 1.0)
        }
        previewCanvas.addCurve(r.name || "corrected", r.x,
                               corrected ? r.corrected : r.raw, "#ffffff", 1.5)

        for (var i = 0; i < r.peakX.length; i++) {
            previewCanvas.addFixedInfiniteLine(
                "pk" + i, "vertical", r.peakX[i], "#F5A9B8", "")
        }

        statusLabel.text = r.count + (r.count === 1 ? " peak" : " peaks") +
                           " in " + (r.name || "spectrum")
        statusLabel.color = textMuted
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

    function runAnalysis() {
        if (datasetCombo.currentIndex < 0) return
        running = true
        statusLabel.text = "Analysing all " + spectrumCount + " spectra..."
        statusLabel.color = accentBlue
        backend.runConfinementAnalysis(datasetCombo.currentText, collectParams())
    }

    Component.onCompleted: refreshDatasets()

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }
        function onToolCompleted(toolName, path) {
            if (toolName === "Confinement Analysis") {
                running = false
                statusLabel.text = "Done — results are in the project browser."
                statusLabel.color = accentBlue
            }
        }
    }

    // =====================================================================
    // Layout
    // =====================================================================
    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        // ---------------- Parameters ----------------
        ScrollView {
            id: paramsScroll
            SplitView.preferredWidth: 400
            SplitView.minimumWidth: 340
            clip: true
            contentWidth: availableWidth      // never scroll sideways

            ColumnLayout {
                width: paramsScroll.availableWidth
                spacing: 8

                Label {
                    text: "Confinement Analysis"
                    font.pixelSize: 18
                    font.bold: true
                    color: textLight
                }

                Label {
                    text: "Removes the background and finds peaks in one pass, then " +
                          "writes an occupancy table: 1 where a spectrum has a peak, blank elsewhere."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    color: accentPurple
                }

                Section {
                    title: "Dataset"
                    Layout.fillWidth: true

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
                                from: 0
                                to: 0
                                value: 0
                                editable: true
                                onValueChanged: queuePreview()
                            }
                            Label {
                                text: "of " + spectrumCount
                                color: textMuted
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                Section {
                    title: "Polynomial background"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Background:"; color: textLight }
                        FieldCombo {
                            id: backgroundCombo
                            Layout.fillWidth: true
                            model: ["poly-iter", "poly", "als", "rubberband", "endpoints", "none"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label {
                            text: "Degree:"
                            color: backgroundCombo.currentText === "none" ? textMuted : textLight
                        }
                        FieldBox {
                            id: degreeSpin
                            from: 0; to: 15; value: 3
                            enabled: backgroundCombo.currentText !== "none"
                            onValueChanged: queuePreview()
                        }

                        Label {
                            text: "Coefficient basis:"
                            color: backgroundCombo.currentText === "none" ? textMuted : textLight
                        }
                        FieldCombo {
                            id: basisCombo
                            Layout.fillWidth: true
                            model: ["power", "legendre", "chebyshev"]
                            enabled: backgroundCombo.currentText !== "none"
                            onCurrentTextChanged: queuePreview()
                        }

                        Label {
                            text: "Iterations:"
                            color: backgroundCombo.currentText === "poly-iter" ? textLight : textMuted
                        }
                        FieldBox {
                            id: iterationsSpin
                            from: 1; to: 500; value: 25
                            enabled: backgroundCombo.currentText === "poly-iter"
                            onValueChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "poly-iter strips the peaks out of the fit, so small in-gap " +
                                  "features survive a threshold the band edges would otherwise dominate. " +
                                  "An orthogonal basis fits the same curve but returns decorrelated " +
                                  "coefficients — use it when the coefficients are the result you want."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Temperature"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Acquisition T (K):"; color: textLight }
                        FieldBox {
                            id: temperatureSpin
                            from: 0; to: 500000     // 0.00 - 5000.00 K, two decimals
                            value: 0
                            stepSize: 100
                            editable: true
                            property real realValue: value / 100.0
                            textFromValue: function(v) { return (v / 100.0).toFixed(2) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 100) }
                            onValueChanged: queuePreview()
                        }

                        Label { text: "X axis unit:"; color: textLight }
                        FieldCombo {
                            id: energyUnitCombo
                            Layout.fillWidth: true
                            model: ["eV", "meV"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: kbtLabel()
                            font.pixelSize: 11
                            font.bold: temperatureSpin.realValue > 0
                            color: temperatureSpin.realValue > 0 ? accentBlue : textMuted
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "kʙT is the error bar on a peak position. Peaks closer " +
                                  "together than this are one feature, and the output energy " +
                                  "axis is binned at the same width."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Search range"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        FieldCheck {
                            id: limitRangeCheck
                            Layout.columnSpan: 2
                            text: "Limit the X range"
                            onCheckedChanged: queuePreview()
                        }

                        Label {
                            text: "From Xmin:"
                            color: limitRangeCheck.checked ? textLight : textMuted
                        }
                        FieldBox {
                            id: xminSpin
                            from: -1000000; to: 1000000; value: -300
                            enabled: limitRangeCheck.checked
                            editable: true
                            property real realValue: value / 1000.0
                            textFromValue: function(v) { return (v / 1000.0).toFixed(3) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 1000) }
                            onValueChanged: queuePreview()
                        }

                        Label {
                            text: "To Xmax:"
                            color: limitRangeCheck.checked ? textLight : textMuted
                        }
                        FieldBox {
                            id: xmaxSpin
                            from: -1000000; to: 1000000; value: 300
                            enabled: limitRangeCheck.checked
                            editable: true
                            property real realValue: value / 1000.0
                            textFromValue: function(v) { return (v / 1000.0).toFixed(3) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 1000) }
                            onValueChanged: queuePreview()
                        }
                    }
                }

                Section {
                    title: "Filter"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Direction:"; color: textLight }
                        FieldCombo {
                            id: directionCombo
                            Layout.fillWidth: true
                            model: ["positive", "negative", "both"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label { text: "Height (%):"; color: textLight }
                        FieldBox {
                            id: heightSpin
                            from: 0; to: 10000; value: 500
                            stepSize: 50
                            editable: true
                            property real realValue: value / 100.0
                            textFromValue: function(v) { return (v / 100.0).toFixed(2) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 100) }
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Measured as:"; color: textLight }
                        FieldCombo {
                            id: heightModeCombo
                            Layout.fillWidth: true
                            model: ["range", "prominence", "max"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label { text: "Smooth (half-width):"; color: textLight }
                        FieldBox {
                            id: smoothSpin
                            from: 0; to: 500; value: 2
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Smoother:"; color: textLight }
                        FieldCombo {
                            id: smoothTypeCombo
                            Layout.fillWidth: true
                            model: ["average", "savgol"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Smoothing defaults to 2: an unsmoothed search finds several " +
                                  "times too many peaks on noisy spectra. Set 0 to disable."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Section {
                    title: "Derivative smoothing"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Type:"; color: textLight }
                        FieldCombo {
                            id: derivTypeCombo
                            Layout.fillWidth: true
                            model: ["none", "average", "savgol"]
                            onCurrentTextChanged: queuePreview()
                        }

                        Label {
                            text: "Points (half-width):"
                            color: derivTypeCombo.currentText === "none" ? textMuted : textLight
                        }
                        FieldBox {
                            id: derivPointsSpin
                            from: 0; to: 500; value: 2
                            enabled: derivTypeCombo.currentText !== "none"
                            onValueChanged: queuePreview()
                        }
                    }
                }

                Section {
                    title: "Peak selection"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Keep at most:"; color: textLight }
                        FieldBox {
                            id: maxPeaksSpin
                            from: 0; to: 100000; value: 0
                            editable: true
                            textFromValue: function(v) { return v === 0 ? "all" : String(v) }
                            valueFromText: function(t) { return t === "all" ? 0 : parseInt(t) || 0 }
                            onValueChanged: queuePreview()
                        }

                        Label { text: "Min. separation:"; color: textLight }
                        FieldBox {
                            id: minDistanceSpin
                            from: 0; to: 1000000; value: 0
                            editable: true
                            property real realValue: value / 1000.0
                            textFromValue: function(v) { return (v / 1000.0).toFixed(3) }
                            valueFromText: function(t) { return Math.round(parseFloat(t) * 1000) }
                            onValueChanged: queuePreview()
                        }

                        FieldCheck {
                            id: interpolateCheck
                            Layout.columnSpan: 2
                            text: "Interpolate peak centres"
                            onCheckedChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Min. separation defaults to kʙT when a temperature is set."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Item { Layout.preferredHeight: 4 }
            }
        }

        // ---------------- Preview ----------------
        ColumnLayout {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 300
            spacing: 6

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
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

                // Live cursor position, over the plot's top-left corner.
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
                    text: running ? "Running..." : "Run on all spectra"
                    enabled: !running && datasetCombo.currentIndex >= 0
                    onClicked: runAnalysis()
                    contentItem: Text {
                        text: runButton.text
                        color: runButton.enabled ? "#1a1a2e" : "#777777"
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 160
                        implicitHeight: 34
                        radius: 4
                        color: !runButton.enabled ? "#2a2a3e"
                             : runButton.pressed ? "#D60270" : accentPink
                        border.color: runButton.enabled ? accentPink : "#3a3a4e"
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
