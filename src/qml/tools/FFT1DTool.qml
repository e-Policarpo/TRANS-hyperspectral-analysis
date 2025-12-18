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
import "../components"

// 1D FFT Utility Tool
Item {
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Tool description
        Label {
            text: "1D FFT Utility"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Perform Fast Fourier Transform on spectral curves to analyze frequency components."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#9B4F96"
        }

        // Dataset selection
        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 5

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                }

                Label {
                    id: datasetInfo
                    text: getDatasetInfo()
                    font.pixelSize: 10
                    color: "#666666"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        // Info panel
        GroupBox {
            title: "FFT Information"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                Label {
                    text: "The FFT will compute:"
                    font.bold: true
                }

                Label {
                    text: "• Magnitude spectrum (absolute value of FFT)"
                    font.pixelSize: 11
                }

                Label {
                    text: "• Phase spectrum (phase angle of FFT)"
                    font.pixelSize: 11
                }

                Label {
                    text: "• Frequency axis based on data spacing"
                    font.pixelSize: 11
                }

                Label {
                    text: "\nOutput: Two CSV files (magnitude and phase) + New dataset in list"
                    wrapMode: Text.Wrap
                    font.pixelSize: 10
                    color: "#666666"
                }
            }
        }

        // Spacer
        Item { Layout.fillHeight: true }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Calculate FFT"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performFFT()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
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

    function getDatasetInfo() {
        if (datasetCombo.currentIndex < 0) return "No dataset selected"

        var datasetName = datasetCombo.currentText
        var info = backend.getDatasetInfo(datasetName)

        return "Type: " + info.type + " | Spectra: " + info.num_spectra +
               " | Points: " + info.num_points + " | Variable: " + info.independent_var
    }

    function performFFT() {
        console.log("Performing 1D FFT on:", datasetCombo.currentText)

        var result = backend.fft1D(datasetCombo.currentText)

        if (result) {
            console.log("FFT complete, saved to:", result)
        }
    }
}
