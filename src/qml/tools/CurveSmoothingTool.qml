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

// Curve Smoothing Tool
Item {
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Curve Smoothing"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Apply smoothing filters to spectral curves to reduce noise."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#9B4F96"
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                }
            }
        }

        GroupBox {
            title: "Smoothing Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 10
                columnSpacing: 10

                Label { text: "Smoothing Type:" }
                ComboBox {
                    id: smoothingTypeCombo
                    Layout.fillWidth: true
                    model: ["Savitzky-Golay", "Moving Average", "Gaussian"]
                    currentIndex: 0
                }

                Label { text: "Window Size:" }
                SpinBox {
                    id: windowSizeSpin
                    from: 3
                    to: 51
                    stepSize: 2
                    value: 11
                    editable: true
                }

                Label {
                    text: "Polynomial Order:"
                    visible: smoothingTypeCombo.currentIndex === 0
                }
                SpinBox {
                    id: polyOrderSpin
                    from: 1
                    to: 5
                    value: 3
                    visible: smoothingTypeCombo.currentIndex === 0
                }
            }
        }

        GroupBox {
            title: "Preview"
            Layout.fillWidth: true

            Label {
                text: "Smoothing method: " + getSmoothingMethod() +
                      "\nWindow size: " + windowSizeSpin.value +
                      (smoothingTypeCombo.currentIndex === 0 ? "\nPolynomial order: " + polyOrderSpin.value : "")
                wrapMode: Text.Wrap
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Apply Smoothing"
                enabled: datasetCombo.currentIndex >= 0
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

    function getSmoothingMethod() {
        var types = ["savgol", "moving_average", "gaussian"]
        return types[smoothingTypeCombo.currentIndex]
    }

    function performSmoothing() {
        console.log("Smoothing:", datasetCombo.currentText,
                   "Method:", getSmoothingMethod(),
                   "Window:", windowSizeSpin.value)

        var result = backend.smoothCurves(
            datasetCombo.currentText,
            windowSizeSpin.value,
            polyOrderSpin.value,
            getSmoothingMethod()
        )

        if (result) {
            console.log("Smoothing complete, saved to:", result)
        }
    }
}
