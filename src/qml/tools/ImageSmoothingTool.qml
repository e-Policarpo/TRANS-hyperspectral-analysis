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

// Image Smoothing Tool
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
            text: "Image Smoothing"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Apply smoothing filters to map/image data to reduce noise."
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
                    var win = Window.window
                    if (win) win.close()
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
