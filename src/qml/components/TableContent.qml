/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * TableContent - Self-contained spreadsheet component
 * Opens with empty dataset, supports inline editing, formulas, and column math
 * Made by Eduarda Policarpo, with love
 * Date: December 2025
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: tableContent

    property string entityId: ""
    property var backend: null

    // Table dimensions
    property int numRows: 20
    property int numCols: 5

    // Display options
    property int columnWidth: 100
    property int rowHeight: 26
    property int headerHeight: 28
    property int rowNumberWidth: 45

    // Selection
    property int selectedRow: -1
    property int selectedColumn: -1
    property int editingRow: -1
    property int editingColumn: -1

    // Theme colors
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgDarker: mainWin ? mainWin.bgDarker : "#0d0d1a"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Data storage - simple 2D array
    property var tableData: []
    property var columnNames: []

    // Initialize empty table
    function initEmptyTable(rows, cols) {
        var data = []
        var names = []
        for (var c = 0; c < cols; c++) {
            names.push(getColumnLetter(c))
        }
        for (var r = 0; r < rows; r++) {
            var row = []
            for (c = 0; c < cols; c++) {
                row.push("")
            }
            data.push(row)
        }
        tableData = data
        columnNames = names
        numRows = rows
        numCols = cols
    }

    // Get cell value
    function getCellValue(row, col) {
        if (row >= 0 && row < tableData.length && col >= 0 && col < (tableData[0] ? tableData[0].length : 0)) {
            return tableData[row][col]
        }
        return ""
    }

    // Set cell value
    function setCellValue(row, col, value) {
        if (row >= 0 && row < tableData.length && col >= 0 && col < tableData[0].length) {
            var newData = tableData.slice()
            newData[row] = newData[row].slice()
            newData[row][col] = value
            tableData = newData
        }
    }

    // Parse value (number or string)
    function parseValue(val) {
        if (val === "" || val === null || val === undefined) return ""
        var str = String(val).trim()
        // Try to parse as number
        var num = parseFloat(str.replace(",", "."))
        if (!isNaN(num)) return num
        return str
    }

    // Format value for display
    function formatValue(val) {
        if (val === "" || val === null || val === undefined) return ""
        if (typeof val === "number") {
            if (Math.abs(val) < 0.001 && val !== 0) return val.toExponential(3)
            if (Math.abs(val) > 99999) return val.toExponential(3)
            return val.toPrecision(6).replace(/\.?0+$/, "")
        }
        return String(val)
    }

    // Column letter from index
    function getColumnLetter(idx) {
        var result = ""
        var n = idx + 1
        while (n > 0) {
            n -= 1
            result = String.fromCharCode(65 + (n % 26)) + result
            n = Math.floor(n / 26)
        }
        return result
    }

    // Add row
    function addRow() {
        var newRow = []
        for (var c = 0; c < numCols; c++) {
            newRow.push("")
        }
        tableData = tableData.concat([newRow])
        numRows++
    }

    // Add column
    function addColumn(name) {
        var colName = name || getColumnLetter(numCols)
        columnNames = columnNames.concat([colName])
        var newData = []
        for (var r = 0; r < tableData.length; r++) {
            newData.push(tableData[r].concat([""]))
        }
        tableData = newData
        numCols++
    }

    // Fill column with formula
    function fillColumnWithFormula(colIdx, formula) {
        var newData = tableData.slice()
        for (var r = 0; r < newData.length; r++) {
            newData[r] = newData[r].slice()
            var result = evaluateFormula(formula, r, colIdx)
            newData[r][colIdx] = result
        }
        tableData = newData
    }

    // Simple formula evaluator
    function evaluateFormula(formula, row, col) {
        try {
            var expr = formula

            // Replace 'i' with row number (1-based)
            expr = expr.replace(/\bi\b/g, String(row + 1))

            // Replace [A], [B], etc. with column values
            var colRefPattern = /\[([A-Z]+)\]/g
            var match
            while ((match = colRefPattern.exec(formula)) !== null) {
                var colLetter = match[1]
                var refCol = 0
                for (var i = 0; i < colLetter.length; i++) {
                    refCol = refCol * 26 + (colLetter.charCodeAt(i) - 64)
                }
                refCol -= 1
                var refVal = getCellValue(row, refCol)
                var numVal = parseFloat(String(refVal).replace(",", ".")) || 0
                expr = expr.replace(match[0], numVal)
            }

            // Replace math functions
            expr = expr.replace(/sin\(/g, "Math.sin(")
            expr = expr.replace(/cos\(/g, "Math.cos(")
            expr = expr.replace(/sqrt\(/g, "Math.sqrt(")
            expr = expr.replace(/abs\(/g, "Math.abs(")
            expr = expr.replace(/log\(/g, "Math.log(")
            expr = expr.replace(/exp\(/g, "Math.exp(")
            expr = expr.replace(/\^/g, "**")
            expr = expr.replace(/pi/g, "Math.PI")

            // Safe eval
            var result = Function('"use strict"; return (' + expr + ')')()
            return isNaN(result) ? 0 : result
        } catch (e) {
            console.log("Formula error:", e, "formula:", formula)
            return 0
        }
    }

    // Calculate column statistics
    function calcColumnStats(colIdx) {
        var values = []
        for (var r = 0; r < tableData.length; r++) {
            var val = parseFloat(String(getCellValue(r, colIdx)).replace(",", "."))
            if (!isNaN(val)) values.push(val)
        }
        if (values.length === 0) return null

        var sum = values.reduce(function(a, b) { return a + b }, 0)
        var mean = sum / values.length
        var variance = values.reduce(function(acc, val) { return acc + Math.pow(val - mean, 2) }, 0) / values.length
        var std = Math.sqrt(variance)
        var min = Math.min.apply(null, values)
        var max = Math.max.apply(null, values)

        return { count: values.length, mean: mean, std: std, min: min, max: max, sum: sum }
    }

    // Sort by column
    function sortByColumn(colIdx, ascending) {
        var indices = []
        for (var i = 0; i < tableData.length; i++) indices.push(i)

        indices.sort(function(a, b) {
            var valA = parseValue(getCellValue(a, colIdx))
            var valB = parseValue(getCellValue(b, colIdx))

            // Handle numeric vs string comparison
            if (typeof valA === "number" && typeof valB === "number") {
                return ascending ? valA - valB : valB - valA
            }
            var strA = String(valA)
            var strB = String(valB)
            return ascending ? strA.localeCompare(strB) : strB.localeCompare(strA)
        })

        var newData = []
        for (i = 0; i < indices.length; i++) {
            newData.push(tableData[indices[i]].slice())
        }
        tableData = newData
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 36
            Layout.preferredHeight: 36
            color: bgDarker

            RowLayout {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 6

                // Cell reference display - fixed minimum, can shrink slightly
                Rectangle {
                    Layout.minimumWidth: 45
                    Layout.preferredWidth: 55
                    Layout.fillHeight: true
                    color: bgMedium
                    radius: 3

                    Text {
                        anchors.centerIn: parent
                        text: selectedRow >= 0 && selectedColumn >= 0 ?
                              getColumnLetter(selectedColumn) + (selectedRow + 1) : ""
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
                    Layout.alignment: Qt.AlignVCenter
                }

                // Formula/value input - takes all available space
                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 80
                    Layout.fillHeight: true
                    Layout.topMargin: 3
                    Layout.bottomMargin: 3
                    color: bgDark
                    border.color: formulaInput.activeFocus ? accentBlue : borderColor
                    radius: 3

                    TextInput {
                        id: formulaInput
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        verticalAlignment: Text.AlignVCenter
                        color: textLight
                        font.pixelSize: 12
                        selectByMouse: true
                        clip: true

                        onAccepted: {
                            if (selectedRow >= 0 && selectedColumn >= 0) {
                                setCellValue(selectedRow, selectedColumn, parseValue(text))
                                // Move to next row
                                if (selectedRow < numRows - 1) {
                                    selectCell(selectedRow + 1, selectedColumn)
                                }
                            }
                        }

                        Keys.onTabPressed: {
                            if (selectedRow >= 0 && selectedColumn >= 0) {
                                setCellValue(selectedRow, selectedColumn, parseValue(text))
                                if (selectedColumn < numCols - 1) {
                                    selectCell(selectedRow, selectedColumn + 1)
                                }
                            }
                        }
                    }
                }

                // Toolbar buttons - fixed size, don't shrink
                RowLayout {
                    Layout.alignment: Qt.AlignVCenter
                    spacing: 4

                    ToolButton {
                        text: "+"
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 26
                        onClicked: addRow()
                        ToolTip.text: "Add Row"
                        ToolTip.visible: hovered

                        background: Rectangle {
                            color: parent.hovered ? accentBlue : bgLight
                            radius: 3
                        }
                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            font.pixelSize: 14
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    ToolButton {
                        text: "Col"
                        Layout.preferredWidth: 36
                        Layout.preferredHeight: 26
                        onClicked: addColumn()
                        ToolTip.text: "Add Column"
                        ToolTip.visible: hovered

                        background: Rectangle {
                            color: parent.hovered ? accentPink : bgLight
                            radius: 3
                        }
                        contentItem: Text {
                            text: parent.text
                            color: textLight
                            font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }
        }

        // Spreadsheet area
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            clip: true

            // Corner cell
            Rectangle {
                id: cornerCell
                x: 0
                y: 0
                width: rowNumberWidth
                height: headerHeight
                color: bgDarker
                border.color: borderColor
                z: 10

                Text {
                    anchors.centerIn: parent
                    text: "#"
                    color: textMuted
                    font.pixelSize: 10
                }
            }

            // Column headers
            Row {
                id: headerRow
                x: rowNumberWidth - cellFlickable.contentX
                y: 0
                height: headerHeight
                z: 5

                Repeater {
                    model: numCols

                    Rectangle {
                        width: columnWidth
                        height: headerHeight
                        color: index === selectedColumn ? accentBlue : bgMedium
                        border.color: borderColor

                        Text {
                            anchors.centerIn: parent
                            text: columnNames[index] || getColumnLetter(index)
                            color: index === selectedColumn ? bgDark : accentPink
                            font.pixelSize: 11
                            font.bold: true
                            elide: Text.ElideRight
                            width: parent.width - 8
                            horizontalAlignment: Text.AlignHCenter
                        }

                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.RightButton) {
                                    columnMenu.targetColumn = index
                                    columnMenu.popup()
                                } else {
                                    selectedColumn = index
                                    selectedRow = -1
                                }
                            }
                        }
                    }
                }
            }

            // Row numbers
            Column {
                id: rowNumberCol
                x: 0
                y: headerHeight - cellFlickable.contentY
                width: rowNumberWidth
                z: 5

                Repeater {
                    model: numRows

                    Rectangle {
                        width: rowNumberWidth
                        height: rowHeight
                        color: index === selectedRow ? accentPink : bgMedium
                        border.color: borderColor

                        Text {
                            anchors.centerIn: parent
                            text: index + 1
                            color: index === selectedRow ? bgDark : textMuted
                            font.pixelSize: 10
                        }

                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                selectedRow = index
                                selectedColumn = -1
                            }
                        }
                    }
                }
            }

            // Cell grid
            Flickable {
                id: cellFlickable
                x: rowNumberWidth
                y: headerHeight
                width: parent.width - rowNumberWidth
                height: parent.height - headerHeight
                contentWidth: numCols * columnWidth
                contentHeight: numRows * rowHeight
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

                Grid {
                    id: cellGrid
                    columns: numCols

                    Repeater {
                        id: cellRepeater
                        model: numRows * numCols

                        Rectangle {
                            id: cell
                            width: columnWidth
                            height: rowHeight

                            property int cellRow: Math.floor(index / numCols)
                            property int cellCol: index % numCols
                            property bool isSelected: cellRow === selectedRow && cellCol === selectedColumn
                            property bool isEditing: cellRow === editingRow && cellCol === editingColumn

                            color: {
                                if (isSelected) return accentBlue + "40"
                                if (cellRow === selectedRow || cellCol === selectedColumn) return bgLight + "60"
                                return cellRow % 2 === 0 ? bgDark : bgDarker
                            }
                            border.color: isSelected ? accentBlue : "#333"
                            border.width: isSelected ? 2 : 1

                            // Display text (hidden when editing)
                            Text {
                                anchors.fill: parent
                                anchors.margins: 4
                                visible: !cell.isEditing
                                text: formatValue(getCellValue(cell.cellRow, cell.cellCol))
                                color: textLight
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                            }

                            // Edit field (shown when editing)
                            TextInput {
                                id: cellEditor
                                anchors.fill: parent
                                anchors.margins: 2
                                visible: cell.isEditing
                                color: textLight
                                font.pixelSize: 11
                                selectByMouse: true
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter

                                onAccepted: {
                                    commitEdit()
                                    // Move down
                                    if (cell.cellRow < numRows - 1) {
                                        selectCell(cell.cellRow + 1, cell.cellCol)
                                        startEditing()
                                    } else {
                                        stopEditing()
                                    }
                                }

                                Keys.onEscapePressed: stopEditing()

                                Keys.onTabPressed: {
                                    commitEdit()
                                    if (cell.cellCol < numCols - 1) {
                                        selectCell(cell.cellRow, cell.cellCol + 1)
                                        startEditing()
                                    } else {
                                        stopEditing()
                                    }
                                }

                                function commitEdit() {
                                    if (cell.isEditing) {
                                        setCellValue(cell.cellRow, cell.cellCol, parseValue(text))
                                    }
                                    editingRow = -1
                                    editingColumn = -1
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: !cell.isEditing
                                onClicked: selectCell(cell.cellRow, cell.cellCol)
                                onDoubleClicked: {
                                    selectCell(cell.cellRow, cell.cellCol)
                                    startEditing()
                                }
                            }

                            onIsEditingChanged: {
                                if (isEditing) {
                                    cellEditor.text = String(getCellValue(cellRow, cellCol))
                                    cellEditor.forceActiveFocus()
                                    cellEditor.selectAll()
                                }
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
                    text: numRows + " rows, " + numCols + " cols"
                    color: textMuted
                    font.pixelSize: 10
                }

                Text {
                    id: statsText
                    text: ""
                    color: accentBlue
                    font.pixelSize: 10
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "Double-click to edit | Right-click header for options"
                    color: textMuted
                    font.pixelSize: 9
                }
            }
        }
    }

    // Column context menu
    Menu {
        id: columnMenu
        property int targetColumn: 0

        background: Rectangle { color: bgMedium; border.color: borderColor; radius: 4 }

        MenuItem {
            text: "Set Column Values..."
            onTriggered: { setValuesDialog.targetColumn = columnMenu.targetColumn; setValuesDialog.open() }
            background: Rectangle { color: parent.highlighted ? accentBlue : "transparent" }
            contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 11 }
        }
        MenuItem {
            text: "Fill with Row Numbers"
            onTriggered: fillColumnWithFormula(columnMenu.targetColumn, "i")
            background: Rectangle { color: parent.highlighted ? accentBlue : "transparent" }
            contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 11 }
        }
        MenuSeparator {}
        MenuItem {
            text: "Sort Ascending"
            onTriggered: sortByColumn(columnMenu.targetColumn, true)
            background: Rectangle { color: parent.highlighted ? accentBlue : "transparent" }
            contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 11 }
        }
        MenuItem {
            text: "Sort Descending"
            onTriggered: sortByColumn(columnMenu.targetColumn, false)
            background: Rectangle { color: parent.highlighted ? accentBlue : "transparent" }
            contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 11 }
        }
        MenuSeparator {}
        MenuItem {
            text: "Statistics"
            onTriggered: showColumnStats(columnMenu.targetColumn)
            background: Rectangle { color: parent.highlighted ? accentBlue : "transparent" }
            contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 11 }
        }
        MenuItem {
            text: "Clear Column"
            onTriggered: clearColumn(columnMenu.targetColumn)
            background: Rectangle { color: parent.highlighted ? accentPink : "transparent" }
            contentItem: Text { text: parent.text; color: accentPink; font.pixelSize: 11 }
        }
    }

    // Set column values dialog
    Dialog {
        id: setValuesDialog
        title: "Set Column Values"
        modal: true
        anchors.centerIn: parent
        width: 320
        property int targetColumn: 0

        background: Rectangle { color: bgMedium; border.color: borderColor; radius: 6 }
        header: Text { text: "Column " + getColumnLetter(setValuesDialog.targetColumn) + " Formula"; color: accentPink; font.pixelSize: 12; font.bold: true; padding: 12 }

        contentItem: ColumnLayout {
            spacing: 8

            Text { text: "Use: i (row), [A] (column), sin, cos, sqrt, ^"; color: textMuted; font.pixelSize: 9; wrapMode: Text.WordWrap }

            TextField {
                id: formulaField
                Layout.fillWidth: true
                text: "i"
                color: textLight
                font.family: "monospace"
                background: Rectangle { color: bgDark; border.color: borderColor; radius: 3 }
            }

            Text { text: "Examples: i^2, [A]*2, sin(i*0.1)"; color: textMuted; font.pixelSize: 9; font.italic: true }
        }

        footer: RowLayout {
            Item { Layout.fillWidth: true }
            Button {
                text: "Cancel"
                onClicked: setValuesDialog.close()
                background: Rectangle { color: bgLight; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter }
            }
            Button {
                text: "Apply"
                onClicked: {
                    fillColumnWithFormula(setValuesDialog.targetColumn, formulaField.text)
                    setValuesDialog.close()
                }
                background: Rectangle { color: accentBlue; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    // Functions
    function selectCell(row, col) {
        if (editingRow >= 0 && editingColumn >= 0) {
            stopEditing()
        }
        selectedRow = row
        selectedColumn = col

        if (row >= 0 && col >= 0) {
            formulaInput.text = String(getCellValue(row, col))
        }
    }

    function startEditing() {
        if (selectedRow >= 0 && selectedColumn >= 0) {
            editingRow = selectedRow
            editingColumn = selectedColumn
        }
    }

    function stopEditing() {
        editingRow = -1
        editingColumn = -1
    }

    function showColumnStats(col) {
        var stats = calcColumnStats(col)
        if (stats) {
            statsText.text = "Mean: " + stats.mean.toFixed(4) + " | Std: " + stats.std.toFixed(4) +
                             " | Min: " + stats.min.toFixed(4) + " | Max: " + stats.max.toFixed(4)
        } else {
            statsText.text = "No numeric data"
        }
    }

    function clearColumn(col) {
        var newData = tableData.slice()
        for (var r = 0; r < newData.length; r++) {
            newData[r] = newData[r].slice()
            newData[r][col] = ""
        }
        tableData = newData
    }

    // Keyboard shortcuts
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (editingRow < 0) {
                startEditing()
            }
            event.accepted = true
        } else if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) {
            if (editingRow < 0 && selectedRow >= 0 && selectedColumn >= 0) {
                setCellValue(selectedRow, selectedColumn, "")
            }
        } else if (event.key === Qt.Key_Up && editingRow < 0) {
            if (selectedRow > 0) selectCell(selectedRow - 1, selectedColumn)
        } else if (event.key === Qt.Key_Down && editingRow < 0) {
            if (selectedRow < numRows - 1) selectCell(selectedRow + 1, selectedColumn)
        } else if (event.key === Qt.Key_Left && editingRow < 0) {
            if (selectedColumn > 0) selectCell(selectedRow, selectedColumn - 1)
        } else if (event.key === Qt.Key_Right && editingRow < 0) {
            if (selectedColumn < numCols - 1) selectCell(selectedRow, selectedColumn + 1)
        }
    }

    Component.onCompleted: {
        console.log("TableContent created:", entityId)
        initEmptyTable(20, 5)
        forceActiveFocus()
    }
}
