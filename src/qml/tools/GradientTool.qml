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

// Gradient Filter: gradient magnitude of maps and images from the project
// browser. The list shows titles; each maps to a browser ref
// ("map:<id>" / "image:<id>") that the backend resolves.
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    property bool datasetDropActive: false

    // A browser drag carries map/image refs alongside dataset names; keep
    // the ones this tool lists and add them by their titles.
    function acceptDatasetDrop(names) {
        root.refreshSources()
        var labels = []
        for (var i = 0; i < names.length; i++) {
            var label = root.labelForRef[names[i]]
            if (label !== undefined) labels.push(label)
        }
        sourceList.addToSelection(labels)
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
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color successColor: (parentWindow && parentWindow.successColor !== undefined) ? parentWindow.successColor : Theme.successColor

    // label -> ref and ref -> label, rebuilt from backend.getFieldSourceList().
    property var refForLabel: ({})
    property var labelForRef: ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Gradient Filter"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Gradient magnitude of a map or image — edges and slopes stand out, " +
                  "flat regions go dark. The output is a calibrated map in the source's " +
                  "value unit per lateral unit."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Maps and images"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                DatasetMultiSelect {
                    id: sourceList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 130
                    model: []
                    placeholderText: "No maps or images in the project"

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
                              : "…or drag maps or images here from the project browser"
                        font.pixelSize: 10
                        color: root.datasetDropActive ? accentBlue : textMuted
                        elide: Text.ElideRight
                    }

                    ToolButton {
                        text: "Refresh list"
                        flat: true
                        font.pixelSize: 10
                        onClicked: root.refreshSources()
                    }
                }
            }
        }

        Connections {
            target: backend
            function onMapCreated(mapId, title) { root.refreshSources() }
            function onImageAdded(imageId, name) { root.refreshSources() }
            function onImageDeleted(imageId) { root.refreshSources() }
            function onDataLoaded(name) { root.refreshSources() }
            function onToolCompleted(toolName, outputPath) {
                if (toolName === "Gradient Filter") {
                    root.runningTaskName = ""
                    statusLabel.text = "Gradient map registered under Maps (" + outputPath + ")"
                    statusLabel.color = successColor
                }
            }
            function onErrorOccurred(title, message) {
                if (title.indexOf("Gradient") >= 0) {
                    root.runningTaskName = ""
                    statusLabel.text = "Error: " + message
                    statusLabel.color = accentMagenta
                }
            }
            // A cancelled task reaches neither of the two handlers above, so
            // without this the panel goes on saying "Computing gradient...".
            function onOperationCancelled(name) {
                if (name !== root.runningTaskName) return
                root.runningTaskName = ""
                statusLabel.text = "Cancelled"
                statusLabel.color = textMuted
            }
        }

        GroupBox {
            title: "Gradient Method"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                ComboBox {
                    id: methodCombo
                    Layout.fillWidth: true
                    model: ["Sobel", "Prewitt", "Scharr"]
                }

                Label {
                    text: "Sobel: standard edge detection\n" +
                          "Prewitt: similar to Sobel, simpler kernel\n" +
                          "Scharr: better rotational symmetry\n\n" +
                          "Select several maps to filter them one after another — each " +
                          "produces its own gradient map, filed under Maps."
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                    color: textMuted
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: sourceList.selectedDatasets.length > 1
                      ? "Apply Gradient (" + sourceList.selectedDatasets.length + ")"
                      : "Apply Gradient"
                enabled: sourceList.selectedDatasets.length > 0
                primary: true
                onClicked: performGradient()
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

    Component.onCompleted: refreshSources()

    function refreshSources() {
        var entries = backend.getFieldSourceList()
        var labels = [], byLabel = {}, byRef = {}
        for (var i = 0; i < entries.length; i++) {
            var label = entries[i].label
            // Two maps can share a title; suffix the later one so the pick
            // stays unambiguous.
            if (byLabel[label] !== undefined) label = label + " (" + entries[i].ref + ")"
            labels.push(label)
            byLabel[label] = entries[i].ref
            byRef[entries[i].ref] = label
        }
        root.refForLabel = byLabel
        root.labelForRef = byRef
        sourceList.model = labels
        sourceList.pruneSelection()
    }

    function performGradient() {
        var picks = sourceList.selectedDatasets
        if (picks.length === 0) return
        var refs = []
        for (var i = 0; i < picks.length; i++) {
            var ref = root.refForLabel[picks[i]]
            if (ref !== undefined) refs.push(ref)
        }
        var method = methodCombo.currentText.toLowerCase()
        console.log("Applying gradient filter:", method, "to:", refs.join(", "))
        statusLabel.text = "Computing gradient..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("gradient_filter", refs,
                                                         { "method": method })
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
