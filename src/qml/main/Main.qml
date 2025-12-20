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
import "../dialogs"
import "../workflow"
import "../map_editor"
import TransQML 1.0

ApplicationWindow {
    id: mainWindow
    objectName: "mainWindow"  // Used by child windows to find this window for theme colors
    visible: true
    width: 1400
    height: 900
    title: backend.projectReady ? "TRANS-QML - " + backend.projectName : "TRANS-QML - Hyperspectral Data Analysis"

    // Close all child windows when main window closes
    onClosing: function(close) {
        closeAllWorkflowWindows()
        backend.closeAllWindows()
        close.accepted = true
    }

    // Project state
    property bool projectReady: backend.projectReady

    // Track open tool windows
    property var openTools: []
    property int currentTabIndex: 0

    // Show startup dialog on launch and apply saved color scheme
    Component.onCompleted: {
        // Apply saved color scheme from preferences
        applyColorScheme()

        if (!backend.projectReady) {
            projectStartupDialog.open()
        }
    }

    // Reactive tools list based on current tab
    // Tab indices: 0=STS, 1=SNOM, 2=Map, 3=Workflow
    property var currentTools: {
        if (currentTabIndex === 0) {
            return [
                "1D FFT",
                "Curve Smoothing",
                "Derivative Calculator",
                "Curve Fitting",
                "Integration Utility",
                "Map Generator",
                "Spatial Average",
                "Truncate Data",
                "Curve Analysis"
            ]
        } else if (currentTabIndex === 1) {
            return [
                "1D FFT",
                "2D FFT",
                "Curve Smoothing",
                "Image Smoothing",
                "Derivative Calculator",
                "Gradient Filter",
                "Integration Utility",
                "Map Generator",
                "Truncate Data",
                "Curve Analysis"
            ]
        } else if (currentTabIndex === 2) {
            return [
                "2D FFT",
                "Image Smoothing",
                "Gradient Filter",
                "Map Discretizer"
            ]
        } else {
            // Workflow mode - no separate tools menu, tools are in the palette
            return []
        }
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

    // ========== FONT SCALING ==========
    // Global font sizes - components should reference these for consistent scaling
    property int fontSizeSmall: 10
    property int fontSizeMedium: 12
    property int fontSizeLarge: 14
    property int fontSizeHeader: 16
    property int fontSizeTitle: 18
    property string fontFamily: "system-ui"

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
            fontFamily = scheme.font.family || "system-ui"
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

        // T.R.A.N.S. application menu (first menu like on macOS)
        Menu {
            title: "T.R.A.N.S."
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
                onTriggered: preferencesDialog.open()
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
                onTriggered: importMeasurementDialog.open()
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

            // STS Analysis tools (tab 0)
            MenuItem {
                text: "1D FFT"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "2D FFT"
                visible: currentTabIndex === 1 || currentTabIndex === 2
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Curve Smoothing"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Image Smoothing"
                visible: currentTabIndex === 1 || currentTabIndex === 2
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Derivative Calculator"
                visible: currentTabIndex === 0 || currentTabIndex === 1
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
                visible: currentTabIndex === 1 || currentTabIndex === 2
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Integration Utility"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Generator"
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Discretizer"
                visible: currentTabIndex === 2
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Map Processing"
                visible: currentTabIndex === 2
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
                visible: currentTabIndex === 0 || currentTabIndex === 1
                height: visible ? implicitHeight : 0
                onTriggered: openToolWindow(text)
            }
            MenuItem {
                text: "Curve Analysis"
                visible: currentTabIndex === 0 || currentTabIndex === 1
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

            // Preset workflows section
            MenuItem {
                text: "Presets"
                enabled: false
                contentItem: Text {
                    text: "— Presets —"
                    font.pixelSize: 11
                    font.italic: true
                    color: textMuted
                    leftPadding: 10
                }
            }
            MenuItem {
                text: "STS Analysis Workflow"
                enabled: currentTabIndex === 0
                onTriggered: openWorkflowWindow("STS Analysis")
            }
            MenuItem {
                text: "SNOM Analysis Workflow"
                enabled: currentTabIndex === 1
                onTriggered: openWorkflowWindow("SNOM Analysis")
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
                        loadWorkflowDialog.loadWorkflowFromFile(workflowMenuItem.path)
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
                onTriggered: loadWorkflowDialog.open()
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
                onTriggered: saveLayoutDialog.open()
            }
            MenuItem {
                text: "Load Layout..."
                onTriggered: loadLayoutDialog.open()
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
                onTriggered: {
                    console.log("Cascade Windows")
                    // TODO: Implement cascade windows
                }
            }
            MenuItem {
                text: "Tile Windows"
                enabled: openTools.length > 0
                onTriggered: {
                    console.log("Tile Windows")
                    // TODO: Implement tile windows
                }
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
                    text: "  " + modelData
                    onTriggered: {
                        console.log("Focus tool:", modelData)
                        // TODO: Bring tool window to front
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
                text: "Documentation"
                onTriggered: Qt.openUrlExternally("file:///" + backend.getOutputDirectory() + "/../docs")
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

        // Project Browser (left side) - hidden in Workflow mode
        Rectangle {
            SplitView.minimumWidth: currentTabIndex === 3 ? 0 : 200
            SplitView.preferredWidth: currentTabIndex === 3 ? 0 : 280
            SplitView.maximumWidth: currentTabIndex === 3 ? 0 : 400
            visible: currentTabIndex !== 3
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

                        // Dock position selector
                        ComboBox {
                            id: dockPositionCombo
                            Layout.preferredWidth: 120
                            model: ["Left", "Right", "Top", "Bottom"]
                            currentIndex: 0

                            background: Rectangle {
                                color: bgLight
                                border.color: borderColor
                                radius: 3
                            }

                            contentItem: Text {
                                text: dockPositionCombo.displayText
                                color: textLight
                                font.pixelSize: 12
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
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
                                text: "STS Analysis"
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
                                text: "SNOM Analysis"
                                contentItem: Text {
                                    text: parent.text
                                    font.pixelSize: 14
                                    font.bold: parent.checked
                                    color: parent.checked ? accentBlue : textMuted
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
                                        color: accentBlue
                                    }
                                }
                            }
                            TabButton {
                                text: "Map Editor"
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
                                text: "Workflow"
                                contentItem: Text {
                                    text: parent.text
                                    font.pixelSize: 14
                                    font.bold: parent.checked
                                    color: parent.checked ? accentOrange : textMuted
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
                                        color: accentOrange
                                    }
                                }
                            }
                        }  // TabBar
                    }  // RowLayout
                }  // Rectangle (toolbar)

        // Workspace container - switches between workspaces based on tab
        StackLayout {
            id: workspaceStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            // Tab indices: 0=STS, 1=SNOM, 2=Map, 3=Workflow
            currentIndex: {
                if (currentTabIndex === 2) return 1      // Map Editor
                else if (currentTabIndex === 3) return 2 // Workflow
                else return 0                             // STS/SNOM
            }

            // Unified Workspace (for STS and SNOM tabs)
            UnifiedWorkspace {
                id: workspace
                currentMode: currentTabIndex === 0 ? "sts" : "snom"
                backend: mainWindow.backend
                workflowManager: backend ? backend.workflowManager : null

                // Panel visibility for STS/SNOM modes
                showLeftPanel: false  // ProjectBrowser is in outer SplitView
                showRightPanel: false
                showTopPanel: false
                showBottomPanel: false

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

            // Map Editor Workstation (for Map Editor tab)
            MapEditorWorkstation {
                id: mapEditorWorkstation

                onSpectrumRequested: function(row, col) {
                    console.log("Spectrum requested at:", row, col)
                }

                onBlockSelectionChanged: function(count) {
                    console.log("Block selection changed:", count, "blocks")
                }

                onOpenSpectrumPlotRequested: function(datasetName, spectra, forceNewWindow) {
                    console.log("Open spectrum plot requested:", datasetName, "with", spectra.length, "spectra")
                    openSpectrumPlotWindow(datasetName, spectra, forceNewWindow || false)
                }

                onOpenMultiDatasetSpectraRequested: function(datasetSpectraList, forceNewWindow) {
                    console.log("Open multi-dataset spectra requested:", datasetSpectraList.length, "datasets")
                    openMultiDatasetSpectra(datasetSpectraList, forceNewWindow || false)
                }
            }

            // Workflow Workspace (for Workflow tab)
            UnifiedWorkspace {
                id: workflowWorkspace
                currentMode: "workflow"
                backend: mainWindow.backend
                workflowManager: backend ? backend.workflowManager : null

                // Workflow mode uses internal panels
                showLeftPanel: true   // WorkflowToolPalette
                showRightPanel: true  // For NodeParameterEditor (future)
                showTopPanel: false
                showBottomPanel: false
                leftPanelWidth: 260

                // Handle workflow canvas interactions
                onFloatingEntityAdded: function(entity) {
                    console.log("Workflow entity added:", entity.id, entity.type)
                }

                onFloatingEntityRemoved: function(entityId) {
                    console.log("Workflow entity removed:", entityId)
                }
            }
        }

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
            text: "TRANS-QML\nHyperspectral Data Analysis Platform\n\nVersion 2.0\n\nResearch Software"
            horizontalAlignment: Text.AlignHCenter
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

            // Refresh Map Editor datasets when new data is loaded
            mapEditorWorkstation.linkDatasetsFromBackend(backend)
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
            // Switch to Map Editor tab
            tabBar.currentIndex = 2
            currentTabIndex = 2

            // Load the map data into the Map Editor
            mapEditorWorkstation.loadMap(filePath)
        }

        function onLoadMapInEditor(mapPath) {
            console.log("Loading map in editor:", mapPath)
            // Switch to Map Editor tab
            tabBar.currentIndex = 2
            currentTabIndex = 2

            // Close the current active map if any (force close without save dialog)
            if (mapEditorWorkstation.openMaps && mapEditorWorkstation.openMaps.length > 0) {
                mapEditorWorkstation.forceCloseMap(mapEditorWorkstation.activeMapIndex)
            }

            // Load the new map
            mapEditorWorkstation.loadMap(mapPath)
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

    // Functions
    function getToolsForCurrentTab() {
        // Tab indices: 0=STS, 1=SNOM, 2=Map, 3=Workflow
        if (currentTabIndex === 0) {
            // STS Analysis tools
            return [
                "1D FFT",
                "Curve Smoothing",
                "Derivative Calculator",
                "Curve Fitting",
                "Integration Utility",
                "Map Generator",
                "Spatial Average",
                "Truncate Data",
                "Curve Analysis"
            ]
        } else if (currentTabIndex === 1) {
            // SNOM Analysis tools
            return [
                "1D FFT",
                "2D FFT",
                "Curve Smoothing",
                "Image Smoothing",
                "Derivative Calculator",
                "Gradient Filter",
                "Integration Utility",
                "Map Generator",
                "Truncate Data",
                "Curve Analysis"
            ]
        } else if (currentTabIndex === 2) {
            // Map Editor tools
            return [
                "2D FFT",
                "Image Smoothing",
                "Gradient Filter",
                "Map Discretizer",
                "Map Processing"
            ]
        } else {
            // Workflow mode - tools are accessed via ToolPalette
            return []
        }
    }

    function openToolWindow(toolName) {
        console.log("Opening tool:", toolName)

        // Create tool window component
        var component = Qt.createComponent("../tools/ToolWindow.qml")
        if (component.status === Component.Ready) {
            var window = component.createObject(mainWindow, {
                toolName: toolName,
                parentWindow: mainWindow
            })
            openTools.push(window)
            window.show()
        } else {
            console.error("Error creating tool window:", component.errorString())
        }
    }

    // Track the main spectrum plot window (reused for click-to-plot)
    property var mainSpectrumWindow: null

    // Track additional spectrum windows (for "New Window" action)
    property var additionalSpectrumWindows: []

    function openSpectrumPlotWindow(datasetName, spectra, forceNewWindow) {
        console.log("Spectrum plot requested for:", datasetName, "with", spectra.length, "spectra, forceNew:", forceNewWindow)

        // If we have an existing main window and not forcing new, add to it
        if (!forceNewWindow && mainSpectrumWindow && mainSpectrumWindow.visible) {
            console.log("Adding spectra to existing window")
            for (var i = 0; i < spectra.length; i++) {
                mainSpectrumWindow.addSpectrum(spectra[i])
            }
            mainSpectrumWindow.raise()
            mainSpectrumWindow.requestActivate()
            return
        }

        // Create new window
        var component = Qt.createComponent("../map_editor/SpectrumPlotWindow.qml")
        if (component.status === Component.Ready) {
            var window = component.createObject(mainWindow, {
                datasetName: datasetName,
                spectra: spectra
            })
            if (window) {
                if (forceNewWindow) {
                    // Track as additional window
                    additionalSpectrumWindows.push(window)
                    window.closing.connect(function() {
                        var idx = additionalSpectrumWindows.indexOf(window)
                        if (idx >= 0) additionalSpectrumWindows.splice(idx, 1)
                    })
                } else {
                    // Set as main window
                    mainSpectrumWindow = window
                    window.closing.connect(function() {
                        mainSpectrumWindow = null
                    })
                }
                window.show()
                console.log("Spectrum plot window created successfully")
            } else {
                console.error("Failed to create spectrum plot window object")
            }
        } else if (component.status === Component.Error) {
            console.error("Error creating spectrum plot window:", component.errorString())
        } else {
            // Component loading asynchronously
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    var window = component.createObject(mainWindow, {
                        datasetName: datasetName,
                        spectra: spectra
                    })
                    if (window) {
                        if (forceNewWindow) {
                            additionalSpectrumWindows.push(window)
                            window.closing.connect(function() {
                                var idx = additionalSpectrumWindows.indexOf(window)
                                if (idx >= 0) additionalSpectrumWindows.splice(idx, 1)
                            })
                        } else {
                            mainSpectrumWindow = window
                            window.closing.connect(function() {
                                mainSpectrumWindow = null
                            })
                        }
                        window.show()
                    }
                }
            })
        }
    }

    // Open spectra from multiple datasets at once
    function openMultiDatasetSpectra(datasetSpectraList, forceNewWindow) {
        // datasetSpectraList is array of {datasetName, spectra}
        if (datasetSpectraList.length === 0) return

        // Combine all spectra
        var allSpectra = []
        var combinedName = []
        for (var i = 0; i < datasetSpectraList.length; i++) {
            var ds = datasetSpectraList[i]
            combinedName.push(ds.datasetName)
            for (var j = 0; j < ds.spectra.length; j++) {
                allSpectra.push(ds.spectra[j])
            }
        }

        openSpectrumPlotWindow(combinedName.join(" + "), allSpectra, forceNewWindow)
    }

    // Track open workflow windows
    property var openWorkflowWindows: []

    function openWorkflowWindow(workflowName) {
        console.log("Opening workflow:", workflowName)

        // Create workflow window component
        var component = Qt.createComponent("../workflow/WorkflowWindow.qml")
        if (component.status === Component.Ready) {
            var window = component.createObject(mainWindow, {
                workflowName: workflowName,
                workflowManager: backend.workflowManager,
                mainWin: mainWindow  // Pass main window for theme colors
            })
            if (window) {
                openWorkflowWindows.push(window)
                window.closing.connect(function() {
                    var idx = openWorkflowWindows.indexOf(window)
                    if (idx >= 0) openWorkflowWindows.splice(idx, 1)
                })
                window.show()
                console.log("Workflow window created successfully")
            } else {
                console.error("Failed to create workflow window object")
            }
        } else if (component.status === Component.Error) {
            console.error("Error creating workflow window:", component.errorString())
        } else {
            console.log("Component loading... status:", component.status)
            component.statusChanged.connect(function() {
                if (component.status === Component.Ready) {
                    var window = component.createObject(mainWindow, {
                        workflowName: workflowName,
                        workflowManager: backend.workflowManager,
                        mainWin: mainWindow  // Pass main window for theme colors
                    })
                    if (window) {
                        openWorkflowWindows.push(window)
                        window.closing.connect(function() {
                            var idx = openWorkflowWindows.indexOf(window)
                            if (idx >= 0) openWorkflowWindows.splice(idx, 1)
                        })
                        window.show()
                    }
                }
            })
        }
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
        for (var i = openWorkflowWindows.length - 1; i >= 0; i--) {
            if (openWorkflowWindows[i]) {
                try {
                    openWorkflowWindows[i].visible = false
                    openWorkflowWindows[i].close()
                    openWorkflowWindows[i].destroy()
                } catch (e) {
                    console.log("Error closing workflow window:", e)
                }
            }
        }
        openWorkflowWindows = []
    }

    // Dialogs
    ImportMeasurementDialog {
        id: importMeasurementDialog
        anchors.centerIn: Overlay.overlay
    }

    // Preferences Dialog
    PreferencesDialog {
        id: preferencesDialog
        anchors.centerIn: Overlay.overlay
        preferencesManager: backend.preferencesManager
        bgDark: mainWindow.bgDark
        bgMedium: mainWindow.bgMedium
        bgLight: mainWindow.bgLight
        textLight: mainWindow.textLight
        textMuted: mainWindow.textMuted
        borderColor: mainWindow.borderColor
        accentPink: mainWindow.accentPink
        accentBlue: mainWindow.accentBlue
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
            if (path.startsWith("file://")) {
                path = path.substring(7)
            }
            console.log("Importing image:", path)
            backend.importImage(path)
        }
    }

    SaveLayoutDialog {
        id: saveLayoutDialog
        anchors.centerIn: Overlay.overlay
    }

    LoadLayoutDialog {
        id: loadLayoutDialog
        anchors.centerIn: Overlay.overlay
    }

    LoadWorkflowDialog {
        id: loadWorkflowDialog
        anchors.centerIn: Overlay.overlay
    }

    // Project Startup Dialog - shown when app starts without a project
    ProjectStartupDialog {
        id: projectStartupDialog
        anchors.centerIn: Overlay.overlay

        onProjectCreated: function(projectPath, projectName) {
            console.log("Creating project:", projectName, "at", projectPath)
            backend.createProject(projectPath, projectName)
        }

        onProjectOpened: function(projectPath, projectName) {
            console.log("Opening project:", projectName, "at", projectPath)
            backend.openProject(projectPath, projectName)
        }

        onDialogCancelled: {
            console.log("Project dialog cancelled, quitting...")
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
                if (!projectStartupDialog.visible) {
                    projectStartupDialog.open()
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
            // Remove file:// prefix
            if (path.startsWith("file://")) {
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
}
