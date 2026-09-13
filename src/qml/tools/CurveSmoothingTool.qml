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

// Curve Smoothing Tool
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    property bool datasetDropActive: false

    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    // Theme colors - reactive bindings to the hosting window
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Curve Smoothing"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Apply smoothing filters to spectral curves to reduce noise."
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

                    ToolButton {
                        text: "Refresh list"
                        flat: true
                        font.pixelSize: 10
                        onClicked: root.refreshDatasets()
                    }
                }
            }
        }

        Connections {
            target: backend
            function onDataLoaded(name) { root.refreshDatasets() }
            // This panel shows no progress of its own, so there is nothing to
            // put right on screen — but the remembered task name has to go,
            // or closing the window later would try to cancel a finished run.
            function onToolCompleted(toolName, outputPath) {
                if (root.runningTaskName.indexOf(toolName) === 0) root.runningTaskName = ""
            }
            function onOperationCancelled(name) {
                if (name === root.runningTaskName) root.runningTaskName = ""
            }
        }

        GroupBox {
            title: "Smoothing Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 10
                columnSpacing: 10

                Label { text: "Smoothing Type:" }
                ComboBox {
                    id: smoothingTypeCombo
                    Layout.fillWidth: true
                    model: ["Savitzky-Golay", "Moving Average", "Gaussian"]
                    currentIndex: 0
                }

                Label { text: "Window Size:" }
                SpinBox {
                    id: windowSizeSpin
                    from: 3
                    to: 51
                    stepSize: 2
                    value: 11
                    editable: true
                }

                Label {
                    text: "Polynomial Order:"
                    visible: smoothingTypeCombo.currentIndex === 0
                }
                SpinBox {
                    id: polyOrderSpin
                    from: 1
                    to: 5
                    value: 3
                    visible: smoothingTypeCombo.currentIndex === 0
                }
            }
        }

        GroupBox {
            title: "Preview"
            Layout.fillWidth: true

            Label {
                text: "Smoothing method: " + getSmoothingMethod() +
                      "\nWindow size: " + windowSizeSpin.value +
                      (smoothingTypeCombo.currentIndex === 0 ? "\nPolynomial order: " + polyOrderSpin.value : "") +
                      "\n\nSelect several datasets to smooth them one after another —" +
                      "\neach produces its own output, named after its input."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: datasetList.selectedDatasets.length > 1
                      ? "Apply Smoothing (" + datasetList.selectedDatasets.length + ")"
                      : "Apply Smoothing"
                enabled: datasetList.selectedDatasets.length > 0
                primary: true
                onClicked: performSmoothing()
            }

            ToolButton {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            Item { Layout.fillWidth: true }

            ToolButton {
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

    function getSmoothingMethod() {
        var types = ["savgol", "moving_average", "gaussian"]
        return types[smoothingTypeCombo.currentIndex]
    }

    function performSmoothing() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        console.log("Smoothing:", datasets.join(", "),
                   "Method:", getSmoothingMethod(),
                   "Window:", windowSizeSpin.value)
        root.runningTaskName = backend.runToolOnDatasets("smooth_curves", datasets, {
            "window_size": windowSizeSpin.value,
            "poly_order": polyOrderSpin.value,
            "smoothing_type": getSmoothingMethod()
        })
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
