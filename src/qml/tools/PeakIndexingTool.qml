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

// Peak Indexing Tool
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
            text: "Peak Indexing Utility"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Automatically find and index peaks in spectral data, including position and FWHM."
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
                    model: getNoBaselineDatasets()
                }

                Label {
                    text: "Tip: Use baseline-corrected data (NoBaseline_...) for best results"
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                }
            }
        }

        GroupBox {
            title: "Peak Detection Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2

                Label { text: "Prominence:" }
                CheckBox {
                    id: adaptiveProminenceCheck
                    text: "Adaptive (recommended)"
                    checked: true
                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        leftPadding: parent.indicator.width + 6
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Label {
                    text: "Minimum Prominence:"
                    color: adaptiveProminenceCheck.checked ? textMuted : textLight
                }
                SpinBox {
                    id: prominenceSpin
                    from: 1
                    to: 100
                    value: 10
                    enabled: !adaptiveProminenceCheck.checked
                    property real realValue: value / 100.0

                    Label {
                        anchors.left: parent.right
                        anchors.leftMargin: 5
                        text: (prominenceSpin.realValue).toFixed(2)
                        color: adaptiveProminenceCheck.checked ? textMuted : textLight
                    }
                }

                Label { text: "Min Distance (points):" }
                SpinBox {
                    id: minDistanceSpin
                    from: 1
                    to: 50
                    value: 5
                }

                Label {
                    Layout.columnSpan: 2
                    text: "\nAdaptive prominence is estimated per spectrum from the noise level\n" +
                          "(max of 5% of signal span and 3× the noise σ). Uncheck to set it manually.\n" +
                          "Min Distance: Minimum spacing between peaks"
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        GroupBox {
            title: "Output"
            Layout.fillWidth: true

            Label {
                text: "Peak data will include:\n" +
                      "• Peak position (X value)\n" +
                      "• Peak height\n" +
                      "• Peak prominence\n" +
                      "• FWHM (Full Width at Half Maximum)\n\n" +
                      "Saved as CSV with one row per peak"
                wrapMode: Text.Wrap
                font.pixelSize: 10
                color: textMuted
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Find Peaks"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: performPeakFinding()
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

    function getNoBaselineDatasets() {
        var all = backend.getDatasetList()
        // Prefer NoBaseline datasets but show all
        return all.length > 0 ? all : ["No datasets loaded"]
    }

    function performPeakFinding() {
        // 0 is the backend sentinel for "use adaptive prominence per spectrum".
        var prominence = adaptiveProminenceCheck.checked ? 0.0 : prominenceSpin.realValue
        console.log("Finding peaks in:", datasetCombo.currentText,
                   "Prominence:", adaptiveProminenceCheck.checked ? "adaptive" : prominence,
                   "Min distance:", minDistanceSpin.value)

        var result = backend.findPeaks(
            datasetCombo.currentText,
            prominence,
            minDistanceSpin.value
        )

        if (result) {
            console.log("Peak finding complete, saved to:", result)
        }
    }
}
