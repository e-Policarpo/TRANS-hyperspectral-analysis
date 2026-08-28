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
import "../components"   // the Theme singleton

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
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

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

                    // The strip's plot ground matches the panel it sits in.
                    backgroundColor: root.bgDark
                    foregroundColor: root.textMuted
                    // borderColor, not bgLight: this draws the axes frame and the
                    // gridlines, and bgLight-on-bgDark measures 1.12:1 to 1.54:1 on
                    // all 22 schemes — the frame came out fainter than either
                    // candidate and the painted gridline at 1.02–1.08:1, i.e. no
                    // visible box on any scheme. borderColor wins on 21 of the 22.
                    gridColor: root.borderColor
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
            // GraphCanvas.addCurve is (label, x, y, color, linewidth) and the
            // slot declares all five, so every argument has to be passed.
            spectrumGraph.addCurve(
                result.title || "Average Spectrum",
                result.x, result.y,
                root.accentBlue,
                2.0
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
                result.title || "Average Spectrum",
                result.x, result.y,
                root.accentBlue,
                2.0
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
