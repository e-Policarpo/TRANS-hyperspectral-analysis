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

// Truncate Data Tool
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
            text: "Truncate Data Range"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Keep only the part of each spectrum inside a range of the independent " +
                  "variable (bias, wavelength, wavenumber…)."
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
                    onSelectionChanged: {
                        statusLabel.text = ""
                        rangeLabel.text = root.currentRangeText()
                    }
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
                    id: rangeLabel
                    Layout.fillWidth: true
                    text: root.currentRangeText()
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
                if (toolName === "Truncate Data") {
                    root.runningTaskName = ""
                    statusLabel.text = "✓ Truncated: " + outputPath
                    statusLabel.color = successColor
                }
            }
            function onErrorOccurred(title, message) {
                if (title.indexOf("Truncat") >= 0) {
                    root.runningTaskName = ""
                    statusLabel.text = "✗ Error: " + message
                    statusLabel.color = accentMagenta
                }
            }
            // A cancelled task reaches neither of the two handlers above, so
            // without this the panel goes on saying "Truncating data...".
            function onOperationCancelled(name) {
                if (name !== root.runningTaskName) return
                root.runningTaskName = ""
                statusLabel.text = "Cancelled"
                statusLabel.color = textMuted
            }
        }

        GroupBox {
            title: "Truncation Range"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 8
                columnSpacing: 10

                Label {
                    text: "Minimum Value:"
                    Layout.alignment: Qt.AlignRight
                }
                TextField {
                    // A bare TextField takes the style's own palette, which under the
                    // Basic style is a light one — white ground, black text — regardless
                    // of what the window around it is painted. Say it explicitly.
                    id: minValueField
                    Layout.fillWidth: true
                    color: root.textLight
                    placeholderTextColor: root.textMuted
                    background: Rectangle {
                        color: root.bgDark
                        border.color: root.bgLight
                        border.width: 1
                        radius: 4
                    }
                    placeholderText: "e.g., -2.0"
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                }

                Label {
                    text: "Maximum Value:"
                    Layout.alignment: Qt.AlignRight
                }
                TextField {
                    id: maxValueField
                    Layout.fillWidth: true
                    color: root.textLight
                    placeholderTextColor: root.textMuted
                    background: Rectangle {
                        color: root.bgDark
                        border.color: root.bgLight
                        border.width: 1
                        radius: 4
                    }
                    placeholderText: "e.g., 2.0"
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                }

                Label {
                    Layout.columnSpan: 2
                    font.pixelSize: 10
                    color: root.isRangeValid() ? successColor : accentMagenta
                    text: root.rangeValidationText()
                    visible: minValueField.text !== "" && maxValueField.text !== ""
                }

                Label {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    text: "The same range is applied to every selected dataset, each " +
                          "producing its own '- Truncated' output."
                    font.pixelSize: 10
                    font.italic: true
                    color: textMuted
                    wrapMode: Text.Wrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            ToolButton {
                text: datasetList.selectedDatasets.length > 1
                      ? "Truncate (" + datasetList.selectedDatasets.length + ")"
                      : "Truncate"
                enabled: datasetList.selectedDatasets.length > 0 && root.isRangeValid() && !backend.isBusy
                primary: true
                onClicked: performTruncation()
            }

            ToolButton {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()
            }

            ToolButton {
                text: "Reset"
                onClicked: resetFields()
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
        rangeLabel.text = currentRangeText()
    }

    // The extent of the selection: one dataset's range, or the envelope of
    // several so the user sees what a single range will cut from each.
    function currentRangeText() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return "Select a dataset to see its range"
        var lo = Infinity, hi = -Infinity, unit = "", variable = ""
        for (var i = 0; i < picks.length; i++) {
            var info = backend.getDatasetInfo(picks[i])
            if (!info || info.x_min === undefined) continue
            lo = Math.min(lo, info.x_min)
            hi = Math.max(hi, info.x_max)
            unit = info.x_unit || unit
            variable = info.independent_var || variable
        }
        if (!isFinite(lo)) return "No axis range available"
        var span = variable + ": " + lo.toPrecision(5) + " … " + hi.toPrecision(5) + (unit ? " " + unit : "")
        return picks.length > 1 ? picks.length + " datasets — combined range " + span : "Current range — " + span
    }

    function isRangeValid() {
        if (minValueField.text === "" || maxValueField.text === "") return false
        var minVal = parseFloat(minValueField.text)
        var maxVal = parseFloat(maxValueField.text)
        return !isNaN(minVal) && !isNaN(maxVal) && minVal < maxVal
    }

    function rangeValidationText() {
        if (!isRangeValid()) return "⚠ Invalid range: maximum must be greater than minimum"
        var range = parseFloat(maxValueField.text) - parseFloat(minValueField.text)
        return "✓ Valid range: " + range.toFixed(3) + " units"
    }

    function resetFields() {
        minValueField.text = ""
        maxValueField.text = ""
        statusLabel.text = ""
    }

    function performTruncation() {
        if (!isRangeValid()) return
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        var minVal = parseFloat(minValueField.text)
        var maxVal = parseFloat(maxValueField.text)
        console.log("Truncating:", datasets.join(", "), "to [", minVal, ",", maxVal, "]")
        statusLabel.text = "Truncating data..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("truncate", datasets, {
            "min_val": minVal,
            "max_val": maxVal
        })
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
