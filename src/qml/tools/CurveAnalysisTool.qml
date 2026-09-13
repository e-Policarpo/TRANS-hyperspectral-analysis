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

// Curve Plotting (formerly "Curve Analysis"): overlay curves from one or
// more datasets in a single graph window. A viewer — it writes nothing.
// The file keeps its old name so the tool map and docs history still
// point here.
Item {
    id: root
    property var closeWindow: null

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
            text: "Curve Plotting"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Overlay curves from one or more datasets in a single graph window " +
                  "to compare them. Nothing is written."
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
                    onSelectionChanged: summaryLabel.text = root.selectionSummary()
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
                    id: summaryLabel
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
        }

        GroupBox {
            title: "Curves to plot (per dataset)"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 6
                columnSpacing: 10

                Label { text: "Selection:" }
                ComboBox {
                    id: modeCombo
                    Layout.fillWidth: true
                    model: ["All curves", "First N curves", "Every Nth curve", "Index range"]
                }

                Label { text: "N:"; visible: modeCombo.currentIndex === 1 || modeCombo.currentIndex === 2 }
                SpinBox {
                    id: nSpin
                    from: 1; to: 100000; value: 10; editable: true
                    visible: modeCombo.currentIndex === 1 || modeCombo.currentIndex === 2
                }

                Label { text: "From (1-based):"; visible: modeCombo.currentIndex === 3 }
                SpinBox {
                    id: startSpin
                    from: 1; to: 100000; value: 1; editable: true
                    visible: modeCombo.currentIndex === 3
                }

                Label { text: "To (0 = last):"; visible: modeCombo.currentIndex === 3 }
                SpinBox {
                    id: stopSpin
                    from: 0; to: 100000; value: 0; editable: true
                    visible: modeCombo.currentIndex === 3
                }

                CheckBox {
                    id: normalizeCheck
                    Layout.columnSpan: 2
                    text: "Normalise each curve to its maximum"
                    checked: false
                }

                Label { text: "Vertical offset:" }
                SpinBox {
                    id: offsetSpin
                    Layout.fillWidth: true
                    from: 0; to: 1000000; value: 0; stepSize: 1; editable: true
                    property int decimals: 3
                    property real realValue: value / 1000
                    textFromValue: function(value, locale) { return Number(value / 1000).toLocaleString(locale, 'f', decimals) }
                    valueFromText: function(text, locale) { return Math.round(Number.fromLocaleString(locale, text) * 1000) }
                }
            }
        }

        GroupBox {
            title: "Information"
            Layout.fillWidth: true

            Label {
                text: "Curves are labelled '<dataset> - <spectrum>' so the legend still " +
                      "says where each came from. Use a vertical offset for a waterfall " +
                      "view of many spectra. Plotting hundreds of curves is slow — pick " +
                      "'Every Nth' for a large map."
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: "Plot"
                enabled: datasetList.selectedDatasets.length > 0
                primary: true
                onClicked: plotCurves()
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
        summaryLabel.text = selectionSummary()
    }

    function selectionSummary() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return "No dataset selected"
        var total = 0
        for (var i = 0; i < picks.length; i++) {
            var info = backend.getDatasetInfo(picks[i])
            if (info && info.num_spectra) total += info.num_spectra
        }
        return picks.length + " dataset" + (picks.length > 1 ? "s" : "") + ", " + total + " spectra in total"
    }

    function plotCurves() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0) return
        var modes = ["all", "first", "every", "range"]
        backend.plotDatasetCurves(datasets, {
            "mode": modes[modeCombo.currentIndex],
            "count": nSpin.value,
            "step": nSpin.value,
            "start": startSpin.value,
            "stop": stopSpin.value,
            "normalize": normalizeCheck.checked,
            "offset": offsetSpin.realValue
        })
    }
}
