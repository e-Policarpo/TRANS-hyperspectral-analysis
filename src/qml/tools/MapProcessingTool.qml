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
import QtQuick.Dialogs
import QtQuick.Window 2.15
import "../components"

// Map Processing Tool - Standalone tool for map/image processing operations
// Operations: Gaussian Filter, Median Filter, Plane Level, Row Align, Normalize
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

    FileDialog {
        id: imageFileDialog
        title: "Select Map/Image File"
        nameFilters: [
            "All Supported (*.tif *.tiff *.png *.npy *.gsf)",
            "TIFF Files (*.tif *.tiff)",
            "PNG Files (*.png)",
            "NumPy Files (*.npy)",
            "Gwyddion Files (*.gsf)",
            "All files (*)"
        ]
        onAccepted: {
            imagePathField.text = selectedFile.toString().replace("file://", "")
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Map Processing"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Apply processing operations to map/image data: filtering, leveling, normalization."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        // Input Selection
        GroupBox {
            title: "Input Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RadioButton {
                    id: useMapDataset
                    text: "Use Map from Project"
                    checked: true
                }

                DatasetComboBox {
                    id: mapDatasetCombo
                    Layout.fillWidth: true
                    enabled: useMapDataset.checked
                    model: backend ? backend.getMapList().map(m => m.title) : []
                    placeholderText: "Select map..."
                }

                RadioButton {
                    id: useExternalFile
                    text: "Use External File"
                }

                RowLayout {
                    enabled: useExternalFile.checked

                    TextField {
                        // A bare TextField takes the style's own palette, which under the
                        // Basic style is a light one — white ground, black text — regardless
                        // of what the window around it is painted. Say it explicitly.
                        color: root.textLight
                        placeholderTextColor: root.textMuted
                        background: Rectangle {
                            color: root.bgDark
                            border.color: root.bgLight
                            border.width: 1
                            radius: 4
                        }
                        id: imagePathField
                        Layout.fillWidth: true
                        placeholderText: "Select image file..."
                        readOnly: true
                    }

                    Button {
                        text: "Browse..."
                        onClicked: imageFileDialog.open()
                    }
                }
            }
        }

        // Operation Selection
        GroupBox {
            title: "Operation"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                ComboBox {
                    id: operationCombo
                    Layout.fillWidth: true
                    model: [
                        "Gaussian Filter",
                        "Median Filter",
                        "Plane Level",
                        "Row Align",
                        "Normalize",
                        "Polynomial Background Removal"
                    ]
                    onCurrentIndexChanged: updateParametersUI()
                }

                // Parameters - changes based on operation
                StackLayout {
                    id: parametersStack
                    Layout.fillWidth: true
                    currentIndex: operationCombo.currentIndex

                    // Gaussian Filter parameters
                    GridLayout {
                        columns: 2
                        columnSpacing: 10

                        Label { text: "Sigma:" }
                        SpinBox {
                            id: gaussianSigma
                            from: 1
                            to: 100
                            value: 10
                            stepSize: 1

                            property real realValue: value / 10.0

                            textFromValue: function(value) {
                                return (value / 10.0).toFixed(1)
                            }
                            valueFromText: function(text) {
                                return parseFloat(text) * 10
                            }
                        }

                        Label {
                            text: "Higher sigma = more smoothing"
                            Layout.columnSpan: 2
                            color: textMuted
                            font.pixelSize: 10
                        }
                    }

                    // Median Filter parameters
                    GridLayout {
                        columns: 2
                        columnSpacing: 10

                        Label { text: "Kernel Size:" }
                        SpinBox {
                            id: medianSize
                            from: 3
                            to: 21
                            value: 3
                            stepSize: 2
                        }

                        Label {
                            text: "Odd values only (3, 5, 7...)"
                            Layout.columnSpan: 2
                            color: textMuted
                            font.pixelSize: 10
                        }
                    }

                    // Plane Level - no parameters
                    Label {
                        text: "Fits and subtracts a plane from the image.\nNo additional parameters required."
                        color: textMuted
                        wrapMode: Text.Wrap
                    }

                    // Row Align - no parameters
                    Label {
                        text: "Aligns rows by subtracting median of each row.\nNo additional parameters required."
                        color: textMuted
                        wrapMode: Text.Wrap
                    }

                    // Normalize - no parameters
                    Label {
                        text: "Normalizes values to [0, 1] range.\nNo additional parameters required."
                        color: textMuted
                        wrapMode: Text.Wrap
                    }

                    // Polynomial Background Removal
                    GridLayout {
                        columns: 2
                        columnSpacing: 10

                        Label { text: "Polynomial Order:" }
                        SpinBox {
                            id: polyOrder
                            from: 1
                            to: 6
                            value: 2
                        }

                        Label {
                            text: "Higher order = more flexible background fit"
                            Layout.columnSpan: 2
                            color: textMuted
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        // Output Options
        GroupBox {
            title: "Output"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                CheckBox {
                    id: saveTiffCheck
                    text: "Save as TIFF"
                    checked: true
                }

                CheckBox {
                    id: savePngCheck
                    text: "Save as PNG (colormap)"
                    checked: false
                }

                CheckBox {
                    id: openResultCheck
                    text: "Open result in Map Editor"
                    checked: true
                }

                Label {
                    text: "Output will be saved to: outputs/maps/"
                    color: textMuted
                    font.pixelSize: 10
                }
            }
        }

        Item { Layout.fillHeight: true }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Apply"
                enabled: (useMapDataset.checked && mapDatasetCombo.currentIndex >= 0) ||
                        (useExternalFile.checked && imagePathField.text.length > 0)
                highlighted: true
                onClicked: performProcessing()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() } else { var win = root.Window.window; if (win) win.close() }
                }
            }
        }
    }

    function updateParametersUI() {
        // Parameters UI is handled by StackLayout currentIndex binding
    }

    function getOperationName() {
        var operations = [
            "gaussian_filter",
            "median_filter",
            "plane_level",
            "row_align",
            "normalize",
            "polynomial_bg_removal"
        ]
        return operations[operationCombo.currentIndex]
    }

    function getParameters() {
        var params = {}
        switch(operationCombo.currentIndex) {
            case 0: // Gaussian
                params.sigma = gaussianSigma.realValue
                break
            case 1: // Median
                params.size = medianSize.value
                break
            case 2: // Plane Level
                break
            case 3: // Row Align
                break
            case 4: // Normalize
                break
            case 5: // Polynomial
                params.order = polyOrder.value
                break
        }
        params.save_tiff = saveTiffCheck.checked
        params.save_png = savePngCheck.checked
        params.open_result = openResultCheck.checked
        return params
    }

    function performProcessing() {
        var inputPath = ""
        var inputType = ""

        if (useMapDataset.checked) {
            inputType = "dataset"
            inputPath = mapDatasetCombo.currentText
        } else {
            inputType = "file"
            inputPath = imagePathField.text
        }

        var operation = getOperationName()
        var params = getParameters()

        console.log("Processing map:", inputPath, "Operation:", operation, "Params:", JSON.stringify(params))

        // Call backend
        backend.processMap(inputPath, inputType, operation, params)
    }
}
