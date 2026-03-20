/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * WindowManager - Manages embedded windows within a workspace
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: windowManager

    // Window registry
    property var windows: []
    property string activeWindowId: ""
    property int nextWindowId: 1
    property int baseZ: 100

    // Backend reference to pass to tool windows
    property var backend: null

    // Theme colors
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Signals
    signal windowOpened(string windowId, string windowType)
    signal windowClosed(string windowId)
    signal windowActivated(string windowId)

    // Content bounds tracking for scrollable workspace
    property real contentNeededWidth: width
    property real contentNeededHeight: height

    // Scrollable workspace container
    Flickable {
        id: windowFlickable
        anchors.fill: parent
        contentWidth: Math.max(width, windowManager.contentNeededWidth)
        contentHeight: Math.max(height, windowManager.contentNeededHeight)
        clip: true
        interactive: false  // Windows handle their own dragging
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AlwaysOn }
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AlwaysOn }

        Item {
            id: windowContainer
            width: windowFlickable.contentWidth
            height: windowFlickable.contentHeight

            // Background wheel handler for scrolling (below windows in z-order)
            MouseArea {
                anchors.fill: parent
                z: -1
                acceptedButtons: Qt.NoButton

                onWheel: function(wheel) {
                    var maxScrollX = Math.max(0, windowFlickable.contentWidth - windowFlickable.width)
                    var maxScrollY = Math.max(0, windowFlickable.contentHeight - windowFlickable.height)

                    if (maxScrollY > 0 || maxScrollX > 0) {
                        windowFlickable.contentY = Math.max(0, Math.min(maxScrollY,
                            windowFlickable.contentY - wheel.angleDelta.y * 0.5))
                        windowFlickable.contentX = Math.max(0, Math.min(maxScrollX,
                            windowFlickable.contentX - wheel.angleDelta.x * 0.5))
                        wheel.accepted = true
                    } else {
                        wheel.accepted = false
                    }
                }
            }
        }
    }

    // Cached EmbeddedWindow component - preload on creation
    property var embeddedWindowComponent: null

    Component.onCompleted: {
        // Preload EmbeddedWindow component
        embeddedWindowComponent = Qt.createComponent("EmbeddedWindow.qml")
        if (embeddedWindowComponent.status === Component.Error) {
            console.error("Failed to preload EmbeddedWindow:", embeddedWindowComponent.errorString())
        } else {
            console.log("WindowManager ready, EmbeddedWindow preloaded")
        }
    }

    // Window creation functions
    function createWindow(windowType, title, contentComponent, config) {
        var windowId = "window_" + nextWindowId++
        var props = config || {}

        // Load EmbeddedWindow component once and cache it
        if (!embeddedWindowComponent) {
            embeddedWindowComponent = Qt.createComponent("EmbeddedWindow.qml")
        }

        var component = embeddedWindowComponent

        if (component.status === Component.Loading) {
            console.log("EmbeddedWindow component still loading...")
            // Wait for it to finish
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    finishCreateWindow(windowId, windowType, title, contentComponent, props)
                } else if (component.status === Component.Error) {
                    console.error("Failed to load EmbeddedWindow:", component.errorString())
                }
            })
            return windowId  // Return ID, window will be created when component is ready
        }

        if (component.status === Component.Error) {
            console.error("Failed to load EmbeddedWindow component:", component.errorString())
            return null
        }

        if (component.status === Component.Ready) {
            return finishCreateWindow(windowId, windowType, title, contentComponent, props)
        }

        console.error("Unexpected component status:", component.status)
        return null
    }

    function finishCreateWindow(windowId, windowType, title, contentComponent, props) {
        console.log("Creating embedded window:", windowId, windowType, title)

        var window = embeddedWindowComponent.createObject(windowContainer, {
            "windowId": windowId,
            "windowTitle": title || "Window",
            "windowType": windowType || "generic",
            "contentComponent": contentComponent,
            "previousX": windowFlickable.contentX + (props.x || 50 + (windows.length * 30) % 200),
            "previousY": windowFlickable.contentY + (props.y || 50 + (windows.length * 30) % 150),
            "previousWidth": props.width || 500,
            "previousHeight": props.height || 400,
            "baseZ": baseZ + windows.length,
            "backend": windowManager.backend,
            "viewportWidth": Qt.binding(function() { return windowFlickable.width }),
            "viewportHeight": Qt.binding(function() { return windowFlickable.height }),
            "viewportX": Qt.binding(function() { return windowFlickable.contentX }),
            "viewportY": Qt.binding(function() { return windowFlickable.contentY })
        })

        if (!window) {
            console.error("Failed to create EmbeddedWindow object")
            return null
        }

        // Connect signals
        window.closed.connect(function() {
            closeWindow(windowId)
        })

        window.activated.connect(function() {
            activateWindow(windowId)
        })

        window.stateChanged.connect(function(newState) {
            handleWindowStateChange(windowId, newState)
        })

        window.windowMoved.connect(function() {
            updateContentBounds()
        })

        window.windowResized.connect(function() {
            updateContentBounds()
        })

        // Add to registry
        windows.push({
            id: windowId,
            window: window,
            type: windowType,
            title: title
        })

        // Activate the new window
        activateWindow(windowId)

        windowOpened(windowId, windowType)
        updateContentBounds()
        console.log("Embedded window created successfully:", windowId)
        return windowId
    }

    function createToolWindow(toolName, contentComponent, config) {
        return createWindow("tool", toolName, contentComponent, config)
    }

    function createGraphWindow(title, contentComponent, config) {
        return createWindow("graph", title, contentComponent, config)
    }

    function createTableWindow(title, contentComponent, config) {
        return createWindow("table", title, contentComponent, config)
    }

    function createImageWindow(title, contentComponent, config) {
        return createWindow("image", title, contentComponent, config)
    }

    // Enhanced window creation using new content components
    function createEnhancedGraphWindow(title, config) {
        var graphContent = Qt.createComponent("GraphWindowContent.qml")
        if (graphContent.status === Component.Error) {
            console.error("Failed to load GraphWindowContent:", graphContent.errorString())
            return null
        }

        var windowConfig = config || {}
        windowConfig.width = windowConfig.width || 600
        windowConfig.height = windowConfig.height || 450

        var windowId = createWindow("graph", title || "Graph", graphContent, windowConfig)

        // Apply config to the content item (curves, labels, etc.)
        function applyGraphConfig(content) {
            if (!content) return
            content.entityId = windowId
            if (content.hasOwnProperty("graphTitle"))
                content.graphTitle = title || "Graph"
            if (config && config.curves)
                content.curves = config.curves
            if (config && config.xLabel)
                content.xLabel = config.xLabel
            if (config && config.yLabel)
                content.yLabel = config.yLabel
        }

        // Get the window and set up the content (defer if Loader hasn't finished)
        var windowInfo = getWindow(windowId)
        if (windowInfo && windowInfo.window) {
            var win = windowInfo.window
            if (win.contentItem) {
                applyGraphConfig(win.contentItem)
            } else {
                // Content not loaded yet — defer until Loader finishes
                win.contentItemChanged.connect(function() {
                    if (win.contentItem) {
                        applyGraphConfig(win.contentItem)
                    }
                })
            }
        }

        return windowId
    }

    function createEnhancedTableWindow(title, config) {
        var tableContent = Qt.createComponent("TableWindowContent.qml")
        if (tableContent.status === Component.Error) {
            console.error("Failed to load TableWindowContent:", tableContent.errorString())
            return null
        }

        var windowConfig = config || {}
        windowConfig.width = windowConfig.width || 650
        windowConfig.height = windowConfig.height || 500

        var windowId = createWindow("table", title || "Table", tableContent, windowConfig)

        // Apply config to the content item
        function applyTableConfig(content) {
            if (!content) return
            content.entityId = windowId
            if (config && config.dataRows)
                content.dataRows = config.dataRows
            if (config && config.headers)
                content.headers = config.headers
        }

        // Get the window and set up the content (defer if Loader hasn't finished)
        var windowInfo = getWindow(windowId)
        if (windowInfo && windowInfo.window) {
            var win = windowInfo.window
            if (win.contentItem) {
                applyTableConfig(win.contentItem)
            } else {
                win.contentItemChanged.connect(function() {
                    if (win.contentItem) {
                        applyTableConfig(win.contentItem)
                    }
                })
            }
        }

        return windowId
    }

    // Convenience: open a graph window with curve data directly
    function openGraphWindow(title, curves, xLabel, yLabel) {
        return createEnhancedGraphWindow(title, {
            curves: curves,
            xLabel: xLabel || "X",
            yLabel: yLabel || "Y"
        })
    }

    // Update an existing graph window's curves (for reuse instead of creating new)
    function updateGraphWindow(windowId, title, curves, xLabel, yLabel) {
        var windowInfo = getWindow(windowId)
        if (!windowInfo || !windowInfo.window) return false

        var win = windowInfo.window
        win.windowTitle = title || win.windowTitle

        function doUpdate(content) {
            if (!content) return
            // Clear old curves and set new ones
            content.curves = curves || []
            if (xLabel) content.xLabel = xLabel
            if (yLabel) content.yLabel = yLabel
        }

        if (win.contentItem) {
            doUpdate(win.contentItem)
        } else {
            win.contentItemChanged.connect(function() {
                if (win.contentItem) doUpdate(win.contentItem)
            })
        }

        // Bring to front
        activateWindow(windowId)
        return true
    }

    // Check if a window exists and is valid
    function hasWindow(windowId) {
        return windowId && getWindow(windowId) !== null
    }

    // Link a table window to a graph window
    function linkTableToGraph(tableWindowId, graphWindowId) {
        var tableInfo = getWindow(tableWindowId)
        var graphInfo = getWindow(graphWindowId)

        if (tableInfo && tableInfo.window && tableInfo.window.contentItem) {
            tableInfo.window.contentItem.linkedGraphId = graphWindowId
        }
        if (graphInfo && graphInfo.window && graphInfo.window.contentItem) {
            graphInfo.window.contentItem.linkedTableId = tableWindowId
        }

        // Also register with backend
        if (backend) {
            backend.linkTableToGraph(tableWindowId, graphWindowId)
        }

        console.log("Linked table", tableWindowId, "to graph", graphWindowId)
    }

    // Window management functions
    function closeWindow(windowId) {
        // Find and destroy window
        for (var j = windows.length - 1; j >= 0; j--) {
            if (windows[j].id === windowId) {
                windows[j].window.destroy()
                windows.splice(j, 1)
                break
            }
        }

        // Activate next window if this was active
        if (activeWindowId === windowId) {
            activeWindowId = ""
            if (windows.length > 0) {
                activateWindow(windows[windows.length - 1].id)
            }
        }

        windowClosed(windowId)
        updateContentBounds()
    }

    function activateWindow(windowId) {
        // Deactivate current
        if (activeWindowId !== "") {
            var currentWindow = getWindow(activeWindowId)
            if (currentWindow) {
                currentWindow.window.isActive = false
            }
        }

        // Activate new
        activeWindowId = windowId
        var newWindow = getWindow(windowId)
        if (newWindow) {
            newWindow.window.isActive = true
            // Bring to front by updating z
            for (var i = 0; i < windows.length; i++) {
                if (windows[i].id === windowId) {
                    windows[i].window.baseZ = baseZ + 1000
                } else {
                    windows[i].window.baseZ = baseZ + i
                }
            }
        }

        windowActivated(windowId)
    }

    function minimizeWindow(windowId) {
        var windowInfo = getWindow(windowId)
        if (windowInfo) {
            windowInfo.window.minimize()
        }
    }

    function maximizeWindow(windowId) {
        var windowInfo = getWindow(windowId)
        if (windowInfo) {
            windowInfo.window.maximize()
        }
    }

    function restoreWindow(windowId) {
        var windowInfo = getWindow(windowId)
        if (windowInfo) {
            windowInfo.window.restore()
            activateWindow(windowId)
        }
    }

    function handleWindowStateChange(windowId, newState) {
        // Windows now collapse in place when minimized - no separate tracking needed
        // Just log for debugging
        var stateName = newState === 0 ? "Windowed" : (newState === 1 ? "Fullscreen" : "Minimized")
        console.log("Window", windowId, "state changed to:", stateName)
    }

    function getWindow(windowId) {
        for (var i = 0; i < windows.length; i++) {
            if (windows[i].id === windowId) {
                return windows[i]
            }
        }
        return null
    }

    function closeAllWindows() {
        while (windows.length > 0) {
            closeWindow(windows[0].id)
        }
    }

    function getWindowCount() {
        return windows.length
    }

    function getActiveWindow() {
        return getWindow(activeWindowId)
    }

    function getWindowStates() {
        var states = []
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i]
            var win = w.window
            var state = {
                id: w.id,
                type: w.type,
                title: w.title,
                x: win.x,
                y: win.y,
                width: win.width,
                height: win.height
            }
            // Extract content data if available
            if (win.contentItem) {
                var content = win.contentItem
                if (w.type === "graph") {
                    state.curves = content.curves || []
                    state.xLabel = content.xLabel || ""
                    state.yLabel = content.yLabel || ""
                } else if (w.type === "table") {
                    state.headers = content.headers || []
                    state.dataRows = content.dataRows || []
                }
            }
            states.push(state)
        }
        return states
    }

    // Tile windows within visible viewport
    function tileWindows() {
        var visibleWindows = windows.filter(function(w) {
            return w.window.windowState !== 2 // Not minimized
        })

        if (visibleWindows.length === 0) return

        var cols = Math.ceil(Math.sqrt(visibleWindows.length))
        var rows = Math.ceil(visibleWindows.length / cols)
        var winWidth = windowFlickable.width / cols
        var winHeight = windowFlickable.height / rows

        for (var i = 0; i < visibleWindows.length; i++) {
            var row = Math.floor(i / cols)
            var col = i % cols
            var win = visibleWindows[i].window

            win.windowState = 0 // Windowed
            win.previousX = col * winWidth
            win.previousY = row * winHeight
            win.previousWidth = winWidth
            win.previousHeight = winHeight
        }

        windowFlickable.contentX = 0
        windowFlickable.contentY = 0
        updateContentBounds()
    }

    // Cascade windows within visible viewport
    function cascadeWindows() {
        var offset = 30
        for (var i = 0; i < windows.length; i++) {
            var win = windows[i].window
            if (win.windowState === 2) continue // Skip minimized

            win.windowState = 0 // Windowed
            win.previousX = offset + i * offset
            win.previousY = offset + i * offset
            win.previousWidth = windowFlickable.width * 0.6
            win.previousHeight = windowFlickable.height * 0.6
        }

        windowFlickable.contentX = 0
        windowFlickable.contentY = 0
        updateContentBounds()
    }

    // Recalculate content bounds from all window positions
    function updateContentBounds() {
        var maxRight = windowFlickable.width
        var maxBottom = windowFlickable.height

        for (var i = 0; i < windows.length; i++) {
            var w = windows[i].window
            if (w) {
                var right = w.previousX + w.previousWidth + 20
                var bottom = w.previousY + w.previousHeight + 20
                if (right > maxRight) maxRight = right
                if (bottom > maxBottom) maxBottom = bottom
            }
        }

        contentNeededWidth = maxRight
        contentNeededHeight = maxBottom
    }
}
