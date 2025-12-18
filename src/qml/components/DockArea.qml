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

// Dock area with tabbed interface for multiple windows
Rectangle {
    id: dockArea

    property string dockPosition: "left"  // left, right, top, bottom, center
    property var windowList: []  // List of window IDs in this dock
    property string activeWindowId: ""

    signal tabCloseRequested(string windowId)
    signal tabActivated(string windowId)
    signal windowDropped(string windowId)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    color: bgDark
    border.color: borderColor
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Tab bar
        Rectangle {
            id: tabBar
            Layout.fillWidth: true
            Layout.preferredHeight: dockArea.windowList.length > 0 ? 35 : 0
            visible: dockArea.windowList.length > 0
            color: bgLight

            ScrollView {
                anchors.fill: parent
                clip: true

                Row {
                    spacing: 2
                    padding: 2

                    Repeater {
                        model: dockArea.windowList

                        Rectangle {
                            width: 150
                            height: 31
                            color: modelData === dockArea.activeWindowId ? accentPink : bgDark
                            opacity: modelData === dockArea.activeWindowId ? 0.3 : 1
                            radius: 3

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 4

                                Text {
                                    text: getWindowTitle(modelData)
                                    font.pixelSize: 12
                                    color: textLight
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                Button {
                                    text: "×"
                                    Layout.preferredWidth: 20
                                    Layout.preferredHeight: 20
                                    font.pixelSize: 14

                                    onClicked: {
                                        dockArea.tabCloseRequested(modelData)
                                    }

                                    background: Rectangle {
                                        color: parent.pressed ? accentPink : (parent.hovered ? "#3a3a4e" : "transparent")
                                        radius: 2
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

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    dockArea.activeWindowId = modelData
                                    dockArea.tabActivated(modelData)
                                }
                                // Prevent button click from propagating
                                propagateComposedEvents: true
                                onPressed: mouse.accepted = false
                            }
                        }
                    }
                }
            }
        }

        // Content area
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark

            // Drop zone overlay (shown during drag)
            Rectangle {
                id: dropZoneOverlay
                anchors.fill: parent
                color: accentPink
                opacity: 0
                visible: opacity > 0
                border.color: "#ffffff"
                border.width: 2

                Text {
                    anchors.centerIn: parent
                    text: "Drop here to dock"
                    font.pixelSize: 16
                    font.bold: true
                    color: textLight
                }

                Behavior on opacity {
                    NumberAnimation { duration: 150 }
                }
            }

            DropArea {
                id: dropArea
                anchors.fill: parent

                onEntered: (drag) => {
                    dropZoneOverlay.opacity = 0.3
                }

                onExited: {
                    dropZoneOverlay.opacity = 0
                }

                onDropped: (drop) => {
                    dropZoneOverlay.opacity = 0
                    if (drop.hasText) {
                        var windowId = drop.text
                        dockArea.windowDropped(windowId)
                    }
                }
            }

            // Active window content
            Loader {
                id: contentLoader
                anchors.fill: parent
                anchors.margins: 5

                source: {
                    if (!dockArea.activeWindowId) return ""
                    // Load the appropriate window component
                    return getWindowSource(dockArea.activeWindowId)
                }

                onStatusChanged: {
                    if (status === Loader.Error) {
                        console.error("Failed to load window:", dockArea.activeWindowId)
                    }
                }
            }

            // Placeholder when no windows
            Text {
                anchors.centerIn: parent
                visible: dockArea.windowList.length === 0
                text: getDockPlaceholderText()
                font.pixelSize: 13
                color: textMuted
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    function getWindowTitle(windowId) {
        if (!backend || !backend.dockManager) return windowId

        var state = backend.dockManager.getWindowState(windowId)
        return state.title || windowId
    }

    function getWindowSource(windowId) {
        // Return empty for now - windows are managed externally
        // This would load tool/graph/table components
        return ""
    }

    function getDockPlaceholderText() {
        switch(dockPosition) {
            case "center":
                return "Central Workspace\n\nDrag graphs and tables here\nOr use File → New Graph / New Table"
            case "left":
                return "Left Dock\n\nDrag windows here"
            case "right":
                return "Right Dock\n\nDrag windows here"
            case "top":
                return "Top Dock\n\nDrag windows here"
            case "bottom":
                return "Bottom Dock\n\nDrag windows here"
            default:
                return "Drop windows here"
        }
    }

    function addWindow(windowId) {
        if (windowList.indexOf(windowId) === -1) {
            var newList = windowList.slice()
            newList.push(windowId)
            windowList = newList
            activeWindowId = windowId
        }
    }

    function removeWindow(windowId) {
        var newList = []
        for (var i = 0; i < windowList.length; i++) {
            if (windowList[i] !== windowId) {
                newList.push(windowList[i])
            }
        }
        windowList = newList

        // Set new active tab
        if (activeWindowId === windowId && windowList.length > 0) {
            activeWindowId = newList[0]
        }
    }

    function refresh() {
        if (!backend || !backend.dockManager) return

        var docked = backend.dockManager.getDockedWindows(dockPosition)
        windowList = docked

        var active = backend.dockManager.getActiveTab(dockPosition)
        if (active) {
            activeWindowId = active
        } else if (windowList.length > 0) {
            activeWindowId = windowList[0]
        }
    }
}
