/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * WorkflowToolPalette - Draggable tool palette for workflow editor
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: toolPalette

    // Workflow manager reference
    property var workflowManager: null

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentMagenta: mainWin ? mainWin.accentMagenta : "#D60270"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Port colors for indicators
    readonly property var portColors: ({
        "dataset": "#5BCEFA",
        "flat_data": "#FFD700",
        "image": "#FF6B6B",
        "map": "#9B4F96",
        "table": "#2ECC71",
        "number": "#E91E63",
        "string": "#FF9800",
        "intervals": "#00BCD4",
        "any": "#9E9E9E"
    })

    // Signals
    signal toolDragStarted(string toolName, string displayName)
    signal toolDragEnded(string toolName, real x, real y)

    color: bgMedium

    function getPortColor(portType) {
        return portColors[portType] || portColors["any"]
    }

    function loadToolCategories() {
        if (!workflowManager) {
            console.log("WorkflowToolPalette: No workflowManager available")
            return
        }

        var categoriesList = workflowManager.getToolCategories()
        if (!categoriesList || categoriesList.length === 0) {
            console.log("WorkflowToolPalette: No categories returned")
            return
        }

        toolboxModel.clear()
        var totalTools = 0

        for (var i = 0; i < categoriesList.length; i++) {
            var catObj = categoriesList[i]
            var category = catObj.category
            var tools = catObj.tools
            for (var j = 0; j < tools.length; j++) {
                var toolInfo = workflowManager.getToolInfo(tools[j])
                var portTypesStr = JSON.stringify(toolInfo.port_types || [])
                toolboxModel.append({
                    "category": category,
                    "toolName": tools[j],
                    "displayName": toolInfo.display_name || tools[j],
                    "description": toolInfo.description || "",
                    "portTypes": portTypesStr
                })
                totalTools++
            }
        }

        console.log("WorkflowToolPalette: Loaded", totalTools, "tools")
    }

    onWorkflowManagerChanged: {
        if (workflowManager) {
            loadToolCategories()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        // Header
        Text {
            text: "Tool Palette"
            color: accentPink
            font.pixelSize: 14
            font.bold: true
            Layout.fillWidth: true
            padding: 5
        }

        // Search field
        TextField {
            id: toolSearch
            placeholderText: "Search tools..."
            Layout.fillWidth: true
            color: textLight

            background: Rectangle {
                color: bgDark
                border.color: toolSearch.activeFocus ? accentBlue : borderColor
                radius: 3
            }
        }

        // Tool list
        ListView {
            id: toolList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            model: ListModel { id: toolboxModel }

            section.property: "category"
            section.delegate: Rectangle {
                width: toolList.width
                height: 25
                color: bgDarker

                Text {
                    text: section
                    color: accentBlue
                    font.pixelSize: 12
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                    leftPadding: 8
                }
            }

            delegate: Rectangle {
                width: toolList.width
                height: visible ? 50 : 0
                visible: toolSearch.text === "" ||
                         displayName.toLowerCase().includes(toolSearch.text.toLowerCase())
                color: toolDragArea.containsMouse ? bgLight : "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 5
                    spacing: 8

                    // Port type color indicators
                    Item {
                        id: portIndicators
                        Layout.preferredWidth: {
                            var types = JSON.parse(portTypes || "[]")
                            if (types.length === 0) return 0
                            var circleSize = 10
                            var spacing = circleSize / 1.618
                            return circleSize + (types.length - 1) * spacing
                        }
                        Layout.preferredHeight: 10
                        Layout.alignment: Qt.AlignVCenter

                        Repeater {
                            model: JSON.parse(portTypes || "[]")

                            Rectangle {
                                width: 10
                                height: 10
                                radius: 5
                                color: getPortColor(modelData)
                                border.width: 1
                                border.color: Qt.darker(color, 1.3)
                                x: index * (10 / 1.618)
                                y: 0
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            text: displayName
                            color: textLight
                            font.pixelSize: 12
                        }

                        Text {
                            text: description
                            color: textMuted
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                MouseArea {
                    id: toolDragArea
                    anchors.fill: parent
                    hoverEnabled: true
                    drag.target: dragItem

                    property string currentToolName: toolName
                    property string currentDisplayName: displayName

                    onPressed: function(mouse) {
                        dragItem.toolName = currentToolName
                        dragItem.displayName = currentDisplayName
                        dragItem.visible = true
                        var globalPos = mapToItem(null, mouse.x, mouse.y)
                        dragItem.x = globalPos.x - dragItem.width / 2
                        dragItem.y = globalPos.y - dragItem.height / 2
                        toolDragStarted(currentToolName, currentDisplayName)
                    }

                    onReleased: function(mouse) {
                        if (dragItem.visible) {
                            var globalPos = mapToItem(null, dragItem.x + dragItem.width / 2, dragItem.y + dragItem.height / 2)
                            toolDragEnded(dragItem.toolName, globalPos.x, globalPos.y)
                            dragItem.visible = false
                        }
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                active: true
            }
        }

        // Help text
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: bgDark
            radius: 5

            Text {
                anchors.fill: parent
                anchors.margins: 8
                text: "Drag tools to canvas\nClick ports to wire\nDel removes selection"
                color: textMuted
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
        }
    }

    // Drag item (shown while dragging)
    Rectangle {
        id: dragItem
        width: 140
        height: 35
        radius: 5
        color: bgLight
        border.color: accentPink
        border.width: 2
        visible: false
        z: 1000

        property string toolName: ""
        property string displayName: ""

        Drag.active: visible
        Drag.hotSpot.x: width / 2
        Drag.hotSpot.y: height / 2
        Drag.mimeData: { "text/plain": toolName }

        Text {
            anchors.centerIn: parent
            text: dragItem.displayName
            color: textLight
            font.pixelSize: 11
            font.bold: true
        }
    }

    Component.onCompleted: {
        console.log("WorkflowToolPalette created")
        if (workflowManager) {
            loadToolCategories()
        }
    }
}
