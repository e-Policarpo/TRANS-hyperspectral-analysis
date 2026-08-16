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
import Qt.labs.platform 1.1 as Platform
import "../components"

ApplicationWindow {
    id: mainWindow
    objectName: "mainWindow"  // Used by child windows to find this window for theme colors
    visible: true
    width: 1400
    height: 900
    title: backend.projectReady ? "TRANS-QML - " + backend.projectName : "TRANS-QML - Hyperspectral Data Analysis"

    // Set to true once the user has confirmed they want to quit despite a
    // running operation. Lets the second onClosing pass through.
    property bool _forceClose: false

    // Close all child windows when main window closes
    onClosing: function(close) {
        // If a background worker is still running (e.g. a project save or a
        // long tool), closing immediately can hang the app or lose work.
        // Intercept and ask the user instead of accepting the close.
        if (backend.isBusy && !_forceClose) {
            close.accepted = false
            busyCloseDialog.open()
            return
        }
        closeAllWorkflowWindows()
        backend.closeAllWindows()
        close.accepted = true
    }

    // Project state
    property bool projectReady: backend.projectReady

    // Track open tool windows
    property var openTools: []
    property int currentTabIndex: 0

    // Pending map-load requests received before the lazy MapEditorWorkstation
    // finishes instantiating. Lifted from the StackLayout to the root window so
    // all backend signal handlers can reach them via the file-scoped `mainWindow`
    // id (signal handlers don't see properties declared on inner items).
    property string _pendingMapLoad: ""
    property string _pendingMapLoadById: ""
    property string _pendingLineScan: ""

    // Show startup dialog on launch and apply saved color scheme
    Component.onCompleted: {
        var t0 = Date.now()
        // Apply saved color scheme from preferences
        applyColorScheme()
        console.log("[TIMING] applyColorScheme: " + (Date.now() - t0) + "ms")

        // Wire the global ``backend`` context property into WindowManager.
        // This Component.onCompleted runs in ApplicationWindow's scope, so
        // ``backend`` resolves to the context property, not WindowManager's
        // local one. The image/note window plumbing depends on this — see
        // openImageWindow/openNoteWindow in WindowManager.qml.
        toolWindowManager.appBackend = backend

        // Map editor backend is registered lazily when MapEditorWorkstation loads

        if (!backend.projectReady) {
            startupDialogLoader.active = true
        }
        console.log("[TIMING] Main.qml Component.onCompleted total: " + (Date.now() - t0) + "ms")
    }

    // Reactive tools list based on current tab
    // Tab indices: 0=Spectral, 1=Hyperspectral
    property var currentTools: {
        if (currentTabIndex === 0) {
            return [
                "1D FFT", "Curve Smoothing", "Image Smoothing",
                "Derivative Calculator", "Curve Fitting", "Gradient Filter",
                "Integration Utility", "Map Generator", "Spatial Average",
                "Truncate Data", "Curve Analysis", "Confinement Analysis",
                "Spectral Features", "Peak Indexing",
                "Average Curves", "Filter Bad Data", "Cosmic Ray Filter",
                "Background Subtraction",
                "Dirac Point Estimator", "Detect Bandgap & Doping",
                "Spectral Axis Converter", "Multi-Peak Fitting"
            ]
        } else if (currentTabIndex === 1) {
            return ["Confinement Analysis", "Spectral Features", "Image Smoothing", "Gradient Filter", "Map Discretizer", "Map Processing"]
        }
        return []
    }


    // ========== REACTIVE COLOR SCHEME ==========
    // Colors are now reactive and update when PreferencesManager emits colorSchemeChanged
    property color bgDark: "#1a1a2e"
    property color bgDarker: "#0d0d1a"
    property color bgMedium: "#2a2a3e"
    property color bgLight: "#3a3a4e"
    property color accentPink: "#F5A9B8"      // accentPrimary
    property color accentBlue: "#5BCEFA"      // accentSecondary
    property color accentMagenta: "#D60270"   // Maps to error color
    property color accentPurple: "#9B4F96"    // Maps to borderColor
    property color accentOrange: "#FF9B55"    // accentTertiary (for workflow button)
    property color textLight: "#ffffff"       // textPrimary
    property color textMuted: "#cccccc"       // textMuted
    property color borderColor: "#9B4F96"     // borderColor

    // ========== CONTROL PALETTE ==========
    // Qt Quick Controls that aren't explicitly styled (plain TextField,
    // ComboBox, Button, GroupBox titles …) fall back to Qt's default palette,
    // which follows the *system* appearance. On macOS in dark mode that paints
    // black text fields and dark buttons inside a light TRANS theme. Setting
    // the window palette makes the Basic style follow the scheme instead; it
    // propagates to every child item, so tools inherit it without each one
    // having to restyle its controls.
    palette.window: bgDark
    palette.windowText: textLight
    palette.base: bgDarker            // editable field background
    palette.alternateBase: bgMedium
    palette.text: textLight
    palette.button: bgLight
    palette.buttonText: textLight
    palette.highlight: accentPink     // selection
    palette.highlightedText: bgDark
    palette.placeholderText: textMuted
    palette.mid: borderColor
    palette.dark: bgDarker
    palette.light: bgLight
    palette.toolTipBase: bgMedium
    palette.toolTipText: textLight

    // ========== FONT SCALING ==========
    // Global font sizes - components should reference these for consistent scaling
    property int fontSizeSmall: 10
    property int fontSizeMedium: 12
    property int fontSizeLarge: 14
    property int fontSizeHeader: 16
    property int fontSizeTitle: 18
    property string fontFamily: Qt.platform.os === "osx" ? ".AppleSystemUIFont" : "Segoe UI"
    property string fontFamilyMono: Qt.platform.os === "osx" ? "Menlo" : "Consolas"

    // Computed scaled sizes for convenience
    property int fontSizeXSmall: Math.max(8, fontSizeSmall - 2)
    property int fontSizeXLarge: fontSizeHeader + 2

    // Port type colors for workflow editor - maximally distinct colors
    // Port types from PortType enum: dataset, flat_data, image, map, table, number, string, intervals, any
    // NOTE: Using hardcoded fallback - regeneratePortColors() creates the themed version
    property var portColors: ({
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

    // Apply color scheme from PreferencesManager
    function applyColorScheme() {
        if (!backend || !backend.preferencesManager) {
            console.log("PreferencesManager not ready, using defaults")
            return
        }

        var scheme = backend.preferencesManager.getCurrentScheme()
        if (!scheme || !scheme.colors) {
            console.log("No color scheme available")
            return
        }

        var c = scheme.colors
        console.log("Applying color scheme:", backend.preferencesManager.getCurrentSchemeName())

        // Apply background colors
        bgDark = c.bgDark || "#1a1a2e"
        bgDarker = c.bgDarker || "#0d0d1a"
        bgMedium = c.bgMedium || "#2a2a3e"
        bgLight = c.bgLight || "#3a3a4e"

        // Apply accent colors
        accentPink = c.accentPrimary || "#F5A9B8"
        accentBlue = c.accentSecondary || "#5BCEFA"
        accentOrange = c.accentTertiary || "#FF9B55"
        accentMagenta = c.error || "#D60270"
        accentPurple = c.borderColor || "#9B4F96"

        // Apply text colors
        textLight = c.textPrimary || "#ffffff"
        textMuted = c.textMuted || "#cccccc"

        // Apply border color
        borderColor = c.borderColor || "#9B4F96"

        // Apply font settings
        if (scheme.font) {
            fontSizeSmall = scheme.font.sizeSmall || 10
            fontSizeMedium = scheme.font.sizeMedium || 12
            fontSizeLarge = scheme.font.sizeLarge || 14
            fontSizeHeader = scheme.font.sizeHeader || 16
            fontSizeTitle = scheme.font.sizeTitle || 18
            var ff = scheme.font.family || ""
            if (!ff || ff === "system-ui")
                ff = Qt.platform.os === "osx" ? ".AppleSystemUIFont" : "Segoe UI"
            fontFamily = ff
            console.log("Applied font sizes: small=" + fontSizeSmall + ", medium=" + fontSizeMedium + ", large=" + fontSizeLarge)
        }

        // Regenerate portColors object to trigger reactive updates in workflow windows
        // QML doesn't track changes inside objects, so we must reassign the entire object
        regeneratePortColors()
    }

    // Regenerate the portColors object (call after color properties change)
    // Port types from PortType enum: dataset, flat_data, image, map, table, number, string, intervals, any
    // Colors are fixed to be maximally distinct - theme affects only dataset/map/number
    function regeneratePortColors() {
        try {
            portColors = {
                "dataset": accentBlue,              // Theme cyan/blue
                "flat_data": "#FFD700",             // Fixed gold (distinct from blue)
                "image": "#FF6B6B",                 // Fixed coral red
                "map": accentPurple,                // Theme purple
                "table": "#2ECC71",                 // Fixed emerald green
                "number": accentMagenta,            // Theme magenta/pink
                "string": "#FF9800",                // Fixed orange
                "intervals": "#00BCD4",             // Fixed teal
                "any": textMuted                    // Theme gray
            }
            console.log("Port colors regenerated for theme")
        } catch (e) {
            console.log("Error regenerating port colors, using fallback:", e)
            // Use hardcoded fallback if Qt.lighter fails
            portColors = {
                "dataset": "#5BCEFA",
                "flat_data": "#FFD700",
                "image": "#FF6B6B",
                "map": "#9B4F96",
                "table": "#2ECC71",
                "number": "#E91E63",
                "string": "#FF9800",
                "intervals": "#00BCD4",
                "any": "#9E9E9E"
            }
        }
    }

    // Listen for color scheme changes from PreferencesManager
    Connections {
        target: backend ? backend.preferencesManager : null
        enabled: backend && backend.preferencesManager

        function onColorSchemeChanged(schemeName) {
            console.log("Color scheme changed signal received:", schemeName)
            applyColorScheme()
        }

        function onPreferencesLoaded() {
            console.log("Preferences loaded, applying color scheme")
            applyColorScheme()
        }

        function onFontChanged() {
            console.log("Font changed signal received")
            applyColorScheme()
        }
    }

    // Main background - binds to reactive bgDark
    color: bgDark

    // Menu bar
    menuBar: MenuBar {
        background: Rectangle {
            color: bgDarker
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: borderColor
            }
        }

        delegate: MenuBarItem {
            id: menuBarItem
            contentItem: Text {
                text: menuBarItem.text
                font.pixelSize: 14
                color: menuBarItem.enabled ? textLight : textMuted
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
                padding: 10
            }
            background: Rectangle {
                color: menuBarItem.highlighted ? bgLight : "transparent"
                radius: 3
            }
        }

        // T.R.A.N.S. application menu (macOS only - on Windows/Linux, items move to Help)
        Menu {
            title: "T.R.A.N.S."
            visible: Qt.platform.os === "osx"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
                radius: 4
            }
            delegate: MenuItem {
                id: transMenuItem
                contentItem: Text {
                    text: transMenuItem.text
                    font.pixelSize: 13
                    color: transMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: transMenuItem.highlighted ? accentPink : "transparent"
                    opacity: transMenuItem.highlighted ? 0.3 : 1
                    radius: 3
                }
            }
            MenuItem {
                text: "About T.R.A.N.S."
                onTriggered: aboutDialog.open()
            }
            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }
            MenuItem {
                text: "Preferences..."
                onTriggered: openPreferencesDialog()
            }
            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }
            MenuItem {
                text: "Quit T.R.A.N.S."
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "File"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: fileMenuItem
                contentItem: Text {
                    text: fileMenuItem.text
                    font.pixelSize: 13
                    color: fileMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: fileMenuItem.highlighted ? accentBlue : "transparent"
                    opacity: fileMenuItem.highlighted ? 0.3 : 1
                }
            }
            MenuItem {
                text: "New Project..."
                onTriggered: projectStartupDialog.open()
            }
            MenuItem {
                text: "Open Project..."
                onTriggered: projectStartupDialog.open()
            }
            MenuItem {
                text: "Save Project"
                enabled: backend.projectReady
                onTriggered: backend.saveProjectFile("")
            }
            MenuItem {
                text: "Save Project As..."
                enabled: backend.projectReady
                onTriggered: saveProjectDialog.open()
            }
            MenuItem {
                text: "Close Project"
                enabled: backend.projectReady
                onTriggered: {
                    backend.closeProject()
                    projectStartupDialog.open()
                }
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Import Measurement..."
                enabled: backend.projectReady
                onTriggered: openLazyDialog(importMeasurementLoader)
            }
            MenuItem {
                text: "Import Image..."
                enabled: backend.projectReady
                onTriggered: importImageDialog.open()
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "New Table"
                onTriggered: backend.newTable()
            }
            MenuItem {
                text: "New Graph"
                onTriggered: backend.newPlot()
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Exit"
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "Edit"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: editMenuItem
                contentItem: Text {
                    text: editMenuItem.text
                    font.pixelSize: 13
                    color: editMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: editMenuItem.highlighted ? accentBlue : "transparent"
                    opacity: editMenuItem.highlighted ? 0.3 : 1
                }
            }

            MenuItem {
                text: backend.undoManager ? backend.undoManager.undoText : "Undo"
                enabled: backend.undoManager ? backend.undoManager.canUndo : false
                onTriggered: backend.undoManager.undo()
            }

            MenuItem {
                text: backend.undoManager ? backend.undoManager.redoText : "Redo"
                enabled: backend.undoManager ? backend.undoManager.canRedo : false
                onTriggered: backend.undoManager.redo()
            }
        }

        Menu {
            id: toolsMenu
            title: "Tools"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: toolMenuItem
                contentItem: Text {
                    text: toolMenuItem.text
                    font.pixelSize: 13
                    color: toolMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: toolMenuItem.highlighted ? accentPink : "transparent"
                    opacity: toolMenuItem.highlighted ? 0.3 : 1
                }
            }

            // Spectral Analysis tools (tab 0)
            MenuItem {
                text: "1D FFT"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Curve Smoothing"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Image Smoothing"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Derivative Calculator"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Curve Fitting"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Gradient Filter"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Integration Utility"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Generator"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Discretizer"
                visible: currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Processing"
                visible: currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Spatial Average"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Truncate Data"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Curve Analysis"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Confinement Analysis"
                // Also available on the Hyperspectral tab: it is the tool that
                // turns a map's spectra into the peak-occupancy table.
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Spectral Features"
                // Also on the Hyperspectral tab: it turns a map's spectra
                // into the table that classification runs on.
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Peak Indexing"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Average Curves"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Filter Bad Data"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Cosmic Ray Filter"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Background Subtraction"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Dirac Point Estimator"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Detect Bandgap & Doping"
                visible: currentTabIndex === 0
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
        }

        Menu {
            id: workflowsMenu
            title: "Workflows"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: workflowMenuItem
                contentItem: Text {
                    text: workflowMenuItem.text
                    font.pixelSize: 13
                    color: workflowMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: workflowMenuItem.highlighted ? accentBlue : "transparent"
                    opacity: workflowMenuItem.highlighted ? 0.3 : 1
                }
            }
            MenuItem {
                text: "New Workflow..."
                onTriggered: openWorkflowWindow("New Workflow")
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            // Project workflows section
            MenuItem {
                text: "Project Workflows"
                enabled: false
                contentItem: Text {
                    text: "— Project Workflows —"
                    font.pixelSize: 11
                    font.italic: true
                    color: textMuted
                    leftPadding: 10
                }
            }

            Instantiator {
                id: projectWorkflowsInstantiator
                model: ListModel { id: projectWorkflowsModel }
                delegate: MenuItem {
                    id: workflowMenuItem
                    required property int index
                    required property string name
                    required property string path
                    text: name
                    contentItem: Text {
                        text: workflowMenuItem.name  // Use the required property directly
                        font.pixelSize: 13
                        color: textLight
                        leftPadding: 10
                        rightPadding: 10
                    }
                    background: Rectangle {
                        color: workflowMenuItem.highlighted ? accentBlue : "transparent"
                        opacity: workflowMenuItem.highlighted ? 0.3 : 1
                    }
                    onTriggered: {
                        if (loadWorkflowLoader.item) {
                            loadWorkflowLoader.item.loadWorkflowFromFile(workflowMenuItem.path)
                        } else {
                            loadWorkflowLoader.pendingPath = workflowMenuItem.path
                            loadWorkflowLoader.active = true
                        }
                    }
                }
                onObjectAdded: function(index, object) {
                    workflowsMenu.insertItem(workflowsMenu.count - 2, object)
                }
                onObjectRemoved: function(index, object) {
                    workflowsMenu.removeItem(object)
                }
            }

            MenuItem {
                text: "(No saved workflows)"
                enabled: false
                visible: projectWorkflowsModel.count === 0
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Load Workflow..."
                onTriggered: openLazyDialog(loadWorkflowLoader)
            }

            MenuItem {
                text: "Refresh List"
                onTriggered: refreshProjectWorkflows()
            }

            onAboutToShow: {
                refreshProjectWorkflows()
            }
        }

        Menu {
            title: "Window"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: windowMenuItem
                contentItem: Text {
                    text: windowMenuItem.text
                    font.pixelSize: 13
                    color: windowMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: windowMenuItem.highlighted ? accentPink : "transparent"
                    opacity: windowMenuItem.highlighted ? 0.3 : 1
                }
            }
            MenuItem {
                text: "Toggle Project Browser"
                checkable: true
                checked: projectBrowser.visible
                onTriggered: {
                    projectBrowser.parent.visible = !projectBrowser.parent.visible
                }
                // Shortcut: Ctrl+B (will be added)
            }
            MenuItem {
                text: "Toggle Debug Console"
                checkable: true
                checked: debugConsole.visible
                onTriggered: {
                    debugConsole.visible = !debugConsole.visible
                }
                // Shortcut: Ctrl+D
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Save Layout..."
                onTriggered: openLazyDialog(saveLayoutLoader)
            }
            MenuItem {
                text: "Load Layout..."
                onTriggered: openLazyDialog(loadLayoutLoader)
            }
            MenuItem {
                text: "Reset Layout"
                onTriggered: {
                    if (backend && backend.dockManager) {
                        backend.dockManager.resetLayout()
                    }
                }
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Cascade Windows"
                enabled: openTools.length > 0
                onTriggered: toolWindowManager.cascadeWindows()
            }
            MenuItem {
                text: "Tile Windows"
                enabled: openTools.length > 0
                onTriggered: toolWindowManager.tileWindows()
            }

            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }

            MenuItem {
                text: "Open Tools"
                enabled: false
            }

            // Dynamic list of open tool windows
            Repeater {
                model: openTools
                delegate: MenuItem {
                    text: "  " + modelData.name
                    onTriggered: {
                        toolWindowManager.activateWindow(modelData.windowId)
                    }
                }
            }
        }

        Menu {
            title: "Help"
            background: Rectangle {
                color: bgMedium
                border.color: borderColor
                border.width: 1
            }
            delegate: MenuItem {
                id: helpMenuItem
                contentItem: Text {
                    text: helpMenuItem.text
                    font.pixelSize: 13
                    color: helpMenuItem.enabled ? textLight : textMuted
                    leftPadding: 10
                    rightPadding: 10
                }
                background: Rectangle {
                    color: helpMenuItem.highlighted ? accentPink : "transparent"
                    opacity: helpMenuItem.highlighted ? 0.3 : 1
                }
            }
            MenuItem {
                text: "Documentation (Coming Soon)"
                enabled: false
            }
            MenuSeparator {
                visible: Qt.platform.os !== "osx"
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }
            MenuItem {
                text: "Preferences..."
                visible: Qt.platform.os !== "osx"
                onTriggered: openPreferencesDialog()
            }
            MenuSeparator {
                contentItem: Rectangle {
                    implicitHeight: 1
                    color: borderColor
                }
            }
            MenuItem {
                text: "About"
                onTriggered: aboutDialog.open()
            }
        }
    }

    // Main content area with project browser
    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        // Project Browser (left side)
        Rectangle {
            SplitView.minimumWidth: 200
            SplitView.preferredWidth: 280
            SplitView.maximumWidth: 400
            color: "transparent"

            ProjectBrowser {
                id: projectBrowser
                anchors.fill: parent
            }
        }

        // Main workspace (right side)
        Item {
            SplitView.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Toolbar for workspace controls
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    color: bgMedium

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: borderColor
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 5
                        spacing: 10

                        Text {
                            text: "Workspace"
                            font.pixelSize: 14
                            font.bold: true
                            color: textLight
                        }

                        Item { Layout.fillWidth: true }

                        // Tab selector (still useful for tool filtering)
                        TabBar {
                            id: tabBar
                            Layout.preferredWidth: 400
                            currentIndex: currentTabIndex
                            onCurrentIndexChanged: {
                                currentTabIndex = currentIndex
                                backend.currentTab = currentIndex
                                // Lazy-load MapEditorWorkstation on first switch to Hyperspectral tab
                                if (currentIndex === 1) {
                                    mapEditorLoader.ensureLoaded()
                                }
                            }

                            background: Rectangle {
                                color: bgMedium
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 1
                                    color: borderColor
                                }
                            }

                            TabButton {
                                text: "Spectral Analysis"
                                contentItem: Text {
                                    text: parent.text
                                    font.pixelSize: 14
                                    font.bold: parent.checked
                                    color: parent.checked ? accentPink : textMuted
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                background: Rectangle {
                                    color: parent.checked ? bgLight : "transparent"
                                    Rectangle {
                                        visible: parent.parent.checked
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: 2
                                        color: accentPink
                                    }
                                }
                            }
                            TabButton {
                                text: "Hyperspectral Analysis"
                                contentItem: Text {
                                    text: parent.text
                                    font.pixelSize: 14
                                    font.bold: parent.checked
                                    color: parent.checked ? accentPink : textMuted
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                background: Rectangle {
                                    color: parent.checked ? bgLight : "transparent"
                                    Rectangle {
                                        visible: parent.parent.checked
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: 2
                                        color: accentPink
                                    }
                                }
                            }
                        }  // TabBar

                        // Workflow Editor button
                        Button {
                            text: "Workflow Editor"
                            onClicked: openWorkflowWindow("New Workflow")
                            contentItem: Text {
                                text: parent.text
                                font.pixelSize: fontSizeLarge
                                font.bold: true
                                font.family: fontFamily
                                color: parent.hovered ? textLight : textMuted
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 4
                                Rectangle {
                                    visible: parent.parent.hovered
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 2
                                    color: accentOrange
                                }
                            }
                        }
                    }  // RowLayout
                }  // Rectangle (toolbar)

        // Workspace container wrapper - constrains WindowManager to canvas area
        Item {
            id: workspaceContainer
            Layout.fillWidth: true
            Layout.fillHeight: true

        StackLayout {
            id: workspaceStack
            anchors.fill: parent
            // Tab indices: 0=Spectral, 1=Hyperspectral
            currentIndex: currentTabIndex

            // Unified Workspace (for Spectral Analysis tab)
            UnifiedWorkspace {
                id: workspace
                currentMode: "spectral"
                backend: backend
                workflowManager: backend ? backend.workflowManager : null

                // Panel visibility for Spectral Analysis mode
                showLeftPanel: true
                leftPanelWidth: 220
                showRightPanel: false
                showTopPanel: false
                showBottomPanel: false
                canvasZoomEnabled: false

                // Provide tool palette as left panel content
                standalonePaletteComponent: Component {
                    ToolPalettePanel {
                        tools: currentTools
                        onToolActivated: function(toolName) {
                            openToolWindow(toolName)
                        }
                    }
                }

                // Listen to backend tool open signals
                Connections {
                    target: backend
                    function onToolOpened(toolName) {
                        console.log("Tool opened signal received:", toolName)
                        // In future: create floating entity for the tool
                    }
                }

                // Handle canvas interactions
                onFloatingEntityAdded: function(entity) {
                    console.log("Floating entity added:", entity.id, entity.type)
                }

                onFloatingEntityRemoved: function(entityId) {
                    console.log("Floating entity removed:", entityId)
                }
            }

            // Map Editor Workstation (for Hyperspectral Analysis tab) — lazy loaded
            Loader {
                id: mapEditorLoader
                active: false  // Activated on first tab switch or map load
                source: ""
                property bool initialized: false

                function ensureLoaded() {
                    if (!active) {
                        source = "../map_editor/MapEditorWorkstation.qml"
                        active = true
                    }
                }

                onLoaded: {
                    if (!initialized && item) {
                        initialized = true
                        var mew = item
                        backend.setMapEditorBackend(mew.mapEditorBackend)
                        mew.linkDatasetsFromBackend(backend)

                        mew.spectrumRequested.connect(function(row, col) {
                            console.log("Spectrum requested at:", row, col)
                        })
                        mew.blockSelectionChanged.connect(function(count) {
                            console.log("Block selection changed:", count, "blocks")
                        })
                        mew.openSpectrumPlotRequested.connect(function(datasetName, spectra, forceNewWindow) {
                            console.log("Open spectrum plot requested:", datasetName, "with", spectra.length, "spectra")
                            if (!spectra || spectra.length === 0) return

                            var curves = []
                            for (var i = 0; i < spectra.length; i++) {
                                curves.push({
                                    x: spectra[i].x,
                                    y: spectra[i].y,
                                    label: spectra[i].title || ("Spectrum " + (i+1)),
                                    color: ""
                                })
                            }
                            var title = datasetName + " Spectra"
                            var xl = spectra[0].x_name || "X"
                            var yl = spectra[0].y_name || "Intensity"

                            // Key the reused window by datasetName so distinct
                            // sources (e.g. "STS points · Forward/Backward/Mixed")
                            // each get their own window instead of clobbering one.
                            var ids = mainWindow.spectrumWindowIds
                            var wid = ids[datasetName]
                            if (!forceNewWindow && wid
                                    && toolWindowManager.hasWindow(wid)) {
                                toolWindowManager.updateGraphWindow(
                                    wid, title, curves, xl, yl)
                            } else {
                                wid = toolWindowManager.openGraphWindow(
                                    title, curves, xl, yl)
                                ids[datasetName] = wid
                                mainWindow.spectrumWindowIds = ids
                            }
                        })
                        mew.openMultiDatasetSpectraRequested.connect(function(datasetSpectraList, forceNewWindow) {
                            console.log("Open multi-dataset spectra requested:", datasetSpectraList.length, "datasets")
                            openMultiDatasetSpectra(datasetSpectraList, forceNewWindow || false)
                        })

                        // Process any pending operations (properties live on
                        // the root mainWindow so they're accessible from any
                        // backend signal handler — see comment near the
                        // declaration of _pendingMapLoad).
                        if (mainWindow._pendingMapLoad) {
                            mew.loadMap(mainWindow._pendingMapLoad)
                            mainWindow._pendingMapLoad = ""
                        }
                        if (mainWindow._pendingMapLoadById && mew.mapEditorBackend) {
                            mew.mapEditorBackend.loadMapById(mainWindow._pendingMapLoadById)
                            mainWindow._pendingMapLoadById = ""
                        }
                        if (mainWindow._pendingLineScan) {
                            mew.loadDatasetAsLineScan(mainWindow._pendingLineScan)
                            mainWindow._pendingLineScan = ""
                        }

                        console.log("MapEditorWorkstation lazy-loaded and initialized")
                    }
                }
            }

            // Convenience accessor (kept as a property for any inner QML
            // child that reads it via parent-chain). Signal handlers at the
            // ApplicationWindow level use ``mapEditorLoader.item`` directly,
            // because property lookup from JS functions doesn't traverse
            // up into nested items the way property bindings do.
            property var mapEditorWorkstation: mapEditorLoader.item

        }  // StackLayout

            // Embedded tool windows manager (overlays workspace canvas, not the tool palette)
            WindowManager {
                id: toolWindowManager
                visible: currentTabIndex === 0
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                anchors.left: parent.left
                anchors.leftMargin: {
                    if (currentTabIndex !== 0) return 0
                    if (!workspace.showLeftPanel) return 0
                    return workspace.leftCollapsed ? 32 : workspace.leftPanelWidth
                }
                // Backend is wired in ApplicationWindow's Component.onCompleted
                // (further up in this file). ``backend: backend`` doesn't
                // work because the RHS resolves to the local property,
                // and Component.onCompleted INSIDE WindowManager has the
                // same scoping issue.
                z: 50  // Above workspace content

                onWindowOpened: function(windowId, windowType) {
                    // Add to ProjectBrowser models
                    var info = toolWindowManager.getWindow(windowId)
                    var title = info ? info.title : windowId
                    if (windowType === "table") {
                        projectBrowser.addTableEntry(windowId, title)
                    } else if (windowType === "graph") {
                        projectBrowser.addGraphEntry(windowId, title)
                    }
                }

                onWindowClosed: function(windowId) {
                    // Remove from open tools tracking
                    var tools = openTools.slice()
                    for (var i = tools.length - 1; i >= 0; i--) {
                        if (tools[i].windowId === windowId) {
                            tools.splice(i, 1)
                            break
                        }
                    }
                    openTools = tools
                    // Also notify ProjectBrowser
                    projectBrowser.removeWindowEntry(windowId)
                }
            }
        }  // Item (workspaceContainer)

        // Debug Console (toggleable)
        DebugConsole {
            id: debugConsole
            Layout.fillWidth: true
            Layout.preferredHeight: 200
            Layout.minimumHeight: 100
            Layout.maximumHeight: 400
            visible: false  // Hidden by default, toggle with Ctrl+D
        }

        // Status bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: bgDarker

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 5
                spacing: 10

                // Visual busy indicator
                BusyIndicator {
                    id: busyIndicator
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    visible: backend.isBusy
                    running: backend.isBusy

                    contentItem: Item {
                        implicitWidth: 20
                        implicitHeight: 20

                        Rectangle {
                            id: spinner
                            width: 16
                            height: 16
                            radius: 8
                            border.color: accentPink
                            border.width: 2
                            color: "transparent"
                            anchors.centerIn: parent

                            Rectangle {
                                width: 4
                                height: 4
                                radius: 2
                                color: accentPink
                                x: parent.width / 2 - 2
                                y: 2
                            }

                            RotationAnimation on rotation {
                                running: busyIndicator.running
                                loops: Animation.Infinite
                                from: 0
                                to: 360
                                duration: 1000
                            }
                        }
                    }
                }

                Text {
                    id: statusText
                    text: backend.status
                    Layout.fillWidth: true
                    color: backend.isBusy ? accentPink : textLight
                    font.pixelSize: 12
                    font.bold: backend.isBusy
                }

                ProgressBar {
                    id: progressBar
                    Layout.preferredWidth: 200
                    visible: value > 0 && value < 1
                    from: 0
                    to: 1
                    value: 0

                    background: Rectangle {
                        implicitWidth: 200
                        implicitHeight: 6
                        color: bgLight
                        radius: 3
                        border.color: borderColor
                        border.width: 1
                    }

                    contentItem: Item {
                        implicitWidth: 200
                        implicitHeight: 6

                        Rectangle {
                            width: progressBar.visualPosition * parent.width
                            height: parent.height
                            radius: 3
                            color: accentPink
                        }
                    }

                    Connections {
                        target: backend
                        function onProgressChanged(current, total, message) {
                            if (total > 0) {
                                progressBar.value = current / total
                            }
                        }
                    }
                }

                Text {
                    id: datasetText
                    text: backend.activeDataset ? "Dataset: " + backend.activeDataset : "No data loaded"
                    color: backend.activeDataset ? accentBlue : textMuted
                    font.pixelSize: 12
                }
            }
        }
            }  // ColumnLayout
        }  // Item (Main workspace)
    }  // SplitView

    // About dialog
    Dialog {
        id: aboutDialog
        title: "About TRANS-QML"
        standardButtons: Dialog.Ok

        Label {
            text: "TRANS-QML\nHyperspectral Data Analysis Platform\n\nVersion 1.0\n\nResearch Software"
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // Shown when the user tries to close the app while a background worker
    // (project save, long-running tool, etc.) is still active.
    Dialog {
        id: busyCloseDialog
        title: "Operation in progress"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 440
        closePolicy: Popup.NoAutoClose

        Label {
            width: parent.width
            wrapMode: Text.Wrap
            text: "TRANS is still working on \"" + (backend ? backend.getCurrentOperation() : "") +
                  "\".\n\nQuitting now will cancel it and any unsaved work may be lost. " +
                  "You can keep working and try again once it finishes."
        }

        footer: DialogButtonBox {
            Button {
                text: "Keep Working"
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
            Button {
                text: "Cancel & Quit"
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            }
        }

        onRejected: close()
        onAccepted: {
            // Cancel the worker, mark force-close, then re-issue the close.
            backend.cancelAllOperations()
            mainWindow._forceClose = true
            close()
            Qt.callLater(function() { mainWindow.close() })
        }
    }

    // Backend connections
    Connections {
        target: backend

        function onToolOpened(toolName) {
            console.log("Tool opened:", toolName)
        }

        function onDataLoaded(datasetName) {
            console.log("Data loaded:", datasetName)
            statusText.text = "Loaded: " + datasetName

            // Refresh Map Editor datasets when new data is loaded (coalesced)
            mainWindow.scheduleMapEditorRelink()
        }

        function onToolCompleted(toolName, outputPath) {
            console.log("Tool completed:", toolName, "output:", outputPath)
            // Refresh Map Editor dataset links after tool completion
            mainWindow.scheduleMapEditorRelink()
        }

        function onErrorOccurred(title, message) {
            errorDialog.title = title
            errorDialog.text = message
            errorDialog.open()
        }

        function onProgressChanged(current, total, message) {
            progressDialog.current = current
            progressDialog.total = total
            progressDialog.message = message

            if (current === total) {
                progressDialog.close()
            } else if (!progressDialog.visible) {
                progressDialog.open()
            }
        }

        function onImageImported(mapName, filePath, mapId) {
            console.log("Image imported:", mapName, "from", filePath)
            tabBar.currentIndex = 1
            currentTabIndex = 1
            mapEditorLoader.ensureLoaded()
            var mew = mapEditorLoader.item
            if (mew) {
                mew.loadMap(filePath)
            } else {
                mainWindow._pendingMapLoad = filePath
            }
        }

        // Open a line scan / point-set dataset in the Hyperspectral tab.
        function onOpenInHyperspectralRequested(datasetName) {
            console.log("Open in Hyperspectral:", datasetName)
            tabBar.currentIndex = 1
            currentTabIndex = 1
            mapEditorLoader.ensureLoaded()
            var mew = mapEditorLoader.item
            if (mew) {
                mew.loadDatasetAsLineScan(datasetName)
            } else {
                mainWindow._pendingLineScan = datasetName
            }
        }

        function onLoadMapInEditor(mapPath) {
            console.log("Loading map in editor:", mapPath)
            tabBar.currentIndex = 1
            currentTabIndex = 1
            mapEditorLoader.ensureLoaded()
            var mew = mapEditorLoader.item
            if (mew) {
                if (mew.openMaps && mew.openMaps.length > 0) {
                    mew.forceCloseMap(mew.activeMapIndex)
                }
                mew.loadMap(mapPath)
            } else {
                mainWindow._pendingMapLoad = mapPath
            }
        }

        function onLoadMapInEditorById(mapId) {
            console.log("Loading in-memory map in editor: id=", mapId)
            tabBar.currentIndex = 1
            currentTabIndex = 1
            mapEditorLoader.ensureLoaded()
            var mew = mapEditorLoader.item
            if (mew && mew.mapEditorBackend) {
                if (mew.openMaps && mew.openMaps.length > 0) {
                    mew.forceCloseMap(mew.activeMapIndex)
                }
                mew.mapEditorBackend.loadMapById(mapId)
            } else {
                mainWindow._pendingMapLoadById = mapId
            }
        }
    }

    // Workflow manager connections
    Connections {
        target: backend ? backend.workflowManager : null

        function onWorkflowSaved(path) {
            console.log("Workflow saved:", path)
            refreshProjectWorkflows()
        }
    }

    // Error dialog
    Dialog {
        id: errorDialog
        property alias text: errorLabel.text
        standardButtons: Dialog.Ok
        modal: true
        width: 400

        Label {
            id: errorLabel
            width: parent.width - 40
            wrapMode: Text.Wrap
        }
    }

    // Progress dialog
    Dialog {
        id: progressDialog
        property int current: 0
        property int total: 1
        property string message: ""

        title: "Loading..."
        modal: true
        closePolicy: Popup.NoAutoClose
        width: 350

        ColumnLayout {
            width: parent.width - 40
            spacing: 10

            Label {
                text: progressDialog.message
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }

            ProgressBar {
                Layout.fillWidth: true
                from: 0
                to: progressDialog.total
                value: progressDialog.current
            }
        }
    }

    // Coalesced Map-Editor relink. Every import and every tool completion
    // wants the editor's dataset links refreshed, and that refresh walks the
    // whole dataset registry — so a queue of imports must not trigger one
    // full relink per import (that is what made batch Matrix imports get
    // slower and slower). Only runs if the editor has actually been loaded.
    Timer {
        id: mapEditorRelinkTimer
        interval: 250
        repeat: false
        onTriggered: {
            var mew = mapEditorLoader.item
            if (mew) mew.linkDatasetsFromBackend(backend)
        }
    }

    function scheduleMapEditorRelink() {
        if (mapEditorLoader.item)
            mapEditorRelinkTimer.restart()
    }

    // Functions
    function getToolsForCurrentTab() {
        // Reuse the reactive currentTools property
        return currentTools
    }

    // Tools usable from more than one tab must not yank the user back to
    // Spectral, and a tool with a plot needs more room than a form does.
    property var multiTabTools: ({ "Confinement Analysis": true, "Spectral Features": true })
    property var toolWindowSizes: ({ "Confinement Analysis": { width: 1000, height: 700 },
                                     "Spectral Features": { width: 1020, height: 720 } })

    function toolWindowSize(toolName) {
        return toolWindowSizes[toolName] || { width: 450, height: 550 }
    }

    function openToolWindow(toolName) {
        console.log("Opening tool:", toolName)

        // Switch to spectral analysis tab if not already there
        if (currentTabIndex !== 0 && !multiTabTools[toolName]) {
            tabBar.currentIndex = 0
        }

        // Map tool names to QML file paths
        var toolMap = {
            "1D FFT": "../tools/FFT1DTool.qml",
            "Curve Smoothing": "../tools/CurveSmoothingTool.qml",
            "Image Smoothing": "../tools/ImageSmoothingTool.qml",
            "Derivative Calculator": "../tools/DerivativeTool.qml",
            "Gradient Filter": "../tools/GradientTool.qml",
            "Curve Fitting": "../tools/CurveFittingTool.qml",
            "Integration Utility": "../tools/IntegrationTool.qml",
            "Map Generator": "../tools/MapGeneratorTool.qml",
            "Spatial Average": "../tools/SpatialAverageTool.qml",
            "Map Discretizer": "../tools/MapDiscretizerTool.qml",
            "Map Processing": "../tools/MapProcessingTool.qml",
            "Curve Analysis": "../tools/CurveAnalysisTool.qml",
            "Truncate Data": "../tools/TruncateTool.qml",
            "Confinement Analysis": "../tools/ConfinementAnalysisTool.qml",
            "Spectral Features": "../tools/SpectralFeaturesTool.qml",
            "Peak Indexing": "../tools/PeakIndexingTool.qml",
            "Filter Bad Data": "../tools/FilterBadDataTool.qml",
            "Cosmic Ray Filter": "../tools/CosmicRayFilterTool.qml",
            "Background Subtraction": "../tools/BackgroundSubtractionTool.qml",
            "Average Curves": "../tools/AverageCurvesTool.qml",
            "Dirac Point Estimator": "../tools/DiracPointEstimatorTool.qml",
            "Detect Bandgap & Doping": "../tools/DetectBandgapDopingTool.qml",
            "Spectral Axis Converter": "../tools/SpectralAxisConvertTool.qml",
            "Multi-Peak Fitting": "../tools/MultiPeakFitTool.qml"
        }

        var toolPath = toolMap[toolName] || "../tools/GenericToolUI.qml"
        var component = Qt.createComponent(toolPath)
        if (component.status === Component.Ready) {
            var size = toolWindowSize(toolName)
            var windowId = toolWindowManager.createToolWindow(toolName, component, {
                width: size.width,
                height: size.height
            })
            if (windowId) {
                var tools = openTools.slice()
                tools.push({ name: toolName, windowId: windowId })
                openTools = tools
            }
        } else if (component.status === Component.Error) {
            console.error("Error loading tool:", toolName, component.errorString())
        } else {
            // Component is still loading, wait for it
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    var size2 = toolWindowSize(toolName)
                    var wid = toolWindowManager.createToolWindow(toolName, component, {
                        width: size2.width,
                        height: size2.height
                    })
                    if (wid) {
                        var t = openTools.slice()
                        t.push({ name: toolName, windowId: wid })
                        openTools = t
                    }
                }
            })
        }
    }

    // Track the main spectrum plot window ID (reused for click-to-plot)
    property string mainSpectrumWindowId: ""
    // Per-source spectrum windows (datasetName → windowId), so e.g. the STS
    // dots' Forward / Backward / Mixed each reuse their own window.
    property var spectrumWindowIds: ({})

    // Expose the WindowManager so embedded table contents can create graph windows
    function getToolWindowManager() { return toolWindowManager }

    // Open spectra from multiple datasets at once
    function openMultiDatasetSpectra(datasetSpectraList, forceNewWindow) {
        // datasetSpectraList is array of {datasetName, spectra}
        if (datasetSpectraList.length === 0) return

        // Combine all spectra into curves
        var curves = []
        var combinedName = []
        for (var i = 0; i < datasetSpectraList.length; i++) {
            var ds = datasetSpectraList[i]
            combinedName.push(ds.datasetName)
            for (var j = 0; j < ds.spectra.length; j++) {
                var s = ds.spectra[j]
                curves.push({
                    x: s.x, y: s.y,
                    label: s.title || (ds.datasetName + " " + (j+1)),
                    color: ""
                })
            }
        }

        var title = combinedName.join(" + ") + " Spectra"
        var xl = datasetSpectraList[0].spectra[0].x_name || "X"
        var yl = datasetSpectraList[0].spectra[0].y_name || "Intensity"

        if (!forceNewWindow && mainSpectrumWindowId
                && toolWindowManager.hasWindow(mainSpectrumWindowId)) {
            toolWindowManager.updateGraphWindow(mainSpectrumWindowId, title, curves, xl, yl)
        } else {
            mainSpectrumWindowId = toolWindowManager.openGraphWindow(title, curves, xl, yl)
        }
    }

    // Track open workflow windows
    property var openWorkflowWindows: []

    // Create, register and show a WorkflowWindow. All workflow windows MUST
    // go through here so they are tracked in openWorkflowWindows (otherwise
    // they outlive the main window on shutdown).
    function _createWorkflowWindow(props) {
        var component = Qt.createComponent("../workflow/WorkflowWindow.qml")

        function instantiate() {
            var window = component.createObject(mainWindow, props)
            if (window) {
                openWorkflowWindows.push(window)
                window.closing.connect(function() {
                    var idx = openWorkflowWindows.indexOf(window)
                    if (idx >= 0) openWorkflowWindows.splice(idx, 1)
                })
                if (props.workflowId) {
                    window.refreshWorkflow()
                }
                window.show()
                console.log("Workflow window created successfully")
            } else {
                console.error("Failed to create workflow window object")
            }
            return window
        }

        if (component.status === Component.Ready) {
            return instantiate()
        } else if (component.status === Component.Error) {
            console.error("Error creating workflow window:", component.errorString())
        } else {
            console.log("Component loading... status:", component.status)
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    instantiate()
                } else if (component.status === Component.Error) {
                    console.error("Error creating workflow window:", component.errorString())
                }
            })
        }
        return null
    }

    function openWorkflowWindow(workflowName) {
        console.log("Opening workflow:", workflowName)
        return _createWorkflowWindow({
            workflowName: workflowName,
            workflowManager: backend.workflowManager,
            mainWin: mainWindow  // Pass main window for theme colors
        })
    }

    // Open an already-loaded workflow (e.g. from the Load Workflow dialog or
    // the Project Workflows menu) in a tracked, themed window.
    function openWorkflowWindowFromId(workflowId, workflowName) {
        console.log("Opening loaded workflow:", workflowName, "id:", workflowId)
        return _createWorkflowWindow({
            workflowId: workflowId,
            workflowName: workflowName,
            workflowManager: backend.workflowManager,
            mainWin: mainWindow  // Pass main window for theme colors
        })
    }

    function refreshProjectWorkflows() {
        projectWorkflowsModel.clear()
        if (backend && backend.workflowManager) {
            var workflows = backend.workflowManager.getSavedWorkflows()
            for (var i = 0; i < workflows.length; i++) {
                projectWorkflowsModel.append({
                    name: workflows[i].name,
                    path: workflows[i].path
                })
            }
        }
    }

    function closeAllWorkflowWindows() {
        console.log("Closing all workflow windows, count:", openWorkflowWindows.length)
        // Detach the list first: each close() fires the window's closing
        // handler, which splices openWorkflowWindows — iterating the live
        // array made openWorkflowWindows[i] undefined mid-loop and left
        // windows alive after the main window closed.
        var windows = openWorkflowWindows
        openWorkflowWindows = []
        for (var i = 0; i < windows.length; i++) {
            var w = windows[i]
            if (!w) continue
            try {
                w.visible = false
                w.close()
                w.destroy()
            } catch (e) {
                console.log("Error closing workflow window:", e)
            }
        }
    }

    // Dialogs — lazy loaded to reduce startup time
    Loader {
        id: importMeasurementLoader
        active: false
        source: "../dialogs/ImportMeasurementDialog.qml"
        property bool openOnLoad: false
        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            if (openOnLoad) { openOnLoad = false; item.open() }
        }
    }

    // Preferences Dialog — lazy loaded (1174 lines, only needed on user action)
    Loader {
        id: preferencesLoader
        active: false
        source: "../dialogs/PreferencesDialog.qml"
        property bool openOnLoad: false

        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            item.preferencesManager = backend.preferencesManager
            item.bgDark = Qt.binding(function() { return mainWindow.bgDark })
            item.bgMedium = Qt.binding(function() { return mainWindow.bgMedium })
            item.bgLight = Qt.binding(function() { return mainWindow.bgLight })
            item.textLight = Qt.binding(function() { return mainWindow.textLight })
            item.textMuted = Qt.binding(function() { return mainWindow.textMuted })
            item.borderColor = Qt.binding(function() { return mainWindow.borderColor })
            item.accentPink = Qt.binding(function() { return mainWindow.accentPink })
            item.accentBlue = Qt.binding(function() { return mainWindow.accentBlue })
            console.log("[TIMING] PreferencesDialog lazy-loaded")
            if (openOnLoad) {
                openOnLoad = false
                item.open()
            }
        }
    }

    function openPreferencesDialog() {
        if (preferencesLoader.item) {
            preferencesLoader.item.open()
        } else {
            preferencesLoader.openOnLoad = true
            preferencesLoader.active = true
        }
    }

    // Generic helper for lazy-loaded dialogs
    function openLazyDialog(loader) {
        if (loader.item) {
            loader.item.open()
        } else {
            loader.openOnLoad = true
            loader.active = true
        }
    }

    // Import Image Dialog
    Platform.FileDialog {
        id: importImageDialog
        title: "Import Image"
        nameFilters: [
            "Image Files (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.gsf *.npy)",
            "TIFF Files (*.tif *.tiff)",
            "PNG Files (*.png)",
            "JPEG Files (*.jpg *.jpeg)",
            "Gwyddion Files (*.gsf)",
            "NumPy Files (*.npy)",
            "All Files (*)"
        ]
        fileMode: Platform.FileDialog.OpenFile

        onAccepted: {
            var path = file.toString()
            // file:///path -> /path (preserve leading slash for absolute paths)
            if (path.startsWith("file:///")) {
                path = path.substring(7)  // "file:///" is 7 chars, leaves "/path"
            } else if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            console.log("Importing image:", path)
            backend.importImage(path)
        }
    }

    Loader {
        id: saveLayoutLoader
        active: false
        source: "../dialogs/SaveLayoutDialog.qml"
        property bool openOnLoad: false
        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            if (openOnLoad) { openOnLoad = false; item.open() }
        }
    }

    Loader {
        id: loadLayoutLoader
        active: false
        source: "../dialogs/LoadLayoutDialog.qml"
        property bool openOnLoad: false
        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            if (openOnLoad) { openOnLoad = false; item.open() }
        }
    }

    Loader {
        id: loadWorkflowLoader
        active: false
        source: "../dialogs/LoadWorkflowDialog.qml"
        property bool openOnLoad: false
        property string pendingPath: ""
        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            if (pendingPath) {
                var p = pendingPath; pendingPath = ""
                item.loadWorkflowFromFile(p)
            }
            if (openOnLoad) { openOnLoad = false; item.open() }
        }
    }

    // Project Startup Dialog — lazy loaded
    Loader {
        id: startupDialogLoader
        active: false
        source: "../dialogs/ProjectStartupDialog.qml"
        onLoaded: {
            item.anchors.centerIn = Overlay.overlay
            item.projectCreated.connect(function(projectPath, projectName) {
                console.log("Creating project:", projectName, "at", projectPath)
                backend.createProject(projectPath, projectName)
            })
            item.projectOpened.connect(function(projectPath, projectName) {
                console.log("Opening project:", projectName, "at", projectPath)
                backend.openProject(projectPath, projectName)
            })
            item.dialogCancelled.connect(function() {
                console.log("Project dialog cancelled, quitting...")
            })
            item.open()
        }
    }
    property var projectStartupDialog: startupDialogLoader.item

    // Close startup dialog whenever a project becomes ready
    Connections {
        target: backend
        function onProjectReadyChanged() {
            if (backend.projectReady && projectStartupDialog && projectStartupDialog.visible) {
                projectStartupDialog.close()
            }
            // Editors from the previous project reference workflows that were
            // just cleared in the backend — close them, then repopulate the
            // Workflows menu from the (new) project's workflows dir
            closeAllWorkflowWindows()
            if (backend.projectReady) {
                refreshProjectWorkflows()
            }
        }
    }

    // Overlay when no project is open (blocks interaction)
    Rectangle {
        id: noProjectOverlay
        anchors.fill: parent
        color: "#cc000000"
        visible: !backend.projectReady
        z: 1000

        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (!projectStartupDialog || !projectStartupDialog.visible) {
                    startupDialogLoader.active = true
                    if (projectStartupDialog) projectStartupDialog.open()
                }
            }
        }

        Column {
            anchors.centerIn: parent
            spacing: 20

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "No Project Open"
                font.pixelSize: 24
                font.bold: true
                color: accentPink
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Click anywhere to open or create a project"
                font.pixelSize: 14
                color: textMuted
            }
        }
    }

    // Save Project As dialog
    Platform.FileDialog {
        id: saveProjectDialog
        title: "Save Project As"
        nameFilters: ["TRANS-QML Project (*.hrt)"]
        fileMode: Platform.FileDialog.SaveFile
        defaultSuffix: "hrt"

        onAccepted: {
            var path = file.toString()
            // file:///path -> /path (preserve leading slash for absolute paths)
            if (path.startsWith("file:///")) {
                path = path.substring(7)  // "file:///" is 7 chars, leaves "/path"
            } else if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            console.log("Saving project to:", path)
            backend.saveProjectFile(path)
        }
    }

    // Large dataset confirmation dialog
    Dialog {
        id: largeDatasetDialog
        title: "Large Dataset Detected"
        modal: true
        width: 450
        standardButtons: Dialog.Yes | Dialog.No

        property string datasetName: ""
        property int numSpectra: 0
        property int numPoints: 0

        background: Rectangle {
            color: bgMedium
            border.color: accentPink
            border.width: 1
            radius: 5
        }

        contentItem: ColumnLayout {
            spacing: 15

            RowLayout {
                spacing: 10

                Rectangle {
                    width: 40
                    height: 40
                    radius: 20
                    color: "#FFB7C5"

                    Text {
                        anchors.centerIn: parent
                        text: "!"
                        color: bgDark
                        font.pixelSize: 24
                        font.bold: true
                    }
                }

                Text {
                    text: "Large Dataset"
                    color: textLight
                    font.pixelSize: 16
                    font.bold: true
                }
            }

            Text {
                text: "The dataset \"" + largeDatasetDialog.datasetName + "\" is large:"
                color: textLight
                font.pixelSize: 13
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }

            Rectangle {
                Layout.fillWidth: true
                height: 60
                color: bgDark
                radius: 5

                Column {
                    anchors.centerIn: parent
                    spacing: 5

                    Text {
                        text: largeDatasetDialog.numSpectra.toLocaleString() + " spectra"
                        color: accentBlue
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Text {
                        text: largeDatasetDialog.numPoints.toLocaleString() + " data points each"
                        color: textMuted
                        font.pixelSize: 12
                    }
                }
            }

            Text {
                text: "Opening this dataset may take some time and use significant memory.\n\nDo you want to continue?"
                color: textMuted
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }

        onAccepted: {
            backend.confirmOpenLargeDataset(datasetName)
        }

        onRejected: {
            backend.cancelOpenLargeDataset(datasetName)
        }
    }

    // Connection for large dataset signal
    Connections {
        target: backend

        function onLargeDatasetConfirmation(datasetName, numSpectra, numPoints) {
            largeDatasetDialog.datasetName = datasetName
            largeDatasetDialog.numSpectra = numSpectra
            largeDatasetDialog.numPoints = numPoints
            largeDatasetDialog.open()
        }
    }

    // ========== UNDO/REDO KEYBOARD SHORTCUTS ==========
    Shortcut {
        sequence: StandardKey.Undo
        onActivated: if (backend.undoManager && backend.undoManager.canUndo) backend.undoManager.undo()
    }

    Shortcut {
        sequence: StandardKey.Redo
        onActivated: if (backend.undoManager && backend.undoManager.canRedo) backend.undoManager.redo()
    }

    // ========== PROJECT STATE RESTORATION ==========
    Connections {
        target: backend

        function onProjectStateRestored(stateJson) {
            var state = JSON.parse(stateJson)
            // Restore graph windows
            if (state.graphs) {
                for (var i = 0; i < state.graphs.length; i++) {
                    var g = state.graphs[i]
                    toolWindowManager.createEnhancedGraphWindow(g.title || g.id || "Graph", {
                        curves: g.curves || [],
                        xLabel: g.xLabel,
                        yLabel: g.yLabel,
                        width: g.width,
                        height: g.height
                    })
                }
            }
            // Restore table windows. Field names match the save side
            // (`headers`, `dataRows`) — earlier code read `data` / `columns`
            // and silently restored empty tables.
            if (state.tables) {
                for (var j = 0; j < state.tables.length; j++) {
                    var t = state.tables[j]
                    var rows = t.dataRows || t.data || []
                    var cols = t.headers || t.columns || []
                    backend.restoreTableFromState(
                        t.title || t.id || "Table", rows, cols)
                }
            }
            // Restore image windows by id (image entities themselves were
            // already loaded from the .hrt by the time this signal fires).
            if (state.image_windows) {
                for (var k = 0; k < state.image_windows.length; k++) {
                    var iw = state.image_windows[k]
                    if (iw.imageId) {
                        toolWindowManager.openImageWindow(
                            iw.title || "Image", iw.imageId)
                    }
                }
            }
        }
    }

    // ========== EMBEDDED DATASET WINDOWS ==========
    Connections {
        target: backend

        function onOpenDatasetEmbedded(name, curves, xLabel, yLabel) {
            if (currentTabIndex !== 0) tabBar.currentIndex = 0
            // The window's stable dataset identity is the dataset name.
            toolWindowManager.openGraphWindow(name, curves, xLabel, yLabel, name)
        }

        // A dataset operation produced a derived result: overlay it onto the
        // source dataset's open graph window, or open a new window if the
        // source isn't currently shown.
        function onDisplayDerivedDataset(source, result, curves, xLabel, yLabel) {
            if (currentTabIndex !== 0) tabBar.currentIndex = 0
            var wid = toolWindowManager.findGraphWindowByDataset(source)
            if (wid) {
                toolWindowManager.addCurvesToGraphWindow(wid, curves)
            } else {
                toolWindowManager.openGraphWindow(result, curves, xLabel, yLabel, result)
            }
        }

        function onOpenTableEmbedded(title, tableModel) {
            if (currentTabIndex !== 0) tabBar.currentIndex = 0
            toolWindowManager.createEnhancedTableWindow(title, {tableModel: tableModel})
        }

        function onOpenImageEmbedded(title, imageId) {
            if (currentTabIndex !== 0) tabBar.currentIndex = 0
            toolWindowManager.openImageWindow(title, imageId)
        }

        function onOpenNoteEmbedded(title, body, source) {
            if (currentTabIndex !== 0) tabBar.currentIndex = 0
            toolWindowManager.openNoteWindow(title, body, source)
        }

        function onCollectWindowStatesRequested() {
            var states = toolWindowManager.getWindowStates()
            backend.setEmbeddedWindowStates(states)
        }
    }

    // ========== AUTOSAVE RECOVERY DIALOG ==========
    Dialog {
        id: recoveryDialog
        title: "Autosave Recovery"
        modal: true
        width: 450
        height: 220
        anchors.centerIn: Overlay.overlay

        property string autosavePath: ""
        property string mainPath: ""

        background: Rectangle {
            color: bgDark
            border.color: borderColor
            border.width: 1
            radius: 8
        }

        header: Rectangle {
            color: bgMedium
            height: 45
            radius: 8

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: parent.radius
                color: parent.color
            }

            Text {
                anchors.centerIn: parent
                text: "Autosave Recovery"
                font.pixelSize: 16
                font.bold: true
                color: textLight
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 12

            Text {
                text: "A more recent autosave was found for this project."
                color: textLight
                font.pixelSize: 13
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }

            Text {
                text: "Would you like to recover from the autosave, or discard it and use the last manually saved version?"
                color: textMuted
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }

        footer: Rectangle {
            color: bgMedium
            height: 55
            radius: 8

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10

                Item { Layout.fillWidth: true }

                Button {
                    text: "Discard"
                    Layout.preferredWidth: 100

                    background: Rectangle {
                        color: parent.hovered ? bgLight : "transparent"
                        border.color: borderColor
                        radius: 4
                    }

                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        backend.autosaveManager.discardAutosave(recoveryDialog.autosavePath)
                        recoveryDialog.close()
                    }
                }

                Button {
                    text: "Recover"
                    Layout.preferredWidth: 100

                    background: Rectangle {
                        color: parent.hovered ? accentPink : accentBlue
                        radius: 4
                    }

                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }

                    onClicked: {
                        backend.autosaveManager.recoverFromAutosave(recoveryDialog.autosavePath)
                        recoveryDialog.close()
                    }
                }
            }
        }
    }

    // Connection for autosave recovery
    Connections {
        target: backend.autosaveManager

        function onRecoveryAvailable(autosavePath, mainPath) {
            recoveryDialog.autosavePath = autosavePath
            recoveryDialog.mainPath = mainPath
            recoveryDialog.open()
        }
    }
}
