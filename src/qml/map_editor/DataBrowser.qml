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

// Data Browser for Map Editor
// Displays channels, masks, and provides channel selection/management

Rectangle {
    id: dataBrowser

    property var channelNames: []
    property string activeChannel: ""
    property var maskNames: []
    property bool hasSpectralData: false
    property int spectralPoints: 0
    property int mapRows: 0
    property int mapCols: 0

    // Signals
    signal channelSelected(string channelName)
    signal maskSelected(string maskName)
    signal channelDeleteRequested(string channelName)
    signal maskDeleteRequested(string maskName)
    signal statisticsRequested(string channelName)

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
    width: 220
    radius: 6

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        // Channels Section
        GroupBox {
            id: channelsGroup
            title: "Channels"
            Layout.fillWidth: true
            Layout.preferredHeight: 180

            background: Rectangle {
                y: channelsGroup.topPadding - channelsGroup.bottomPadding
                width: parent.width
                height: parent.height - channelsGroup.topPadding + channelsGroup.bottomPadding
                color: bgDark
                border.color: borderColor
                border.width: 1
                radius: 4
            }

            label: Label {
                x: channelsGroup.leftPadding
                width: channelsGroup.availableWidth
                text: channelsGroup.title
                font.pixelSize: 12
                font.bold: true
                color: textLight
            }

            ListView {
                id: channelList
                anchors.fill: parent
                clip: true
                model: channelNames

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                delegate: ItemDelegate {
                    id: channelDelegate
                    width: channelList.width
                    height: 36

                    property bool isActive: modelData === activeChannel

                    background: Rectangle {
                        color: {
                            if (channelDelegate.isActive) return accentBlue
                            if (channelDelegate.hovered) return bgLight
                            return "transparent"
                        }
                        opacity: channelDelegate.isActive ? 0.4 : 1
                        radius: 3
                    }

                    contentItem: RowLayout {
                        spacing: 8

                        // Channel type indicator
                        Rectangle {
                            Layout.preferredWidth: 4
                            Layout.preferredHeight: 24
                            radius: 2
                            color: {
                                var name = modelData.toLowerCase()
                                if (name.includes("height") || name.includes("topo")) return "#66ff99"
                                if (name.includes("amp")) return "#5BCEFA"
                                if (name.includes("phase")) return "#9B4F96"
                                if (name.includes("optical") || name.includes("snom")) return "#F5A9B8"
                                return textMuted
                            }
                        }

                        // Channel name
                        Label {
                            text: modelData
                            font.pixelSize: 12
                            color: channelDelegate.isActive ? textLight : textMuted
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        // Stats button
                        ToolButton {
                            Layout.preferredWidth: 24
                            Layout.preferredHeight: 24
                            text: "S"
                            font.pixelSize: 10
                            visible: channelDelegate.hovered || channelDelegate.isActive

                            ToolTip.text: "View Statistics"
                            ToolTip.visible: hovered
                            ToolTip.delay: 500

                            background: Rectangle {
                                color: parent.pressed ? accentBlue : (parent.hovered ? bgLight : "transparent")
                                radius: 3
                            }

                            contentItem: Text {
                                text: parent.text
                                font: parent.font
                                color: textMuted
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: statisticsRequested(modelData)
                        }
                    }

                    onClicked: channelSelected(modelData)

                    // Context menu
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton) {
                                channelContextMenu.channelName = modelData
                                channelContextMenu.popup()
                            }
                        }
                    }
                }

                // Empty state
                Label {
                    anchors.centerIn: parent
                    text: "No channels loaded"
                    font.pixelSize: 11
                    color: textMuted
                    visible: channelList.count === 0
                }
            }

            Menu {
                id: channelContextMenu
                property string channelName: ""

                background: Rectangle {
                    color: bgMedium
                    border.color: borderColor
                    border.width: 1
                    radius: 4
                }

                MenuItem {
                    text: "View Statistics"
                    onTriggered: statisticsRequested(channelContextMenu.channelName)
                }
                MenuItem {
                    text: "Duplicate"
                    enabled: false // TODO: Implement
                }
                MenuSeparator {}
                MenuItem {
                    text: "Delete"
                    onTriggered: channelDeleteRequested(channelContextMenu.channelName)
                }
            }
        }

        // Masks Section
        GroupBox {
            id: masksGroup
            title: "Masks"
            Layout.fillWidth: true
            Layout.preferredHeight: 120

            background: Rectangle {
                y: masksGroup.topPadding - masksGroup.bottomPadding
                width: parent.width
                height: parent.height - masksGroup.topPadding + masksGroup.bottomPadding
                color: bgDark
                border.color: borderColor
                border.width: 1
                radius: 4
            }

            label: Label {
                x: masksGroup.leftPadding
                width: masksGroup.availableWidth
                text: masksGroup.title
                font.pixelSize: 12
                font.bold: true
                color: textLight
            }

            ListView {
                id: maskList
                anchors.fill: parent
                clip: true
                model: maskNames

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                delegate: ItemDelegate {
                    id: maskDelegate
                    width: maskList.width
                    height: 32

                    background: Rectangle {
                        color: maskDelegate.hovered ? bgLight : "transparent"
                        radius: 3
                    }

                    contentItem: RowLayout {
                        spacing: 8

                        CheckBox {
                            id: maskCheck
                            Layout.preferredWidth: 20
                            checked: false
                            onCheckedChanged: {
                                // TODO: Toggle mask visibility
                            }
                        }

                        Label {
                            text: modelData
                            font.pixelSize: 11
                            color: textMuted
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    onClicked: maskSelected(modelData)
                }

                // Empty state
                Label {
                    anchors.centerIn: parent
                    text: "No masks defined"
                    font.pixelSize: 11
                    color: textMuted
                    visible: maskList.count === 0
                }
            }
        }

        // Info Section
        GroupBox {
            id: infoGroup
            title: "Info"
            Layout.fillWidth: true
            Layout.fillHeight: true

            background: Rectangle {
                y: infoGroup.topPadding - infoGroup.bottomPadding
                width: parent.width
                height: parent.height - infoGroup.topPadding + infoGroup.bottomPadding
                color: bgDark
                border.color: borderColor
                border.width: 1
                radius: 4
            }

            label: Label {
                x: infoGroup.leftPadding
                width: infoGroup.availableWidth
                text: infoGroup.title
                font.pixelSize: 12
                font.bold: true
                color: textLight
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Label {
                    text: mapRows > 0 ? "Dimensions: " + mapRows + " x " + mapCols : "No data loaded"
                    font.pixelSize: 11
                    color: textMuted
                }

                Label {
                    text: hasSpectralData ?
                          "Spectral: " + spectralPoints + " pts" :
                          "No spectral data"
                    font.pixelSize: 11
                    color: hasSpectralData ? accentBlue : textMuted
                }

                Label {
                    text: channelNames.length + " channel(s)"
                    font.pixelSize: 11
                    color: textMuted
                }

                Item { Layout.fillHeight: true }

                // Quick actions hint
                Label {
                    text: "Right-click channel\nfor more options"
                    font.pixelSize: 9
                    color: Qt.darker(textMuted, 1.3)
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                    visible: channelNames.length > 0
                }
            }
        }
    }
}
