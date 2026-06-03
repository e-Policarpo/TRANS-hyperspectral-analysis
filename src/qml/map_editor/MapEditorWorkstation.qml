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

// Map Editor Workstation - Gwyddion-style map editing interface
// Implements TRANS_v3 interactive canvas with spatial-spectral reconstruction
// Maps are opened as docked tabs within the main window (no separate windows)
// Non-destructive editing with save-on-close dialog

Item {
    id: root

    // Expose the backend for external access
    property alias mapEditorBackend: mapBackend

    // Track open maps
    property var openMaps: []  // Array of {id, name, path, hasUnsavedChanges}
    property int activeMapIndex: -1

    // Signals
    signal spectrumRequested(int row, int col)
    signal blockSelectionChanged(int count)
    signal profileExportRequested(var profileData)
    signal mapClosed(string mapId)
    signal openSpectrumPlotRequested(string datasetName, var spectra, bool forceNewWindow)
    signal openMultiDatasetSpectraRequested(var datasetSpectraList, bool forceNewWindow)

    // Dataset list model for dropdown
    ListModel {
        id: datasetListModel
    }

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
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    // Backend instance
    MapEditorBackend {
        id: mapBackend

        onActiveChannelChanged: function(channelName) {
            // Update data browser
            dataBrowser.activeChannel = channelName
            // Update statistics
            var stats = mapBackend.getChannelStatistics(channelName)
            statsPanel.updateStats(stats, channelName, false, 0)
        }

        onSelectionChanged: function(count) {
            root.blockSelectionChanged(count)
        }

        onProcessingStarted: function(operation) {
            processingIndicator.visible = true
            statusLabel.text = "Processing: " + operation + "..."
        }

        onProcessingFinished: function(operation, success, message) {
            processingIndicator.visible = false
            statusLabel.text = success ? "Ready" : ("Error: " + message)
            if (success && mapBackend.activeChannelName) {
                var stats = mapBackend.getChannelStatistics(mapBackend.activeChannelName)
                statsPanel.updateStats(stats, mapBackend.activeChannelName, false, 0)
            }
        }

        onMapDataChanged: {
            dataBrowser.channelNames = mapBackend.channelNames
            dataBrowser.mapRows = mapBackend.mapRows
            dataBrowser.mapCols = mapBackend.mapCols
            dataBrowser.hasSpectralData = mapBackend.hasSpectralData
            dataBrowser.spectralPoints = mapBackend.spectralPoints
            // Auto-link datasets with matching spatial dimensions
            mapBackend.autoLinkMatchingDatasets(backend)
        }

        onOpenPlotWindowRequested: function(datasetName, spectra) {
            // Forward to Main.qml to open plot window (reuse existing window)
            root.openSpectrumPlotRequested(datasetName, spectra, false)
        }

        onChannelListChanged: {
            dataBrowser.channelNames = mapBackend.channelNames
        }

        onSpectralDataChanged: {
            dataBrowser.hasSpectralData = mapBackend.hasSpectralData
            dataBrowser.spectralPoints = mapBackend.spectralPoints
            pointInspector.setSpectrumAvailable(mapBackend.hasSpectralData)
        }
    }

    // Main layout
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Left: Tool Palette
        ToolPalette {
            id: toolPalette
            Layout.fillHeight: true

            onToolSelected: function(toolName) {
                mapCanvas.setTool(toolName)
            }

            onSelectAllRequested: mapBackend.selectAllBlocks()
            onClearSelectionRequested: mapBackend.clearSelection()
            onFilterRequested: function(filterType, params) {
                mapBackend.applyProcessing(filterType, params)
                // Mark map as modified
                if (activeMapIndex >= 0 && activeMapIndex < openMaps.length) {
                    markMapModified(activeMapIndex)
                }
            }
        }

        // Center: Main content area (Map tabs + Bottom panels)
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Top toolbar Row 1 - Map controls
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                color: bgMedium

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 8

                    // Channel selector
                    Label {
                        text: "Channel:"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    ComboBox {
                        id: channelCombo
                        Layout.preferredWidth: 120
                        model: mapBackend.channelNames
                        font.pixelSize: 10

                        background: Rectangle {
                            color: bgDark
                            border.color: borderColor
                            border.width: 1
                            radius: 3
                        }

                        contentItem: Text {
                            text: channelCombo.displayText
                            font: channelCombo.font
                            color: textLight
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: 6
                            elide: Text.ElideRight
                        }

                        onCurrentTextChanged: {
                            if (currentText) {
                                mapBackend.setActiveChannel(currentText)
                            }
                        }
                    }

                    // Separator
                    Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 6; Layout.bottomMargin: 6; color: borderColor }

                    // Colormap selector
                    Label {
                        text: "Colormap:"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    ComboBox {
                        id: colormapCombo
                        Layout.preferredWidth: 90
                        model: ["viridis", "plasma", "inferno", "magma", "cividis",
                                "hot", "cool", "coolwarm", "RdYlBu", "RdBu",
                                "gray", "bone", "copper", "terrain"]
                        currentIndex: 0
                        font.pixelSize: 10

                        background: Rectangle {
                            color: bgDark
                            border.color: borderColor
                            border.width: 1
                            radius: 3
                        }

                        contentItem: Text {
                            text: colormapCombo.displayText
                            font: colormapCombo.font
                            color: textLight
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: 6
                        }

                        onCurrentTextChanged: {
                            mapCanvas.setColormap(currentText)
                        }
                    }

                    // Invert colormap
                    CheckBox {
                        id: invertColormapCheck
                        text: "Inv"
                        font.pixelSize: 9

                        indicator: Rectangle {
                            implicitWidth: 12
                            implicitHeight: 12
                            x: invertColormapCheck.leftPadding
                            y: parent.height / 2 - height / 2
                            radius: 2
                            border.color: borderColor
                            color: invertColormapCheck.checked ? accentBlue : bgDark

                            Text {
                                anchors.centerIn: parent
                                text: "\u2713"
                                color: textLight
                                font.pixelSize: 8
                                visible: invertColormapCheck.checked
                            }
                        }

                        contentItem: Text {
                            text: invertColormapCheck.text
                            font: invertColormapCheck.font
                            color: textLight
                            leftPadding: invertColormapCheck.indicator.width + 2
                            verticalAlignment: Text.AlignVCenter
                        }

                        onCheckedChanged: {
                            var cmap = colormapCombo.currentText
                            if (checked) cmap += "_r"
                            mapCanvas.setColormap(cmap)
                        }
                    }

                    // Separator
                    Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 6; Layout.bottomMargin: 6; color: borderColor }

                    // Color scale controls
                    Label {
                        text: "Scale:"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    TextField {
                        id: vminField
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: 22
                        placeholderText: "Min"
                        font.pixelSize: 9

                        background: Rectangle {
                            color: bgDark
                            border.color: borderColor
                            radius: 2
                        }
                        color: textLight

                        onEditingFinished: applyColorScale()
                    }

                    TextField {
                        id: vmaxField
                        Layout.preferredWidth: 60
                        Layout.preferredHeight: 22
                        placeholderText: "Max"
                        font.pixelSize: 9

                        background: Rectangle {
                            color: bgDark
                            border.color: borderColor
                            radius: 2
                        }
                        color: textLight

                        onEditingFinished: applyColorScale()
                    }

                    Button {
                        text: "Auto"
                        font.pixelSize: 9
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 22

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgDark
                            border.color: borderColor
                            radius: 2
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

                    Item { Layout.fillWidth: true }

                    // Processing indicator
                    BusyIndicator {
                        id: processingIndicator
                        visible: false
                        running: visible
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                    }
                }
            }

            // Top toolbar Row 2 - Spectrum/Dataset controls
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                color: bgDarker

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 6

                    // Spectrum section label
                    Label {
                        text: "Spectrum:"
                        font.pixelSize: 10
                        font.bold: true
                        color: accentPink
                    }

                    // Dataset multi-select button (opens popup)
                    Button {
                        id: datasetSelectBtn
                        text: getSelectedDatasetsText()
                        font.pixelSize: 9
                        Layout.preferredWidth: 220
                        Layout.preferredHeight: 22

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgDark
                            border.color: accentPink
                            border.width: 1
                            radius: 3
                        }

                        contentItem: RowLayout {
                            spacing: 4
                            Text {
                                text: datasetSelectBtn.text
                                font: datasetSelectBtn.font
                                color: textLight
                                Layout.fillWidth: true
                                elide: Text.ElideMiddle
                                leftPadding: 4
                            }
                            Text {
                                text: "\u25BC"
                                font.pixelSize: 8
                                color: textMuted
                                rightPadding: 4
                            }
                        }

                        onClicked: datasetPopup.open()
                    }

                    // Dataset selection popup
                    Popup {
                        id: datasetPopup
                        x: datasetSelectBtn.x
                        y: datasetSelectBtn.y + datasetSelectBtn.height + 2
                        width: 280
                        height: Math.min(300, datasetListModel.count * 28 + 40)
                        modal: true
                        focus: true
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                        background: Rectangle {
                            color: bgMedium
                            border.color: accentPink
                            border.width: 1
                            radius: 4
                        }

                        contentItem: ColumnLayout {
                            spacing: 4

                            Label {
                                text: "Select datasets to plot:"
                                font.pixelSize: 10
                                font.bold: true
                                color: textLight
                                Layout.fillWidth: true
                            }

                            ScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true

                                ColumnLayout {
                                    width: parent.width
                                    spacing: 2

                                    Repeater {
                                        model: datasetListModel

                                        CheckBox {
                                            id: datasetCheck
                                            text: model.name
                                            checked: model.selected || false
                                            font.pixelSize: 9
                                            Layout.fillWidth: true

                                            indicator: Rectangle {
                                                implicitWidth: 14
                                                implicitHeight: 14
                                                x: datasetCheck.leftPadding
                                                y: parent.height / 2 - height / 2
                                                radius: 2
                                                border.color: model.is_integrated ? accentBlue : accentPink
                                                color: datasetCheck.checked ? (model.is_integrated ? accentBlue : accentPink) : bgDark

                                                Text {
                                                    anchors.centerIn: parent
                                                    text: "\u2713"
                                                    color: textLight
                                                    font.pixelSize: 10
                                                    visible: datasetCheck.checked
                                                }
                                            }

                                            contentItem: RowLayout {
                                                spacing: 4
                                                anchors.left: parent.indicator.right
                                                anchors.leftMargin: 4

                                                // Type indicator
                                                Rectangle {
                                                    width: 6
                                                    height: 6
                                                    radius: 3
                                                    color: model.is_truncated ? "#66ff99" : (model.is_discretized ? "#FFB7C5" : accentPink)
                                                    visible: true
                                                }

                                                Text {
                                                    text: datasetCheck.text
                                                    font: datasetCheck.font
                                                    color: textLight
                                                    elide: Text.ElideMiddle
                                                    Layout.fillWidth: true
                                                }
                                            }

                                            onCheckedChanged: {
                                                datasetListModel.setProperty(index, "selected", checked)
                                            }
                                        }
                                    }
                                }
                            }

                            // Legend
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                RowLayout {
                                    spacing: 3
                                    Rectangle { width: 6; height: 6; radius: 3; color: "#66ff99" }
                                    Label { text: "Truncated"; font.pixelSize: 8; color: textMuted }
                                }
                                RowLayout {
                                    spacing: 3
                                    Rectangle { width: 6; height: 6; radius: 3; color: "#FFB7C5" }
                                    Label { text: "Discretized"; font.pixelSize: 8; color: textMuted }
                                }
                                RowLayout {
                                    spacing: 3
                                    Rectangle { width: 6; height: 6; radius: 3; color: accentPink }
                                    Label { text: "Spectral"; font.pixelSize: 8; color: textMuted }
                                }
                            }
                        }
                    }

                    // Plot button
                    Button {
                        text: "Plot"
                        font.pixelSize: 9
                        Layout.preferredWidth: 50
                        Layout.preferredHeight: 22
                        enabled: hasSelectedDatasets()

                        background: Rectangle {
                            color: parent.enabled ? (parent.hovered ? accentPink : bgLight) : bgDark
                            border.color: parent.enabled ? accentPink : borderColor
                            radius: 2
                            opacity: parent.enabled ? 1.0 : 0.5
                        }

                        contentItem: Text {
                            text: parent.text
                            font: parent.font
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: plotSelectedDatasets()

                        ToolTip.visible: hovered
                        ToolTip.text: "Plot spectra for selected blocks from checked datasets"
                        ToolTip.delay: 500
                    }

                    // Clear plot button
                    Button {
                        text: "Clear"
                        font.pixelSize: 9
                        Layout.preferredWidth: 45
                        Layout.preferredHeight: 22

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgDark
                            border.color: borderColor
                            radius: 2
                        }

                        contentItem: Text {
                            text: parent.text
                            font: parent.font
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: clearPlotWindow()

                        ToolTip.visible: hovered
                        ToolTip.text: "Clear current plot window"
                        ToolTip.delay: 500
                    }

                    // Separator
                    Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 5; Layout.bottomMargin: 5; color: borderColor }

                    // Selection count
                    Label {
                        id: selectionLabel
                        text: mapCanvas.getSelectedBlockCount() + " selected"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    Item { Layout.fillWidth: true }

                    // Click behavior hint
                    Label {
                        text: hasSelectedDatasets() ? "Click map to add spectrum" : "Select datasets above"
                        font.pixelSize: 9
                        font.italic: true
                        color: hasSelectedDatasets() ? accentBlue : textMuted
                    }
                }
            }

            // Map tabs bar (for multiple open maps)
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: openMaps.length > 0 ? 28 : 0
                visible: openMaps.length > 0
                color: bgDarker

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 4
                    spacing: 2

                    Repeater {
                        model: openMaps

                        Rectangle {
                            height: 26
                            width: tabLabel.implicitWidth + closeBtn.width + 24
                            color: index === activeMapIndex ? bgMedium : (tabMouseArea.containsMouse ? bgLight : "transparent")
                            radius: index === activeMapIndex ? 0 : 3

                            Rectangle {
                                visible: index === activeMapIndex
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: 2
                                color: accentPink
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 4

                                // Unsaved indicator
                                Rectangle {
                                    visible: modelData.hasUnsavedChanges
                                    width: 6
                                    height: 6
                                    radius: 3
                                    color: accentPink
                                }

                                Label {
                                    id: tabLabel
                                    text: modelData.name + (modelData.hasUnsavedChanges ? " *" : "")
                                    font.pixelSize: 11
                                    color: index === activeMapIndex ? textLight : textMuted
                                    elide: Text.ElideMiddle
                                    Layout.maximumWidth: 150
                                }

                                // Close button
                                Rectangle {
                                    id: closeBtn
                                    width: 16
                                    height: 16
                                    radius: 8
                                    color: closeBtnArea.containsMouse ? "#C00260" : "transparent"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "\u2715"
                                        font.pixelSize: 10
                                        color: closeBtnArea.containsMouse ? textLight : textMuted
                                    }

                                    MouseArea {
                                        id: closeBtnArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        onClicked: closeMap(index)
                                    }
                                }
                            }

                            MouseArea {
                                id: tabMouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: setActiveMap(index)
                                // Propagate clicks to close button
                                propagateComposedEvents: true
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            // Map Canvas area
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDark

                // Drop area for dragging maps from project browser
                DropArea {
                    id: mapDropArea
                    anchors.fill: parent
                    keys: ["application/x-trans-map", "text/plain"]

                    onEntered: function(drag) {
                        dropIndicator.visible = true
                    }

                    onExited: {
                        dropIndicator.visible = false
                    }

                    onDropped: function(drop) {
                        dropIndicator.visible = false
                        var mapData = null

                        // Try to parse the map data from mime data
                        if (drop.hasText) {
                            var text = drop.text
                            try {
                                // Try to parse as JSON (from application/x-trans-map)
                                mapData = JSON.parse(text)
                            } catch (e) {
                                // Fallback: treat as map name/id
                                mapData = { name: text, id: text }
                            }
                        }

                        if (mapData && (mapData.name || mapData.id || mapData.path)) {
                            console.log("Map dropped:", JSON.stringify(mapData))
                            // Load the map using mapBackend
                            var identifier = mapData.path || mapData.id || mapData.name
                            if (identifier) {
                                mapBackend.loadMap(identifier)
                            }
                        }
                    }
                }

                // Visual indicator when dragging over
                Rectangle {
                    id: dropIndicator
                    anchors.fill: parent
                    visible: false
                    color: Qt.rgba(accentPink.r, accentPink.g, accentPink.b, 0.2)
                    border.color: accentPink
                    border.width: 3
                    radius: 8

                    Text {
                        anchors.centerIn: parent
                        text: "Drop map here to load"
                        color: accentPink
                        font.pixelSize: 18
                        font.bold: true
                    }
                }

                MapCanvas {
                    id: mapCanvas
                    anchors.fill: parent

                    onPointClicked: function(x, y, row, col, value) {
                        coordLabel.text = "(" + row + ", " + col + ") = " + value.toFixed(4)
                        pointInspector.setPoint(row, col, value, mapBackend.activeChannelName)
                        root.spectrumRequested(row, col)

                        // Plot spectra from all selected datasets
                        var selectedNames = getSelectedDatasetNames()
                        if (selectedNames.length > 0) {
                            mapBackend.requestPlotFromMultipleDatasets(selectedNames, row, col)
                        }
                    }

                    onCursorMoved: function(x, y, row, col, value) {
                        coordLabel.text = "(" + row + ", " + col + ") = " + value.toFixed(4)
                    }

                    onSpectralDataRequested: function(row, col) {
                        var spectrum = mapBackend.getSpectrumAt(row, col)
                        if (!spectrum.error) {
                            root.spectrumRequested(row, col)
                        }
                    }

                    onBlockSelectionChanged: {
                        var count = getSelectedBlockCount()
                        selectionLabel.text = count + " selected"
                        root.blockSelectionChanged(count)
                        // Debounce spectrum updates to avoid memory leak from rapid clicks
                        spectrumUpdateTimer.restart()
                    }

                    Timer {
                        id: spectrumUpdateTimer
                        interval: 200; repeat: false
                        onTriggered: inlineSpectrumViewer.updateSpectrum()
                    }

                    onProfileDrawn: function(x1, y1, x2, y2) {
                        var startRow = Math.floor(y1 / (height / mapBackend.mapRows))
                        var startCol = Math.floor(x1 / (width / mapBackend.mapCols))
                        var endRow = Math.floor(y2 / (height / mapBackend.mapRows))
                        var endCol = Math.floor(x2 / (width / mapBackend.mapCols))

                        var profileResult = mapBackend.extractProfile(startRow, startCol, endRow, endCol)
                        if (profileResult && profileResult.distance && profileResult.values) {
                            profileViewer.setProfile(
                                profileResult.distance,
                                profileResult.values,
                                Qt.point(startCol, startRow),
                                Qt.point(endCol, endRow)
                            )
                        }
                    }

                    Component.onCompleted: {
                        mapBackend.setCanvas(mapCanvas)
                    }
                }

                // Empty state overlay
                Rectangle {
                    anchors.fill: parent
                    color: bgDark
                    visible: !mapBackend.hasMapData

                    Column {
                        anchors.centerIn: parent
                        spacing: 12

                        Label {
                            text: "No Map Loaded"
                            font.pixelSize: 18
                            color: textMuted
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Label {
                            text: "Use File \u2192 Import Image or\nload a dataset with map data"
                            font.pixelSize: 12
                            color: Qt.darker(textMuted, 1.3)
                            horizontalAlignment: Text.AlignHCenter
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }
            }

            // Status bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 24
                color: bgDarker

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 16

                    Label {
                        id: coordLabel
                        text: "(-, -) = -"
                        font.pixelSize: 11
                        font.family: monoFont
                        color: textMuted
                    }

                    Rectangle {
                        width: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        color: borderColor
                    }

                    Label {
                        id: statusLabel
                        text: "Ready"
                        font.pixelSize: 11
                        color: textMuted
                    }

                    // Line-scan view toggle (kymograph vs scalar strip).
                    Label {
                        visible: mapBackend.isLineScanMode
                        text: "View:"
                        font.pixelSize: 11
                        color: textMuted
                    }
                    ComboBox {
                        id: lineScanViewCombo
                        visible: mapBackend.isLineScanMode
                        model: ["Kymograph", "Strip"]
                        currentIndex: mapBackend.lineScanView === "strip" ? 1 : 0
                        implicitHeight: 26
                        font.pixelSize: 11
                        onActivated: mapBackend.setLineScanView(
                            currentIndex === 1 ? "strip" : "kymograph")
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: mapBackend.isLineScanMode
                              ? ("Line scan \u00b7 " + mapBackend.lineScanPoints + " pts")
                              : (mapBackend.hasMapData
                                 ? mapBackend.mapRows + " \u00d7 " + mapBackend.mapCols
                                 : "No data")
                        font.pixelSize: 11
                        color: Qt.darker(textMuted, 1.2)
                    }
                }
            }

            // Inline Spectrum Viewer (collapsible, below status bar)
            InlineSpectrumViewer {
                id: inlineSpectrumViewer
                Layout.fillWidth: true
                mapBackend: mapBackend
            }

            // Bottom panel area (Profile Viewer)
            ProfileViewer {
                id: profileViewer
                Layout.fillWidth: true
                visible: toolPalette.currentTool === "line_profile" || profileViewer.hasProfile

                onExportRequested: {
                    root.profileExportRequested(profileViewer.profileData)
                }

                onClearRequested: {
                    profileViewer.clearProfile()
                    mapCanvas.clearOverlays()
                }
            }
        }

        // Right: Data Browser & Panels
        Rectangle {
            Layout.preferredWidth: 240
            Layout.fillHeight: true
            color: bgMedium

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Data Browser (channels, masks)
                DataBrowser {
                    id: dataBrowser
                    Layout.fillWidth: true
                    Layout.preferredHeight: 280

                    channelNames: mapBackend.channelNames
                    activeChannel: mapBackend.activeChannelName
                    hasSpectralData: mapBackend.hasSpectralData
                    spectralPoints: mapBackend.spectralPoints
                    mapRows: mapBackend.mapRows
                    mapCols: mapBackend.mapCols

                    onChannelSelected: function(channelName) {
                        mapBackend.setActiveChannel(channelName)
                    }

                    onStatisticsRequested: function(channelName) {
                        var stats = mapBackend.getChannelStatistics(channelName)
                        statsPanel.updateStats(stats, channelName, false, 0)
                    }
                }

                // Separator
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: borderColor
                }

                // Point Inspector
                PointInspector {
                    id: pointInspector
                    Layout.fillWidth: true

                    hasSpectrum: mapBackend.hasSpectralData

                    onPlotSpectrumRequested: function(row, col) {
                        root.spectrumRequested(row, col)
                    }

                    onAddToComparisonRequested: function(row, col) {
                        console.log("Add to comparison:", row, col)
                    }
                }

                // Separator
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: borderColor
                }

                // Statistics Panel
                StatisticsPanel {
                    id: statsPanel
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                }

                // Separator
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: borderColor
                }

                // Hyperspectral Control Panel (replaces Export section)
                HyperspectralControlPanel {
                    id: hyperspectralPanel
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    mapBackend: mapBackend
                    appBackend: backend
                    mapCanvas: mapCanvas

                    onOpenGraphRequested: {
                        // Forward to parent for embedded window creation
                        root.openSpectrumPlotRequested(
                            mapBackend.activeDataset,
                            mapBackend.getSelectedSpectraFromDataset(mapBackend.activeDataset),
                            false)
                    }

                    onOpenTableRequested: {
                        console.log("Table view requested for", mapBackend.activeDataset)
                    }
                }
            }
        }
    }

    // File dialogs (TIFF and CSV only - PNG export removed)
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
        property int mapIndex: -1
        property string mapName: ""

        title: "Unsaved Changes"
        modal: true
        width: 350
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel

        background: Rectangle {
            color: bgMedium
            border.color: accentPink
            border.width: 1
            radius: 5
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 15

            Label {
                text: "The map \"" + unsavedChangesDialog.mapName + "\" has unsaved changes."
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
            // Save then close
            saveMapDialog.mapIndex = mapIndex
            saveMapDialog.open()
        }

        onDiscarded: {
            // Close without saving
            forceCloseMap(mapIndex)
        }
    }

    Platform.FileDialog {
        id: saveMapDialog
        property int mapIndex: -1
        title: "Save Map"
        nameFilters: ["TIFF Files (*.tif *.tiff)", "NumPy Files (*.npy)"]
        fileMode: Platform.FileDialog.SaveFile
        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) path = path.substring(7)
            mapCanvas.saveMapData(path)
            forceCloseMap(mapIndex)
        }
    }

    // Public API
    // Open a line scan / point-set dataset as a kymograph (toggle to strip
    // in the status bar). The map backend looks the dataset up via the
    // injected AppBackend and links it for per-position spectrum inspection.
    function loadDatasetAsLineScan(datasetName) {
        mapBackend.loadDatasetAsLineScan(datasetName, "kymograph")
        autoScale()
    }

    function loadMap(filePath) {
        mapBackend.loadMapFromFile(filePath)
        // Add to open maps list
        var mapInfo = {
            id: "map_" + Date.now(),
            name: filePath.split("/").pop(),
            path: filePath,
            hasUnsavedChanges: false
        }
        openMaps.push(mapInfo)
        openMaps = openMaps  // Trigger binding update
        activeMapIndex = openMaps.length - 1

        // Update color scale fields
        autoScale()
    }

    function loadMapData(data, name, path) {
        // Load from numpy array (from importImage)
        mapBackend.setMapDataFromArray(data, name)

        var mapInfo = {
            id: "map_" + Date.now(),
            name: name || "Untitled",
            path: path || "",
            hasUnsavedChanges: path ? false : true  // New maps without path need saving
        }
        openMaps.push(mapInfo)
        openMaps = openMaps
        activeMapIndex = openMaps.length - 1

        autoScale()
    }

    function setActiveMap(index) {
        if (index >= 0 && index < openMaps.length) {
            activeMapIndex = index
            // TODO: Load map data for this tab
        }
    }

    function closeMap(index) {
        if (index < 0 || index >= openMaps.length) return

        var mapInfo = openMaps[index]
        if (mapInfo.hasUnsavedChanges) {
            unsavedChangesDialog.mapIndex = index
            unsavedChangesDialog.mapName = mapInfo.name
            unsavedChangesDialog.open()
        } else {
            forceCloseMap(index)
        }
    }

    function forceCloseMap(index) {
        if (index < 0 || index >= openMaps.length) return

        var mapId = openMaps[index].id
        openMaps.splice(index, 1)
        openMaps = openMaps  // Trigger binding update

        if (activeMapIndex >= openMaps.length) {
            activeMapIndex = openMaps.length - 1
        }

        mapClosed(mapId)
    }

    function markMapModified(index) {
        if (index >= 0 && index < openMaps.length) {
            openMaps[index].hasUnsavedChanges = true
            openMaps = openMaps
        }
    }

    function applyColorScale() {
        var vmin = parseFloat(vminField.text)
        var vmax = parseFloat(vmaxField.text)
        if (!isNaN(vmin) && !isNaN(vmax) && vmin < vmax) {
            mapCanvas.setColorLimits(vmin, vmax)
        }
    }

    function autoScale() {
        var stats = mapCanvas.getStatistics()
        if (stats && stats.min !== undefined) {
            vminField.text = stats.min.toFixed(4)
            vmaxField.text = stats.max.toFixed(4)
            mapCanvas.setColorLimits(stats.min, stats.max)

            // Update statistics panel
            statsPanel.updateStats(stats, mapBackend.activeChannelName, false, 0)
        }
    }

    function getSelectedBlocks() {
        return mapBackend.getSelectedBlocks()
    }

    function getSelectionMask() {
        return mapCanvas.getSelectionMask()
    }

    function getAverageSpectrum() {
        return mapBackend.getAverageSpectrumFromSelection()
    }

    function setTool(toolName) {
        toolPalette.currentTool = toolName
        mapCanvas.setTool(toolName)
    }

    // Check for unsaved changes when closing
    function checkUnsavedChanges() {
        for (var i = 0; i < openMaps.length; i++) {
            if (openMaps[i].hasUnsavedChanges) {
                return true
            }
        }
        return false
    }

    // Link datasets from AppBackend for spectrum viewing
    function linkDatasetsFromBackend(appBackend) {
        // Clear existing
        datasetListModel.clear()
        mapBackend.clearLinkedDatasets()

        // Get dataset list with info
        var datasets = appBackend.getDatasetListWithInfo()

        for (var i = 0; i < datasets.length; i++) {
            var info = datasets[i]
            datasetListModel.append({
                "name": info.name,
                "num_spectra": info.num_spectra,
                "is_truncated": info.is_truncated,
                "is_discretized": info.is_discretized || false,
                "is_integrated": false,  // Integrated datasets are now excluded by backend
                "selected": info.is_truncated  // Auto-select truncated spectral datasets
            })

            // Link the actual SpectralData object
            var spectralData = appBackend.getDataset(info.name)
            if (spectralData) {
                mapBackend.linkDataset(info.name, spectralData)
            }
        }

        console.log("Linked", datasetListModel.count, "datasets for spectrum viewing")
    }

    // Helper functions for multi-dataset selection
    function getSelectedDatasetNames() {
        var names = []
        for (var i = 0; i < datasetListModel.count; i++) {
            var item = datasetListModel.get(i)
            if (item && item.selected) {
                names.push(item.name)
            }
        }
        return names
    }

    function hasSelectedDatasets() {
        for (var i = 0; i < datasetListModel.count; i++) {
            var item = datasetListModel.get(i)
            if (item && item.selected) {
                return true
            }
        }
        return false
    }

    function getSelectedDatasetsText() {
        var names = getSelectedDatasetNames()
        if (names.length === 0) return "Select datasets..."
        if (names.length === 1) return names[0]
        return names.length + " datasets selected"
    }

    function plotSelectedDatasets() {
        var selectedNames = getSelectedDatasetNames()
        if (selectedNames.length === 0) return

        // Get spectra for all selected blocks from all selected datasets
        var allSpectra = []
        var selectedBlocks = mapCanvas.getSelectedBlocks()

        if (selectedBlocks.length === 0) {
            console.log("No blocks selected for plotting")
            return
        }

        for (var i = 0; i < selectedNames.length; i++) {
            var datasetName = selectedNames[i]
            for (var j = 0; j < selectedBlocks.length; j++) {
                var block = selectedBlocks[j]
                var spectrum = mapBackend.getSpectrumFromDataset(datasetName, block.row, block.col)
                if (!spectrum.error) {
                    allSpectra.push(spectrum)
                }
            }
        }

        if (allSpectra.length > 0) {
            var combinedName = selectedNames.join(" + ")
            root.openSpectrumPlotRequested(combinedName, allSpectra, false)
        }
    }

    function clearPlotWindow() {
        // Signal to clear/close the main plot window
        // This will be handled by creating a new window next time
        console.log("Clear plot window requested")
    }

    // Refresh dataset list
    function refreshDatasets(appBackend) {
        linkDatasetsFromBackend(appBackend)
    }
}
