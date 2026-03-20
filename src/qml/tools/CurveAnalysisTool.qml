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

// Curve Analysis Tool
Item {
    id: root
    property var closeWindow: null

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
            text: "Curve Analysis"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Interactive plotting and manipulation of spectral curves."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                    onCurrentIndexChanged: updateInfo()
                }

                Label {
                    id: datasetInfo
                    text: getDatasetInfo()
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                }
            }
        }

        GroupBox {
            title: "Plot Options"
            Layout.fillWidth: true

            ColumnLayout {
                anchors.fill: parent

                CheckBox {
                    id: showGridCheck
                    text: "Show grid"
                    checked: true
                }

                CheckBox {
                    id: logScaleCheck
                    text: "Log scale Y-axis"
                    checked: false
                }

                RowLayout {
                    Label { text: "Plot range:" }
                    ComboBox {
                        id: rangeCombo
                        model: ["Full range", "Auto zoom", "Custom"]
                    }
                }
            }
        }

        GroupBox {
            title: "Curve Selection"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent

                Label {
                    text: "Select curves to plot (multi-select):"
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: curveList
                        model: getCurveList()
                        delegate: CheckBox {
                            text: modelData
                            checked: index === 0
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Plot Selected Curves"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: plotCurves()
            }

            Button {
                text: "Export Plot"
                enabled: false
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

    function getDatasetInfo() {
        if (datasetCombo.currentIndex < 0) return "No dataset selected"

        var datasetName = datasetCombo.currentText
        var info = backend.getDatasetInfo(datasetName)

        return "Type: " + info.type + " | Dimensions: " + info.dimensions +
               " | Spectra: " + info.num_spectra + " | Points: " + info.num_points
    }

    function getCurveList() {
        if (datasetCombo.currentIndex < 0) return []

        var info = backend.getDatasetInfo(datasetCombo.currentText)
        var numCurves = info.num_spectra
        var curves = []

        for (var i = 0; i < Math.min(numCurves, 20); i++) {
            curves.push("Curve " + (i + 1))
        }

        if (numCurves > 20) {
            curves.push("... (" + numCurves + " total)")
        }

        return curves
    }

    function updateInfo() {
        datasetInfo.text = getDatasetInfo()
        curveList.model = getCurveList()
    }

    function plotCurves() {
        console.log("Plotting curves from:", datasetCombo.currentText)
        console.log("Note: Matplotlib integration needed for actual plotting")

        // Placeholder - would need matplotlib integration
        console.log("Plot would show selected curves with options:",
                   "Grid:", showGridCheck.checked,
                   "Log scale:", logScaleCheck.checked)
    }
}
