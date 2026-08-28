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
import "../components"   // the Theme singleton

Rectangle {
    id: nodeRoot

    property var nodeData: ({})
    property var workflowWindow: null
    property bool isSelected: workflowWindow && workflowWindow.selectedNode &&
                              nodeData && workflowWindow.selectedNode.id === nodeData.id

    // Ensure nodeData is always a valid object
    property bool nodeDataValid: nodeData !== null && nodeData !== undefined && typeof nodeData === "object"

    // Theme colors - get from parent workflowWindow
    property color bgDark: (workflowWindow && workflowWindow.bgDark !== undefined) ? workflowWindow.bgDark : Theme.bgDark
    property color bgMedium: (workflowWindow && workflowWindow.bgMedium !== undefined) ? workflowWindow.bgMedium : Theme.bgMedium
    property color bgLight: (workflowWindow && workflowWindow.bgLight !== undefined) ? workflowWindow.bgLight : Theme.bgLight
    property color accentPink: (workflowWindow && workflowWindow.accentPink !== undefined) ? workflowWindow.accentPink : Theme.accentPink
    property color accentBlue: (workflowWindow && workflowWindow.accentBlue !== undefined) ? workflowWindow.accentBlue : Theme.accentBlue
    property color accentMagenta: (workflowWindow && workflowWindow.accentMagenta !== undefined) ? workflowWindow.accentMagenta : Theme.accentMagenta
    // Status colours. Green means "valid / connected", the error red means
    // "this will not run" — semantics, not decoration, so they keep their
    // hue rather than taking an accent. They still come from the palette:
    // every scheme carries a `success` and an `error` key for exactly this,
    // and Theme publishes them as successColor and accentMagenta. (The amber
    // warning below has no home on Theme yet; it is left fixed until it does.)
    property color accentGreen: (workflowWindow && workflowWindow.successColor !== undefined) ? workflowWindow.successColor : Theme.successColor
    property color accentOrange: "#FFB7C5"
    property color textLight: (workflowWindow && workflowWindow.textLight !== undefined) ? workflowWindow.textLight : Theme.textLight
    property color textMuted: (workflowWindow && workflowWindow.textMuted !== undefined) ? workflowWindow.textMuted : Theme.textMuted
    property color borderColor: (workflowWindow && workflowWindow.borderColor !== undefined) ? workflowWindow.borderColor : Theme.borderColor

    // Port colors are now obtained via getPortColor() function which delegates to workflowWindow
    // Version counter from workflowWindow triggers re-evaluation when theme changes
    property int portColorVersion: workflowWindow ? workflowWindow.portColorVersion : 0

    // Bumped by WorkflowWindow whenever any node parameter changes; bindings
    // that read nodeData.parameters reference this so they re-evaluate
    // (nodeData itself is mutated in place and emits no change signal)
    property int paramsVersion: workflowWindow ? workflowWindow.nodeParamsVersion : 0

    signal nodeSelected()
    signal nodeMoved(string nodeId, real newX, real newY)
    signal nodePositionChanged(string nodeId, real newX, real newY)  // Emitted during drag
    signal portClicked(string nodeId, string portId, bool isOutput, real portX, real portY)
    signal deleteRequested(string nodeId)

    x: nodeDataValid && nodeData.x !== undefined ? nodeData.x : 0
    y: nodeDataValid && nodeData.y !== undefined ? nodeData.y : 0
    width: { var v = paramsVersion; return isCommentNode ? getCommentWidth() : 180 }
    height: { var v = paramsVersion; return calculateHeight() }
    visible: nodeDataValid

    color: { var v = paramsVersion; return isCommentNode ? getCommentBgColor() : bgMedium }
    opacity: { var v = paramsVersion; return isCommentNode ? getCommentOpacity() : 1.0 }
    border.color: { var v = paramsVersion; return isSelected ? accentPink : (isCommentNode ? Qt.darker(getCommentBgColor(), 1.2) : borderColor) }
    border.width: isSelected ? 2 : 1
    radius: isCommentNode ? 6 : 8
    clip: false  // Allow port circles to extend outside node bounds

    // Comment node resizing
    function getCommentWidth() {
        if (!nodeDataValid || !nodeData.parameters) return 180
        return nodeData.parameters.node_width || 180
    }

    function getCommentHeight() {
        if (!nodeDataValid || !nodeData.parameters) return 100
        return nodeData.parameters.node_height || 100
    }

    function calculateHeight() {
        if (!nodeDataValid) return 80  // Default height when data not ready

        var inputCount = nodeData.inputs ? nodeData.inputs.length : 0
        var outputCount = nodeData.outputs ? nodeData.outputs.length : 0
        var portCount = Math.max(inputCount, outputCount)

        // Comment nodes use custom sizing from parameters
        if (isCommentNode) {
            return getCommentHeight()
        }

        var baseHeight = 60 + Math.max(portCount, 1) * 25
        // Add extra height if we have parameters to display
        if (getDisplayParameter()) {
            baseHeight += 20
        }
        return baseHeight
    }

    // Get the most important parameter to display on the node
    function getDisplayParameter() {
        if (!nodeDataValid || !nodeData.parameters) return ""
        // For comment nodes, show the text
        if (isCommentNode && nodeData.parameters.text) return nodeData.parameters.text

        var params = nodeData.parameters
        var parts = []

        // Output name always shown first if present
        if (params.output_name) parts.push(params.output_name)
        if (params.dataset_names && params.dataset_names.length > 1)
            parts.push(params.dataset_names.length + " datasets (run in turn)")
        else if (params.dataset_name) parts.push(params.dataset_name)

        // Tool-specific parameter display
        if (nodeData.tool_name === "TruncateData") {
            var xMin = params.x_min !== undefined ? params.x_min : "-"
            var xMax = params.x_max !== undefined ? params.x_max : "-"
            parts.push("Range: " + xMin + " to " + xMax)
        } else if (nodeData.tool_name === "Derivative") {
            var order = params.order || 1
            parts.push(order + (order === 1 ? "st" : "nd") + " order")
        } else if (nodeData.tool_name === "Integration") {
            if (params.intervals && params.intervals.length > 0) {
                parts.push(params.intervals.length + " intervals")
            }
        } else if (nodeData.tool_name === "BaselineCorrection") {
            parts.push((params.fit_type || "polynomial") + " deg " + (params.degree || 2))
        } else if (nodeData.tool_name === "PeakFinder") {
            var prom = params.prominence
            if (prom === undefined || prom === null || prom <= 0) {
                parts.push("prominence: auto")
            } else {
                parts.push("prominence: " + prom)
            }
        } else if (nodeData.tool_name === "ConfinementAnalysis") {
            var bg = params.baseline || "poly-iter"
            parts.push(bg === "none" ? "no background"
                                     : bg + " deg " + (params.baseline_degree !== undefined
                                                       ? params.baseline_degree : 3))
            if (params.temperature_k > 0) parts.push(params.temperature_k + " K")
        } else if (nodeData.tool_name === "BaselineEstimate") {
            var method = params.method || "arpls"
            parts.push(method === "none" ? "no background"
                                         : (method === "poly" || method === "poly-iter"
                                            || method === "endpoints")
                                           ? method + " deg " + (params.degree !== undefined
                                                                 ? params.degree : 3)
                                           : method)
        } else if (nodeData.tool_name === "EnergyBinning") {
            if (params.bin_width > 0) parts.push("bins of " + params.bin_width)
            else if (params.temperature_k > 0) parts.push(params.temperature_k + " K bins")
            else parts.push("sweep-step bins")
            if (params.min_spectra_per_bin > 1)
                parts.push("min " + params.min_spectra_per_bin + " spectra")
        } else if (nodeData.tool_name === "MapAssembly") {
            parts.push(params.scan_type || "auto")
            if (params.columns) parts.push(params.columns)
            if (params.joined_map === false) parts.push("no joined map")
        } else if (nodeData.tool_name === "MapGenerator") {
            if (params.column_index !== undefined) {
                parts.push("col: " + params.column_index)
            }
        } else if (nodeData.tool_name === "SpatialAverage") {
            parts.push((params.discrete_x || 10) + "x" + (params.discrete_y || 10))
        } else if (nodeData.tool_name === "CurveSmoothing") {
            parts.push((params.method || "savgol") + " w=" + (params.window_size || 11))
        } else if (nodeData.tool_name === "DataManipulation") {
            if (params.equation) parts.push(params.equation)
        }

        return parts.join(" | ")
    }

    // Check if this is a comment node
    property bool isCommentNode: nodeDataValid && nodeData.tool_name === "CommentNode"

    // A comment node's colours are the user's: whatever they picked is stored
    // in nodeData.parameters and is returned untouched. Only the DEFAULT —
    // what an unconfigured comment gets — comes from the scheme, so a new
    // comment matches the workflow it was dropped into instead of always
    // arriving in the 2018 brand pink.
    //
    // The default pair is deliberate rather than convenient: accentPink is
    // the scheme's accentPrimary and bgDark is its window ground, and
    // bgDark-on-accentPrimary is one of the pairings
    // src/utils/color_contrast.py enforces at 4.5:1 — the "primary button"
    // pair. So the default text is guaranteed readable on the default ground
    // for all 22 schemes, which the old #333333-on-#F5A9B8 was not.
    function getCommentBgColor() {
        if (!isCommentNode || !nodeData.parameters) return accentPink
        return nodeData.parameters.bg_color || accentPink
    }

    function getCommentTextColor() {
        if (!isCommentNode || !nodeData.parameters) return bgDark
        return nodeData.parameters.text_color || bgDark
    }

    // Get comment node opacity
    function getCommentOpacity() {
        if (!isCommentNode || !nodeData.parameters) return 0.9
        var opacity = nodeData.parameters.opacity
        if (opacity === undefined || opacity === null) return 0.9
        return Math.max(0.1, Math.min(1.0, opacity))
    }

    // Get comment node font size (now a numeric value)
    function getCommentFontSize() {
        if (!isCommentNode || !nodeData.parameters) return 12
        return nodeData.parameters.font_size || 12
    }

    // Default fallback color to prevent crashes
    readonly property color fallbackColor: "#888888"

    // Hardcoded color map - guaranteed to work without crashes
    // Colors chosen to be maximally distinct from each other
    readonly property var safePortColors: ({
        "dataset": "#5BCEFA",       // Cyan/Trans blue - spectral datasets
        "flat_data": "#FFD700",     // Gold/Yellow - flattened data
        "image": "#FF6B6B",         // Coral red - images
        "map": "#9B4F96",           // Purple - map data
        "table": "#2ECC71",         // Emerald green - table/DataFrame
        "number": "#E91E63",        // Pink/Magenta - numeric values
        "string": "#FF9800",        // Orange - text strings
        "intervals": "#00BCD4",     // Teal - interval lists
        "any": "#9E9E9E"            // Gray - any type (flexible)
    })

    function getPortColor(portType) {
        // Debug: log what port type we're getting (uncomment to troubleshoot)
        // console.log("WorkflowNode.getPortColor called with:", portType, "->", safePortColors[portType])

        // First try to get themed color from workflowWindow
        if (workflowWindow && workflowWindow.getPortColor) {
            try {
                var themedColor = workflowWindow.getPortColor(portType)
                if (themedColor && themedColor !== "" && themedColor !== "undefined" && themedColor !== "#888888") {
                    return themedColor
                }
            } catch (e) {
                console.log("WorkflowNode.getPortColor error:", e)
            }
        }

        // Fallback to local safe hardcoded colors
        var localColor = safePortColors[portType]
        if (localColor) {
            return localColor
        }

        // Ultimate fallback
        console.log("WorkflowNode.getPortColor: unknown port type:", portType)
        return safePortColors["any"] || "#888888"
    }

    // Safe color operations that won't crash on invalid colors
    function safeColor(c) {
        // Ensure we always have a valid color
        if (!c || c === undefined || c === null) return fallbackColor
        return c
    }

    function safeLighter(c, factor) {
        var color = safeColor(c)
        try {
            return Qt.lighter(color, factor)
        } catch (e) {
            return color
        }
    }

    function safeDarker(c, factor) {
        var color = safeColor(c)
        try {
            return Qt.darker(color, factor)
        } catch (e) {
            return color
        }
    }

    function safeRgba(c, alpha) {
        var colorStr = safeColor(c)
        try {
            // Qt.color() properly converts a color string to a QColor object
            var color = Qt.color(colorStr)
            return Qt.rgba(color.r, color.g, color.b, alpha)
        } catch (e) {
            // Fallback: return a semi-transparent gray
            return Qt.rgba(0.5, 0.5, 0.5, alpha)
        }
    }

    // Check if a port is compatible with the current wiring operation
    function isPortCompatible(portType, isOutput) {
        if (!workflowWindow || !workflowWindow.isWiring || !workflowWindow.connectionStart) {
            return false
        }

        var start = workflowWindow.connectionStart
        // Can't connect to same node
        if (start.nodeId === nodeData.id) return false
        // Must connect output to input (opposite types)
        if (start.isOutput === isOutput) return false
        // Type compatibility check
        if (start.portType === "any" || portType === "any") return true
        return start.portType === portType
    }

    // Header - hidden for comment nodes
    Rectangle {
        id: header
        visible: !isCommentNode
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: isCommentNode ? 0 : 30
        radius: 8
        color: isSelected ? accentPink : bgLight

        Rectangle {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: 8
            color: parent.color
        }

        // Drag area for non-comment nodes
        MouseArea {
            id: dragArea
            anchors.fill: parent
            drag.target: nodeRoot
            hoverEnabled: true
            cursorShape: Qt.SizeAllCursor
            z: 150

            onPressed: {
                nodeSelected()
            }

            onPositionChanged: {
                if (drag.active) {
                    nodePositionChanged(nodeData.id, nodeRoot.x, nodeRoot.y)
                }
            }

            onReleased: {
                nodeMoved(nodeData.id, nodeRoot.x, nodeRoot.y)
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 5
            spacing: 5

            Text {
                text: nodeData.display_name || "Node"
                color: isSelected ? bgDark : textLight
                font.pixelSize: 11
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            // Delete button for non-comment nodes
            Rectangle {
                id: deleteButtonRect
                width: 18
                height: 18
                radius: 9
                color: deleteBtn.containsMouse ? accentMagenta : "transparent"
                z: 200

                Text {
                    anchors.centerIn: parent
                    text: "x"
                    color: deleteBtn.containsMouse ? textLight : textMuted
                    font.pixelSize: 12
                    font.bold: true
                }

                MouseArea {
                    id: deleteBtn
                    anchors.fill: parent
                    anchors.margins: -5
                    hoverEnabled: true
                    propagateComposedEvents: false

                    onPressed: function(mouse) {
                        mouse.accepted = true
                    }

                    onClicked: function(mouse) {
                        mouse.accepted = true
                        deleteRequested(nodeData.id)
                    }
                }

                ToolTip {
                    visible: deleteBtn.containsMouse
                    text: "Delete node (Del key)"
                    delay: 500
                }
            }
        }
    }

    // Comment node special layout - entire node is draggable with text
    Item {
        id: commentNodeLayout
        visible: isCommentNode
        anchors.fill: parent

        // Make entire comment node draggable
        MouseArea {
            id: commentDragArea
            anchors.fill: parent
            drag.target: nodeRoot
            hoverEnabled: true
            cursorShape: Qt.SizeAllCursor
            z: 50

            onPressed: {
                nodeSelected()
            }

            onPositionChanged: {
                if (drag.active) {
                    nodePositionChanged(nodeData.id, nodeRoot.x, nodeRoot.y)
                }
            }

            onReleased: {
                nodeMoved(nodeData.id, nodeRoot.x, nodeRoot.y)
            }
        }

        // Comment text display
        Text {
            id: commentText
            anchors.fill: parent
            anchors.margins: 10
            anchors.rightMargin: 30  // Leave space for close button
            text: { var v = paramsVersion; return nodeData.parameters ? (nodeData.parameters.text || "Enter note here...") : "Enter note here..." }
            color: { var v = paramsVersion; return getCommentTextColor() }
            font.pixelSize: { var v = paramsVersion; return getCommentFontSize() }
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            verticalAlignment: Text.AlignTop
            horizontalAlignment: Text.AlignLeft
        }

        // Floating close button for comment node
        Rectangle {
            id: commentDeleteBtn
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 5
            anchors.rightMargin: 5
            width: 20
            height: 20
            radius: 10
            color: commentDeleteArea.containsMouse ? accentMagenta : Qt.rgba(0, 0, 0, 0.3)
            z: 200

            Text {
                anchors.centerIn: parent
                text: "×"
                color: commentDeleteArea.containsMouse ? textLight : Qt.darker(getCommentBgColor(), 1.5)
                font.pixelSize: 14
                font.bold: true
            }

            MouseArea {
                id: commentDeleteArea
                anchors.fill: parent
                anchors.margins: -5
                hoverEnabled: true
                propagateComposedEvents: false

                onPressed: function(mouse) {
                    mouse.accepted = true
                }

                onClicked: function(mouse) {
                    mouse.accepted = true
                    deleteRequested(nodeData.id)
                }
            }

            ToolTip {
                visible: commentDeleteArea.containsMouse
                text: "Delete comment (Del key)"
                delay: 500
            }
        }

        // Resize handle (bottom-right corner)
        Rectangle {
            id: resizeHandle
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            width: 12
            height: 12
            color: "transparent"
            z: 300

            // Visual indicator
            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.strokeStyle = Qt.darker(getCommentBgColor(), 1.3)
                    ctx.lineWidth = 1
                    // Draw diagonal lines
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

            MouseArea {
                id: resizeArea
                anchors.fill: parent
                anchors.margins: -5
                hoverEnabled: true
                cursorShape: Qt.SizeFDiagCursor
                propagateComposedEvents: false

                property real startX: 0
                property real startY: 0
                property real startWidth: 0
                property real startHeight: 0

                onPressed: function(mouse) {
                    mouse.accepted = true
                    startX = mouse.x
                    startY = mouse.y
                    startWidth = nodeRoot.width
                    startHeight = nodeRoot.height
                }

                onPositionChanged: function(mouse) {
                    if (pressed) {
                        var newWidth = Math.round(Math.max(100, startWidth + mouse.x - startX))
                        var newHeight = Math.round(Math.max(60, startHeight + mouse.y - startY))
                        // Persist in the backend workflow model
                        if (workflowWindow && workflowWindow.workflowManager) {
                            workflowWindow.workflowManager.setNodeParameter(
                                workflowWindow.workflowId, nodeData.id, "node_width", newWidth)
                            workflowWindow.workflowManager.setNodeParameter(
                                workflowWindow.workflowId, nodeData.id, "node_height", newHeight)
                        }
                        // Update the local node data + bump paramsVersion so the
                        // width/height bindings re-evaluate (live resize)
                        if (workflowWindow) {
                            workflowWindow.nodeParameterChanged(nodeData.id, "node_width", newWidth)
                            workflowWindow.nodeParameterChanged(nodeData.id, "node_height", newHeight)
                        }
                    }
                }
            }
        }
    }

    // Node body with ports - hidden for comment nodes
    Item {
        visible: !isCommentNode
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 5
        clip: false  // Allow ports to extend outside

        // Input ports (left side)
        Column {
            id: inputPorts
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.topMargin: 5
            spacing: 5
            clip: false  // Allow ports to extend outside
            z: 10  // Ensure ports are above other content

            Repeater {
                model: nodeData.inputs || []

                delegate: Item {
                    id: inputPortItem
                    width: 85
                    height: 20

                    property bool isCompatible: isPortCompatible(modelData.port_type, false)
                    property bool isHighlighted: inputPortArea.containsMouse ||
                                                 (workflowWindow && workflowWindow.isWiring && isCompatible)

                    // Port circle - positioned outside the node body
                    Rectangle {
                        id: inputPort
                        width: isHighlighted ? 16 : 12
                        height: isHighlighted ? 16 : 12
                        radius: width / 2
                        anchors.left: parent.left
                        anchors.leftMargin: isHighlighted ? -8 : -6
                        anchors.verticalCenter: parent.verticalCenter
                        // Include portColorVersion to trigger re-evaluation on theme change
                        property string currentPortColor: {
                            var v = portColorVersion  // Force rebinding when version changes
                            return getPortColor(modelData.port_type)
                        }
                        color: inputPortArea.containsMouse ? safeLighter(currentPortColor, 1.4) : currentPortColor
                        border.color: isHighlighted ? textLight : safeDarker(currentPortColor, 1.2)
                        border.width: isHighlighted ? 2 : 1

                        Behavior on width { NumberAnimation { duration: 100 } }
                        Behavior on height { NumberAnimation { duration: 100 } }

                        // Pulsing animation when compatible during wiring
                        SequentialAnimation on opacity {
                            running: inputPortItem.isCompatible && workflowWindow && workflowWindow.isWiring
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.6; duration: 400 }
                            NumberAnimation { to: 1.0; duration: 400 }
                        }

                        MouseArea {
                            id: inputPortArea
                            anchors.fill: parent
                            anchors.margins: -10  // Larger click area
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            z: 100  // Ensure ports are on top

                            onClicked: function(mouse) {
                                mouse.accepted = true  // Prevent event from propagating
                                var pos = getPortPosition()
                                console.log("Input port clicked:", modelData.id, "at", pos.x, pos.y)
                                portClicked(nodeData.id, modelData.id, false, pos.x, pos.y)
                            }

                            function getPortPosition() {
                                return {
                                    x: nodeRoot.x,
                                    y: nodeRoot.y + header.height + inputPorts.y + index * 25 + 15
                                }
                            }
                        }

                        // No tooltip - info shown inline
                    }

                    // Port label with type indicator - displayed inline on the node
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3

                        Text {
                            text: modelData.name
                            color: inputPortItem.isHighlighted ? textLight : textMuted
                            font.pixelSize: 10
                            font.bold: inputPortItem.isHighlighted
                        }

                        // Required indicator
                        Text {
                            visible: modelData.required
                            text: "*"
                            color: accentOrange
                            font.pixelSize: 10
                            font.bold: true
                        }

                        // Type badge (shown on hover)
                        Rectangle {
                            visible: inputPortArea.containsMouse
                            width: typeText.implicitWidth + 6
                            height: 12
                            radius: 3
                            // Use the inputPort's currentPortColor for consistency
                            color: safeRgba(inputPort.currentPortColor, 0.3)
                            border.color: inputPort.currentPortColor
                            border.width: 1

                            Text {
                                id: typeText
                                anchors.centerIn: parent
                                text: modelData.port_type
                                color: textLight
                                font.pixelSize: 8
                            }
                        }
                    }
                }
            }
        }

        // Parameter display (centered below ports)
        Rectangle {
            id: paramDisplay
            visible: { var v = paramsVersion; return getDisplayParameter() !== "" }
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 2
            height: isCommentNode ? Math.min(60, paramText.implicitHeight + 8) : 16
            color: isCommentNode ? "transparent" : Qt.rgba(0, 0, 0, 0.3)
            radius: 3

            Text {
                id: paramText
                anchors.fill: parent
                anchors.margins: 3
                text: { var v = paramsVersion; return getDisplayParameter() }
                color: isCommentNode ? getCommentTextColor() : accentBlue
                font.pixelSize: { var v = paramsVersion; return isCommentNode ? getCommentFontSize() : 9 }
                font.italic: !isCommentNode
                elide: Text.ElideRight
                wrapMode: isCommentNode ? Text.Wrap : Text.NoWrap
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        // Output ports (right side)
        Column {
            id: outputPorts
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 5
            spacing: 5
            clip: false  // Allow ports to extend outside
            z: 10  // Ensure ports are above other content

            Repeater {
                model: nodeData.outputs || []

                delegate: Item {
                    id: outputPortItem
                    width: 85
                    height: 20

                    property bool isCompatible: isPortCompatible(modelData.port_type, true)
                    property bool isHighlighted: outputPortArea.containsMouse ||
                                                 (workflowWindow && workflowWindow.isWiring && isCompatible)

                    // Port circle - positioned outside the node body
                    Rectangle {
                        id: outputPort
                        width: isHighlighted ? 16 : 12
                        height: isHighlighted ? 16 : 12
                        radius: width / 2
                        anchors.right: parent.right
                        anchors.rightMargin: isHighlighted ? -8 : -6
                        anchors.verticalCenter: parent.verticalCenter
                        // Include portColorVersion to trigger re-evaluation on theme change
                        property string currentPortColor: {
                            var v = portColorVersion  // Force rebinding when version changes
                            return getPortColor(modelData.port_type)
                        }
                        color: outputPortArea.containsMouse ? safeLighter(currentPortColor, 1.4) : currentPortColor
                        border.color: isHighlighted ? textLight : safeDarker(currentPortColor, 1.2)
                        border.width: isHighlighted ? 2 : 1

                        Behavior on width { NumberAnimation { duration: 100 } }
                        Behavior on height { NumberAnimation { duration: 100 } }

                        // Pulsing animation when compatible during wiring
                        SequentialAnimation on opacity {
                            running: outputPortItem.isCompatible && workflowWindow && workflowWindow.isWiring
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.6; duration: 400 }
                            NumberAnimation { to: 1.0; duration: 400 }
                        }

                        MouseArea {
                            id: outputPortArea
                            anchors.fill: parent
                            anchors.margins: -10  // Larger click area
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            z: 100  // Ensure ports are on top

                            onClicked: function(mouse) {
                                mouse.accepted = true  // Prevent event from propagating
                                var pos = getPortPosition()
                                console.log("Output port clicked:", modelData.id, "at", pos.x, pos.y)
                                portClicked(nodeData.id, modelData.id, true, pos.x, pos.y)
                            }

                            function getPortPosition() {
                                return {
                                    x: nodeRoot.x + nodeRoot.width,
                                    y: nodeRoot.y + header.height + outputPorts.y + index * 25 + 15
                                }
                            }
                        }

                        // No tooltip - info shown inline
                    }

                    // Port label with type indicator - displayed inline on the node (right-aligned)
                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        layoutDirection: Qt.RightToLeft

                        Text {
                            text: modelData.name
                            color: outputPortItem.isHighlighted ? textLight : textMuted
                            font.pixelSize: 10
                            font.bold: outputPortItem.isHighlighted
                            horizontalAlignment: Text.AlignRight
                        }

                        // Type badge (shown on hover)
                        Rectangle {
                            visible: outputPortArea.containsMouse
                            width: outTypeText.implicitWidth + 6
                            height: 12
                            radius: 3
                            // Use the outputPort's currentPortColor for consistency
                            color: safeRgba(outputPort.currentPortColor, 0.3)
                            border.color: outputPort.currentPortColor
                            border.width: 1

                            Text {
                                id: outTypeText
                                anchors.centerIn: parent
                                text: modelData.port_type
                                color: textLight
                                font.pixelSize: 8
                            }
                        }
                    }
                }
            }
        }
    }

    // Selection highlight glow
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: 11
        color: "transparent"
        border.color: accentPink
        border.width: isSelected ? 1 : 0
        opacity: 0.5
        visible: isSelected
    }

    // Helper function to count connections for this node
    function countConnections() {
        if (!workflowWindow) return 0
        var count = 0
        var conns = workflowWindow.connections || []
        for (var i = 0; i < conns.length; i++) {
            if (conns[i].source_node_id === nodeData.id ||
                conns[i].target_node_id === nodeData.id) {
                count++
            }
        }
        return count
    }

    // Connected indicator (shows number of connections)
    Rectangle {
        visible: false  // Can enable to show connection count
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 5
        width: 20
        height: 16
        radius: 3
        color: bgDark

        Text {
            anchors.centerIn: parent
            text: nodeRoot.countConnections()
            color: accentBlue
            font.pixelSize: 9
            font.bold: true
        }
    }
}
