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

// Curve Fitting Tool
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

        Label {
            text: "Curve Fitting Utility"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Fit baseline to spectral curves and subtract it to obtain corrected data."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            DatasetComboBox {
                id: datasetCombo
                Layout.fillWidth: true
                model: backend.getDatasetList()
            }
        }

        GroupBox {
            title: "Fitting Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2

                Label { text: "Fit Type:" }
                ComboBox {
                    id: fitTypeCombo
                    Layout.fillWidth: true
                    model: ["Polynomial", "Linear", "Exponential"]
                    onCurrentIndexChanged: updateDegreeVisibility()
                }

                Label {
                    id: degreeLabel
                    text: "Polynomial Degree:"
                    visible: fitTypeCombo.currentIndex === 0
                }
                SpinBox {
                    id: degreeSpin
                    from: 1
                    to: 10
                    value: 2
                    visible: fitTypeCombo.currentIndex === 0
                }

                Label {
                    id: basisLabel
                    text: "Coefficient Basis:"
                    visible: fitTypeCombo.currentIndex === 0
                }
                ComboBox {
                    id: basisCombo
                    Layout.fillWidth: true
                    model: ["power", "legendre", "chebyshev"]
                    visible: fitTypeCombo.currentIndex === 0
                    // Same fitted curve either way; the orthogonal bases give
                    // decorrelated coefficients that compare across spectra.
                }
            }
        }

        GroupBox {
            title: "Output"
            Layout.fillWidth: true

            Label {
                text: "Two files will be generated:\n" +
                      "1. Fit parameters (CSV)\n" +
                      "2. Baseline-corrected spectra (NoBaseline_...csv)\n\n" +
                      "Corrected data will be added as new dataset."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Fit and Subtract Baseline"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performFitting()
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

    function updateDegreeVisibility() {
        degreeLabel.visible = fitTypeCombo.currentIndex === 0
        degreeSpin.visible = fitTypeCombo.currentIndex === 0
        basisLabel.visible = fitTypeCombo.currentIndex === 0
        basisCombo.visible = fitTypeCombo.currentIndex === 0
    }

    function performFitting() {
        var fitType = ["polynomial", "linear", "exponential"][fitTypeCombo.currentIndex]
        console.log("Fitting curves:",
                   "Type:", fitType, "Degree:", degreeSpin.value)

        var result = backend.fitCurves(
            datasetCombo.currentText,
            fitType,
            degreeSpin.value,
            basisCombo.currentText
        )

        if (result) {
            console.log("Curve fitting complete, saved to:", result)
        }
    }
}
