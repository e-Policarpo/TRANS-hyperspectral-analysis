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
    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Peak Indexing Utility"
            font.pixelSize: 18
            font.bold: true
        }

        Label {
            text: "Automatically find and index peaks in spectral data, including position and FWHM."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#9B4F96"
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
                    color: "#666666"
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

                Label { text: "Minimum Prominence:" }
                SpinBox {
                    id: prominenceSpin
                    from: 1
                    to: 100
                    value: 10
                    property real realValue: value / 100.0

                    Label {
                        anchors.left: parent.right
                        anchors.leftMargin: 5
                        text: (prominenceSpin.realValue).toFixed(2)
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
                    text: "\nProminence: How much peak stands out from surroundings\n" +
                          "Min Distance: Minimum spacing between peaks"
                    font.pixelSize: 10
                    color: "#666666"
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
                color: "#666666"
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
                    var win = Window.window
                    if (win) win.close()
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
        console.log("Finding peaks in:", datasetCombo.currentText,
                   "Prominence:", prominenceSpin.realValue,
                   "Min distance:", minDistanceSpin.value)

        var result = backend.findPeaks(
            datasetCombo.currentText,
            prominenceSpin.realValue,
            minDistanceSpin.value
        )

        if (result) {
            console.log("Peak finding complete, saved to:", result)
        }
    }
}
