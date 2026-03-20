# Module 7: Advanced UI Patterns

## Workspaces, Dockable Panels, and Embedded Windows

Professional applications need sophisticated UI patterns: dockable panels, floating windows, theme systems, and layout persistence. This module teaches you to build these patterns using QML's declarative power combined with Python backend logic.

---

## Learning Objectives

By the end of this module, you will be able to:
- Create dockable, collapsible panels
- Build an embedded window management system
- Implement theme systems with reactive color bindings
- Design mode-specific workspace layouts
- Handle drag-and-drop for window repositioning
- Save and restore layout state

---

## 7.1 Workspace Architecture

### The Unified Workspace Pattern

TRANS-QML uses a `UnifiedWorkspace` component that provides:
- **Dockable panels** - Left, right, top, bottom edges
- **Floating entities** - Draggable windows within the workspace
- **Embedded windows** - OS-like windows for tools, graphs, tables
- **Mode switching** - Different layouts for different tasks

```
┌──────────────────────────────────────────────────────────┐
│                    Top Panel (optional)                   │
├──────────┬──────────────────────────────────┬────────────┤
│          │                                   │            │
│   Left   │        Center Canvas              │   Right    │
│  Panel   │   ┌───────────┐ ┌───────────┐    │   Panel    │
│          │   │  Window 1 │ │  Window 2 │    │            │
│  Project │   └───────────┘ └───────────┘    │  Inspector │
│  Browser │                                   │            │
│          │         [Floating Entities]       │            │
│          │                                   │            │
├──────────┴──────────────────────────────────┴────────────┤
│                  Bottom Panel (optional)                  │
└──────────────────────────────────────────────────────────┘
```

### Basic Structure

```qml
// UnifiedWorkspace.qml
Rectangle {
    id: unifiedWorkspace

    // Current mode: "sts", "snom", "map", "workflow"
    property string currentMode: "sts"

    // Panel visibility
    property bool showLeftPanel: true
    property bool showRightPanel: false
    property bool showTopPanel: false
    property bool showBottomPanel: false

    // Panel collapsed states
    property bool leftCollapsed: false
    property bool rightCollapsed: false

    // Panel sizes (persisted)
    property real leftPanelWidth: 280
    property real rightPanelWidth: 300

    // Content components (set by parent)
    property Component leftPanelContent: null
    property Component rightPanelContent: null
    property Component centerContent: null

    // Signals
    signal modeChanged(string newMode)
    signal layoutChanged()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Middle row: Left + Center + Right
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Left panel
            DockPanel {
                id: leftDockPanel
                Layout.preferredWidth: showLeftPanel && !leftCollapsed ?
                                       leftPanelWidth : (showLeftPanel ? 32 : 0)
                Layout.fillHeight: true
                visible: showLeftPanel
                position: "left"
                collapsed: leftCollapsed

                onCollapseToggled: (collapsed) => {
                    leftCollapsed = collapsed
                    layoutChanged()
                }
            }

            // Center workspace
            WorkspaceCanvas {
                id: centerCanvas
                Layout.fillWidth: true
                Layout.fillHeight: true

                // WindowManager for embedded windows
                WindowManager {
                    id: embeddedWindowManager
                    anchors.fill: parent
                }
            }

            // Right panel
            DockPanel {
                id: rightDockPanel
                Layout.preferredWidth: showRightPanel && !rightCollapsed ?
                                       rightPanelWidth : (showRightPanel ? 32 : 0)
                Layout.fillHeight: true
                visible: showRightPanel
                position: "right"
            }
        }
    }
}
```

---

## 7.2 Dockable Panels

### The DockPanel Component

A reusable panel that can:
- Collapse to a thin bar
- Be resized by dragging
- Load dynamic content

```qml
// DockPanel.qml
Rectangle {
    id: dockPanel

    property string position: "left"  // "left", "right", "top", "bottom"
    property bool collapsed: false
    property real preferredSize: 250
    property real minimumSize: 150
    property real maximumSize: 500
    property Component contentComponent: null

    signal collapseToggled(bool collapsed)
    signal panelResized(real newSize)

    color: bgMedium
    border.color: borderColor
    border.width: 1

    // Collapse button
    Rectangle {
        id: collapseButton
        width: collapsed ? parent.width : 24
        height: collapsed ? 24 : parent.height
        anchors {
            right: position === "left" ? parent.right : undefined
            left: position === "right" ? parent.left : undefined
            verticalCenter: parent.verticalCenter
        }
        color: collapseArea.containsMouse ? bgLight : "transparent"

        Text {
            anchors.centerIn: parent
            text: getCollapseIcon()
            color: textMuted
            font.pixelSize: 12
        }

        MouseArea {
            id: collapseArea
            anchors.fill: parent
            hoverEnabled: true
            onClicked: {
                collapsed = !collapsed
                collapseToggled(collapsed)
            }
        }

        function getCollapseIcon() {
            if (collapsed) {
                return position === "left" ? "▶" : "◀"
            } else {
                return position === "left" ? "◀" : "▶"
            }
        }
    }

    // Content loader
    Loader {
        id: contentLoader
        anchors.fill: parent
        anchors.rightMargin: position === "left" ? 28 : 4
        anchors.leftMargin: position === "right" ? 28 : 4
        visible: !collapsed
        sourceComponent: contentComponent
    }

    // Resize handle
    Rectangle {
        id: resizeHandle
        width: 6
        height: parent.height
        anchors {
            right: position === "left" ? parent.right : undefined
            left: position === "right" ? parent.left : undefined
        }
        color: resizeArea.containsMouse ? accentBlue : "transparent"
        visible: !collapsed

        MouseArea {
            id: resizeArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SizeHorCursor

            property real startX: 0
            property real startWidth: 0

            onPressed: (mouse) => {
                startX = mouse.x
                startWidth = preferredSize
            }

            onPositionChanged: (mouse) => {
                if (pressed) {
                    var delta = position === "left" ?
                                (mouse.x - startX) : (startX - mouse.x)
                    var newSize = Math.max(minimumSize,
                                          Math.min(maximumSize, startWidth + delta))
                    preferredSize = newSize
                    panelResized(newSize)
                }
            }
        }
    }

    // Set content from parent
    function setContent(component) {
        contentComponent = component
    }
}
```

---

## 7.3 The Window Manager

### Embedded Windows Pattern

TRANS-QML uses an "embedded window" pattern where tool windows appear inside the workspace rather than as OS-level windows. This provides:
- Consistent look and feel
- Pan/zoom with workspace
- Tiling and cascading
- No OS window chrome issues

### Window Manager Structure

```qml
// WindowManager.qml
Item {
    id: windowManager

    property var windows: []
    property string activeWindowId: ""
    property int nextWindowId: 1
    property int baseZ: 100
    property var backend: null

    signal windowOpened(string windowId, string windowType)
    signal windowClosed(string windowId)
    signal windowActivated(string windowId)

    // Container for windows
    Item {
        id: windowContainer
        anchors.fill: parent
    }

    // Preload window component
    property var embeddedWindowComponent: null

    Component.onCompleted: {
        embeddedWindowComponent = Qt.createComponent("EmbeddedWindow.qml")
    }

    function createWindow(windowType, title, contentComponent, config) {
        var windowId = "window_" + nextWindowId++
        var props = config || {}

        var window = embeddedWindowComponent.createObject(windowContainer, {
            "windowId": windowId,
            "windowTitle": title || "Window",
            "windowType": windowType,
            "contentComponent": contentComponent,
            "previousX": props.x || 50 + (windows.length * 30) % 200,
            "previousY": props.y || 50 + (windows.length * 30) % 150,
            "previousWidth": props.width || 500,
            "previousHeight": props.height || 400,
            "baseZ": baseZ + windows.length,
            "backend": backend
        })

        // Connect signals
        window.closed.connect(() => closeWindow(windowId))
        window.activated.connect(() => activateWindow(windowId))

        // Register window
        windows.push({
            id: windowId,
            window: window,
            type: windowType,
            title: title
        })

        activateWindow(windowId)
        windowOpened(windowId, windowType)
        return windowId
    }
}
```

### Specialized Window Creation

```qml
function createToolWindow(toolName, contentComponent, config) {
    return createWindow("tool", toolName, contentComponent, config)
}

function createGraphWindow(title, contentComponent, config) {
    return createWindow("graph", title, contentComponent, {
        width: 650,
        height: 500,
        ...config
    })
}

function createTableWindow(title, contentComponent, config) {
    return createWindow("table", title, contentComponent, {
        width: 600,
        height: 580,
        ...config
    })
}
```

### Window Activation and Z-Order

```qml
function activateWindow(windowId) {
    // Deactivate current
    if (activeWindowId !== "") {
        var current = getWindow(activeWindowId)
        if (current) current.window.isActive = false
    }

    // Activate new
    activeWindowId = windowId
    var newWindow = getWindow(windowId)
    if (newWindow) {
        newWindow.window.isActive = true

        // Bring to front
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
```

### Tiling and Cascading

```qml
function tileWindows() {
    var visibleWindows = windows.filter(w => w.window.windowState !== 2)
    if (visibleWindows.length === 0) return

    var cols = Math.ceil(Math.sqrt(visibleWindows.length))
    var rows = Math.ceil(visibleWindows.length / cols)
    var winWidth = windowContainer.width / cols
    var winHeight = windowContainer.height / rows

    for (var i = 0; i < visibleWindows.length; i++) {
        var row = Math.floor(i / cols)
        var col = i % cols
        var win = visibleWindows[i].window

        win.windowState = 0  // Windowed
        win.previousX = col * winWidth
        win.previousY = row * winHeight
        win.previousWidth = winWidth
        win.previousHeight = winHeight
    }
}

function cascadeWindows() {
    var offset = 30
    for (var i = 0; i < windows.length; i++) {
        var win = windows[i].window
        if (win.windowState === 2) continue  // Skip minimized

        win.windowState = 0
        win.previousX = offset + i * offset
        win.previousY = offset + i * offset
        win.previousWidth = windowContainer.width * 0.6
        win.previousHeight = windowContainer.height * 0.6
    }
}
```

---

## 7.4 Embedded Window Component

### Window States

```qml
// EmbeddedWindow.qml
Rectangle {
    id: embeddedWindow

    // Window identity
    property string windowId: ""
    property string windowTitle: "Window"
    property string windowType: "generic"

    // Window state: 0=Windowed, 1=Fullscreen, 2=Minimized
    property int windowState: 0

    // Position/size when windowed
    property real previousX: 50
    property real previousY: 50
    property real previousWidth: 500
    property real previousHeight: 400

    // Z-ordering
    property int baseZ: 100
    property bool isActive: false

    // Content
    property Component contentComponent: null
    property var backend: null

    signal closed()
    signal activated()
    signal stateChanged(int newState)

    // Computed position/size based on state
    x: windowState === 1 ? 0 : previousX
    y: windowState === 1 ? 0 : previousY
    width: windowState === 1 ? parent.width :
           windowState === 2 ? 200 : previousWidth
    height: windowState === 1 ? parent.height :
            windowState === 2 ? 36 : previousHeight
    z: baseZ + (isActive ? 100 : 0)

    // Visual styling
    color: bgDark
    border.color: isActive ? accentBlue : borderColor
    border.width: isActive ? 2 : 1
    radius: 4
}
```

### Title Bar with Controls

```qml
// Inside EmbeddedWindow
Rectangle {
    id: titleBar
    height: 32
    anchors {
        top: parent.top
        left: parent.left
        right: parent.right
    }
    color: isActive ? "#2a3a4a" : bgMedium
    radius: 4

    // Drag handler
    MouseArea {
        anchors.fill: parent
        property real startX: 0
        property real startY: 0

        onPressed: (mouse) => {
            startX = mouse.x
            startY = mouse.y
            activated()
        }

        onPositionChanged: (mouse) => {
            if (pressed && windowState === 0) {
                previousX += mouse.x - startX
                previousY += mouse.y - startY
            }
        }

        onDoubleClicked: toggleMaximize()
    }

    // Title text
    Text {
        anchors.centerIn: parent
        text: windowTitle
        color: textLight
        font.bold: true
    }

    // Window controls
    Row {
        anchors {
            right: parent.right
            verticalCenter: parent.verticalCenter
            rightMargin: 8
        }
        spacing: 4

        // Minimize button
        Rectangle {
            width: 20; height: 20
            radius: 10
            color: minimizeArea.containsMouse ? "#ffc107" : "transparent"

            Text {
                anchors.centerIn: parent
                text: "−"
                color: textLight
                font.pixelSize: 16
            }

            MouseArea {
                id: minimizeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: minimize()
            }
        }

        // Maximize button
        Rectangle {
            width: 20; height: 20
            radius: 10
            color: maximizeArea.containsMouse ? "#4caf50" : "transparent"

            Text {
                anchors.centerIn: parent
                text: windowState === 1 ? "◱" : "◻"
                color: textLight
                font.pixelSize: 12
            }

            MouseArea {
                id: maximizeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: toggleMaximize()
            }
        }

        // Close button
        Rectangle {
            width: 20; height: 20
            radius: 10
            color: closeArea.containsMouse ? "#f44336" : "transparent"

            Text {
                anchors.centerIn: parent
                text: "×"
                color: textLight
                font.pixelSize: 16
            }

            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: closed()
            }
        }
    }
}
```

### Resize Handles

```qml
// Resize handles (8 directions)
Repeater {
    model: [
        { edge: "right", cursor: Qt.SizeHorCursor },
        { edge: "bottom", cursor: Qt.SizeVerCursor },
        { edge: "left", cursor: Qt.SizeHorCursor },
        { edge: "top", cursor: Qt.SizeVerCursor },
        { edge: "bottomRight", cursor: Qt.SizeFDiagCursor },
        { edge: "bottomLeft", cursor: Qt.SizeBDiagCursor },
        { edge: "topRight", cursor: Qt.SizeBDiagCursor },
        { edge: "topLeft", cursor: Qt.SizeFDiagCursor }
    ]

    Rectangle {
        property string edge: modelData.edge
        width: isCorner ? 12 : (isHorizontal ? 6 : parent.width)
        height: isCorner ? 12 : (isHorizontal ? parent.height : 6)
        color: "transparent"
        visible: windowState === 0

        property bool isCorner: edge.includes("top") || edge.includes("bottom")
        property bool isHorizontal: edge === "left" || edge === "right"

        anchors {
            right: edge.includes("Right") || edge === "right" ? parent.right : undefined
            left: edge.includes("Left") || edge === "left" ? parent.left : undefined
            top: edge.includes("top") || edge === "top" ? parent.top : undefined
            bottom: edge.includes("bottom") || edge === "bottom" ? parent.bottom : undefined
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: modelData.cursor

            property real startX: 0
            property real startY: 0
            property real startWidth: 0
            property real startHeight: 0

            onPressed: (mouse) => {
                startX = mouseX
                startY = mouseY
                startWidth = previousWidth
                startHeight = previousHeight
            }

            onPositionChanged: (mouse) => {
                if (!pressed) return

                var dx = mouseX - startX
                var dy = mouseY - startY

                if (edge.includes("Right")) {
                    previousWidth = Math.max(200, startWidth + dx)
                }
                if (edge.includes("bottom")) {
                    previousHeight = Math.max(100, startHeight + dy)
                }
                if (edge.includes("Left")) {
                    previousX += dx
                    previousWidth = Math.max(200, startWidth - dx)
                }
                if (edge.includes("top")) {
                    previousY += dy
                    previousHeight = Math.max(100, startHeight - dy)
                }
            }
        }
    }
}
```

---

## 7.5 Theme Systems

### Reactive Color Bindings

TRANS-QML uses reactive bindings for theme colors. Components bind to the main window's color properties:

```qml
// Main.qml - Theme definition
ApplicationWindow {
    id: mainWindow

    // Theme colors (can be changed at runtime)
    property color bgDark: "#1a1a2e"
    property color bgMedium: "#2a2a3e"
    property color bgLight: "#3a3a4e"
    property color textLight: "#ffffff"
    property color textMuted: "#cccccc"
    property color accentPink: "#F5A9B8"
    property color accentBlue: "#5BCEFA"
    property color borderColor: "#9B4F96"

    // Font scaling
    property int fontSizeSmall: 10
    property int fontSizeMedium: 12
    property int fontSizeLarge: 14
    property int fontSizeHeader: 16
    property string fontFamily: "system-ui"

    function applyColorScheme(scheme) {
        if (scheme === "dark") {
            bgDark = "#1a1a2e"
            bgMedium = "#2a2a3e"
            textLight = "#ffffff"
        } else if (scheme === "light") {
            bgDark = "#f0f0f0"
            bgMedium = "#e0e0e0"
            textLight = "#000000"
        }
    }
}
```

### Component Theme Binding

Child components access the main window's theme:

```qml
// In any component
Rectangle {
    id: myComponent

    // Get reference to main window
    property var mainWin: ApplicationWindow.window

    // Bind to theme colors
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"

    // Use the colors
    color: bgDark

    Text {
        text: "Hello"
        color: textLight
    }
}
```

### Font Scaling

```qml
// Reactive font size binding
Text {
    property var mainWin: ApplicationWindow.window
    property int fontSize: mainWin ? mainWin.fontSizeMedium : 12

    font.pixelSize: fontSize
    font.family: mainWin ? mainWin.fontFamily : "system-ui"
}
```

---

## 7.6 Mode-Specific Layouts

### Mode Configuration

Different application modes need different panel layouts:

```qml
// In UnifiedWorkspace
onCurrentModeChanged: {
    configurePanelsForMode(currentMode)
}

function configurePanelsForMode(mode) {
    switch(mode) {
        case "workflow":
            // Workflow mode: Tool palette + canvas
            showLeftPanel = true
            showRightPanel = true  // For node editor
            leftPanelContent = toolPaletteComponent
            centerContent = workflowCanvasComponent
            break

        case "sts":
        case "snom":
            // Spectroscopy: Project browser only
            showLeftPanel = true
            showRightPanel = false
            leftPanelContent = projectBrowserComponent
            centerContent = null
            break

        case "map":
            // Map mode: Browser + inspector
            showLeftPanel = true
            showRightPanel = true
            leftPanelContent = projectBrowserComponent
            rightPanelContent = mapInspectorComponent
            break
    }

    modeChanged(mode)
    layoutChanged()
}
```

### Mode Presets

```qml
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
            leftPanelWidth = 250
            rightPanelWidth = 300
            break

        case "workflow":
            showLeftPanel = true
            showRightPanel = true
            leftPanelWidth = 200
            rightPanelWidth = 350
            break
    }

    layoutChanged()
}
```

---

## 7.7 Layout State Persistence

### Saving Layout State

```qml
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
        canvas: {
            zoom: centerCanvas.zoomLevel,
            panX: centerCanvas.panX,
            panY: centerCanvas.panY
        }
    }
}
```

### Restoring Layout State

```qml
function restoreLayoutState(state) {
    if (!state) return

    if (state.mode) currentMode = state.mode

    if (state.leftPanel) {
        showLeftPanel = state.leftPanel.visible ?? showLeftPanel
        leftCollapsed = state.leftPanel.collapsed ?? false
        leftPanelWidth = state.leftPanel.width ?? 280
    }

    if (state.rightPanel) {
        showRightPanel = state.rightPanel.visible ?? showRightPanel
        rightCollapsed = state.rightPanel.collapsed ?? false
        rightPanelWidth = state.rightPanel.width ?? 300
    }

    if (state.canvas) {
        centerCanvas.zoomLevel = state.canvas.zoom ?? 1.0
        centerCanvas.panX = state.canvas.panX ?? 0
        centerCanvas.panY = state.canvas.panY ?? 0
    }

    layoutChanged()
}
```

### Python Backend Integration

```python
# In app_backend.py
@Slot(result='QVariant')
def loadLayoutState(self):
    """Load layout state from preferences"""
    prefs = self._preferences_manager
    return prefs.get("layout_state", {})

@Slot('QVariant')
def saveLayoutState(self, state):
    """Save layout state to preferences"""
    prefs = self._preferences_manager
    prefs.set("layout_state", state)
    prefs.save()
```

---

## 7.8 Dynamic Tool Loading

### Tool Registry

TRANS-QML dynamically loads tool windows based on tool names:

```qml
// Tool name to file mapping
property var toolFileMapping: {
    "1D FFT": "FFT1DTool",
    "2D FFT": "FFT2DTool",
    "Curve Smoothing": "CurveSmoothingTool",
    "Derivative Calculator": "DerivativeTool",
    "Curve Fitting": "CurveFittingTool",
    "Map Generator": "MapGeneratorTool"
}

function openToolWindow(toolName, config) {
    var component = toolComponents[toolName]

    if (!component) {
        // Get file name from mapping
        var fileName = toolFileMapping[toolName]
        if (!fileName) {
            fileName = toolName.replace(/ /g, "") + "Tool"
        }

        // Dynamically load component
        var path = "../tools/" + fileName + ".qml"
        component = Qt.createComponent(path)

        if (component.status === Component.Error) {
            console.error("Failed to load tool:", toolName, component.errorString())
            // Use generic fallback
            component = Qt.createComponent("../tools/GenericToolUI.qml")
        }

        // Handle async loading
        if (component.status === Component.Loading) {
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    toolComponents[toolName] = component
                    embeddedWindowManager.createToolWindow(toolName, component, config)
                }
            })
            return "loading_" + toolName
        }

        toolComponents[toolName] = component
    }

    return embeddedWindowManager.createToolWindow(toolName, component, config)
}
```

---

## 7.9 Floating Entities

For entities that don't need the full window chrome:

```qml
// Floating entities model
ListModel {
    id: floatingEntitiesModel
}

function addFloatingEntity(entityId, entityType, component, x, y, width, height, data) {
    // Calculate z-order
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

    return floatingEntitiesModel.count - 1
}

function bringEntityToFront(entityId) {
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
```

---

## 7.10 Summary

### Key Patterns

1. **Unified Workspace** - Central container for all UI elements
2. **Dock Panels** - Collapsible, resizable edge panels
3. **Window Manager** - Manages embedded windows with z-ordering
4. **Theme Bindings** - Reactive color/font propagation
5. **Mode Configuration** - Different layouts per application mode
6. **Layout Persistence** - Save/restore workspace state

### Best Practices

| Do | Don't |
|----|-------|
| Use reactive bindings for theme | Hardcode colors |
| Preload frequently-used components | Create components on every use |
| Separate window state from content | Mix window chrome with content |
| Persist layout preferences | Lose user customizations |
| Use z-ordering for window stacking | Manually manage window order |

---

## Exercises

### Exercise 7.1: Custom Dock Panel
Create a dock panel with a search box and filterable list.

### Exercise 7.2: Theme Switcher
Implement light/dark theme switching with smooth transitions.

### Exercise 7.3: Window Snapping
Add edge snapping when windows are dragged near each other.

### Exercise 7.4: Layout Presets
Create named layout presets that users can save and restore.

### Exercise 7.5: Floating Toolbar
Create a floating toolbar that stays visible across mode changes.

---

## Next Steps

In **Module 8: Application Architecture**, you'll learn:
- Backend/frontend separation patterns
- State management strategies
- Project save/load systems
- Plugin and workflow systems
- Testing strategies

---

*Module 7 of 8 | TRANS-QML Course*
