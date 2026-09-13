/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Cosmic Ray / Hot Pixel Filter — remove narrow CCD spikes from luminescence
 * and Raman spectra before peak finding / fitting / integration.
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

Item {
    id: root
    property var closeWindow: null

    // cosmicRayFilter() hands no task name back, so this panel can only know
    // that it is waiting for a run, not which one it is waiting for.
    property bool running: false

    // Empty by design here: see the comment on `running`. Kept so the
    // destruction handler reads the same as in every other tool.
    property string runningTaskName: ""

    // `Window.window`, not `ApplicationWindow.window`: a tool is hosted
    // either by the embedded window (whose root IS the ApplicationWindow) or
    // by ToolWindow, whose root is a plain Window. The ApplicationWindow
    // attached property resolves to null in the second case, and every colour
    // below then falls through to the singleton instead of following the
    // host. Window.window resolves in both.
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    implicitWidth: mainLayout.implicitWidth + 20
    implicitHeight: mainLayout.implicitHeight + 20

    ColumnLayout {
        id: mainLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Cosmic Ray Filter"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Remove narrow, very-intense CCD spikes (cosmic-ray hits, hot pixels) " +
                  "that smoothing leaves behind and that confuse peak finding."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            DatasetComboBox {
                id: datasetCombo
                Layout.fillWidth: true
                model: backend ? backend.getDatasetList() : []
            }
        }

        GroupBox {
            title: "Detection Parameters"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 2
                columnSpacing: 8
                rowSpacing: 6

                Label { text: "Threshold (σ):"; color: textLight }
                SpinBox {
                    id: thresholdSpin
                    from: 30
                    to: 200
                    value: 50  // → 5.0σ
                    property real realValue: value / 10.0
                    textFromValue: function(v) { return (v / 10.0).toFixed(1) }
                }

                Label { text: "Median window (samples):"; color: textLight }
                SpinBox {
                    id: windowSpin
                    from: 3
                    to: 21
                    stepSize: 2
                    value: 5
                }

                Label { text: "Max spike width (samples):"; color: textLight }
                SpinBox {
                    id: maxWidthSpin
                    from: 1
                    to: 5
                    value: 2
                }

                Label {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "A sample is flagged when it exceeds the local median by more than " +
                          "Threshold × σ (σ estimated from MAD of the median residuals). " +
                          "Connected runs of flagged samples wider than Max spike width are kept " +
                          "(they are likely real, narrow peaks)."
                    font.pixelSize: 10
                    color: textMuted
                }
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

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: "Filter"
                enabled: datasetCombo.currentIndex >= 0
                primary: true
                onClicked: performFilter()
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

    Connections {
        target: backend
        enabled: backend !== null
        function onToolCompleted(toolName, outputPath) {
            if (toolName === "Cosmic Ray Filter") {
                root.running = false
                statusLabel.text = "Done. A '- CR Cleaned' dataset has been added to the browser."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Cosmic") >= 0) {
                root.running = false
                statusLabel.text = "Error: " + message
            }
        }
        // Cancel reaches neither handler above, so the status line would keep
        // saying "Filtering cosmic rays..." for the life of the window.
        function onOperationCancelled(name) {
            if (!root.running || name.indexOf("Cosmic Ray Filter") !== 0) return
            root.running = false
            statusLabel.text = "Cancelled"
            statusLabel.color = textMuted
        }
    }

    function performFilter() {
        root.running = true
        statusLabel.text = "Filtering cosmic rays..."
        backend.cosmicRayFilter(
            datasetCombo.currentText,
            thresholdSpin.realValue,
            windowSpin.value,
            maxWidthSpin.value
        )
    }

    Component.onDestruction: {
        // No task name to cancel by (see `runningTaskName`), so the run can
        // only be stopped as "the current one", and only while this panel is
        // really waiting for one.
        if (root.running) backend.cancelCurrentOperation()
    }
}
