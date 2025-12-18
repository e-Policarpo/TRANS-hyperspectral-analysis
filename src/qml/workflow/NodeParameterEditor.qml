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

Rectangle {
    id: editorRoot

    property var workflowWindow: null
    property var currentNode: null
    property var toolInfo: ({})

    // Theme colors - get from parent workflowWindow
    property color bgDark: workflowWindow ? workflowWindow.bgDark : "#1a1a2e"
    property color bgMedium: workflowWindow ? workflowWindow.bgMedium : "#2a2a3e"
    property color bgLight: workflowWindow ? workflowWindow.bgLight : "#3a3a4e"
    property color accentPink: workflowWindow ? workflowWindow.accentPink : "#F5A9B8"
    property color accentBlue: workflowWindow ? workflowWindow.accentBlue : "#5BCEFA"
    property color accentGreen: "#66ff99"   // Keep workflow status color
    property color textLight: workflowWindow ? workflowWindow.textLight : "#ffffff"
    property color textMuted: workflowWindow ? workflowWindow.textMuted : "#cccccc"
    property color borderColor: workflowWindow ? workflowWindow.borderColor : "#9B4F96"

    color: "transparent"

    function loadNode(nodeData) {
        currentNode = nodeData
        if (workflowWindow && workflowWindow.workflowManager) {
            toolInfo = workflowWindow.workflowManager.getToolInfo(nodeData.tool_name)
        }
        buildParameterUI()
    }

    function clearNode() {
        currentNode = null
        toolInfo = {}
        parameterContainer.children = []
    }

    function buildParameterUI() {
        // Clear existing parameters
        for (var i = parameterContainer.children.length - 1; i >= 0; i--) {
            parameterContainer.children[i].destroy()
        }

        if (!currentNode || !toolInfo.parameters) return

        var params = toolInfo.parameters
        for (var paramName in params) {
            var paramDef = params[paramName]
            var currentValue = currentNode.parameters ? currentNode.parameters[paramName] : paramDef.default

            createParameterControl(paramName, paramDef, currentValue)
        }
    }

    function createParameterControl(paramName, paramDef, currentValue) {
        var component

        switch (paramDef.type) {
            case "int":
            case "float":
            case "number":
                component = numberInputComponent
                break
            case "string":
                component = stringInputComponent
                break
            case "bool":
                component = boolInputComponent
                break
            case "select":
            case "combo":
                component = selectInputComponent
                break
            case "color":
                component = colorPickerComponent
                break
            case "dataset_select":
                component = datasetSelectComponent
                break
            case "interval_list":
                component = intervalListComponent
                break
            case "multi_input_queue":
                component = multiInputQueueComponent
                break
            case "equation":
                component = equationInputComponent
                break
            case "input_mapping":
                component = inputMappingComponent
                break
            case "column_select":
                component = columnSelectComponent
                break
            default:
                component = stringInputComponent
        }

        var item = component.createObject(parameterContainer, {
            paramName: paramName,
            paramDef: paramDef,
            currentValue: currentValue
        })
    }

    function updateParameter(paramName, value) {
        if (workflowWindow && workflowWindow.workflowManager &&
            workflowWindow.workflowId && currentNode) {
            // Update in backend
            workflowWindow.workflowManager.setNodeParameter(
                workflowWindow.workflowId,
                currentNode.id,
                paramName,
                value
            )

            // Update local currentNode to keep in sync
            if (!currentNode.parameters) {
                currentNode.parameters = {}
            }
            currentNode.parameters[paramName] = value

            // Emit signal to update the node display in the canvas
            workflowWindow.nodeParameterChanged(currentNode.id, paramName, value)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 35
            color: bgLight
            radius: 5

            Text {
                anchors.centerIn: parent
                text: currentNode ? currentNode.display_name : "No Node Selected"
                color: currentNode ? accentPink : textMuted
                font.pixelSize: 14
                font.bold: true
            }
        }

        // Node info
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: descriptionText.height + 20
            color: bgDark
            radius: 5
            visible: currentNode !== null

            Text {
                id: descriptionText
                anchors.fill: parent
                anchors.margins: 10
                text: toolInfo.description || ""
                color: textMuted
                font.pixelSize: 11
                wrapMode: Text.Wrap
            }
        }

        // Parameters header
        Text {
            text: "Parameters"
            color: accentBlue
            font.pixelSize: 12
            font.bold: true
            visible: currentNode !== null
        }

        // Parameter controls
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                id: parameterContainer
                width: parent.width
                spacing: 10
            }
        }

        // Auto-save status indicator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            visible: currentNode !== null
            color: "#1a3322"  // Dark green background
            radius: 4
            border.color: "#2a5533"
            border.width: 1

            Row {
                anchors.centerIn: parent
                spacing: 6

                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: accentGreen
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: "Changes saved automatically"
                    color: accentGreen
                    font.pixelSize: 10
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        // Empty state
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: currentNode === null

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10

                Text {
                    text: "Select a node to edit"
                    color: textMuted
                    font.pixelSize: 14
                    Layout.alignment: Qt.AlignHCenter
                }

                Text {
                    text: "Click on a node in the canvas\nto view and edit its parameters"
                    color: textMuted
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignHCenter
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }
    }

    // Component templates for different parameter types
    Component {
        id: numberInputComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: 0

            Layout.fillWidth: true
            spacing: 3

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                // Helper function to get initial value (handles 0 correctly)
                function getInitialValue() {
                    if (currentValue !== undefined && currentValue !== null) return currentValue
                    if (paramDef.default !== undefined && paramDef.default !== null) return paramDef.default
                    return 0
                }

                Slider {
                    id: numberSlider
                    Layout.fillWidth: true
                    from: paramDef.min !== undefined ? paramDef.min : -1000
                    to: paramDef.max !== undefined ? paramDef.max : 1000
                    stepSize: paramDef.type === "int" ? 1 : 0.01
                    value: parent.getInitialValue()
                    visible: paramDef.min !== undefined && paramDef.max !== undefined

                    onValueChanged: {
                        numberField.text = paramDef.type === "int" ? Math.round(value).toString() : value.toFixed(4)
                        updateParameter(paramName, paramDef.type === "int" ? Math.round(value) : value)
                    }
                }

                TextField {
                    id: numberField
                    Layout.preferredWidth: numberSlider.visible ? 80 : -1
                    Layout.fillWidth: !numberSlider.visible
                    text: {
                        var val = parent.getInitialValue()
                        return paramDef.type === "int" ? val.toString() : val.toFixed(4)
                    }
                    color: textLight
                    // Use regex validator to accept both . and , as decimal separators
                    validator: RegularExpressionValidator {
                        regularExpression: /^-?\d*[.,]?\d*$/
                    }

                    background: Rectangle {
                        color: bgDark
                        border.color: numberField.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }

                    onTextChanged: {
                        // Replace comma with dot for parsing (handle locale differences)
                        var normalizedText = text.replace(",", ".")
                        var val = paramDef.type === "int" ? parseInt(normalizedText) : parseFloat(normalizedText)
                        if (!isNaN(val)) {
                            if (numberSlider.visible) numberSlider.value = val
                            updateParameter(paramName, val)
                        }
                    }
                }
            }
        }
    }

    Component {
        id: stringInputComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: ""

            Layout.fillWidth: true
            spacing: 3

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            // Single-line input for non-multiline strings
            TextField {
                id: singleLineInput
                Layout.fillWidth: true
                visible: !paramDef.multiline
                text: currentValue || paramDef.default || ""
                color: textLight
                placeholderText: paramDef.required ? "Required" : "Optional"

                background: Rectangle {
                    color: bgDark
                    border.color: parent.activeFocus ? accentBlue : borderColor
                    radius: 3
                }

                onTextChanged: updateParameter(paramName, text)
            }

            // Multi-line input for multiline strings (e.g., comments)
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 100
                visible: paramDef.multiline === true
                color: bgDark
                radius: 4
                border.color: multiLineInput.activeFocus ? accentBlue : borderColor

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 4

                    TextArea {
                        id: multiLineInput
                        text: currentValue || paramDef.default || ""
                        color: textLight
                        font.pixelSize: 11
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        placeholderText: paramDef.required ? "Required" : "Enter text here..."
                        placeholderTextColor: textMuted

                        background: Rectangle {
                            color: "transparent"
                        }

                        onTextChanged: updateParameter(paramName, text)
                    }
                }
            }
        }
    }

    Component {
        id: boolInputComponent

        RowLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: false

            Layout.fillWidth: true
            spacing: 10

            CheckBox {
                id: boolCheck
                checked: currentValue !== undefined ? currentValue : (paramDef.default || false)

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    radius: 3
                    color: bgDark
                    border.color: boolCheck.checked ? accentGreen : borderColor

                    Rectangle {
                        width: 12
                        height: 12
                        anchors.centerIn: parent
                        radius: 2
                        color: accentGreen
                        visible: boolCheck.checked
                    }
                }

                onCheckedChanged: updateParameter(paramName, checked)
            }

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
                Layout.fillWidth: true
            }
        }
    }

    Component {
        id: selectInputComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: ""

            Layout.fillWidth: true
            spacing: 3

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            ComboBox {
                id: selectCombo
                Layout.fillWidth: true
                model: paramDef.options || []
                currentIndex: {
                    var val = currentValue || paramDef.default
                    return paramDef.options ? paramDef.options.indexOf(val) : 0
                }

                background: Rectangle {
                    color: bgDark
                    border.color: selectCombo.activeFocus ? accentBlue : borderColor
                    radius: 3
                }

                contentItem: Text {
                    text: selectCombo.displayText
                    color: textLight
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 8
                }

                delegate: ItemDelegate {
                    width: selectCombo.width
                    contentItem: Text {
                        text: modelData
                        color: textLight
                        font.pixelSize: 11
                    }
                    background: Rectangle {
                        color: highlighted ? bgLight : bgMedium
                    }
                }

                popup: Popup {
                    y: selectCombo.height
                    width: selectCombo.width
                    implicitHeight: contentItem.implicitHeight
                    padding: 1

                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: selectCombo.popup.visible ? selectCombo.delegateModel : null
                        currentIndex: selectCombo.highlightedIndex
                    }

                    background: Rectangle {
                        color: bgMedium
                        border.color: borderColor
                        radius: 3
                    }
                }

                onCurrentTextChanged: updateParameter(paramName, currentText)
            }
        }
    }

    Component {
        id: datasetSelectComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: ""

            Layout.fillWidth: true
            spacing: 3

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            ComboBox {
                id: datasetCombo
                Layout.fillWidth: true
                model: workflowWindow && workflowWindow.workflowManager ?
                       workflowWindow.workflowManager.getAvailableDatasets() : []
                currentIndex: {
                    var datasets = workflowWindow && workflowWindow.workflowManager ?
                                   workflowWindow.workflowManager.getAvailableDatasets() : []
                    return datasets.indexOf(currentValue)
                }

                background: Rectangle {
                    color: bgDark
                    border.color: datasetCombo.activeFocus ? accentPink : borderColor
                    radius: 3
                }

                contentItem: Text {
                    text: datasetCombo.displayText || "Select dataset..."
                    color: datasetCombo.displayText ? textLight : textMuted
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 8
                }

                delegate: ItemDelegate {
                    width: datasetCombo.width
                    contentItem: Text {
                        text: modelData
                        color: textLight
                        font.pixelSize: 11
                    }
                    background: Rectangle {
                        color: highlighted ? bgLight : bgMedium
                    }
                }

                onCurrentTextChanged: updateParameter(paramName, currentText)
            }

            Button {
                text: "Refresh"
                Layout.alignment: Qt.AlignRight

                contentItem: Text {
                    text: parent.text
                    color: textMuted
                    font.pixelSize: 10
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    radius: 3
                }

                onClicked: {
                    datasetCombo.model = workflowWindow.workflowManager.getAvailableDatasets()
                }
            }
        }
    }

    Component {
        id: intervalListComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: []
            property var intervals: currentValue || []

            Layout.fillWidth: true
            spacing: 5

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            // Interval list
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(60, intervalListView.contentHeight + 10)
                color: bgDark
                radius: 3
                border.color: borderColor

                ListView {
                    id: intervalListView
                    anchors.fill: parent
                    anchors.margins: 5
                    model: intervals
                    spacing: 3
                    clip: true

                    delegate: RowLayout {
                        width: intervalListView.width
                        spacing: 5

                        TextField {
                            Layout.fillWidth: true
                            text: modelData[0] || ""
                            placeholderText: "Start"
                            color: textLight
                            font.pixelSize: 10

                            background: Rectangle {
                                color: bgMedium
                                border.color: borderColor
                                radius: 2
                            }

                            onTextChanged: {
                                var newIntervals = intervals.slice()
                                newIntervals[index] = [parseFloat(text), newIntervals[index][1]]
                                intervals = newIntervals
                                updateParameter(paramName, intervals)
                            }
                        }

                        Text {
                            text: "-"
                            color: textMuted
                        }

                        TextField {
                            Layout.fillWidth: true
                            text: modelData[1] || ""
                            placeholderText: "End"
                            color: textLight
                            font.pixelSize: 10

                            background: Rectangle {
                                color: bgMedium
                                border.color: borderColor
                                radius: 2
                            }

                            onTextChanged: {
                                var newIntervals = intervals.slice()
                                newIntervals[index] = [newIntervals[index][0], parseFloat(text)]
                                intervals = newIntervals
                                updateParameter(paramName, intervals)
                            }
                        }

                        Button {
                            text: "x"
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20

                            contentItem: Text {
                                text: parent.text
                                color: parent.hovered ? "#D60270" : textMuted
                                font.pixelSize: 10
                                horizontalAlignment: Text.AlignHCenter
                            }

                            background: Rectangle {
                                color: parent.hovered ? bgLight : "transparent"
                                radius: 2
                            }

                            onClicked: {
                                var newIntervals = intervals.slice()
                                newIntervals.splice(index, 1)
                                intervals = newIntervals
                                updateParameter(paramName, intervals)
                            }
                        }
                    }
                }
            }

            Button {
                text: "+ Add Interval"
                Layout.fillWidth: true

                contentItem: Text {
                    text: parent.text
                    color: accentBlue
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : bgMedium
                    border.color: accentBlue
                    radius: 3
                }

                onClicked: {
                    var newIntervals = intervals.slice()
                    newIntervals.push([0, 0])
                    intervals = newIntervals
                    updateParameter(paramName, intervals)
                }
            }
        }
    }

    // Multi-input queue component for nodes that accept multiple inputs
    Component {
        id: multiInputQueueComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: []
            property var queueItems: []

            Layout.fillWidth: true
            spacing: 5

            Component.onCompleted: {
                refreshConnectedInputs()
            }

            function refreshConnectedInputs() {
                if (workflowWindow && workflowWindow.workflowManager &&
                    workflowWindow.workflowId && currentNode) {
                    var connected = workflowWindow.workflowManager.getConnectedInputs(
                        workflowWindow.workflowId, currentNode.id)

                    // Merge with existing queue order/enabled state
                    var existingQueue = currentValue || []
                    var newQueue = []

                    // First, add items in existing order if they're still connected
                    for (var i = 0; i < existingQueue.length; i++) {
                        var existing = existingQueue[i]
                        var stillConnected = connected.find(function(c) {
                            return c.source_node_id === existing.source_node_id
                        })
                        if (stillConnected) {
                            newQueue.push({
                                source_node_id: existing.source_node_id,
                                source_node_name: stillConnected.source_node_name,
                                source_port_id: stillConnected.source_port_id,
                                target_port_id: stillConnected.target_port_id,
                                enabled: existing.enabled !== undefined ? existing.enabled : true
                            })
                        }
                    }

                    // Then add any new connections not in existing queue
                    for (var j = 0; j < connected.length; j++) {
                        var conn = connected[j]
                        var alreadyInQueue = newQueue.find(function(q) {
                            return q.source_node_id === conn.source_node_id
                        })
                        if (!alreadyInQueue) {
                            newQueue.push({
                                source_node_id: conn.source_node_id,
                                source_node_name: conn.source_node_name,
                                source_port_id: conn.source_port_id,
                                target_port_id: conn.target_port_id,
                                enabled: true
                            })
                        }
                    }

                    queueItems = newQueue
                    queueListView.model = queueItems
                }
            }

            function moveItem(fromIndex, toIndex) {
                if (fromIndex === toIndex) return
                var items = queueItems.slice()
                var item = items.splice(fromIndex, 1)[0]
                items.splice(toIndex, 0, item)
                queueItems = items
                queueListView.model = queueItems
                updateParameter(paramName, queueItems)
            }

            function setItemEnabled(index, enabled) {
                var items = queueItems.slice()
                items[index].enabled = enabled
                queueItems = items
                updateParameter(paramName, queueItems)
            }

            Text {
                text: paramDef.label || "Processing Queue"
                color: textLight
                font.pixelSize: 11
            }

            Text {
                text: "Drag to reorder, uncheck to skip"
                color: textMuted
                font.pixelSize: 9
                visible: queueItems.length > 0
            }

            // Queue list
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(60, Math.min(200, queueListView.contentHeight + 10))
                color: bgDark
                radius: 3
                border.color: borderColor

                ListView {
                    id: queueListView
                    anchors.fill: parent
                    anchors.margins: 5
                    spacing: 4
                    clip: true
                    // Note: model is set explicitly in refreshConnectedInputs() to avoid binding loop

                    delegate: DraggableListItem {
                        itemIndex: index
                        itemText: modelData.source_node_name || "Unknown"
                        itemEnabled: modelData.enabled !== undefined ? modelData.enabled : true
                        listView: queueListView

                        onItemMoved: function(fromIdx, toIdx) {
                            moveItem(fromIdx, toIdx)
                        }

                        onItemEnabledToggled: function(idx, enabled) {
                            setItemEnabled(idx, enabled)
                        }
                    }

                    // Empty state
                    Text {
                        visible: queueListView.count === 0
                        anchors.centerIn: parent
                        text: "No inputs connected"
                        color: textMuted
                        font.pixelSize: 10
                        font.italic: true
                    }
                }
            }

            // Refresh button
            Button {
                text: "Refresh Connections"
                Layout.fillWidth: true

                contentItem: Text {
                    text: parent.text
                    color: textMuted
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 3
                }

                onClicked: refreshConnectedInputs()
            }

            // Info text
            Text {
                visible: queueItems.length > 0
                text: queueItems.filter(function(q) { return q.enabled }).length +
                      " of " + queueItems.length + " inputs enabled"
                color: accentBlue
                font.pixelSize: 9
                Layout.alignment: Qt.AlignRight
            }
        }
    }

    // Equation input component for DataManipulation node
    Component {
        id: equationInputComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property string currentValue: ""

            Layout.fillWidth: true
            spacing: 8

            Text {
                text: paramDef.label || "Equation"
                color: textLight
                font.pixelSize: 11
            }

            // Equation input field
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 60
                color: bgDark
                radius: 4
                border.color: equationInput.activeFocus ? accentPink : borderColor

                TextArea {
                    id: equationInput
                    anchors.fill: parent
                    anchors.margins: 6
                    text: currentValue
                    color: textLight
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    placeholderText: "e.g., A + B, Sum(A,B,C), sqrt(A)"
                    placeholderTextColor: textMuted

                    background: Rectangle {
                        color: "transparent"
                    }

                    onTextChanged: {
                        updateParameter(paramName, text)
                        validateEquation(text)
                    }
                }
            }

            // Basic operators
            Text {
                text: "Operators:"
                color: textMuted
                font.pixelSize: 9
            }

            Flow {
                Layout.fillWidth: true
                spacing: 4

                Repeater {
                    model: ["A", "B", "C", "+", "-", "*", "/", "^"]

                    Rectangle {
                        width: hintText.implicitWidth + 8
                        height: 18
                        radius: 3
                        color: hintArea.containsMouse ? bgLight : "transparent"
                        border.color: borderColor

                        Text {
                            id: hintText
                            anchors.centerIn: parent
                            text: modelData
                            color: textMuted
                            font.pixelSize: 9
                            font.family: "monospace"
                        }

                        MouseArea {
                            id: hintArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor

                            onClicked: {
                                equationInput.insert(equationInput.cursorPosition, modelData)
                            }
                        }
                    }
                }
            }

            // Single-argument functions
            Text {
                text: "Functions:"
                color: textMuted
                font.pixelSize: 9
            }

            Flow {
                Layout.fillWidth: true
                spacing: 4

                Repeater {
                    model: ["sqrt", "log", "exp", "abs", "sin", "cos"]

                    Rectangle {
                        width: funcText.implicitWidth + 8
                        height: 18
                        radius: 3
                        color: funcArea.containsMouse ? bgLight : "transparent"
                        border.color: borderColor

                        Text {
                            id: funcText
                            anchors.centerIn: parent
                            text: modelData
                            color: accentBlue
                            font.pixelSize: 9
                            font.family: "monospace"
                        }

                        MouseArea {
                            id: funcArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor

                            onClicked: {
                                equationInput.insert(equationInput.cursorPosition, modelData + "()")
                            }
                        }
                    }
                }
            }

            // Aggregation functions (LISP-style)
            Text {
                text: "Aggregations (multi-input):"
                color: textMuted
                font.pixelSize: 9
            }

            Flow {
                Layout.fillWidth: true
                spacing: 4

                Repeater {
                    model: [
                        {name: "Sum", hint: "Sum(A,B,C)"},
                        {name: "Mean", hint: "Mean(A,B,C)"},
                        {name: "Min", hint: "Min(A,B,C)"},
                        {name: "Max", hint: "Max(A,B,C)"},
                        {name: "Prod", hint: "Prod(A,B)"}
                    ]

                    Rectangle {
                        width: aggText.implicitWidth + 8
                        height: 18
                        radius: 3
                        color: aggArea.containsMouse ? bgLight : "transparent"
                        border.color: accentPink

                        Text {
                            id: aggText
                            anchors.centerIn: parent
                            text: modelData.name
                            color: accentPink
                            font.pixelSize: 9
                            font.family: "monospace"
                        }

                        MouseArea {
                            id: aggArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor

                            onClicked: {
                                equationInput.insert(equationInput.cursorPosition, modelData.name + "(A,B)")
                            }

                            ToolTip {
                                visible: aggArea.containsMouse
                                text: modelData.hint
                                delay: 300
                            }
                        }
                    }
                }
            }

            // Validation indicator
            Rectangle {
                id: validationIndicator
                Layout.fillWidth: true
                height: 20
                radius: 3
                color: "transparent"

                property bool isValid: true
                property string message: ""

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5

                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: validationIndicator.isValid ? accentGreen : "#D60270"
                    }

                    Text {
                        text: validationIndicator.message || (validationIndicator.isValid ? "Valid equation" : "Invalid syntax")
                        color: validationIndicator.isValid ? accentGreen : "#D60270"
                        font.pixelSize: 9
                    }
                }
            }

            // Help text
            Text {
                text: "Variables: A, B, C, D... (mapped to connected inputs)\nAggregations accept multiple variables: Sum(A,B,C,D)"
                color: textMuted
                font.pixelSize: 9
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            function validateEquation(eq) {
                // Basic validation
                if (!eq || eq.trim() === "") {
                    validationIndicator.isValid = false
                    validationIndicator.message = "Equation required"
                    return
                }

                // Check for balanced parentheses
                var open = (eq.match(/\(/g) || []).length
                var close = (eq.match(/\)/g) || []).length
                if (open !== close) {
                    validationIndicator.isValid = false
                    validationIndicator.message = "Unbalanced parentheses"
                    return
                }

                // Check for at least one variable reference (A-Z)
                if (!/[A-Z]/.test(eq)) {
                    validationIndicator.isValid = false
                    validationIndicator.message = "Need at least one variable (A, B, C...)"
                    return
                }

                // Check for dangerous patterns
                var dangerous = ['import', 'exec', 'eval', 'open', 'file', '__']
                for (var i = 0; i < dangerous.length; i++) {
                    if (eq.toLowerCase().indexOf(dangerous[i]) >= 0) {
                        validationIndicator.isValid = false
                        validationIndicator.message = "Invalid pattern detected"
                        return
                    }
                }

                validationIndicator.isValid = true
                validationIndicator.message = "Valid equation"
            }

            Component.onCompleted: {
                if (currentValue) {
                    validateEquation(currentValue)
                }
            }
        }
    }

    // Input mapping component for DataManipulation node
    Component {
        id: inputMappingComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: ({})
            property var mappingItems: []

            Layout.fillWidth: true
            spacing: 5

            Component.onCompleted: {
                refreshConnectedInputs()
            }

            function refreshConnectedInputs() {
                if (workflowWindow && workflowWindow.workflowManager &&
                    workflowWindow.workflowId && currentNode) {
                    var connected = workflowWindow.workflowManager.getConnectedInputs(
                        workflowWindow.workflowId, currentNode.id)

                    // Assign letters A, B, C, ... to connected inputs
                    var letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    var mapping = currentValue || {}
                    var newMapping = {}
                    var items = []

                    for (var i = 0; i < connected.length && i < 26; i++) {
                        var conn = connected[i]
                        var letter = letters[i]

                        // Check if there's an existing mapping for this connection
                        var existingLetter = null
                        for (var key in mapping) {
                            if (mapping[key] === conn.source_node_id) {
                                existingLetter = key
                                break
                            }
                        }

                        // Use existing letter if available, otherwise assign new one
                        var assignedLetter = existingLetter || letter
                        newMapping[assignedLetter] = conn.source_node_id

                        items.push({
                            letter: assignedLetter,
                            source_node_id: conn.source_node_id,
                            source_node_name: conn.source_node_name || "Unknown",
                            source_port_id: conn.source_port_id
                        })
                    }

                    mappingItems = items
                    mappingListView.model = mappingItems
                    updateParameter(paramName, newMapping)
                }
            }

            Text {
                text: "Input Mapping"
                color: textLight
                font.pixelSize: 11
            }

            Text {
                text: "Variables assigned to connected inputs:"
                color: textMuted
                font.pixelSize: 9
                visible: mappingItems.length > 0
            }

            // Mapping list
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, Math.min(150, mappingListView.contentHeight + 10))
                color: bgDark
                radius: 3
                border.color: borderColor

                ListView {
                    id: mappingListView
                    anchors.fill: parent
                    anchors.margins: 5
                    spacing: 3
                    clip: true

                    delegate: RowLayout {
                        width: mappingListView.width - 10
                        spacing: 8

                        // Variable letter badge
                        Rectangle {
                            width: 24
                            height: 24
                            radius: 4
                            color: accentPink
                            opacity: 0.8

                            Text {
                                anchors.centerIn: parent
                                text: modelData.letter
                                color: bgDark
                                font.pixelSize: 14
                                font.bold: true
                                font.family: "monospace"
                            }
                        }

                        // Arrow
                        Text {
                            text: "←"
                            color: textMuted
                            font.pixelSize: 12
                        }

                        // Source node name
                        Text {
                            text: modelData.source_node_name
                            color: textLight
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    // Empty state
                    Text {
                        visible: mappingListView.count === 0
                        anchors.centerIn: parent
                        text: "No inputs connected"
                        color: textMuted
                        font.pixelSize: 10
                        font.italic: true
                    }
                }
            }

            // Refresh button
            Button {
                text: "Refresh Mapping"
                Layout.fillWidth: true

                contentItem: Text {
                    text: parent.text
                    color: textMuted
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                }

                background: Rectangle {
                    color: parent.hovered ? bgLight : "transparent"
                    border.color: borderColor
                    radius: 3
                }

                onClicked: refreshConnectedInputs()
            }

            // Info text
            Text {
                visible: mappingItems.length > 0
                text: mappingItems.length + " input(s) mapped"
                color: accentBlue
                font.pixelSize: 9
                Layout.alignment: Qt.AlignRight
            }
        }
    }

    // Color picker component with RGB sliders and preview
    Component {
        id: colorPickerComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: "#F5A9B8"

            Layout.fillWidth: true
            spacing: 5

            // Helper function to parse hex color
            function hexToRgb(hex) {
                var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
                return result ? {
                    r: parseInt(result[1], 16),
                    g: parseInt(result[2], 16),
                    b: parseInt(result[3], 16)
                } : { r: 245, g: 169, b: 184 }  // Default to trans pink
            }

            // Helper function to convert RGB to hex
            function rgbToHex(r, g, b) {
                return "#" + ((1 << 24) + (Math.round(r) << 16) + (Math.round(g) << 8) + Math.round(b)).toString(16).slice(1).toUpperCase()
            }

            // Initialize from current value
            Component.onCompleted: {
                var rgb = hexToRgb(currentValue || paramDef.default || "#F5A9B8")
                redSlider.value = rgb.r
                greenSlider.value = rgb.g
                blueSlider.value = rgb.b
            }

            Text {
                text: paramDef.label || paramName
                color: textLight
                font.pixelSize: 11
            }

            // Color preview with hex input
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                // Color preview square
                Rectangle {
                    id: colorPreview
                    width: 40
                    height: 40
                    radius: 4
                    color: rgbToHex(redSlider.value, greenSlider.value, blueSlider.value)
                    border.color: borderColor
                    border.width: 1

                    // Eyedropper icon overlay
                    Text {
                        anchors.centerIn: parent
                        text: "🎨"
                        font.pixelSize: 16
                        opacity: dropperArea.containsMouse ? 1.0 : 0.3
                    }

                    MouseArea {
                        id: dropperArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.CrossCursor

                        ToolTip.visible: containsMouse
                        ToolTip.text: "Click to pick color (opens system picker)"

                        onClicked: {
                            // For now, just cycle through some preset colors
                            var presets = ["#F5A9B8", "#5BCEFA", "#9B4F96", "#FFD700", "#2ECC71", "#FF6B6B", "#333333", "#FFFFFF"]
                            var currentHex = colorPreview.color.toString().toUpperCase()
                            var idx = presets.indexOf(currentHex)
                            var nextIdx = (idx + 1) % presets.length
                            var rgb = hexToRgb(presets[nextIdx])
                            redSlider.value = rgb.r
                            greenSlider.value = rgb.g
                            blueSlider.value = rgb.b
                        }
                    }
                }

                // Hex input field
                TextField {
                    id: hexField
                    Layout.preferredWidth: 80
                    text: colorPreview.color.toString().toUpperCase()
                    color: textLight
                    font.family: "monospace"
                    font.pixelSize: 11

                    background: Rectangle {
                        color: bgDark
                        border.color: hexField.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }

                    onEditingFinished: {
                        var hex = text.startsWith("#") ? text : "#" + text
                        if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
                            var rgb = hexToRgb(hex)
                            redSlider.value = rgb.r
                            greenSlider.value = rgb.g
                            blueSlider.value = rgb.b
                        }
                    }
                }
            }

            // Red slider
            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "R"
                    color: "#FF6666"
                    font.pixelSize: 10
                    font.bold: true
                    Layout.preferredWidth: 15
                }

                Slider {
                    id: redSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 255
                    stepSize: 1
                    value: 245

                    background: Rectangle {
                        x: redSlider.leftPadding
                        y: redSlider.topPadding + redSlider.availableHeight / 2 - height / 2
                        implicitWidth: 200
                        implicitHeight: 4
                        width: redSlider.availableWidth
                        height: implicitHeight
                        radius: 2
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.rgba(0, greenSlider.value/255, blueSlider.value/255, 1) }
                            GradientStop { position: 1.0; color: Qt.rgba(1, greenSlider.value/255, blueSlider.value/255, 1) }
                        }
                    }

                    onValueChanged: {
                        hexField.text = rgbToHex(value, greenSlider.value, blueSlider.value)
                        updateParameter(paramName, hexField.text)
                    }
                }

                Text {
                    text: Math.round(redSlider.value)
                    color: textMuted
                    font.pixelSize: 10
                    Layout.preferredWidth: 25
                    horizontalAlignment: Text.AlignRight
                }
            }

            // Green slider
            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "G"
                    color: "#66FF66"
                    font.pixelSize: 10
                    font.bold: true
                    Layout.preferredWidth: 15
                }

                Slider {
                    id: greenSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 255
                    stepSize: 1
                    value: 169

                    background: Rectangle {
                        x: greenSlider.leftPadding
                        y: greenSlider.topPadding + greenSlider.availableHeight / 2 - height / 2
                        implicitWidth: 200
                        implicitHeight: 4
                        width: greenSlider.availableWidth
                        height: implicitHeight
                        radius: 2
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.rgba(redSlider.value/255, 0, blueSlider.value/255, 1) }
                            GradientStop { position: 1.0; color: Qt.rgba(redSlider.value/255, 1, blueSlider.value/255, 1) }
                        }
                    }

                    onValueChanged: {
                        hexField.text = rgbToHex(redSlider.value, value, blueSlider.value)
                        updateParameter(paramName, hexField.text)
                    }
                }

                Text {
                    text: Math.round(greenSlider.value)
                    color: textMuted
                    font.pixelSize: 10
                    Layout.preferredWidth: 25
                    horizontalAlignment: Text.AlignRight
                }
            }

            // Blue slider
            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "B"
                    color: "#6666FF"
                    font.pixelSize: 10
                    font.bold: true
                    Layout.preferredWidth: 15
                }

                Slider {
                    id: blueSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 255
                    stepSize: 1
                    value: 184

                    background: Rectangle {
                        x: blueSlider.leftPadding
                        y: blueSlider.topPadding + blueSlider.availableHeight / 2 - height / 2
                        implicitWidth: 200
                        implicitHeight: 4
                        width: blueSlider.availableWidth
                        height: implicitHeight
                        radius: 2
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.rgba(redSlider.value/255, greenSlider.value/255, 0, 1) }
                            GradientStop { position: 1.0; color: Qt.rgba(redSlider.value/255, greenSlider.value/255, 1, 1) }
                        }
                    }

                    onValueChanged: {
                        hexField.text = rgbToHex(redSlider.value, greenSlider.value, value)
                        updateParameter(paramName, hexField.text)
                    }
                }

                Text {
                    text: Math.round(blueSlider.value)
                    color: textMuted
                    font.pixelSize: 10
                    Layout.preferredWidth: 25
                    horizontalAlignment: Text.AlignRight
                }
            }
        }
    }

    // Column select component for dataset column filtering
    Component {
        id: columnSelectComponent

        ColumnLayout {
            property string paramName: ""
            property var paramDef: ({})
            property var currentValue: []

            Layout.fillWidth: true
            spacing: 5

            property var availableColumns: []
            property var selectedColumns: []

            Text {
                text: paramDef.label || "Select Columns"
                color: textLight
                font.pixelSize: 11
            }

            // Scrollable column checklist
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(150, columnListView.contentHeight + 10)
                color: bgDark
                border.color: borderColor
                radius: 4

                ListView {
                    id: columnListView
                    anchors.fill: parent
                    anchors.margins: 5
                    clip: true
                    model: availableColumns
                    spacing: 2

                    delegate: RowLayout {
                        width: columnListView.width
                        spacing: 5

                        CheckBox {
                            id: columnCheck
                            checked: selectedColumns.indexOf(modelData) !== -1

                            indicator: Rectangle {
                                implicitWidth: 14
                                implicitHeight: 14
                                radius: 2
                                color: columnCheck.checked ? accentBlue : bgMedium
                                border.color: borderColor

                                Text {
                                    anchors.centerIn: parent
                                    text: "✓"
                                    color: textLight
                                    font.pixelSize: 10
                                    visible: columnCheck.checked
                                }
                            }

                            onCheckedChanged: {
                                var idx = selectedColumns.indexOf(modelData)
                                if (checked && idx === -1) {
                                    selectedColumns.push(modelData)
                                } else if (!checked && idx !== -1) {
                                    selectedColumns.splice(idx, 1)
                                }
                                updateParameter(paramName, selectedColumns)
                            }
                        }

                        Text {
                            text: modelData
                            color: textLight
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            // Select All / Deselect All buttons
            RowLayout {
                Layout.fillWidth: true
                spacing: 5

                Button {
                    text: "Select All"
                    Layout.fillWidth: true
                    implicitHeight: 24

                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignHCenter
                    }

                    background: Rectangle {
                        color: parent.hovered ? accentBlue : bgMedium
                        border.color: borderColor
                        radius: 3
                    }

                    onClicked: {
                        selectedColumns = availableColumns.slice()
                        updateParameter(paramName, selectedColumns)
                    }
                }

                Button {
                    text: "Deselect All"
                    Layout.fillWidth: true
                    implicitHeight: 24

                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignHCenter
                    }

                    background: Rectangle {
                        color: parent.hovered ? accentPink : bgMedium
                        border.color: borderColor
                        radius: 3
                    }

                    onClicked: {
                        selectedColumns = []
                        updateParameter(paramName, selectedColumns)
                    }
                }
            }

            Text {
                text: selectedColumns.length + " of " + availableColumns.length + " columns selected"
                color: textMuted
                font.pixelSize: 9
            }

            // Load columns from connected dataset
            Component.onCompleted: {
                // This will be populated when a dataset is connected
                // For now, show placeholder
                if (availableColumns.length === 0) {
                    availableColumns = ["(Connect dataset to see columns)"]
                }
                selectedColumns = currentValue || []
            }
        }
    }
}
