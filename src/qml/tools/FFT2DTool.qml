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

// 2D FFT Utility Tool
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
            text: "2D FFT Utility"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Perform 2D Fast Fourier Transform on map/image data to analyze spatial frequencies."
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
            title: "FFT Options"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                Label {
                    text: "Output will be magnitude spectrum in log scale"
                    font.pixelSize: 11
                }

                Label {
                    text: "Low frequencies are at the center of the image"
                    font.pixelSize: 11
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Calculate 2D FFT"
                enabled: imagePathField.text.length > 0
                highlighted: true
                onClicked: performFFT2D()
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

    function performFFT2D() {
        console.log("Performing 2D FFT on:", imagePathField.text)

        var result = backend.fft2D(imagePathField.text)

        if (result) {
            console.log("2D FFT complete, saved to:", result)
        }
    }
}
