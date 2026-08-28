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
    id: workspaceRoot
    color: bgDark

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    // Dock areas models
    ListModel {
        id: leftDockModel
    }

    ListModel {
        id: rightDockModel
    }

    ListModel {
        id: topDockModel
    }

    ListModel {
        id: bottomDockModel
    }

    // Main layout: Top, Middle (Left-Center-Right), Bottom
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Top dock area
        Rectangle {
            id: topDock
            Layout.fillWidth: true
            Layout.preferredHeight: topDockList.count > 0 ? 200 : 0
            visible: topDockList.count > 0
            color: bgLight
            border.color: borderColor
            border.width: topDockList.count > 0 ? 1 : 0

            ListView {
                id: topDockList
                anchors.fill: parent
                anchors.margins: 5
                model: topDockModel
                orientation: ListView.Horizontal
                spacing: 5

                delegate: DockableToolItem {
                    width: 300
                    height: topDock.height - 10
                    toolName: model.name
                    onCloseRequested: {
                        topDockModel.remove(index)
                    }
                }
            }

            // Resize handle
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 4
                color: "transparent"

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeVerCursor
                    onPressed: {
                        topDock.Layout.preferredHeight = topDock.height
                    }
                    onPositionChanged: {
                        if (pressed) {
                            var newHeight = topDock.height + mouse.y
                            if (newHeight >= 100 && newHeight <= 400) {
                                topDock.Layout.preferredHeight = newHeight
                            }
                        }
                    }
                }
            }
        }

        // Middle row: Left dock, Center workspace, Right dock
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Left dock area
            Rectangle {
                id: leftDock
                Layout.preferredWidth: leftDockList.count > 0 ? 300 : 0
                Layout.fillHeight: true
                visible: leftDockList.count > 0
                color: bgLight
                border.color: borderColor
                border.width: leftDockList.count > 0 ? 1 : 0

                ListView {
                    id: leftDockList
                    anchors.fill: parent
                    anchors.margins: 5
                    model: leftDockModel
                    spacing: 5

                    delegate: DockableToolItem {
                        width: leftDock.width - 10
                        height: 250
                        toolName: model.name
                        onCloseRequested: {
                            leftDockModel.remove(index)
                        }
                    }
                }

                // Resize handle
                Rectangle {
                    anchors.right: parent.right
                    width: 4
                    height: parent.height
                    color: "transparent"

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.SizeHorCursor
                        onPressed: {
                            leftDock.Layout.preferredWidth = leftDock.width
                        }
                        onPositionChanged: {
                            if (pressed) {
                                var newWidth = leftDock.width + mouse.x
                                if (newWidth >= 200 && newWidth <= 600) {
                                    leftDock.Layout.preferredWidth = newWidth
                                }
                            }
                        }
                    }
                }
            }

            // Center workspace - for graphs and tables only
            Rectangle {
                id: centerWorkspace
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDark

                Text {
                    anchors.centerIn: parent
                    text: "Central Workspace\n\nGraphs and Tables appear here\n\nUse File → New Graph or New Table"
                    font.pixelSize: 16
                    color: textMuted
                    horizontalAlignment: Text.AlignHCenter
                    lineHeight: 1.8
                }

                // Decorative accent
                Rectangle {
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: -100
                    width: 80
                    height: 4
                    color: accentPink
                    radius: 2
                }
            }

            // Right dock area
            Rectangle {
                id: rightDock
                Layout.preferredWidth: rightDockList.count > 0 ? 300 : 0
                Layout.fillHeight: true
                visible: rightDockList.count > 0
                color: bgLight
                border.color: borderColor
                border.width: rightDockList.count > 0 ? 1 : 0

                ListView {
                    id: rightDockList
                    anchors.fill: parent
                    anchors.margins: 5
                    model: rightDockModel
                    spacing: 5

                    delegate: DockableToolItem {
                        width: rightDock.width - 10
                        height: 250
                        toolName: model.name
                        onCloseRequested: {
                            rightDockModel.remove(index)
                        }
                    }
                }

                // Resize handle
                Rectangle {
                    anchors.left: parent.left
                    width: 4
                    height: parent.height
                    color: "transparent"

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.SizeHorCursor
                        onPressed: {
                            rightDock.Layout.preferredWidth = rightDock.width
                        }
                        onPositionChanged: {
                            if (pressed) {
                                var newWidth = rightDock.width - mouse.x
                                if (newWidth >= 200 && newWidth <= 600) {
                                    rightDock.Layout.preferredWidth = newWidth
                                }
                            }
                        }
                    }
                }
            }
        }

        // Bottom dock area
        Rectangle {
            id: bottomDock
            Layout.fillWidth: true
            Layout.preferredHeight: bottomDockList.count > 0 ? 200 : 0
            visible: bottomDockList.count > 0
            color: bgLight
            border.color: borderColor
            border.width: bottomDockList.count > 0 ? 1 : 0

            ListView {
                id: bottomDockList
                anchors.fill: parent
                anchors.margins: 5
                model: bottomDockModel
                orientation: ListView.Horizontal
                spacing: 5

                delegate: DockableToolItem {
                    width: 300
                    height: bottomDock.height - 10
                    toolName: model.name
                    onCloseRequested: {
                        bottomDockModel.remove(index)
                    }
                }
            }

            // Resize handle
            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 4
                color: "transparent"

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeVerCursor
                    onPressed: {
                        bottomDock.Layout.preferredHeight = bottomDock.height
                    }
                    onPositionChanged: {
                        if (pressed) {
                            var newHeight = bottomDock.height - mouse.y
                            if (newHeight >= 100 && newHeight <= 400) {
                                bottomDock.Layout.preferredHeight = newHeight
                            }
                        }
                    }
                }
            }
        }
    }

    // Public functions for docking tools
    function dockTool(toolName, dockPosition) {
        // dockPosition: "left", "right", "top", "bottom"
        console.log("Docking tool:", toolName, "to", dockPosition)

        switch(dockPosition.toLowerCase()) {
            case "left":
                leftDockModel.append({"name": toolName})
                break
            case "right":
                rightDockModel.append({"name": toolName})
                break
            case "top":
                topDockModel.append({"name": toolName})
                break
            case "bottom":
                bottomDockModel.append({"name": toolName})
                break
            default:
                console.warn("Unknown dock position:", dockPosition)
        }
    }

    function clearDock(dockPosition) {
        switch(dockPosition.toLowerCase()) {
            case "left":
                leftDockModel.clear()
                break
            case "right":
                rightDockModel.clear()
                break
            case "top":
                topDockModel.clear()
                break
            case "bottom":
                bottomDockModel.clear()
                break
            case "all":
                leftDockModel.clear()
                rightDockModel.clear()
                topDockModel.clear()
                bottomDockModel.clear()
                break
        }
    }

    Component.onCompleted: {
        console.log("DockableWorkspace initialized")
    }
}
