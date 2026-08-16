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
    id: workflowWindowRoot

    property string workflowId: ""
    property string workflowName: "New Workflow"
    property var workflowManager: null

    // Theme colors - reactive bindings to main window
    // mainWin is passed directly when WorkflowWindow is created
    property var mainWin: null

    // Debug: log when mainWin is set
    onMainWinChanged: {
        if (mainWin) {
            console.log("WorkflowWindow: mainWin set, theme colors available")
        }
    }

    // Watch for color changes on main window - trigger repaint and port color refresh
    Connections {
        target: mainWin
        enabled: mainWin !== null

        function onBgDarkChanged() { refreshColors() }
        function onAccentPinkChanged() { refreshColors() }
        function onAccentBlueChanged() { refreshColors() }
        function onAccentMagentaChanged() { refreshColors() }
        function onAccentPurpleChanged() { refreshColors() }
        function onBorderColorChanged() { refreshColors() }
        function onTextMutedChanged() { refreshColors() }
    }

    // Refresh all colors - increment version to force bindings to re-evaluate
    function refreshColors() {
        portColorVersion++
        gridCanvas.requestPaint()
        canvas.requestPaint()
    }

    // Re-render canvases when theme changes
    onIsLightThemeChanged: {
        refreshColors()
    }

    // Reactive color properties with fallbacks
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentMagenta: mainWin ? mainWin.accentMagenta : "#D60270"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color accentGreen: "#66ff99"  // Keep workflow-specific colors
    property color accentOrange: "#FFB7C5"
    property color accentYellow: "#FFE5B4"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Detect if we're in a light theme by checking bgDark luminance
    // Light themes have bgDark values like "#F5F0F8" (high luminance)
    property bool isLightTheme: {
        var hex = bgDark.toString().replace("#", "")
        if (hex.length >= 2) {
            var r = parseInt(hex.substring(0, 2), 16)
            return r > 200  // If red component > 200, it's a light theme
        }
        return false
    }

    // Grid color - reactive to theme
    property color gridColor: isLightTheme ? "#D0D0D8" : "#2a2a3e"

    // Version counter to force re-evaluation of port colors when theme changes
    property int portColorVersion: 0

    // Safe port colors - hardcoded hex strings that ALWAYS work as fallback
    // Port types from PortType enum: dataset, flat_data, image, map, table, number, string, intervals, any
    // Colors chosen to be maximally distinct from each other
    readonly property var safePortColors: ({
        "dataset": "#5BCEFA",       // Cyan/Trans blue - spectral datasets
        "flat_data": "#FFD700",     // Gold/Yellow - flattened data (distinct from blue)
        "image": "#FF6B6B",         // Coral red - images
        "map": "#9B4F96",           // Purple - map data
        "table": "#2ECC71",         // Emerald green - table/DataFrame
        "number": "#E91E63",        // Pink/Magenta - numeric values
        "string": "#FF9800",        // Orange - text strings
        "intervals": "#00BCD4",     // Teal - interval lists
        "any": "#9E9E9E"            // Gray - any type (flexible)
    })

    // Safe getPortColor function - computes themed colors dynamically each call
    // This ensures colors are always current (readonly property would freeze at init time)
    function getPortColor(portType) {
        // Debug: check accent colors (uncomment to troubleshoot)
        // console.log("getPortColor:", portType, "accentBlue:", accentBlue.toString(), "accentPink:", accentPink.toString())

        // If accent colors aren't initialized yet (black), use safe fallback directly
        var blueStr = accentBlue.toString()
        if (blueStr === "#000000" || blueStr === "") {
            console.log("WorkflowWindow.getPortColor: accentBlue not initialized, using fallback for", portType)
            return safePortColors[portType] || safePortColors["any"] || "#888888"
        }

        // Compute themed color dynamically - fixed distinct colors with some theme accents
        var themedColor = null
        try {
            switch (portType) {
                case "dataset":
                    themedColor = accentBlue.toString()       // Theme cyan/blue
                    break
                case "flat_data":
                    themedColor = "#FFD700"                   // Fixed gold (distinct)
                    break
                case "image":
                    themedColor = "#FF6B6B"                   // Fixed coral red
                    break
                case "map":
                    themedColor = accentPurple.toString()     // Theme purple
                    break
                case "table":
                    themedColor = "#2ECC71"                   // Fixed emerald green
                    break
                case "number":
                    themedColor = accentMagenta.toString()    // Theme magenta/pink
                    break
                case "string":
                    themedColor = "#FF9800"                   // Fixed orange
                    break
                case "intervals":
                    themedColor = "#00BCD4"                   // Fixed teal
                    break
                case "any":
                    themedColor = textMuted.toString()        // Theme gray
                    break
                default:
                    // Unknown port type - log it
                    console.log("WorkflowWindow.getPortColor: unknown port type:", portType)
                    break
            }
        } catch (e) {
            console.log("WorkflowWindow.getPortColor: error for", portType, ":", e)
            // Fall through to safe colors
        }

        // Return themed color if valid, otherwise fallback to safe hardcoded colors
        if (themedColor && themedColor !== "" && themedColor !== "undefined" && themedColor !== "#000000") {
            return themedColor
        }
        return safePortColors[portType] || safePortColors["any"] || "#888888"
    }

    // Legacy portColors for backwards compatibility
    property var portColors: safePortColors

    // Canvas state
    property real canvasScale: 1.0
    property real canvasOffsetX: 0
    property real canvasOffsetY: 0
    property var nodes: []
    property var connections: []
    property var selectedNode: null
    property var selectedConnection: null
    property var connectionStart: null  // {nodeId, portId, isOutput, x, y, portType}
    property bool isWiring: false

    // Signal emitted when a parameter changes (for live updates)
    signal nodeParameterChanged(string nodeId, string paramName, var value)

    // Bumped on every parameter change so node delegates re-evaluate their
    // param-dependent bindings WITHOUT resetting the Repeater model.
    // (Resetting the model destroyed all node delegates mid-interaction,
    // which killed the active drag — comment/text nodes became unmovable.)
    property int nodeParamsVersion: 0

    width: 1200
    height: 800
    minimumWidth: 800
    minimumHeight: 600
    title: "Workflow Editor - " + workflowName
    color: bgDark

    Component.onCompleted: {
        // mainWin is now passed directly when creating WorkflowWindow
        console.log("WorkflowWindow completed, mainWin:", mainWin ? "available" : "not set")
        if (workflowManager && workflowId === "") {
            workflowId = workflowManager.createWorkflow(workflowName)
        }
        loadToolCategories()

        // If tools didn't load, retry with a timer (handles timing issues)
        if (toolboxModel.count === 0) {
            console.log("Tool palette empty on completion, scheduling retry...")
            toolLoadRetryTimer.start()
        }
    }

    // Watch for workflowManager being set after creation
    onWorkflowManagerChanged: {
        console.log("workflowManager changed:", workflowManager ? "valid" : "null")
        if (workflowManager) {
            // Create workflow if needed
            if (workflowId === "") {
                workflowId = workflowManager.createWorkflow(workflowName)
            }
            // Reload tools
            loadToolCategories()
        }
    }

    // Retry timer for loading tools
    Timer {
        id: toolLoadRetryTimer
        interval: 100
        repeat: false
        onTriggered: {
            console.log("Retrying tool load...")
            loadToolCategories()
            if (toolboxModel.count === 0 && retryCount < 5) {
                retryCount++
                start()
            }
        }
        property int retryCount: 0
    }

    // Handler for parameter changes - update node data in place and bump the
    // version counter so delegates refresh. Never reset nodeRepeater.model
    // here: that recreates every delegate and cancels any in-progress drag.
    onNodeParameterChanged: function(nodeId, paramName, value) {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].id === nodeId) {
                if (!nodes[i].parameters) {
                    nodes[i].parameters = {}
                }
                nodes[i].parameters[paramName] = value
                nodeParamsVersion++
                break
            }
        }
    }

    function loadToolCategories() {
        console.log("loadToolCategories called, workflowManager:", workflowManager ? "valid" : "null")

        if (!workflowManager) {
            console.log("No workflowManager available")
            return
        }

        var categoriesList = workflowManager.getToolCategories()

        if (!categoriesList || categoriesList.length === 0) {
            console.log("No categories returned from getToolCategories")
            return
        }

        console.log("Got", categoriesList.length, "categories")
        toolboxModel.clear()
        var totalTools = 0

        for (var i = 0; i < categoriesList.length; i++) {
            var catObj = categoriesList[i]
            var category = catObj.category
            var tools = catObj.tools
            console.log("Processing category:", category, "with", tools.length, "tools")

            for (var j = 0; j < tools.length; j++) {
                var toolInfo = workflowManager.getToolInfo(tools[j])
                // Get port types as JSON string for ListModel
                var portTypesStr = JSON.stringify(toolInfo.port_types || [])
                toolboxModel.append({
                    "category": category,
                    "toolName": tools[j],
                    "displayName": toolInfo.display_name || tools[j],
                    "description": toolInfo.description || "",
                    "portTypes": portTypesStr
                })
                totalTools++
            }
        }

        console.log("Tool palette loaded with", totalTools, "tools")
    }

    function addNode(toolName, x, y) {
        if (workflowManager && workflowId) {
            var nodeId = workflowManager.addNode(workflowId, toolName, x, y)
            if (nodeId) {
                refreshWorkflow()
                return nodeId
            }
        }
        return ""
    }

    function removeNode(nodeId) {
        if (workflowManager && workflowId) {
            workflowManager.removeNode(workflowId, nodeId)
            if (selectedNode && selectedNode.id === nodeId) {
                selectedNode = null
                parameterEditor.clearNode()
            }
            refreshWorkflow()
        }
    }

    function addConnection(sourceNode, sourcePort, targetNode, targetPort) {
        if (workflowManager && workflowId) {
            var connId = workflowManager.addConnection(workflowId, sourceNode, sourcePort, targetNode, targetPort)
            if (connId) {
                refreshWorkflow()
                validationStatus.text = "Connection added"
                validationStatus.color = accentGreen
                return connId
            } else {
                validationStatus.text = "Invalid connection (type mismatch or cycle)"
                validationStatus.color = accentOrange
            }
        }
        return ""
    }

    function removeConnection(connectionId) {
        if (workflowManager && workflowId) {
            workflowManager.removeConnection(workflowId, connectionId)
            selectedConnection = null
            refreshWorkflow()
        }
    }

    function refreshWorkflow() {
        if (!workflowManager || !workflowId) {
            console.log("refreshWorkflow: workflowManager or workflowId not available")
            return
        }

        try {
            console.log("refreshWorkflow: Getting workflow data...")
            var data = workflowManager.getWorkflowData(workflowId)

            if (!data) {
                console.log("refreshWorkflow: No data returned")
                return
            }

            console.log("refreshWorkflow: Got", data.nodes ? data.nodes.length : 0, "nodes")

            // Update nodes and connections with defensive copies
            nodes = data.nodes ? data.nodes.slice() : []
            connections = data.connections ? data.connections.slice() : []

            // Use Qt.callLater to defer model update (prevents race conditions)
            Qt.callLater(function() {
                if (nodeRepeater) {
                    nodeRepeater.model = nodes
                }
                if (canvas) {
                    canvas.requestPaint()
                }
            })
        } catch (e) {
            console.error("refreshWorkflow error:", e)
        }
    }

    function validateWorkflow() {
        if (workflowManager && workflowId) {
            var errors = workflowManager.validateWorkflow(workflowId)
            if (errors.length === 0) {
                validationStatus.text = "Workflow is valid"
                validationStatus.color = accentGreen
            } else {
                validationStatus.text = "Errors: " + errors.join("; ")
                validationStatus.color = accentOrange
            }
            return errors.length === 0
        }
        return false
    }

    function saveWorkflow() {
        if (workflowManager && workflowId) {
            // Update workflow name from text field before saving
            workflowManager.setWorkflowName(workflowId, workflowName)
            var path = workflowManager.saveWorkflow(workflowId)
            if (path) {
                validationStatus.text = "Saved to: " + path
                validationStatus.color = accentGreen
            }
        }
    }

    function executeWorkflow() {
        if (validateWorkflow()) {
            if (workflowManager && workflowId) {
                workflowManager.executeWorkflow(workflowId)
            }
        }
    }

    function cancelWiring() {
        connectionStart = null
        isWiring = false
        canvas.requestPaint()
        validationStatus.text = "Wiring cancelled"
        validationStatus.color = textMuted
    }

    function handlePortClick(nodeId, portId, isOutput, portX, portY) {
        console.log("handlePortClick called:", nodeId, portId, isOutput, portX, portY)
        var node = getNodeById(nodeId)
        var portType = node ? getPortType(node, portId, isOutput) : "any"
        console.log("Port type:", portType, "isWiring:", isWiring)

        if (!isWiring) {
            // Start wiring
            connectionStart = {
                nodeId: nodeId,
                portId: portId,
                isOutput: isOutput,
                x: portX,
                y: portY,
                portType: portType
            }
            isWiring = true
            console.log("Wiring started from port:", portId, "on node:", nodeId)
            validationStatus.text = "Click on " + (isOutput ? "an input" : "an output") + " port to complete connection"
            validationStatus.color = accentPink
            canvas.requestPaint()
        } else {
            // Complete wiring
            if (connectionStart.nodeId !== nodeId) {
                // Determine source and target based on port types
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
                    validationStatus.text = "Connect output to input (not same type)"
                    validationStatus.color = accentOrange
                }

                if (sourceNode && targetNode) {
                    console.log("Creating connection:", sourceNode, sourcePort, "->", targetNode, targetPort)
                    addConnection(sourceNode, sourcePort, targetNode, targetPort)
                }
            } else {
                validationStatus.text = "Cannot connect node to itself"
                validationStatus.color = accentOrange
            }

            connectionStart = null
            isWiring = false
            canvas.requestPaint()
        }
    }

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

        var portY = node.y + 45 + portIndex * 25  // Header height + port offset
        var portX = isOutput ? (node.x + 180) : node.x  // Node width is 180

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

    // Keyboard shortcuts
    Shortcut {
        sequence: "Delete"
        onActivated: {
            if (selectedConnection) {
                removeConnection(selectedConnection.id)
                validationStatus.text = "Connection deleted"
                validationStatus.color = textMuted
            } else if (selectedNode) {
                deleteConfirmDialog.nodeToDelete = selectedNode.id
                deleteConfirmDialog.nodeName = selectedNode.display_name
                deleteConfirmDialog.open()
            }
        }
    }

    Shortcut {
        sequence: "Backspace"
        onActivated: {
            if (selectedConnection) {
                removeConnection(selectedConnection.id)
                validationStatus.text = "Connection deleted"
                validationStatus.color = textMuted
            } else if (selectedNode) {
                deleteConfirmDialog.nodeToDelete = selectedNode.id
                deleteConfirmDialog.nodeName = selectedNode.display_name
                deleteConfirmDialog.open()
            }
        }
    }

    Shortcut {
        sequence: "Escape"
        onActivated: {
            if (isWiring) {
                cancelWiring()
            }
        }
    }

    // Toolbar
    Rectangle {
        id: toolbar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 50
        color: bgDarker
        z: 100

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: borderColor
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 10

            // Workflow name
            TextField {
                id: nameField
                text: workflowName
                Layout.preferredWidth: 200
                color: textLight
                font.pixelSize: 14
                font.bold: true

                background: Rectangle {
                    color: bgMedium
                    border.color: nameField.activeFocus ? accentBlue : borderColor
                    radius: 3
                }

                onTextChanged: {
                    workflowName = text
                }
            }

            Rectangle { width: 1; height: 30; color: borderColor }

            // Action buttons
            Button {
                text: "Validate"
                onClicked: validateWorkflow()

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : bgMedium
                    border.color: accentBlue
                    radius: 3
                }
            }

            Button {
                text: "Save"
                onClicked: saveWorkflow()

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : bgMedium
                    border.color: accentGreen
                    radius: 3
                }
            }

            Button {
                text: "Run"
                onClicked: executeWorkflow()

                contentItem: Text {
                    text: parent.text
                    color: textLight
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
                background: Rectangle {
                    color: parent.hovered ? accentPink : bgMedium
                    border.color: accentPink
                    radius: 3
                }
            }

            Rectangle { width: 1; height: 30; color: borderColor }

            // Zoom controls
            Text {
                text: "Zoom:"
                color: textMuted
                font.pixelSize: 12
            }

            Slider {
                id: zoomSlider
                Layout.preferredWidth: 100
                from: 0.25
                to: 2.0
                value: 1.0
                onValueChanged: {
                    canvasScale = value
                    gridCanvas.requestPaint()
                    canvas.requestPaint()
                }
            }

            Text {
                text: Math.round(canvasScale * 100) + "%"
                color: textLight
                font.pixelSize: 12
            }

            Button {
                text: "Reset View"
                onClicked: {
                    canvasScale = 1.0
                    canvasOffsetX = 0
                    canvasOffsetY = 0
                    zoomSlider.value = 1.0
                }

                contentItem: Text {
                    text: parent.text
                    color: textMuted
                    font.pixelSize: 11
                }
                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }
            }

            Item { Layout.fillWidth: true }

            // Wiring indicator
            Rectangle {
                visible: isWiring
                width: wiringText.width + 20
                height: 24
                radius: 12
                color: accentPink
                opacity: 0.8

                Text {
                    id: wiringText
                    anchors.centerIn: parent
                    text: "Wiring... (ESC to cancel)"
                    color: bgDark
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            // Status
            Text {
                id: validationStatus
                text: "Ready - Drag tools to canvas, click ports to wire"
                color: textMuted
                font.pixelSize: 12
            }
        }
    }

    // Main content area
    SplitView {
        anchors.top: toolbar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        orientation: Qt.Horizontal

        // Toolbox (left panel)
        Rectangle {
            SplitView.minimumWidth: 200
            SplitView.preferredWidth: 250
            SplitView.maximumWidth: 350
            color: bgMedium

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 5
                spacing: 5

                Text {
                    text: "Tool Palette"
                    color: accentPink
                    font.pixelSize: 14
                    font.bold: true
                    Layout.fillWidth: true
                    padding: 5
                }

                TextField {
                    id: toolSearch
                    placeholderText: "Search tools..."
                    Layout.fillWidth: true
                    color: textLight

                    background: Rectangle {
                        color: bgDark
                        border.color: toolSearch.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }
                }

                ListView {
                    id: toolList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    model: ListModel { id: toolboxModel }

                    section.property: "category"
                    section.delegate: Rectangle {
                        width: toolList.width
                        height: 25
                        color: bgDarker

                        Text {
                            text: section
                            color: accentBlue
                            font.pixelSize: 12
                            font.bold: true
                            anchors.verticalCenter: parent.verticalCenter
                            leftPadding: 8
                        }
                    }

                    delegate: Rectangle {
                        width: toolList.width
                        height: visible ? 50 : 0
                        visible: toolSearch.text === "" ||
                                 displayName.toLowerCase().includes(toolSearch.text.toLowerCase())
                        color: toolDragArea.containsMouse ? bgLight : "transparent"

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 5
                            spacing: 8

                            // Port type color indicators with golden ratio overlap
                            Item {
                                id: portIndicators
                                Layout.preferredWidth: {
                                    var types = JSON.parse(portTypes || "[]")
                                    if (types.length === 0) return 0
                                    // Circle diameter = 10, spacing = diameter / golden ratio = ~6.18
                                    var circleSize = 10
                                    var spacing = circleSize / 1.618  // Golden ratio spacing
                                    return circleSize + (types.length - 1) * spacing
                                }
                                Layout.preferredHeight: 10
                                Layout.alignment: Qt.AlignVCenter

                                Repeater {
                                    model: JSON.parse(portTypes || "[]")

                                    Rectangle {
                                        id: portColorRect
                                        width: 10
                                        height: 10
                                        radius: 5
                                        // Use the safe getPortColor function
                                        // Include portColorVersion to force re-evaluation on theme change
                                        property string portColorStr: {
                                            var v = portColorVersion  // Reference to trigger rebinding
                                            return getPortColor(modelData)
                                        }
                                        color: portColorStr
                                        border.width: 1
                                        // Safe border color - use try-catch pattern
                                        border.color: {
                                            try {
                                                return Qt.darker(portColorStr, 1.3)
                                            } catch (e) {
                                                return "#666666"
                                            }
                                        }
                                        // Position each circle with golden ratio overlap
                                        x: index * (10 / 1.618)  // 10 / 1.618 ≈ 6.18
                                        y: 0
                                    }
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: displayName
                                    color: textLight
                                    font.pixelSize: 12
                                }

                                Text {
                                    text: description
                                    color: textMuted
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        MouseArea {
                            id: toolDragArea
                            anchors.fill: parent
                            hoverEnabled: true

                            drag.target: toolDragItem

                            onPressed: function(mouse) {
                                toolDragItem.toolName = toolName
                                toolDragItem.displayName = displayName
                                toolDragItem.visible = true
                                // Convert mouse position to root item coordinates (null = root)
                                var globalPos = mapToItem(null, mouse.x, mouse.y)
                                toolDragItem.x = globalPos.x - toolDragItem.width / 2
                                toolDragItem.y = globalPos.y - toolDragItem.height / 2
                            }

                            onReleased: {
                                if (toolDragItem.visible) {
                                    // Check if dropped on canvas - use center of drag item
                                    var dragCenterX = toolDragItem.x + toolDragItem.width / 2
                                    var dragCenterY = toolDragItem.y + toolDragItem.height / 2
                                    var canvasPos = canvasArea.mapFromItem(null, dragCenterX, dragCenterY)
                                    if (canvasPos.x > 0 && canvasPos.y > 0 &&
                                        canvasPos.x < canvasArea.width && canvasPos.y < canvasArea.height) {
                                        // Add node at drop position
                                        var nodeX = (canvasPos.x - canvasOffsetX) / canvasScale
                                        var nodeY = (canvasPos.y - canvasOffsetY) / canvasScale
                                        addNode(toolDragItem.toolName, nodeX, nodeY)
                                    }
                                    toolDragItem.visible = false
                                }
                            }
                        }
                    }

                    ScrollBar.vertical: ScrollBar {
                        active: true
                    }
                }

                // Help text
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 70
                    color: bgDark
                    radius: 5

                    Text {
                        anchors.fill: parent
                        anchors.margins: 8
                        text: "Drag tools to canvas\nClick output port, then input port to wire\nClick wire to select, Del/Backspace to delete\nDel key removes selected node"
                        color: textMuted
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                    }
                }
            }
        }

        // Canvas area (center)
        Rectangle {
            id: canvasArea
            SplitView.fillWidth: true
            color: bgDark
            clip: true

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

                    // Use theme-reactive grid color
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
                id: canvas
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

                        // Draw bezier curve to mouse
                        var endX = canvasArea.tempConnectionEnd.x
                        var endY = canvasArea.tempConnectionEnd.y
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

                        // Draw endpoint circle
                        ctx.fillStyle = portColor
                        ctx.beginPath()
                        ctx.arc(endX, endY, 6, 0, Math.PI * 2)
                        ctx.fill()
                    }
                }

                function drawConnection(ctx, conn, isSelected) {
                    var sourceNode = getNodeById(conn.source_node_id)
                    var targetNode = getNodeById(conn.target_node_id)

                    if (!sourceNode || !targetNode) return

                    // Get accurate port positions
                    var sourcePos = getPortPosition(sourceNode, conn.source_port_id, true)
                    var targetPos = getPortPosition(targetNode, conn.target_port_id, false)

                    var startX = sourcePos.x * canvasScale + canvasOffsetX
                    var startY = sourcePos.y * canvasScale + canvasOffsetY
                    var endX = targetPos.x * canvasScale + canvasOffsetX
                    var endY = targetPos.y * canvasScale + canvasOffsetY

                    // Get port type for color - use safe getPortColor function
                    var portType = getPortType(sourceNode, conn.source_port_id, true)
                    var wireColor = getPortColor(portType)

                    // Draw bezier curve
                    ctx.strokeStyle = isSelected ? accentPink : wireColor
                    ctx.lineWidth = isSelected ? 4 : 2.5
                    ctx.lineWidth *= canvasScale

                    var controlOffset = Math.max(50, Math.abs(endX - startX) * 0.4)

                    ctx.beginPath()
                    ctx.moveTo(startX, startY)
                    ctx.bezierCurveTo(
                        startX + controlOffset, startY,
                        endX - controlOffset, endY,
                        endX, endY
                    )
                    ctx.stroke()

                    // Draw glow if selected
                    if (isSelected) {
                        ctx.strokeStyle = accentPink
                        ctx.lineWidth = 8 * canvasScale
                        ctx.globalAlpha = 0.3
                        ctx.beginPath()
                        ctx.moveTo(startX, startY)
                        ctx.bezierCurveTo(
                            startX + controlOffset, startY,
                            endX - controlOffset, endY,
                            endX, endY
                        )
                        ctx.stroke()
                        ctx.globalAlpha = 1.0
                    }

                    // Draw arrow at end
                    var arrowSize = 8 * canvasScale
                    var angle = Math.atan2(endY - (endY - controlOffset * 0.1), endX - (endX - controlOffset))
                    ctx.fillStyle = isSelected ? accentPink : wireColor
                    ctx.beginPath()
                    ctx.moveTo(endX, endY)
                    ctx.lineTo(endX - arrowSize * Math.cos(angle - Math.PI/6), endY - arrowSize * Math.sin(angle - Math.PI/6))
                    ctx.lineTo(endX - arrowSize * Math.cos(angle + Math.PI/6), endY - arrowSize * Math.sin(angle + Math.PI/6))
                    ctx.closePath()
                    ctx.fill()
                }

                // Hit test for connections
                function hitTestConnection(mouseX, mouseY) {
                    var threshold = 10

                    for (var i = 0; i < connections.length; i++) {
                        var conn = connections[i]
                        var sourceNode = getNodeById(conn.source_node_id)
                        var targetNode = getNodeById(conn.target_node_id)

                        if (!sourceNode || !targetNode) continue

                        var sourcePos = getPortPosition(sourceNode, conn.source_port_id, true)
                        var targetPos = getPortPosition(targetNode, conn.target_port_id, false)

                        var startX = sourcePos.x * canvasScale + canvasOffsetX
                        var startY = sourcePos.y * canvasScale + canvasOffsetY
                        var endX = targetPos.x * canvasScale + canvasOffsetX
                        var endY = targetPos.y * canvasScale + canvasOffsetY

                        // Simple distance check along the bezier curve
                        var controlOffset = Math.max(50, Math.abs(endX - startX) * 0.4)

                        // Sample points along the curve
                        for (var t = 0; t <= 1; t += 0.05) {
                            var px = bezierPoint(startX, startX + controlOffset, endX - controlOffset, endX, t)
                            var py = bezierPoint(startY, startY, endY, endY, t)

                            var dist = Math.sqrt(Math.pow(mouseX - px, 2) + Math.pow(mouseY - py, 2))
                            if (dist < threshold) {
                                return conn
                            }
                        }
                    }
                    return null
                }

                function bezierPoint(p0, p1, p2, p3, t) {
                    var u = 1 - t
                    return u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3
                }
            }

            property point tempConnectionEnd: Qt.point(0, 0)

            // Nodes container
            Item {
                id: nodesContainer
                anchors.fill: parent
                z: 2
                clip: false  // Allow node ports to extend outside

                transform: [
                    Scale {
                        origin.x: 0
                        origin.y: 0
                        xScale: canvasScale
                        yScale: canvasScale
                    },
                    Translate {
                        x: canvasOffsetX
                        y: canvasOffsetY
                    }
                ]

                Repeater {
                    id: nodeRepeater
                    model: []

                    delegate: WorkflowNode {
                        id: workflowNodeDelegate
                        nodeData: modelData
                        workflowWindow: workflowWindowRoot

                        onNodeSelected: {
                            selectedNode = nodeData
                            selectedConnection = null
                            parameterEditor.loadNode(nodeData)
                            if (canvas) canvas.requestPaint()
                        }

                        onNodeMoved: function(nodeId, newX, newY) {
                            if (workflowManager && workflowId) {
                                workflowManager.updateNodePosition(workflowId, nodeId, newX, newY)
                                if (canvas) canvas.requestPaint()
                            }
                        }

                        onNodePositionChanged: function(nodeId, newX, newY) {
                            // Update node position in local array during drag for live wire updates
                            for (var i = 0; i < nodes.length; i++) {
                                if (nodes[i].id === nodeId) {
                                    nodes[i].x = newX
                                    nodes[i].y = newY
                                    break
                                }
                            }
                            if (canvas) canvas.requestPaint()
                        }

                        onPortClicked: function(nodeId, portId, isOutput, portX, portY) {
                            handlePortClick(nodeId, portId, isOutput, portX, portY)
                        }

                        onDeleteRequested: function(nodeId) {
                            deleteConfirmDialog.nodeToDelete = nodeId
                            var node = getNodeById(nodeId)
                            deleteConfirmDialog.nodeName = node ? node.display_name : "Node"
                            deleteConfirmDialog.open()
                        }
                    }
                }
            }

            // Canvas pan/zoom interaction - BEHIND nodes (z: 0)
            MouseArea {
                id: canvasMouseArea
                anchors.fill: parent
                z: 0
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                hoverEnabled: true  // Need this to track mouse position for wiring

                property point lastPos

                onPressed: function(mouse) {
                    lastPos = Qt.point(mouse.x, mouse.y)

                    if (mouse.button === Qt.LeftButton) {
                        // Check if clicking on a connection
                        var hitConn = canvas.hitTestConnection(mouse.x, mouse.y)
                        if (hitConn) {
                            selectedConnection = hitConn
                            selectedNode = null
                            parameterEditor.clearNode()
                            canvas.requestPaint()
                        } else if (!isWiring) {
                            selectedNode = null
                            selectedConnection = null
                            parameterEditor.clearNode()
                            canvas.requestPaint()
                        }
                    }

                    if (mouse.button === Qt.RightButton && isWiring) {
                        cancelWiring()
                    }
                }

                onPositionChanged: function(mouse) {
                    // Pan with left mouse button (or middle button)
                    if (pressed && (mouse.buttons & Qt.LeftButton || mouse.buttons & Qt.MiddleButton)) {
                        canvasOffsetX += mouse.x - lastPos.x
                        canvasOffsetY += mouse.y - lastPos.y
                        lastPos = Qt.point(mouse.x, mouse.y)
                        gridCanvas.requestPaint()
                        canvas.requestPaint()
                    }

                    // Update temp connection line while wiring (even when not pressed)
                    if (isWiring) {
                        canvasArea.tempConnectionEnd = Qt.point(mouse.x, mouse.y)
                        canvas.requestPaint()
                    }
                }

                // Scroll zoom with 30% sensitivity
                onWheel: function(wheel) {
                    // Reduced sensitivity: 1.03/0.97 instead of 1.1/0.9 (about 30% of original)
                    var zoomFactor = wheel.angleDelta.y > 0 ? 1.03 : 0.97
                    var newScale = Math.max(0.25, Math.min(2.0, canvasScale * zoomFactor))

                    // Zoom towards mouse position
                    var mouseX = wheel.x
                    var mouseY = wheel.y

                    canvasOffsetX = mouseX - (mouseX - canvasOffsetX) * (newScale / canvasScale)
                    canvasOffsetY = mouseY - (mouseY - canvasOffsetY) * (newScale / canvasScale)

                    canvasScale = newScale
                    zoomSlider.value = newScale
                    gridCanvas.requestPaint()
                    canvas.requestPaint()
                }
            }
        }

        // Parameter editor (right panel)
        Rectangle {
            id: parameterPanel
            SplitView.minimumWidth: 200
            SplitView.preferredWidth: 280
            SplitView.maximumWidth: 400
            color: bgMedium

            NodeParameterEditor {
                id: parameterEditor
                anchors.fill: parent
                anchors.margins: 5
                workflowWindow: workflowWindowRoot
            }
        }
    }

    // Drag item for tools
    Rectangle {
        id: toolDragItem
        width: 150
        height: 40
        color: bgLight
        border.color: accentPink
        border.width: 2
        radius: 5
        visible: false
        z: 1000

        property string toolName: ""
        property string displayName: ""

        Text {
            anchors.centerIn: parent
            text: parent.displayName
            color: textLight
            font.pixelSize: 12
        }

        Drag.active: true
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteConfirmDialog

        property string nodeToDelete: ""
        property string nodeName: ""

        title: "Delete Node"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent

        width: 350
        height: 150

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            border.width: 1
            radius: 5
        }

        contentItem: ColumnLayout {
            spacing: 10

            Text {
                text: "Delete node \"" + deleteConfirmDialog.nodeName + "\"?"
                color: textLight
                font.pixelSize: 14
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }

            Text {
                text: "This will also remove all connections to this node."
                color: textMuted
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }

        onAccepted: {
            if (nodeToDelete) {
                removeNode(nodeToDelete)
                validationStatus.text = "Node deleted"
                validationStatus.color = textMuted
            }
        }
    }

    // Connections to workflow manager
    Connections {
        target: workflowManager

        function onWorkflowExecutionStarted(name) {
            validationStatus.text = "Executing: " + name
            validationStatus.color = accentPink
            executionOverlay.visible = true
            executionOverlay.workflowName = name
            executionOverlay.currentStep = 0
            executionOverlay.totalSteps = 0
            executionOverlay.currentMessage = "Starting..."
        }

        function onWorkflowExecutionCompleted(name, success, errors) {
            executionOverlay.visible = false

            if (success) {
                validationStatus.text = "Completed: " + name
                validationStatus.color = accentGreen
                resultDialog.isSuccess = true
                resultDialog.workflowName = name
                resultDialog.resultMessage = "Workflow executed successfully!\n\nOutputs have been added to the dataset list."
                resultDialog.open()
            } else {
                validationStatus.text = "Failed: " + errors.join("; ")
                validationStatus.color = "#D60270"
                resultDialog.isSuccess = false
                resultDialog.workflowName = name
                resultDialog.resultMessage = "Workflow execution failed:\n\n" + errors.join("\n")
                resultDialog.open()
            }
        }

        function onWorkflowExecutionProgress(current, total, message) {
            validationStatus.text = message + " (" + current + "/" + total + ")"
            executionOverlay.currentStep = current
            executionOverlay.totalSteps = total
            executionOverlay.currentMessage = message
        }
    }

    // Execution overlay (shows during workflow execution)
    Rectangle {
        id: executionOverlay
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.7)
        visible: false
        z: 2000

        property string workflowName: ""
        property int currentStep: 0
        property int totalSteps: 0
        property string currentMessage: ""

        MouseArea {
            anchors.fill: parent
            // Block all mouse events while executing
        }

        Rectangle {
            anchors.centerIn: parent
            width: 350
            height: 180
            color: bgMedium
            border.color: accentPink
            border.width: 2
            radius: 10

            Column {
                anchors.centerIn: parent
                spacing: 15

                Text {
                    text: "Executing Workflow"
                    color: accentPink
                    font.pixelSize: 18
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: executionOverlay.workflowName
                    color: textLight
                    font.pixelSize: 14
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                // Progress indicator
                Rectangle {
                    width: 280
                    height: 8
                    color: bgDark
                    radius: 4
                    anchors.horizontalCenter: parent.horizontalCenter

                    Rectangle {
                        width: executionOverlay.totalSteps > 0 ?
                               parent.width * (executionOverlay.currentStep / executionOverlay.totalSteps) : 0
                        height: parent.height
                        color: accentPink
                        radius: 4

                        Behavior on width { NumberAnimation { duration: 200 } }
                    }
                }

                Text {
                    text: executionOverlay.currentMessage
                    color: textMuted
                    font.pixelSize: 12
                    anchors.horizontalCenter: parent.horizontalCenter
                    elide: Text.ElideMiddle
                    width: 280
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    text: executionOverlay.totalSteps > 0 ?
                          "Step " + executionOverlay.currentStep + " of " + executionOverlay.totalSteps : ""
                    color: textMuted
                    font.pixelSize: 11
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    // Result dialog
    Dialog {
        id: resultDialog

        property bool isSuccess: true
        property string workflowName: ""
        property string resultMessage: ""

        title: isSuccess ? "Workflow Complete" : "Workflow Failed"
        modal: true
        standardButtons: Dialog.Ok
        anchors.centerIn: parent

        width: 400
        height: 250

        background: Rectangle {
            color: bgMedium
            border.color: resultDialog.isSuccess ? accentGreen : "#D60270"
            border.width: 2
            radius: 8
        }

        contentItem: ColumnLayout {
            spacing: 15

            // Icon and title row
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Rectangle {
                    width: 40
                    height: 40
                    radius: 20
                    color: resultDialog.isSuccess ? accentGreen : "#D60270"

                    Text {
                        anchors.centerIn: parent
                        text: resultDialog.isSuccess ? "✓" : "✕"
                        color: bgDark
                        font.pixelSize: 24
                        font.bold: true
                    }
                }

                Text {
                    text: resultDialog.workflowName
                    color: textLight
                    font.pixelSize: 16
                    font.bold: true
                    Layout.fillWidth: true
                }
            }

            // Message
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                TextArea {
                    text: resultDialog.resultMessage
                    color: textLight
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    readOnly: true
                    background: Rectangle {
                        color: bgDark
                        radius: 4
                    }
                }
            }
        }
    }
}
