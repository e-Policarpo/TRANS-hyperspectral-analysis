/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * GraphEntity - Floating entity for displaying graphs/plots
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FloatingEntity {
    id: graphEntity

    entityType: "graph"
    entityTitle: "Graph"
    minWidth: 300
    minHeight: 200

    // Graph data
    property var curves: []  // Array of {x: [], y: [], label: "", color: ""}
    property string xLabel: "X"
    property string yLabel: "Y"
    property string graphTitle: ""

    // Auto-scaling bounds
    property real xMin: 0
    property real xMax: 1
    property real yMin: 0
    property real yMax: 1
    property bool autoScale: true

    // Display options
    property bool showGrid: true
    property bool showLegend: true
    property bool showAxis: true
    property real lineWidth: 2

    // Color palette for curves
    readonly property var colorPalette: [
        "#F5A9B8", "#5BCEFA", "#66ff66", "#FFD700", "#FF6B6B",
        "#9B4F96", "#00BCD4", "#FF9800", "#E91E63", "#2ECC71"
    ]

    // Content component - the actual graph
    contentComponent: Component {
        Item {
            id: graphContent

            // Graph canvas
            Canvas {
                id: graphCanvas
                anchors.fill: parent
                anchors.margins: 40  // Space for axis labels

                property real plotWidth: width
                property real plotHeight: height

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)

                    if (curves.length === 0) {
                        drawPlaceholder(ctx)
                        return
                    }

                    // Calculate bounds if auto-scaling
                    if (autoScale) {
                        calculateBounds()
                    }

                    // Draw grid
                    if (showGrid) {
                        drawGrid(ctx)
                    }

                    // Draw curves
                    for (var i = 0; i < curves.length; i++) {
                        drawCurve(ctx, curves[i], i)
                    }
                }

                function drawPlaceholder(ctx) {
                    ctx.fillStyle = textMuted
                    ctx.font = "14px sans-serif"
                    ctx.textAlign = "center"
                    ctx.fillText("No data loaded", width / 2, height / 2)
                    ctx.font = "11px sans-serif"
                    ctx.fillText("Add curves to display", width / 2, height / 2 + 20)
                }

                function drawGrid(ctx) {
                    ctx.strokeStyle = Qt.rgba(textMuted.r, textMuted.g, textMuted.b, 0.2)
                    ctx.lineWidth = 1

                    var gridLines = 5

                    // Vertical grid lines
                    for (var i = 0; i <= gridLines; i++) {
                        var x = (plotWidth / gridLines) * i
                        ctx.beginPath()
                        ctx.moveTo(x, 0)
                        ctx.lineTo(x, plotHeight)
                        ctx.stroke()
                    }

                    // Horizontal grid lines
                    for (i = 0; i <= gridLines; i++) {
                        var y = (plotHeight / gridLines) * i
                        ctx.beginPath()
                        ctx.moveTo(0, y)
                        ctx.lineTo(plotWidth, y)
                        ctx.stroke()
                    }
                }

                function drawCurve(ctx, curve, index) {
                    if (!curve.x || !curve.y || curve.x.length === 0) return

                    var color = curve.color || colorPalette[index % colorPalette.length]
                    ctx.strokeStyle = color
                    ctx.lineWidth = lineWidth
                    ctx.lineCap = "round"
                    ctx.lineJoin = "round"

                    ctx.beginPath()
                    var firstPoint = true

                    for (var i = 0; i < curve.x.length; i++) {
                        var px = mapX(curve.x[i])
                        var py = mapY(curve.y[i])

                        if (firstPoint) {
                            ctx.moveTo(px, py)
                            firstPoint = false
                        } else {
                            ctx.lineTo(px, py)
                        }
                    }

                    ctx.stroke()
                }

                function mapX(value) {
                    var range = xMax - xMin
                    if (range === 0) range = 1
                    return ((value - xMin) / range) * plotWidth
                }

                function mapY(value) {
                    var range = yMax - yMin
                    if (range === 0) range = 1
                    // Invert Y (canvas Y increases downward)
                    return plotHeight - ((value - yMin) / range) * plotHeight
                }
            }

            // X-axis label
            Text {
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottomMargin: 5
                text: xLabel
                font.pixelSize: 11
                color: textMuted
                visible: showAxis
            }

            // Y-axis label (rotated)
            Text {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 5
                text: yLabel
                font.pixelSize: 11
                color: textMuted
                rotation: -90
                transformOrigin: Item.Center
                visible: showAxis
            }

            // Title
            Text {
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.topMargin: 5
                text: graphTitle
                font.pixelSize: 12
                font.bold: true
                color: textLight
                visible: graphTitle.length > 0
            }

            // Axis tick labels
            // X-axis ticks
            Row {
                anchors.bottom: parent.bottom
                anchors.left: graphCanvas.left
                anchors.right: graphCanvas.right
                anchors.bottomMargin: 18
                visible: showAxis && curves.length > 0

                Repeater {
                    model: 6

                    Text {
                        width: graphCanvas.plotWidth / 5
                        text: formatNumber(xMin + (xMax - xMin) * index / 5)
                        font.pixelSize: 9
                        color: textMuted
                        horizontalAlignment: index === 0 ? Text.AlignLeft :
                                            (index === 5 ? Text.AlignRight : Text.AlignHCenter)
                    }
                }
            }

            // Y-axis ticks
            Column {
                anchors.left: parent.left
                anchors.top: graphCanvas.top
                anchors.bottom: graphCanvas.bottom
                anchors.leftMargin: 20
                visible: showAxis && curves.length > 0

                Repeater {
                    model: 6

                    Text {
                        height: graphCanvas.plotHeight / 5
                        text: formatNumber(yMax - (yMax - yMin) * index / 5)
                        font.pixelSize: 9
                        color: textMuted
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            // Legend
            Rectangle {
                anchors.top: graphCanvas.top
                anchors.right: graphCanvas.right
                anchors.margins: 8
                width: legendColumn.width + 16
                height: legendColumn.height + 8
                color: Qt.rgba(bgDark.r, bgDark.g, bgDark.b, 0.8)
                radius: 4
                visible: showLegend && curves.length > 0

                Column {
                    id: legendColumn
                    anchors.centerIn: parent
                    spacing: 4

                    Repeater {
                        model: curves

                        Row {
                            spacing: 6

                            Rectangle {
                                width: 16
                                height: 3
                                color: modelData.color || colorPalette[index % colorPalette.length]
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: modelData.label || ("Curve " + (index + 1))
                                font.pixelSize: 10
                                color: textLight
                            }
                        }
                    }
                }
            }

            // Mouse interaction for zoom/pan (future)
            MouseArea {
                anchors.fill: graphCanvas
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                hoverEnabled: true

                property point lastPos

                onWheel: function(wheel) {
                    // Zoom functionality
                    var zoomFactor = wheel.angleDelta.y > 0 ? 0.9 : 1.1

                    var centerX = (xMax + xMin) / 2
                    var centerY = (yMax + yMin) / 2
                    var rangeX = (xMax - xMin) * zoomFactor
                    var rangeY = (yMax - yMin) * zoomFactor

                    xMin = centerX - rangeX / 2
                    xMax = centerX + rangeX / 2
                    yMin = centerY - rangeY / 2
                    yMax = centerY + rangeY / 2

                    autoScale = false
                    graphCanvas.requestPaint()
                }

                onDoubleClicked: {
                    // Reset to auto-scale
                    autoScale = true
                    calculateBounds()
                    graphCanvas.requestPaint()
                }
            }
        }
    }

    // Helper functions
    function calculateBounds() {
        if (curves.length === 0) return

        var newXMin = Infinity, newXMax = -Infinity
        var newYMin = Infinity, newYMax = -Infinity

        for (var i = 0; i < curves.length; i++) {
            var curve = curves[i]
            if (!curve.x || !curve.y) continue

            for (var j = 0; j < curve.x.length; j++) {
                if (curve.x[j] < newXMin) newXMin = curve.x[j]
                if (curve.x[j] > newXMax) newXMax = curve.x[j]
                if (curve.y[j] < newYMin) newYMin = curve.y[j]
                if (curve.y[j] > newYMax) newYMax = curve.y[j]
            }
        }

        // Add padding
        var xPadding = (newXMax - newXMin) * 0.05 || 0.5
        var yPadding = (newYMax - newYMin) * 0.05 || 0.5

        xMin = newXMin - xPadding
        xMax = newXMax + xPadding
        yMin = newYMin - yPadding
        yMax = newYMax + yPadding
    }

    function formatNumber(num) {
        if (Math.abs(num) < 0.001 || Math.abs(num) >= 10000) {
            return num.toExponential(1)
        }
        return num.toFixed(2)
    }

    function addCurve(x, y, label, color) {
        var newCurve = {
            x: x,
            y: y,
            label: label || ("Curve " + (curves.length + 1)),
            color: color || colorPalette[curves.length % colorPalette.length]
        }
        curves = curves.concat([newCurve])

        if (autoScale) {
            calculateBounds()
        }

        if (contentItem) {
            contentItem.children[0].requestPaint()  // graphCanvas
        }
    }

    function clearCurves() {
        curves = []
        if (contentItem) {
            contentItem.children[0].requestPaint()
        }
    }

    function updateCurve(index, x, y) {
        if (index >= 0 && index < curves.length) {
            var updatedCurves = curves.slice()
            updatedCurves[index].x = x
            updatedCurves[index].y = y
            curves = updatedCurves

            if (autoScale) {
                calculateBounds()
            }

            if (contentItem) {
                contentItem.children[0].requestPaint()
            }
        }
    }

    function refresh() {
        if (contentItem) {
            contentItem.children[0].requestPaint()
        }
    }

    // Repaint when curves change
    onCurvesChanged: {
        if (contentItem) {
            contentItem.children[0].requestPaint()
        }
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.curves) curves = entityData.curves
            if (entityData.xLabel) xLabel = entityData.xLabel
            if (entityData.yLabel) yLabel = entityData.yLabel
            if (entityData.graphTitle) graphTitle = entityData.graphTitle
        }
    }

    Component.onCompleted: {
        console.log("GraphEntity created:", entityId)
        // Apply initial data if present
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.curves) curves = entityData.curves
        }
    }
}
