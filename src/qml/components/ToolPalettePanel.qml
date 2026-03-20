/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * ToolPalettePanel - Standalone tool palette for workspace left panel
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: toolPalettePanel

    // Tool list to display (string array of tool names)
    property var tools: []

    // Signal emitted when a tool is activated (double-click)
    signal toolActivated(string toolName)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Font scaling
    property int fontSizeSmall: mainWin ? mainWin.fontSizeSmall : 10
    property int fontSizeMedium: mainWin ? mainWin.fontSizeMedium : 12

    color: bgMedium

    onToolsChanged: rebuildModel()

    function rebuildModel() {
        toolModel.clear()
        if (!tools) return
        for (var i = 0; i < tools.length; i++) {
            toolModel.append({ "name": tools[i] })
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        // Header
        Text {
            text: "Tools"
            color: accentPink
            font.pixelSize: 14
            font.bold: true
            Layout.fillWidth: true
            padding: 5
        }

        // Search field
        TextField {
            id: toolSearch
            placeholderText: "Search tools..."
            placeholderTextColor: Qt.rgba(textMuted.r, textMuted.g, textMuted.b, 0.5)
            Layout.fillWidth: true
            color: textLight
            font.pixelSize: fontSizeMedium

            background: Rectangle {
                color: bgDark
                border.color: toolSearch.activeFocus ? accentBlue : borderColor
                radius: 3
            }
        }

        // Tool list
        ListView {
            id: toolList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2

            model: ListModel { id: toolModel }

            delegate: Rectangle {
                width: toolList.width
                height: visible ? 32 : 0
                visible: toolSearch.text === "" ||
                         name.toLowerCase().includes(toolSearch.text.toLowerCase())
                color: toolMouseArea.containsMouse ? bgLight : "transparent"
                radius: 3

                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    text: name
                    color: textLight
                    font.pixelSize: fontSizeMedium
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: toolMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor

                    onDoubleClicked: {
                        toolActivated(name)
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                active: true
            }
        }

        // Help text
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: bgDark
            radius: 5

            Text {
                anchors.fill: parent
                anchors.margins: 6
                text: "Double-click to open a tool"
                color: textMuted
                font.pixelSize: fontSizeSmall
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Component.onCompleted: {
        rebuildModel()
    }
}
