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

Rectangle {
    id: toolItem

    property string toolName: "Tool"
    signal closeRequested()

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    color: bgLight
    border.color: borderColor
    border.width: 1
    radius: 4

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        // Header with tool name and close button
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: bgDark
            radius: 3

            RowLayout {
                anchors.fill: parent
                anchors.margins: 5
                spacing: 8

                Text {
                    text: toolItem.toolName
                    font.pixelSize: 13
                    font.bold: true
                    color: textLight
                    Layout.fillWidth: true
                }

                Button {
                    text: "×"
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    font.pixelSize: 16
                    font.bold: true

                    onClicked: toolItem.closeRequested()

                    background: Rectangle {
                        color: parent.pressed ? accentPink : (parent.hovered ? bgLight : "transparent")
                        radius: 3
                        opacity: parent.pressed ? 0.3 : 1
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // Tool content area
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            radius: 3

            Loader {
                id: toolLoader
                anchors.fill: parent
                anchors.margins: 5

                source: {
                    // Map tool names to their QML components
                    switch(toolItem.toolName) {
                        case "Integration Utility":
                            return "../tools/IntegrationTool.qml"
                        case "Spatial Average":
                            return "../tools/SpatialAverageTool.qml"
                        case "1D FFT":
                            return "../tools/FFT1DTool.qml"
                        case "Curve Smoothing":
                            return "../tools/CurveSmoothingTool.qml"
                        case "Image Smoothing":
                            return "../tools/ImageSmoothingTool.qml"
                        case "Derivative Calculator":
                            return "../tools/DerivativeTool.qml"
                        case "Gradient Filter":
                            return "../tools/GradientFilterTool.qml"
                        case "Curve Fitting":
                            return "../tools/CurveFittingTool.qml"
                        case "Map Generator":
                            return "../tools/MapGeneratorTool.qml"
                        case "Peak Finder":
                            return "../tools/PeakFinderTool.qml"
                        case "Map Discretizer":
                            return "../tools/MapDiscretizerTool.qml"
                        case "Curve Analysis":
                            return "../tools/CurveAnalysisTool.qml"
                        case "Truncate Data":
                            return "../tools/TruncateTool.qml"
                        default:
                            return ""
                    }
                }

                // Fallback if tool not found
                onStatusChanged: {
                    if (status === Loader.Error || source === "") {
                        toolLoader.sourceComponent = placeholderComponent
                    }
                }
            }

            // Placeholder component for tools without UI
            Component {
                id: placeholderComponent
                Rectangle {
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: toolItem.toolName + "\n\nTool interface will appear here"
                        font.pixelSize: 12
                        color: textMuted
                        horizontalAlignment: Text.AlignHCenter
                        lineHeight: 1.5
                    }
                }
            }
        }
    }

    // Hover effect
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: accentPink
        border.width: 2
        radius: 4
        visible: toolMouseArea.containsMouse
        opacity: 0.3
    }

    MouseArea {
        id: toolMouseArea
        anchors.fill: parent
        hoverEnabled: true
        propagateComposedEvents: true
        onPressed: mouse.accepted = false
    }
}
