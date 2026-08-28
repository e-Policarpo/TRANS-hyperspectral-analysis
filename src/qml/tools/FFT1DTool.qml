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

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Tool description
        Label {
            text: "1D FFT Utility"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Perform Fast Fourier Transform on spectral curves to analyze frequency components."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
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
                    color: textMuted
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
                    color: textMuted
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
                    if (root.closeWindow) { root.closeWindow() } else { var win = Window.window; if (win) win.close() }
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
