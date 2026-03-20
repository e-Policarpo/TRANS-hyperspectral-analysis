# Standalone Tool Theming System

## Overview

All standalone tools in `/src/qml/tools/` now follow the reactive color scheme defined in `Main.qml`. When the user changes themes via Preferences, tool windows automatically update their colors.

## Architecture

```
Main.qml (color properties)
    ↓ (findMainWindow)
DraggableWindow.qml (exposes colors)
    ↓ (Window.window)
Tool*.qml (uses colors)
```

## Color Properties Available

Each tool has access to these color properties via `parentWindow`:

| Property | Default | Usage |
|----------|---------|-------|
| `bgDark` | `#1a1a2e` | Main background |
| `bgMedium` | `#2a2a3e` | GroupBox backgrounds |
| `bgLight` | `#3a3a4e` | Highlight backgrounds |
| `accentPink` | `#F5A9B8` | Primary accent (from theme) |
| `accentBlue` | `#5BCEFA` | Secondary accent (info states) |
| `accentMagenta` | `#D60270` | Error/warning states |
| `accentPurple` | `#9B4F96` | Description text accent |
| `textLight` | `#ffffff` | Primary text |
| `textMuted` | `#cccccc` | Secondary/helper text |
| `successColor` | `#2ECC71` | Success states |
| `borderColor` | `#8B4F86` | Borders and dividers |

## Color Migration Reference

Old hardcoded colors replaced with theme properties:

| Old Color | New Property | Context |
|-----------|--------------|---------|
| `#9B4F96` | `accentPurple` | Tool description labels |
| `#666666` | `textMuted` | Info/helper text |
| `#B0A0B8` | `textMuted` | Italic helper text |
| `#D60270` | `accentMagenta` | Error states, delete buttons |
| `#0066cc` | `accentBlue` | Info states, status text |
| `#00aa00` / `#009933` | `successColor` | Success states |
| `#dddddd` / `#cccccc` | `borderColor` | Divider lines |
| `#f5f5f5` | `bgLight` | Light backgrounds |

## Tool Template

New tools should include this color binding block:

```qml
Item {
    id: root

    // Theme colors - reactive bindings to parent DraggableWindow
    property var parentWindow: Window.window
    property color bgDark: parentWindow ? parentWindow.bgDark : "#1a1a2e"
    property color bgMedium: parentWindow ? parentWindow.bgMedium : "#2a2a3e"
    property color bgLight: parentWindow ? parentWindow.bgLight : "#3a3a4e"
    property color accentPink: parentWindow ? parentWindow.accentPink : "#F5A9B8"
    property color accentBlue: parentWindow ? parentWindow.accentBlue : "#5BCEFA"
    property color accentMagenta: parentWindow ? parentWindow.accentMagenta : "#D60270"
    property color accentPurple: parentWindow ? parentWindow.accentPurple : "#9B4F96"
    property color textLight: parentWindow ? parentWindow.textLight : "#ffffff"
    property color textMuted: parentWindow ? parentWindow.textMuted : "#cccccc"
    property color successColor: parentWindow ? parentWindow.successColor : "#2ECC71"

    // Tool content...
}
```

## Files Updated (December 2025)

- `DraggableWindow.qml` - Added `accentMagenta`, `accentPurple`, `accentOrange`, `successColor`
- `GenericToolUI.qml`
- `IntegrationTool.qml`
- `CurveSmoothingTool.qml`
- `DerivativeTool.qml`
- `FFT1DTool.qml`
- `FFT2DTool.qml`
- `GradientTool.qml`
- `ImageSmoothingTool.qml`
- `MapDiscretizerTool.qml`
- `MapGeneratorTool.qml`
- `MapProcessingTool.qml`
- `CurveAnalysisTool.qml`
- `CurveFittingTool.qml`
- `PeakIndexingTool.qml`
- `SpatialAverageTool.qml`
- `TruncateTool.qml`
