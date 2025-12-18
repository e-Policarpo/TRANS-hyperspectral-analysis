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
import QtQuick.Dialogs
import QtQuick.Window 2.15

// Custom import dialog that allows selecting files OR folders
Dialog {
    id: dialog

    title: "Import Measurement"
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    width: 600
    height: 500

    property var selectedItems: []  // Can contain file paths or folder path
    property bool isFolderMode: false

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    background: Rectangle {
        color: bgLight
        border.color: borderColor
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Label {
            text: "Choose import mode:"
            font.pixelSize: 13
            font.bold: true
            color: textLight
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            RadioButton {
                id: filesMode
                text: "Select Files"
                checked: true

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 13
                    color: textLight
                    leftPadding: parent.indicator.width + 8
                    verticalAlignment: Text.AlignVCenter
                }

                indicator: Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    border.color: textLight
                    border.width: 2
                    color: "transparent"

                    Rectangle {
                        anchors.centerIn: parent
                        width: 10
                        height: 10
                        radius: 5
                        color: accentPink
                        visible: parent.parent.checked
                    }
                }

                onCheckedChanged: {
                    if (checked) {
                        dialog.isFolderMode = false
                        selectedItems = []
                        updateSelectionInfo()
                    }
                }
            }

            RadioButton {
                id: folderMode
                text: "Select Entire Folder"

                contentItem: Text {
                    text: parent.text
                    font.pixelSize: 13
                    color: textLight
                    leftPadding: parent.indicator.width + 8
                    verticalAlignment: Text.AlignVCenter
                }

                indicator: Rectangle {
                    width: 18
                    height: 18
                    radius: 9
                    border.color: textLight
                    border.width: 2
                    color: "transparent"

                    Rectangle {
                        anchors.centerIn: parent
                        width: 10
                        height: 10
                        radius: 5
                        color: accentPink
                        visible: parent.parent.checked
                    }
                }

                onCheckedChanged: {
                    if (checked) {
                        dialog.isFolderMode = true
                        selectedItems = []
                        updateSelectionInfo()
                    }
                }
            }
        }

        Label {
            text: dialog.isFolderMode ?
                  "Click 'Browse' to select a folder containing measurement files:" :
                  "Click 'Browse' to select one or more measurement files:"
            font.pixelSize: 12
            color: textMuted
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Button {
            text: "Browse..."
            Layout.preferredHeight: 40
            font.pixelSize: 13

            onClicked: {
                if (dialog.isFolderMode) {
                    folderDialog.open()
                } else {
                    fileDialog.open()
                }
            }

            background: Rectangle {
                color: parent.pressed ? accentPink : (parent.hovered ? bgDark : bgLight)
                border.color: accentPink
                border.width: 2
                radius: 4
            }

            contentItem: Text {
                text: parent.text
                font: parent.font
                color: textLight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            border.color: borderColor
            border.width: 1
            radius: 3

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 5

                Label {
                    text: "Selected:"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    TextArea {
                        id: selectionInfo
                        readOnly: true
                        text: "Nothing selected"
                        font.pixelSize: 11
                        color: textMuted
                        wrapMode: Text.Wrap
                        selectByMouse: true

                        background: Rectangle {
                            color: "transparent"
                        }
                    }
                }

                Label {
                    id: countLabel
                    text: ""
                    font.pixelSize: 11
                    color: accentPink
                    visible: text !== ""
                }
            }
        }

        Label {
            text: "Supported formats: .nid (Nanosurf), .txt (NeaSpec), .I(V)_mtrx .Z_flat (Omicron Matrix)"
            font.pixelSize: 10
            color: textMuted
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
    }

    // File dialog for selecting multiple files
    FileDialog {
        id: fileDialog
        title: "Select Measurement Files"
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            "All Measurement Files (*.nid *.txt *.I(V)_mtrx *.Z_flat *.I_flat)",
            "Nanosurf Files (*.nid)",
            "NeaSpec Files (*.txt)",
            "Omicron Matrix STS (*.I(V)_mtrx)",
            "Omicron Matrix Images (*.Z_flat *.I_flat)",
            "All Files (*)"
        ]

        onAccepted: {
            dialog.selectedItems = []
            for (var i = 0; i < selectedFiles.length; i++) {
                var path = selectedFiles[i].toString().replace("file://", "")
                dialog.selectedItems.push(path)
            }
            updateSelectionInfo()
        }
    }

    // Folder dialog for selecting entire directory
    FolderDialog {
        id: folderDialog
        title: "Select Folder Containing Measurements"

        onAccepted: {
            var path = selectedFolder.toString().replace("file://", "")
            dialog.selectedItems = [path]
            updateSelectionInfo()
        }
    }

    function updateSelectionInfo() {
        if (dialog.selectedItems.length === 0) {
            selectionInfo.text = "Nothing selected"
            selectionInfo.color = textMuted
            countLabel.text = ""
            return
        }

        if (dialog.isFolderMode) {
            selectionInfo.text = dialog.selectedItems[0]
            selectionInfo.color = textLight
            countLabel.text = "Folder: Will import all supported measurement files"
        } else {
            selectionInfo.text = dialog.selectedItems.join("\n")
            selectionInfo.color = textLight
            countLabel.text = "Selected " + dialog.selectedItems.length + " file(s)"
        }
    }

    onAccepted: {
        if (dialog.selectedItems.length === 0) {
            console.log("No items selected")
            return
        }

        if (backend) {
            if (dialog.isFolderMode) {
                backend.importFromFolder(dialog.selectedItems[0])
            } else {
                backend.importFromFiles(dialog.selectedItems)
            }
        }
    }

    onOpened: {
        filesMode.checked = true
        dialog.isFolderMode = false
        dialog.selectedItems = []
        updateSelectionInfo()
    }
}
