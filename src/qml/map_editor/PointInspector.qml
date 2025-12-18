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

// Point Inspector Panel for Map Editor
// Displays information about the currently inspected point

Rectangle {
    id: pointInspector

    // Current point info
    property int currentRow: -1
    property int currentCol: -1
    property real currentValue: 0.0
    property string channelName: ""

    // Spectral data if available
    property bool hasSpectrum: false
    property var spectrumX: []
    property var spectrumY: []

    // Signals
    signal plotSpectrumRequested(int row, int col)
    signal addToComparisonRequested(int row, int col)

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

    color: bgMedium
    height: 120

    property bool hasPoint: currentRow >= 0 && currentCol >= 0

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
                    text: "Point Inspector"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                }

                Item { Layout.fillWidth: true }

                // Crosshair indicator
                Rectangle {
                    Layout.preferredWidth: 8
                    Layout.preferredHeight: 8
                    radius: 4
                    color: hasPoint ? accentBlue : textMuted
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
                columns: 2
                columnSpacing: 16
                rowSpacing: 4

                // Position
                Label {
                    text: "Position:"
                    font.pixelSize: 11
                    color: textMuted
                }
                Label {
                    text: hasPoint ? "(" + currentRow + ", " + currentCol + ")" : "--"
                    font.pixelSize: 11
                    font.family: "monospace"
                    color: hasPoint ? textLight : textMuted
                }

                // Value
                Label {
                    text: "Value:"
                    font.pixelSize: 11
                    color: textMuted
                }
                Label {
                    text: hasPoint ? currentValue.toFixed(6) : "--"
                    font.pixelSize: 11
                    font.family: "monospace"
                    color: hasPoint ? accentBlue : textMuted
                }

                // Channel
                Label {
                    text: "Channel:"
                    font.pixelSize: 11
                    color: textMuted
                }
                Label {
                    text: channelName || "--"
                    font.pixelSize: 11
                    color: textMuted
                    elide: Text.ElideRight
                }

                // Actions
                Item { Layout.columnSpan: 2; Layout.preferredHeight: 4 }

                RowLayout {
                    Layout.columnSpan: 2
                    spacing: 8

                    Button {
                        text: "Plot Spectrum"
                        Layout.preferredHeight: 28
                        enabled: hasPoint && hasSpectrum

                        background: Rectangle {
                            color: parent.pressed ? accentBlue : (parent.hovered ? bgLight : bgMedium)
                            radius: 4
                            border.color: borderColor
                            border.width: 1
                            opacity: parent.enabled ? 1 : 0.5
                        }

                        contentItem: Text {
                            text: parent.text
                            font.pixelSize: 11
                            color: parent.enabled ? textLight : textMuted
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: plotSpectrumRequested(currentRow, currentCol)
                    }

                    Button {
                        text: "+ Compare"
                        Layout.preferredHeight: 28
                        enabled: hasPoint && hasSpectrum

                        background: Rectangle {
                            color: parent.pressed ? accentPink : (parent.hovered ? bgLight : bgMedium)
                            radius: 4
                            border.color: borderColor
                            border.width: 1
                            opacity: parent.enabled ? 1 : 0.5
                        }

                        contentItem: Text {
                            text: parent.text
                            font.pixelSize: 11
                            color: parent.enabled ? textLight : textMuted
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: addToComparisonRequested(currentRow, currentCol)
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            // Empty state overlay
            Rectangle {
                anchors.fill: parent
                color: bgDark
                visible: !hasPoint

                Label {
                    anchors.centerIn: parent
                    text: "Click on map to inspect"
                    font.pixelSize: 11
                    color: textMuted
                }
            }
        }
    }

    // Function to update point info
    function setPoint(row, col, value, channel) {
        currentRow = row
        currentCol = col
        currentValue = value
        channelName = channel || ""
    }

    // Function to clear point
    function clearPoint() {
        currentRow = -1
        currentCol = -1
        currentValue = 0.0
    }

    // Function to set spectrum availability
    function setSpectrumAvailable(available) {
        hasSpectrum = available
    }
}
