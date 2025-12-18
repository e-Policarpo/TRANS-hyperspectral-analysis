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

// Map Discretizer Tool
Item {
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
        }

        Label {
            text: "Reduce spatial resolution of map images by averaging pixel blocks."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#9B4F96"
        }

        GroupBox {
            title: "Image Selection"
            Layout.fillWidth: true

            RowLayout {
                anchors.fill: parent

                TextField {
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
                    var win = Window.window
                    if (win) win.close()
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
