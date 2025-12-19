/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * TableEntity - Floating entity for displaying data tables
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FloatingEntity {
    id: tableEntity

    entityType: "table"
    entityTitle: "Table"
    minWidth: 350
    minHeight: 200

    // Table data
    property var tableData: []  // 2D array: [[row0col0, row0col1, ...], [row1col0, ...], ...]
    property var columnHeaders: []  // Array of column header strings
    property var rowHeaders: []  // Optional row headers

    // Display options
    property int columnWidth: 100
    property int rowHeight: 28
    property int headerHeight: 32
    property bool showRowNumbers: true
    property bool alternateRowColors: true

    // Selection
    property int selectedRow: -1
    property int selectedColumn: -1
    property var selectedCells: []  // Array of {row, col} for multi-selection

    // Signals
    signal cellClicked(int row, int col)
    signal cellDoubleClicked(int row, int col)
    signal selectionChanged(var cells)

    // Content component
    contentComponent: Component {
        Item {
            id: tableContent

            // Column header row
            Rectangle {
                id: headerRow
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: headerHeight
                color: bgLight
                clip: true

                Row {
                    id: headerRowContent
                    x: -horizontalScroll.position * (headerRowContent.width - headerRow.width) + (showRowNumbers ? 50 : 0)

                    // Row number header
                    Rectangle {
                        visible: showRowNumbers
                        width: 50
                        height: headerHeight
                        color: bgLight
                        x: horizontalScroll.position * (headerRowContent.width - headerRow.width)
                        z: 1

                        Rectangle {
                            anchors.right: parent.right
                            width: 1
                            height: parent.height
                            color: borderColor
                        }

                        Text {
                            anchors.centerIn: parent
                            text: "#"
                            font.pixelSize: 11
                            font.bold: true
                            color: textMuted
                        }
                    }

                    Repeater {
                        model: columnHeaders.length > 0 ? columnHeaders : (tableData.length > 0 ? tableData[0].length : 0)

                        Rectangle {
                            width: columnWidth
                            height: headerHeight
                            color: bgLight

                            Rectangle {
                                anchors.right: parent.right
                                width: 1
                                height: parent.height
                                color: borderColor
                            }

                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: 1
                                color: borderColor
                            }

                            Text {
                                anchors.centerIn: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                width: parent.width - 16
                                text: columnHeaders.length > 0 ? columnHeaders[index] : ("Col " + (index + 1))
                                font.pixelSize: 11
                                font.bold: true
                                color: textLight
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                            }

                            // Resize handle
                            MouseArea {
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: 6
                                cursorShape: Qt.SizeHorCursor

                                property real startX
                                property real startWidth

                                onPressed: function(mouse) {
                                    startX = mouse.x
                                    startWidth = columnWidth
                                }

                                onPositionChanged: function(mouse) {
                                    if (pressed) {
                                        var newWidth = startWidth + (mouse.x - startX)
                                        if (newWidth >= 50 && newWidth <= 400) {
                                            columnWidth = newWidth
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Table body with scrolling
            Flickable {
                id: tableFlickable
                anchors.top: headerRow.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                contentWidth: (columnHeaders.length > 0 ? columnHeaders.length : (tableData.length > 0 ? tableData[0].length : 1)) * columnWidth + (showRowNumbers ? 50 : 0)
                contentHeight: tableData.length * rowHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.horizontal: ScrollBar {
                    id: horizontalScroll
                    policy: tableFlickable.contentWidth > tableFlickable.width ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                }

                ScrollBar.vertical: ScrollBar {
                    id: verticalScroll
                    policy: tableFlickable.contentHeight > tableFlickable.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                }

                // Row number column (fixed)
                Column {
                    id: rowNumberColumn
                    visible: showRowNumbers
                    x: tableFlickable.contentX
                    z: 1

                    Repeater {
                        model: tableData.length

                        Rectangle {
                            width: 50
                            height: rowHeight
                            color: index === selectedRow ? Qt.darker(accentPink, 1.3) : bgMedium

                            Rectangle {
                                anchors.right: parent.right
                                width: 1
                                height: parent.height
                                color: borderColor
                            }

                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: 1
                                color: borderColor
                                opacity: 0.5
                            }

                            Text {
                                anchors.centerIn: parent
                                text: rowHeaders.length > index ? rowHeaders[index] : (index + 1).toString()
                                font.pixelSize: 10
                                color: textMuted
                            }
                        }
                    }
                }

                // Data cells
                Column {
                    id: dataColumn
                    x: showRowNumbers ? 50 : 0

                    Repeater {
                        id: rowRepeater
                        model: tableData.length

                        Row {
                            property int rowIndex: index

                            Repeater {
                                model: tableData.length > 0 ? tableData[rowIndex].length : 0

                                Rectangle {
                                    id: cell
                                    width: columnWidth
                                    height: rowHeight

                                    property int colIndex: index
                                    property bool isSelected: rowIndex === selectedRow && colIndex === selectedColumn

                                    color: {
                                        if (isSelected) return Qt.darker(accentBlue, 1.3)
                                        if (rowIndex === selectedRow) return Qt.darker(accentPink, 1.5)
                                        if (alternateRowColors && rowIndex % 2 === 1) return Qt.darker(bgMedium, 1.1)
                                        return bgMedium
                                    }

                                    Rectangle {
                                        anchors.right: parent.right
                                        width: 1
                                        height: parent.height
                                        color: borderColor
                                        opacity: 0.3
                                    }

                                    Rectangle {
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: 1
                                        color: borderColor
                                        opacity: 0.3
                                    }

                                    Text {
                                        anchors.fill: parent
                                        anchors.margins: 4
                                        text: formatCellValue(tableData[rowIndex][colIndex])
                                        font.pixelSize: 11
                                        color: isSelected ? textLight : textMuted
                                        elide: Text.ElideRight
                                        verticalAlignment: Text.AlignVCenter

                                        // Right-align numbers
                                        horizontalAlignment: isNumber(tableData[rowIndex][colIndex]) ?
                                            Text.AlignRight : Text.AlignLeft
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            selectedRow = rowIndex
                                            selectedColumn = colIndex
                                            cellClicked(rowIndex, colIndex)
                                        }
                                        onDoubleClicked: {
                                            cellDoubleClicked(rowIndex, colIndex)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                visible: tableData.length === 0
                text: "No data loaded"
                font.pixelSize: 14
                color: textMuted
            }

            // Status bar
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 20
                color: bgLight
                visible: tableData.length > 0

                Rectangle {
                    anchors.top: parent.top
                    width: parent.width
                    height: 1
                    color: borderColor
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8

                    Text {
                        text: tableData.length + " rows × " +
                              (tableData.length > 0 ? tableData[0].length : 0) + " columns"
                        font.pixelSize: 10
                        color: textMuted
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: selectedRow >= 0 && selectedColumn >= 0 ?
                              "Cell: R" + (selectedRow + 1) + " C" + (selectedColumn + 1) : ""
                        font.pixelSize: 10
                        color: accentBlue
                    }
                }
            }
        }
    }

    // Helper functions
    function formatCellValue(value) {
        if (value === null || value === undefined) return ""
        if (typeof value === "number") {
            if (Number.isInteger(value)) return value.toString()
            if (Math.abs(value) < 0.001 || Math.abs(value) >= 10000) {
                return value.toExponential(3)
            }
            return value.toFixed(4)
        }
        return String(value)
    }

    function isNumber(value) {
        return typeof value === "number" && !isNaN(value)
    }

    function setData(data, headers, rowLabels) {
        tableData = data || []
        columnHeaders = headers || []
        rowHeaders = rowLabels || []
        selectedRow = -1
        selectedColumn = -1
    }

    function clearData() {
        tableData = []
        columnHeaders = []
        rowHeaders = []
        selectedRow = -1
        selectedColumn = -1
    }

    function getCell(row, col) {
        if (row >= 0 && row < tableData.length && col >= 0 && col < tableData[row].length) {
            return tableData[row][col]
        }
        return null
    }

    function setCell(row, col, value) {
        if (row >= 0 && row < tableData.length && col >= 0 && col < tableData[row].length) {
            var newData = tableData.slice()
            newData[row] = newData[row].slice()
            newData[row][col] = value
            tableData = newData
        }
    }

    function getSelectedData() {
        if (selectedRow >= 0 && selectedColumn >= 0) {
            return tableData[selectedRow][selectedColumn]
        }
        return null
    }

    function getRow(index) {
        if (index >= 0 && index < tableData.length) {
            return tableData[index]
        }
        return null
    }

    function getColumn(index) {
        if (tableData.length === 0) return []
        var col = []
        for (var i = 0; i < tableData.length; i++) {
            if (index < tableData[i].length) {
                col.push(tableData[i][index])
            }
        }
        return col
    }

    // Initialize from entityData when loaded
    onEntityDataChanged: {
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.tableData) tableData = entityData.tableData
            if (entityData.columnHeaders) columnHeaders = entityData.columnHeaders
            if (entityData.rowHeaders) rowHeaders = entityData.rowHeaders
        }
    }

    Component.onCompleted: {
        console.log("TableEntity created:", entityId)
        // Apply initial data if present
        if (entityData && typeof entityData === "object") {
            if (entityData.title) entityTitle = entityData.title
            if (entityData.tableData) tableData = entityData.tableData
            if (entityData.columnHeaders) columnHeaders = entityData.columnHeaders
        }
    }
}
