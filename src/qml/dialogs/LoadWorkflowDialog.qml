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

Dialog {
    id: dialog

    title: "Load Workflow"
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    width: 500
    height: 500

    property string selectedWorkflow: ""
    property var selectedWorkflowPath: ""

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentGreen: "#66ff99"  // Keep status color
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
            text: "Select a workflow to load:"
            font.pixelSize: 13
            color: textLight
        }

        // Workflow list
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
                    id: workflowListView
                    model: ListModel { id: workflowModel }
                    spacing: 2

                    delegate: Rectangle {
                        width: workflowListView.width
                        height: 60
                        color: mouseArea.containsMouse ? accentBlue :
                               (model.name === dialog.selectedWorkflow ? bgLight : "transparent")
                        opacity: mouseArea.containsMouse ? 0.3 :
                                 (model.name === dialog.selectedWorkflow ? 0.5 : 1)
                        radius: 3

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 10

                            Rectangle {
                                width: 40
                                height: 40
                                radius: 5
                                color: accentBlue
                                opacity: 0.3

                                Text {
                                    anchors.centerIn: parent
                                    text: "WF"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: textLight
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: model.name
                                    font.pixelSize: 13
                                    font.bold: model.name === dialog.selectedWorkflow
                                    color: textLight
                                }

                                Text {
                                    text: model.description || "No description"
                                    font.pixelSize: 10
                                    color: textMuted
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "Modified: " + (model.modified || "Unknown")
                                    font.pixelSize: 9
                                    color: textMuted
                                }
                            }

                            Button {
                                text: "Delete"
                                font.pixelSize: 11
                                Layout.preferredHeight: 24
                                visible: model.name === dialog.selectedWorkflow

                                onClicked: {
                                    deleteConfirmDialog.workflowToDelete = model.name
                                    deleteConfirmDialog.workflowPath = model.path
                                    deleteConfirmDialog.open()
                                }

                                background: Rectangle {
                                    color: parent.pressed ? "#C00260" :
                                           (parent.hovered ? "#D60270" : bgLight)
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
                        }

                        MouseArea {
                            id: mouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                dialog.selectedWorkflow = model.name
                                dialog.selectedWorkflowPath = model.path
                            }
                            onDoubleClicked: {
                                dialog.selectedWorkflow = model.name
                                dialog.selectedWorkflowPath = model.path
                                dialog.accept()
                            }
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: workflowListView.count === 0
                text: "No saved workflows found\n\nCreate a new workflow from\nthe Workflows menu"
                font.pixelSize: 12
                color: textMuted
                horizontalAlignment: Text.AlignHCenter
            }
        }

        // Browse for file section
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: borderColor
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                text: "Or browse for a .flow file:"
                font.pixelSize: 12
                color: textMuted
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Browse..."
                font.pixelSize: 12

                onClicked: workflowFileDialog.open()

                contentItem: Text {
                    text: parent.text
                    font: parent.font
                    color: textLight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                background: Rectangle {
                    color: parent.hovered ? "#8B4F86" : bgDark
                    border.color: accentGreen
                    border.width: 2
                    radius: 4
                    implicitWidth: 100
                    implicitHeight: 30
                }
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

    // File dialog for browsing .flow files
    Platform.FileDialog {
        id: workflowFileDialog
        title: "Open Workflow File"
        nameFilters: ["Workflow Files (*.flow)", "All Files (*)"]
        fileMode: Platform.FileDialog.OpenFile

        // Default to project's workflows folder
        folder: {
            if (backend && backend.projectPath) {
                return "file://" + backend.projectPath + "/workflows"
            }
            return Platform.StandardPaths.writableLocation(Platform.StandardPaths.DocumentsLocation)
        }

        onAccepted: {
            var path = file.toString()
            // Remove file:// prefix
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            console.log("Loading workflow from file:", path)
            loadWorkflowFromFile(path)
        }
    }

    function loadWorkflowFromFile(filePath) {
        if (backend && backend.workflowManager) {
            var workflowId = backend.workflowManager.loadWorkflow(filePath)
            if (workflowId) {
                // Extract name from path
                var parts = filePath.split("/")
                var fileName = parts[parts.length - 1]
                var workflowName = fileName.replace(".flow", "")

                console.log("Workflow loaded with ID:", workflowId, "Name:", workflowName)
                openWorkflowFromId(workflowId, workflowName)
                dialog.close()
            } else {
                statusLabel.text = "Error loading workflow file"
            }
        }
    }

    onAccepted: {
        if (dialog.selectedWorkflow === "" || dialog.selectedWorkflowPath === "") {
            statusLabel.text = "Please select a workflow"
            return
        }

        if (backend && backend.workflowManager) {
            var workflowId = backend.workflowManager.loadWorkflow(dialog.selectedWorkflowPath)
            if (workflowId) {
                console.log("Workflow loaded with ID:", workflowId)
                // Open the workflow window
                openWorkflowFromId(workflowId, dialog.selectedWorkflow)
            } else {
                statusLabel.text = "Error loading workflow"
            }
        }
    }

    onOpened: {
        refreshWorkflowList()
        dialog.selectedWorkflow = ""
        dialog.selectedWorkflowPath = ""
        statusLabel.text = ""
    }

    function refreshWorkflowList() {
        workflowModel.clear()

        if (backend && backend.workflowManager) {
            var workflows = backend.workflowManager.getSavedWorkflows()
            for (var i = 0; i < workflows.length; i++) {
                workflowModel.append({
                    name: workflows[i].name,
                    path: workflows[i].path,
                    description: workflows[i].description,
                    modified: workflows[i].modified
                })
            }
        }
    }

    function openWorkflowFromId(workflowId, workflowName) {
        // Create workflow window component
        var component = Qt.createComponent("../workflow/WorkflowWindow.qml")
        if (component.status === Component.Ready) {
            var window = component.createObject(null, {
                workflowId: workflowId,
                workflowName: workflowName,
                workflowManager: backend.workflowManager
            })
            if (window) {
                window.refreshWorkflow()
                window.show()
            }
        } else {
            console.error("Error creating workflow window:", component.errorString())
        }
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteConfirmDialog

        property string workflowToDelete: ""
        property string workflowPath: ""

        title: "Delete Workflow"
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
            text: "Are you sure you want to delete:\n\n\"" + deleteConfirmDialog.workflowToDelete + "\"?"
            font.pixelSize: 13
            color: textLight
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        onAccepted: {
            // Delete the workflow file using backend
            if (backend && backend.workflowManager) {
                var success = backend.workflowManager.deleteWorkflow(workflowPath)
                if (success) {
                    statusLabel.text = "Workflow deleted"
                    dialog.selectedWorkflow = ""
                    dialog.selectedWorkflowPath = ""
                } else {
                    statusLabel.text = "Error deleting workflow"
                }
                refreshWorkflowList()
            }
        }
    }
}
