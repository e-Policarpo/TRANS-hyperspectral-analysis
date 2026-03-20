/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * HyperspectralControlPanel - Core TRANS_v3 workflow: discretize + select + export
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: March 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt.labs.platform 1.1 as Platform

Item {
    id: root

    // Required bindings from parent
    property var mapBackend: null
    property var appBackend: null
    property var mapCanvas: null

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    // Signals
    signal discretizeFullRequested(string datasetName, int gridX, int gridY, bool ignoreEmpty)
    signal discretizeSelectionRequested(string datasetName, int gridX, int gridY, bool ignoreEmpty, var selectedBlocks)
    signal exportSelectionRequested(string datasetName)
    signal openGraphRequested()
    signal openTableRequested()

    // State
    property int gridCols: targetColsSpin.value
    property int gridRows: targetRowsSpin.value
    property int blockW: mapBackend && mapBackend.mapCols > 0 ? Math.ceil(mapBackend.mapCols / gridCols) : 1
    property int blockH: mapBackend && mapBackend.mapRows > 0 ? Math.ceil(mapBackend.mapRows / gridRows) : 1
    property int selectedCount: 0
    property int totalBlocks: gridCols * gridRows

    Rectangle {
        anchors.fill: parent
        color: bgDark

        Flickable {
            anchors.fill: parent
            contentHeight: panelLayout.implicitHeight + 16
            clip: true
            boundsMovement: Flickable.StopAtBounds

            ColumnLayout {
                id: panelLayout
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 8
                spacing: 4

                // ========== Section 1: Discretization ==========
                Label {
                    text: "Discretization"
                    font.pixelSize: 12
                    font.bold: true
                    color: accentPink
                    Layout.topMargin: 8
                }

                // Target grid size
                GridLayout {
                    columns: 2
                    columnSpacing: 6
                    rowSpacing: 4
                    Layout.fillWidth: true

                    Label { text: "Target Cols:"; font.pixelSize: 10; color: textMuted }
                    SpinBox {
                        id: targetColsSpin
                        from: 1; to: 999; value: 10
                        Layout.fillWidth: true
                        font.pixelSize: 10
                        editable: true

                        background: Rectangle {
                            color: bgMedium; border.color: borderColor; radius: 3
                        }

                        contentItem: TextInput {
                            text: targetColsSpin.textFromValue(targetColsSpin.value, targetColsSpin.locale)
                            font: targetColsSpin.font
                            color: textLight
                            horizontalAlignment: Qt.AlignHCenter
                            verticalAlignment: Qt.AlignVCenter
                            readOnly: !targetColsSpin.editable
                            validator: targetColsSpin.validator
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                    }

                    Label { text: "Target Rows:"; font.pixelSize: 10; color: textMuted }
                    SpinBox {
                        id: targetRowsSpin
                        from: 1; to: 999; value: 10
                        Layout.fillWidth: true
                        font.pixelSize: 10
                        editable: true

                        background: Rectangle {
                            color: bgMedium; border.color: borderColor; radius: 3
                        }

                        contentItem: TextInput {
                            text: targetRowsSpin.textFromValue(targetRowsSpin.value, targetRowsSpin.locale)
                            font: targetRowsSpin.font
                            color: textLight
                            horizontalAlignment: Qt.AlignHCenter
                            verticalAlignment: Qt.AlignVCenter
                            readOnly: !targetRowsSpin.editable
                            validator: targetRowsSpin.validator
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                        }
                    }
                }

                // Block size info
                Label {
                    text: "Block Size: " + blockW + " x " + blockH +
                          "   Grid: " + gridCols + " x " + gridRows
                    font.pixelSize: 9
                    color: textMuted
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }

                // Apply Grid button
                Button {
                    text: "Apply Grid"
                    Layout.fillWidth: true
                    font.pixelSize: 11

                    background: Rectangle {
                        color: parent.hovered ? accentPink : bgMedium
                        border.color: accentPink
                        border.width: 1
                        radius: 4
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: parent.hovered ? bgDark : textLight
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        if (mapBackend && mapCanvas) {
                            mapBackend.setDiscretizationGrid(blockW, blockH)
                            mapCanvas.setGridBlockSize(blockW, blockH)
                        }
                    }
                }

                // Show grid checkbox
                CheckBox {
                    id: showGridCheck
                    text: "Show Grid Overlay"
                    checked: true
                    font.pixelSize: 10

                    indicator: Rectangle {
                        implicitWidth: 12; implicitHeight: 12
                        x: showGridCheck.leftPadding
                        y: parent.height / 2 - height / 2
                        radius: 2
                        border.color: borderColor
                        color: showGridCheck.checked ? accentBlue : bgDark

                        Text {
                            anchors.centerIn: parent
                            text: "\u2713"; color: textLight; font.pixelSize: 8
                            visible: showGridCheck.checked
                        }
                    }

                    contentItem: Text {
                        text: showGridCheck.text; font: showGridCheck.font
                        color: textLight
                        leftPadding: showGridCheck.indicator.width + 4
                        verticalAlignment: Text.AlignVCenter
                    }

                    onCheckedChanged: {
                        if (mapCanvas) mapCanvas.setGridOverlayVisible(checked)
                    }
                }

                // Separator
                Rectangle { Layout.fillWidth: true; height: 1; color: borderColor; Layout.topMargin: 4 }

                // ========== Section 2: Block Selection ==========
                Label {
                    text: "Block Selection"
                    font.pixelSize: 12
                    font.bold: true
                    color: accentPink
                    Layout.topMargin: 4
                }

                Label {
                    text: selectedCount + " / " + totalBlocks + " blocks selected"
                    font.pixelSize: 10
                    color: textMuted
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Button {
                        text: "All"
                        Layout.fillWidth: true
                        font.pixelSize: 10

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor; radius: 3
                        }
                        contentItem: Text {
                            text: parent.text; font: parent.font; color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        onClicked: {
                            if (mapBackend) mapBackend.selectAllBlocks()
                        }
                    }

                    Button {
                        text: "Clear"
                        Layout.fillWidth: true
                        font.pixelSize: 10

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor; radius: 3
                        }
                        contentItem: Text {
                            text: parent.text; font: parent.font; color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        onClicked: {
                            if (mapBackend) mapBackend.clearSelection()
                        }
                    }

                    Button {
                        text: "Invert"
                        Layout.fillWidth: true
                        font.pixelSize: 10

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor; radius: 3
                        }
                        contentItem: Text {
                            text: parent.text; font: parent.font; color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        onClicked: {
                            if (mapBackend) mapBackend.invertSelection()
                        }
                    }
                }

                // Separator
                Rectangle { Layout.fillWidth: true; height: 1; color: borderColor; Layout.topMargin: 4 }

                // ========== Section 3: Export / Discretize ==========
                Label {
                    text: "Export"
                    font.pixelSize: 12
                    font.bold: true
                    color: accentPink
                    Layout.topMargin: 4
                }

                // Dataset selector
                Label { text: "Dataset:"; font.pixelSize: 10; color: textMuted }
                ComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: mapBackend ? mapBackend.linkedDatasetNames : []
                    font.pixelSize: 10

                    background: Rectangle {
                        color: bgMedium; border.color: borderColor; radius: 3
                    }

                    contentItem: Text {
                        text: datasetCombo.displayText
                        font: datasetCombo.font
                        color: textLight
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 6
                        elide: Text.ElideRight
                    }
                }

                // Ignore empty blocks
                CheckBox {
                    id: ignoreEmptyCheck
                    text: "Ignore empty blocks"
                    checked: true
                    font.pixelSize: 10

                    indicator: Rectangle {
                        implicitWidth: 12; implicitHeight: 12
                        x: ignoreEmptyCheck.leftPadding
                        y: parent.height / 2 - height / 2
                        radius: 2
                        border.color: borderColor
                        color: ignoreEmptyCheck.checked ? accentBlue : bgDark

                        Text {
                            anchors.centerIn: parent
                            text: "\u2713"; color: textLight; font.pixelSize: 8
                            visible: ignoreEmptyCheck.checked
                        }
                    }

                    contentItem: Text {
                        text: ignoreEmptyCheck.text; font: ignoreEmptyCheck.font
                        color: textLight
                        leftPadding: ignoreEmptyCheck.indicator.width + 4
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Button {
                    text: "Discretize Full Dataset"
                    Layout.fillWidth: true
                    font.pixelSize: 11
                    enabled: datasetCombo.currentText !== ""

                    background: Rectangle {
                        color: parent.enabled ? (parent.hovered ? accentBlue : bgMedium) : Qt.darker(bgMedium, 1.3)
                        border.color: parent.enabled ? accentBlue : borderColor
                        border.width: 1; radius: 4
                    }

                    contentItem: Text {
                        text: parent.text; font: parent.font
                        color: parent.enabled ? (parent.hovered ? bgDark : textLight) : textMuted
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        if (appBackend && datasetCombo.currentText) {
                            appBackend.spatialAverageWithSelection(
                                datasetCombo.currentText,
                                gridCols, gridRows,
                                ignoreEmptyCheck.checked, [])
                        }
                    }
                }

                Button {
                    text: "Discretize Selection"
                    Layout.fillWidth: true
                    font.pixelSize: 11
                    enabled: datasetCombo.currentText !== "" && selectedCount > 0

                    background: Rectangle {
                        color: parent.enabled ? (parent.hovered ? accentBlue : bgMedium) : Qt.darker(bgMedium, 1.3)
                        border.color: parent.enabled ? accentBlue : borderColor
                        border.width: 1; radius: 4
                    }

                    contentItem: Text {
                        text: parent.text; font: parent.font
                        color: parent.enabled ? (parent.hovered ? bgDark : textLight) : textMuted
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        if (appBackend && mapBackend && datasetCombo.currentText) {
                            var blocks = mapBackend.getSelectedBlocks()
                            appBackend.spatialAverageWithSelection(
                                datasetCombo.currentText,
                                gridCols, gridRows,
                                ignoreEmptyCheck.checked, blocks)
                        }
                    }
                }

                // Separator
                Rectangle { Layout.fillWidth: true; height: 1; color: borderColor; Layout.topMargin: 4 }

                // ========== Section 4: Embedded Views ==========
                Label {
                    text: "Views"
                    font.pixelSize: 12
                    font.bold: true
                    color: accentPink
                    Layout.topMargin: 4
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Button {
                        text: "Graph"
                        Layout.fillWidth: true
                        font.pixelSize: 10

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor; radius: 3
                        }
                        contentItem: Text {
                            text: parent.text; font: parent.font; color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        onClicked: root.openGraphRequested()
                    }

                    Button {
                        text: "Table"
                        Layout.fillWidth: true
                        font.pixelSize: 10

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor; radius: 3
                        }
                        contentItem: Text {
                            text: parent.text; font: parent.font; color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        onClicked: root.openTableRequested()
                    }
                }

                // Export buttons
                Button {
                    text: "Export TIFF"
                    Layout.fillWidth: true
                    font.pixelSize: 11

                    background: Rectangle {
                        color: parent.hovered ? bgLight : bgMedium
                        border.color: borderColor; radius: 4
                    }

                    contentItem: Text {
                        text: parent.text; font: parent.font; color: textLight
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: exportTiffDialog.open()
                }

                Button {
                    text: "Export CSV"
                    Layout.fillWidth: true
                    font.pixelSize: 11

                    background: Rectangle {
                        color: parent.hovered ? bgLight : bgMedium
                        border.color: borderColor; radius: 4
                    }

                    contentItem: Text {
                        text: parent.text; font: parent.font; color: textLight
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: exportCsvDialog.open()
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    // Update selected count when selection changes
    Connections {
        target: mapBackend
        function onSelectionChanged(count) {
            root.selectedCount = count
        }
    }

    // File dialogs
    Platform.FileDialog {
        id: exportTiffDialog
        title: "Export as TIFF"
        nameFilters: ["TIFF Files (*.tif *.tiff)"]
        fileMode: Platform.FileDialog.SaveFile
        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) path = path.substring(7)
            if (mapCanvas) mapCanvas.exportImage(path, "tiff")
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
            if (mapCanvas) mapCanvas.exportCsv(path)
        }
    }
}
