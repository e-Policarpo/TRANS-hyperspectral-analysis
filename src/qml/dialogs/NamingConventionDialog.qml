/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Dialog {
    id: dialog

    title: "Choose Dataset Names"
    modal: true
    width: 450
    height: 380

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentOrange: "#FFB7C5"  // Keep status color
    property color accentGreen: "#66ff99"   // Keep status color
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    // Check if [dataset_id] is in the pattern
    property bool hasDatasetId: conventionField.text.toLowerCase().indexOf("[dataset_id]") !== -1
    property bool hasIndex: conventionField.text.toLowerCase().indexOf("[index]") !== -1

    background: Rectangle {
        color: bgLight
        border.color: borderColor
        border.width: 1
        radius: 4
    }

    // Custom footer with OK and Cancel buttons
    footer: DialogButtonBox {
        background: Rectangle {
            color: bgMedium
        }

        Button {
            text: "OK"
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            enabled: hasDatasetId

            background: Rectangle {
                color: parent.enabled ? (parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentGreen, 1.2) : bgDark)) : Qt.darker(bgDark, 1.3)
                radius: 3
                border.color: parent.enabled ? accentGreen : borderColor
                border.width: 1
            }

            contentItem: Text {
                text: parent.text
                font.pixelSize: 12
                color: parent.enabled ? textLight : textMuted
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Button {
            text: "Cancel"
            DialogButtonBox.buttonRole: DialogButtonBox.RejectRole

            background: Rectangle {
                color: parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentBlue, 1.2) : bgDark)
                radius: 3
                border.color: borderColor
                border.width: 1
            }

            contentItem: Text {
                text: parent.text
                font.pixelSize: 12
                color: textLight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 12

        // Instructions
        Label {
            text: "Create a naming pattern for your datasets:"
            font.pixelSize: 13
            color: textLight
        }

        // Convention text field
        TextField {
            id: conventionField
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            text: "[dataset_id]"
            color: textLight
            placeholderText: "[dataset_id]"
            placeholderTextColor: textMuted
            selectByMouse: true
            font.pixelSize: 13

            background: Rectangle {
                color: bgDark
                border.color: conventionField.activeFocus ? accentBlue : borderColor
                border.width: 1
                radius: 3
            }
        }

        // Warning if [dataset_id] is missing
        Label {
            text: "[dataset_id] is required in the naming pattern"
            font.pixelSize: 11
            color: accentOrange
            visible: !hasDatasetId
        }

        // Token buttons
        Label {
            text: "Add tokens to the pattern:"
            font.pixelSize: 11
            color: textMuted
            Layout.topMargin: 4
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 4
            rowSpacing: 6
            columnSpacing: 6

            Button {
                text: "[dataset_id]"
                Layout.preferredWidth: 95
                Layout.preferredHeight: 32

                background: Rectangle {
                    color: parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentGreen, 1.2) : bgDark)
                    radius: 3
                    border.color: accentGreen
                    border.width: 2
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    font.bold: true
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                onClicked: insertToken("[dataset_id]")

                ToolTip.visible: hovered
                ToolTip.text: "Required. The base name of the dataset."
                ToolTip.delay: 500
            }

            Button {
                text: "[date]"
                Layout.preferredWidth: 95
                Layout.preferredHeight: 32

                background: Rectangle {
                    color: parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentBlue, 1.2) : bgDark)
                    radius: 3
                    border.color: borderColor
                    border.width: 1
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                onClicked: insertToken("[date]")

                ToolTip.visible: hovered
                ToolTip.text: "Current date (dd-mm-yyyy)"
                ToolTip.delay: 500
            }

            Button {
                text: "[time]"
                Layout.preferredWidth: 95
                Layout.preferredHeight: 32

                background: Rectangle {
                    color: parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentBlue, 1.2) : bgDark)
                    radius: 3
                    border.color: borderColor
                    border.width: 1
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                onClicked: insertToken("[time]")

                ToolTip.visible: hovered
                ToolTip.text: "Current time (HH-MM-SS)"
                ToolTip.delay: 500
            }

            Button {
                text: "[index]"
                Layout.preferredWidth: 95
                Layout.preferredHeight: 32

                background: Rectangle {
                    color: parent.pressed ? accentPink : (parent.hovered ? Qt.darker(accentBlue, 1.2) : bgDark)
                    radius: 3
                    border.color: borderColor
                    border.width: 1
                }

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 11
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                onClicked: insertToken("[index]")

                ToolTip.visible: hovered
                ToolTip.text: "Auto-incrementing number (001, 002, ...)"
                ToolTip.delay: 500
            }
        }

        // Starting index field (only enabled when [index] is in pattern)
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            opacity: hasIndex ? 1.0 : 0.4

            Label {
                text: "Starting index:"
                font.pixelSize: 11
                color: hasIndex ? textLight : textMuted
            }

            TextField {
                id: startIndexField
                Layout.preferredWidth: 60
                Layout.preferredHeight: 28
                text: "000"
                color: hasIndex ? textLight : textMuted
                enabled: hasIndex
                selectByMouse: true
                font.pixelSize: 11
                horizontalAlignment: Text.AlignHCenter
                validator: IntValidator { bottom: 0; top: 9999 }

                background: Rectangle {
                    color: hasIndex ? bgDark : Qt.darker(bgDark, 1.3)
                    border.color: startIndexField.activeFocus ? accentBlue : borderColor
                    border.width: 1
                    radius: 3
                }
            }

            Label {
                text: "(leave empty for 000)"
                font.pixelSize: 10
                color: textMuted
                visible: hasIndex
            }
        }

        // Preview section
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: Qt.rgba(0, 0, 0, 0.2)
            radius: 3
            border.color: borderColor
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 2

                Label {
                    text: "Preview:"
                    font.pixelSize: 10
                    color: textMuted
                }

                Label {
                    id: previewLabel
                    text: generatePreview()
                    font.pixelSize: 12
                    color: accentBlue
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }

        Item { Layout.fillHeight: true }
    }

    function insertToken(token) {
        var cursorPos = conventionField.cursorPosition
        var text = conventionField.text
        conventionField.text = text.substring(0, cursorPos) + token + text.substring(cursorPos)
        conventionField.cursorPosition = cursorPos + token.length
        conventionField.forceActiveFocus()
    }

    function generatePreview() {
        var pattern = conventionField.text
        var result = pattern

        // Replace tokens with sample values
        result = result.replace(/\[dataset_id\]/gi, "SampleData")
        result = result.replace(/\[date\]/gi, "17-12-2025")
        result = result.replace(/\[time\]/gi, "14-30-45")

        var startIdx = parseInt(startIndexField.text) || 0
        var indexStr = startIdx.toString().padStart(3, '0')
        result = result.replace(/\[index\]/gi, indexStr)

        return result
    }

    // Update preview when text changes
    Connections {
        target: conventionField
        function onTextChanged() {
            previewLabel.text = generatePreview()
        }
    }

    Connections {
        target: startIndexField
        function onTextChanged() {
            previewLabel.text = generatePreview()
        }
    }

    onOpened: {
        // Load current convention from backend
        if (backend) {
            var current = backend.namingConvention
            // Convert old [dataset_name] to [dataset_id]
            current = current.replace(/\[dataset_name\]/gi, "[dataset_id]")
            conventionField.text = current
            startIndexField.text = backend.getNamingIndexStart().toString().padStart(3, '0')
        }
        conventionField.forceActiveFocus()
        previewLabel.text = generatePreview()
    }

    onAccepted: {
        if (backend && hasDatasetId) {
            // Convert [dataset_id] back to [dataset_name] for backend compatibility
            var pattern = conventionField.text.replace(/\[dataset_id\]/gi, "[dataset_name]")
            backend.setNamingConvention(pattern)

            // Set starting index
            var startIdx = parseInt(startIndexField.text) || 0
            backend.setNamingIndexStart(startIdx)

            console.log("Naming convention set to:", pattern)
        }
    }
}
