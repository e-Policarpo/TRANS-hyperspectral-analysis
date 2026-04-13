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

// Statistics Panel for Map Editor
// Displays statistics for the current channel or selection

Rectangle {
    id: statsPanel

    // Statistics data
    property var stats: ({})
    property string channelName: ""
    property int selectionCount: 0
    property bool isSelectionStats: false

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    color: bgMedium
    height: 160
    radius: 6

    property bool hasStats: stats && (stats.min !== undefined || stats.mean !== undefined)

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: bgDark

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Label {
                    text: isSelectionStats ? "Selection Statistics" : "Channel Statistics"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                }

                Item { Layout.fillWidth: true }

                // Selection count badge
                Rectangle {
                    visible: isSelectionStats && selectionCount > 0
                    Layout.preferredHeight: 18
                    Layout.preferredWidth: selectionLabel.implicitWidth + 12
                    radius: 9
                    color: accentBlue
                    opacity: 0.8

                    Label {
                        id: selectionLabel
                        anchors.centerIn: parent
                        text: selectionCount + " pts"
                        font.pixelSize: 10
                        color: textLight
                    }
                }
            }
        }

        // Content
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark

            GridLayout {
                anchors.fill: parent
                anchors.margins: 8
                columns: 4
                columnSpacing: 8
                rowSpacing: 6

                // Row 1: Min, Max
                Label {
                    text: "Min:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.min !== undefined ? stats.min.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                Label {
                    text: "Max:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.max !== undefined ? stats.max.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                // Row 2: Mean, Std
                Label {
                    text: "Mean:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.mean !== undefined ? stats.mean.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: accentBlue
                    Layout.fillWidth: true
                }

                Label {
                    text: "Std:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.std !== undefined ? stats.std.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                // Row 3: Median, RMS
                Label {
                    text: "Median:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.median !== undefined ? stats.median.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                Label {
                    text: "RMS:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.rms !== undefined ? stats.rms.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                // Row 4: Range, additional info
                Label {
                    text: "Range:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: hasStats && stats.range !== undefined ? stats.range.toFixed(4) : "--"
                    font.pixelSize: 10
                    font.family: monoFont
                    color: textLight
                    Layout.fillWidth: true
                }

                Label {
                    text: "Channel:"
                    font.pixelSize: 10
                    color: textMuted
                }
                Label {
                    text: channelName || "--"
                    font.pixelSize: 10
                    color: textMuted
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            // Empty state
            Rectangle {
                anchors.fill: parent
                color: bgDark
                visible: !hasStats

                Label {
                    anchors.centerIn: parent
                    text: "No statistics available\nLoad data or make a selection"
                    font.pixelSize: 11
                    color: textMuted
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    // Function to update statistics
    function updateStats(newStats, channel, isSelection, count) {
        stats = newStats || {}
        channelName = channel || ""
        isSelectionStats = isSelection || false
        selectionCount = count || 0
    }

    // Function to clear statistics
    function clearStats() {
        stats = {}
        channelName = ""
        isSelectionStats = false
        selectionCount = 0
    }
}
