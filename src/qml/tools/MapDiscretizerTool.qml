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
import QtQuick.Dialogs
import QtQuick.Window 2.15
import "../components"   // the Theme singleton

// Map Discretizer Tool
Item {
    id: root
    property var closeWindow: null

    // Theme colors - reactive bindings to parent DraggableWindow
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    FileDialog {
        id: imageFileDialog
        title: "Select Map Image"
        nameFilters: ["Image files (*.png *.jpg *.tiff *.tif)", "All files (*)"]
        onAccepted: {
            imagePathField.text = imageFileDialog.selectedFile.toString().replace("file://", "")
            updatePreview()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Map Discretizer"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Reduce spatial resolution of map images by averaging pixel blocks."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Image Selection"
            Layout.fillWidth: true

            RowLayout {
                anchors.fill: parent

                TextField {
                    // A bare TextField takes the style's own palette, which under the
                    // Basic style is a light one — white ground, black text — regardless
                    // of what the window around it is painted. Say it explicitly.
                    color: root.textLight
                    placeholderTextColor: root.textMuted
                    background: Rectangle {
                        color: root.bgDark
                        border.color: root.bgLight
                        border.width: 1
                        radius: 4
                    }
                    id: imagePathField
                    Layout.fillWidth: true
                    placeholderText: "Select map image..."
                    readOnly: true
                }

                Button {
                    text: "Browse..."
                    onClicked: imageFileDialog.open()
                }
            }
        }

        GroupBox {
            title: "Discretization Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: "Target Size X:" }
                TextField {
                    // A bare TextField takes the style's own palette, which under the
                    // Basic style is a light one — white ground, black text — regardless
                    // of what the window around it is painted. Say it explicitly.
                    color: root.textLight
                    placeholderTextColor: root.textMuted
                    background: Rectangle {
                        color: root.bgDark
                        border.color: root.bgLight
                        border.width: 1
                        radius: 4
                    }
                    id: targetXField
                    Layout.preferredWidth: 80
                    text: "50"
                    horizontalAlignment: Text.AlignHCenter
                    validator: IntValidator { bottom: 1; top: 9999 }
                    selectByMouse: true
                    onTextChanged: updatePreview()
                }

                Label { text: "Target Size Y:" }
                TextField {
                    // A bare TextField takes the style's own palette, which under the
                    // Basic style is a light one — white ground, black text — regardless
                    // of what the window around it is painted. Say it explicitly.
                    color: root.textLight
                    placeholderTextColor: root.textMuted
                    background: Rectangle {
                        color: root.bgDark
                        border.color: root.bgLight
                        border.width: 1
                        radius: 4
                    }
                    id: targetYField
                    Layout.preferredWidth: 80
                    text: "50"
                    horizontalAlignment: Text.AlignHCenter
                    validator: IntValidator { bottom: 1; top: 9999 }
                    selectByMouse: true
                    onTextChanged: updatePreview()
                }
            }
        }

        GroupBox {
            title: "Preview"
            Layout.fillWidth: true

            Label {
                id: previewLabel
                text: updatePreview()
                wrapMode: Text.Wrap
                font.pixelSize: 10
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Discretize Map"
                enabled: imagePathField.text.length > 0
                highlighted: true
                onClicked: performDiscretization()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() } else { var win = Window.window; if (win) win.close() }
                }
            }
        }
    }

    function updatePreview() {
        if (imagePathField.text.length === 0) {
            return "No image selected"
        }

        var targetX = parseInt(targetXField.text) || 50
        var targetY = parseInt(targetYField.text) || 50

        var info = "Target grid: " + targetX + " x " + targetY + "\n"
        info += "Pixels will be averaged to reduce resolution"

        return info
    }

    function performDiscretization() {
        var targetX = parseInt(targetXField.text) || 50
        var targetY = parseInt(targetYField.text) || 50

        console.log("Discretizing map:", imagePathField.text,
                   "Target:", targetX, "x", targetY)

        var result = backend.discretizeMap(
            imagePathField.text,
            targetX,
            targetY
        )

        if (result) {
            console.log("Map discretization complete, saved to:", result)
            // Auto-load result into map editor
            backend.requestLoadMapInEditor(result)
        }
    }
}
