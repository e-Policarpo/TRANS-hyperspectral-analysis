# Unified UI Implementation Plan

## Current Status: Phase 6 Pending

**Branch:** `Unified-UI`
**Last Commit:** `3fd4505` - Phase 5: Global font scaling

---

## Completed Phases

### Phase 1: Core Docking Infrastructure ✅
**Commit:** `098e398`

Files created:
- `src/qml/components/DockPanel.qml` - Collapsible, tabbed, resizable dock panel
- `src/qml/components/WorkspaceCanvas.qml` - Central canvas with configurable backgrounds
- `src/qml/components/UnifiedWorkspace.qml` - Main container with mode-based layout

### Phase 2: Floating Entity System ✅
**Commit:** `9d6904e`

Files created:
- `src/qml/components/FloatingEntity.qml` - Base draggable/resizable entity
- `src/qml/components/GraphEntity.qml` - QML-native graph visualization
- `src/qml/components/TableEntity.qml` - Data table with headers, selection
- `src/qml/components/MapEntity.qml` - Hyperspectral map with colormaps

Features:
- Entity creation functions in UnifiedWorkspace (createGraphEntity, createTableEntity, createMapEntity)
- Drag, resize, minimize, dock support
- Theme-reactive colors

### Phase 3: Workflow & Panel Entities ✅
**Commit:** `57ea8a4`

Files created:
- `src/qml/workflow/WorkflowCanvas.qml` - Embeddable workflow node canvas
- `src/qml/workflow/WorkflowToolPalette.qml` - Draggable tool palette
- `src/qml/components/ProjectBrowserEntity.qml` - Floating wrapper for ProjectBrowser
- `src/qml/components/DataBrowserEntity.qml` - Floating wrapper for map DataBrowser
- `src/qml/components/PointInspectorEntity.qml` - Floating wrapper for PointInspector
- `src/qml/components/StatisticsPanelEntity.qml` - Floating wrapper for StatisticsPanel

Files modified:
- `src/qml/components/qmldir` - Registered new entity components
- `src/qml/workflow/qmldir` - Registered WorkflowCanvas and WorkflowToolPalette
- `src/qml/components/UnifiedWorkspace.qml` - Added entity creation functions

Features:
- Entity creation functions (createProjectBrowserEntity, createDataBrowserEntity, createPointInspectorEntity, createStatisticsPanelEntity)
- WorkflowCanvas with node editing and connections
- WorkflowToolPalette with draggable tool items

### Phase 4: Mode-Specific Configurations ✅
**Commit:** `c6e2399`

Files modified:
- `src/qml/components/UnifiedWorkspace.qml` - Added mode-specific panel configuration
- `src/qml/main/Main.qml` - Added Workflow tab and mode switching

Features:
- backend and workflowManager properties for external references
- Mode-specific panel content components (toolPalette, workflowCanvas)
- configurePanelsForMode() function for auto-configuration
- Workflow tab as 4th tab with dedicated workspace
- ProjectBrowser hidden in workflow mode (uses internal ToolPalette)

### Phase 5: Global Font Scaling ✅
**Commit:** `3fd4505`

Files modified:
- `src/qml/main/Main.qml` - Added global font size properties
- `src/qml/components/UnifiedWorkspace.qml` - Added font scaling bindings
- `src/qml/components/DockPanel.qml` - Updated to use scaled fonts

Features:
- fontSizeSmall/Medium/Large/Header/Title properties in Main.qml
- fontFamily property for consistent font selection
- applyColorScheme() now applies font settings from preferences
- Reactive font size bindings in child components
- Font sizes flow: PreferencesManager -> Main.qml -> components

---

## Remaining Phases

### Phase 6: Polish and Testing
- Layout persistence (save/restore)
- Keyboard shortcuts
- Performance optimization
- Edge case handling

---

## Architecture

```
ApplicationWindow
└── UnifiedWorkspace
    ├── LeftDockPanel (collapsible, tabbed)
    │   └── ProjectBrowser OR ToolPalette (mode-dependent)
    ├── CenterWorkspace
    │   ├── WorkspaceCanvas (dotted/grid background)
    │   └── FloatingEntities (graphs, tables, maps, browsers)
    ├── RightDockPanel (collapsible, tabbed)
    │   └── Properties / Parameter Editor / DataBrowser
    └── TopDockPanel / BottomDockPanel (optional)
```

## Design Decisions

| Decision | Choice |
|----------|--------|
| Graphs/Tables | QML-native (not Python wrappers) |
| Floating Entities | Full dock support (drag to/from panels) |
| Workflow Mode | Tool Palette replaces Project Browser |
| STS/SNOM Background | Dotted grid style |
| Map Editor Panels | Converted to floating entities |
