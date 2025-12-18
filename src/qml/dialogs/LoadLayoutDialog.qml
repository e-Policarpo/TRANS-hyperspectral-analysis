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

Dialog {
    id: dialog

    title: "Load Layout"
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    width: 450
    height: 400

    property string selectedPreset: ""

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
            text: "Select a layout to load:"
            font.pixelSize: 13
            color: textLight
        }

        // Preset list
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            border.color: borderColor
            border.width: 1
            radius: 3

            ScrollView {
                anchors.fill: parent
                anchors.margins: 2
                clip: true

                ListView {
                    id: presetListView
                    model: ListModel { id: presetModel }
                    spacing: 2

                    delegate: Rectangle {
                        width: presetListView.width
                        height: 40
                        color: mouseArea.containsMouse ? accentPink : (model.name === dialog.selectedPreset ? bgLight : "transparent")
                        opacity: mouseArea.containsMouse ? 0.3 : (model.name === dialog.selectedPreset ? 0.5 : 1)
                        radius: 3

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 10

                            Text {
                                text: "📁"
                                font.pixelSize: 16
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: model.name
                                    font.pixelSize: 13
                                    font.bold: model.name === dialog.selectedPreset
                                    color: textLight
                                }

                                Text {
                                    text: model.path || ""
                                    font.pixelSize: 10
                                    color: textMuted
                                    elide: Text.ElideMiddle
                                    Layout.fillWidth: true
                                }
                            }

                            Button {
                                text: "Set as Default"
                                font.pixelSize: 11
                                Layout.preferredHeight: 24
                                visible: model.name === dialog.selectedPreset

                                onClicked: {
                                    if (backend && backend.dockManager) {
                                        backend.dockManager.setAsDefaultLayout(model.name)
                                        statusLabel.text = "Set as default: " + model.name
                                    }
                                }

                                background: Rectangle {
                                    color: parent.pressed ? accentPink : (parent.hovered ? bgDark : bgLight)
                                    border.color: borderColor
                                    border.width: 1
                                    radius: 3
                                }

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    color: textLight
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }

                            Button {
                                text: "🗑"
                                font.pixelSize: 14
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 24
                                visible: model.name === dialog.selectedPreset

                                onClicked: {
                                    deleteConfirmDialog.presetToDelete = model.name
                                    deleteConfirmDialog.open()
                                }

                                background: Rectangle {
                                    color: parent.pressed ? "#C00260" : (parent.hovered ? "#D60270" : bgLight)
                                    opacity: parent.hovered ? 0.8 : 1
                                    border.color: borderColor
                                    border.width: 1
                                    radius: 3
                                }

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        MouseArea {
                            id: mouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                dialog.selectedPreset = model.name
                            }
                            onDoubleClicked: {
                                dialog.selectedPreset = model.name
                                dialog.accept()
                            }
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: presetListView.count === 0
                text: "No saved layouts found\n\nUse 'Save Layout' to create one"
                font.pixelSize: 12
                color: textMuted
                horizontalAlignment: Text.AlignHCenter
            }
        }

        Label {
            id: statusLabel
            text: ""
            font.pixelSize: 11
            color: accentPink
            visible: text !== ""
            Layout.fillWidth: true
        }

        Label {
            text: "Double-click to load, or select and click OK"
            font.pixelSize: 10
            color: textMuted
            Layout.fillWidth: true
        }
    }

    onAccepted: {
        if (dialog.selectedPreset === "") {
            statusLabel.text = "Please select a layout"
            return
        }

        if (backend && backend.dockManager) {
            var result = backend.dockManager.loadLayout(dialog.selectedPreset)
            if (result.success) {
                console.log("Layout loaded:", result.message)
                statusLabel.text = ""
            } else {
                statusLabel.text = "Error: " + result.message
            }
        }
    }

    onOpened: {
        refreshPresetList()
        dialog.selectedPreset = ""
        statusLabel.text = ""
    }

    function refreshPresetList() {
        presetModel.clear()

        if (backend && backend.dockManager) {
            var presets = backend.dockManager.getAvailablePresets()
            for (var i = 0; i < presets.length; i++) {
                presetModel.append({
                    name: presets[i],
                    path: "~/.trans_qml/layouts/" + presets[i] + ".json"
                })
            }
        }
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteConfirmDialog

        property string presetToDelete: ""

        title: "Delete Layout"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No

        width: 350
        height: 150

        background: Rectangle {
            color: bgLight
            border.color: borderColor
            border.width: 1
        }

        Label {
            anchors.fill: parent
            text: "Are you sure you want to delete the layout:\n\n\"" + deleteConfirmDialog.presetToDelete + "\"?"
            font.pixelSize: 13
            color: textLight
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        onAccepted: {
            if (backend && backend.dockManager) {
                var success = backend.dockManager.deletePreset(deleteConfirmDialog.presetToDelete)
                if (success) {
                    statusLabel.text = "Deleted: " + deleteConfirmDialog.presetToDelete
                    dialog.selectedPreset = ""
                    refreshPresetList()
                } else {
                    statusLabel.text = "Failed to delete preset"
                }
            }
        }
    }
}
