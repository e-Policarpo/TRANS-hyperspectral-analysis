/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * UnifiedWorkspace - Main tileable workspace with dockable panels
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../workflow"

Rectangle {
    id: unifiedWorkspace

    // Current workspace mode: "sts", "snom", "map", "workflow"
    property string currentMode: "sts"

    // External references needed for mode-specific panels
    property var backend: null
    property var workflowManager: null

    // Panel visibility per mode (can be overridden)
    property bool showLeftPanel: true
    property bool showRightPanel: false
    property bool showTopPanel: false
    property bool showBottomPanel: false

    // Panel collapsed states
    property bool leftCollapsed: false
    property bool rightCollapsed: false
    property bool topCollapsed: false
    property bool bottomCollapsed: false

    // Panel sizes (persisted)
    property real leftPanelWidth: 280
    property real rightPanelWidth: 300
    property real topPanelHeight: 200
    property real bottomPanelHeight: 200

    // Components to load in panels (set by parent or auto-configured by mode)
    property Component leftPanelContent: null
    property Component rightPanelContent: null
    property Component topPanelContent: null
    property Component bottomPanelContent: null
    property Component centerContent: null

    // Mode-specific default panel components
    property Component projectBrowserComponent: null  // Set by parent (Main.qml)
    property Component toolPaletteComponent: Component {
        WorkflowToolPalette {
            workflowManager: unifiedWorkspace.workflowManager
        }
    }
    property Component workflowCanvasComponent: Component {
        WorkflowCanvas {
            id: embeddedWorkflowCanvas
            workflowManager: unifiedWorkspace.workflowManager

            onNodeSelected: function(node) {
                console.log("Workflow node selected:", node.id)
            }

            onStatusMessage: function(message, messageColor) {
                console.log("Workflow:", message)
            }
        }
    }

    // Auto-configure panels based on mode
    onCurrentModeChanged: {
        configurePanelsForMode(currentMode)
    }

    function configurePanelsForMode(mode) {
        switch(mode) {
            case "workflow":
                // Workflow mode: ToolPalette on left, WorkflowCanvas in center
                showLeftPanel = true
                showRightPanel = true  // For NodeParameterEditor
                leftPanelContent = toolPaletteComponent
                centerContent = workflowCanvasComponent
                break

            case "sts":
            case "snom":
                // STS/SNOM: ProjectBrowser on left (if provided)
                showLeftPanel = projectBrowserComponent !== null
                showRightPanel = false
                leftPanelContent = projectBrowserComponent
                centerContent = null
                break

            case "map":
                // Map mode: handled by MapEditorWorkstation externally
                showLeftPanel = false
                showRightPanel = false
                centerContent = null
                break

            default:
                showLeftPanel = projectBrowserComponent !== null
                showRightPanel = false
                leftPanelContent = projectBrowserComponent
                centerContent = null
        }
    }

    // Canvas background style based on mode
    property string canvasBackground: {
        switch(currentMode) {
            case "workflow": return "workflow"
            case "map": return "none"
            default: return "dotted"
        }
    }

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
    signal modeChanged(string newMode)
    signal layoutChanged()
    signal floatingEntityAdded(var entity)
    signal floatingEntityRemoved(string entityId)

    color: bgDark

    // Floating entities model
    ListModel {
        id: floatingEntitiesModel
    }

    // Access to child components
    property alias canvas: centerCanvas
    property alias leftPanel: leftDockPanel
    property alias rightPanel: rightDockPanel
    property alias topPanel: topDockPanel
    property alias bottomPanel: bottomDockPanel
    property alias floatingEntities: floatingEntitiesModel

    // Main layout structure
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Top panel (optional)
        DockPanel {
            id: topDockPanel
            Layout.fillWidth: true
            Layout.preferredHeight: showTopPanel && !topCollapsed ? topPanelHeight : (showTopPanel ? 32 : 0)
            visible: showTopPanel
            position: "top"
            collapsed: topCollapsed
            preferredSize: topPanelHeight
            minimumSize: 100
            maximumSize: 400

            onCollapseToggled: function(collapsed) {
                topCollapsed = collapsed
                layoutChanged()
            }

            onPanelResized: function(newSize) {
                topPanelHeight = newSize
                layoutChanged()
            }

            Component.onCompleted: {
                if (topPanelContent) {
                    setContent(topPanelContent)
                }
            }
        }

        // Middle row: Left panel + Center + Right panel
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Left panel
            DockPanel {
                id: leftDockPanel
                Layout.preferredWidth: showLeftPanel && !leftCollapsed ? leftPanelWidth : (showLeftPanel ? 32 : 0)
                Layout.fillHeight: true
                visible: showLeftPanel
                position: "left"
                collapsed: leftCollapsed
                preferredSize: leftPanelWidth
                minimumSize: 150
                maximumSize: 500

                onCollapseToggled: function(collapsed) {
                    leftCollapsed = collapsed
                    layoutChanged()
                }

                onPanelResized: function(newSize) {
                    leftPanelWidth = newSize
                    layoutChanged()
                }

                Component.onCompleted: {
                    if (leftPanelContent) {
                        setContent(leftPanelContent)
                    }
                }
            }

            // Center workspace canvas
            WorkspaceCanvas {
                id: centerCanvas
                Layout.fillWidth: true
                Layout.fillHeight: true
                backgroundStyle: canvasBackground

                // Content loader for mode-specific content
                Loader {
                    id: centerContentLoader
                    anchors.fill: parent
                    sourceComponent: centerContent
                }

                // Floating entities layer
                Repeater {
                    model: floatingEntitiesModel

                    delegate: Item {
                        id: floatingEntityWrapper
                        x: model.entityX || 100
                        y: model.entityY || 100
                        width: model.entityWidth || 400
                        height: model.entityHeight || 300
                        z: model.zOrder || 0

                        // Entity content loaded via Loader
                        Loader {
                            id: entityLoader
                            anchors.fill: parent
                            sourceComponent: model.entityComponent

                            onLoaded: {
                                if (item) {
                                    // Pass entity data to loaded item
                                    if (item.hasOwnProperty("entityId")) {
                                        item.entityId = model.entityId
                                    }
                                    if (item.hasOwnProperty("entityData")) {
                                        item.entityData = model.entityData
                                    }
                                }
                            }
                        }

                        // Drag handling for floating entities
                        MouseArea {
                            id: entityDragArea
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            height: 30  // Title bar area
                            z: 1

                            property bool isDragging: false
                            property real startX: 0
                            property real startY: 0
                            property real entityStartX: 0
                            property real entityStartY: 0

                            onPressed: function(mouse) {
                                isDragging = true
                                startX = mouse.x
                                startY = mouse.y
                                entityStartX = floatingEntityWrapper.x
                                entityStartY = floatingEntityWrapper.y

                                // Bring to front
                                bringEntityToFront(model.entityId)
                            }

                            onReleased: {
                                isDragging = false
                            }

                            onPositionChanged: function(mouse) {
                                if (isDragging) {
                                    var newX = entityStartX + (mouse.x - startX)
                                    var newY = entityStartY + (mouse.y - startY)

                                    // Constrain to canvas bounds
                                    newX = Math.max(0, Math.min(centerCanvas.width - floatingEntityWrapper.width, newX))
                                    newY = Math.max(0, Math.min(centerCanvas.height - floatingEntityWrapper.height, newY))

                                    floatingEntityWrapper.x = newX
                                    floatingEntityWrapper.y = newY

                                    // Update model
                                    floatingEntitiesModel.setProperty(model.index, "entityX", newX)
                                    floatingEntitiesModel.setProperty(model.index, "entityY", newY)
                                }
                            }
                        }
                    }
                }

                // Canvas click handling
                onCanvasClicked: function(x, y, button) {
                    // Deselect floating entities when clicking canvas
                    console.log("Canvas clicked at:", x, y)
                }
            }

            // Right panel
            DockPanel {
                id: rightDockPanel
                Layout.preferredWidth: showRightPanel && !rightCollapsed ? rightPanelWidth : (showRightPanel ? 32 : 0)
                Layout.fillHeight: true
                visible: showRightPanel
                position: "right"
                collapsed: rightCollapsed
                preferredSize: rightPanelWidth
                minimumSize: 200
                maximumSize: 600

                onCollapseToggled: function(collapsed) {
                    rightCollapsed = collapsed
                    layoutChanged()
                }

                onPanelResized: function(newSize) {
                    rightPanelWidth = newSize
                    layoutChanged()
                }

                Component.onCompleted: {
                    if (rightPanelContent) {
                        setContent(rightPanelContent)
                    }
                }
            }
        }

        // Bottom panel (optional)
        DockPanel {
            id: bottomDockPanel
            Layout.fillWidth: true
            Layout.preferredHeight: showBottomPanel && !bottomCollapsed ? bottomPanelHeight : (showBottomPanel ? 32 : 0)
            visible: showBottomPanel
            position: "bottom"
            collapsed: bottomCollapsed
            preferredSize: bottomPanelHeight
            minimumSize: 100
            maximumSize: 400

            onCollapseToggled: function(collapsed) {
                bottomCollapsed = collapsed
                layoutChanged()
            }

            onPanelResized: function(newSize) {
                bottomPanelHeight = newSize
                layoutChanged()
            }

            Component.onCompleted: {
                if (bottomPanelContent) {
                    setContent(bottomPanelContent)
                }
            }
        }
    }

    // Mode configuration presets
    function applyModePreset(mode) {
        currentMode = mode

        switch(mode) {
            case "sts":
            case "snom":
                showLeftPanel = true
                showRightPanel = false
                showTopPanel = false
                showBottomPanel = false
                break

            case "map":
                showLeftPanel = true
                showRightPanel = true
                showTopPanel = false
                showBottomPanel = false
                break

            case "workflow":
                showLeftPanel = true
                showRightPanel = true
                showTopPanel = false
                showBottomPanel = false
                break

            default:
                showLeftPanel = true
                showRightPanel = false
                showTopPanel = false
                showBottomPanel = false
        }

        modeChanged(mode)
        layoutChanged()
    }

    // Floating entity management
    function addFloatingEntity(entityId, entityType, component, x, y, width, height, data) {
        // Find max z-order
        var maxZ = 0
        for (var i = 0; i < floatingEntitiesModel.count; i++) {
            var z = floatingEntitiesModel.get(i).zOrder || 0
            if (z > maxZ) maxZ = z
        }

        floatingEntitiesModel.append({
            "entityId": entityId,
            "entityType": entityType,
            "entityComponent": component,
            "entityX": x || 100,
            "entityY": y || 100,
            "entityWidth": width || 400,
            "entityHeight": height || 300,
            "entityData": data || {},
            "zOrder": maxZ + 1
        })

        floatingEntityAdded({ id: entityId, type: entityType })
        return floatingEntitiesModel.count - 1
    }

    function removeFloatingEntity(entityId) {
        for (var i = 0; i < floatingEntitiesModel.count; i++) {
            if (floatingEntitiesModel.get(i).entityId === entityId) {
                floatingEntitiesModel.remove(i)
                floatingEntityRemoved(entityId)
                return true
            }
        }
        return false
    }

    function bringEntityToFront(entityId) {
        // Find max z-order and the entity
        var maxZ = 0
        var entityIndex = -1

        for (var i = 0; i < floatingEntitiesModel.count; i++) {
            var item = floatingEntitiesModel.get(i)
            if (item.zOrder > maxZ) maxZ = item.zOrder
            if (item.entityId === entityId) entityIndex = i
        }

        if (entityIndex >= 0) {
            floatingEntitiesModel.setProperty(entityIndex, "zOrder", maxZ + 1)
        }
    }

    function getFloatingEntity(entityId) {
        for (var i = 0; i < floatingEntitiesModel.count; i++) {
            if (floatingEntitiesModel.get(i).entityId === entityId) {
                return floatingEntitiesModel.get(i)
            }
        }
        return null
    }

    function clearFloatingEntities() {
        while (floatingEntitiesModel.count > 0) {
            var entityId = floatingEntitiesModel.get(0).entityId
            floatingEntitiesModel.remove(0)
            floatingEntityRemoved(entityId)
        }
    }

    // Entity type components for convenience
    property Component graphEntityComponent: Component {
        GraphEntity {
            id: graphEntityInstance
        }
    }

    property Component tableEntityComponent: Component {
        TableEntity {
            id: tableEntityInstance
        }
    }

    property Component mapEntityComponent: Component {
        MapEntity {
            id: mapEntityInstance
        }
    }

    // Convenience functions for creating specific entity types
    function createGraphEntity(title, x, y, width, height, curves) {
        var entityId = "graph_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = {
            title: title || "Graph",
            curves: curves || []
        }
        var idx = addFloatingEntity(
            entityId, "graph", graphEntityComponent,
            x || 50, y || 50,
            width || 450, height || 350,
            data
        )
        console.log("Created graph entity:", entityId)
        return entityId
    }

    function createTableEntity(title, x, y, width, height, tableData, columnHeaders) {
        var entityId = "table_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = {
            title: title || "Table",
            tableData: tableData || [],
            columnHeaders: columnHeaders || []
        }
        var idx = addFloatingEntity(
            entityId, "table", tableEntityComponent,
            x || 80, y || 80,
            width || 500, height || 400,
            data
        )
        console.log("Created table entity:", entityId)
        return entityId
    }

    function createMapEntity(title, x, y, width, height, mapData, mapWidth, mapHeight) {
        var entityId = "map_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = {
            title: title || "Map",
            mapData: mapData || [],
            mapWidth: mapWidth || 0,
            mapHeight: mapHeight || 0
        }
        var idx = addFloatingEntity(
            entityId, "map", mapEntityComponent,
            x || 100, y || 100,
            width || 400, height || 400,
            data
        )
        console.log("Created map entity:", entityId)
        return entityId
    }

    // Additional entity components
    property Component projectBrowserEntityComponent: Component {
        ProjectBrowserEntity {}
    }

    property Component dataBrowserEntityComponent: Component {
        DataBrowserEntity {}
    }

    property Component pointInspectorEntityComponent: Component {
        PointInspectorEntity {}
    }

    property Component statisticsPanelEntityComponent: Component {
        StatisticsPanelEntity {}
    }

    // Additional entity creation functions
    function createProjectBrowserEntity(backend, x, y, width, height) {
        var entityId = "browser_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = { title: "Project Browser", backend: backend }
        addFloatingEntity(entityId, "browser", projectBrowserEntityComponent, x || 20, y || 20, width || 280, height || 400, data)
        return entityId
    }

    function createDataBrowserEntity(channelNames, activeChannel, x, y, width, height) {
        var entityId = "databrowser_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = { title: "Data Browser", channelNames: channelNames || [], activeChannel: activeChannel || "" }
        addFloatingEntity(entityId, "browser", dataBrowserEntityComponent, x || 50, y || 50, width || 240, height || 300, data)
        return entityId
    }

    function createPointInspectorEntity(hasSpectrum, x, y, width, height) {
        var entityId = "inspector_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = { title: "Point Inspector", hasSpectrum: hasSpectrum || false }
        addFloatingEntity(entityId, "inspector", pointInspectorEntityComponent, x || 70, y || 70, width || 220, height || 180, data)
        return entityId
    }

    function createStatisticsPanelEntity(stats, channelName, x, y, width, height) {
        var entityId = "stats_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9)
        var data = { title: "Statistics", stats: stats || {}, channelName: channelName || "" }
        addFloatingEntity(entityId, "statistics", statisticsPanelEntityComponent, x || 90, y || 90, width || 240, height || 200, data)
        return entityId
    }

    // Layout state management
    function getLayoutState() {
        return {
            mode: currentMode,
            leftPanel: {
                visible: showLeftPanel,
                collapsed: leftCollapsed,
                width: leftPanelWidth
            },
            rightPanel: {
                visible: showRightPanel,
                collapsed: rightCollapsed,
                width: rightPanelWidth
            },
            topPanel: {
                visible: showTopPanel,
                collapsed: topCollapsed,
                height: topPanelHeight
            },
            bottomPanel: {
                visible: showBottomPanel,
                collapsed: bottomCollapsed,
                height: bottomPanelHeight
            },
            canvas: {
                zoom: centerCanvas.zoomLevel,
                panX: centerCanvas.panX,
                panY: centerCanvas.panY
            }
        }
    }

    function restoreLayoutState(state) {
        if (!state) return

        if (state.mode) currentMode = state.mode

        if (state.leftPanel) {
            showLeftPanel = state.leftPanel.visible !== undefined ? state.leftPanel.visible : showLeftPanel
            leftCollapsed = state.leftPanel.collapsed || false
            leftPanelWidth = state.leftPanel.width || 280
        }

        if (state.rightPanel) {
            showRightPanel = state.rightPanel.visible !== undefined ? state.rightPanel.visible : showRightPanel
            rightCollapsed = state.rightPanel.collapsed || false
            rightPanelWidth = state.rightPanel.width || 300
        }

        if (state.topPanel) {
            showTopPanel = state.topPanel.visible !== undefined ? state.topPanel.visible : showTopPanel
            topCollapsed = state.topPanel.collapsed || false
            topPanelHeight = state.topPanel.height || 200
        }

        if (state.bottomPanel) {
            showBottomPanel = state.bottomPanel.visible !== undefined ? state.bottomPanel.visible : showBottomPanel
            bottomCollapsed = state.bottomPanel.collapsed || false
            bottomPanelHeight = state.bottomPanel.height || 200
        }

        if (state.canvas) {
            centerCanvas.zoomLevel = state.canvas.zoom || 1.0
            centerCanvas.panX = state.canvas.panX || 0
            centerCanvas.panY = state.canvas.panY || 0
        }

        layoutChanged()
    }

    Component.onCompleted: {
        console.log("UnifiedWorkspace created, mode:", currentMode)
        applyModePreset(currentMode)
    }
}
