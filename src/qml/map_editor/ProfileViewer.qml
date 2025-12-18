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
import TransQML 1.0

// Profile Viewer for Map Editor
// Displays line profiles extracted from the map

Rectangle {
    id: profileViewer

    // Profile data (set from Python)
    property var profileData: null  // { distance: [...], values: [...], stats: {...} }
    property bool hasProfile: profileData !== null && profileData.distance && profileData.distance.length > 0

    // Profile endpoints (in data coordinates)
    property point startPoint: Qt.point(-1, -1)
    property point endPoint: Qt.point(-1, -1)

    // Signals
    signal exportRequested()
    signal clearRequested()

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
    property color profileColor: "#ff6b6b"  // Keep profile-specific color

    color: bgMedium
    height: 200

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: bgDark

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                Label {
                    text: "Line Profile"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                }

                // Profile endpoint info
                Label {
                    text: hasProfile ?
                          "(" + startPoint.x + ", " + startPoint.y + ") → (" + endPoint.x + ", " + endPoint.y + ")" :
                          "Draw profile on map"
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                    visible: startPoint.x >= 0 || !hasProfile
                }

                Item { Layout.fillWidth: true }

                // Export button
                ToolButton {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    text: "E"
                    enabled: hasProfile

                    ToolTip.text: "Export Profile"
                    ToolTip.visible: hovered
                    ToolTip.delay: 500

                    background: Rectangle {
                        color: parent.pressed ? accentBlue : (parent.hovered ? bgLight : "transparent")
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: 12
                        color: parent.enabled ? textLight : textMuted
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: exportRequested()
                }

                // Clear button
                ToolButton {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    text: "×"
                    enabled: hasProfile

                    ToolTip.text: "Clear Profile"
                    ToolTip.visible: hovered
                    ToolTip.delay: 500

                    background: Rectangle {
                        color: parent.pressed ? accentPink : (parent.hovered ? bgLight : "transparent")
                        radius: 3
                    }

                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: 14
                        font.bold: true
                        color: parent.enabled ? textLight : textMuted
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: clearRequested()
                }
            }
        }

        // Profile Canvas
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            clip: true

            // Profile plot using ProfileCanvas (QQuickPaintedItem)
            ProfileCanvas {
                id: profileCanvas
                anchors.fill: parent
                anchors.margins: 4
                visible: hasProfile
            }

            // Empty state
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 8
                visible: !hasProfile

                Label {
                    text: "No Profile"
                    font.pixelSize: 14
                    color: textMuted
                    Layout.alignment: Qt.AlignHCenter
                }

                Label {
                    text: "Select Line Profile tool (L)\nand drag on the map"
                    font.pixelSize: 11
                    color: Qt.darker(textMuted, 1.3)
                    horizontalAlignment: Text.AlignHCenter
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }

        // Statistics bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: bgDark
            visible: hasProfile

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 16

                Label {
                    text: "Min: " + (profileData && profileData.stats ?
                          profileData.stats.min.toFixed(3) : "--")
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                }

                Label {
                    text: "Max: " + (profileData && profileData.stats ?
                          profileData.stats.max.toFixed(3) : "--")
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                }

                Label {
                    text: "Mean: " + (profileData && profileData.stats ?
                          profileData.stats.mean.toFixed(3) : "--")
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                }

                Label {
                    text: "Length: " + (profileData && profileData.distance ?
                          profileData.distance.length + " pts" : "--")
                    font.pixelSize: 10
                    font.family: "monospace"
                    color: textMuted
                }

                Item { Layout.fillWidth: true }
            }
        }
    }

    // Function to set profile data
    function setProfile(distance, values, start, end) {
        var stats = {
            min: Math.min(...values),
            max: Math.max(...values),
            mean: values.reduce((a, b) => a + b, 0) / values.length
        }

        profileData = {
            distance: distance,
            values: values,
            stats: stats
        }

        startPoint = Qt.point(Math.round(start.x), Math.round(start.y))
        endPoint = Qt.point(Math.round(end.x), Math.round(end.y))

        // Update canvas
        profileCanvas.setProfileData(distance, values)
    }

    // Function to clear profile
    function clearProfile() {
        profileData = null
        startPoint = Qt.point(-1, -1)
        endPoint = Qt.point(-1, -1)
        profileCanvas.clearData()
    }
}
