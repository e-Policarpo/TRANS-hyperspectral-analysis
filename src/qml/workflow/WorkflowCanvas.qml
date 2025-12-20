/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * WorkflowCanvas - Embeddable workflow canvas for node-based editing
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: workflowCanvas

    // Workflow data
    property string workflowId: ""
    property var workflowManager: null
    property var nodes: []
    property var connections: []

    // Canvas state
    property real canvasScale: 1.0
    property real canvasOffsetX: 0
    property real canvasOffsetY: 0
    property var selectedNode: null
    property var selectedConnection: null
    property var connectionStart: null
    property bool isWiring: false

    // Temporary connection end point
    property point tempConnectionEnd: Qt.point(0, 0)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentMagenta: mainWin ? mainWin.accentMagenta : "#D60270"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color accentGreen: "#66ff99"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Detect light theme
    property bool isLightTheme: {
        var hex = bgDark.toString().replace("#", "")
        if (hex.length >= 2) {
            var r = parseInt(hex.substring(0, 2), 16)
            return r > 200
        }
        return false
    }

    // Grid color
    property color gridColor: isLightTheme ? "#D0D0D8" : "#2a2a3e"

    // Port colors
    readonly property var portColors: ({
        "dataset": "#5BCEFA",
        "flat_data": "#FFD700",
        "image": "#FF6B6B",
        "map": "#9B4F96",
        "table": "#2ECC71",
        "number": "#E91E63",
        "string": "#FF9800",
        "intervals": "#00BCD4",
        "any": "#9E9E9E"
    })

    // Signals
    signal nodeSelected(var node)
    signal nodeDeselected()
    signal connectionCreated(string sourceNode, string sourcePort, string targetNode, string targetPort)
    signal connectionRemoved(string connectionId)
    signal nodeRemoved(string nodeId)
    signal nodeAdded(string nodeId, string toolName, real x, real y)
    signal statusMessage(string message, color messageColor)

    color: bgDark
    clip: true

    function getPortColor(portType) {
        var color = portColors[portType]
        return color ? color : portColors["any"]
    }

    // Grid background
    Canvas {
        id: gridCanvas
        anchors.fill: parent

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()

            var gridSize = 20 * canvasScale
            var offsetX = canvasOffsetX % gridSize
            var offsetY = canvasOffsetY % gridSize

            ctx.strokeStyle = gridColor.toString()
            ctx.lineWidth = 1

            // Vertical lines
            for (var x = offsetX; x < width; x += gridSize) {
                ctx.beginPath()
                ctx.moveTo(x, 0)
                ctx.lineTo(x, height)
                ctx.stroke()
            }

            // Horizontal lines
            for (var y = offsetY; y < height; y += gridSize) {
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(width, y)
                ctx.stroke()
            }
        }
    }

    // Connection lines canvas
    Canvas {
        id: connectionCanvas
        anchors.fill: parent
        z: 1

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()

            // Draw existing connections
            for (var i = 0; i < connections.length; i++) {
                var conn = connections[i]
                var isSelected = selectedConnection && selectedConnection.id === conn.id
                drawConnection(ctx, conn, isSelected)
            }

            // Draw temporary connection while wiring
            if (connectionStart && isWiring) {
                var portColor = getPortColor(connectionStart.portType)
                ctx.strokeStyle = portColor
                ctx.lineWidth = 3
                ctx.setLineDash([8, 4])

                var startX = connectionStart.x * canvasScale + canvasOffsetX
                var startY = connectionStart.y * canvasScale + canvasOffsetY

                var endX = tempConnectionEnd.x
                var endY = tempConnectionEnd.y
                var controlOffset = Math.abs(endX - startX) * 0.5

                ctx.beginPath()
                ctx.moveTo(startX, startY)
                ctx.bezierCurveTo(
                    startX + (connectionStart.isOutput ? controlOffset : -controlOffset), startY,
                    endX + (connectionStart.isOutput ? -controlOffset : controlOffset), endY,
                    endX, endY
                )
                ctx.stroke()
                ctx.setLineDash([])
            }
        }

        function drawConnection(ctx, conn, isSelected) {
            var sourceNode = getNodeById(conn.source_node)
            var targetNode = getNodeById(conn.target_node)

            if (!sourceNode || !targetNode) return

            var sourcePos = getPortPosition(sourceNode, conn.source_port, true)
            var targetPos = getPortPosition(targetNode, conn.target_port, false)

            var x1 = sourcePos.x * canvasScale + canvasOffsetX
            var y1 = sourcePos.y * canvasScale + canvasOffsetY
            var x2 = targetPos.x * canvasScale + canvasOffsetX
            var y2 = targetPos.y * canvasScale + canvasOffsetY

            var portType = getPortType(sourceNode, conn.source_port, true)
            var portColor = getPortColor(portType)

            ctx.strokeStyle = isSelected ? accentPink.toString() : portColor
            ctx.lineWidth = isSelected ? 4 : 2

            var controlOffset = Math.abs(x2 - x1) * 0.5

            ctx.beginPath()
            ctx.moveTo(x1, y1)
            ctx.bezierCurveTo(x1 + controlOffset, y1, x2 - controlOffset, y2, x2, y2)
            ctx.stroke()

            // Draw arrow at end
            if (!isSelected) {
                ctx.fillStyle = portColor
                var angle = Math.atan2(y2 - y1, x2 - x1)
                ctx.beginPath()
                ctx.moveTo(x2, y2)
                ctx.lineTo(x2 - 8 * Math.cos(angle - 0.3), y2 - 8 * Math.sin(angle - 0.3))
                ctx.lineTo(x2 - 8 * Math.cos(angle + 0.3), y2 - 8 * Math.sin(angle + 0.3))
                ctx.closePath()
                ctx.fill()
            }
        }
    }

    // Node container
    Item {
        id: nodeContainer
        x: canvasOffsetX
        y: canvasOffsetY
        scale: canvasScale
        transformOrigin: Item.TopLeft
        z: 2

        Repeater {
            id: nodeRepeater
            model: nodes

            delegate: WorkflowNode {
                id: nodeItem
                nodeData: modelData
                isSelected: selectedNode && selectedNode.id === modelData.id
                workflowWindow: workflowCanvas

                x: modelData.x
                y: modelData.y

                onNodeSelected: {
                    selectedNode = nodeData
                    selectedConnection = null
                    workflowCanvas.nodeSelected(nodeData)
                }

                onNodeMoved: function(nodeId, newX, newY) {
                    if (workflowManager && workflowId) {
                        workflowManager.updateNodePosition(workflowId, nodeId, newX, newY)
                    }
                }

                onPortClicked: function(nodeId, portId, isOutput, portX, portY) {
                    handlePortClick(nodeId, portId, isOutput, portX, portY)
                }

                onDeleteRequested: function(nodeId) {
                    if (workflowManager && workflowId) {
                        workflowManager.removeNode(workflowId, nodeId)
                        if (selectedNode && selectedNode.id === nodeId) {
                            selectedNode = null
                            nodeDeselected()
                        }
                        refreshWorkflow()
                        nodeRemoved(nodeId)
                    }
                }
            }
        }
    }

    // Mouse handling
    MouseArea {
        id: canvasMouseArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        hoverEnabled: true

        property bool isPanning: false
        property real lastX: 0
        property real lastY: 0

        onPressed: function(mouse) {
            if (mouse.button === Qt.MiddleButton || (mouse.button === Qt.LeftButton && mouse.modifiers & Qt.ControlModifier)) {
                isPanning = true
                lastX = mouse.x
                lastY = mouse.y
            } else if (mouse.button === Qt.RightButton && isWiring) {
                cancelWiring()
            } else if (mouse.button === Qt.LeftButton) {
                // Deselect if clicking empty canvas
                selectedNode = null
                selectedConnection = null
                nodeDeselected()
            }
        }

        onReleased: {
            isPanning = false
        }

        onPositionChanged: function(mouse) {
            if (isPanning) {
                canvasOffsetX += mouse.x - lastX
                canvasOffsetY += mouse.y - lastY
                lastX = mouse.x
                lastY = mouse.y
                gridCanvas.requestPaint()
                connectionCanvas.requestPaint()
            }

            if (isWiring) {
                tempConnectionEnd = Qt.point(mouse.x, mouse.y)
                connectionCanvas.requestPaint()
            }
        }

        onWheel: function(wheel) {
            var zoomFactor = wheel.angleDelta.y > 0 ? 1.1 : 0.9
            var newScale = Math.max(0.25, Math.min(2.0, canvasScale * zoomFactor))

            // Zoom toward mouse position
            var mouseX = wheel.x
            var mouseY = wheel.y
            canvasOffsetX = mouseX - (mouseX - canvasOffsetX) * (newScale / canvasScale)
            canvasOffsetY = mouseY - (mouseY - canvasOffsetY) * (newScale / canvasScale)

            canvasScale = newScale
            gridCanvas.requestPaint()
            connectionCanvas.requestPaint()
        }
    }

    // Drop area for tools
    DropArea {
        anchors.fill: parent
        z: 3

        onDropped: function(drop) {
            if (drop.hasText) {
                var toolName = drop.text
                var dropX = (drop.x - canvasOffsetX) / canvasScale
                var dropY = (drop.y - canvasOffsetY) / canvasScale
                addNode(toolName, dropX, dropY)
            }
        }
    }

    // Helper functions
    function getNodeById(nodeId) {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].id === nodeId) return nodes[i]
        }
        return null
    }

    function getPortPosition(node, portId, isOutput) {
        var ports = isOutput ? node.outputs : node.inputs
        var portIndex = 0
        for (var i = 0; i < ports.length; i++) {
            if (ports[i].id === portId) {
                portIndex = i
                break
            }
        }
        var portY = node.y + 45 + portIndex * 25
        var portX = isOutput ? (node.x + 180) : node.x
        return { x: portX, y: portY }
    }

    function getPortType(node, portId, isOutput) {
        var ports = isOutput ? node.outputs : node.inputs
        for (var i = 0; i < ports.length; i++) {
            if (ports[i].id === portId) {
                return ports[i].port_type
            }
        }
        return "any"
    }

    function handlePortClick(nodeId, portId, isOutput, portX, portY) {
        var node = getNodeById(nodeId)
        var portType = node ? getPortType(node, portId, isOutput) : "any"

        if (!isWiring) {
            connectionStart = {
                nodeId: nodeId,
                portId: portId,
                isOutput: isOutput,
                x: portX,
                y: portY,
                portType: portType
            }
            isWiring = true
            statusMessage("Click on " + (isOutput ? "an input" : "an output") + " port to complete connection", accentPink)
            connectionCanvas.requestPaint()
        } else {
            if (connectionStart.nodeId !== nodeId) {
                var sourceNode, sourcePort, targetNode, targetPort

                if (connectionStart.isOutput && !isOutput) {
                    sourceNode = connectionStart.nodeId
                    sourcePort = connectionStart.portId
                    targetNode = nodeId
                    targetPort = portId
                } else if (!connectionStart.isOutput && isOutput) {
                    sourceNode = nodeId
                    sourcePort = portId
                    targetNode = connectionStart.nodeId
                    targetPort = connectionStart.portId
                } else {
                    statusMessage("Connect output to input (not same type)", accentPink)
                }

                if (sourceNode && targetNode) {
                    addConnection(sourceNode, sourcePort, targetNode, targetPort)
                }
            } else {
                statusMessage("Cannot connect node to itself", accentPink)
            }

            connectionStart = null
            isWiring = false
            connectionCanvas.requestPaint()
        }
    }

    function cancelWiring() {
        connectionStart = null
        isWiring = false
        connectionCanvas.requestPaint()
        statusMessage("Wiring cancelled", textMuted)
    }

    function addNode(toolName, x, y) {
        if (workflowManager && workflowId) {
            var nodeId = workflowManager.addNode(workflowId, toolName, x, y)
            if (nodeId) {
                refreshWorkflow()
                nodeAdded(nodeId, toolName, x, y)
                return nodeId
            }
        }
        return ""
    }

    function addConnection(sourceNode, sourcePort, targetNode, targetPort) {
        if (workflowManager && workflowId) {
            var connId = workflowManager.addConnection(workflowId, sourceNode, sourcePort, targetNode, targetPort)
            if (connId) {
                refreshWorkflow()
                connectionCreated(sourceNode, sourcePort, targetNode, targetPort)
                statusMessage("Connection added", accentGreen)
                return connId
            } else {
                statusMessage("Invalid connection (type mismatch or cycle)", accentPink)
            }
        }
        return ""
    }

    function refreshWorkflow() {
        if (!workflowManager || !workflowId) return

        try {
            var data = workflowManager.getWorkflowData(workflowId)
            if (data) {
                nodes = data.nodes ? data.nodes.slice() : []
                connections = data.connections ? data.connections.slice() : []

                Qt.callLater(function() {
                    nodeRepeater.model = nodes
                    connectionCanvas.requestPaint()
                })
            }
        } catch (e) {
            console.error("refreshWorkflow error:", e)
        }
    }

    function resetView() {
        canvasScale = 1.0
        canvasOffsetX = 0
        canvasOffsetY = 0
        gridCanvas.requestPaint()
        connectionCanvas.requestPaint()
    }

    // Watch for scale changes
    onCanvasScaleChanged: {
        gridCanvas.requestPaint()
        connectionCanvas.requestPaint()
    }

    Component.onCompleted: {
        console.log("WorkflowCanvas created")
    }
}
