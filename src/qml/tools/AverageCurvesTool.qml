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

// Average Curves: one mean spectrum per selected dataset.
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    // Set by WindowManager while a browser drag hovers this tool.
    property bool datasetDropActive: false

    // Datasets dropped from the project browser join the selection — see
    // WindowManager.deliverDatasetDrop.
    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    // Theme colors - reactive bindings to the hosting window (Window.window
    // resolves both for the embedded host and for a ToolWindow).
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color successColor: (parentWindow && parentWindow.successColor !== undefined) ? parentWindow.successColor : Theme.successColor

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Average Curves"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Compute the arithmetic mean of all spectra in each selected dataset, " +
                  "producing one averaged spectrum per dataset."
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
                    onSelectionChanged: statusLabel.text = ""
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

                Label {
                    Layout.fillWidth: true
                    text: root.selectionSummary()
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                }
            }
        }

        Connections {
            target: backend
            function onDataLoaded(name) { root.refreshDatasets() }
            function onToolCompleted(toolName, outputPath) {
                if (toolName === "Average Curves") {
                    root.runningTaskName = ""
                    statusLabel.text = "Averaged: " + outputPath
                    statusLabel.color = successColor
                }
            }
            function onErrorOccurred(title, message) {
                if (title.indexOf("Average") >= 0) {
                    root.runningTaskName = ""
                    statusLabel.text = "Error: " + message
                    statusLabel.color = accentMagenta
                }
            }
            // A cancelled task reaches neither of the two handlers above, so
            // without this the panel goes on claiming it is averaging.
            function onOperationCancelled(name) {
                if (name !== root.runningTaskName) return
                root.runningTaskName = ""
                statusLabel.text = "Cancelled"
                statusLabel.color = textMuted
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "The mean is taken across all spectra (columns) of a dataset.\n" +
                      "Use Filter Bad Data first to drop curves that should not count.\n\n" +
                      "Select several datasets to average them one after another —\n" +
                      "each produces its own '- Average' output, named after its input."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            ToolButton {
                text: datasetList.selectedDatasets.length > 1
                      ? "Average (" + datasetList.selectedDatasets.length + ")"
                      : "Average"
                enabled: datasetList.selectedDatasets.length > 0 && !backend.isBusy
                primary: true
                onClicked: performAverage()
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

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
    }

    function selectionSummary() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return "No dataset selected"
        if (picks.length > 1) return picks.length + " datasets — averaged one after another"
        var info = backend.getDatasetInfo(picks[0])
        if (!info || !info.type) return ""
        return "Type: " + info.type + " | Spectra: " + info.num_spectra +
               " | Points: " + info.num_points + " | Variable: " + info.independent_var
    }

    function performAverage() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        statusLabel.text = "Averaging curves..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("average_curves", datasets, {})
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
