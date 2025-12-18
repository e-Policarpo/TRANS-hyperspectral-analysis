/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * WorkspaceCanvas - Central canvas with configurable grid background
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: workspaceCanvas

    // Background style: "none", "dotted", "grid", "workflow"
    property string backgroundStyle: "dotted"

    // Grid properties
    property real gridSpacing: 20
    property real dotSize: 2
    property color gridColor: Qt.rgba(textMuted.r, textMuted.g, textMuted.b, 0.15)

    // Zoom and pan
    property real zoomLevel: 1.0
    property real minZoom: 0.25
    property real maxZoom: 4.0
    property real panX: 0
    property real panY: 0

    // Snap to grid
    property bool snapToGrid: false
    property real snapSize: gridSpacing

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Signals
    signal canvasClicked(real x, real y, int button)
    signal canvasDoubleClicked(real x, real y)
    signal entityDropped(var entityData, real x, real y)
    signal zoomChanged(real newZoom)
    signal panChanged(real newX, real newY)

    color: bgDark
    clip: true

    // Background pattern layer
    Item {
        id: backgroundLayer
        anchors.fill: parent

        // Dotted grid background (for STS/SNOM analysis)
        Canvas {
            id: dottedCanvas
            anchors.fill: parent
            visible: backgroundStyle === "dotted"

            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)

                ctx.fillStyle = gridColor

                var spacing = gridSpacing * zoomLevel
                var offsetX = panX % spacing
                var offsetY = panY % spacing

                for (var x = offsetX; x < width; x += spacing) {
                    for (var y = offsetY; y < height; y += spacing) {
                        ctx.beginPath()
                        ctx.arc(x, y, dotSize * 0.5, 0, Math.PI * 2)
                        ctx.fill()
                    }
                }
            }

            // Repaint when properties change
            Connections {
                target: workspaceCanvas
                function onZoomLevelChanged() { dottedCanvas.requestPaint() }
                function onPanXChanged() { dottedCanvas.requestPaint() }
                function onPanYChanged() { dottedCanvas.requestPaint() }
                function onWidthChanged() { dottedCanvas.requestPaint() }
                function onHeightChanged() { dottedCanvas.requestPaint() }
            }

            Component.onCompleted: requestPaint()
        }

        // Line grid background (for workflow editor)
        Canvas {
            id: gridCanvas
            anchors.fill: parent
            visible: backgroundStyle === "grid" || backgroundStyle === "workflow"

            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)

                ctx.strokeStyle = gridColor
                ctx.lineWidth = 1

                var spacing = gridSpacing * zoomLevel
                var offsetX = panX % spacing
                var offsetY = panY % spacing

                // Vertical lines
                ctx.beginPath()
                for (var x = offsetX; x < width; x += spacing) {
                    ctx.moveTo(x, 0)
                    ctx.lineTo(x, height)
                }

                // Horizontal lines
                for (var y = offsetY; y < height; y += spacing) {
                    ctx.moveTo(0, y)
                    ctx.lineTo(width, y)
                }
                ctx.stroke()

                // Major grid lines (every 5 cells)
                if (backgroundStyle === "workflow") {
                    ctx.strokeStyle = Qt.rgba(gridColor.r, gridColor.g, gridColor.b, 0.3)
                    ctx.lineWidth = 1.5

                    var majorSpacing = spacing * 5

                    ctx.beginPath()
                    for (x = offsetX; x < width; x += majorSpacing) {
                        ctx.moveTo(x, 0)
                        ctx.lineTo(x, height)
                    }
                    for (y = offsetY; y < height; y += majorSpacing) {
                        ctx.moveTo(0, y)
                        ctx.lineTo(width, y)
                    }
                    ctx.stroke()
                }
            }

            Connections {
                target: workspaceCanvas
                function onZoomLevelChanged() { gridCanvas.requestPaint() }
                function onPanXChanged() { gridCanvas.requestPaint() }
                function onPanYChanged() { gridCanvas.requestPaint() }
                function onWidthChanged() { gridCanvas.requestPaint() }
                function onHeightChanged() { gridCanvas.requestPaint() }
            }

            Component.onCompleted: requestPaint()
        }
    }

    // Content layer - entities go here via Loader or direct children
    Item {
        id: contentLayer
        anchors.fill: parent

        transform: [
            Scale {
                origin.x: workspaceCanvas.width / 2
                origin.y: workspaceCanvas.height / 2
                xScale: zoomLevel
                yScale: zoomLevel
            },
            Translate {
                x: panX
                y: panY
            }
        ]

        // Default content (placeholder)
        default property alias contentChildren: contentLayer.children
    }

    // Interaction layer
    MouseArea {
        id: interactionArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        hoverEnabled: true

        property bool isPanning: false
        property real lastX: 0
        property real lastY: 0

        onPressed: function(mouse) {
            if (mouse.button === Qt.MiddleButton || (mouse.button === Qt.LeftButton && mouse.modifiers & Qt.AltModifier)) {
                isPanning = true
                lastX = mouse.x
                lastY = mouse.y
                cursorShape = Qt.ClosedHandCursor
            }
        }

        onReleased: function(mouse) {
            if (isPanning) {
                isPanning = false
                cursorShape = Qt.ArrowCursor
            } else if (mouse.button === Qt.LeftButton) {
                var worldX = (mouse.x - panX) / zoomLevel
                var worldY = (mouse.y - panY) / zoomLevel
                canvasClicked(worldX, worldY, mouse.button)
            }
        }

        onPositionChanged: function(mouse) {
            if (isPanning) {
                var deltaX = mouse.x - lastX
                var deltaY = mouse.y - lastY
                panX += deltaX
                panY += deltaY
                lastX = mouse.x
                lastY = mouse.y
                panChanged(panX, panY)
            }
        }

        onDoubleClicked: function(mouse) {
            var worldX = (mouse.x - panX) / zoomLevel
            var worldY = (mouse.y - panY) / zoomLevel
            canvasDoubleClicked(worldX, worldY)
        }

        onWheel: function(wheel) {
            var zoomFactor = wheel.angleDelta.y > 0 ? 1.1 : 0.9
            var newZoom = zoomLevel * zoomFactor
            newZoom = Math.max(minZoom, Math.min(maxZoom, newZoom))

            if (newZoom !== zoomLevel) {
                // Zoom towards mouse position
                var mouseX = wheel.x
                var mouseY = wheel.y
                var worldX = (mouseX - panX) / zoomLevel
                var worldY = (mouseY - panY) / zoomLevel

                zoomLevel = newZoom

                // Adjust pan to keep mouse position stable
                panX = mouseX - worldX * zoomLevel
                panY = mouseY - worldY * zoomLevel

                zoomChanged(zoomLevel)
                panChanged(panX, panY)
            }
        }
    }

    // Drop area for entities
    DropArea {
        id: dropArea
        anchors.fill: parent

        onDropped: function(drop) {
            var worldX = (drop.x - panX) / zoomLevel
            var worldY = (drop.y - panY) / zoomLevel

            if (snapToGrid) {
                worldX = Math.round(worldX / snapSize) * snapSize
                worldY = Math.round(worldY / snapSize) * snapSize
            }

            entityDropped(drop.source, worldX, worldY)
        }
    }

    // Zoom indicator (bottom right)
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 8
        width: zoomLabel.implicitWidth + 16
        height: 24
        radius: 4
        color: Qt.rgba(bgMedium.r, bgMedium.g, bgMedium.b, 0.8)
        visible: zoomLevel !== 1.0

        Text {
            id: zoomLabel
            anchors.centerIn: parent
            text: Math.round(zoomLevel * 100) + "%"
            font.pixelSize: 11
            color: textMuted
        }
    }

    // Public functions
    function resetView() {
        zoomLevel = 1.0
        panX = 0
        panY = 0
        zoomChanged(1.0)
        panChanged(0, 0)
    }

    function zoomIn() {
        var newZoom = Math.min(maxZoom, zoomLevel * 1.25)
        zoomLevel = newZoom
        zoomChanged(newZoom)
    }

    function zoomOut() {
        var newZoom = Math.max(minZoom, zoomLevel / 1.25)
        zoomLevel = newZoom
        zoomChanged(newZoom)
    }

    function fitToContent(contentBounds) {
        // contentBounds: {x, y, width, height}
        if (!contentBounds || contentBounds.width <= 0 || contentBounds.height <= 0) {
            resetView()
            return
        }

        var padding = 50
        var scaleX = (width - padding * 2) / contentBounds.width
        var scaleY = (height - padding * 2) / contentBounds.height
        zoomLevel = Math.min(scaleX, scaleY, maxZoom)
        zoomLevel = Math.max(zoomLevel, minZoom)

        panX = width / 2 - (contentBounds.x + contentBounds.width / 2) * zoomLevel
        panY = height / 2 - (contentBounds.y + contentBounds.height / 2) * zoomLevel

        zoomChanged(zoomLevel)
        panChanged(panX, panY)
    }

    function screenToWorld(screenX, screenY) {
        return {
            x: (screenX - panX) / zoomLevel,
            y: (screenY - panY) / zoomLevel
        }
    }

    function worldToScreen(worldX, worldY) {
        return {
            x: worldX * zoomLevel + panX,
            y: worldY * zoomLevel + panY
        }
    }

    function snapPosition(x, y) {
        if (snapToGrid) {
            return {
                x: Math.round(x / snapSize) * snapSize,
                y: Math.round(y / snapSize) * snapSize
            }
        }
        return { x: x, y: y }
    }

    Component.onCompleted: {
        console.log("WorkspaceCanvas created with background:", backgroundStyle)
    }
}
