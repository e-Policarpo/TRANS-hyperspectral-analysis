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
    // Renamed from ``backend`` to ``appBackend`` to avoid the QML
    // self-reference trap when callers write ``backend: backend`` (the RHS
    // resolves to the not-yet-initialized local property = null).
    property var appBackend: null
    // Backwards-compatibility alias — anything still reading
    // ``windowManager.backend`` keeps working.
    property alias backend: windowManager.appBackend

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

        // Add to registry. ``datasetName`` is the dataset identity a graph
        // window represents (defaults to the title; overridden for dataset
        // windows) so tool results can be routed back to the right window.
        windows.push({
            id: windowId,
            window: window,
            type: windowType,
            title: title,
            datasetName: title || ""
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

        // Remember which dataset this window represents (for routing tool
        // results back to it). Defaults to the title when not specified.
        for (var wi = 0; wi < windows.length; wi++) {
            if (windows[wi].id === windowId) {
                windows[wi].datasetName = windowConfig.datasetName || title || ""
                break
            }
        }

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
        // Jump-to-front when the same table is already open.
        var existing = findWindowByTitle("table", title)
        if (existing) {
            // Refresh the model in case the dataset content was updated.
            var winInfo = getWindow(existing)
            if (winInfo && winInfo.window && winInfo.window.contentItem &&
                config && config.tableModel) {
                winInfo.window.contentItem.tableModel = config.tableModel
            }
            activateWindow(existing)
            return existing
        }
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
            if (!content) {
                console.warn("applyTableConfig: content is null")
                return
            }
            content.entityId = windowId
            if (config && config.tableModel) {
                content.tableModel = config.tableModel
                console.log("Table model set on content: rows=" + config.tableModel.rows + " cols=" + config.tableModel.columns)
            } else {
                console.warn("applyTableConfig: no tableModel in config")
            }
        }

        // Get the window and set up the content (defer if Loader hasn't finished)
        var windowInfo = getWindow(windowId)
        if (windowInfo && windowInfo.window) {
            var win = windowInfo.window
            if (win.contentItem) {
                console.log("Table content available immediately")
                applyTableConfig(win.contentItem)
            } else {
                console.log("Table content not yet loaded, deferring...")
                win.contentItemChanged.connect(function() {
                    if (win.contentItem) {
                        console.log("Table content now available (deferred)")
                        applyTableConfig(win.contentItem)
                    }
                })
            }
        } else {
            console.warn("createEnhancedTableWindow: window not found for id " + windowId)
        }

        return windowId
    }

    // Open an embedded text-viewer window for a note entity. Notes are
    // identified by their title (multiple notes with the same title bring
    // an existing window to the front instead of duplicating).
    function openNoteWindow(title, text, source) {
        var existing = findWindowByTitle("note", title)
        if (existing) {
            var info = getWindow(existing)
            if (info && info.window && info.window.contentItem) {
                info.window.contentItem.noteText = text || ""
                info.window.contentItem.noteSource = source || ""
            }
            activateWindow(existing)
            return existing
        }
        var noteContent = Qt.createComponent("NoteWindowContent.qml")
        if (noteContent.status === Component.Error) {
            console.error("Failed to load NoteWindowContent:", noteContent.errorString())
            return null
        }
        var windowConfig = { width: 520, height: 320 }
        var windowId = createWindow("note", title || "Note", noteContent, windowConfig)
        function applyNoteConfig(content) {
            if (!content) return
            content.entityId = windowId
            content.noteTitle = title || "Note"
            content.noteText = text || ""
            content.noteSource = source || ""
        }
        var winInfo = getWindow(windowId)
        if (winInfo && winInfo.window) {
            var win = winInfo.window
            if (win.contentItem) {
                applyNoteConfig(win.contentItem)
            } else {
                win.contentItemChanged.connect(function() {
                    if (win.contentItem) applyNoteConfig(win.contentItem)
                })
            }
        }
        return windowId
    }

    // Open an embedded image-viewer window for the given image entity id.
    // Loaded lazily so the canvas widget only initializes when used.
    // If a window already shows this image, activate it instead of creating
    // a new one.
    function openImageWindow(title, imageId) {
        var existing = findImageWindowById(imageId)
        if (existing) {
            activateWindow(existing)
            return existing
        }
        var imgContent = Qt.createComponent("ImageWindowContent.qml")
        if (imgContent.status === Component.Error) {
            console.error("Failed to load ImageWindowContent:", imgContent.errorString())
            return null
        }
        var windowConfig = { width: 760, height: 480 }
        var windowId = createWindow("image", title || "Image", imgContent, windowConfig)

        function applyImageConfig(content) {
            if (!content) return
            content.entityId = windowId
            // Wire the backend explicitly — the EmbeddedWindow loader's
            // own ``item.backend = …`` only fires when WindowManager.appBackend
            // is non-null, and we want the canvas to be able to call
            // backend.getImage(...) regardless. ``appBackend`` is initialized
            // in ApplicationWindow.Component.onCompleted (Main.qml).
            content.appBackend = appBackend
            content.imageId = imageId
        }

        var windowInfo = getWindow(windowId)
        if (windowInfo && windowInfo.window) {
            var win = windowInfo.window
            if (win.contentItem) {
                applyImageConfig(win.contentItem)
            } else {
                win.contentItemChanged.connect(function() {
                    if (win.contentItem) applyImageConfig(win.contentItem)
                })
            }
        }
        return windowId
    }

    // Convenience: open a graph window with curve data directly. When a graph
    // window with the same title already exists, refresh its curves and bring
    // it to the front instead of creating a duplicate.
    function openGraphWindow(title, curves, xLabel, yLabel, datasetName) {
        var existing = findWindowByTitle("graph", title)
        if (existing) {
            updateGraphWindow(existing, title, curves, xLabel, yLabel)
            return existing
        }
        return createEnhancedGraphWindow(title, {
            curves: curves,
            xLabel: xLabel || "X",
            yLabel: yLabel || "Y",
            datasetName: datasetName || title
        })
    }

    // Find the graph window representing the given dataset (by stable
    // dataset identity, not just visible title). Returns the window id or "".
    function findGraphWindowByDataset(datasetName) {
        if (!datasetName) return ""
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i]
            if (w.type === "graph" && w.window && w.datasetName === datasetName) {
                return w.id
            }
        }
        return ""
    }

    // Append curves to an existing graph window (without clearing the
    // current ones) and frame the data. Used to overlay tool results.
    function addCurvesToGraphWindow(windowId, curves) {
        var info = getWindow(windowId)
        if (!info || !info.window) return false
        var win = info.window

        function doAdd(content) {
            if (content && typeof content.addCurvesAndFit === "function") {
                content.addCurvesAndFit(curves)
            }
        }

        if (win.contentItem) {
            doAdd(win.contentItem)
        } else {
            win.contentItemChanged.connect(function() {
                if (win.contentItem) doAdd(win.contentItem)
            })
        }
        activateWindow(windowId)
        return true
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

    // Find an open window of the given ``type`` whose title matches ``title``,
    // or whose content item has matching ``contentKey`` properties. Returns
    // the window id, or "" when nothing matches. Used by openGraphWindow /
    // openImageWindow / createEnhancedTableWindow to bring an already-open
    // window to the front instead of creating a duplicate.
    function findWindowByTitle(type, title) {
        if (!title) return ""
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i]
            if (w.type !== type) continue
            if (w.window && w.window.windowTitle === title) {
                return w.id
            }
        }
        return ""
    }

    // Find an image window already showing the given image entity id.
    function findImageWindowById(imageId) {
        if (!imageId) return ""
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i]
            if (w.type !== "image") continue
            if (w.window && w.window.contentItem &&
                w.window.contentItem.imageId === imageId) {
                return w.id
            }
        }
        return ""
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
                    // Persist the legend's anchor / offset / hidden-
                    // curves payload so the next session opens with
                    // the user's positioning intact. Falls back to
                    // ``null`` when the canvas isn't reachable yet
                    // (window mid-construction) — the loader will
                    // default to the LegendBox constructor anchor.
                    if (content.graphCanvas
                            && content.graphCanvas.getLegendState) {
                        state.legendState = content.graphCanvas.getLegendState()
                    } else if (content.canvas
                            && content.canvas.getLegendState) {
                        state.legendState = content.canvas.getLegendState()
                    }
                } else if (w.type === "table") {
                    // The TableWindowContent owns a TableDataModel (Python
                    // object); pull cells + column names through its slots so
                    // the saved state actually contains the table data —
                    // earlier versions saved nonexistent ``content.headers``
                    // / ``content.dataRows`` and reloaded with empty cells.
                    if (content.tableModel) {
                        state.headers = content.tableModel.getColumnNames() || []
                        state.dataRows = content.tableModel.toList() || []
                    } else {
                        state.headers = []
                        state.dataRows = []
                    }
                } else if (w.type === "image") {
                    state.imageId = content.imageId || ""
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
