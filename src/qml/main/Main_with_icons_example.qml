/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

// EXAMPLE: How to add icons to menu items and UI elements
// This file shows the modifications needed to add PNG icons

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: mainWindow
    // ... existing properties ...

    // Menu bar with icons
    menuBar: MenuBar {
        // ... existing styling ...

        Menu {
            title: "File"

            // EXAMPLE 1: MenuItem with icon (left-aligned)
            MenuItem {
                text: "New Project"
                icon.source: "qrc:/icons/menu/file-new.png"  // PNG icon from resources
                icon.color: "transparent"  // Keep original PNG colors
                icon.width: 16
                icon.height: 16
                onTriggered: backend.newProject()
            }

            MenuItem {
                text: "Open Project..."
                icon.source: "qrc:/icons/menu/file-open.png"
                icon.color: "transparent"
                icon.width: 16
                icon.height: 16
                onTriggered: backend.openProject()
            }

            MenuItem {
                text: "Save Project"
                icon.source: "qrc:/icons/menu/file-save.png"
                icon.color: "transparent"
                icon.width: 16
                icon.height: 16
                enabled: backend.hasProject()
                onTriggered: backend.saveProject()
            }

            MenuSeparator { }

            MenuItem {
                text: "Import Measurement..."
                icon.source: "qrc:/icons/menu/import.png"
                icon.color: "transparent"
                icon.width: 16
                icon.height: 16
                onTriggered: importMeasurementDialog.open()
            }

            MenuItem {
                text: "Exit"
                icon.source: "qrc:/icons/menu/exit.png"
                icon.color: "transparent"
                icon.width: 16
                icon.height: 16
                onTriggered: Qt.quit()
            }
        }

        // EXAMPLE 2: Custom MenuItem with icon and custom contentItem
        Menu {
            title: "Window"

            delegate: MenuItem {
                id: windowMenuItem

                contentItem: RowLayout {
                    spacing: 10

                    // Icon
                    Image {
                        source: windowMenuItem.icon.source
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: 16
                        visible: windowMenuItem.icon.source != ""
                    }

                    // Text
                    Text {
                        text: windowMenuItem.text
                        font.pixelSize: 13
                        color: windowMenuItem.enabled ? "#ffffff" : "#cccccc"
                        Layout.fillWidth: true
                    }
                }

                background: Rectangle {
                    color: windowMenuItem.highlighted ? "#F5A9B8" : "transparent"
                    opacity: windowMenuItem.highlighted ? 0.3 : 1
                }
            }

            MenuItem {
                text: "Toggle Project Browser"
                icon.source: "qrc:/icons/menu/browser.png"
                checkable: true
                onTriggered: { /* ... */ }
            }

            MenuItem {
                text: "Toggle Debug Console"
                icon.source: "qrc:/icons/menu/console.png"
                checkable: true
                onTriggered: { /* ... */ }
            }
        }
    }

    // EXAMPLE 3: Toolbar buttons with icons
    Rectangle {
        id: toolbar
        width: parent.width
        height: 40
        color: "#2a2a3e"

        RowLayout {
            anchors.fill: parent
            anchors.margins: 5
            spacing: 5

            // Button with icon only
            Button {
                text: ""  // No text, icon only
                icon.source: "qrc:/icons/toolbar/add.png"
                icon.color: "transparent"
                icon.width: 20
                icon.height: 20
                ToolTip.visible: hovered
                ToolTip.text: "Add Item"
                onClicked: { /* ... */ }
            }

            // Button with icon and text
            Button {
                text: "Refresh"
                icon.source: "qrc:/icons/toolbar/refresh.png"
                icon.color: "transparent"
                icon.width: 18
                icon.height: 18
                display: AbstractButton.TextBesideIcon  // Icon beside text
                onClicked: { /* ... */ }
            }

            // Button with icon using Image component
            Button {
                contentItem: RowLayout {
                    spacing: 5
                    Image {
                        source: "qrc:/icons/toolbar/play.png"
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                    }
                    Text {
                        text: "Start"
                        color: "#ffffff"
                        font.pixelSize: 13
                    }
                }
                onClicked: { /* ... */ }
            }
        }
    }

    // EXAMPLE 4: Icons in lists (ProjectBrowser style)
    ListView {
        id: exampleList
        model: ["Dataset 1", "Dataset 2", "Dataset 3"]

        delegate: Item {
            width: parent.width
            height: 30

            RowLayout {
                anchors.fill: parent
                spacing: 5

                // Icon
                Image {
                    source: "qrc:/icons/general/dataset.png"
                    Layout.preferredWidth: 16
                    Layout.preferredHeight: 16
                }

                // Text
                Text {
                    text: modelData
                    color: "#ffffff"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }
        }
    }

    // EXAMPLE 5: Status icons in status bar
    Rectangle {
        id: statusBar
        width: parent.width
        height: 30
        color: "#0d0d1a"

        RowLayout {
            anchors.fill: parent
            anchors.margins: 5
            spacing: 10

            // Status icon that changes based on state
            Image {
                source: {
                    if (backend.hasError) return "qrc:/icons/status/error.png"
                    if (backend.hasWarning) return "qrc:/icons/status/warning.png"
                    if (backend.isBusy) return "qrc:/icons/status/info.png"
                    return "qrc:/icons/status/success.png"
                }
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
            }

            Text {
                text: backend.status
                color: "#ffffff"
                font.pixelSize: 12
                Layout.fillWidth: true
            }
        }
    }

    // EXAMPLE 6: TabButton with icons
    TabBar {
        TabButton {
            text: "STS Analysis"
            icon.source: "qrc:/icons/general/graph.png"
            icon.color: "transparent"
            icon.width: 18
            icon.height: 18
            display: AbstractButton.TextBesideIcon
        }

        TabButton {
            text: "Map Editor"
            icon.source: "qrc:/icons/general/map.png"
            icon.color: "transparent"
            icon.width: 18
            icon.height: 18
            display: AbstractButton.TextBesideIcon
        }
    }
}
