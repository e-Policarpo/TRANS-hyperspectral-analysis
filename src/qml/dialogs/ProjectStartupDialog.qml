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
import Qt.labs.platform 1.1 as Platform
import "../components"   // the Theme singleton

Dialog {
    id: dialog

    title: "TRANS-QML - Project Setup"
    modal: true
    closePolicy: Popup.NoAutoClose  // User must choose an option

    width: 550
    height: 500

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    // "It worked" — semantic, so it stays green, but from the scheme's
    // `success` key rather than a fixed one.
    property color accentGreen: (mainWin && mainWin.successColor !== undefined) ? mainWin.successColor : Theme.successColor
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    signal projectCreated(string projectPath, string projectName)
    signal projectOpened(string projectPath, string projectName)
    signal dialogCancelled()

    background: Rectangle {
        color: bgMedium
        border.color: accentPink
        border.width: 2
        radius: 10
    }

    header: Rectangle {
        height: 60
        color: bgDark
        radius: 10

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 10
            color: bgDark
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 15

            Text {
                text: "TRANS-QML"
                font.pixelSize: 24
                font.bold: true
                color: accentPink
            }

            Text {
                text: "Spectral Analysis Suite"
                font.pixelSize: 14
                color: textMuted
                Layout.alignment: Qt.AlignBottom
            }

            Item { Layout.fillWidth: true }
        }
    }

    contentItem: ColumnLayout {
        spacing: 20

        // Welcome message
        Text {
            text: "Welcome! Please create a new project or open an existing one."
            font.pixelSize: 13
            color: textLight
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        // New Project Section
        GroupBox {
            title: "Create New Project"
            Layout.fillWidth: true

            background: Rectangle {
                color: bgDark
                border.color: borderColor
                radius: 5
                y: parent.topPadding - parent.padding
                width: parent.width
                height: parent.height - parent.topPadding + parent.padding
            }

            label: Text {
                text: parent.title
                color: accentGreen
                font.pixelSize: 13
                font.bold: true
                leftPadding: 10
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "Project Name:"
                        color: textLight
                        font.pixelSize: 12
                    }

                    TextField {
                        id: projectNameField
                        Layout.fillWidth: true
                        placeholderText: "Enter project name..."
                        color: textLight
                        font.pixelSize: 12

                        background: Rectangle {
                            color: bgMedium
                            border.color: projectNameField.activeFocus ? accentBlue : borderColor
                            radius: 3
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "Location:"
                        color: textLight
                        font.pixelSize: 12
                    }

                    TextField {
                        id: projectLocationField
                        Layout.fillWidth: true
                        text: backend ? backend.getDefaultProjectsPath() : ""
                        color: textLight
                        font.pixelSize: 11
                        readOnly: true

                        background: Rectangle {
                            color: bgLight
                            border.color: borderColor
                            radius: 3
                        }
                    }

                    Button {
                        text: "Browse..."
                        onClicked: folderDialog.open()

                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                        }

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: borderColor
                            radius: 3
                        }
                    }
                }

                Button {
                    text: "Create Project"
                    Layout.alignment: Qt.AlignRight
                    enabled: projectNameField.text.trim() !== "" && projectLocationField.text !== ""

                    onClicked: {
                        var projectPath = projectLocationField.text + "/" + projectNameField.text.trim()
                        projectCreated(projectPath, projectNameField.text.trim())
                        dialog.close()
                    }

                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? bgDark : textMuted
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }

                    background: Rectangle {
                        color: parent.enabled ? (parent.hovered ? Qt.lighter(accentGreen, 1.2) : accentGreen) : bgLight
                        radius: 5
                    }
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: borderColor
        }

        // Open Existing Project Section
        GroupBox {
            title: "Open Existing Project"
            Layout.fillWidth: true
            Layout.fillHeight: true

            background: Rectangle {
                color: bgDark
                border.color: borderColor
                radius: 5
                y: parent.topPadding - parent.padding
                width: parent.width
                height: parent.height - parent.topPadding + parent.padding
            }

            label: Text {
                text: parent.title
                color: accentBlue
                font.pixelSize: 13
                font.bold: true
                leftPadding: 10
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                Text {
                    text: "Recent Projects:"
                    color: textMuted
                    font.pixelSize: 11
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: recentProjectsList
                        model: ListModel { id: recentProjectsModel }
                        spacing: 5

                        delegate: Rectangle {
                            width: recentProjectsList.width
                            height: 50
                            color: mouseArea.containsMouse ? bgLight : "transparent"
                            radius: 5

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 10

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        text: model.name
                                        color: textLight
                                        font.pixelSize: 12
                                        font.bold: true
                                    }

                                    Text {
                                        text: model.path
                                        color: textMuted
                                        font.pixelSize: 10
                                        elide: Text.ElideMiddle
                                        Layout.fillWidth: true
                                    }
                                }

                                Text {
                                    text: model.lastOpened || ""
                                    color: textMuted
                                    font.pixelSize: 10
                                }
                            }

                            MouseArea {
                                id: mouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    projectOpened(model.path, model.name)
                                    dialog.close()
                                }
                                onDoubleClicked: {
                                    projectOpened(model.path, model.name)
                                    dialog.close()
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: recentProjectsList.count === 0
                            text: "No recent projects"
                            color: textMuted
                            font.italic: true
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Button {
                        text: "Open .hrt File..."
                        onClicked: projectFileDialog.open()

                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                        }

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: accentGreen
                            border.width: 2
                            radius: 3
                        }
                    }

                    Button {
                        text: "Browse Folder..."
                        onClicked: projectFolderDialog.open()

                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                        }

                        background: Rectangle {
                            color: parent.hovered ? bgLight : bgMedium
                            border.color: accentBlue
                            radius: 3
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }
        }
    }

    footer: Rectangle {
        height: 50
        color: bgDark
        radius: 10

        Rectangle {
            anchors.top: parent.top
            width: parent.width
            height: 10
            color: bgDark
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 10

            Text {
                text: "Projects keep your analysis outputs organized"
                color: textMuted
                font.pixelSize: 10
                font.italic: true
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Quit"
                onClicked: {
                    dialogCancelled()
                    Qt.quit()
                }

                contentItem: Text {
                    text: parent.text
                    color: textMuted
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignHCenter
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 3
                }
            }
        }
    }

    // Folder dialog for new project location
    FolderDialog {
        id: folderDialog
        title: "Select Project Location"
        currentFolder: projectLocationField.text !== "" ?
                       "file://" + projectLocationField.text : ""

        onAccepted: {
            var path = selectedFolder.toString()
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            path = decodeURIComponent(path)
            projectLocationField.text = path
        }
    }

    // Folder dialog for opening existing project
    FolderDialog {
        id: projectFolderDialog
        title: "Open Project Folder"

        onAccepted: {
            var path = selectedFolder.toString()
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            path = decodeURIComponent(path)
            // Extract project name from path
            var parts = path.split("/")
            var name = parts[parts.length - 1]
            projectOpened(path, name)
            dialog.close()
        }
    }

    // File dialog for opening .hrt project files
    Platform.FileDialog {
        id: projectFileDialog
        title: "Open Project File"
        nameFilters: ["TRANS-QML Project (*.hrt)", "All Files (*)"]
        fileMode: Platform.FileDialog.OpenFile

        onAccepted: {
            var path = file.toString()
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            // Decode URL-encoded characters (e.g., %20 for spaces)
            path = decodeURIComponent(path)
            console.log("Opening .hrt project file:", path)

            if (backend) {
                backend.openProjectFile(path)
            }
            dialog.close()
        }
    }

    Component.onCompleted: {
        loadRecentProjects()
    }

    function loadRecentProjects() {
        recentProjectsModel.clear()

        if (backend) {
            var recent = backend.getRecentProjects()
            for (var i = 0; i < recent.length; i++) {
                recentProjectsModel.append({
                    name: recent[i].name,
                    path: recent[i].path,
                    lastOpened: recent[i].lastOpened || ""
                })
            }
        }
    }
}
