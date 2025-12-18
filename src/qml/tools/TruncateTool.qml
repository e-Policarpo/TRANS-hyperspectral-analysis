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

// Voltage/Range Truncation Tool
Item {
    id: truncateTool

    // Theme colors - reactive bindings to parent DraggableWindow
    property var parentWindow: Window.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentMagenta: parentWindow ? parentWindow.accentMagenta : "#D60270"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"
    property color successColor: parentWindow ? parentWindow.successColor : "#2ECC71"

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Truncate Data Range"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Truncate spectral data to a specific range of the independent variable (e.g., voltage, wavenumber)."
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
                    model: backend.getDatasetList()
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
            title: "Truncation Range"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 8
                columnSpacing: 10

                Label {
                    text: "Minimum Value:"
                    Layout.alignment: Qt.AlignRight
                }

                TextField {
                    id: minValueField
                    Layout.fillWidth: true
                    placeholderText: "e.g., -2.0"
                    validator: DoubleValidator {
                        notation: DoubleValidator.StandardNotation
                    }
                    onTextChanged: validateRange()
                }

                Label {
                    text: "Maximum Value:"
                    Layout.alignment: Qt.AlignRight
                }

                TextField {
                    id: maxValueField
                    Layout.fillWidth: true
                    placeholderText: "e.g., 2.0"
                    validator: DoubleValidator {
                        notation: DoubleValidator.StandardNotation
                    }
                    onTextChanged: validateRange()
                }

                Label {
                    id: rangeValidationLabel
                    Layout.columnSpan: 2
                    font.pixelSize: 10
                    color: isRangeValid() ? successColor : accentMagenta
                    text: getRangeValidationText()
                    visible: minValueField.text !== "" && maxValueField.text !== ""
                }
            }
        }

        GroupBox {
            title: "Current Data Range"
            Layout.fillWidth: true
            visible: datasetCombo.currentIndex >= 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 5

                Label {
                    id: currentRangeLabel
                    text: getCurrentRangeText()
                    font.pixelSize: 11
                    color: textMuted
                }

                Label {
                    text: "Preview: This will select data points within the specified range"
                    font.pixelSize: 10
                    font.italic: true
                    color: textMuted
                }
            }
        }

        Item { Layout.fillHeight: true }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Button {
                text: "Truncate"
                enabled: datasetCombo.currentIndex >= 0 && isRangeValid() && !backend.isBusy
                highlighted: true
                onClicked: performTruncation()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Button {
                text: "Reset"
                onClicked: resetFields()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    // Find the Window ancestor and close it
                    var window = truncateTool.Window.window
                    if (window) {
                        window.close()
                    }
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
            if (toolName === "Truncate Data") {
                statusLabel.text = "✓ Data truncated successfully: " + outputPath
                statusLabel.color = successColor
            }
        }

        function onErrorOccurred(title, message) {
            if (title.includes("Truncate")) {
                statusLabel.text = "✗ Error: " + message
                statusLabel.color = accentMagenta
            }
        }
    }

    // Helper functions
    function getDatasetInfoText() {
        if (datasetCombo.currentIndex < 0 || !datasetCombo.currentText) {
            return "No dataset selected"
        }

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        if (!info || !info.type) {
            return "No dataset selected"
        }
        return "Type: " + info.type + " | Spectra: " + info.num_spectra +
               " | Points: " + info.num_points + " | Variable: " + info.independent_var
    }

    function getCurrentRangeText() {
        if (datasetCombo.currentIndex < 0) {
            return "Select a dataset to see its range"
        }

        // Note: This would ideally query the actual data range from backend
        // For now, show placeholder
        return "Current range will be displayed here (requires backend method)"
    }

    function isRangeValid() {
        if (minValueField.text === "" || maxValueField.text === "") {
            return false
        }

        var minVal = parseFloat(minValueField.text)
        var maxVal = parseFloat(maxValueField.text)

        return !isNaN(minVal) && !isNaN(maxVal) && minVal < maxVal
    }

    function getRangeValidationText() {
        if (!isRangeValid()) {
            return "⚠ Invalid range: maximum must be greater than minimum"
        }

        var minVal = parseFloat(minValueField.text)
        var maxVal = parseFloat(maxValueField.text)
        var range = maxVal - minVal

        return "✓ Valid range: " + range.toFixed(3) + " units"
    }

    function validateRange() {
        // Trigger validation label update
        rangeValidationLabel.text = getRangeValidationText()
    }

    function updateDatasetInfo() {
        datasetInfo.text = getDatasetInfoText()
        currentRangeLabel.text = getCurrentRangeText()
        statusLabel.text = ""
    }

    function resetFields() {
        minValueField.text = ""
        maxValueField.text = ""
        statusLabel.text = ""
    }

    function performTruncation() {
        if (!isRangeValid()) {
            console.error("Invalid range for truncation")
            return
        }

        var datasetName = datasetCombo.currentText
        var minVal = parseFloat(minValueField.text)
        var maxVal = parseFloat(maxValueField.text)

        console.log("Truncating dataset:", datasetName, "to range [", minVal, ",", maxVal, "]")

        statusLabel.text = "Truncating data..."
        statusLabel.color = accentBlue

        // Call backend truncation method
        backend.truncateData(datasetName, minVal, maxVal)
    }
}
