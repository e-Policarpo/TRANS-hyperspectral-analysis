/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * FloatingEntity - Base component for draggable/resizable workspace entities
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: floatingEntity

    // Entity identification
    property string entityId: ""
    property string entityType: "generic"  // "graph", "table", "map", etc.
    property string entityTitle: "Entity"

    // Entity data (passed to content)
    property var entityData: ({})

    // Size constraints
    property real minWidth: 200
    property real minHeight: 150
    property real maxWidth: 2000
    property real maxHeight: 1500

    // State
    property bool isSelected: false
    property bool isMinimized: false
    property bool isDockable: true

    // Content component (set by parent or specialized entity)
    property Component contentComponent: null
    property alias contentLoader: contentLoader
    property alias contentItem: contentLoader.item

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    // Signals
    signal selected()
    signal closed()
    signal minimized()
    signal maximized()
    signal dockRequested(string position)
    signal moved(real newX, real newY)
    signal resized(real newWidth, real newHeight)

    // Appearance
    width: 400
    height: 300
    color: bgMedium
    border.color: isSelected ? accentPink : borderColor
    border.width: isSelected ? 2 : 1
    radius: 6
    clip: true

    // Shadow effect simulation
    Rectangle {
        anchors.fill: parent
        anchors.margins: -4
        z: -1
        color: "transparent"
        radius: parent.radius + 4
        border.color: Qt.rgba(0, 0, 0, 0.3)
        border.width: 4
        visible: !isMinimized
    }

    // Main layout
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Title bar
        Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: isSelected ? Qt.darker(accentPink, 1.5) : bgLight
            radius: floatingEntity.radius

            // Square off bottom corners
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: parent.radius
                color: parent.color
            }

            // Drag area
            MouseArea {
                id: titleDragArea
                anchors.fill: parent
                anchors.rightMargin: 90  // Leave space for buttons
                cursorShape: Qt.SizeAllCursor
                hoverEnabled: true

                property point startPos
                property point entityStartPos

                onPressed: function(mouse) {
                    startPos = Qt.point(mouse.x, mouse.y)
                    entityStartPos = Qt.point(floatingEntity.x, floatingEntity.y)
                    floatingEntity.selected()
                }

                onPositionChanged: function(mouse) {
                    if (pressed) {
                        var newX = entityStartPos.x + (mouse.x - startPos.x)
                        var newY = entityStartPos.y + (mouse.y - startPos.y)

                        // Constrain to parent bounds
                        if (floatingEntity.parent) {
                            newX = Math.max(0, Math.min(floatingEntity.parent.width - floatingEntity.width, newX))
                            newY = Math.max(0, Math.min(floatingEntity.parent.height - floatingEntity.height, newY))
                        }

                        floatingEntity.x = newX
                        floatingEntity.y = newY
                    }
                }

                onReleased: {
                    moved(floatingEntity.x, floatingEntity.y)
                }

                onDoubleClicked: {
                    if (isMinimized) {
                        isMinimized = false
                        maximized()
                    }
                }
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 4
                spacing: 4

                // Entity type icon
                Text {
                    text: getEntityIcon()
                    font.pixelSize: 12
                    color: textMuted
                }

                // Title
                Text {
                    Layout.fillWidth: true
                    text: entityTitle
                    font.pixelSize: 12
                    font.bold: true
                    color: isSelected ? textLight : textMuted
                    elide: Text.ElideRight
                }

                // Minimize button
                Rectangle {
                    width: 20
                    height: 20
                    radius: 3
                    color: minimizeArea.containsMouse ? Qt.rgba(1, 1, 1, 0.2) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: isMinimized ? "□" : "−"
                        font.pixelSize: 14
                        font.bold: true
                        color: minimizeArea.containsMouse ? textLight : textMuted
                    }

                    MouseArea {
                        id: minimizeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            isMinimized = !isMinimized
                            if (isMinimized) {
                                minimized()
                            } else {
                                maximized()
                            }
                        }
                    }
                }

                // Dock button (optional)
                Rectangle {
                    width: 20
                    height: 20
                    radius: 3
                    color: dockArea.containsMouse ? Qt.rgba(0.35, 0.81, 0.98, 0.3) : "transparent"
                    visible: isDockable

                    Text {
                        anchors.centerIn: parent
                        text: "◫"
                        font.pixelSize: 12
                        color: dockArea.containsMouse ? accentBlue : textMuted
                    }

                    MouseArea {
                        id: dockArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            dockMenu.popup()
                        }
                    }

                    Menu {
                        id: dockMenu
                        background: Rectangle {
                            color: bgMedium
                            border.color: borderColor
                            radius: 4
                        }

                        MenuItem {
                            text: "Dock Left"
                            onTriggered: dockRequested("left")
                        }
                        MenuItem {
                            text: "Dock Right"
                            onTriggered: dockRequested("right")
                        }
                        MenuItem {
                            text: "Dock Top"
                            onTriggered: dockRequested("top")
                        }
                        MenuItem {
                            text: "Dock Bottom"
                            onTriggered: dockRequested("bottom")
                        }
                    }
                }

                // Close button
                Rectangle {
                    width: 20
                    height: 20
                    radius: 3
                    color: closeArea.containsMouse ? Qt.rgba(1, 0.3, 0.3, 0.6) : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "×"
                        font.pixelSize: 16
                        font.bold: true
                        color: closeArea.containsMouse ? textLight : textMuted
                    }

                    MouseArea {
                        id: closeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: closed()
                    }
                }
            }
        }

        // Content area
        Item {
            id: contentArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !isMinimized
            clip: true

            Loader {
                id: contentLoader
                anchors.fill: parent
                anchors.margins: 4
                sourceComponent: contentComponent

                onLoaded: {
                    if (item) {
                        // Pass entity data to loaded content
                        if (item.hasOwnProperty("entityId")) {
                            item.entityId = entityId
                        }
                        if (item.hasOwnProperty("entityData")) {
                            item.entityData = entityData
                        }
                        if (item.hasOwnProperty("entityTitle")) {
                            item.entityTitle = entityTitle
                        }
                    }
                }
            }

            // Placeholder when no content
            Text {
                anchors.centerIn: parent
                visible: !contentLoader.item
                text: "No content loaded"
                font.pixelSize: 12
                color: textMuted
            }
        }

        // Minimized state - compact bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 4
            color: accentPink
            visible: isMinimized
            opacity: 0.5
        }
    }

    // Resize handles
    // Right edge
    MouseArea {
        id: rightResizeHandle
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: titleBar.height
        anchors.bottomMargin: 8
        width: 6
        cursorShape: Qt.SizeHorCursor
        visible: !isMinimized

        property real startX
        property real startWidth

        onPressed: function(mouse) {
            startX = mouse.x
            startWidth = floatingEntity.width
        }

        onPositionChanged: function(mouse) {
            if (pressed) {
                var newWidth = startWidth + (mouse.x - startX)
                newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth))
                floatingEntity.width = newWidth
            }
        }

        onReleased: resized(floatingEntity.width, floatingEntity.height)
    }

    // Bottom edge
    MouseArea {
        id: bottomResizeHandle
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        height: 6
        cursorShape: Qt.SizeVerCursor
        visible: !isMinimized

        property real startY
        property real startHeight

        onPressed: function(mouse) {
            startY = mouse.y
            startHeight = floatingEntity.height
        }

        onPositionChanged: function(mouse) {
            if (pressed) {
                var newHeight = startHeight + (mouse.y - startY)
                newHeight = Math.max(minHeight, Math.min(maxHeight, newHeight))
                floatingEntity.height = newHeight
            }
        }

        onReleased: resized(floatingEntity.width, floatingEntity.height)
    }

    // Bottom-right corner (diagonal resize)
    MouseArea {
        id: cornerResizeHandle
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 12
        height: 12
        cursorShape: Qt.SizeFDiagCursor
        visible: !isMinimized

        property point startPos
        property real startWidth
        property real startHeight

        onPressed: function(mouse) {
            startPos = Qt.point(mouse.x, mouse.y)
            startWidth = floatingEntity.width
            startHeight = floatingEntity.height
        }

        onPositionChanged: function(mouse) {
            if (pressed) {
                var newWidth = startWidth + (mouse.x - startPos.x)
                var newHeight = startHeight + (mouse.y - startPos.y)
                newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth))
                newHeight = Math.max(minHeight, Math.min(maxHeight, newHeight))
                floatingEntity.width = newWidth
                floatingEntity.height = newHeight
            }
        }

        onReleased: resized(floatingEntity.width, floatingEntity.height)

        // Visual indicator
        Rectangle {
            anchors.fill: parent
            color: "transparent"

            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = textMuted
                    ctx.lineWidth = 1

                    // Draw grip lines
                    for (var i = 0; i < 3; i++) {
                        var offset = 3 + i * 3
                        ctx.beginPath()
                        ctx.moveTo(width, offset)
                        ctx.lineTo(offset, height)
                        ctx.stroke()
                    }
                }
            }
        }
    }

    // Helper functions
    function getEntityIcon() {
        switch(entityType) {
            case "graph": return "📈"
            case "table": return "📊"
            case "map": return "🗺"
            case "image": return "🖼"
            default: return "📄"
        }
    }

    function bringToFront() {
        if (parent && parent.bringEntityToFront) {
            parent.bringEntityToFront(entityId)
        }
        selected()
    }

    function getState() {
        return {
            id: entityId,
            type: entityType,
            title: entityTitle,
            x: x,
            y: y,
            width: width,
            height: height,
            isMinimized: isMinimized,
            data: entityData
        }
    }

    function restoreState(state) {
        if (state.x !== undefined) x = state.x
        if (state.y !== undefined) y = state.y
        if (state.width !== undefined) width = state.width
        if (state.height !== undefined) height = state.height
        if (state.isMinimized !== undefined) isMinimized = state.isMinimized
        if (state.data !== undefined) entityData = state.data
    }

    // Click anywhere to select
    MouseArea {
        anchors.fill: parent
        z: -1
        onClicked: selected()
    }

    Component.onCompleted: {
        console.log("FloatingEntity created:", entityId, entityType)
    }
}
