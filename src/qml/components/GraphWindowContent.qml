/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * GraphWindowContent - Enhanced graph window with matplotlib and curve management
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import TransQML 1.0

Item {
    id: root

    // Backend reference (set by EmbeddedWindow onLoaded)
    property var backend: null

    // Graph identifier for linking
    property string graphId: ""
    property string linkedTableId: ""

    // Entity ID for WindowManager
    property string entityId: ""

    // Initial curves to populate (set by WindowManager)
    property var curves: []

    // Axis label properties (set by WindowManager)
    property string xLabel: ""
    property string yLabel: ""
    property string graphTitle: ""

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    // Define size for scrolling
    implicitWidth: mainLayout.implicitWidth
    implicitHeight: mainLayout.implicitHeight

    // Signals
    signal curveProcessed(int originalId, string operation, int newId)
    signal plotDataRequested(string tableId, int xCol, var yCols)

    ColumnLayout {
        id: mainLayout
        anchors.fill: parent
        spacing: 0

        // Tab bar
        TabBar {
            id: tabBar
            Layout.fillWidth: true
            background: Rectangle { color: bgDarker }

            TabButton {
                text: "Plot"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 0 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 0 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 0
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Curves"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 1 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 1 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 1
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Settings"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 2 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 2 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 2
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // Tab content
        StackLayout {
            id: tabStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // =============================================
            // Tab 0: Plot View
            // =============================================
            Item {
                id: plotTab

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Toolbar
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        Layout.margins: 4
                        spacing: 4

                        ToolButton {
                            icon.source: "qrc:/icons/home.png"
                            ToolTip.text: "Reset View"
                            ToolTip.visible: hovered
                            onClicked: graphCanvas.resetView()
                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 3
                            }
                            contentItem: Text {
                                text: "Reset"
                                color: textLight
                                font.pixelSize: 11
                            }
                        }

                        ToolButton {
                            ToolTip.text: "Zoom In"
                            ToolTip.visible: hovered
                            onClicked: graphCanvas.zoomIn(1.2)
                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 3
                            }
                            contentItem: Text {
                                text: "+"
                                color: textLight
                                font.pixelSize: 14
                                font.bold: true
                            }
                        }

                        ToolButton {
                            ToolTip.text: "Zoom Out"
                            ToolTip.visible: hovered
                            onClicked: graphCanvas.zoomOut(1.2)
                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 3
                            }
                            contentItem: Text {
                                text: "-"
                                color: textLight
                                font.pixelSize: 14
                                font.bold: true
                            }
                        }

                        Rectangle {
                            width: 1
                            height: 24
                            color: borderColor
                        }

                        CheckBox {
                            id: gridCheck
                            text: "Grid"
                            checked: true
                            onCheckedChanged: graphCanvas.showGrid = checked
                            contentItem: Text {
                                text: parent.text
                                color: textLight
                                font.pixelSize: 11
                                leftPadding: parent.indicator.width + 4
                            }
                            indicator: Rectangle {
                                implicitWidth: 16
                                implicitHeight: 16
                                x: parent.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 3
                                color: bgLight
                                border.color: parent.checked ? accentBlue : borderColor

                                Rectangle {
                                    width: 10
                                    height: 10
                                    x: 3
                                    y: 3
                                    radius: 2
                                    color: accentBlue
                                    visible: parent.parent.checked
                                }
                            }
                        }

                        CheckBox {
                            id: legendCheck
                            text: "Legend"
                            checked: true
                            onCheckedChanged: graphCanvas.showLegend = checked
                            contentItem: Text {
                                text: parent.text
                                color: textLight
                                font.pixelSize: 11
                                leftPadding: parent.indicator.width + 4
                            }
                            indicator: Rectangle {
                                implicitWidth: 16
                                implicitHeight: 16
                                x: parent.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 3
                                color: bgLight
                                border.color: parent.checked ? accentBlue : borderColor

                                Rectangle {
                                    width: 10
                                    height: 10
                                    x: 3
                                    y: 3
                                    radius: 2
                                    color: accentBlue
                                    visible: parent.parent.checked
                                }
                            }
                        }

                        Rectangle {
                            width: 1
                            height: 24
                            color: borderColor
                        }

                        ToolButton {
                            id: exportButton
                            ToolTip.text: "Export Graph"
                            ToolTip.visible: hovered
                            onClicked: exportMenu.open()
                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 3
                            }
                            contentItem: Text {
                                text: "Export"
                                color: accentPink
                                font.pixelSize: 11
                                font.bold: true
                            }

                            Menu {
                                id: exportMenu
                                y: exportButton.height

                                MenuItem {
                                    text: "Export as PNG"
                                    onTriggered: {
                                        exportDialog.nameFilters = ["PNG files (*.png)"]
                                        exportDialog.selectedNameFilter.index = 0
                                        exportDialog.currentExportType = "png"
                                        exportDialog.open()
                                    }
                                }
                                MenuItem {
                                    text: "Export as SVG"
                                    onTriggered: {
                                        exportDialog.nameFilters = ["SVG files (*.svg)"]
                                        exportDialog.selectedNameFilter.index = 0
                                        exportDialog.currentExportType = "svg"
                                        exportDialog.open()
                                    }
                                }
                                MenuItem {
                                    text: "Export as PDF"
                                    onTriggered: {
                                        exportDialog.nameFilters = ["PDF files (*.pdf)"]
                                        exportDialog.selectedNameFilter.index = 0
                                        exportDialog.currentExportType = "pdf"
                                        exportDialog.open()
                                    }
                                }
                                MenuSeparator {}
                                MenuItem {
                                    text: "Export Data as CSV"
                                    onTriggered: {
                                        exportDialog.nameFilters = ["CSV files (*.csv)"]
                                        exportDialog.selectedNameFilter.index = 0
                                        exportDialog.currentExportType = "csv"
                                        exportDialog.open()
                                    }
                                }
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // Cursor position display
                        Text {
                            id: cursorDisplay
                            text: "X: ---, Y: ---"
                            color: textMuted
                            font.pixelSize: 10
                            font.family: monoFont
                        }
                    }

                    // Graph canvas
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: bgDark

                        GraphCanvas {
                            id: graphCanvas
                            anchors.fill: parent
                            anchors.margins: 2

                            showGrid: true
                            showLegend: true

                            onCursorMoved: function(x, y) {
                                cursorDisplay.text = "X: " + x.toFixed(4) + ", Y: " + y.toExponential(3)
                            }

                            onCurveSelected: function(curveId) {
                                selectedCurveId = curveId
                                // Update curves list selection
                                curvesList.currentIndex = getCurveIndex(curveId)
                            }

                            onCurveProcessed: function(originalId, operation, newId) {
                                root.curveProcessed(originalId, operation, newId)
                                updateCurvesList()
                            }
                        }
                    }

                    // Math operations bar
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        Layout.margins: 4
                        spacing: 4

                        Label {
                            text: "Operations:"
                            color: textMuted
                            font.pixelSize: 11
                        }

                        Button {
                            text: "Derivative"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "derivative", {order: 1})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentBlue : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentBlue : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "Smooth"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "smooth", {method: "savgol", window: 11})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentBlue : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentBlue : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "Integrate"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "integrate", {})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentBlue : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentBlue : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "FFT"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "fft", {})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentPink : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentPink : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "Normalize"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "normalize", {})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentPurple : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentPurple : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "Baseline"
                            enabled: graphCanvas.selectedCurveId >= 0
                            onClicked: graphCanvas.applyCurveOperation(graphCanvas.selectedCurveId, "baseline", {})
                            background: Rectangle {
                                color: parent.enabled ? (parent.hovered ? accentPurple : bgLight) : bgDark
                                radius: 3
                                border.color: parent.enabled ? accentPurple : borderColor
                            }
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // =============================================
            // Tab 1: Curves List
            // =============================================
            Item {
                id: curvesTab

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    Label {
                        text: "Curves (" + graphCanvas.curveCount + ")"
                        color: accentPink
                        font.pixelSize: 14
                        font.bold: true
                    }

                    ListView {
                        id: curvesList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: curvesModel
                        spacing: 4

                        delegate: Rectangle {
                            width: curvesList.width
                            height: 50
                            color: curvesList.currentIndex === index ? bgLight : bgMedium
                            radius: 4
                            border.color: curvesList.currentIndex === index ? accentBlue : "transparent"
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                // Color indicator
                                Rectangle {
                                    width: 20
                                    height: 20
                                    radius: 10
                                    color: model.color || accentBlue

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: colorDialog.open()
                                    }
                                }

                                // Visibility checkbox
                                CheckBox {
                                    checked: model.visible
                                    onCheckedChanged: {
                                        graphCanvas.updateCurveProperty(model.curveId, "visible", checked ? "true" : "false")
                                    }
                                    indicator: Rectangle {
                                        implicitWidth: 16
                                        implicitHeight: 16
                                        radius: 3
                                        color: bgLight
                                        border.color: parent.checked ? accentBlue : borderColor

                                        Text {
                                            anchors.centerIn: parent
                                            text: parent.parent.checked ? "V" : ""
                                            color: accentBlue
                                            font.pixelSize: 10
                                            font.bold: true
                                        }
                                    }
                                }

                                // Label
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        text: model.label
                                        color: textLight
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        text: model.pointCount + " points"
                                        color: textMuted
                                        font.pixelSize: 10
                                    }
                                }

                                // Delete button
                                ToolButton {
                                    text: "X"
                                    onClicked: {
                                        graphCanvas.removeCurve(model.curveId)
                                    }
                                    background: Rectangle {
                                        color: parent.hovered ? "#FF6B6B" : "transparent"
                                        radius: 3
                                    }
                                    contentItem: Text {
                                        text: parent.text
                                        color: parent.hovered ? textLight : textMuted
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                z: -1
                                onClicked: {
                                    curvesList.currentIndex = index
                                    graphCanvas.selectCurve(model.curveId)
                                }
                            }
                        }

                        ScrollBar.vertical: ScrollBar { active: true }
                    }

                    // Action buttons
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "Clear All"
                            onClicked: {
                                graphCanvas.clearCurves()
                            }
                            background: Rectangle {
                                color: parent.hovered ? "#FF6B6B" : bgLight
                                radius: 4
                                border.color: "#FF6B6B"
                            }
                            contentItem: Text {
                                text: parent.text
                                color: textLight
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // =============================================
            // Tab 2: Settings
            // =============================================
            Item {
                id: settingsTab

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 8
                    clip: true

                    ColumnLayout {
                        width: settingsTab.width - 16
                        spacing: 16

                        // Axis Labels
                        GroupBox {
                            title: "Axis Labels"
                            Layout.fillWidth: true

                            background: Rectangle {
                                color: bgMedium
                                radius: 4
                                border.color: borderColor
                            }

                            label: Label {
                                text: parent.title
                                color: accentPink
                                font.bold: true
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "X Label:"; color: textLight; Layout.preferredWidth: 80 }
                                    TextField {
                                        id: xLabelField
                                        Layout.fillWidth: true
                                        text: graphCanvas.xLabel
                                        onEditingFinished: graphCanvas.xLabel = text
                                        color: textLight
                                        background: Rectangle {
                                            color: bgDark
                                            border.color: parent.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Y Label:"; color: textLight; Layout.preferredWidth: 80 }
                                    TextField {
                                        id: yLabelField
                                        Layout.fillWidth: true
                                        text: graphCanvas.yLabel
                                        onEditingFinished: graphCanvas.yLabel = text
                                        color: textLight
                                        background: Rectangle {
                                            color: bgDark
                                            border.color: parent.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Title:"; color: textLight; Layout.preferredWidth: 80 }
                                    TextField {
                                        id: titleField
                                        Layout.fillWidth: true
                                        text: graphCanvas.title
                                        onEditingFinished: graphCanvas.title = text
                                        color: textLight
                                        background: Rectangle {
                                            color: bgDark
                                            border.color: parent.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }
                                    }
                                }
                            }
                        }

                        // Scale
                        GroupBox {
                            title: "Scale"
                            Layout.fillWidth: true

                            background: Rectangle {
                                color: bgMedium
                                radius: 4
                                border.color: borderColor
                            }

                            label: Label {
                                text: parent.title
                                color: accentPink
                                font.bold: true
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "X Scale:"; color: textLight; Layout.preferredWidth: 80 }
                                    ComboBox {
                                        id: xScaleCombo
                                        Layout.fillWidth: true
                                        model: ["linear", "log"]
                                        currentIndex: graphCanvas.xScale === "log" ? 1 : 0
                                        onCurrentTextChanged: graphCanvas.xScale = currentText

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: borderColor
                                            radius: 3
                                        }
                                        contentItem: Text {
                                            text: parent.displayText
                                            color: textLight
                                            font.pixelSize: 12
                                            leftPadding: 8
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Y Scale:"; color: textLight; Layout.preferredWidth: 80 }
                                    ComboBox {
                                        id: yScaleCombo
                                        Layout.fillWidth: true
                                        model: ["linear", "log"]
                                        currentIndex: graphCanvas.yScale === "log" ? 1 : 0
                                        onCurrentTextChanged: graphCanvas.yScale = currentText

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: borderColor
                                            radius: 3
                                        }
                                        contentItem: Text {
                                            text: parent.displayText
                                            color: textLight
                                            font.pixelSize: 12
                                            leftPadding: 8
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                    }
                                }

                                CheckBox {
                                    id: autoScaleCheck
                                    text: "Auto Scale"
                                    checked: graphCanvas.autoScale
                                    onCheckedChanged: graphCanvas.autoScale = checked
                                    contentItem: Text {
                                        text: parent.text
                                        color: textLight
                                        font.pixelSize: 12
                                        leftPadding: parent.indicator.width + 4
                                    }
                                    indicator: Rectangle {
                                        implicitWidth: 18
                                        implicitHeight: 18
                                        radius: 3
                                        color: bgLight
                                        border.color: parent.checked ? accentBlue : borderColor

                                        Rectangle {
                                            width: 10
                                            height: 10
                                            x: 4
                                            y: 4
                                            radius: 2
                                            color: accentBlue
                                            visible: parent.parent.checked
                                        }
                                    }
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
    }

    // Curves model
    ListModel {
        id: curvesModel
    }

    // Track selected curve
    property int selectedCurveId: -1

    // Helper functions
    function updateCurvesList() {
        curvesModel.clear()
        var curves = graphCanvas.getCurveList()
        for (var i = 0; i < curves.length; i++) {
            curvesModel.append({
                curveId: curves[i].id,
                label: curves[i].label,
                color: curves[i].color,
                visible: curves[i].visible,
                pointCount: curves[i].pointCount
            })
        }
    }

    function getCurveIndex(curveId) {
        for (var i = 0; i < curvesModel.count; i++) {
            if (curvesModel.get(i).curveId === curveId) {
                return i
            }
        }
        return -1
    }

    // Public API
    function addCurve(label, xData, yData, color) {
        // curvesChanged signal from graphCanvas.addCurve() triggers updateCurvesList() via Connections
        return graphCanvas.addCurve(label, xData, yData, color || "", 2.0)
    }

    function clearCurves() {
        // curvesChanged signal from graphCanvas.clearCurves() triggers updateCurvesList() via Connections
        graphCanvas.clearCurves()
    }

    function setLabels(xLabel, yLabel) {
        graphCanvas.setLabels(xLabel, yLabel)
    }

    // Export file dialog
    FileDialog {
        id: exportDialog
        title: "Export Graph"
        fileMode: FileDialog.SaveFile
        property string currentExportType: "png"

        onAccepted: {
            var filePath = selectedFile.toString()
            // Convert file:// URL to local path
            if (filePath.startsWith("file:///")) {
                filePath = filePath.substring(7)  // macOS/Linux: file:///path -> /path
            } else if (filePath.startsWith("file://")) {
                filePath = filePath.substring(7)
            }

            var success = false
            if (currentExportType === "png") {
                success = graphCanvas.exportToPNG(filePath)
            } else if (currentExportType === "svg") {
                success = graphCanvas.exportToSVG(filePath)
            } else if (currentExportType === "pdf") {
                success = graphCanvas.exportToPDF(filePath)
            } else if (currentExportType === "csv") {
                success = graphCanvas.exportToCSV(filePath)
            }

            if (success) {
                console.log("Graph exported successfully to: " + filePath)
            } else {
                console.warn("Graph export failed")
            }
        }
    }

    // Populate graph when curves property is set (e.g. from WindowManager)
    onCurvesChanged: {
        if (curves && curves.length > 0) {
            graphCanvas.clearCurves()
            for (var i = 0; i < curves.length; i++) {
                var c = curves[i]
                if (c.x && c.y && c.x.length > 0 && c.y.length > 0) {
                    graphCanvas.addCurve(
                        c.label || ("Curve " + (i + 1)),
                        c.x,
                        c.y,
                        c.color || "",
                        2.0
                    )
                }
            }
            // curvesChanged signal handles updateCurvesList() via Connections
        }
    }

    // Apply axis labels when set
    onXLabelChanged: {
        if (xLabel) graphCanvas.xLabel = xLabel
    }
    onYLabelChanged: {
        if (yLabel) graphCanvas.yLabel = yLabel
    }
    onGraphTitleChanged: {
        if (graphTitle) graphCanvas.title = graphTitle
    }

    // Cleanup matplotlib resources when destroyed to prevent memory leaks
    Component.onDestruction: {
        if (graphCanvas) graphCanvas.cleanup()
    }

    // Initialize
    Component.onCompleted: {
        console.log("GraphWindowContent created, curves:", curves ? curves.length : 0)
        // Apply initial properties if already set
        if (xLabel) graphCanvas.xLabel = xLabel
        if (yLabel) graphCanvas.yLabel = yLabel
        if (graphTitle) graphCanvas.title = graphTitle
        // Apply initial curves if already set (may have been set before component completed)
        if (curves && curves.length > 0) {
            for (var i = 0; i < curves.length; i++) {
                var c = curves[i]
                if (c.x && c.y && c.x.length > 0 && c.y.length > 0) {
                    graphCanvas.addCurve(
                        c.label || ("Curve " + (i + 1)),
                        c.x, c.y,
                        c.color || "", 2.0
                    )
                }
            }
            // curvesChanged signal handles updateCurvesList() via Connections
        }
    }

    // Update curves list when curves are added/removed
    // Note: curvesChanged only fires on add/remove, NOT on property changes (like visibility),
    // to avoid rebuilding the entire ListView on every checkbox toggle.
    Connections {
        target: graphCanvas
        function onCurvesChanged() {
            updateCurvesList()
        }
    }
}
