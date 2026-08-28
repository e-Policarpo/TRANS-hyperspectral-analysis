/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Cosmic Ray / Hot Pixel Filter — remove narrow CCD spikes from luminescence
 * and Raman spectra before peak finding / fitting / integration.
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

Item {
    id: root
    property var closeWindow: null

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
            text: "Cosmic Ray Filter"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Remove narrow, very-intense CCD spikes (cosmic-ray hits, hot pixels) " +
                  "that smoothing leaves behind and that confuse peak finding."
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
                model: backend ? backend.getDatasetList() : []
            }
        }

        GroupBox {
            title: "Detection Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                columnSpacing: 8
                rowSpacing: 6

                Label { text: "Threshold (σ):"; color: textLight }
                SpinBox {
                    id: thresholdSpin
                    from: 30
                    to: 200
                    value: 50  // → 5.0σ
                    property real realValue: value / 10.0
                    textFromValue: function(v) { return (v / 10.0).toFixed(1) }
                }

                Label { text: "Median window (samples):"; color: textLight }
                SpinBox {
                    id: windowSpin
                    from: 3
                    to: 21
                    stepSize: 2
                    value: 5
                }

                Label { text: "Max spike width (samples):"; color: textLight }
                SpinBox {
                    id: maxWidthSpin
                    from: 1
                    to: 5
                    value: 2
                }

                Label {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "A sample is flagged when it exceeds the local median by more than " +
                          "Threshold × σ (σ estimated from MAD of the median residuals). " +
                          "Connected runs of flagged samples wider than Max spike width are kept " +
                          "(they are likely real, narrow peaks)."
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

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
            if (toolName === "Cosmic Ray Filter") {
                statusLabel.text = "Done. A '- CR Cleaned' dataset has been added to the browser."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Cosmic") >= 0) {
                statusLabel.text = "Error: " + message
            }
        }
    }

    function performFilter() {
        statusLabel.text = "Filtering cosmic rays..."
        backend.cosmicRayFilter(
            datasetCombo.currentText,
            thresholdSpin.realValue,
            windowSpin.value,
            maxWidthSpin.value
        )
    }
}
