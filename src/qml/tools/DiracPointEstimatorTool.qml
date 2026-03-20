/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Dirac Point Estimator Tool
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

// Dirac Point Estimator Tool
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
            text: "Dirac Point Estimator"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Estimate the Dirac point from linear slope intersections in LDOS curves."
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
            title: "Fit Range Detection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                CheckBox {
                    id: autoDetectCheck
                    text: "Auto-detect fit ranges"
                    checked: true
                    Layout.fillWidth: true
                }

                Label {
                    text: "Automatically determines fit ranges from bandgap edges per spectrum."
                    wrapMode: Text.Wrap
                    font.pixelSize: 10
                    color: textMuted
                    visible: autoDetectCheck.checked
                    Layout.fillWidth: true
                }
            }
        }

        GroupBox {
            title: "Left Fit Range (V)"
            Layout.fillWidth: true
            enabled: !autoDetectCheck.checked
            opacity: autoDetectCheck.checked ? 0.5 : 1.0

            GridLayout {
                anchors.fill: parent
                columns: 4

                Label { text: "Min:"; color: textLight }
                SpinBox {
                    id: leftMinSpin
                    Layout.fillWidth: true
                    from: -10000
                    to: 10000
                    value: -1000
                    stepSize: 100
                    editable: true
                    property real realValue: value / 1000.0
                    textFromValue: function(value) { return (value / 1000.0).toFixed(3) }
                    valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) }
                }

                Label { text: "Max:"; color: textLight }
                SpinBox {
                    id: leftMaxSpin
                    Layout.fillWidth: true
                    from: -10000
                    to: 10000
                    value: -200
                    stepSize: 100
                    editable: true
                    property real realValue: value / 1000.0
                    textFromValue: function(value) { return (value / 1000.0).toFixed(3) }
                    valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) }
                }
            }
        }

        GroupBox {
            title: "Right Fit Range (V)"
            Layout.fillWidth: true
            enabled: !autoDetectCheck.checked
            opacity: autoDetectCheck.checked ? 0.5 : 1.0

            GridLayout {
                anchors.fill: parent
                columns: 4

                Label { text: "Min:"; color: textLight }
                SpinBox {
                    id: rightMinSpin
                    Layout.fillWidth: true
                    from: -10000
                    to: 10000
                    value: 200
                    stepSize: 100
                    editable: true
                    property real realValue: value / 1000.0
                    textFromValue: function(value) { return (value / 1000.0).toFixed(3) }
                    valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) }
                }

                Label { text: "Max:"; color: textLight }
                SpinBox {
                    id: rightMaxSpin
                    Layout.fillWidth: true
                    from: -10000
                    to: 10000
                    value: 1000
                    stepSize: 100
                    editable: true
                    property real realValue: value / 1000.0
                    textFromValue: function(value) { return (value / 1000.0).toFixed(3) }
                    valueFromText: function(text) { return Math.round(parseFloat(text) * 1000) }
                }
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "Fits linear slopes in the left and right voltage ranges,\n" +
                      "then finds their intersection (Dirac point).\n\n" +
                      "Output is flat_data. Use Map Generator to visualize\n" +
                      "Dirac Voltage (V) or Dirac LDOS as spatial maps."
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
                text: "Estimate"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performEstimate()
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
            if (toolName === "Dirac Point Estimator") {
                statusLabel.text = "Estimation complete. Output dataset available for Map Generator."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Dirac") >= 0) {
                statusLabel.text = "Error: " + message
            }
        }
    }

    function performEstimate() {
        statusLabel.text = "Estimating..."
        console.log("Estimating Dirac point for:", datasetCombo.currentText,
                     "auto_detect:", autoDetectCheck.checked)

        backend.estimateDiracPoint(
            datasetCombo.currentText,
            leftMinSpin.realValue,
            leftMaxSpin.realValue,
            rightMinSpin.realValue,
            rightMaxSpin.realValue,
            smoothSlider.value,
            smoothMethodCombo.currentText,
            autoDetectCheck.checked
        )
    }
}
