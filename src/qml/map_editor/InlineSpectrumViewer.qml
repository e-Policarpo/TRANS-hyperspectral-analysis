/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * InlineSpectrumViewer - Collapsible average spectrum panel below the map
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: March 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import TransQML 1.0

Item {
    id: root

    // Required bindings
    property var mapBackend: null

    // State
    property bool expanded: false
    property int blockCount: 0
    // When the average comes from STS dots (not map blocks) we show a point
    // count instead of a block count in the header.
    property int stsPointCount: 0

    // Theme colors
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    // True when either block-selection or STS-dot data is displayed.
    property bool hasData: blockCount > 0 || stsPointCount > 0

    Layout.fillWidth: true
    Layout.preferredHeight: expanded ? 228 : 28

    Behavior on Layout.preferredHeight {
        NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
    }

    Rectangle {
        anchors.fill: parent
        color: bgDark
        border.color: borderColor
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Collapsible header
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                color: expanded ? bgMedium : bgDark

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.expanded = !root.expanded
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8

                    Label {
                        text: (expanded ? "\u25BC " : "\u25B6 ") +
                              "Average Spectrum" +
                              (stsPointCount > 0
                               ? " (" + stsPointCount + " STS pt" + (stsPointCount !== 1 ? "s" : "") + ")"
                               : (blockCount > 0 ? " (" + blockCount + " blocks)" : ""))
                        font.pixelSize: 11
                        font.bold: true
                        color: accentPink
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: !hasData ? "No selection" : ""
                        font.pixelSize: 9
                        color: textMuted
                        visible: !expanded
                    }
                }
            }

            // Spectrum plot area
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: expanded
                clip: true

                // Empty state
                Label {
                    anchors.centerIn: parent
                    text: "Select blocks or STS points on the map to see average spectrum"
                    font.pixelSize: 11
                    color: textMuted
                    visible: !hasData
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    width: parent.width - 20
                }

                // GraphCanvas for spectrum display
                GraphCanvas {
                    id: spectrumGraph
                    anchors.fill: parent
                    anchors.margins: 2
                    visible: hasData
                }
            }
        }
    }

    // Public function to update the spectrum
    function updateSpectrum() {
        if (!mapBackend) return

        var result = mapBackend.getAverageSpectrumForSelectedBlocks()

        if (result && !result.error && result.x && result.y) {
            blockCount = result.block_count || 0
            stsPointCount = 0   // block selection overrides any STS-dot average
            spectrumGraph.clearCurves()
            spectrumGraph.addCurve(
                result.x, result.y,
                result.title || "Average Spectrum",
                "#5BCEFA"  // accent blue
            )
            spectrumGraph.setLabels(
                result.x_name || "x",
                result.y_name || "Intensity"
            )

            // Auto-expand when data arrives
            if (!expanded && blockCount > 0) {
                expanded = true
            }
        } else {
            blockCount = 0
            spectrumGraph.clearCurves()
        }
    }

    // Display the average of the currently-selected STS dots (item 2a). An
    // empty/blank result clears the panel. Independent of block selection.
    function showStsAverage(result) {
        if (result && !result.error && result.x && result.y
                && result.x.length > 0) {
            blockCount = 0   // STS-dot average overrides any block selection
            stsPointCount = result.point_count || 0
            spectrumGraph.clearCurves()
            spectrumGraph.addCurve(
                result.x, result.y,
                result.title || "Average Spectrum",
                "#5BCEFA"
            )
            spectrumGraph.setLabels(
                result.x_name || "V",
                result.y_name || "Current"
            )
            if (!expanded) expanded = true
        } else {
            stsPointCount = 0
            if (blockCount === 0) spectrumGraph.clearCurves()
        }
    }

    // Clear the viewer
    function clear() {
        blockCount = 0
        stsPointCount = 0
        spectrumGraph.clearCurves()
    }

    // Cleanup matplotlib resources when destroyed
    Component.onDestruction: {
        if (spectrumGraph) spectrumGraph.cleanup()
    }
}
