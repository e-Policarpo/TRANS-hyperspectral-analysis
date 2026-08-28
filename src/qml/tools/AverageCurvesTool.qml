/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: January 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

// Average Curves Tool
// Computes the arithmetic mean of all spectra in a dataset,
// producing a single averaged spectrum as output.
Item {
    id: averageCurvesTool
    property var closeWindow: null

    // Theme colors - reactive bindings to parent window
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
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color successColor: (parentWindow && parentWindow.successColor !== undefined) ? parentWindow.successColor : Theme.successColor

    // Define implicit size for proper scrolling
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
            text: "Average Curves"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Compute the arithmetic mean of all spectra in the selected dataset, producing a single averaged spectrum."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend ? backend.getDatasetList() : []
                    onCurrentIndexChanged: updateDatasetInfo()
                }

                Label {
                    id: datasetInfo
                    text: getDatasetInfoText()
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        GroupBox {
            title: "Operation"
            Layout.fillWidth: true
            visible: datasetCombo.currentIndex >= 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 5

                Label {
                    text: "This tool computes the simple arithmetic mean across all spectra (columns) in the dataset."
                    font.pixelSize: 11
                    color: textMuted
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Label {
                    text: "Tip: Use Column Selector first to average only specific spectra."
                    font.pixelSize: 10
                    font.italic: true
                    color: accentBlue
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        Item { Layout.fillHeight: true }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Button {
                text: "Average"
                enabled: datasetCombo.currentIndex >= 0 && !backend.isBusy
                highlighted: true
                onClicked: performAverage()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    if (averageCurvesTool.closeWindow) { averageCurvesTool.closeWindow() } else { var window = averageCurvesTool.Window.window; if (window) window.close() }
                }
            }
        }

        Label {
            id: statusLabel
            Layout.fillWidth: true
            text: ""
            font.pixelSize: 10
            color: accentBlue
            visible: text !== ""
            wrapMode: Text.Wrap
        }
    }

    // Backend connections
    Connections {
        target: backend

        function onToolCompleted(toolName, outputPath) {
            if (toolName === "Average Curves") {
                statusLabel.text = "Data averaged successfully: " + outputPath
                statusLabel.color = successColor
            }
        }

        function onErrorOccurred(title, message) {
            if (title.includes("Average")) {
                statusLabel.text = "Error: " + message
                statusLabel.color = accentMagenta
            }
        }
    }

    // Helper functions
    function getDatasetInfoText() {
        if (!backend || datasetCombo.currentIndex < 0 || !datasetCombo.currentText) {
            return "No dataset selected"
        }

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        if (!info || !info.type) {
            return "No dataset selected"
        }
        return "Type: " + info.type + " | Spectra: " + info.num_spectra +
               " | Points: " + info.num_points + " | Variable: " + info.independent_var
    }

    function updateDatasetInfo() {
        datasetInfo.text = getDatasetInfoText()
        statusLabel.text = ""
    }

    function performAverage() {
        var datasetName = datasetCombo.currentText
        console.log("Averaging curves for dataset:", datasetName)

        statusLabel.text = "Averaging curves..."
        statusLabel.color = accentBlue

        backend.averageCurves(datasetName)
    }
}
