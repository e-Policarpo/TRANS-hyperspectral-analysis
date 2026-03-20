/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * TableWindowContent - Enhanced table window with spreadsheet, formulas, and plot integration
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs

Item {
    id: root
    focus: true

    // Backend reference (set by EmbeddedWindow onLoaded)
    property var backend: null

    // Table data model (set externally)
    property var tableModel: null

    // Table identifier for linking
    property string tableId: ""
    property string linkedGraphId: ""

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color accentPurple: mainWin ? mainWin.accentPurple : "#9B4F96"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Define size for scrolling
    implicitWidth: mainLayout.implicitWidth
    implicitHeight: mainLayout.implicitHeight

    // Signals
    signal plotRequested(int xColumn, var yColumns)
    signal dataModified()

    // Current selection
    property int selectedRow: -1
    property int selectedColumn: -1
    property int xColumnForPlot: 0
    property var yColumnsForPlot: []

    ColumnLayout {
        id: mainLayout
        anchors.fill: parent
        spacing: 0

        // Tab bar
        TabBar {
            id: tabBar
            Layout.fillWidth: true
            background: Rectangle { color: bgDarker }

            TabButton {
                text: "Data"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 0 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 0 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 0
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Columns"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 1 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 1 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 1
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Plot"
                width: implicitWidth
                background: Rectangle {
                    color: tabBar.currentIndex === 2 ? bgMedium : "transparent"
                }
                contentItem: Text {
                    text: parent.text
                    color: tabBar.currentIndex === 2 ? accentBlue : textMuted
                    font.pixelSize: 12
                    font.bold: tabBar.currentIndex === 2
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // Tab content
        StackLayout {
            id: tabStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // =============================================
            // Tab 0: Data (Spreadsheet)
            // =============================================
            Item {
                id: dataTab

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Formula bar
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        color: bgDarker

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 4
                            spacing: 8

                            // Cell reference display
                            Rectangle {
                                Layout.preferredWidth: 60
                                Layout.fillHeight: true
                                color: bgMedium
                                radius: 3

                                Text {
                                    id: cellRefDisplay
                                    anchors.centerIn: parent
                                    text: selectedRow >= 0 && selectedColumn >= 0 ?
                                          indexToLetter(selectedColumn) + (selectedRow + 1) : "A1"
                                    color: accentBlue
                                    font.pixelSize: 11
                                    font.bold: true
                                }
                            }

                            Text {
                                text: "fx"
                                color: accentPink
                                font.pixelSize: 12
                                font.bold: true
                                font.italic: true
                            }

                            // Formula input
                            TextField {
                                id: formulaInput
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                placeholderText: "Enter value or formula (start with =)"
                                color: textLight
                                font.pixelSize: 11

                                background: Rectangle {
                                    color: bgDark
                                    border.color: formulaInput.activeFocus ? accentBlue : borderColor
                                    radius: 3
                                }

                                onAccepted: {
                                    applyFormula()
                                }
                            }

                            Button {
                                text: "Apply"
                                Layout.preferredWidth: 60
                                onClicked: applyFormula()

                                background: Rectangle {
                                    color: parent.hovered ? accentBlue : bgLight
                                    radius: 3
                                    border.color: accentBlue
                                }
                                contentItem: Text {
                                    text: parent.text
                                    color: textLight
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }

                            Rectangle {
                                width: 1
                                Layout.fillHeight: true
                                color: borderColor
                            }

                            Button {
                                text: "Export CSV"
                                Layout.preferredWidth: 80
                                onClicked: tableExportDialog.open()

                                background: Rectangle {
                                    color: parent.hovered ? accentPink : bgLight
                                    radius: 3
                                    border.color: accentPink
                                }
                                contentItem: Text {
                                    text: parent.text
                                    color: textLight
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                    }

                    // Table view
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: bgDark

                        // Header row
                        Row {
                            id: headerRow
                            x: rowNumberWidth
                            y: 0
                            height: headerHeight
                            z: 2

                            Repeater {
                                model: tableModel ? tableModel.columns : 0

                                Rectangle {
                                    width: columnWidth
                                    height: headerHeight
                                    color: bgMedium
                                    border.color: borderColor
                                    border.width: 1

                                    Text {
                                        anchors.centerIn: parent
                                        text: tableModel ? tableModel.headerData(index, Qt.Horizontal) || indexToLetter(index) : indexToLetter(index)
                                        color: accentPink
                                        font.pixelSize: 11
                                        font.bold: true
                                        elide: Text.ElideRight
                                        width: parent.width - 8
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: selectColumn(index)
                                    }
                                }
                            }
                        }

                        // Row numbers column
                        Column {
                            id: rowNumberColumn
                            x: 0
                            y: headerHeight
                            width: rowNumberWidth
                            z: 2

                            Repeater {
                                model: tableModel ? tableModel.rows : 0

                                Rectangle {
                                    width: rowNumberWidth
                                    height: rowHeight
                                    color: bgMedium
                                    border.color: borderColor
                                    border.width: 1

                                    Text {
                                        anchors.centerIn: parent
                                        text: index + 1
                                        color: textMuted
                                        font.pixelSize: 10
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: selectRow(index)
                                    }
                                }
                            }
                        }

                        // Corner cell
                        Rectangle {
                            x: 0
                            y: 0
                            width: rowNumberWidth
                            height: headerHeight
                            color: bgDarker
                            border.color: borderColor
                            z: 3

                            MouseArea {
                                anchors.fill: parent
                                onClicked: selectAll()
                            }
                        }

                        // Data cells
                        Flickable {
                            id: tableFlickable
                            x: rowNumberWidth
                            y: headerHeight
                            width: parent.width - rowNumberWidth
                            height: parent.height - headerHeight
                            contentWidth: (tableModel ? tableModel.columns : 5) * columnWidth
                            contentHeight: (tableModel ? tableModel.rows : 10) * rowHeight
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds

                            ScrollBar.vertical: ScrollBar {
                                active: true
                                policy: ScrollBar.AsNeeded
                            }
                            ScrollBar.horizontal: ScrollBar {
                                active: true
                                policy: ScrollBar.AsNeeded
                            }

                            // Grid of cells
                            Grid {
                                id: cellGrid
                                columns: tableModel ? tableModel.columns : 5
                                rows: tableModel ? tableModel.rows : 10

                                Repeater {
                                    model: (tableModel ? tableModel.rows : 10) * (tableModel ? tableModel.columns : 5)

                                    Rectangle {
                                        id: cellDelegate
                                        width: columnWidth
                                        height: rowHeight
                                        color: {
                                            var row = Math.floor(index / (tableModel ? tableModel.columns : 5))
                                            var col = index % (tableModel ? tableModel.columns : 5)
                                            if (row === selectedRow && col === selectedColumn) {
                                                return accentBlue + "40"
                                            }
                                            return row % 2 === 0 ? bgDark : bgDarker
                                        }
                                        border.color: {
                                            var row = Math.floor(index / (tableModel ? tableModel.columns : 5))
                                            var col = index % (tableModel ? tableModel.columns : 5)
                                            if (row === selectedRow && col === selectedColumn) {
                                                return accentBlue
                                            }
                                            return "#333333"
                                        }
                                        border.width: 1

                                        property int cellRow: Math.floor(index / (tableModel ? tableModel.columns : 5))
                                        property int cellCol: index % (tableModel ? tableModel.columns : 5)

                                        Text {
                                            anchors.fill: parent
                                            anchors.margins: 4
                                            text: tableModel ? (tableModel.data(tableModel.index(cellDelegate.cellRow, cellDelegate.cellCol)) || "") : ""
                                            color: textLight
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            horizontalAlignment: Text.AlignRight
                                            verticalAlignment: Text.AlignVCenter
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            onClicked: selectCell(cellDelegate.cellRow, cellDelegate.cellCol)
                                            onDoubleClicked: editCell(cellDelegate.cellRow, cellDelegate.cellCol)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Status bar
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 24
                        color: bgDarker

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 4
                            spacing: 16

                            Text {
                                text: (tableModel ? tableModel.rows : 0) + " rows x " + (tableModel ? tableModel.columns : 0) + " columns"
                                color: textMuted
                                font.pixelSize: 10
                            }

                            Text {
                                text: selectedRow >= 0 && selectedColumn >= 0 ?
                                      "Selected: " + indexToLetter(selectedColumn) + (selectedRow + 1) : ""
                                color: accentBlue
                                font.pixelSize: 10
                            }

                            Item { Layout.fillWidth: true }

                            Text {
                                id: statisticsDisplay
                                text: ""
                                color: textMuted
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }

            // =============================================
            // Tab 1: Columns Configuration
            // =============================================
            Item {
                id: columnsTab

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    Label {
                        text: "Column Configuration"
                        color: accentPink
                        font.pixelSize: 14
                        font.bold: true
                    }

                    ListView {
                        id: columnsList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: tableModel ? tableModel.columns : 0
                        spacing: 4

                        delegate: Rectangle {
                            width: columnsList.width
                            height: 100
                            color: bgMedium
                            radius: 4
                            border.color: borderColor

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4

                                // Column header
                                RowLayout {
                                    Layout.fillWidth: true

                                    Text {
                                        text: indexToLetter(index) + ":"
                                        color: accentBlue
                                        font.pixelSize: 12
                                        font.bold: true
                                    }

                                    TextField {
                                        id: nameField
                                        Layout.fillWidth: true
                                        text: tableModel ? (tableModel.getColumnMetadata(index).name || "") : ""
                                        placeholderText: "Column name"
                                        color: textLight
                                        font.pixelSize: 11

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: nameField.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }

                                        onEditingFinished: {
                                            if (tableModel) {
                                                var meta = tableModel.getColumnMetadata(index)
                                                tableModel.setColumnMetadata(index, text, meta.unit || "", meta.comment || "")
                                            }
                                        }
                                    }
                                }

                                // Unit and comment
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label { text: "Unit:"; color: textMuted; font.pixelSize: 10 }
                                    TextField {
                                        id: unitField
                                        Layout.preferredWidth: 80
                                        text: tableModel ? (tableModel.getColumnMetadata(index).unit || "") : ""
                                        color: textLight
                                        font.pixelSize: 10

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: unitField.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }

                                        onEditingFinished: {
                                            if (tableModel) {
                                                var meta = tableModel.getColumnMetadata(index)
                                                tableModel.setColumnMetadata(index, meta.name || "", text, meta.comment || "")
                                            }
                                        }
                                    }

                                    Label { text: "Comment:"; color: textMuted; font.pixelSize: 10 }
                                    TextField {
                                        id: commentField
                                        Layout.fillWidth: true
                                        text: tableModel ? (tableModel.getColumnMetadata(index).comment || "") : ""
                                        color: textLight
                                        font.pixelSize: 10

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: commentField.activeFocus ? accentBlue : borderColor
                                            radius: 3
                                        }

                                        onEditingFinished: {
                                            if (tableModel) {
                                                var meta = tableModel.getColumnMetadata(index)
                                                tableModel.setColumnMetadata(index, meta.name || "", meta.unit || "", text)
                                            }
                                        }
                                    }
                                }

                                // Column formula
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4

                                    Label { text: "Formula:"; color: textMuted; font.pixelSize: 10 }
                                    TextField {
                                        id: colFormulaField
                                        Layout.fillWidth: true
                                        text: tableModel ? (tableModel.getColumnMetadata(index).formula || "") : ""
                                        placeholderText: "[A] * 2 + [B]"
                                        color: textLight
                                        font.pixelSize: 10

                                        background: Rectangle {
                                            color: bgDark
                                            border.color: colFormulaField.activeFocus ? accentPink : borderColor
                                            radius: 3
                                        }
                                    }

                                    Button {
                                        text: "Apply"
                                        Layout.preferredWidth: 50
                                        onClicked: {
                                            if (tableModel) {
                                                tableModel.setColumnFormula(index, colFormulaField.text)
                                            }
                                        }

                                        background: Rectangle {
                                            color: parent.hovered ? accentPink : bgLight
                                            radius: 3
                                        }
                                        contentItem: Text {
                                            text: parent.text
                                            color: textLight
                                            font.pixelSize: 9
                                            horizontalAlignment: Text.AlignHCenter
                                        }
                                    }
                                }
                            }
                        }

                        ScrollBar.vertical: ScrollBar { active: true }
                    }

                    // Add/remove column buttons
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Button {
                            text: "+ Add Column"
                            onClicked: addColumnDialog.open()

                            background: Rectangle {
                                color: parent.hovered ? accentBlue : bgLight
                                radius: 4
                                border.color: accentBlue
                            }
                            contentItem: Text {
                                text: parent.text
                                color: textLight
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Button {
                            text: "+ Add Row"
                            onClicked: {
                                if (tableModel) tableModel.addRow()
                            }

                            background: Rectangle {
                                color: parent.hovered ? accentPurple : bgLight
                                radius: 4
                                border.color: accentPurple
                            }
                            contentItem: Text {
                                text: parent.text
                                color: textLight
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // =============================================
            // Tab 2: Plot Selection
            // =============================================
            Item {
                id: plotTab

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 12

                    Label {
                        text: "Plot Data"
                        color: accentPink
                        font.pixelSize: 14
                        font.bold: true
                    }

                    // X Column selection
                    GroupBox {
                        title: "X Axis Column"
                        Layout.fillWidth: true

                        background: Rectangle {
                            color: bgMedium
                            radius: 4
                            border.color: borderColor
                        }

                        label: Label {
                            text: parent.title
                            color: accentBlue
                            font.bold: true
                        }

                        ComboBox {
                            id: xColumnCombo
                            anchors.fill: parent
                            model: columnNamesModel
                            currentIndex: xColumnForPlot

                            onCurrentIndexChanged: {
                                xColumnForPlot = currentIndex
                            }

                            background: Rectangle {
                                color: bgDark
                                border.color: borderColor
                                radius: 3
                            }
                            contentItem: Text {
                                text: parent.displayText
                                color: textLight
                                font.pixelSize: 12
                                leftPadding: 8
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    // Y Columns selection
                    GroupBox {
                        title: "Y Axis Columns (select one or more)"
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        background: Rectangle {
                            color: bgMedium
                            radius: 4
                            border.color: borderColor
                        }

                        label: Label {
                            text: parent.title
                            color: accentPink
                            font.bold: true
                        }

                        ListView {
                            id: yColumnsList
                            anchors.fill: parent
                            clip: true
                            model: columnNamesModel
                            spacing: 2

                            delegate: Rectangle {
                                width: yColumnsList.width
                                height: 32
                                color: isSelected ? accentBlue + "30" : "transparent"
                                radius: 3

                                property bool isSelected: yColumnsForPlot.indexOf(index) >= 0

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    spacing: 8

                                    CheckBox {
                                        checked: parent.parent.isSelected
                                        onCheckedChanged: {
                                            toggleYColumn(index, checked)
                                        }

                                        indicator: Rectangle {
                                            implicitWidth: 18
                                            implicitHeight: 18
                                            radius: 3
                                            color: bgLight
                                            border.color: parent.checked ? accentPink : borderColor

                                            Rectangle {
                                                width: 10
                                                height: 10
                                                x: 4
                                                y: 4
                                                radius: 2
                                                color: accentPink
                                                visible: parent.parent.checked
                                            }
                                        }
                                    }

                                    Text {
                                        text: modelData
                                        color: textLight
                                        font.pixelSize: 12
                                        Layout.fillWidth: true
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    z: -1
                                    onClicked: toggleYColumn(index, !parent.isSelected)
                                }
                            }

                            ScrollBar.vertical: ScrollBar { active: true }
                        }
                    }

                    // Plot button
                    Button {
                        text: "Plot Selected Columns"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        enabled: yColumnsForPlot.length > 0

                        onClicked: {
                            plotRequested(xColumnForPlot, yColumnsForPlot)
                        }

                        background: Rectangle {
                            color: parent.enabled ? (parent.hovered ? accentPink : accentBlue) : bgLight
                            radius: 6
                            border.color: parent.enabled ? accentPink : borderColor
                            border.width: 2
                        }
                        contentItem: Text {
                            text: parent.text
                            color: parent.enabled ? textLight : textMuted
                            font.pixelSize: 14
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    // Statistics
                    GroupBox {
                        title: "Selected Column Statistics"
                        Layout.fillWidth: true
                        visible: yColumnsForPlot.length === 1

                        background: Rectangle {
                            color: bgMedium
                            radius: 4
                            border.color: borderColor
                        }

                        label: Label {
                            text: parent.title
                            color: accentPurple
                            font.bold: true
                        }

                        GridLayout {
                            anchors.fill: parent
                            columns: 4
                            rowSpacing: 4
                            columnSpacing: 16

                            Label { text: "Mean:"; color: textMuted; font.pixelSize: 10 }
                            Label { id: statMean; text: "---"; color: textLight; font.pixelSize: 10 }
                            Label { text: "Std:"; color: textMuted; font.pixelSize: 10 }
                            Label { id: statStd; text: "---"; color: textLight; font.pixelSize: 10 }

                            Label { text: "Min:"; color: textMuted; font.pixelSize: 10 }
                            Label { id: statMin; text: "---"; color: textLight; font.pixelSize: 10 }
                            Label { text: "Max:"; color: textMuted; font.pixelSize: 10 }
                            Label { id: statMax; text: "---"; color: textLight; font.pixelSize: 10 }
                        }
                    }
                }
            }
        }
    }

    // Column names model
    ListModel {
        id: columnNamesModel
    }

    // Constants
    property int columnWidth: 100
    property int rowHeight: 24
    property int headerHeight: 28
    property int rowNumberWidth: 50

    // Helper functions
    function indexToLetter(idx) {
        var result = ""
        idx += 1
        while (idx > 0) {
            idx -= 1
            result = String.fromCharCode(65 + idx % 26) + result
            idx = Math.floor(idx / 26)
        }
        return result
    }

    function selectCell(row, col) {
        selectedRow = row
        selectedColumn = col

        // Update formula bar
        if (tableModel) {
            var value = tableModel.data(tableModel.index(row, col), Qt.EditRole)
            formulaInput.text = value || ""
        }
    }

    function selectRow(row) {
        selectedRow = row
        selectedColumn = -1
    }

    function selectColumn(col) {
        selectedRow = -1
        selectedColumn = col

        // Calculate and display statistics
        if (tableModel) {
            var stats = tableModel.calculateColumnStatistics(col)
            if (stats && !stats.error) {
                statisticsDisplay.text = "Mean: " + stats.mean.toFixed(4) + " | Std: " + stats.std.toFixed(4)
            }
        }
    }

    function selectAll() {
        selectedRow = -1
        selectedColumn = -1
    }

    function editCell(row, col) {
        selectCell(row, col)
        formulaInput.forceActiveFocus()
        formulaInput.selectAll()
    }

    function applyFormula() {
        if (selectedRow >= 0 && selectedColumn >= 0 && tableModel) {
            tableModel.setData(tableModel.index(selectedRow, selectedColumn), formulaInput.text, Qt.EditRole)
            dataModified()
        }
    }

    function toggleYColumn(index, selected) {
        var newSelection = yColumnsForPlot.slice()
        var pos = newSelection.indexOf(index)

        if (selected && pos < 0) {
            newSelection.push(index)
        } else if (!selected && pos >= 0) {
            newSelection.splice(pos, 1)
        }

        yColumnsForPlot = newSelection

        // Update statistics for single selection
        if (yColumnsForPlot.length === 1 && tableModel) {
            var stats = tableModel.calculateColumnStatistics(yColumnsForPlot[0])
            if (stats && !stats.error) {
                statMean.text = stats.mean.toExponential(3)
                statStd.text = stats.std.toExponential(3)
                statMin.text = stats.min.toExponential(3)
                statMax.text = stats.max.toExponential(3)
            }
        }
    }

    function updateColumnNames() {
        columnNamesModel.clear()
        if (tableModel) {
            var names = tableModel.getColumnNames()
            for (var i = 0; i < names.length; i++) {
                columnNamesModel.append({name: names[i], index: i})
            }
        }
    }

    // Public API
    function setData(data, headers) {
        if (tableModel) {
            tableModel.setTableData(data, headers)
            updateColumnNames()
        }
    }

    function getPlotData(xCol, yCol) {
        if (tableModel) {
            return tableModel.getPlotData(xCol, yCol)
        }
        return [[], []]
    }

    // Dialog for adding columns
    Dialog {
        id: addColumnDialog
        title: "Add Column"
        modal: true
        anchors.centerIn: parent
        width: 300

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 8
        }

        header: Label {
            text: addColumnDialog.title
            color: accentPink
            font.pixelSize: 14
            font.bold: true
            padding: 12
        }

        contentItem: ColumnLayout {
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Name:"; color: textLight; Layout.preferredWidth: 60 }
                TextField {
                    id: newColumnName
                    Layout.fillWidth: true
                    placeholderText: "Column name"
                    color: textLight
                    background: Rectangle {
                        color: bgDark
                        border.color: newColumnName.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Unit:"; color: textLight; Layout.preferredWidth: 60 }
                TextField {
                    id: newColumnUnit
                    Layout.fillWidth: true
                    placeholderText: "Unit (optional)"
                    color: textLight
                    background: Rectangle {
                        color: bgDark
                        border.color: newColumnUnit.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }
                }
            }
        }

        footer: RowLayout {
            spacing: 8

            Item { Layout.fillWidth: true }

            Button {
                text: "Cancel"
                onClicked: addColumnDialog.close()
                background: Rectangle { color: bgLight; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; horizontalAlignment: Text.AlignHCenter }
            }

            Button {
                text: "Add"
                onClicked: {
                    if (tableModel && newColumnName.text) {
                        tableModel.addColumn(newColumnName.text, newColumnUnit.text, "")
                        updateColumnNames()
                        newColumnName.text = ""
                        newColumnUnit.text = ""
                    }
                    addColumnDialog.close()
                }
                background: Rectangle { color: accentBlue; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    // CSV export dialog
    FileDialog {
        id: tableExportDialog
        title: "Export Table as CSV"
        fileMode: FileDialog.SaveFile
        nameFilters: ["CSV files (*.csv)"]

        onAccepted: {
            var filePath = selectedFile.toString()
            if (filePath.startsWith("file:///")) {
                filePath = filePath.substring(7)
            } else if (filePath.startsWith("file://")) {
                filePath = filePath.substring(7)
            }

            if (tableModel) {
                var success = tableModel.exportToCSV(filePath)
                if (success) {
                    console.log("Table exported to: " + filePath)
                } else {
                    console.warn("Table export failed")
                }
            }
        }
    }

    // Keyboard shortcuts for copy/paste
    Keys.onPressed: function(event) {
        if (event.modifiers & Qt.ControlModifier) {
            if (event.key === Qt.Key_C) {
                // Copy selected cell or range
                if (tableModel && selectedRow >= 0 && selectedColumn >= 0) {
                    tableModel.copyRange(selectedRow, selectedColumn, selectedRow, selectedColumn)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_V) {
                // Paste at selected cell
                if (tableModel && selectedRow >= 0 && selectedColumn >= 0) {
                    tableModel.pasteFromClipboard(selectedRow, selectedColumn, "")
                }
                event.accepted = true
            }
        }
    }

    // Initialize
    Component.onCompleted: {
        console.log("TableWindowContent created")
        updateColumnNames()
    }

    // Watch for model changes
    onTableModelChanged: {
        updateColumnNames()
    }
}
