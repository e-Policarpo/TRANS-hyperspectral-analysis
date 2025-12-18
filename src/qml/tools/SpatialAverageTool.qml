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

// Spatial Average Utility Tool
Item {
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Tool description
        Label {
            text: "Spatial Average Utility"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Transform hyperspectral grid by averaging spectra in discrete spatial blocks.\nThis creates a lower-resolution grid where each point is the average of multiple spectra."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#9B4F96"
        }

        // Dataset selection
        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 5

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                    onCurrentIndexChanged: updateGridInfo()
                }

                Label {
                    id: datasetInfo
                    text: getDatasetInfo()
                    font.pixelSize: 10
                    color: "#666666"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        // Grid discretization parameters
        GroupBox {
            title: "Discretization Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 10
                columnSpacing: 10

                Label {
                    text: "Original Grid:"
                    font.bold: true
                }
                Label {
                    id: originalGridLabel
                    text: getOriginalGridSize()
                    color: "#0066cc"
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    height: 1
                    color: "#dddddd"
                }

                Label {
                    text: "Discrete X (horizontal):"
                }
                SpinBox {
                    id: discreteXSpin
                    from: 1
                    to: 1000
                    value: 10
                    editable: true
                    onValueChanged: updateResultGrid()
                }

                Label {
                    text: "Discrete Y (vertical):"
                }
                SpinBox {
                    id: discreteYSpin
                    from: 1
                    to: 1000
                    value: 10
                    editable: true
                    onValueChanged: updateResultGrid()
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    height: 1
                    color: "#dddddd"
                }

                Label {
                    text: "Result Grid:"
                    font.bold: true
                }
                Label {
                    id: resultGridLabel
                    text: calculateResultGrid()
                    color: "#009933"
                }

                Label {
                    text: "Block Size:"
                }
                Label {
                    id: blockSizeLabel
                    text: calculateBlockSize()
                    color: "#666666"
                }

                Label {
                    text: "Spectra per Block:"
                }
                Label {
                    id: spectraPerBlockLabel
                    text: calculateSpectraPerBlock()
                    color: "#666666"
                }
            }
        }

        // Visualization
        GroupBox {
            title: "Discretization Preview"
            Layout.fillWidth: true
            Layout.preferredHeight: 150

            Rectangle {
                anchors.fill: parent
                color: "#f5f5f5"
                border.color: "#cccccc"
                border.width: 1

                Column {
                    anchors.centerIn: parent
                    spacing: 10

                    Text {
                        text: "Preview Grid Transformation"
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Row {
                        spacing: 20
                        anchors.horizontalCenter: parent.horizontalCenter

                        Rectangle {
                            width: 60
                            height: 60
                            color: "#0066cc"
                            opacity: 0.3
                            border.color: "#0066cc"
                            border.width: 2

                            Text {
                                anchors.centerIn: parent
                                text: getOriginalGridSize()
                                color: "#0066cc"
                                font.bold: true
                            }
                        }

                        Text {
                            text: "→"
                            font.pixelSize: 24
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Rectangle {
                            width: 60
                            height: 60
                            color: "#009933"
                            opacity: 0.3
                            border.color: "#009933"
                            border.width: 2

                            Text {
                                anchors.centerIn: parent
                                text: calculateResultGrid()
                                color: "#009933"
                                font.bold: true
                            }
                        }
                    }
                }
            }
        }

        // Options
        GroupBox {
            title: "Options"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                CheckBox {
                    id: ignoreEmptyCheck
                    text: "Ignore empty blocks (blocks with all NaN values)"
                    checked: true
                }

                CheckBox {
                    id: saveIntermediateCheck
                    text: "Save intermediate results (horizontal averaging stage)"
                    checked: false
                }
            }
        }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Calculate Spatial Average"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performSpatialAverage()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Export to CSV"
                enabled: false  // Enable after calculation
            }

            Button {
                text: "Close"
                onClicked: {
                    var win = Window.window
                    if (win) win.close()
                }
            }
        }
    }

    // Functions
    function getDatasetInfo() {
        if (datasetCombo.currentIndex < 0) return "No dataset selected"

        var datasetName = datasetCombo.currentText
        var info = backend.getDatasetInfo(datasetName)

        return "Type: " + info.type + " | Dimensions: " + info.dimensions +
               " | Spectra: " + info.num_spectra + " | Points: " + info.num_points +
               " | Independent Variable: " + info.independent_var
    }

    function getOriginalGridSize() {
        if (datasetCombo.currentIndex < 0) return "N/A"

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        var dims = info.dimensions || [0, 0]
        return dims[0] + " × " + dims[1]
    }

    function calculateResultGrid() {
        return discreteXSpin.value + " × " + discreteYSpin.value
    }

    function calculateBlockSize() {
        if (datasetCombo.currentIndex < 0) return "N/A"

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        var dims = info.dimensions || [1, 1]

        var blockWidth = Math.floor(dims[0] / discreteXSpin.value)
        var blockHeight = Math.floor(dims[1] / discreteYSpin.value)

        return blockWidth + " × " + blockHeight + " pixels"
    }

    function calculateSpectraPerBlock() {
        if (datasetCombo.currentIndex < 0) return "N/A"

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        var dims = info.dimensions || [1, 1]

        var blockWidth = Math.floor(dims[0] / discreteXSpin.value)
        var blockHeight = Math.floor(dims[1] / discreteYSpin.value)

        return (blockWidth * blockHeight) + " spectra"
    }

    function updateGridInfo() {
        originalGridLabel.text = getOriginalGridSize()
        updateResultGrid()
    }

    function updateResultGrid() {
        resultGridLabel.text = calculateResultGrid()
        blockSizeLabel.text = calculateBlockSize()
        spectraPerBlockLabel.text = calculateSpectraPerBlock()
    }

    function performSpatialAverage() {
        console.log("Performing spatial average on:", datasetCombo.currentText)
        console.log("Discrete grid:", discreteXSpin.value, "×", discreteYSpin.value)
        console.log("Ignore empty:", ignoreEmptyCheck.checked)
        console.log("Save intermediate:", saveIntermediateCheck.checked)

        // Call backend
        var result = backend.spatialAverage(
            datasetCombo.currentText,
            discreteXSpin.value,
            discreteYSpin.value,
            ignoreEmptyCheck.checked,
            saveIntermediateCheck.checked
        )

        if (result) {
            console.log("Spatial average complete, saved to:", result)
        }
    }

    Component.onCompleted: {
        updateGridInfo()
    }
}
