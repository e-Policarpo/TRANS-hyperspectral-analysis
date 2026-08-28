/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * TableWindowContent - Spreadsheet with formula bar, right-click menu, column formulas
 * Uses TableView for virtualized cell rendering (only visible cells are instantiated)
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

    // Table data model (set externally by WindowManager from backend)
    property var tableModel: null

    // Entity ID for WindowManager
    property string entityId: ""

    // Table identifier for linking
    property string tableId: ""
    property string linkedGraphId: ""

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color accentPurple: (mainWin && mainWin.accentPurple !== undefined) ? mainWin.accentPurple : Theme.accentPurple
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor
    // The scheme's `error` key, for destructive affordances — delete
    // buttons and invalid-state warnings. Semantic, so it keeps the
    // warning reading; from the scheme, so it is not a fixed red.
    property color accentMagenta: (mainWin && mainWin.accentMagenta !== undefined) ? mainWin.accentMagenta : Theme.accentMagenta
    property string monoFont: mainWin ? mainWin.fontFamilyMono : (Qt.platform.os === "osx" ? "Menlo" : "Consolas")

    implicitWidth: mainLayout.implicitWidth
    implicitHeight: mainLayout.implicitHeight

    // Signals
    signal plotRequested(int xColumn, var yColumns)
    signal dataModified()

    // Selection state
    property int selectedRow: -1
    property int selectedColumn: -1
    property int selectionEndRow: -1
    property int selectionEndCol: -1

    // Layout constants
    property int columnWidth: 100
    property int rowHeight: 24
    property int headerHeight: 28
    property int rowNumberWidth: 50

    // Model dimensions (reactive via notify signals)
    property int numRows: tableModel ? tableModel.rows : 0
    property int numCols: tableModel ? tableModel.columns : 0

    // Revision counter — used in cell text bindings to force re-read when data changes
    property int dataRevision: tableModel ? tableModel.dataRevision : 0

    // Inline editing state
    property bool inlineEditing: false
    property string inlineEditText: ""

    // Drag-selection state
    property bool isDragging: false

    // =========================================================================
    // Main layout
    // =========================================================================
    ColumnLayout {
        id: mainLayout
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
                              indexToLetter(selectedColumn) + (selectedRow + 1) : ""
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

                    onAccepted: applyFormula()

                    Keys.onTabPressed: {
                        applyFormula()
                        moveSelection(0, 1)
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
                    text: "Plot"
                    Layout.preferredWidth: 55
                    onClicked: doPlotSelectedColumns()

                    background: Rectangle {
                        color: parent.hovered ? accentPurple : bgLight
                        radius: 3
                        border.color: accentPurple
                    }
                    contentItem: Text {
                        text: parent.text
                        color: textLight
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                // Promote this table to a dataset (SpectralData) so the dataset
                // tools can operate on it. The first column is the X axis.
                Button {
                    id: addAsDatasetBtn
                    text: "Add as Dataset"
                    Layout.preferredWidth: 110
                    // dataRevision dependency forces re-evaluation after edits.
                    enabled: tableModel !== null && dataRevision >= 0 && tableModel.canBeDataset()
                    ToolTip.visible: hovered
                    ToolTip.text: enabled
                        ? "Promote this table to a dataset you can run tools on"
                        : "Needs at least 2 columns with a numeric first column (X axis)"
                    onClicked: {
                        if (backend && tableModel) {
                            backend.createDatasetFromTable(tableModel, "")
                        }
                    }

                    background: Rectangle {
                        color: !addAsDatasetBtn.enabled ? bgMedium
                               : (addAsDatasetBtn.hovered ? accentBlue : bgLight)
                        radius: 3
                        border.color: accentBlue
                    }
                    contentItem: Text {
                        text: parent.text
                        color: addAsDatasetBtn.enabled ? textLight : textMuted
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignHCenter
                    }
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

        // =========================================================================
        // Spreadsheet area — virtualized with manual cell positioning
        // =========================================================================
        Rectangle {
            id: spreadsheetArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgDark
            clip: true

            // Corner cell (top-left)
            Rectangle {
                id: cornerCell
                x: 0; y: 0; z: 3
                width: rowNumberWidth
                height: headerHeight
                color: bgDarker
                border.color: borderColor

                MouseArea {
                    anchors.fill: parent
                    onClicked: selectAll()
                }
            }

            // Column headers (fixed at top, scrolls horizontally with data)
            Flickable {
                id: headerFlickable
                x: rowNumberWidth; y: 0; z: 2
                width: parent.width - rowNumberWidth
                height: headerHeight
                contentWidth: numCols * columnWidth + addColButtonWidth
                clip: true
                interactive: false
                contentX: dataFlickable.contentX

                property int addColButtonWidth: 32

                Row {
                    Repeater {
                        model: numCols

                        Rectangle {
                            width: columnWidth
                            height: headerHeight
                            color: isColumnInSelection(index) ? accentBlue + "40" : bgMedium
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
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: function(mouse) {
                                    if (mouse.button === Qt.RightButton) {
                                        contextColumn = index
                                        contextRow = -1
                                        columnContextMenu.popup()
                                    } else {
                                        selectColumn(index)
                                    }
                                }
                            }
                        }
                    }

                    // "+" button to add column
                    Rectangle {
                        width: headerFlickable.addColButtonWidth
                        height: headerHeight
                        color: bgDarker
                        border.color: borderColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "+"
                            color: accentBlue
                            font.pixelSize: 14
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: addColumnDialog.open()
                        }
                    }
                }
            }

            // Row numbers (fixed at left, scrolls vertically with data — virtualized)
            Item {
                id: rowNumArea
                x: 0; y: headerHeight; z: 2
                width: rowNumberWidth
                height: parent.height - headerHeight
                clip: true

                // Only create items for visible rows
                Repeater {
                    id: rowNumRepeater
                    model: {
                        if (numRows === 0) return 0
                        var visibleCount = Math.ceil(rowNumArea.height / rowHeight) + 1
                        return Math.min(visibleCount, numRows)
                    }

                    Rectangle {
                        property int rowIndex: {
                            var firstVisible = Math.floor(dataFlickable.contentY / rowHeight)
                            return firstVisible + index
                        }
                        visible: rowIndex >= 0 && rowIndex < numRows
                        x: 0
                        y: rowIndex * rowHeight - dataFlickable.contentY
                        width: rowNumberWidth
                        height: rowHeight
                        color: rowIndex === selectedRow ? accentBlue + "40" : bgMedium
                        border.color: borderColor
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: parent.rowIndex + 1
                            color: textMuted
                            font.pixelSize: 10
                        }

                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.RightButton) {
                                    contextRow = parent.rowIndex
                                    contextColumn = -1
                                    rowContextMenu.popup()
                                } else {
                                    selectRow(parent.rowIndex)
                                }
                            }
                        }
                    }
                }
            }

            // Data cells — Flickable with virtualized cell Repeater
            // Only ~300 items created for visible viewport (vs 16k+ for full grid)
            Flickable {
                id: dataFlickable
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

                // Visible cell pool — stable during scroll, only changes on resize
                property int visibleRowCount: Math.min(Math.ceil(height / rowHeight) + 2, Math.max(numRows, 1))
                property int visibleColCount: Math.min(Math.ceil(width / columnWidth) + 2, Math.max(numCols, 1))

                // First visible row/col — updates on scroll
                property int firstRow: Math.max(0, Math.floor(contentY / rowHeight))
                property int firstCol: Math.max(0, Math.floor(contentX / columnWidth))

                Item {
                    id: cellContainer
                    width: dataFlickable.contentWidth
                    height: dataFlickable.contentHeight

                    // Mouse overlay for selection — covers entire content area
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        hoverEnabled: false

                        onPressed: function(mouse) {
                            if (mouse.button === Qt.LeftButton) {
                                if (inlineEditing) commitInlineEdit()
                                root.forceActiveFocus()
                                var cellRow = Math.floor(mouse.y / rowHeight)
                                var cellCol = Math.floor(mouse.x / columnWidth)
                                cellRow = Math.max(0, Math.min(numRows - 1, cellRow))
                                cellCol = Math.max(0, Math.min(numCols - 1, cellCol))
                                if (mouse.modifiers & Qt.ShiftModifier) {
                                    selectionEndRow = cellRow
                                    selectionEndCol = cellCol
                                } else {
                                    selectCell(cellRow, cellCol)
                                    isDragging = true
                                }
                            }
                        }

                        onReleased: isDragging = false

                        onPositionChanged: function(mouse) {
                            if (isDragging && (mouse.buttons & Qt.LeftButton)) {
                                var hoverRow = Math.max(0, Math.min(numRows - 1, Math.floor(mouse.y / rowHeight)))
                                var hoverCol = Math.max(0, Math.min(numCols - 1, Math.floor(mouse.x / columnWidth)))
                                selectionEndRow = hoverRow
                                selectionEndCol = hoverCol
                            }
                        }

                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton) {
                                if (inlineEditing) commitInlineEdit()
                                root.forceActiveFocus()
                                contextRow = Math.max(0, Math.min(numRows - 1, Math.floor(mouse.y / rowHeight)))
                                contextColumn = Math.max(0, Math.min(numCols - 1, Math.floor(mouse.x / columnWidth)))
                                cellContextMenu.popup()
                            }
                        }

                        onDoubleClicked: function(mouse) {
                            isDragging = false
                            var cellRow = Math.max(0, Math.min(numRows - 1, Math.floor(mouse.y / rowHeight)))
                            var cellCol = Math.max(0, Math.min(numCols - 1, Math.floor(mouse.x / columnWidth)))
                            selectCell(cellRow, cellCol)
                            startInlineEdit(true)
                        }
                    }

                    // Virtualized cell delegates — positioned via scroll-dependent bindings
                    Repeater {
                        id: cellRepeater
                        model: (numRows > 0 && numCols > 0)
                               ? dataFlickable.visibleRowCount * dataFlickable.visibleColCount
                               : 0

                        Rectangle {
                            id: cellRect
                            property int gridRow: dataFlickable.firstRow + Math.floor(index / dataFlickable.visibleColCount)
                            property int gridCol: dataFlickable.firstCol + (index % dataFlickable.visibleColCount)
                            property bool isValid: gridRow >= 0 && gridRow < numRows && gridCol >= 0 && gridCol < numCols
                            property bool isCurrent: isValid && gridRow === selectedRow && gridCol === selectedColumn
                            property bool inRange: isValid && isInSelection(gridRow, gridCol)

                            visible: isValid
                            x: gridCol * columnWidth
                            y: gridRow * rowHeight
                            width: columnWidth
                            height: rowHeight

                            color: isCurrent ? Qt.rgba(0.357, 0.808, 0.98, 0.31) :
                                   inRange   ? Qt.rgba(0.357, 0.808, 0.98, 0.13) :
                                               (gridRow % 2 === 0) ? bgDark : bgDarker

                            border.color: isCurrent ? accentBlue : borderColor
                            border.width: isCurrent ? 2 : 0.5

                            Text {
                                anchors.fill: parent
                                anchors.rightMargin: 4
                                anchors.leftMargin: 4
                                text: {
                                    if (!cellRect.isValid || !tableModel) return ""
                                    var rev = dataRevision
                                    return tableModel.data(tableModel.index(cellRect.gridRow, cellRect.gridCol)) || ""
                                }
                                color: textLight
                                font.pixelSize: 11
                                font.family: monoFont
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                                visible: !(cellRect.isCurrent && inlineEditing)
                            }
                        }
                    }
                }
            }

            // Inline editor overlay — positioned over the selected cell in the viewport
            TextInput {
                id: inlineCellEditor
                visible: inlineEditing && selectedRow >= 0 && selectedColumn >= 0
                x: visible ? rowNumberWidth + selectedColumn * columnWidth - dataFlickable.contentX : 0
                y: visible ? headerHeight + selectedRow * rowHeight - dataFlickable.contentY : 0
                width: columnWidth
                height: rowHeight
                z: 5
                color: textLight
                font.pixelSize: 11
                font.family: monoFont
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
                clip: true
                selectByMouse: true
                text: inlineEditText
                leftPadding: 4
                rightPadding: 4

                Rectangle {
                    anchors.fill: parent
                    z: -1
                    color: bgDark
                    border.color: accentBlue
                    border.width: 2
                }

                onAccepted: commitInlineEdit()
                Keys.onEscapePressed: cancelInlineEdit()
                Keys.onTabPressed: {
                    commitInlineEdit()
                    moveSelection(0, 1)
                }

                onVisibleChanged: {
                    if (visible) forceActiveFocus()
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
                spacing: 12

                Text {
                    text: numRows + " rows x " + numCols + " columns"
                    color: textMuted
                    font.pixelSize: 10
                }

                Text {
                    text: {
                        if (selectedRow < 0 || selectedColumn < 0) return ""
                        var anchor = indexToLetter(selectedColumn) + (selectedRow + 1)
                        if (selectionEndRow >= 0 && selectionEndCol >= 0 &&
                            (selectionEndRow !== selectedRow || selectionEndCol !== selectedColumn)) {
                            var end = indexToLetter(selectionEndCol) + (selectionEndRow + 1)
                            return "Selected: " + anchor + ":" + end
                        }
                        return "Selected: " + anchor
                    }
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

                // Number format controls
                Rectangle {
                    width: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 2
                    Layout.bottomMargin: 2
                    color: borderColor
                }

                ComboBox {
                    id: formatCombo
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 18
                    model: ["Auto", "Scientific", "Decimal"]
                    currentIndex: {
                        if (!tableModel) return 0
                        var fmt = tableModel.displayFormat
                        if (fmt === "scientific") return 1
                        if (fmt === "decimal") return 2
                        return 0
                    }
                    onActivated: function(index) {
                        var fmts = ["auto", "scientific", "decimal"]
                        if (tableModel) tableModel.setDisplayFormat(fmts[index], decimalSpin.value)
                    }
                    font.pixelSize: 10

                    background: Rectangle {
                        color: bgMedium
                        border.color: borderColor
                        radius: 2
                    }
                    contentItem: Text {
                        text: formatCombo.displayText
                        color: textLight
                        font.pixelSize: 10
                        leftPadding: 4
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                SpinBox {
                    id: decimalSpin
                    Layout.preferredWidth: 70
                    Layout.preferredHeight: 18
                    from: 0
                    to: 15
                    value: tableModel ? tableModel.decimalPlaces : 6
                    editable: true
                    font.pixelSize: 10

                    onValueModified: {
                        if (tableModel) {
                            var fmts = ["auto", "scientific", "decimal"]
                            tableModel.setDisplayFormat(fmts[formatCombo.currentIndex], value)
                        }
                    }

                    background: Rectangle {
                        color: bgMedium
                        border.color: borderColor
                        radius: 2
                    }
                    contentItem: TextInput {
                        text: decimalSpin.textFromValue(decimalSpin.value, decimalSpin.locale)
                        color: textLight
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        readOnly: !decimalSpin.editable
                        validator: decimalSpin.validator
                    }
                    up.indicator: Rectangle {
                        x: parent.width - width
                        width: 14
                        height: parent.height / 2
                        color: decimalSpin.up.pressed ? accentBlue : bgLight
                        radius: 2
                        Text { anchors.centerIn: parent; text: "+"; color: textLight; font.pixelSize: 8 }
                    }
                    down.indicator: Rectangle {
                        x: parent.width - width
                        y: parent.height / 2
                        width: 14
                        height: parent.height / 2
                        color: decimalSpin.down.pressed ? accentBlue : bgLight
                        radius: 2
                        Text { anchors.centerIn: parent; text: "-"; color: textLight; font.pixelSize: 8 }
                    }
                }

                Text {
                    text: "decimals"
                    color: textMuted
                    font.pixelSize: 9
                }
            }
        }
    }

    // =========================================================================
    // Context menus
    // =========================================================================

    // Track which row/col the context menu was opened on
    property int contextRow: -1
    property int contextColumn: -1

    // Cell right-click menu
    Menu {
        id: cellContextMenu

        MenuItem {
            text: "Plot Column"
            onTriggered: {
                if (contextColumn >= 0) {
                    doPlotColumn(contextColumn)
                }
            }
        }

        MenuSeparator {}

        MenuItem {
            text: "Insert Row Above"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.insertRowAt(contextRow)
        }
        MenuItem {
            text: "Insert Row Below"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.insertRowAt(contextRow + 1)
        }

        MenuSeparator {}

        MenuItem {
            text: "Insert Column Left"
            onTriggered: insertColumnAt(contextColumn)
        }
        MenuItem {
            text: "Insert Column Right"
            onTriggered: insertColumnAt(contextColumn + 1)
        }

        MenuSeparator {}

        MenuItem {
            text: "Set Column Values..."
            onTriggered: openSetColumnValuesDialog(contextColumn)
        }

        MenuSeparator {}

        MenuItem {
            text: "Copy"
            onTriggered: doCopy()
        }
        MenuItem {
            text: "Copy with Headers"
            onTriggered: doCopyWithHeaders()
        }
        MenuItem {
            text: "Cut"
            onTriggered: doCut()
        }
        MenuItem {
            text: "Paste"
            onTriggered: doPaste()
        }

        MenuSeparator {}

        MenuItem {
            text: "Clear Selection"
            onTriggered: doClearSelection()
        }
        MenuItem {
            text: "Delete Row"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.removeRowAt(contextRow)
        }
        MenuItem {
            text: "Delete Column"
            onTriggered: if (tableModel && contextColumn >= 0) tableModel.removeColumnAt(contextColumn)
        }
    }

    // Column header right-click menu
    Menu {
        id: columnContextMenu

        MenuItem {
            text: "Plot Column"
            onTriggered: {
                if (contextColumn >= 0) {
                    doPlotColumn(contextColumn)
                }
            }
        }

        MenuSeparator {}

        MenuItem {
            text: "Set Column Values..."
            onTriggered: openSetColumnValuesDialog(contextColumn)
        }

        MenuSeparator {}

        MenuItem {
            text: "Sort Ascending"
            onTriggered: if (tableModel && contextColumn >= 0) tableModel.sortByColumn(contextColumn, true)
        }
        MenuItem {
            text: "Sort Descending"
            onTriggered: if (tableModel && contextColumn >= 0) tableModel.sortByColumn(contextColumn, false)
        }

        MenuSeparator {}

        MenuItem {
            text: "Rename Column..."
            onTriggered: openRenameColumnDialog(contextColumn)
        }
        MenuItem {
            text: "Insert Column Left"
            onTriggered: insertColumnAt(contextColumn)
        }
        MenuItem {
            text: "Insert Column Right"
            onTriggered: insertColumnAt(contextColumn + 1)
        }

        MenuSeparator {}

        MenuItem {
            text: "Column Statistics"
            onTriggered: showColumnStats(contextColumn)
        }

        MenuSeparator {}

        MenuItem {
            text: "Copy Column"
            onTriggered: {
                selectColumn(contextColumn)
                doCopy()
            }
        }
        MenuItem {
            text: "Copy Column with Header"
            onTriggered: {
                selectColumn(contextColumn)
                doCopyWithHeaders()
            }
        }
        MenuItem {
            text: "Paste"
            onTriggered: doPaste()
        }

        MenuSeparator {}

        MenuItem {
            text: "Clear Column"
            onTriggered: if (tableModel && contextColumn >= 0) tableModel.clearColumn(contextColumn)
        }
        MenuItem {
            text: "Delete Column"
            onTriggered: if (tableModel && contextColumn >= 0) tableModel.removeColumnAt(contextColumn)
        }
    }

    // Row header right-click menu
    Menu {
        id: rowContextMenu

        MenuItem {
            text: "Insert Row Above"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.insertRowAt(contextRow)
        }
        MenuItem {
            text: "Insert Row Below"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.insertRowAt(contextRow + 1)
        }

        MenuSeparator {}

        MenuItem {
            text: "Copy Row"
            onTriggered: {
                selectRow(contextRow)
                doCopy()
            }
        }
        MenuItem {
            text: "Cut Row"
            onTriggered: {
                selectRow(contextRow)
                doCut()
            }
        }
        MenuItem {
            text: "Paste"
            onTriggered: doPaste()
        }

        MenuSeparator {}

        MenuItem {
            text: "Clear Row"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.clearRow(contextRow)
        }
        MenuItem {
            text: "Delete Row"
            onTriggered: if (tableModel && contextRow >= 0) tableModel.removeRowAt(contextRow)
        }
    }

    // =========================================================================
    // Dialogs
    // =========================================================================

    // Set Column Values dialog
    Dialog {
        id: setValuesDialog
        title: "Set Column Values"
        modal: true
        anchors.centerIn: parent
        width: 420
        height: 320

        property int targetColumn: 0

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 8
        }

        header: Rectangle {
            color: bgDarker
            height: 40
            radius: 8
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 8; color: parent.color }

            Text {
                anchors.centerIn: parent
                text: "Set Column Values"
                color: accentPink
                font.pixelSize: 14
                font.bold: true
            }
        }

        contentItem: ColumnLayout {
            spacing: 12
            anchors.margins: 12

            // Target column selector
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Target Column:"; color: textLight; font.pixelSize: 12 }
                ComboBox {
                    id: targetColumnCombo
                    Layout.fillWidth: true
                    model: columnNamesModel
                    currentIndex: setValuesDialog.targetColumn
                    onCurrentIndexChanged: setValuesDialog.targetColumn = currentIndex

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

            // Formula input
            Label { text: "Formula:"; color: textLight; font.pixelSize: 12 }
            TextField {
                id: columnFormulaField
                Layout.fillWidth: true
                placeholderText: "col(A) * 2 + col(B)"
                color: textLight
                font.pixelSize: 12
                font.family: monoFont

                background: Rectangle {
                    color: bgDark
                    border.color: columnFormulaField.activeFocus ? accentPink : borderColor
                    radius: 3
                }
            }

            // Syntax help
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDarker
                radius: 4

                Text {
                    anchors.fill: parent
                    anchors.margins: 8
                    text: "Syntax:\n" +
                          "  col(A), col(B)  — reference columns by letter\n" +
                          "  [A], [B]        — alternative column reference\n" +
                          "  i               — row number (1-based)\n" +
                          "  sin, cos, sqrt, log, exp, abs, pi\n\n" +
                          "Examples:\n" +
                          "  col(A) * 1000\n" +
                          "  sin(col(A) * pi / 180) + col(B)\n" +
                          "  i * 0.1"
                    color: textMuted
                    font.pixelSize: 10
                    font.family: monoFont
                    wrapMode: Text.Wrap
                }
            }
        }

        footer: Rectangle {
            color: bgDarker
            height: 50
            radius: 8
            Rectangle { anchors.top: parent.top; width: parent.width; height: 8; color: parent.color }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10

                Item { Layout.fillWidth: true }

                Button {
                    text: "Cancel"
                    onClicked: setValuesDialog.close()
                    background: Rectangle { color: bgLight; radius: 4 }
                    contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter }
                }

                Button {
                    text: "Apply"
                    onClicked: {
                        if (tableModel && columnFormulaField.text) {
                            tableModel.setColumnFormula(setValuesDialog.targetColumn, columnFormulaField.text)
                            dataModified()
                        }
                        setValuesDialog.close()
                    }
                    background: Rectangle { color: accentBlue; radius: 4 }
                    contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 12; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                }
            }
        }
    }

    // Rename column dialog
    Dialog {
        id: renameColumnDialog
        title: "Rename Column"
        modal: true
        anchors.centerIn: parent
        width: 300

        property int targetColumn: 0

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 8
        }

        header: Label {
            text: renameColumnDialog.title
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
                    id: renameField
                    Layout.fillWidth: true
                    color: textLight
                    background: Rectangle {
                        color: bgDark
                        border.color: renameField.activeFocus ? accentBlue : borderColor
                        radius: 3
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Unit:"; color: textLight; Layout.preferredWidth: 60 }
                TextField {
                    id: unitField
                    Layout.fillWidth: true
                    color: textLight
                    placeholderText: "optional"
                    background: Rectangle {
                        color: bgDark
                        border.color: unitField.activeFocus ? accentBlue : borderColor
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
                onClicked: renameColumnDialog.close()
                background: Rectangle { color: bgLight; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; horizontalAlignment: Text.AlignHCenter }
            }
            Button {
                text: "Apply"
                onClicked: {
                    if (tableModel) {
                        tableModel.setColumnMetadata(renameColumnDialog.targetColumn, renameField.text, unitField.text, "")
                        updateColumnNames()
                    }
                    renameColumnDialog.close()
                }
                background: Rectangle { color: accentBlue; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    // Add column dialog (for blank table bootstrapping)
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
                    if (tableModel) {
                        var name = newColumnName.text || indexToLetter(numCols)
                        tableModel.addColumn(name, "", "")
                        updateColumnNames()
                        newColumnName.text = ""
                    }
                    addColumnDialog.close()
                }
                background: Rectangle { color: accentBlue; radius: 4 }
                contentItem: Text { text: parent.text; color: textLight; horizontalAlignment: Text.AlignHCenter }
            }
        }
    }

    // Plot column picker dialog — assign each column as X or Y
    Dialog {
        id: plotDialog
        title: "Plot Columns"
        modal: true
        anchors.centerIn: parent
        width: 380
        height: 450

        property int plotXCol: -1
        property int plotYCount: 0

        function refreshCounts() {
            var xc = -1, yc = 0
            for (var i = 0; i < plotColumnsModel.count; i++) {
                var a = plotColumnsModel.get(i).assignment
                if (a === "x") xc = plotColumnsModel.get(i).colIndex
                else if (a === "y") yc++
            }
            plotXCol = xc
            plotYCount = yc
        }

        background: Rectangle {
            color: bgMedium
            border.color: borderColor
            radius: 8
        }

        header: Rectangle {
            color: bgDarker
            height: 40
            radius: 8
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 8; color: parent.color }
            Text {
                anchors.centerIn: parent
                text: "Plot Columns"
                color: accentPink
                font.pixelSize: 14
                font.bold: true
            }
        }

        contentItem: ColumnLayout {
            spacing: 8
            anchors.margins: 10

            Text {
                text: "Select one X axis and one or more Y axes"
                color: textMuted
                font.pixelSize: 10
                Layout.fillWidth: true
            }

            // Column header row
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                spacing: 4
                Text { Layout.fillWidth: true; text: "Column"; color: accentPink; font.pixelSize: 10; font.bold: true }
                Text { Layout.preferredWidth: 36; text: "X"; color: accentBlue; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.preferredWidth: 36; text: "Y"; color: accentPink; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignHCenter }
            }

            // Column list
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgDarker
                radius: 4
                clip: true

                ListView {
                    id: plotColumnList
                    anchors.fill: parent
                    anchors.margins: 4
                    model: plotColumnsModel
                    spacing: 1
                    clip: true

                    delegate: Rectangle {
                        width: plotColumnList.width
                        height: 26
                        color: model.assignment === "x" ? Qt.rgba(0.357, 0.808, 0.98, 0.1)
                             : model.assignment === "y" ? Qt.rgba(0.961, 0.663, 0.722, 0.1)
                             : "transparent"
                        radius: 3

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 4
                            anchors.rightMargin: 4
                            spacing: 4

                            Text {
                                Layout.fillWidth: true
                                text: model.name
                                color: textLight
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }

                            // X toggle (radio — only one allowed)
                            Rectangle {
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 20
                                radius: 3
                                color: model.assignment === "x" ? accentBlue : bgMedium
                                border.color: accentBlue
                                border.width: model.assignment === "x" ? 2 : 1

                                Text {
                                    anchors.centerIn: parent
                                    text: "X"
                                    // Not a fixed ink: which of the two reads on this fill depends
                                    // on the scheme (bgDark on accentSecondary is 2.42:1 on
                                    // Tropical Panchito and 12.06:1 on Attracted to Pans).
                                    color: model.assignment === "x" ? Theme.ink(accentBlue) : textMuted
                                    font.pixelSize: 10
                                    font.bold: model.assignment === "x"
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (model.assignment === "x") {
                                            plotColumnsModel.setProperty(index, "assignment", "none")
                                        } else {
                                            // Clear any previous X
                                            for (var i = 0; i < plotColumnsModel.count; i++) {
                                                if (plotColumnsModel.get(i).assignment === "x")
                                                    plotColumnsModel.setProperty(i, "assignment", "none")
                                            }
                                            plotColumnsModel.setProperty(index, "assignment", "x")
                                        }
                                        plotDialog.refreshCounts()
                                    }
                                }
                            }

                            // Y toggle (multi-select)
                            Rectangle {
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 20
                                radius: 3
                                color: model.assignment === "y" ? accentPink : bgMedium
                                border.color: accentPink
                                border.width: model.assignment === "y" ? 2 : 1

                                Text {
                                    anchors.centerIn: parent
                                    text: "Y"
                                    color: model.assignment === "y" ? Theme.ink(accentPink) : textMuted
                                    font.pixelSize: 10
                                    font.bold: model.assignment === "y"
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (model.assignment === "y")
                                            plotColumnsModel.setProperty(index, "assignment", "none")
                                        else
                                            plotColumnsModel.setProperty(index, "assignment", "y")
                                        plotDialog.refreshCounts()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Quick actions + status
            RowLayout {
                spacing: 8
                Button {
                    text: "All as Y"
                    onClicked: {
                        for (var i = 0; i < plotColumnsModel.count; i++) {
                            if (plotColumnsModel.get(i).assignment !== "x")
                                plotColumnsModel.setProperty(i, "assignment", "y")
                        }
                        plotDialog.refreshCounts()
                    }
                    background: Rectangle { color: bgLight; radius: 3; border.color: borderColor }
                    contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter }
                }
                Button {
                    text: "Clear"
                    onClicked: {
                        for (var i = 0; i < plotColumnsModel.count; i++)
                            plotColumnsModel.setProperty(i, "assignment", "none")
                        plotDialog.refreshCounts()
                    }
                    background: Rectangle { color: bgLight; radius: 3; border.color: borderColor }
                    contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: plotDialog.plotXCol >= 0
                          ? (plotDialog.plotYCount > 0 ? plotDialog.plotYCount + " curve(s) ready" : "Select Y column(s)")
                          : "Select an X column"
                    color: (plotDialog.plotXCol >= 0 && plotDialog.plotYCount > 0) ? accentBlue : accentMagenta
                    font.pixelSize: 10
                }
            }
        }

        footer: Rectangle {
            color: bgDarker
            height: 50
            radius: 8
            Rectangle { anchors.top: parent.top; width: parent.width; height: 8; color: parent.color }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: plotDialog.close()
                    background: Rectangle { color: bgLight; radius: 4 }
                    contentItem: Text { text: parent.text; color: textLight; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter }
                }
                Button {
                    enabled: plotDialog.plotXCol >= 0 && plotDialog.plotYCount > 0
                    text: "Plot"
                    onClicked: {
                        executePlot()
                        plotDialog.close()
                    }
                    background: Rectangle {
                        color: parent.enabled ? accentPurple : bgLight
                        radius: 4
                        opacity: parent.enabled ? 1.0 : 0.5
                    }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? textLight : textMuted
                        font.pixelSize: 12
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
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

    // Column names model for combo boxes
    ListModel {
        id: columnNamesModel
    }

    // Plot columns model for the plot dialog checkboxes
    ListModel {
        id: plotColumnsModel
    }

    // =========================================================================
    // Helper functions
    // =========================================================================

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

    function isColumnInSelection(col) {
        if (selectedColumn < 0) return false
        var c1 = Math.min(selectedColumn, selectionEndCol >= 0 ? selectionEndCol : selectedColumn)
        var c2 = Math.max(selectedColumn, selectionEndCol >= 0 ? selectionEndCol : selectedColumn)
        return col >= c1 && col <= c2
    }

    function isInSelection(row, col) {
        if (selectedRow < 0 || selectedColumn < 0) return false
        if (selectionEndRow < 0 || selectionEndCol < 0) return row === selectedRow && col === selectedColumn

        var r1 = Math.min(selectedRow, selectionEndRow)
        var r2 = Math.max(selectedRow, selectionEndRow)
        var c1 = Math.min(selectedColumn, selectionEndCol)
        var c2 = Math.max(selectedColumn, selectionEndCol)
        return row >= r1 && row <= r2 && col >= c1 && col <= c2
    }

    function selectCell(row, col) {
        selectedRow = row
        selectedColumn = col
        selectionEndRow = row
        selectionEndCol = col

        // Update formula bar
        if (tableModel) {
            var value = tableModel.data(tableModel.index(row, col), Qt.EditRole)
            formulaInput.text = value || ""
        }
    }

    function selectRow(row) {
        selectedRow = row
        selectedColumn = 0
        selectionEndRow = row
        selectionEndCol = numCols - 1
    }

    function selectColumn(col) {
        selectedRow = 0
        selectedColumn = col
        selectionEndRow = numRows - 1
        selectionEndCol = col

        // Show statistics
        showColumnStats(col)
    }

    function selectAll() {
        if (numRows > 0 && numCols > 0) {
            selectedRow = 0
            selectedColumn = 0
            selectionEndRow = numRows - 1
            selectionEndCol = numCols - 1
        }
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
            // Move down after applying
            moveSelection(1, 0)
        }
    }

    function moveSelection(dr, dc) {
        if (selectedRow < 0 || selectedColumn < 0) {
            selectCell(0, 0)
            return
        }

        var newRow = selectedRow + dr
        var newCol = selectedColumn + dc

        // Auto-add rows when moving past the last row
        if (newRow >= numRows && tableModel && dr > 0) {
            tableModel.addRow()
        }

        newRow = Math.max(0, Math.min(numRows - 1, newRow))
        newCol = Math.max(0, Math.min(numCols - 1, newCol))
        selectCell(newRow, newCol)

        // Auto-scroll to keep selection visible
        ensureVisible(newRow, newCol)
    }

    function ensureVisible(row, col) {
        var targetY = row * rowHeight
        var targetX = col * columnWidth

        if (targetY < dataFlickable.contentY)
            dataFlickable.contentY = targetY
        else if (targetY + rowHeight > dataFlickable.contentY + dataFlickable.height)
            dataFlickable.contentY = targetY + rowHeight - dataFlickable.height

        if (targetX < dataFlickable.contentX)
            dataFlickable.contentX = targetX
        else if (targetX + columnWidth > dataFlickable.contentX + dataFlickable.width)
            dataFlickable.contentX = targetX + columnWidth - dataFlickable.width
    }

    function extendSelection(dr, dc) {
        if (selectedRow < 0 || selectedColumn < 0) {
            selectCell(0, 0)
            return
        }
        var endR = (selectionEndRow >= 0 ? selectionEndRow : selectedRow) + dr
        var endC = (selectionEndCol >= 0 ? selectionEndCol : selectedColumn) + dc
        selectionEndRow = Math.max(0, Math.min(numRows - 1, endR))
        selectionEndCol = Math.max(0, Math.min(numCols - 1, endC))

        // Update formula bar to show the end-of-selection cell value
        if (tableModel) {
            var value = tableModel.data(tableModel.index(selectionEndRow, selectionEndCol), Qt.EditRole)
            formulaInput.text = value || ""
        }
    }

    function insertColumnAt(colIndex) {
        if (!tableModel) return
        var name = indexToLetter(numCols)
        tableModel.addColumn(name, "", "")
        updateColumnNames()
    }

    function openSetColumnValuesDialog(col) {
        if (col < 0 || !tableModel) return
        setValuesDialog.targetColumn = col
        targetColumnCombo.currentIndex = col
        columnFormulaField.text = ""
        updateColumnNames()
        setValuesDialog.open()
        columnFormulaField.forceActiveFocus()
    }

    function openRenameColumnDialog(col) {
        if (col < 0 || !tableModel) return
        renameColumnDialog.targetColumn = col
        var meta = tableModel.getColumnMetadata(col)
        renameField.text = meta.name || ""
        unitField.text = meta.unit || ""
        renameColumnDialog.open()
        renameField.forceActiveFocus()
    }

    function showColumnStats(col) {
        if (col < 0 || !tableModel) return
        var stats = tableModel.calculateColumnStatistics(col)
        if (stats && !stats.error) {
            statisticsDisplay.text = "Mean: " + stats.mean.toFixed(4) +
                                     " | Std: " + stats.std.toFixed(4) +
                                     " | Min: " + stats.min.toFixed(4) +
                                     " | Max: " + stats.max.toFixed(4)
        }
    }

    function getSelectionBounds() {
        var r1 = selectedRow, c1 = selectedColumn
        var r2 = selectionEndRow >= 0 ? selectionEndRow : r1
        var c2 = selectionEndCol >= 0 ? selectionEndCol : c1
        return {
            r1: Math.min(r1, r2), c1: Math.min(c1, c2),
            r2: Math.max(r1, r2), c2: Math.max(c1, c2)
        }
    }

    function doCopy() {
        if (!tableModel || selectedRow < 0) return
        var b = getSelectionBounds()
        tableModel.copyRange(b.r1, b.c1, b.r2, b.c2)
    }

    function doCopyWithHeaders() {
        if (!tableModel || selectedRow < 0) return
        var b = getSelectionBounds()
        tableModel.copyRangeWithHeaders(b.r1, b.c1, b.r2, b.c2)
    }

    function doCut() {
        if (!tableModel || selectedRow < 0) return
        doCopy()
        var b = getSelectionBounds()
        tableModel.clearRange(b.r1, b.c1, b.r2, b.c2)
    }

    function doPaste() {
        if (!tableModel || selectedRow < 0 || selectedColumn < 0) return
        tableModel.pasteFromClipboard(selectedRow, selectedColumn, "")
    }

    function doClearSelection() {
        if (!tableModel || selectedRow < 0) return
        var b = getSelectionBounds()
        tableModel.clearRange(b.r1, b.c1, b.r2, b.c2)
    }

    function updateColumnNames() {
        columnNamesModel.clear()
        if (tableModel) {
            var names = tableModel.getColumnNames()
            for (var i = 0; i < names.length; i++) {
                columnNamesModel.append({text: indexToLetter(i) + ": " + names[i]})
            }
        }
    }

    // Inline editing helpers
    function startInlineEdit(keepExisting) {
        if (selectedRow < 0 || selectedColumn < 0) return
        if (keepExisting && tableModel) {
            var val = tableModel.data(tableModel.index(selectedRow, selectedColumn), Qt.EditRole)
            inlineEditText = val || ""
        } else {
            inlineEditText = ""
        }
        inlineEditing = true
    }

    function commitInlineEdit() {
        if (!inlineEditing || selectedRow < 0 || selectedColumn < 0 || !tableModel) {
            inlineEditing = false
            return
        }
        var editorText = inlineCellEditor.text
        tableModel.setData(tableModel.index(selectedRow, selectedColumn), editorText, Qt.EditRole)
        inlineEditing = false
        root.forceActiveFocus()
        dataModified()
    }

    function cancelInlineEdit() {
        inlineEditing = false
        root.forceActiveFocus()
    }

    function doUndo() {
        if (tableModel && tableModel.canUndo()) {
            tableModel.undo()
        }
    }

    // =========================================================================
    // Plot functions
    // =========================================================================

    function populatePlotModel() {
        updateColumnNames()
        plotColumnsModel.clear()
        var names = tableModel.getColumnNames()
        for (var i = 0; i < names.length; i++) {
            plotColumnsModel.append({
                colIndex: i,
                name: indexToLetter(i) + ": " + names[i],
                assignment: "none"
            })
        }
    }

    function doPlotSelectedColumns() {
        if (!tableModel || numCols < 2) return

        populatePlotModel()

        // Smart pre-select: first column as X
        if (plotColumnsModel.count > 0)
            plotColumnsModel.setProperty(0, "assignment", "x")

        // If user has a column selection range, set those as Y (skip the X)
        if (selectedColumn >= 0 && selectionEndCol >= 0) {
            var c1 = Math.min(selectedColumn, selectionEndCol)
            var c2 = Math.max(selectedColumn, selectionEndCol)
            for (var j = c1; j <= c2 && j < plotColumnsModel.count; j++) {
                if (plotColumnsModel.get(j).assignment !== "x")
                    plotColumnsModel.setProperty(j, "assignment", "y")
            }
        } else if (plotColumnsModel.count > 1) {
            plotColumnsModel.setProperty(1, "assignment", "y")
        }

        plotDialog.refreshCounts()
        plotDialog.open()
    }

    function doPlotColumn(yCol) {
        // Open dialog with smart defaults — always prompt the user
        if (!tableModel || numCols < 2) return

        populatePlotModel()

        // First column as X (unless yCol is 0, then column 1)
        var xCol = (yCol === 0 && plotColumnsModel.count > 1) ? 1 : 0
        plotColumnsModel.setProperty(xCol, "assignment", "x")
        plotColumnsModel.setProperty(yCol, "assignment", "y")

        plotDialog.refreshCounts()
        plotDialog.open()
    }

    function executePlot() {
        if (!tableModel) return
        var xCol = -1
        var yCols = []
        for (var i = 0; i < plotColumnsModel.count; i++) {
            var item = plotColumnsModel.get(i)
            if (item.assignment === "x") xCol = item.colIndex
            else if (item.assignment === "y") yCols.push(item.colIndex)
        }
        if (xCol < 0 || yCols.length === 0) return

        var curves = buildCurvesFromColumns(xCol, yCols)
        if (curves.length > 0) {
            plotRequested(xCol, yCols)
            emitPlotToWindowManager(curves, xCol)
        }
    }

    function buildCurvesFromColumns(xCol, yCols) {
        var curves = []
        var xDataFull = tableModel.getColumnData(xCol)
        var xName = tableModel.getColumnNames()[xCol] || indexToLetter(xCol)

        // Downsample to at most ~500 points per curve for performance
        var maxPts = 500
        var step = Math.max(1, Math.floor(xDataFull.length / maxPts))
        var xData = downsample(xDataFull, step)

        for (var i = 0; i < yCols.length; i++) {
            var yCol = yCols[i]
            var yDataFull = tableModel.getColumnData(yCol)
            var yName = tableModel.getColumnNames()[yCol] || indexToLetter(yCol)
            if (xData.length > 0 && yDataFull.length > 0) {
                curves.push({
                    x: xData,
                    y: downsample(yDataFull, step),
                    label: yName
                })
            }
        }
        return curves
    }

    function downsample(arr, step) {
        if (step <= 1) return arr
        var out = []
        for (var i = 0; i < arr.length; i += step)
            out.push(arr[i])
        if (arr.length > 0 && (arr.length - 1) % step !== 0)
            out.push(arr[arr.length - 1])
        return out
    }

    function emitPlotToWindowManager(curves, xCol) {
        var xName = "X"
        if (tableModel && xCol >= 0) {
            var names = tableModel.getColumnNames()
            if (xCol < names.length) xName = names[xCol]
        }

        var appWin = ApplicationWindow.window
        if (appWin && appWin.getToolWindowManager) {
            appWin.getToolWindowManager().openGraphWindow(
                "Table Plot",
                curves,
                xName,
                "Y"
            )
        } else {
            console.warn("Could not find toolWindowManager for plotting")
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
        if (tableModel) return tableModel.getPlotData(xCol, yCol)
        return [[], []]
    }

    // =========================================================================
    // Keyboard shortcuts
    // =========================================================================
    Keys.onPressed: function(event) {
        // Ctrl shortcuts — always active (even during inline edit for copy/paste)
        if (event.modifiers & Qt.ControlModifier) {
            if (event.key === Qt.Key_C) {
                if (inlineEditing) {
                    // Let inline editor handle native copy
                    return
                }
                doCopy()
                event.accepted = true
                return
            } else if (event.key === Qt.Key_V) {
                if (inlineEditing) return  // native paste in editor
                doPaste()
                event.accepted = true
                return
            } else if (event.key === Qt.Key_X) {
                if (inlineEditing) return  // native cut in editor
                doCut()
                event.accepted = true
                return
            } else if (event.key === Qt.Key_A) {
                if (inlineEditing) return  // native select all in editor
                selectAll()
                event.accepted = true
                return
            } else if (event.key === Qt.Key_Z) {
                if (inlineEditing) return  // native undo in editor
                doUndo()
                event.accepted = true
                return
            }
        }

        // Navigation (when formula bar and inline editor not focused)
        if (!formulaInput.activeFocus && !inlineEditing) {
            var isShift = !!(event.modifiers & Qt.ShiftModifier)

            if (event.key === Qt.Key_Up) {
                if (isShift) extendSelection(-1, 0); else moveSelection(-1, 0)
                event.accepted = true
            } else if (event.key === Qt.Key_Down) {
                if (isShift) extendSelection(1, 0); else moveSelection(1, 0)
                event.accepted = true
            } else if (event.key === Qt.Key_Left) {
                if (isShift) extendSelection(0, -1); else moveSelection(0, -1)
                event.accepted = true
            } else if (event.key === Qt.Key_Right) {
                if (isShift) extendSelection(0, 1); else moveSelection(0, 1)
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (selectedRow >= 0 && selectedColumn >= 0) {
                    editCell(selectedRow, selectedColumn)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Delete) {
                // Clear entire selection
                doClearSelection()
                event.accepted = true
            } else if (event.key === Qt.Key_Backspace) {
                if (selectedRow >= 0 && selectedColumn >= 0) {
                    startInlineEdit(false)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_F2) {
                if (selectedRow >= 0 && selectedColumn >= 0) {
                    startInlineEdit(true)
                }
                event.accepted = true
            } else if (event.key === Qt.Key_Tab) {
                moveSelection(0, 1)
                event.accepted = true
            } else if (event.key === Qt.Key_Escape) {
                selectedRow = -1
                selectedColumn = -1
                selectionEndRow = -1
                selectionEndCol = -1
                event.accepted = true
            } else if (selectedRow >= 0 && selectedColumn >= 0 &&
                       event.text && event.text.length === 1 &&
                       !event.modifiers) {
                // Printable character: start inline editing (replace mode)
                inlineEditText = event.text
                inlineEditing = true
                event.accepted = true
            }
        }
    }

    // =========================================================================
    // Initialization
    // =========================================================================
    Component.onCompleted: {
        console.log("TableWindowContent created")
        updateColumnNames()
    }

    onTableModelChanged: {
        console.log("TableWindowContent: model changed, rows=" + (tableModel ? tableModel.rows : 0) +
                     " cols=" + (tableModel ? tableModel.columns : 0))
        updateColumnNames()
    }
}
