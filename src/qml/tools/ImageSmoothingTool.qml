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

// Image Smoothing Tool
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
            text: "Image Smoothing"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Apply smoothing filters to map/image data to reduce noise."
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
            title: "Filter Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2

                Label { text: "Filter Type:" }
                ComboBox {
                    id: filterTypeCombo
                    Layout.fillWidth: true
                    model: ["Gaussian", "Median", "Bilateral"]
                }

                Label { text: "Kernel Size:" }
                SpinBox {
                    id: kernelSizeSpin
                    from: 3
                    to: 21
                    stepSize: 2
                    value: 5
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Apply Filter"
                enabled: imagePathField.text.length > 0
                highlighted: true
                onClicked: performSmoothing()
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

    function performSmoothing() {
        var filterType = ["gaussian", "median", "bilateral"][filterTypeCombo.currentIndex]
        console.log("Smoothing image:", imagePathField.text, "Filter:", filterType)

        var result = backend.smoothImage(
            imagePathField.text,
            filterType,
            kernelSizeSpin.value
        )

        if (result) {
            console.log("Image smoothing complete, saved to:", result)
        }
    }
}
