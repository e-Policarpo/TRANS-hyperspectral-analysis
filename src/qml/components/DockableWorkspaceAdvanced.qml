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

// Advanced dockable workspace with drag-to-edge detection and tabbed dock areas
Rectangle {
    id: workspace

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    color: bgDark

    // Edge drop zone properties
    property int dropZoneSize: 80
    property bool showDropZones: false

    // Signals
    signal windowDocked(string windowId, string position)

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Top dock area
        DockArea {
            id: topDock
            Layout.fillWidth: true
            Layout.preferredHeight: windowList.length > 0 ? 200 : 0
            Layout.minimumHeight: windowList.length > 0 ? 100 : 0
            Layout.maximumHeight: 400
            visible: windowList.length > 0
            dockPosition: "top"

            onTabCloseRequested: (windowId) => {
                backend.dockManager.closeWindow(windowId)
                refresh()
            }

            onTabActivated: (windowId) => {
                backend.dockManager.setActiveTab("top", windowId)
            }

            onWindowDropped: (windowId) => {
                handleWindowDrop(windowId, "top")
            }
        }

        // Main row: left + center + right
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Left dock area
            DockArea {
                id: leftDock
                Layout.fillHeight: true
                Layout.preferredWidth: windowList.length > 0 ? 300 : 0
                Layout.minimumWidth: windowList.length > 0 ? 200 : 0
                Layout.maximumWidth: 600
                visible: windowList.length > 0
                dockPosition: "left"

                onTabCloseRequested: (windowId) => {
                    backend.dockManager.closeWindow(windowId)
                    refresh()
                }

                onTabActivated: (windowId) => {
                    backend.dockManager.setActiveTab("left", windowId)
                }

                onWindowDropped: (windowId) => {
                    handleWindowDrop(windowId, "left")
                }
            }

            // Center workspace
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDark
                border.color: borderColor
                border.width: 1

                DockArea {
                    id: centerDock
                    anchors.fill: parent
                    dockPosition: "center"

                    onTabCloseRequested: (windowId) => {
                        backend.dockManager.closeWindow(windowId)
                        refresh()
                    }

                    onTabActivated: (windowId) => {
                        backend.dockManager.setActiveTab("center", windowId)
                    }

                    onWindowDropped: (windowId) => {
                        handleWindowDrop(windowId, "center")
                    }
                }

                // Edge drop zones overlay
                Item {
                    anchors.fill: parent
                    visible: workspace.showDropZones

                    // Left edge drop zone
                    Rectangle {
                        id: leftDropZone
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: workspace.dropZoneSize
                        color: accentPink
                        opacity: 0
                        border.color: textLight
                        border.width: 2

                        Text {
                            anchors.centerIn: parent
                            text: "◄\nDock\nLeft"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        DropArea {
                            anchors.fill: parent
                            onEntered: (drag) => { parent.opacity = 0.5 }
                            onExited: { parent.opacity = 0 }
                            onDropped: (drop) => {
                                parent.opacity = 0
                                if (drop.hasText) {
                                    handleWindowDrop(drop.text, "left")
                                }
                            }
                        }
                    }

                    // Right edge drop zone
                    Rectangle {
                        id: rightDropZone
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: workspace.dropZoneSize
                        color: accentPink
                        opacity: 0
                        border.color: textLight
                        border.width: 2

                        Text {
                            anchors.centerIn: parent
                            text: "►\nDock\nRight"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        DropArea {
                            anchors.fill: parent
                            onEntered: (drag) => { parent.opacity = 0.5 }
                            onExited: { parent.opacity = 0 }
                            onDropped: (drop) => {
                                parent.opacity = 0
                                if (drop.hasText) {
                                    handleWindowDrop(drop.text, "right")
                                }
                            }
                        }
                    }

                    // Top edge drop zone
                    Rectangle {
                        id: topDropZone
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: workspace.dropZoneSize
                        color: accentPink
                        opacity: 0
                        border.color: textLight
                        border.width: 2

                        Text {
                            anchors.centerIn: parent
                            text: "▲ Dock Top"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                        }

                        DropArea {
                            anchors.fill: parent
                            onEntered: (drag) => { parent.opacity = 0.5 }
                            onExited: { parent.opacity = 0 }
                            onDropped: (drop) => {
                                parent.opacity = 0
                                if (drop.hasText) {
                                    handleWindowDrop(drop.text, "top")
                                }
                            }
                        }
                    }

                    // Bottom edge drop zone
                    Rectangle {
                        id: bottomDropZone
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: workspace.dropZoneSize
                        color: accentPink
                        opacity: 0
                        border.color: textLight
                        border.width: 2

                        Text {
                            anchors.centerIn: parent
                            text: "▼ Dock Bottom"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                        }

                        DropArea {
                            anchors.fill: parent
                            onEntered: (drag) => { parent.opacity = 0.5 }
                            onExited: { parent.opacity = 0 }
                            onDropped: (drop) => {
                                parent.opacity = 0
                                if (drop.hasText) {
                                    handleWindowDrop(drop.text, "bottom")
                                }
                            }
                        }
                    }

                    // Center drop zone
                    Rectangle {
                        anchors.centerIn: parent
                        width: 120
                        height: 120
                        color: accentPink
                        opacity: 0
                        radius: 60
                        border.color: textLight
                        border.width: 2

                        Text {
                            anchors.centerIn: parent
                            text: "Dock\nCenter"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }

                        DropArea {
                            anchors.fill: parent
                            onEntered: (drag) => { parent.opacity = 0.5 }
                            onExited: { parent.opacity = 0 }
                            onDropped: (drop) => {
                                parent.opacity = 0
                                if (drop.hasText) {
                                    handleWindowDrop(drop.text, "center")
                                }
                            }
                        }
                    }
                }
            }

            // Right dock area
            DockArea {
                id: rightDock
                Layout.fillHeight: true
                Layout.preferredWidth: windowList.length > 0 ? 300 : 0
                Layout.minimumWidth: windowList.length > 0 ? 200 : 0
                Layout.maximumWidth: 600
                visible: windowList.length > 0
                dockPosition: "right"

                onTabCloseRequested: (windowId) => {
                    backend.dockManager.closeWindow(windowId)
                    refresh()
                }

                onTabActivated: (windowId) => {
                    backend.dockManager.setActiveTab("right", windowId)
                }

                onWindowDropped: (windowId) => {
                    handleWindowDrop(windowId, "right")
                }
            }
        }

        // Bottom dock area
        DockArea {
            id: bottomDock
            Layout.fillWidth: true
            Layout.preferredHeight: windowList.length > 0 ? 200 : 0
            Layout.minimumHeight: windowList.length > 0 ? 100 : 0
            Layout.maximumHeight: 400
            visible: windowList.length > 0
            dockPosition: "bottom"

            onTabCloseRequested: (windowId) => {
                backend.dockManager.closeWindow(windowId)
                refresh()
            }

            onTabActivated: (windowId) => {
                backend.dockManager.setActiveTab("bottom", windowId)
            }

            onWindowDropped: (windowId) => {
                handleWindowDrop(windowId, "bottom")
            }
        }
    }

    // Functions
    function handleWindowDrop(windowId, position) {
        console.log("Docking window", windowId, "to", position)
        if (backend && backend.dockManager) {
            backend.dockManager.dockWindow(windowId, position)
            workspace.windowDocked(windowId, position)
            refresh()
        }
    }

    function refresh() {
        leftDock.refresh()
        rightDock.refresh()
        topDock.refresh()
        bottomDock.refresh()
        centerDock.refresh()
    }

    function enableDropZones(enable) {
        workspace.showDropZones = enable
    }

    // Connect to backend signals
    Connections {
        target: backend.dockManager
        function onLayoutChanged() {
            workspace.refresh()
        }
    }

    Component.onCompleted: {
        refresh()
    }
}
