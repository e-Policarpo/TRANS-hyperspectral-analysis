/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Filter Bad Data Tool
 * Algorithms adapted from ststools by Rafael Reis (https://github.com/rafinhareis/ststools)
 * Made by Eduarda Policarpo
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: January 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

// Filter Bad Data Tool
Item {
    id: root
    property var closeWindow: null

    // Theme colors
    property var parentWindow: ApplicationWindow.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"

    implicitWidth: mainLayout.implicitWidth + 20
    implicitHeight: mainLayout.implicitHeight + 20

    ColumnLayout {
        id: mainLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Filter Bad Data"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Classify and separate bad spectra using saturation, noise, linear artifact, periodic noise, and partial noise heuristics."
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
                    model: backend ? backend.getDatasetList() : []
                }
            }
        }

        GroupBox {
            title: "Artifact Weights"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 3
                columnSpacing: 8

                Label { text: "Saturation:"; color: textLight }
                Slider {
                    id: satSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    value: 1.0
                    stepSize: 0.05
                }
                Label { text: satSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }

                Label { text: "Noise:"; color: textLight }
                Slider {
                    id: noiseSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    value: 1.0
                    stepSize: 0.05
                }
                Label { text: noiseSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }

                Label { text: "Linear:"; color: textLight }
                Slider {
                    id: linearSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    value: 1.0
                    stepSize: 0.05
                }
                Label { text: linearSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }

                Label { text: "Periodic:"; color: textLight }
                Slider {
                    id: periodicSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    value: 1.0
                    stepSize: 0.05
                }
                Label { text: periodicSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }

                Label { text: "Partial Noise:"; color: textLight }
                Slider {
                    id: partialNoiseSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    value: 1.0
                    stepSize: 0.05
                }
                Label { text: partialNoiseSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }
            }
        }

        GroupBox {
            title: "Quality Threshold"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                RowLayout {
                    Label { text: "Threshold:"; color: textLight }
                    Slider {
                        id: thresholdSlider
                        Layout.fillWidth: true
                        from: 0.0
                        to: 1.0
                        value: 0.5
                        stepSize: 0.05
                    }
                    Label { text: thresholdSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 35 }
                }

                Label {
                    text: "Spectra with max weighted score >= threshold are classified as bad."
                    wrapMode: Text.Wrap
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

        GroupBox {
            title: "Periodic Noise Correction"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                CheckBox {
                    id: correctPeriodicCheck
                    text: "Correct periodic noise in good spectra"
                    checked: false
                    palette.windowText: textLight
                }

                Label {
                    text: "When enabled, sharp FFT peaks are replaced by interpolation,\n" +
                          "removing periodic artifacts from spectra classified as good."
                    wrapMode: Text.Wrap
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "Three output datasets will be created: 'Good Data', 'Bad Data', and 'FFT Spectra'.\n" +
                      "A text report listing flagged spectra is saved to the outputs folder.\n" +
                      "The combined score is the maximum weighted score across all detectors,\n" +
                      "so a single detector firing above threshold is enough to flag a spectrum.\n" +
                      "Set weight to 0 to disable that detector."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        // Status label
        Label {
            id: statusLabel
            text: ""
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentBlue
            visible: text !== ""
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Filter"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performFilter()
            }

            Button {
                text: "Cancel"
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

    Connections {
        target: backend
        enabled: backend !== null
        function onToolCompleted(toolName, outputPath) {
            if (toolName === "Filter Bad Data") {
                statusLabel.text = "Filter complete. Check the project browser for output datasets. See report for details."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Filter") >= 0) {
                statusLabel.text = "Error: " + message
            }
        }
    }

    function performFilter() {
        statusLabel.text = "Filtering..."
        console.log("Filtering bad data for:", datasetCombo.currentText)

        backend.filterBadData(
            datasetCombo.currentText,
            satSlider.value,
            noiseSlider.value,
            linearSlider.value,
            periodicSlider.value,
            partialNoiseSlider.value,
            thresholdSlider.value,
            correctPeriodicCheck.checked
        )
    }
}
