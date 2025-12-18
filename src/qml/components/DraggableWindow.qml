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

Window {
    id: draggableWindow

    // Properties
    property string windowTitle: "Tool Window"
    property alias contentItem: contentArea.children
    property var parentWindow: null
    property int minWidth: 400
    property int minHeight: 300
    property bool dockable: true
    property bool isDocked: false

    // Theme colors - find main window for reactive bindings
    property var mainWin: null

    function findMainWindow() {
        for (var i = 0; i < Qt.application.allWindows.length; i++) {
            var win = Qt.application.allWindows[i]
            if (win.objectName === "mainWindow") {
                mainWin = win
                break
            }
        }
    }

    Component.onCompleted: findMainWindow()

    // Theme colors - reactive bindings from mainWin (MainWindow)
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentMagenta: mainWin ? mainWin.accentMagenta : "#D60270"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color accentOrange: mainWin ? mainWin.accentOrange : "#FF9B55"
    property color textLight: mainWin ? mainWin.textLight : "#e8e8e8"
    property color textMuted: mainWin ? mainWin.textMuted : "#a0a0a0"
    property color borderColor: mainWin ? mainWin.borderColor : "#8B4F86"
    property color successColor: "#2ECC71"  // Emerald green for success states

    width: 600
    height: 500
    minimumWidth: minWidth
    minimumHeight: minHeight
    flags: Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
    title: windowTitle

    // Make window stay on top initially but allow bringing to front/back
    modality: Qt.NonModal

    // Window appearance
    color: bgDark

    // Title bar
    Rectangle {
        id: titleBar
        width: parent.width
        height: 35
        color: bgDarker
        z: 100

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: borderColor
        }

        MouseArea {
            id: dragArea
            anchors.fill: parent
            property point clickPos: Qt.point(0, 0)

            onPressed: {
                clickPos = Qt.point(mouse.x, mouse.y)
            }

            onPositionChanged: {
                if (pressed) {
                    var delta = Qt.point(mouse.x - clickPos.x, mouse.y - clickPos.y)
                    draggableWindow.x += delta.x
                    draggableWindow.y += delta.y
                }
            }

            onDoubleClicked: {
                if (draggableWindow.visibility === Window.Maximized) {
                    draggableWindow.showNormal()
                } else {
                    draggableWindow.showMaximized()
                }
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 5
            spacing: 10

            Text {
                text: windowTitle
                color: accentPink
                font.pixelSize: 14
                font.bold: true
                Layout.fillWidth: true
            }

            // Bring to front button
            Button {
                text: "▲"
                flat: true
                Layout.preferredWidth: 25
                Layout.preferredHeight: 25
                onClicked: {
                    draggableWindow.raise()
                    draggableWindow.requestActivate()
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? accentBlue : textMuted
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
                ToolTip.visible: hovered
                ToolTip.text: "Bring to front"
            }

            // Send to back button
            Button {
                text: "▼"
                flat: true
                Layout.preferredWidth: 25
                Layout.preferredHeight: 25
                onClicked: {
                    draggableWindow.lower()
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? accentBlue : textMuted
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
                ToolTip.visible: hovered
                ToolTip.text: "Send to back"
            }

            // Minimize button
            Button {
                text: "_"
                flat: true
                Layout.preferredWidth: 25
                Layout.preferredHeight: 25
                onClicked: draggableWindow.showMinimized()
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? accentBlue : textMuted
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
            }

            // Maximize/Restore button
            Button {
                text: draggableWindow.visibility === Window.Maximized ? "❐" : "□"
                flat: true
                Layout.preferredWidth: 25
                Layout.preferredHeight: 25
                onClicked: {
                    if (draggableWindow.visibility === Window.Maximized) {
                        draggableWindow.showNormal()
                    } else {
                        draggableWindow.showMaximized()
                    }
                }
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? accentBlue : textMuted
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
            }

            // Close button
            Button {
                text: "×"
                flat: true
                Layout.preferredWidth: 25
                Layout.preferredHeight: 25
                onClicked: draggableWindow.close()
                contentItem: Text {
                    text: parent.text
                    color: parent.hovered ? "#ff6b6b" : textMuted
                    font.pixelSize: 18
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
            }
        }
    }

    // Content area
    Rectangle {
        id: contentContainer
        anchors.top: titleBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 5
        color: bgMedium
        border.color: borderColor
        border.width: 1
        radius: 3

        Item {
            id: contentArea
            anchors.fill: parent
            anchors.margins: 10
        }
    }

    // Resize handle (bottom-right corner)
    Rectangle {
        width: 15
        height: 15
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        color: bgLight
        border.color: borderColor
        border.width: 1
        z: 101

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.SizeFDiagCursor
            property point clickPos: Qt.point(0, 0)

            onPressed: {
                clickPos = Qt.point(mouse.x, mouse.y)
            }

            onPositionChanged: {
                if (pressed) {
                    var delta = Qt.point(mouse.x - clickPos.x, mouse.y - clickPos.y)
                    var newWidth = Math.max(minWidth, draggableWindow.width + delta.x)
                    var newHeight = Math.max(minHeight, draggableWindow.height + delta.y)
                    draggableWindow.width = newWidth
                    draggableWindow.height = newHeight
                }
            }
        }
    }

    // Functions
    function bringToFront() {
        draggableWindow.raise()
        draggableWindow.requestActivate()
    }

    function sendToBack() {
        draggableWindow.lower()
    }

    function dock(target) {
        if (dockable) {
            isDocked = true
            // Docking logic would go here
        }
    }

    function undock() {
        if (isDocked) {
            isDocked = false
            // Undocking logic would go here
        }
    }
}
