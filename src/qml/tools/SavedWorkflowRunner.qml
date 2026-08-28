/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

// Runs a saved workflow over a dataset selection.
//
// A saved workflow is a composite tool nobody had to code, and this is what
// makes it one: pick the data, press Run. The chain runs with the parameters
// it was saved with — exposing those knobs here is a real feature, and a
// separate one.
Item {
    id: root
    property var closeWindow: null

    // Which workflow this window is for. Set on the application window
    // immediately before the window is created, because WindowManager owns
    // the instantiation and there is nowhere to pass it directly.
    property string workflowName: ""
    property string workflowPath: ""

    property bool datasetDropActive: false
    function acceptDatasetDrop(names) { datasetList.addToSelection(names) }

    property var parentWindow: Window.window
    // Each colour is resolved explicitly, and the property is named as a
    // literal rather than looked up by string.
    //
    // That distinction is the whole point. This used to read
    // parentWindow[name] inside a themeColor() helper, and a subscript is
    // something QML cannot register as a binding dependency — so the binding
    // was evaluated once and never again. Measured: switching the scheme from
    // "Just Dark Mode" to a light one moved the window's own bgDark from
    // #1a1a1a to #f5f0f8 while this tool's bgDark stayed #1a1a1a, and the
    // canvases under it stayed dark inside a light window. Naming the
    // property directly makes it a real dependency, so a scheme change
    // arrives here the moment the window sees it.
    //
    // The `!== undefined` guard stays: reading a colour the host does not
    // carry yields undefined, which lands as an invalid QColor and paints
    // text black-on-black. Theme is the fallback — a singleton nothing has to
    // locate, so it cannot be missing.
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    property bool running: false

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    Component.onCompleted: {
        if (parentWindow && parentWindow.pendingWorkflowPath) {
            root.workflowName = parentWindow.pendingWorkflowName
            root.workflowPath = parentWindow.pendingWorkflowPath
            parentWindow.pendingWorkflowName = ""
            parentWindow.pendingWorkflowPath = ""
        }
        datasetList.model = backend.getDatasetList()
    }

    function run() {
        var picked = datasetList.selectedDatasets
        if (!picked || picked.length === 0 || root.workflowPath === "") return
        root.running = true
        statusLabel.text = picked.length > 1
            ? "Running over " + picked.length + " datasets, one after another…"
            : "Running…"
        backend.workflowManager.runSavedWorkflow(root.workflowPath, picked)
    }

    Connections {
        target: backend
        function onDataLoaded(name) {
            datasetList.model = backend.getDatasetList()
        }
    }

    Connections {
        target: backend.workflowManager

        function onWorkflowExecutionProgress(current, total, message) {
            statusLabel.text = "Step " + (current + 1) + " of " + total
                             + (message ? " — " + message : "")
        }

        function onWorkflowExecutionCompleted(name, success, errors) {
            root.running = false
            if (success) {
                statusLabel.text = "Finished — results are in the project browser"
                statusLabel.color = root.accentBlue
            } else {
                statusLabel.text = (errors && errors.length > 0)
                    ? errors.join("\n") : "The workflow did not finish"
                statusLabel.color = root.accentPink
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Label {
            Layout.fillWidth: true
            text: root.workflowName === "" ? "No workflow"
                                           : "Workflow: " + root.workflowName
            color: accentPurple
            font.bold: true
            wrapMode: Text.Wrap
        }

        Label {
            Layout.fillWidth: true
            text: "Runs the saved chain with the parameters it was saved with. " +
                  "Pick which datasets to run it over; with more than one they " +
                  "are processed in turn, never merged."
            font.pixelSize: 11
            color: textMuted
            wrapMode: Text.Wrap
        }

        ToolSection {
            title: "Datasets"
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                DatasetMultiSelect {
                    id: datasetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visibleRows: 6
                    model: []

                    bgColor: bgDark
                    borderColorNormal: root.datasetDropActive ? accentBlue : accentPurple
                    borderColorFocus: accentPink
                    textColor: textLight
                    textMutedColor: textMuted
                    selectionColor: accentPink
                }

                Label {
                    Layout.fillWidth: true
                    text: datasetList.selectedDatasets.length > 1
                          ? datasetList.selectedDatasets.length +
                            " datasets — the whole chain runs once per dataset"
                          : (root.datasetDropActive
                             ? "Drop to add to the selection"
                             : "Pick the datasets — or drag them here from the " +
                               "project browser")
                    font.pixelSize: 10
                    color: root.datasetDropActive ? accentBlue : textMuted
                    wrapMode: Text.Wrap
                }
            }
        }

        Label {
            id: statusLabel
            Layout.fillWidth: true
            text: "Ready"
            color: textMuted
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: running ? "Running…" : "Run"
                enabled: !running && datasetList.selectedDatasets.length > 0
                         && root.workflowPath !== ""
                highlighted: true
                onClicked: root.run()
            }
            Button {
                text: "Cancel"
                enabled: running
                onClicked: backend.workflowManager.cancelExecution()
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() }
                    else { var win = Window.window; if (win) win.close() }
                }
            }
        }
    }
}
