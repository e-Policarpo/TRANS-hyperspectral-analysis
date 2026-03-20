/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * EmbeddedWindow - Base component for embedded workspace windows
 * Supports fullscreen, windowed, and minimized modes like OS windows
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: embeddedWindow

    // Window identification
    property string windowId: ""
    property string windowTitle: "Window"
    property string windowType: "generic"  // "tool", "graph", "table", "image"

    // Window state
    enum WindowState {
        Windowed,
        Fullscreen,
        Minimized
    }
    property int windowState: EmbeddedWindow.WindowState.Windowed

    // Store previous state for restore
    property real previousX: 50
    property real previousY: 50
    property real previousWidth: 500
    property real previousHeight: 400

    // Size constraints
    property real minWidth: 300
    property real minHeight: 200
    property real maxWidth: 9999
    property real maxHeight: 9999

    // Viewport size (set by WindowManager for proper fullscreen in scrollable workspace)
    property real viewportWidth: parent ? parent.width : 800
    property real viewportHeight: parent ? parent.height : 600
    property real viewportX: 0  // Scroll offset for fullscreen positioning
    property real viewportY: 0

    // Minimized bar dimensions (just title bar height, width stays same)
    property real minimizedHeight: 36

    // Content
    property Component contentComponent: null
    property alias contentItem: contentLoader.item

    // Backend reference for tool content
    property var backend: null

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Z-order management
    property int baseZ: 100
    property bool isActive: false

    // Signals
    signal closed()
    signal activated()
    signal stateChanged(int newState)
    signal windowMoved()
    signal windowResized()

    // Computed properties based on state
    // When minimized, keep same width and position but collapse to title bar
    width: {
        switch(windowState) {
            case EmbeddedWindow.WindowState.Fullscreen:
                return viewportWidth
            case EmbeddedWindow.WindowState.Minimized:
                return previousWidth  // Keep same width when minimized
            default:
                return previousWidth
        }
    }

    height: {
        switch(windowState) {
            case EmbeddedWindow.WindowState.Fullscreen:
                return viewportHeight
            case EmbeddedWindow.WindowState.Minimized:
                return minimizedHeight  // Collapse to title bar only
            default:
                return previousHeight
        }
    }

    x: windowState === EmbeddedWindow.WindowState.Fullscreen ? viewportX : previousX
    y: windowState === EmbeddedWindow.WindowState.Fullscreen ? viewportY : previousY

    z: isActive ? baseZ + 1000 : baseZ

    // State change handlers
    onWindowStateChanged: {
        stateChanged(windowState)
    }

    // Window functions
    function minimize() {
        if (windowState === EmbeddedWindow.WindowState.Windowed) {
            previousX = x
            previousY = y
            previousWidth = width
            previousHeight = height
        }
        windowState = EmbeddedWindow.WindowState.Minimized
    }

    function maximize() {
        if (windowState === EmbeddedWindow.WindowState.Windowed) {
            previousX = x
            previousY = y
            previousWidth = width
            previousHeight = height
        }
        windowState = EmbeddedWindow.WindowState.Fullscreen
    }

    function restore() {
        windowState = EmbeddedWindow.WindowState.Windowed
    }

    function toggleMaximize() {
        if (windowState === EmbeddedWindow.WindowState.Fullscreen) {
            restore()
        } else {
            maximize()
        }
    }

    function close() {
        closed()
    }

    function bringToFront() {
        isActive = true
        activated()
    }

    // Main window rectangle
    Rectangle {
        id: windowFrame
        anchors.fill: parent
        color: bgMedium
        border.color: isActive ? accentPink : borderColor
        border.width: isActive ? 2 : 1
        radius: windowState === EmbeddedWindow.WindowState.Fullscreen ? 0 : 6
        clip: true

        // Shadow (only in windowed mode)
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            z: -1
            color: "transparent"
            radius: parent.radius + 4
            border.color: Qt.rgba(0, 0, 0, 0.3)
            border.width: 4
            visible: windowState === EmbeddedWindow.WindowState.Windowed
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Title bar
            Rectangle {
                id: titleBar
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                color: isActive ? Qt.darker(accentPink, 1.3) : bgLight
                radius: windowFrame.radius
                z: 10  // Ensure title bar is above content

                // Square off bottom corners
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: parent.radius
                    color: parent.color
                }

                // Window controls - positioned absolutely on right for reliable click handling
                Row {
                    id: windowControlsRow
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.rightMargin: 4
                    anchors.topMargin: 4
                    anchors.bottomMargin: 4
                    spacing: 2
                    z: 100  // Always on top

                    // Minimize button
                    Rectangle {
                        width: 28
                        height: parent.height
                        radius: 3
                        color: minimizeArea.containsMouse ? Qt.rgba(255, 255, 255, 0.2) : Qt.rgba(0, 0, 0, 0.15)

                        Text {
                            anchors.centerIn: parent
                            text: windowState === EmbeddedWindow.WindowState.Minimized ? "▢" : "−"
                            color: "#FFFFFF"
                            font.pixelSize: 14
                            font.bold: true
                        }

                        MouseArea {
                            id: minimizeArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (windowState === EmbeddedWindow.WindowState.Minimized) {
                                    embeddedWindow.restore()
                                } else {
                                    embeddedWindow.minimize()
                                }
                            }
                        }
                    }

                    // Maximize/Restore button
                    Rectangle {
                        width: 28
                        height: parent.height
                        radius: 3
                        color: maximizeArea.containsMouse ? Qt.rgba(255, 255, 255, 0.2) : Qt.rgba(0, 0, 0, 0.15)

                        Text {
                            anchors.centerIn: parent
                            text: windowState === EmbeddedWindow.WindowState.Fullscreen ? "❐" : "□"
                            color: "#FFFFFF"
                            font.pixelSize: 12
                        }

                        MouseArea {
                            id: maximizeArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: embeddedWindow.toggleMaximize()
                        }
                    }

                    // Close button
                    Rectangle {
                        width: 28
                        height: parent.height
                        radius: 3
                        color: closeArea.containsMouse ? "#E81123" : Qt.rgba(0, 0, 0, 0.15)

                        Text {
                            anchors.centerIn: parent
                            text: "✕"
                            color: "#FFFFFF"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        MouseArea {
                            id: closeArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: embeddedWindow.close()
                        }
                    }
                }

                // Title and icon row
                Row {
                    anchors.left: parent.left
                    anchors.right: windowControlsRow.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    spacing: 8

                    // Window icon
                    Rectangle {
                        width: 16
                        height: 16
                        radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: {
                            switch(windowType) {
                                case "tool": return accentBlue
                                case "graph": return "#2ECC71"
                                case "table": return "#FF9800"
                                case "image": return "#9B4F96"
                                default: return textMuted
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            text: {
                                switch(windowType) {
                                    case "tool": return "T"
                                    case "graph": return "G"
                                    case "table": return "T"
                                    case "image": return "I"
                                    default: return "W"
                                }
                            }
                            color: bgDark
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }

                    // Title
                    Text {
                        text: windowTitle
                        color: isActive ? bgDarker : textLight
                        font.pixelSize: 12
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width - 30
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                // Drag area - behind everything
                MouseArea {
                    id: titleDragArea
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: windowControlsRow.left
                    z: -1  // Behind buttons
                    cursorShape: windowState !== EmbeddedWindow.WindowState.Fullscreen ? Qt.SizeAllCursor : Qt.ArrowCursor
                    enabled: windowState !== EmbeddedWindow.WindowState.Fullscreen
                    hoverEnabled: true

                    property real pressedWindowX: 0
                    property real pressedWindowY: 0
                    property real pressedMouseX: 0
                    property real pressedMouseY: 0

                    onPressed: function(mouse) {
                        pressedWindowX = embeddedWindow.x
                        pressedWindowY = embeddedWindow.y
                        var globalPos = mapToItem(embeddedWindow.parent, mouse.x, mouse.y)
                        pressedMouseX = globalPos.x
                        pressedMouseY = globalPos.y
                        embeddedWindow.bringToFront()
                    }

                    onPositionChanged: function(mouse) {
                        if (pressed) {
                            var globalPos = mapToItem(embeddedWindow.parent, mouse.x, mouse.y)
                            var deltaX = globalPos.x - pressedMouseX
                            var deltaY = globalPos.y - pressedMouseY
                            var newX = pressedWindowX + deltaX
                            var newY = pressedWindowY + deltaY

                            // Constrain to parent bounds (like workflow nodes)
                            newX = Math.max(0, newX)
                            newY = Math.max(0, newY)

                            embeddedWindow.previousX = newX
                            embeddedWindow.previousY = newY
                        }
                    }

                    onReleased: {
                        embeddedWindow.windowMoved()
                    }

                    onDoubleClicked: {
                        if (windowState !== EmbeddedWindow.WindowState.Minimized) {
                            toggleMaximize()
                        }
                    }
                }
            }

            // Content area with scrollbars (hidden when minimized)
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDark
                visible: windowState !== EmbeddedWindow.WindowState.Minimized

                Item {
                    anchors.fill: parent
                    anchors.margins: 1
                    clip: true

                    Loader {
                        id: contentLoader
                        anchors.fill: parent
                        sourceComponent: contentComponent

                        // Pass backend and theme to loaded content
                        onLoaded: {
                            if (item) {
                                // Pass backend if the item expects it
                                if (item.hasOwnProperty("backend") && embeddedWindow.backend) {
                                    item.backend = embeddedWindow.backend
                                }
                                // Pass close function so embedded tools can close their window
                                if (item.hasOwnProperty("closeWindow")) {
                                    item.closeWindow = function() { embeddedWindow.close() }
                                }
                                // Pass theme colors if the item expects them
                                if (item.hasOwnProperty("bgDark")) item.bgDark = embeddedWindow.bgDark
                                if (item.hasOwnProperty("bgMedium")) item.bgMedium = embeddedWindow.bgMedium
                                if (item.hasOwnProperty("bgLight")) item.bgLight = embeddedWindow.bgLight
                                if (item.hasOwnProperty("textLight")) item.textLight = embeddedWindow.textLight
                                if (item.hasOwnProperty("textMuted")) item.textMuted = embeddedWindow.textMuted
                                if (item.hasOwnProperty("accentPink")) item.accentPink = embeddedWindow.accentPink
                                if (item.hasOwnProperty("accentBlue")) item.accentBlue = embeddedWindow.accentBlue
                                if (item.hasOwnProperty("accentPurple")) item.accentPurple = embeddedWindow.borderColor
                                if (item.hasOwnProperty("borderColor")) item.borderColor = embeddedWindow.borderColor
                            }
                        }
                    }
                }
            }
        }

        // Resize handles (only in windowed mode)
        // Right edge
        MouseArea {
            width: 6
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: titleBar.height
            anchors.bottomMargin: 6
            cursorShape: Qt.SizeHorCursor
            visible: windowState === EmbeddedWindow.WindowState.Windowed

            property real startX
            property real startWidth

            onPressed: function(mouse) {
                startX = mouse.x
                startWidth = embeddedWindow.previousWidth
                embeddedWindow.bringToFront()
            }

            onPositionChanged: function(mouse) {
                if (pressed) {
                    var newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + mouse.x - startX))
                    embeddedWindow.previousWidth = newWidth
                }
            }

            onReleased: embeddedWindow.windowResized()
        }

        // Bottom edge
        MouseArea {
            height: 6
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 6
            anchors.rightMargin: 6
            cursorShape: Qt.SizeVerCursor
            visible: windowState === EmbeddedWindow.WindowState.Windowed

            property real startY
            property real startHeight

            onPressed: function(mouse) {
                startY = mouse.y
                startHeight = embeddedWindow.previousHeight
                embeddedWindow.bringToFront()
            }

            onPositionChanged: function(mouse) {
                if (pressed) {
                    var newHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + mouse.y - startY))
                    embeddedWindow.previousHeight = newHeight
                }
            }

            onReleased: embeddedWindow.windowResized()
        }

        // Bottom-right corner
        MouseArea {
            width: 12
            height: 12
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            cursorShape: Qt.SizeFDiagCursor
            visible: windowState === EmbeddedWindow.WindowState.Windowed

            property point startPos
            property real startWidth
            property real startHeight

            onPressed: function(mouse) {
                startPos = Qt.point(mouse.x, mouse.y)
                startWidth = embeddedWindow.previousWidth
                startHeight = embeddedWindow.previousHeight
                embeddedWindow.bringToFront()
            }

            onPositionChanged: function(mouse) {
                if (pressed) {
                    var newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + mouse.x - startPos.x))
                    var newHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + mouse.y - startPos.y))
                    embeddedWindow.previousWidth = newWidth
                    embeddedWindow.previousHeight = newHeight
                }
            }

            onReleased: embeddedWindow.windowResized()

            // Resize grip visual
            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.strokeStyle = textMuted
                    ctx.lineWidth = 1
                    ctx.beginPath()
                    ctx.moveTo(width, 4)
                    ctx.lineTo(4, height)
                    ctx.stroke()
                    ctx.beginPath()
                    ctx.moveTo(width, 8)
                    ctx.lineTo(8, height)
                    ctx.stroke()
                }
            }
        }
    }

    // Click anywhere to bring to front
    MouseArea {
        anchors.fill: parent
        z: -1
        onPressed: function(mouse) {
            embeddedWindow.bringToFront()
            mouse.accepted = false
        }
    }

    Component.onCompleted: {
        previousWidth = width
        previousHeight = height
        previousX = x
        previousY = y
    }
}
