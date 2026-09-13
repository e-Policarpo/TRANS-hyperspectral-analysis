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

// 1D FFT Tool
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
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color successColor: (parentWindow && parentWindow.successColor !== undefined) ? parentWindow.successColor : Theme.successColor

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "1D FFT"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Fourier-transform every spectrum of a dataset to find its periodic components " +
                  "— a beating in a bias sweep, a fringe period in a wavelength scan."
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
                if (toolName === "1D FFT") {
                    root.runningTaskName = ""
                    statusLabel.text = "Done — magnitude and phase datasets are in the project browser."
                    statusLabel.color = successColor
                }
            }
            function onErrorOccurred(title, message) {
                if (title.indexOf("FFT") >= 0) {
                    root.runningTaskName = ""
                    statusLabel.text = "Error: " + message
                    statusLabel.color = accentMagenta
                }
            }
            // A cancelled task reaches neither of the two handlers above, so
            // without this the panel goes on claiming it is transforming.
            function onOperationCancelled(name) {
                if (name !== root.runningTaskName) return
                root.runningTaskName = ""
                statusLabel.text = "Cancelled"
                statusLabel.color = textMuted
            }
        }

        GroupBox {
            title: "Transform"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 6
                columnSpacing: 10

                Label { text: "Window:" }
                ComboBox {
                    id: windowCombo
                    Layout.fillWidth: true
                    model: ["None (rectangular)", "Hann", "Hamming", "Blackman"]
                    currentIndex: 1
                }

                CheckBox {
                    id: detrendCheck
                    Layout.columnSpan: 2
                    text: "Remove the mean first (otherwise the DC term dwarfs everything)"
                    checked: true
                }

                CheckBox {
                    id: oneSidedCheck
                    Layout.columnSpan: 2
                    text: "One-sided spectrum (non-negative frequencies only)"
                    checked: true
                }

                CheckBox {
                    id: powerCheck
                    Layout.columnSpan: 2
                    text: "Power spectrum |F|² instead of magnitude |F|"
                    checked: false
                }
            }
        }

        GroupBox {
            title: "Output"
            Layout.fillWidth: true

            Label {
                text: "Two datasets per input, filed in the project browser:\n" +
                      "• <name> - FFT " + (powerCheck.checked ? "Power" : "Magnitude") + "\n" +
                      "• <name> - FFT Phase (radians)\n" +
                      "The frequency axis is 1/(axis unit) — 1/V for a bias sweep.\n" +
                      "Both are also written as CSV under <project>_outputs/fft/.\n\n" +
                      "Select several datasets to transform them one after another."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: datasetList.selectedDatasets.length > 1
                      ? "Calculate FFT (" + datasetList.selectedDatasets.length + ")"
                      : "Calculate FFT"
                enabled: datasetList.selectedDatasets.length > 0
                primary: true
                onClicked: performFFT()
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
        if (picks.length > 1) return picks.length + " datasets — transformed one after another"
        var info = backend.getDatasetInfo(picks[0])
        if (!info || !info.type) return ""
        return "Type: " + info.type + " | Spectra: " + info.num_spectra +
               " | Points: " + info.num_points + " | Variable: " + info.independent_var
    }

    function performFFT() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        var windows = ["none", "hann", "hamming", "blackman"]
        statusLabel.text = "Transforming..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("fft_1d", datasets, {
            "window": windows[windowCombo.currentIndex],
            "detrend": detrendCheck.checked,
            "one_sided": oneSidedCheck.checked,
            "power_spectrum": powerCheck.checked
        })
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
