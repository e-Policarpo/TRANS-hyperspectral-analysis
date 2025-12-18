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
    id: root

    // Theme colors - reactive bindings to parent DraggableWindow
    property var parentWindow: Window.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Derivative Calculator"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Calculate numerical derivatives of spectral data (dI/dV or d²I/dV²)."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
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
                color: textMuted
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
