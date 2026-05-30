/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Background Subtraction Tool — subtract one reference background dataset
 * (e.g. shutter-closed acquisition) from one or more signal datasets,
 * truncating to the overlap of the x axes if they don't match exactly.
 *
 * Made by Eduarda Policarpo
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

    property var parentWindow: ApplicationWindow.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"
    property color borderColor: parentWindow ? parentWindow.borderColor : "#7B3F76"

    implicitWidth: 480
    implicitHeight: 600

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Background Subtraction"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Pick the background reference and the signal datasets to correct. " +
                  "Each signal will get its own '- BgSub' output. Axes are auto-aligned; " +
                  "if a signal's axis only partially overlaps the background's, the output " +
                  "is truncated to the overlap interval (logged to the metadata)."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
            font.pixelSize: 11
        }

        GroupBox {
            title: "Background dataset"
            Layout.fillWidth: true
            DatasetComboBox {
                id: backgroundCombo
                Layout.fillWidth: true
                model: backend ? backend.getDatasetList() : []
            }
        }

        GroupBox {
            title: "Signal datasets (check one or more)"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Button {
                        text: "Select all"
                        onClicked: setAllChecked(true)
                    }
                    Button {
                        text: "Clear"
                        onClicked: setAllChecked(false)
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: selectedCount() + " selected"
                        color: textMuted
                        font.pixelSize: 11
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: datasetList
                        model: backend ? backend.getDatasetList() : []
                        delegate: CheckBox {
                            width: ListView.view.width
                            text: modelData
                            // Disable picking the background as its own signal
                            // — it would just produce zero everywhere.
                            enabled: modelData !== backgroundCombo.currentText
                            contentItem: Text {
                                text: parent.text
                                color: parent.enabled ? textLight : textMuted
                                leftPadding: parent.indicator.width + 6
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                            onCheckedChanged: countLabel.text = selectedCount() + " selected"
                        }
                    }
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

        Label { id: countLabel; visible: false }  // hidden helper for change-notification

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Subtract"
                highlighted: true
                enabled: backgroundCombo.currentIndex >= 0 && selectedCount() > 0
                onClicked: performSubtraction()
            }

            Button {
                text: "Cancel"
                onClicked: backend.cancelCurrentOperation()
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

    Connections {
        target: backend
        enabled: backend !== null
        function onToolCompleted(toolName, outputPath) {
            if (toolName === "Background Subtraction") {
                statusLabel.text = "Done. Corrected datasets added to the browser (suffix '- BgSub')."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Background") >= 0) {
                statusLabel.text = "Error: " + message
            }
        }
    }

    function selectedCount() {
        var n = 0
        for (var i = 0; i < datasetList.count; ++i) {
            var item = datasetList.itemAtIndex(i)
            if (item && item.checked && item.enabled) n++
        }
        return n
    }

    function selectedNames() {
        var out = []
        for (var i = 0; i < datasetList.count; ++i) {
            var item = datasetList.itemAtIndex(i)
            if (item && item.checked && item.enabled) {
                out.push(datasetList.model[i])
            }
        }
        return out
    }

    function setAllChecked(checked) {
        for (var i = 0; i < datasetList.count; ++i) {
            var item = datasetList.itemAtIndex(i)
            if (item && item.enabled) item.checked = checked
        }
        countLabel.text = selectedCount() + " selected"
    }

    function performSubtraction() {
        var names = selectedNames()
        if (names.length === 0) {
            statusLabel.text = "Pick at least one signal dataset."
            return
        }
        statusLabel.text = "Subtracting background from " + names.length + " dataset(s)..."
        backend.subtractBackground(names, backgroundCombo.currentText)
    }
}
