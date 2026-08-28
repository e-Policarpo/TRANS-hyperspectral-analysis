/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import Qt.labs.platform 1.1 as Platform
import TransQML 1.0
import "../components"   // the Theme singleton

// MapViewerPanel - Dockable map viewer with controls
// Provides colormap selection, color scale adjustment, statistics, and export
// Implements non-destructive editing with save-on-close

Rectangle {
    id: mapViewerPanel

    // Required properties
    property string mapId: ""
    property string mapName: "Untitled"
    property string sourcePath: ""  // Original file path
    property var mapData: null      // Original unmodified data (numpy array reference)

    // Session state - tracks modifications without changing original
    property var sessionState: ({
        colormap: "viridis",
        colormapInverted: false,
        vmin: 0.0,
        vmax: 1.0,
        autoScale: true,
        // Processing history (for undo)
        processingHistory: [],
        // Current modified data (if any processing applied)
        modifiedData: null,
        hasUnsavedChanges: false
    })

    // Signals
    signal closeRequested()
    signal saveRequested(string path)
    signal exportRequested(string format)
    signal mapClicked(int row, int col, real value)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor
    property color accentMagenta: (mainWin && mainWin.accentMagenta !== undefined) ? mainWin.accentMagenta : Theme.accentMagenta
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    color: bgMedium

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header with title and close button
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: bgDarker

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 4
                spacing: 8

                // Unsaved changes indicator
                Rectangle {
                    visible: sessionState.hasUnsavedChanges
                    width: 8
                    height: 8
                    radius: 4
                    color: accentPink
                }

                Label {
                    text: mapName + (sessionState.hasUnsavedChanges ? " *" : "")
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                    elide: Text.ElideMiddle
                    Layout.fillWidth: true
                }

                // Save button
                Button {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 24
                    visible: sessionState.hasUnsavedChanges

                    background: Rectangle {
                        color: parent.hovered ? bgLight : "transparent"
                        radius: 3
                    }

                    contentItem: Text {
                        text: "\u2193"  // Down arrow (save)
                        color: accentBlue
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: saveDialog.open()

                    ToolTip.visible: hovered
                    ToolTip.text: "Save changes"
                }

                // Close button
                Button {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 24

                    background: Rectangle {
                        color: parent.hovered ? accentMagenta : "transparent"
                        radius: 3
                    }

                    contentItem: Text {
                        text: "\u2715"
                        color: parent.hovered ? textLight : textMuted
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: {
                        if (sessionState.hasUnsavedChanges) {
                            unsavedChangesDialog.open()
                        } else {
                            closeRequested()
                        }
                    }
                }
            }
        }

        // Main content: Map canvas + Controls
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            // Map canvas area
            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 300
                color: bgDark

                MapCanvas {
                    id: mapCanvas
                    anchors.fill: parent
                    anchors.margins: 4

                    // Chrome only; the colormap inside is data.
                    backgroundColor: mapViewerPanel.bgDark
                    foregroundColor: mapViewerPanel.textMuted
                    // borderColor, not bgLight: this draws the axes frame and the
                    // gridlines, and bgLight-on-bgDark measures 1.12:1 to 1.54:1 on
                    // all 22 schemes — the frame came out fainter than either
                    // candidate and the painted gridline at 1.02–1.08:1, i.e. no
                    // visible box on any scheme. borderColor wins on 21 of the 22.
                    gridColor: mapViewerPanel.borderColor

                    onPointClicked: function(x, y, row, col, value) {
                        mapViewerPanel.mapClicked(row, col, value)
                        coordLabel.text = mapViewerPanel.formatCursor(row, col, value)
                    }

                    onCursorMoved: function(x, y, row, col, value) {
                        coordLabel.text = mapViewerPanel.formatCursor(row, col, value)
                    }
                }

                // Coordinate display overlay
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.margins: 8
                    height: 22
                    width: coordLabel.implicitWidth + 16
                    color: Qt.rgba(0, 0, 0, 0.7)
                    radius: 4

                    Label {
                        id: coordLabel
                        anchors.centerIn: parent
                        text: "(-, -) = -"
                        font.pixelSize: 11
                        font.family: monoFont
                        color: textLight
                    }
                }
            }

            // Right panel: Controls
            Rectangle {
                SplitView.preferredWidth: 220
                SplitView.minimumWidth: 180
                SplitView.maximumWidth: 300
                color: bgMedium

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 1
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 0

                        // Colormap Section
                        CollapsibleSection {
                            title: "Colormap"
                            Layout.fillWidth: true
                            expanded: true

                            ColumnLayout {
                                width: parent.width
                                spacing: 8

                                ComboBox {
                                    id: colormapCombo
                                    Layout.fillWidth: true
                                    model: [
                                        "viridis", "plasma", "inferno", "magma", "cividis",
                                        "hot", "cool", "coolwarm", "RdYlBu", "RdBu",
                                        "Spectral", "seismic", "twilight", "turbo",
                                        "gray", "bone", "copper", "pink"
                                    ]
                                    currentIndex: model.indexOf(sessionState.colormap)

                                    background: Rectangle {
                                        color: bgDark
                                        border.color: borderColor
                                        radius: 4
                                    }

                                    contentItem: Text {
                                        text: colormapCombo.displayText
                                        color: textLight
                                        font.pixelSize: 11
                                        verticalAlignment: Text.AlignVCenter
                                        leftPadding: 8
                                    }

                                    onCurrentTextChanged: {
                                        sessionState.colormap = currentText
                                        applyColormap()
                                    }
                                }

                                CheckBox {
                                    id: invertCheck
                                    text: "Invert colormap"
                                    checked: sessionState.colormapInverted
                                    font.pixelSize: 11

                                    indicator: Rectangle {
                                        implicitWidth: 16
                                        implicitHeight: 16
                                        x: invertCheck.leftPadding
                                        y: parent.height / 2 - height / 2
                                        radius: 3
                                        border.color: borderColor
                                        color: invertCheck.checked ? accentBlue : bgDark

                                        Text {
                                            anchors.centerIn: parent
                                            text: "\u2713"
                                            color: textLight
                                            font.pixelSize: 12
                                            visible: invertCheck.checked
                                        }
                                    }

                                    contentItem: Text {
                                        text: invertCheck.text
                                        font: invertCheck.font
                                        color: textLight
                                        leftPadding: invertCheck.indicator.width + 8
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    onCheckedChanged: {
                                        sessionState.colormapInverted = checked
                                        applyColormap()
                                    }
                                }
                            }
                        }

                        // Color Scale Section
                        CollapsibleSection {
                            title: "Color Scale"
                            Layout.fillWidth: true
                            expanded: true

                            ColumnLayout {
                                width: parent.width
                                spacing: 8

                                // Auto scale checkbox
                                CheckBox {
                                    id: autoScaleCheck
                                    text: "Auto scale"
                                    checked: sessionState.autoScale
                                    font.pixelSize: 11

                                    indicator: Rectangle {
                                        implicitWidth: 16
                                        implicitHeight: 16
                                        x: autoScaleCheck.leftPadding
                                        y: parent.height / 2 - height / 2
                                        radius: 3
                                        border.color: borderColor
                                        color: autoScaleCheck.checked ? accentBlue : bgDark

                                        Text {
                                            anchors.centerIn: parent
                                            text: "\u2713"
                                            color: textLight
                                            font.pixelSize: 12
                                            visible: autoScaleCheck.checked
                                        }
                                    }

                                    contentItem: Text {
                                        text: autoScaleCheck.text
                                        font: autoScaleCheck.font
                                        color: textLight
                                        leftPadding: autoScaleCheck.indicator.width + 8
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    onCheckedChanged: {
                                        sessionState.autoScale = checked
                                        if (checked) autoScale()
                                    }
                                }

                                // Min value
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        text: "Min:"
                                        font.pixelSize: 11
                                        color: textMuted
                                        Layout.preferredWidth: 35
                                    }

                                    TextField {
                                        id: vminField
                                        Layout.fillWidth: true
                                        text: sessionState.vmin.toFixed(4)
                                        font.pixelSize: 11
                                        enabled: !autoScaleCheck.checked

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: borderColor
                                            radius: 3
                                        }

                                        color: textLight
                                        selectByMouse: true

                                        onEditingFinished: {
                                            var val = parseFloat(text)
                                            if (!isNaN(val)) {
                                                sessionState.vmin = val
                                                applyColorScale()
                                            }
                                        }
                                    }
                                }

                                // Max value
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        text: "Max:"
                                        font.pixelSize: 11
                                        color: textMuted
                                        Layout.preferredWidth: 35
                                    }

                                    TextField {
                                        id: vmaxField
                                        Layout.fillWidth: true
                                        text: sessionState.vmax.toFixed(4)
                                        font.pixelSize: 11
                                        enabled: !autoScaleCheck.checked

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: borderColor
                                            radius: 3
                                        }

                                        color: textLight
                                        selectByMouse: true

                                        onEditingFinished: {
                                            var val = parseFloat(text)
                                            if (!isNaN(val)) {
                                                sessionState.vmax = val
                                                applyColorScale()
                                            }
                                        }
                                    }
                                }

                                Button {
                                    text: "Reset to Data Range"
                                    Layout.fillWidth: true
                                    font.pixelSize: 11

                                    background: Rectangle {
                                        color: parent.hovered ? bgLight : bgDark
                                        border.color: borderColor
                                        radius: 4
                                    }

                                    contentItem: Text {
                                        text: parent.text
                                        font: parent.font
                                        color: textLight
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    onClicked: autoScale()
                                }
                            }
                        }

                        // Statistics Section
                        CollapsibleSection {
                            title: "Statistics"
                            Layout.fillWidth: true
                            expanded: true

                            GridLayout {
                                width: parent.width
                                columns: 2
                                columnSpacing: 8
                                rowSpacing: 4

                                Label { text: "Min:"; font.pixelSize: 10; color: textMuted }
                                Label { id: statMin; text: "-"; font.pixelSize: 10; color: textLight; font.family: monoFont }

                                Label { text: "Max:"; font.pixelSize: 10; color: textMuted }
                                Label { id: statMax; text: "-"; font.pixelSize: 10; color: textLight; font.family: monoFont }

                                Label { text: "Mean:"; font.pixelSize: 10; color: textMuted }
                                Label { id: statMean; text: "-"; font.pixelSize: 10; color: accentBlue; font.family: monoFont }

                                Label { text: "Std:"; font.pixelSize: 10; color: textMuted }
                                Label { id: statStd; text: "-"; font.pixelSize: 10; color: textLight; font.family: monoFont }

                                Label { text: "Shape:"; font.pixelSize: 10; color: textMuted }
                                Label { id: statShape; text: "-"; font.pixelSize: 10; color: textLight; font.family: monoFont }
                            }
                        }

                        // Export Section
                        CollapsibleSection {
                            title: "Export"
                            Layout.fillWidth: true
                            expanded: false

                            ColumnLayout {
                                width: parent.width
                                spacing: 6

                                Button {
                                    text: "Export TIFF"
                                    Layout.fillWidth: true
                                    font.pixelSize: 11

                                    background: Rectangle {
                                        color: parent.hovered ? bgLight : bgDark
                                        border.color: borderColor
                                        radius: 4
                                    }

                                    contentItem: Text {
                                        text: parent.text
                                        font: parent.font
                                        color: textLight
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    onClicked: exportTiff()
                                }

                                Button {
                                    text: "Export CSV"
                                    Layout.fillWidth: true
                                    font.pixelSize: 11

                                    background: Rectangle {
                                        color: parent.hovered ? bgLight : bgDark
                                        border.color: borderColor
                                        radius: 4
                                    }

                                    contentItem: Text {
                                        text: parent.text
                                        font: parent.font
                                        color: textLight
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    onClicked: exportCsv()
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
    }

    // Collapsible section component
    component CollapsibleSection: Rectangle {
        property string title: "Section"
        property bool expanded: true
        default property alias content: contentColumn.data

        color: bgDark
        Layout.fillWidth: true
        implicitHeight: headerRow.height + (expanded ? contentColumn.height + 8 : 0)

        Behavior on implicitHeight {
            NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Header
            Rectangle {
                id: headerRow
                Layout.fillWidth: true
                height: 28
                color: "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 4

                    Label {
                        text: expanded ? "\u25BC" : "\u25B6"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    Label {
                        text: title
                        font.pixelSize: 11
                        font.bold: true
                        color: textLight
                        Layout.fillWidth: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: expanded = !expanded
                    cursorShape: Qt.PointingHandCursor
                }
            }

            // Content
            ColumnLayout {
                id: contentColumn
                visible: expanded
                Layout.fillWidth: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
                Layout.bottomMargin: 8
                spacing: 6
            }
        }
    }

    // Dialogs
    Platform.FileDialog {
        id: saveDialog
        title: "Save Map"
        nameFilters: ["TIFF Files (*.tif *.tiff)", "NumPy Files (*.npy)"]
        fileMode: Platform.FileDialog.SaveFile
        currentFile: sourcePath ? "file://" + sourcePath : ""

        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) path = path.substring(7)
            saveMap(path)
        }
    }

    // PNG export removed - only TIFF and CSV supported for maps

    Platform.FileDialog {
        id: exportTiffDialog
        title: "Export as TIFF"
        nameFilters: ["TIFF Files (*.tif *.tiff)"]
        fileMode: Platform.FileDialog.SaveFile

        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) path = path.substring(7)
            mapCanvas.exportImage(path, "tiff")
        }
    }

    Platform.FileDialog {
        id: exportCsvDialog
        title: "Export as CSV"
        nameFilters: ["CSV Files (*.csv)"]
        fileMode: Platform.FileDialog.SaveFile

        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) path = path.substring(7)
            mapCanvas.exportCsv(path)
        }
    }

    // Unsaved changes dialog
    Dialog {
        id: unsavedChangesDialog
        title: "Unsaved Changes"
        modal: true
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel

        background: Rectangle {
            color: bgMedium
            border.color: accentPink
            border.width: 1
            radius: 5
        }

        contentItem: ColumnLayout {
            spacing: 15

            Label {
                text: "You have unsaved changes to \"" + mapName + "\"."
                color: textLight
                font.pixelSize: 13
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Label {
                text: "Do you want to save before closing?"
                color: textMuted
                font.pixelSize: 12
            }
        }

        onAccepted: {
            saveDialog.open()
        }

        onDiscarded: {
            sessionState.hasUnsavedChanges = false
            closeRequested()
        }
    }

    // Functions
    // Cursor read-out. Physical coordinates when the map carries a scale —
    // a position on the sample means something, a pixel index does not — with
    // the pixel indices kept alongside so a point can still be identified in
    // the data. Falls back to indices for an uncalibrated map rather than
    // implying a scale that is not there.
    function formatCursor(row, col, value) {
        var phys = mapCanvas.physicalAt(row, col)
        var head = "(" + row + ", " + col + ")"
        if (phys && phys.valid) {
            // Each axis with its own unit: a kymograph is distance across and
            // bias up, not two lengths.
            head = formatAxis(phys.x, phys.x_unit) + ", " +
                   formatAxis(phys.y, phys.y_unit) +
                   "  [" + row + ", " + col + "]"
        }
        return head + " = " + formatValue(value)
    }

    // One axis value. Lengths are shown in the unit that keeps the number
    // readable (nm for a scan, µm for a large window) rather than 3.05e-07 m;
    // anything else (a bias axis, say) keeps its own unit.
    function formatAxis(value, unit) {
        if (unit === "V" || unit === "mV" || unit === "eV" || unit === "meV")
            return value.toFixed(4) + " " + unit
        if (unit !== "m")
            return value.toFixed(2) + (unit ? " " + unit : "")
        var abs = Math.abs(value)
        if (abs >= 1e-3) return (value * 1e3).toFixed(3) + " mm"
        if (abs >= 1e-6) return (value * 1e6).toFixed(3) + " µm"
        if (abs >= 1e-9) return (value * 1e9).toFixed(2) + " nm"
        if (abs === 0) return "0 nm"
        return (value * 1e12).toFixed(1) + " pm"
    }

    function formatValue(value) {
        var abs = Math.abs(value)
        if (abs !== 0 && (abs < 1e-3 || abs >= 1e5))
            return value.toExponential(3)
        return value.toFixed(6)
    }

    function loadMapData(data, name, path) {
        mapName = name || "Untitled"
        sourcePath = path || ""
        mapData = data

        // Set the data on the canvas
        mapCanvas.setMapData(data)

        // Update statistics
        updateStatistics()

        // Auto scale
        autoScale()
    }

    function applyColormap() {
        var cmap = sessionState.colormap
        if (sessionState.colormapInverted) {
            cmap += "_r"
        }
        mapCanvas.setColormap(cmap)
    }

    function applyColorScale() {
        mapCanvas.setColorLimits(sessionState.vmin, sessionState.vmax)
        vminField.text = sessionState.vmin.toFixed(4)
        vmaxField.text = sessionState.vmax.toFixed(4)
    }

    function autoScale() {
        var stats = mapCanvas.getStatistics()
        if (stats && stats.min !== undefined) {
            sessionState.vmin = stats.min
            sessionState.vmax = stats.max
            applyColorScale()
        }
    }

    function updateStatistics() {
        var stats = mapCanvas.getStatistics()
        if (stats) {
            statMin.text = stats.min !== undefined ? stats.min.toFixed(4) : "-"
            statMax.text = stats.max !== undefined ? stats.max.toFixed(4) : "-"
            statMean.text = stats.mean !== undefined ? stats.mean.toFixed(4) : "-"
            statStd.text = stats.std !== undefined ? stats.std.toFixed(4) : "-"
            statShape.text = stats.rows + " x " + stats.cols
        }
    }

    function markModified() {
        sessionState.hasUnsavedChanges = true
    }

    function saveMap(path) {
        // Save the current (possibly modified) data to the specified path
        if (mapCanvas.saveMapData(path)) {
            sessionState.hasUnsavedChanges = false
            sourcePath = path
        }
    }

    function exportTiff() {
        exportTiffDialog.open()
    }

    function exportCsv() {
        exportCsvDialog.open()
    }

    // Cleanup resources before destruction
    Component.onDestruction: {
        if (sessionState.hasUnsavedChanges) {
            console.log("Warning: Map", mapName, "has unsaved changes")
        }
        if (mapCanvas) mapCanvas.cleanup()
    }
}
