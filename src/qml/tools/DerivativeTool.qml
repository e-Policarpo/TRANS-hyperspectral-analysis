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

// Derivative Calculator Tool
Item {
    id: root
    property var closeWindow: null

    // Set by WindowManager while a browser drag hovers this tool, so the
    // drop target is visible before the mouse is released.
    property bool datasetDropActive: false

    // Datasets dropped from the project browser join the selection (the tool
    // never consumes them). Declaring this function is all a tool needs to
    // become a drop target — see WindowManager.deliverDatasetDrop.
    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

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
            text: "Derivative Calculator"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Calculate numerical derivatives of spectral data (dI/dV or d²I/dV²)."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                DatasetMultiSelect {
                    id: datasetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 130
                    model: backend.getDatasetList()

                    bgColor: bgLight
                    borderColorNormal: root.datasetDropActive ? accentBlue : accentPurple
                    borderColorFocus: accentPink
                    textColor: textLight
                    textMutedColor: textMuted
                    selectionColor: accentPink
                }

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 0
                        text: root.datasetDropActive
                              ? "Drop to add to the selection"
                              : "…or drag datasets here from the project browser"
                        font.pixelSize: 10
                        color: root.datasetDropActive ? accentBlue : textMuted
                        elide: Text.ElideRight
                    }

                    Button {
                        text: "Refresh list"
                        flat: true
                        font.pixelSize: 10
                        onClicked: root.refreshDatasets()
                    }
                }
            }
        }

        // Keep the list in step with imports and with datasets produced by
        // other tools, dropping any pick that no longer exists.
        Connections {
            target: backend
            function onDataLoaded(name) { root.refreshDatasets() }
        }

        GroupBox {
            title: "Derivative Parameters"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                RowLayout {
                    Label { text: "Derivative Order:" }
                    ComboBox {
                        id: orderCombo
                        Layout.fillWidth: true
                        model: ["First Derivative (dI/dV)", "Second Derivative (d²I/dV²)"]
                    }
                }

                CheckBox {
                    id: smoothBeforeCheck
                    text: "Smooth before differentiation (recommended)"
                    checked: true
                }

                CheckBox {
                    id: smoothAfterCheck
                    text: "Smooth after differentiation (recommended)"
                    checked: true
                }
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "Numerical differentiation amplifies noise.\n" +
                      "Smoothing before and/or after is highly recommended.\n\n" +
                      "Select several datasets to process them one after another —\n" +
                      "each produces its own output, named after its input."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: datasetList.selectedDatasets.length > 1
                      ? "Calculate Derivatives (" + datasetList.selectedDatasets.length + ")"
                      : "Calculate Derivative"
                enabled: datasetList.selectedDatasets.length > 0
                highlighted: true
                onClicked: performDerivative()
            }

            Button {
                text: "Cancel Operation"
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

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
    }

    function performDerivative() {
        var order = orderCombo.currentIndex + 1
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0)
            return

        console.log("Calculating derivative order", order, "for:", datasets.join(", "))

        // One batch task: the datasets are processed in the order they were
        // picked, each yielding its own output named after its input.
        backend.runToolOnDatasets("derivative", datasets, {
            "order": order,
            "smooth_before": smoothBeforeCheck.checked,
            "smooth_after": smoothAfterCheck.checked
        })
    }
}
