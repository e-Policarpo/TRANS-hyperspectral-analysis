/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

// QtQuick.Window is imported UNVERSIONED on purpose. `Window.palette` arrived
// in revision 6.0, and a pinned `import QtQuick.Window 2.15` hides it — with
// the pin in place the palette block below was not a silent no-op but a hard
// load error, "Cannot assign to non-existent property \"palette\"", which took
// this whole component (and tools/ToolWindow.qml with it) out of the build.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts 1.15
import QtQuick.Window

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

    // Theme colours, straight from the Theme singleton.
    //
    // This used to scan Qt.application.allWindows for objectName "mainWindow",
    // once, in Component.onCompleted. A scan that ran before the main window
    // existed — or on a build where it is not the one being searched — left
    // mainWin null with nothing to retry it, and all twelve colours (and the
    // palette below with them) sat on fallbacks from a scheme that no longer
    // exists for the rest of the session. A singleton has no window to find.
    property color bgDark: Theme.bgDark
    property color bgDarker: Theme.bgDarker
    property color bgMedium: Theme.bgMedium
    property color bgLight: Theme.bgLight
    property color accentPink: Theme.accentPink
    property color accentBlue: Theme.accentBlue
    property color accentMagenta: Theme.accentMagenta
    property color accentPurple: Theme.accentPurple
    property color accentOrange: Theme.accentOrange
    property color textLight: Theme.textLight
    property color textMuted: Theme.textMuted
    property color borderColor: Theme.borderColor
    // The schemes have always carried a `success` key; this was an emerald
    // literal that no scheme could move.
    property color successColor: Theme.successColor

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

    // A tool window is its own top-level Window, so it does NOT inherit the
    // application window's palette. Without this, its unstyled controls
    // (TextField, ComboBox, GroupBox titles …) follow the system appearance —
    // black text fields inside a light TRANS theme. Mirrors Main.qml.
    palette.window: bgDark
    palette.windowText: textLight
    palette.base: bgDarker
    palette.alternateBase: bgMedium
    palette.text: textLight
    palette.button: bgLight
    palette.buttonText: textLight
    palette.highlight: accentPink
    palette.highlightedText: bgDark
    palette.placeholderText: textMuted
    palette.mid: borderColor
    palette.dark: bgDarker
    palette.light: bgLight
    palette.toolTipBase: bgMedium
    palette.toolTipText: textLight

    // Edge outline. In dark schemes the window fill is close to the canvas
    // behind it, so without this the tool has no visible boundary.
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: borderColor
        border.width: 1
        radius: 0
        z: 200
        // Chrome only — must never swallow clicks meant for the content.
        enabled: false
    }

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
