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

// Derivative Calculator Tool
Item {
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Derivative Calculator"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Calculate numerical derivatives of spectral data (dI/dV or d²I/dV²)."
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
            title: "Derivative Parameters"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                RowLayout {
                    Label { text: "Derivative Order:" }
                    ComboBox {
                        id: orderCombo
                        Layout.fillWidth: true
                        model: ["First Derivative (dI/dV)", "Second Derivative (d²I/dV²)"]
                    }
                }

                CheckBox {
                    id: smoothBeforeCheck
                    text: "Smooth before differentiation (recommended)"
                    checked: true
                }

                CheckBox {
                    id: smoothAfterCheck
                    text: "Smooth after differentiation (recommended)"
                    checked: true
                }
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "Numerical differentiation amplifies noise.\n" +
                      "Smoothing before and/or after is highly recommended.\n\n" +
                      "Output will be saved as new dataset with prefix dIdV_ or d2IdV2_"
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: "#666666"
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Calculate Derivative"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performDerivative()
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

    function performDerivative() {
        var order = orderCombo.currentIndex + 1
        console.log("Calculating derivative order", order, "for:", datasetCombo.currentText)

        var result = backend.calculateDerivative(
            datasetCombo.currentText,
            order,
            smoothBeforeCheck.checked,
            smoothAfterCheck.checked
        )

        if (result) {
            console.log("Derivative calculation complete, saved to:", result)
        }
    }
}
