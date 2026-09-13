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

// Subtract Detector Background: a measured reference (dark frame, substrate,
// empty-cell spectrum) taken away from each signal dataset. This is a
// dataset-minus-dataset operation — for a fitted baseline see Curve
// Background Flattening. The file keeps its old name so the tool map and
// docs history still point here.
Item {
    id: root
    property var closeWindow: null

    // subtractBackground() hands no task name back, so this panel cannot ask
    // for its own run by name — it can only know whether it is waiting for
    // one, which is what the cancel handler and the close below need.
    property bool running: false

    // Empty by design here: see the comment on `running`. Kept so the
    // destruction handler reads the same as in every other tool.
    property string runningTaskName: ""

    property bool datasetDropActive: false

    // Dropped datasets join the SIGNAL selection; the background is a
    // single pick and stays where it is.
    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        signalList.addToSelection(names)
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

    implicitWidth: 480
    implicitHeight: 600

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Subtract Detector Background"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Subtract a measured background — a dark frame, a bare-substrate or " +
                  "empty-cell spectrum — from each signal dataset. Every signal gets its " +
                  "own '- BgSub' output. Axes are aligned automatically; where a signal " +
                  "only partly overlaps the background, the output is cut to the overlap " +
                  "(recorded in the metadata)."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
            font.pixelSize: 11
        }

        GroupBox {
            title: "Background dataset (the reference to take away)"
            Layout.fillWidth: true

            DatasetComboBox {
                id: backgroundCombo
                Layout.fillWidth: true
                model: backend ? backend.getDatasetList() : []
            }
        }

        GroupBox {
            title: "Signal datasets"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                DatasetMultiSelect {
                    id: signalList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 130
                    model: backend ? backend.getDatasetList() : []

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
                              ? "Drop to add to the signals"
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
                    visible: signalList.selectedDatasets.indexOf(backgroundCombo.currentText) >= 0
                    text: "The background is also picked as a signal — it would come out as zero everywhere and is skipped."
                    font.pixelSize: 10
                    color: accentMagenta
                    wrapMode: Text.Wrap
                }
            }
        }

        Connections {
            target: backend
            enabled: backend !== null
            function onDataLoaded(name) { root.refreshDatasets() }
            function onToolCompleted(toolName, outputPath) {
                if (toolName === "Subtract Detector Background") {
                    root.running = false
                    statusLabel.text = "Done. Corrected datasets added to the browser (suffix '- BgSub')."
                    statusLabel.color = successColor
                }
            }
            function onErrorOccurred(title, message) {
                if (title.indexOf("Background") >= 0) {
                    root.running = false
                    statusLabel.text = "Error: " + message
                    statusLabel.color = accentMagenta
                }
            }
            // Cancel reaches neither handler above. With no task name to match
            // on, the backend's name for the run is the only thing to go by —
            // and it is only acted on while this panel is actually waiting.
            function onOperationCancelled(name) {
                if (!root.running || name.indexOf("Subtract Background") !== 0) return
                root.running = false
                statusLabel.text = "Cancelled"
                statusLabel.color = textMuted
            }
        }

        Label {
            id: statusLabel
            text: ""
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentBlue
            visible: text !== ""
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: root.signalNames().length > 1
                      ? "Subtract (" + root.signalNames().length + ")"
                      : "Subtract"
                primary: true
                enabled: backgroundCombo.currentIndex >= 0 && root.signalNames().length > 0
                onClicked: performSubtraction()
            }

            ToolButton {
                text: "Cancel"
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
        var list = backend.getDatasetList()
        var current = backgroundCombo.currentText
        backgroundCombo.model = list
        var idx = list.indexOf(current)
        if (idx >= 0) backgroundCombo.currentIndex = idx
        signalList.model = list
        signalList.pruneSelection()
    }

    // Signals minus the background itself.
    function signalNames() {
        var out = []
        var picks = signalList.selectedDatasets
        for (var i = 0; i < picks.length; i++)
            if (picks[i] !== backgroundCombo.currentText) out.push(picks[i])
        return out
    }

    function performSubtraction() {
        var names = signalNames()
        if (names.length === 0) {
            statusLabel.text = "Pick at least one signal dataset."
            return
        }
        root.running = true
        statusLabel.text = "Subtracting background from " + names.length + " dataset(s)..."
        statusLabel.color = accentBlue
        backend.subtractBackground(names, backgroundCombo.currentText)
    }

    Component.onDestruction: {
        // No task name to cancel by (see `runningTaskName`), so the run this
        // panel is waiting for can only be stopped as "the current one" — and
        // only while it really is waiting for one.
        if (root.running) backend.cancelCurrentOperation()
    }
}
