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
import Qt.labs.platform 1.1 as Platform
import "../components"

// Integration Utility Tool
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
    property color accentMagenta: parentWindow ? parentWindow.accentMagenta : "#D60270"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"
    property color successColor: parentWindow ? parentWindow.successColor : "#2ECC71"

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Tool description
        Label {
            text: "Integration Utility"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Calculate the area under curves within specified intervals of X values."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: textMuted
        }

        // Dataset selection
        GroupBox {
            title: "Dataset Selection"
            Layout.fillWidth: true

            background: Rectangle {
                color: bgMedium
                border.color: bgLight
                radius: 4
                y: parent.topPadding - parent.padding
                width: parent.width
                height: parent.height - parent.topPadding + parent.padding
            }

            label: Label {
                text: parent.title
                color: accentPink
                font.bold: true
            }

            ColumnLayout {
                anchors.fill: parent

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                    bgColor: bgLight
                    borderColorNormal: accentPink
                    borderColorFocus: accentBlue
                    textColor: textLight
                    textMutedColor: textMuted
                }

                Label {
                    id: datasetInfo
                    text: getDatasetInfo()
                    font.pixelSize: 10
                    color: textMuted
                }
            }
        }

        // Integration intervals
        GroupBox {
            title: "Integration Intervals"
            Layout.fillWidth: true
            Layout.fillHeight: true

            background: Rectangle {
                color: bgMedium
                border.color: bgLight
                radius: 4
                y: parent.topPadding - parent.padding
                width: parent.width
                height: parent.height - parent.topPadding + parent.padding
            }

            label: Label {
                text: parent.title
                color: accentPink
                font.bold: true
            }

            ColumnLayout {
                anchors.fill: parent

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        text: "Interval List (" + intervalsModel.count + "):"
                        color: textLight
                    }

                    Item { Layout.fillWidth: true }

                    Button {
                        text: "Load from Peak Finder..."
                        onClicked: intervalFileDialog.open()

                        background: Rectangle {
                            color: parent.pressed ? accentBlue : (parent.hovered ? bgLight : bgMedium)
                            border.color: accentBlue
                            radius: 4
                        }
                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    Button {
                        text: "Add Interval"
                        onClicked: addInterval()

                        background: Rectangle {
                            color: parent.pressed ? accentPink : (parent.hovered ? bgLight : bgMedium)
                            border.color: accentPink
                            radius: 4
                        }
                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    Button {
                        text: "Clear All"
                        onClicked: intervalsModel.clear()

                        background: Rectangle {
                            color: parent.pressed ? accentMagenta : (parent.hovered ? bgLight : bgMedium)
                            border.color: accentMagenta
                            radius: 4
                        }
                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }

                // Interval selection checkboxes
                Rectangle {
                    Layout.fillWidth: true
                    height: 30
                    color: bgLight
                    radius: 4
                    visible: intervalsModel.count > 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 5

                        CheckBox {
                            id: selectAllCheck
                            text: "Select All"
                            checked: true
                            onCheckedChanged: {
                                for (var i = 0; i < intervalsModel.count; i++) {
                                    intervalsModel.setProperty(i, "selected", checked)
                                }
                            }

                            contentItem: Text {
                                text: parent.text
                                color: textMuted
                                leftPadding: parent.indicator.width + parent.spacing
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Label {
                            text: "Selected: " + getSelectedCount() + " / " + intervalsModel.count
                            color: textMuted
                            font.pixelSize: 11
                        }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: intervalList
                        model: ListModel {
                            id: intervalsModel
                        }
                        spacing: 2

                        delegate: Rectangle {
                            width: ListView.view.width - 10
                            height: 45
                            color: model.selected ? Qt.rgba(root.accentPink.r, root.accentPink.g, root.accentPink.b, 0.1) : bgLight
                            border.color: model.selected ? root.accentPink : bgMedium
                            border.width: 1
                            radius: 4

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 5
                                spacing: 10

                                CheckBox {
                                    checked: model.selected
                                    onCheckedChanged: model.selected = checked
                                }

                                Label {
                                    text: (index + 1) + "."
                                    Layout.preferredWidth: 30
                                    color: textMuted
                                }

                                TextField {
                                    id: lowerField
                                    Layout.preferredWidth: 100
                                    placeholderText: "Lower X"
                                    text: model.lower
                                    onTextChanged: model.lower = text

                                    background: Rectangle {
                                        color: bgMedium
                                        border.color: lowerField.activeFocus ? accentPink : bgLight
                                        radius: 3
                                    }
                                    color: textLight
                                }

                                Label {
                                    text: "to"
                                    color: textMuted
                                }

                                TextField {
                                    id: upperField
                                    Layout.preferredWidth: 100
                                    placeholderText: "Upper X"
                                    text: model.upper
                                    onTextChanged: model.upper = text

                                    background: Rectangle {
                                        color: bgMedium
                                        border.color: upperField.activeFocus ? accentPink : bgLight
                                        radius: 3
                                    }
                                    color: textLight
                                }

                                Item { Layout.fillWidth: true }

                                Button {
                                    text: "X"
                                    implicitWidth: 30
                                    onClicked: intervalsModel.remove(index)

                                    background: Rectangle {
                                        color: parent.hovered ? root.accentMagenta : "transparent"
                                        radius: 3
                                    }
                                    contentItem: Text {
                                        text: parent.text
                                        color: root.accentMagenta
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Action buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Button {
                text: "Calculate Integration"
                enabled: datasetCombo.currentIndex >= 0 && getSelectedCount() > 0

                background: Rectangle {
                    color: parent.enabled ? (parent.pressed ? Qt.darker(accentPink, 1.2) : accentPink) : bgLight
                    radius: 4
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.enabled ? bgDark : textMuted
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                }

                onClicked: performIntegration()
            }

            Button {
                text: "Cancel Operation"
                onClicked: backend.cancelCurrentOperation()

                background: Rectangle {
                    color: parent.hovered ? bgLight : bgMedium
                    border.color: textMuted
                    radius: 4
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() } else { var win = root.Window.window; if (win) win.close() }
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : bgMedium
                    border.color: textMuted
                    radius: 4
                }
                contentItem: Text {
                    text: parent.text
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    // File dialog for loading intervals from Peak Finder JSON
    Platform.FileDialog {
        id: intervalFileDialog
        title: "Load Intervals from Peak Finder"
        nameFilters: ["Interval Files (*.json)", "All Files (*)"]
        folder: backend.projectPath ? "file://" + backend.projectPath + "/outputs/peaks" : Platform.StandardPaths.writableLocation(Platform.StandardPaths.DocumentsLocation)

        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            loadIntervalsFromFile(path)
        }
    }

    function addInterval() {
        intervalsModel.append({
            lower: "",
            upper: "",
            selected: true
        })
    }

    function getSelectedCount() {
        var count = 0
        for (var i = 0; i < intervalsModel.count; i++) {
            if (intervalsModel.get(i).selected) {
                count++
            }
        }
        return count
    }

    function loadIntervalsFromFile(filePath) {
        console.log("Loading intervals from:", filePath)

        var intervals = backend.loadIntervalsFromFile(filePath)
        if (intervals && intervals.length > 0) {
            intervalsModel.clear()
            for (var i = 0; i < intervals.length; i++) {
                intervalsModel.append({
                    lower: intervals[i][0].toFixed(4),
                    upper: intervals[i][1].toFixed(4),
                    selected: true
                })
            }
            console.log("Loaded", intervals.length, "intervals")
        } else {
            console.log("No intervals found in file")
        }
    }

    function getDatasetInfo() {
        if (datasetCombo.currentIndex < 0) return ""

        var datasetName = datasetCombo.currentText
        var info = backend.getDatasetInfo(datasetName)

        return "Type: " + info.type + " | Dimensions: " + info.dimensions +
               " | Spectra: " + info.num_spectra + " | Points: " + info.num_points
    }

    function performIntegration() {
        console.log("Performing integration on:", datasetCombo.currentText)

        // Collect only selected intervals
        var intervals = []
        for (var i = 0; i < intervalsModel.count; i++) {
            var item = intervalsModel.get(i)
            if (item.selected && item.lower && item.upper) {
                intervals.push({
                    'lower': parseFloat(item.lower),
                    'upper': parseFloat(item.upper)
                })
            }
        }

        if (intervals.length === 0) {
            console.log("No valid intervals selected")
            return
        }

        console.log("Integrating over", intervals.length, "intervals")

        // Call backend
        var result = backend.integrate(datasetCombo.currentText, intervals)

        if (result) {
            console.log("Integration complete, saved to:", result)
        }
    }

    Component.onCompleted: {
        // Add default interval
        addInterval()
    }
}
