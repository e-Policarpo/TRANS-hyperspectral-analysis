/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * MapEntity - Floating entity for displaying hyperspectral map visualizations
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FloatingEntity {
    id: mapEntity

    entityType: "map"
    entityTitle: "Map"
    minWidth: 300
    minHeight: 250

    // Map data
    property var mapData: []  // 2D array of values
    property int mapWidth: 0
    property int mapHeight: 0
    property string mapName: ""

    // Value range
    property real minValue: 0
    property real maxValue: 1
    property bool autoRange: true

    // Colormap
    property string colormap: "viridis"  // "viridis", "plasma", "inferno", "magma", "hot", "cool", "rainbow"
    property bool invertColormap: false

    // Display options
    property bool showColorbar: true
    property bool showCoordinates: true
    property bool showGrid: false

    // Selection
    property int selectedX: -1
    property int selectedY: -1

    // Signals
    signal pixelClicked(int x, int y, real value)
    signal pixelHovered(int x, int y, real value)

    // Colormap definitions
    readonly property var colormaps: ({
        "viridis": ["#440154", "#482878", "#3e4a89", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"],
        "plasma": ["#0d0887", "#46039f", "#7201a8", "#9c179e", "#bd3786", "#d8576b", "#ed7953", "#fb9f3a", "#fdca26", "#f0f921"],
        "inferno": ["#000004", "#1b0c41", "#4a0c6b", "#781c6d", "#a52c60", "#cf4446", "#ed6925", "#fb9b06", "#f7d13d", "#fcffa4"],
        "magma": ["#000004", "#180f3d", "#440f76", "#721f81", "#9e2f7f", "#cd4071", "#f1605d", "#fd9668", "#feca8d", "#fcfdbf"],
        "hot": ["#000000", "#3b0000", "#8b0000", "#cd0000", "#ff4500", "#ff8c00", "#ffd700", "#ffff00", "#ffff7f", "#ffffff"],
        "cool": ["#00ffff", "#19e5ff", "#32cbff", "#4cb1ff", "#6697ff", "#7f7dff", "#9963ff", "#b249ff", "#cc2fff", "#ff00ff"],
        "rainbow": ["#ff0000", "#ff7f00", "#ffff00", "#7fff00", "#00ff00", "#00ff7f", "#00ffff", "#007fff", "#0000ff", "#7f00ff"]
    })

    // Content component
    contentComponent: Component {
        Item {
            id: mapContent

            // Map image canvas
            Canvas {
                id: mapCanvas
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: showColorbar ? colorbarArea.left : parent.right
                anchors.bottom: statusBar.top
                anchors.margins: 4
                anchors.rightMargin: showColorbar ? 8 : 4

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)

                    if (mapData.length === 0 || mapWidth === 0 || mapHeight === 0) {
                        drawPlaceholder(ctx)
                        return
                    }

                    // Calculate pixel size
                    var pixelW = width / mapWidth
                    var pixelH = height / mapHeight

                    // Auto-range if needed
                    if (autoRange) {
                        calculateRange()
                    }

                    // Draw map pixels
                    for (var y = 0; y < mapHeight; y++) {
                        for (var x = 0; x < mapWidth; x++) {
                            var value = getValue(x, y)
                            var color = valueToColor(value)

                            ctx.fillStyle = color
                            ctx.fillRect(x * pixelW, y * pixelH, pixelW + 1, pixelH + 1)
                        }
                    }

                    // Draw selection
                    if (selectedX >= 0 && selectedY >= 0) {
                        // White, and deliberately not from the scheme. This stroke lands
                        // on the colormap, not on the window: its job is to be seen
                        // against viridis or inferno at whatever value happens to be
                        // under it, and a scheme colour has no relationship to that.
                        // (It is genuinely weak over a pale cell — the fix there is a
                        // two-tone stroke, dark under light, not a palette binding.)
                        ctx.strokeStyle = "#ffffff"
                        ctx.lineWidth = 2
                        ctx.strokeRect(selectedX * pixelW, selectedY * pixelH, pixelW, pixelH)
                    }

                    // Draw grid
                    if (showGrid && pixelW > 5 && pixelH > 5) {
                        ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.2)
                        ctx.lineWidth = 0.5
                        for (x = 0; x <= mapWidth; x++) {
                            ctx.beginPath()
                            ctx.moveTo(x * pixelW, 0)
                            ctx.lineTo(x * pixelW, height)
                            ctx.stroke()
                        }
                        for (y = 0; y <= mapHeight; y++) {
                            ctx.beginPath()
                            ctx.moveTo(0, y * pixelH)
                            ctx.lineTo(width, y * pixelH)
                            ctx.stroke()
                        }
                    }
                }

                function drawPlaceholder(ctx) {
                    ctx.fillStyle = textMuted
                    ctx.font = "14px sans-serif"
                    ctx.textAlign = "center"
                    ctx.fillText("No map data", width / 2, height / 2)
                    ctx.font = "11px sans-serif"
                    ctx.fillText("Load a map to display", width / 2, height / 2 + 20)
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true

                    onClicked: function(mouse) {
                        if (mapWidth === 0 || mapHeight === 0) return
                        var pixelW = mapCanvas.width / mapWidth
                        var pixelH = mapCanvas.height / mapHeight
                        var x = Math.floor(mouse.x / pixelW)
                        var y = Math.floor(mouse.y / pixelH)
                        if (x >= 0 && x < mapWidth && y >= 0 && y < mapHeight) {
                            selectedX = x
                            selectedY = y
                            mapCanvas.requestPaint()
                            pixelClicked(x, y, getValue(x, y))
                        }
                    }

                    onPositionChanged: function(mouse) {
                        if (mapWidth === 0 || mapHeight === 0) return
                        var pixelW = mapCanvas.width / mapWidth
                        var pixelH = mapCanvas.height / mapHeight
                        var x = Math.floor(mouse.x / pixelW)
                        var y = Math.floor(mouse.y / pixelH)
                        if (x >= 0 && x < mapWidth && y >= 0 && y < mapHeight) {
                            pixelHovered(x, y, getValue(x, y))
                            coordLabel.text = "(" + x + ", " + y + ")"
                            valueLabel.text = formatValue(getValue(x, y))
                        }
                    }

                    onExited: {
                        coordLabel.text = ""
                        valueLabel.text = ""
                    }
                }
            }

            // Colorbar
            Rectangle {
                id: colorbarArea
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: statusBar.top
                anchors.margins: 4
                width: showColorbar ? 60 : 0
                visible: showColorbar
                color: "transparent"

                Canvas {
                    id: colorbarCanvas
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 20

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)

                        var colors = colormaps[colormap] || colormaps["viridis"]
                        var numColors = colors.length

                        for (var i = 0; i < height; i++) {
                            var t = invertColormap ? (i / height) : (1 - i / height)
                            var colorIndex = Math.floor(t * (numColors - 1))
                            var nextIndex = Math.min(colorIndex + 1, numColors - 1)
                            var blend = (t * (numColors - 1)) - colorIndex

                            // Simple color interpolation
                            ctx.fillStyle = colors[colorIndex]
                            ctx.fillRect(0, i, width, 1)
                        }

                        // Border
                        ctx.strokeStyle = borderColor
                        ctx.strokeRect(0, 0, width, height)
                    }
                }

                // Colorbar labels
                Column {
                    anchors.left: colorbarCanvas.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 4
                    width: 35

                    Text {
                        text: formatValue(invertColormap ? minValue : maxValue)
                        font.pixelSize: 9
                        color: textMuted
                    }

                    Item { height: parent.height - 30; width: 1 }

                    Text {
                        text: formatValue(invertColormap ? maxValue : minValue)
                        font.pixelSize: 9
                        color: textMuted
                    }
                }
            }

            // Status bar
            Rectangle {
                id: statusBar
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 22
                color: bgLight
                visible: showCoordinates

                Rectangle {
                    anchors.top: parent.top
                    width: parent.width
                    height: 1
                    color: borderColor
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 16

                    Text {
                        text: mapWidth + " × " + mapHeight
                        font.pixelSize: 10
                        color: textMuted
                    }

                    Text {
                        id: coordLabel
                        font.pixelSize: 10
                        color: accentBlue
                    }

                    Text {
                        id: valueLabel
                        font.pixelSize: 10
                        color: accentPink
                    }

                    Item { Layout.fillWidth: true }

                    // Colormap selector
                    ComboBox {
                        id: colormapCombo
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 18
                        model: Object.keys(colormaps)
                        currentIndex: Object.keys(colormaps).indexOf(colormap)

                        onActivated: {
                            colormap = model[currentIndex]
                            mapCanvas.requestPaint()
                            colorbarCanvas.requestPaint()
                        }

                        background: Rectangle {
                            color: bgMedium
                            border.color: borderColor
                            radius: 2
                        }

                        contentItem: Text {
                            text: colormapCombo.displayText
                            font.pixelSize: 9
                            color: textMuted
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: 4
                        }
                    }
                }
            }
        }
    }

    // Helper functions
    function getValue(x, y) {
        if (mapData.length === 0) return 0
        var index = y * mapWidth + x
        if (index >= 0 && index < mapData.length) {
            return mapData[index]
        }
        // 2D array format
        if (Array.isArray(mapData[0]) && y < mapData.length && x < mapData[y].length) {
            return mapData[y][x]
        }
        return 0
    }

    function calculateRange() {
        if (mapData.length === 0) return

        var min = Infinity, max = -Infinity

        if (Array.isArray(mapData[0])) {
            // 2D array
            for (var y = 0; y < mapData.length; y++) {
                for (var x = 0; x < mapData[y].length; x++) {
                    var v = mapData[y][x]
                    if (v < min) min = v
                    if (v > max) max = v
                }
            }
        } else {
            // Flat array
            for (var i = 0; i < mapData.length; i++) {
                var v = mapData[i]
                if (v < min) min = v
                if (v > max) max = v
            }
        }

        minValue = min
        maxValue = max
    }

    function valueToColor(value) {
        var colors = colormaps[colormap] || colormaps["viridis"]
        var numColors = colors.length

        var range = maxValue - minValue
        if (range === 0) range = 1

        var t = (value - minValue) / range
        t = Math.max(0, Math.min(1, t))
        if (invertColormap) t = 1 - t

        var colorIndex = Math.floor(t * (numColors - 1))
        return colors[Math.min(colorIndex, numColors - 1)]
    }

    function formatValue(value) {
        if (Math.abs(value) < 0.001 || Math.abs(value) >= 10000) {
            return value.toExponential(2)
        }
        return value.toFixed(3)
    }

    function setMapData(data, width, height, name) {
        mapData = data
        mapWidth = width
        mapHeight = height
        mapName = name || "Map"
        entityTitle = mapName

        if (autoRange) {
            calculateRange()
        }

        refresh()
    }

    function setFlatData(flatArray, width, height, name) {
        mapData = flatArray
        mapWidth = width
        mapHeight = height
        mapName = name || "Map"
        entityTitle = mapName

        if (autoRange) {
            calculateRange()
        }

        refresh()
    }

    function refresh() {
        if (contentItem) {
            contentItem.children[0].requestPaint()  // mapCanvas
            if (showColorbar) {
                // Find colorbar canvas
                var colorbarArea = contentItem.children[1]
                if (colorbarArea && colorbarArea.children[0]) {
                    colorbarArea.children[0].requestPaint()
                }
            }
        }
    }

    function clearMap() {
        mapData = []
        mapWidth = 0
        mapHeight = 0
        selectedX = -1
        selectedY = -1
        refresh()
    }

    // Repaint when properties change
    onColormapChanged: refresh()
    onInvertColormapChanged: refresh()
    onMinValueChanged: refresh()
    onMaxValueChanged: refresh()

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.mapData !== undefined) mapData = entityData.mapData
            if (entityData.mapWidth !== undefined) mapWidth = entityData.mapWidth
            if (entityData.mapHeight !== undefined) mapHeight = entityData.mapHeight
            if (entityData.colormap) colormap = entityData.colormap
            if (entityData.mapName) mapName = entityData.mapName
            refresh()
        }
    }

    Component.onCompleted: {
        console.log("MapEntity created:", entityId)
        // Apply initial data if present
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.mapData !== undefined) {
                setMapData(entityData.mapData, entityData.mapWidth || 0, entityData.mapHeight || 0, entityData.mapName || "Map")
            }
        }
    }
}
