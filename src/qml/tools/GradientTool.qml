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

// Gradient Filter Tool
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
        title: "Select Image File"
        nameFilters: ["Image files (*.png *.jpg *.tiff *.tif)", "All files (*)"]
        onAccepted: {
            imagePathField.text = imageFileDialog.selectedFile.toString().replace("file://", "")
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Gradient Filter"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Apply edge detection / gradient filter to emphasize features in map data."
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
                    placeholderText: "Select image file..."
                    readOnly: true
                }

                Button {
                    text: "Browse..."
                    onClicked: imageFileDialog.open()
                }
            }
        }

        GroupBox {
            title: "Gradient Method"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                ComboBox {
                    id: methodCombo
                    Layout.fillWidth: true
                    model: ["Sobel", "Prewitt", "Scharr"]
                }

                Label {
                    text: "Sobel: Standard edge detection\n" +
                          "Prewitt: Similar to Sobel, simpler\n" +
                          "Scharr: Better rotational symmetry"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                    color: textMuted
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Apply Gradient"
                enabled: imagePathField.text.length > 0
                highlighted: true
                onClicked: performGradient()
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

    function performGradient() {
        var method = methodCombo.currentText.toLowerCase()
        console.log("Applying gradient filter:", method, "to:", imagePathField.text)

        var result = backend.applyGradientFilter(
            imagePathField.text,
            method
        )

        if (result) {
            console.log("Gradient filter complete, saved to:", result)
        }
    }
}
