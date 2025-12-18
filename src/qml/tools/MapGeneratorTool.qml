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

// Map Generator Tool
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
            text: "Map Generator"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Generate spatial maps from flat data (integrated values, peak heights, etc.)."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Flat Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: getFlatDatasets()
                    placeholderText: "Select flat dataset..."
                    onCurrentTextChanged: updateValuesList()
                }

                Label {
                    text: "Flat datasets have one value per spatial point (e.g., integrated data)"
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

        GroupBox {
            title: "Value Selection"
            Layout.fillWidth: true
            Layout.preferredHeight: 200

            ColumnLayout {
                anchors.fill: parent
                spacing: 5

                Label {
                    text: "Select values to generate maps for:"
                    font.bold: true
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ColumnLayout {
                        id: valuesColumn
                        width: parent.width
                        spacing: 5

                        Repeater {
                            id: valuesRepeater
                            model: ListModel { id: valuesModel }

                            delegate: CheckBox {
                                text: model.label
                                checked: model.selected
                                onCheckedChanged: {
                                    valuesModel.setProperty(index, "selected", checked)
                                }
                            }
                        }

                        Label {
                            visible: valuesRepeater.count === 0
                            text: "Select a dataset to see available values"
                            color: textMuted
                            font.italic: true
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        text: "Select All"
                        onClicked: selectAllValues(true)
                    }
                    Button {
                        text: "Deselect All"
                        onClicked: selectAllValues(false)
                    }
                }
            }
        }

        GroupBox {
            title: "Map Options"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                Label {
                    text: "Colormap: Viridis (built-in)"
                    font.pixelSize: 11
                }

                Label {
                    text: "Output: TIFF, PNG, and CSV files"
                    font.pixelSize: 11
                }

                Label {
                    text: "Maps will be saved to: outputs/maps/"
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Generate Maps"
                enabled: datasetCombo.currentIndex >= 0 && getSelectedValuesCount() > 0
                highlighted: true
                onClicked: performMapGeneration()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Label {
                text: getSelectedValuesCount() + " value(s) selected"
                color: textMuted
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    var win = root.Window.window
                    if (win) win.close()
                }
            }
        }
    }

    function getFlatDatasets() {
        // Get all datasets that have flat data structure
        // This includes integrated datasets and any other single-value-per-point data
        var all = backend.getDatasetList()
        var flatData = []

        for (var i = 0; i < all.length; i++) {
            // Include datasets that start with common flat data prefixes
            if (all[i].indexOf("Integrated_") === 0 ||
                all[i].indexOf("Peaks_") === 0 ||
                all[i].indexOf("Flat_") === 0) {
                flatData.push(all[i])
            }
        }

        return flatData.length > 0 ? flatData : ["No flat datasets"]
    }

    function updateValuesList() {
        valuesModel.clear()

        if (datasetCombo.currentIndex < 0 ||
            datasetCombo.currentText === "No flat datasets") {
            return
        }

        // Get value columns from backend (intervals for integrated data, or column names)
        var values = backend.getFlatDataValues(datasetCombo.currentText)

        for (var i = 0; i < values.length; i++) {
            valuesModel.append({
                "index": i,
                "label": "Value " + (i + 1) + ": " + values[i],
                "selected": false,
                "valueData": values[i]
            })
        }
    }

    function selectAllValues(select) {
        for (var i = 0; i < valuesModel.count; i++) {
            valuesModel.setProperty(i, "selected", select)
        }
    }

    function getSelectedValuesCount() {
        var count = 0
        for (var i = 0; i < valuesModel.count; i++) {
            if (valuesModel.get(i).selected) {
                count++
            }
        }
        return count
    }

    function getSelectedValues() {
        var selected = []
        for (var i = 0; i < valuesModel.count; i++) {
            if (valuesModel.get(i).selected) {
                selected.push(valuesModel.get(i).index)
            }
        }
        return selected
    }

    function performMapGeneration() {
        var selectedValues = getSelectedValues()

        if (selectedValues.length === 0) {
            console.log("No values selected")
            return
        }

        console.log("Generating maps from:", datasetCombo.currentText,
                   "Values:", selectedValues)

        backend.generateMaps(
            datasetCombo.currentText,
            selectedValues
        )
    }
}
