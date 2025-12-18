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

// Gradient Filter Tool
Item {
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
        }

        Label {
            text: "Apply edge detection / gradient filter to emphasize features in map data."
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
                    color: "#666666"
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
                    var win = Window.window
                    if (win) win.close()
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
