/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Detect Bandgap & Doping Tool
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

// Detect Bandgap & Doping Tool
Item {
    id: root
    property var closeWindow: null

    // Theme colors
    // `Window.window`, not `ApplicationWindow.window`: a tool is hosted
    // either by the embedded window (whose root IS the ApplicationWindow) or
    // by ToolWindow, whose root is a plain Window. The ApplicationWindow
    // attached property resolves to null in the second case, and every colour
    // below then falls through to the singleton instead of following the
    // host. Window.window resolves in both.
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

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
            text: "Detect Bandgap & Doping"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Determine bandgap size and doping type (N/P/Neutral) per spectrum from I-V curves."
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
            title: "Smoothing"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 3

                Label { text: "Method:"; color: textLight }
                ComboBox {
                    id: smoothMethodCombo
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    model: ["Savgol", "Moving Avg", "None"]
                    currentIndex: 0
                }

                Label { text: "Amount (%):"; color: textLight }
                Slider {
                    id: smoothSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 50
                    value: 1.0
                    stepSize: 0.5
                }
                Label { text: smoothSlider.value.toFixed(1); color: textMuted; Layout.preferredWidth: 35 }
            }
        }

        GroupBox {
            title: "Detection Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 3

                Label { text: "Delta (%):"; color: textLight }
                Slider {
                    id: deltaSlider
                    Layout.fillWidth: true
                    from: 0.1
                    to: 100
                    value: 5.0
                    stepSize: 0.5
                }
                Label { text: deltaSlider.value.toFixed(1); color: textMuted; Layout.preferredWidth: 35 }

                Label { text: "Doping Offset\nTolerance (V):"; color: textLight }
                Slider {
                    id: resolutionSlider
                    Layout.fillWidth: true
                    from: 0.001
                    to: 1.0
                    value: 0.01
                    stepSize: 0.001
                }
                Label { text: resolutionSlider.value.toFixed(3); color: textMuted; Layout.preferredWidth: 45 }

                Label {
                    text: "Spectra with bandgap center offset smaller than this value are classified as Neutral (undoped)."
                    wrapMode: Text.Wrap
                    font.pixelSize: 10
                    color: textMuted
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                }
            }
        }

        GroupBox {
            title: "Doping Classification"
            Layout.fillWidth: true

            Label {
                text: "N-type (electron-doped): Bandgap center shifted to negative voltages\n" +
                      "P-type (hole-doped): Bandgap center shifted to positive voltages\n" +
                      "Neutral: Bandgap centered near zero (within tolerance)\n\n" +
                      "Output: Two datasets (Bandgap and Doping).\n" +
                      "Doping Type column uses -1 (N), 0 (Neutral), +1 (P) for map visualization."
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
                text: "Analyze"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performAnalysis()
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
            if (toolName === "Detect Bandgap & Doping") {
                statusLabel.text = "Analysis complete. Output dataset available for Map Generator."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Bandgap") >= 0) {
                statusLabel.text = "Error: " + message
            }
        }
    }

    function performAnalysis() {
        statusLabel.text = "Analyzing..."
        console.log("Detecting bandgap/doping for:", datasetCombo.currentText)

        backend.detectBandgapDoping(
            datasetCombo.currentText,
            smoothSlider.value,
            deltaSlider.value,
            resolutionSlider.value,
            smoothMethodCombo.currentText
        )
    }
}
