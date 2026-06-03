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
import "../dialogs"

Rectangle {
    id: browserRoot
    color: bgDark
    border.color: borderColor
    border.width: 1
    radius: 6

    // -- Unified-tree state -------------------------------------------------
    // The browser is one flattened folder tree (Phase D2). ``treeModel``
    // (declared below) is the ordered list of visible rows the ListView
    // renders; it is rebuilt from backend.getBrowserTree() + the item lists in
    // rebuildRows(). A ListModel (not a plain JS array) is used so the view
    // reliably re-renders when folders expand/collapse.

    // Per-folder expand/collapse state, keyed by folder id. A folder not
    // present here defaults to expanded.
    property var expandedFolders: ({})

    // Transient embedded windows (tables/graphs) live only in the UI; they
    // are not persisted backend entities, so they're tracked here and merged
    // into the tree as best-effort items keyed by windowId.
    property var transientWindows: []

    // Selection tracking. ``selectedRef`` is the "<type>:<id>" of the chosen
    // item; ``selectedDataset`` mirrors the dataset name for the few
    // dataset-specific code paths (delete/rename selection bookkeeping).
    property string selectedRef: ""
    property string selectedDataset: ""

    // Ref ("<type>:<id>") of the row currently being dragged. Set when a drag
    // starts; the release hit-test reads it to file the item.
    property string draggingRef: ""

    // Folder id ("" = root) that a drop at the current drag position would land
    // in. Recomputed as the drag moves (Finder-style: the folder whose region —
    // its row OR any of its listed contents — is under the cursor) and used to
    // highlight that folder row live.
    property string dropTargetFolder: ""

    // True once a drag has been handled (a move was requested, which rebuilds
    // the tree and repositions every row). If a drag ends WITHOUT being handled
    // (released outside the list viewport), nothing rebuilds and the dragged
    // row is left displaced — so we snap it back.
    property bool dropHandled: false

    // Row geometry shared by the delegate height and the drop hit-test so the
    // two can't drift. A row occupies rowHeight plus the ListView spacing.
    readonly property int rowHeight: 28

    // Sort state (Phase C). "name" or "type"; applied to items when the tree
    // is flattened. Folders are always ordered by name for stability.
    property string sortKey: "name"
    property bool sortAsc: true

    // Comparator over item rows ({name, type}). When sorting by type, ties
    // fall back to name so the order is stable.
    function itemComparator(a, b) {
        var av, bv
        if (browserRoot.sortKey === "type") {
            av = (a.type || "").toLowerCase()
            bv = (b.type || "").toLowerCase()
            if (av !== bv)
                return browserRoot.sortAsc ? (av < bv ? -1 : 1) : (av < bv ? 1 : -1)
        }
        av = (a.name || a.title || "").toLowerCase()
        bv = (b.name || b.title || "").toLowerCase()
        if (av < bv) return browserRoot.sortAsc ? -1 : 1
        if (av > bv) return browserRoot.sortAsc ? 1 : -1
        return 0
    }

    // Change sort key (toggle direction if the same key) and re-flatten.
    function setSort(key) {
        if (browserRoot.sortKey === key)
            browserRoot.sortAsc = !browserRoot.sortAsc
        else {
            browserRoot.sortKey = key
            browserRoot.sortAsc = true
        }
        browserRoot.rebuildRows()
    }

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#2d2d3e"
    property color textLight: mainWin ? mainWin.textLight : "#e0e0e0"
    property color textMuted: mainWin ? mainWin.textMuted : "#B0A0B8"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color borderColor: mainWin ? mainWin.borderColor : "#7B3F76"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            color: bgLight
            radius: 4

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8

                Text {
                    text: "Project Browser"
                    font.pixelSize: 14
                    font.bold: true
                    color: textLight
                    Layout.fillWidth: true
                }

                // New folder (at the root)
                Button {
                    id: newFolderBtn
                    text: "🗀＋"
                    font.pixelSize: 14
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: {
                        newFolderDialog.parentId = ""
                        newFolderDialog.open()
                    }

                    background: Rectangle {
                        color: newFolderBtn.pressed ? accentPink : (newFolderBtn.hovered ? bgDark : "transparent")
                        radius: 4
                        opacity: newFolderBtn.pressed ? 0.3 : (newFolderBtn.hovered ? 0.5 : 1)
                    }

                    contentItem: Text {
                        text: newFolderBtn.text
                        font: newFolderBtn.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    ToolTip {
                        visible: newFolderBtn.hovered
                        text: "New folder"
                        delay: 500
                    }
                }

                // Refresh button
                Button {
                    id: refreshBtn
                    text: "↻"
                    font.pixelSize: 16
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: browserRoot.refreshBrowser()

                    background: Rectangle {
                        color: refreshBtn.pressed ? accentPink : (refreshBtn.hovered ? bgDark : "transparent")
                        radius: 4
                        opacity: refreshBtn.pressed ? 0.3 : (refreshBtn.hovered ? 0.5 : 1)
                    }

                    contentItem: Text {
                        text: refreshBtn.text
                        font: refreshBtn.font
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // Search box
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: bgLight
            border.color: borderColor
            border.width: 1
            radius: 4

            TextField {
                id: searchField
                anchors.fill: parent
                anchors.margins: 4
                placeholderText: "Search items..."
                color: textLight
                placeholderTextColor: textMuted
                background: Rectangle { color: "transparent" }
                selectByMouse: true

                onTextChanged: browserRoot.rebuildRows()
            }
        }

        // Unified tree. The container hosts (bottom→top): a right-click
        // MouseArea for the background context menu and the ListView of
        // folders + items. There is deliberately no root DropArea — a drag
        // released anywhere that is not a folder is a no-op and the row snaps
        // back to where it started (forceLayout in the row's drag handler).
        // To take an item OUT of a folder, use right-click → "Remove from
        // Folder".
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // Right-click on empty background → new folder / sort.
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.RightButton
                onClicked: backgroundMenu.popup()
            }

            ListView {
                id: treeView
                anchors.fill: parent
                clip: true
                model: treeModel
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    id: rowItem
                    readonly property bool isFolder: model.isFolder
                    readonly property string itemRef: model.ref || ""
                    // True while this row's press turned into a drag (vs a click),
                    // so onReleased only files on an actual drag.
                    property bool didDrag: false

                    // Reconstruct the row dict for selection / open / menus.
                    function rowData() {
                        return {
                            kind: model.kind, type: model.type, id: model.id,
                            name: model.name, ref: model.ref, path: model.path,
                            displayType: model.displayType, preview: model.preview,
                            folderId: model.folderId
                        }
                    }

                    width: treeView.width
                    height: browserRoot.rowHeight
                    radius: 3
                    color: {
                        if (rowItem.isFolder) {
                            // Highlight the folder a drop would currently land in.
                            if (browserRoot.draggingRef !== ""
                                    && browserRoot.dropTargetFolder === model.folderId)
                                return Qt.rgba(accentBlue.r, accentBlue.g, accentBlue.b, 0.30)
                            if (rowMouseArea.containsMouse)
                                return bgLight
                            return "transparent"
                        }
                        if (rowItem.itemRef === browserRoot.selectedRef)
                            return Qt.rgba(1, 0.7, 0.85, 0.3)   // selected
                        if (rowMouseArea.containsMouse)
                            return Qt.rgba(1, 0.7, 0.85, 0.2)   // hover
                        return "transparent"
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8 + (model.depth || 0) * 16
                        anchors.rightMargin: 8
                        spacing: 6

                        // Folder expand/collapse chevron (blank for items).
                        Text {
                            text: rowItem.isFolder ? (model.expanded ? "▼" : "▶") : ""
                            font.pixelSize: 10
                            color: textMuted
                            Layout.preferredWidth: 10
                            visible: rowItem.isFolder
                        }

                        // Per-type placeholder glyph ([DS]/[MAP]/[DIR]/…).
                        Text {
                            text: (model.icon && model.icon.length)
                                  ? model.icon
                                  : browserRoot.getDefaultIcon(rowItem.isFolder ? "folder" : model.type)
                            font.pixelSize: 12
                            font.bold: rowItem.isFolder
                            color: "#e0e0e0"
                            renderType: Text.NativeRendering
                        }

                        // Item name. Elides with "…" when too long; on hover,
                        // if it actually overflows, it scrolls (marquee) so the
                        // full name is readable without resizing the panel.
                        Item {
                            id: nameClip
                            Layout.fillWidth: true
                            Layout.preferredHeight: nameText.implicitHeight
                            clip: true

                            readonly property bool overflowing: nameText.implicitWidth > width
                            readonly property bool scrolling: rowMouseArea.containsMouse && overflowing

                            Text {
                                id: nameText
                                text: model.name || ""
                                font.pixelSize: 12
                                font.bold: rowItem.isFolder
                                color: "#e0e0e0"
                                renderType: Text.NativeRendering
                                width: nameClip.scrolling ? implicitWidth : nameClip.width
                                elide: nameClip.scrolling ? Text.ElideNone : Text.ElideRight

                                SequentialAnimation on x {
                                    running: nameClip.scrolling
                                    loops: Animation.Infinite
                                    onRunningChanged: if (!running) nameText.x = 0
                                    PauseAnimation { duration: 600 }
                                    NumberAnimation {
                                        to: Math.min(0, nameClip.width - nameText.implicitWidth)
                                        duration: Math.max(800, (nameText.implicitWidth - nameClip.width) * 25)
                                    }
                                    PauseAnimation { duration: 600 }
                                    NumberAnimation { to: 0; duration: 300 }
                                }
                            }
                        }

                        // Secondary type label for items.
                        Text {
                            text: rowItem.isFolder ? "" : (model.displayType || "")
                            font.pixelSize: 10
                            color: "#999999"
                            renderType: Text.NativeRendering
                            visible: !rowItem.isFolder
                        }
                    }

                    // Drag/drop is handled WITHOUT DropAreas: the row follows the
                    // cursor via MouseArea.drag.target, and on release we hit-test
                    // the drop position against the flattened tree
                    // (browserRoot.folderAtContentY). This gives Finder-style
                    // region drops — drop anywhere within a folder's listed
                    // contents (not just its row), and the empty/root area is a
                    // valid target so items can leave folders. Items only;
                    // folders are drop targets, not draggable.
                    MouseArea {
                        id: rowMouseArea
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        drag.target: rowItem.isFolder ? undefined : rowItem
                        drag.threshold: 10

                        onPressed: rowItem.didDrag = false

                        drag.onActiveChanged: {
                            if (rowMouseArea.drag.active) {
                                rowItem.didDrag = true
                                browserRoot.draggingRef = rowItem.itemRef
                                browserRoot.dropHandled = false
                                browserRoot.dropTargetFolder = ""
                            } else if (!browserRoot.dropHandled) {
                                // Released outside the list → nothing moved and the
                                // tree wasn't rebuilt; snap the displaced row back.
                                snapBackTimer.restart()
                                browserRoot.dropTargetFolder = ""
                            }
                        }

                        // Live-highlight the folder a drop would land in as the
                        // row is dragged over the tree.
                        onPositionChanged: function(mouse) {
                            if (rowMouseArea.drag.active) {
                                var cp = rowItem.mapToItem(treeView.contentItem, mouse.x, mouse.y)
                                browserRoot.dropTargetFolder = browserRoot.folderAtContentY(cp.y)
                            }
                        }

                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton) {
                                if (rowItem.isFolder) {
                                    folderMenu.folderId = model.folderId
                                    folderMenu.folderName = model.name
                                    folderMenu.popup()
                                } else {
                                    itemMenu.row = rowItem.rowData()
                                    itemMenu.popup()
                                }
                            } else if (rowItem.isFolder) {
                                browserRoot.toggleFolder(model.folderId)
                            } else {
                                browserRoot.selectItem(rowItem.rowData())
                            }
                        }

                        onDoubleClicked: {
                            if (rowItem.isFolder)
                                browserRoot.toggleFolder(model.folderId)
                            else
                                browserRoot.openItemRow(rowItem.rowData())
                        }

                        // On release of an actual drag, file the item into the
                        // folder under the cursor (or root). Releases outside the
                        // list viewport are ignored → drag.onActiveChanged snaps
                        // the row back.
                        onReleased: function(mouse) {
                            if (!rowItem.didDrag || rowItem.isFolder)
                                return
                            rowItem.didDrag = false
                            var vp = rowItem.mapToItem(treeView, mouse.x, mouse.y)
                            var inView = vp.x >= 0 && vp.x <= treeView.width
                                         && vp.y >= 0 && vp.y <= treeView.height
                            if (inView && browserRoot.draggingRef) {
                                var cp = rowItem.mapToItem(treeView.contentItem, mouse.x, mouse.y)
                                var target = browserRoot.folderAtContentY(cp.y)
                                browserRoot.dropHandled = true
                                browserRoot.requestMove(browserRoot.draggingRef, target)
                            }
                            browserRoot.dropTargetFolder = ""
                        }
                    }
                }
            }
        }

        // Metadata panel
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            color: bgLight
            border.color: borderColor
            border.width: 1
            radius: 4

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                Text {
                    text: "Metadata"
                    font.pixelSize: 12
                    font.bold: true
                    color: textLight
                }

                Text {
                    id: metadataText
                    text: "No item selected"
                    font.pixelSize: 11
                    color: textMuted
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        // Naming Convention Button
        Button {
            id: namingConventionBtn
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            text: "Choose Dataset Names"

            background: Rectangle {
                color: namingConventionBtn.pressed ? accentPink : (namingConventionBtn.hovered ? bgLight : bgMedium)
                border.color: namingConventionBtn.hovered ? accentBlue : borderColor
                border.width: 1
                radius: 4
            }

            contentItem: Text {
                text: namingConventionBtn.text
                font.pixelSize: 12
                color: textLight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            onClicked: namingConventionDialog.open()

            ToolTip {
                visible: namingConventionBtn.hovered
                text: "Configure naming pattern for output datasets"
                delay: 500
            }
        }
    }

    // Naming Convention Dialog
    NamingConventionDialog {
        id: namingConventionDialog
        anchors.centerIn: parent
    }

    // Flattened, ordered list of visible rows (folders + items) rendered by the
    // ListView. Rebuilt wholesale by rebuildRows(); using a ListModel (rather
    // than a plain JS array) guarantees the view re-renders on expand/collapse.
    ListModel {
        id: treeModel
    }

    // Deferred item move. A drop handler must NOT call backend.moveItem
    // directly: that rebuilds the tree synchronously and destroys the very
    // delegate whose MouseArea is still finishing the drop, corrupting the
    // drag grab (symptom: only the first drag-drop ever worked). Instead the
    // drop stashes the move here and fires this Timer, which runs on the next
    // event-loop tick — after the release fully unwinds. The Timer lives on
    // browserRoot (not the delegate), so it survives the rebuild and ``backend``
    // resolves cleanly.
    property string pendingMoveRef: ""
    property string pendingMoveFolder: ""
    Timer {
        id: moveTimer
        interval: 0
        repeat: false
        onTriggered: {
            if (backend && browserRoot.pendingMoveRef)
                backend.moveItem(browserRoot.pendingMoveRef, browserRoot.pendingMoveFolder)
            browserRoot.pendingMoveRef = ""
            browserRoot.pendingMoveFolder = ""
        }
    }

    // Queue a deferred move (see moveTimer above).
    function requestMove(ref, folderId) {
        if (!ref) return
        browserRoot.pendingMoveRef = ref
        browserRoot.pendingMoveFolder = folderId || ""
        moveTimer.restart()
    }

    // Finder-style drop hit-test: given a Y in treeView CONTENT coordinates,
    // return the folder id ("" = root) a drop there should file into. Every row
    // carries the id of the folder it belongs to (a folder row carries its own
    // id, an item row carries its container), so the rule is simply "the folder
    // owning the row under the cursor". Above the first row or below the last
    // (the empty area) resolves to root, which is how items leave folders.
    function folderAtContentY(contentY) {
        if (contentY < 0)
            return ""
        var stride = browserRoot.rowHeight + treeView.spacing
        var idx = Math.floor(contentY / stride)
        if (idx < 0 || idx >= treeModel.count)
            return ""
        var row = treeModel.get(idx)
        return row ? (row.folderId || "") : ""
    }

    // Snap a displaced row back when a drag ended without a folder drop.
    // rebuildRows() recreates every delegate at its correct position, so the
    // dragged row returns home. Deferred (next tick) for the same reason as
    // moveTimer: rebuilding mid-release would destroy the dragging delegate.
    Timer {
        id: snapBackTimer
        interval: 0
        repeat: false
        onTriggered: browserRoot.rebuildRows()
    }

    // -- Context menus ------------------------------------------------------

    // Per-item actions. Keyed on the item's ``type`` (dataset/map/image/note/
    // output/table/graph) — the old per-category switch rekeyed for the tree.
    Menu {
        id: itemMenu
        property var row: null

        MenuItem {
            text: "Open"
            onTriggered: {
                if (!backend || !itemMenu.row) return
                var r = itemMenu.row
                switch (r.type) {
                    case "dataset": backend.setActiveDataset(r.id); break
                    case "map": backend.openMap(r.id); break
                    case "image": backend.openImage(r.id); break
                    case "note": backend.openNote(r.id); break
                    case "output": backend.openItem(r.path || r.name); break
                    default: break  // tables/graphs are live embedded windows
                }
            }
        }

        // Take the item out of its folder (back to the unfiled root). Only
        // shown when the item is actually inside a folder. This replaces the
        // old "drop on empty space to unfile" behaviour — off-folder drops now
        // snap back instead.
        MenuItem {
            text: "Remove from Folder"
            visible: itemMenu.row && itemMenu.row.folderId
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row && itemMenu.row.ref)
                    backend.moveItem(itemMenu.row.ref, "")
            }
        }

        MenuItem {
            text: "Convert to Image (raw)"
            visible: itemMenu.row && itemMenu.row.type === "map"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row && itemMenu.row.id)
                    backend.convertMapChannelToImage(itemMenu.row.id, "")
            }
        }

        MenuItem {
            text: "Convert to Map (TIFF)"
            visible: itemMenu.row && itemMenu.row.type === "image"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row && itemMenu.row.id)
                    backend.convertImageToMap(itemMenu.row.id)
            }
        }

        MenuItem {
            text: "Open in OS viewer…"
            visible: itemMenu.row && itemMenu.row.type === "image"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row && itemMenu.row.id)
                    backend.openImageInOS(itemMenu.row.id)
            }
        }

        MenuItem {
            text: "Open in OS editor…"
            visible: itemMenu.row && itemMenu.row.type === "note"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row && itemMenu.row.id)
                    backend.openNoteInOS(itemMenu.row.id)
            }
        }

        MenuItem {
            text: "Rename..."
            visible: itemMenu.row && itemMenu.row.type !== "output"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (!itemMenu.row) return
                renameDialog.itemType = itemMenu.row.type
                renameDialog.itemName = itemMenu.row.name
                renameDialog.itemId = itemMenu.row.id || ""
                renameDialog.newNameField.text = itemMenu.row.name
                renameDialog.open()
            }
        }

        MenuSeparator { }

        MenuItem {
            text: "Delete"
            visible: itemMenu.row && itemMenu.row.type !== "output"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (!itemMenu.row) return
                deleteConfirmDialog.itemType = itemMenu.row.type
                deleteConfirmDialog.itemName = itemMenu.row.name
                deleteConfirmDialog.itemId = itemMenu.row.id || ""
                deleteConfirmDialog.open()
            }
        }

        MenuItem {
            text: "Properties..."
            visible: itemMenu.row && itemMenu.row.type === "dataset"
            height: visible ? implicitHeight : 0
            onTriggered: {
                if (backend && itemMenu.row) {
                    var info = backend.getDatasetInfo(itemMenu.row.id)
                    if (info && info.type)
                        console.log("Dataset Info:", JSON.stringify(info, null, 2))
                }
            }
        }
    }

    // Folder actions.
    Menu {
        id: folderMenu
        property string folderId: ""
        property string folderName: ""

        MenuItem {
            text: "New Subfolder..."
            onTriggered: {
                newFolderDialog.parentId = folderMenu.folderId
                newFolderDialog.open()
            }
        }
        MenuItem {
            text: "Rename Folder..."
            onTriggered: {
                renameDialog.itemType = "folder"
                renameDialog.itemName = folderMenu.folderName
                renameDialog.itemId = folderMenu.folderId
                renameDialog.newNameField.text = folderMenu.folderName
                renameDialog.open()
            }
        }
        MenuItem {
            text: "Delete Folder"
            onTriggered: {
                deleteConfirmDialog.itemType = "folder"
                deleteConfirmDialog.itemName = folderMenu.folderName
                deleteConfirmDialog.itemId = folderMenu.folderId
                deleteConfirmDialog.open()
            }
        }
        MenuSeparator { }
        MenuItem {
            text: "Sort by Name" +
                  (browserRoot.sortKey === "name" ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
            onTriggered: browserRoot.setSort("name")
        }
        MenuItem {
            text: "Sort by Type" +
                  (browserRoot.sortKey === "type" ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
            onTriggered: browserRoot.setSort("type")
        }
    }

    // Background (empty space) actions.
    Menu {
        id: backgroundMenu
        MenuItem {
            text: "New Folder..."
            onTriggered: {
                newFolderDialog.parentId = ""
                newFolderDialog.open()
            }
        }
        MenuSeparator { }
        MenuItem {
            text: "Sort by Name" +
                  (browserRoot.sortKey === "name" ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
            onTriggered: browserRoot.setSort("name")
        }
        MenuItem {
            text: "Sort by Type" +
                  (browserRoot.sortKey === "type" ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
            onTriggered: browserRoot.setSort("type")
        }
    }

    // -- Dialogs ------------------------------------------------------------

    // New folder dialog (root or subfolder, set via parentId).
    Dialog {
        id: newFolderDialog
        property string parentId: ""
        property alias nameField: newFolderInput

        title: "New Folder"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 350

        onOpened: {
            newFolderInput.text = ""
            newFolderInput.forceActiveFocus()
        }

        contentItem: ColumnLayout {
            spacing: 10

            Text {
                text: "Folder name:"
                color: textLight
                font.pixelSize: 12
            }

            TextField {
                id: newFolderInput
                Layout.fillWidth: true
                Layout.preferredWidth: 250
                color: textLight
                placeholderText: "Enter folder name"
                placeholderTextColor: textMuted
                selectByMouse: true

                background: Rectangle {
                    color: bgLight
                    border.color: newFolderInput.activeFocus ? accentBlue : borderColor
                    radius: 4
                }

                onAccepted: newFolderDialog.accept()
            }
        }

        background: Rectangle {
            color: bgDark
            border.color: borderColor
            radius: 6
        }

        onAccepted: {
            var name = newFolderInput.text.trim()
            if (name && backend) {
                // Make sure the parent is expanded so the new folder is visible.
                if (newFolderDialog.parentId) {
                    var m = browserRoot.expandedFolders
                    m[newFolderDialog.parentId] = true
                    browserRoot.expandedFolders = m
                }
                backend.createFolder(name, newFolderDialog.parentId)
                // browserTreeChanged → rebuildRows()
            }
        }
    }

    // Delete confirmation dialog (items and folders).
    Dialog {
        id: deleteConfirmDialog
        property string itemType: ""
        property string itemName: ""
        property string itemId: ""

        title: "Delete " + (deleteConfirmDialog.itemType === "folder" ? "Folder" : deleteConfirmDialog.itemType)
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        width: 320

        contentItem: ColumnLayout {
            spacing: 10

            Text {
                text: "Are you sure you want to delete:"
                color: textLight
                font.pixelSize: 12
            }

            Text {
                text: deleteConfirmDialog.itemName
                color: accentPink
                font.pixelSize: 14
                font.bold: true
            }

            Text {
                text: deleteConfirmDialog.itemType === "folder"
                      ? "Items inside will move to the parent folder."
                      : "This action cannot be undone."
                color: textMuted
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        background: Rectangle {
            color: bgDark
            border.color: borderColor
            radius: 6
        }

        onAccepted: {
            if (!backend) return
            switch (deleteConfirmDialog.itemType) {
                case "dataset":
                    if (backend.deleteDataset(deleteConfirmDialog.itemName) &&
                        browserRoot.selectedDataset === deleteConfirmDialog.itemName) {
                        browserRoot.selectedDataset = ""
                        browserRoot.selectedRef = ""
                        metadataText.text = "No item selected"
                    }
                    break
                case "map": backend.deleteMap(deleteConfirmDialog.itemId); break
                case "table": backend.deleteTable(deleteConfirmDialog.itemId); break
                case "graph": backend.deleteGraph(deleteConfirmDialog.itemId); break
                case "image": backend.deleteImage(deleteConfirmDialog.itemId); break
                case "note": backend.deleteNote(deleteConfirmDialog.itemId); break
                case "folder": backend.deleteFolder(deleteConfirmDialog.itemId); break
            }
            browserRoot.rebuildRows()
        }
    }

    // Rename dialog (items and folders).
    Dialog {
        id: renameDialog
        property string itemType: ""
        property string itemName: ""
        property string itemId: ""
        property alias newNameField: newNameInput

        title: "Rename " + (renameDialog.itemType === "folder" ? "Folder" : renameDialog.itemType)
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 350

        contentItem: ColumnLayout {
            spacing: 10

            Text {
                text: "Current name:"
                color: textLight
                font.pixelSize: 12
            }

            Text {
                text: renameDialog.itemName
                color: textMuted
                font.pixelSize: 11
            }

            Text {
                text: "New name:"
                color: textLight
                font.pixelSize: 12
            }

            TextField {
                id: newNameInput
                Layout.fillWidth: true
                Layout.preferredWidth: 250
                color: textLight
                placeholderText: "Enter new name"
                placeholderTextColor: textMuted
                selectByMouse: true

                background: Rectangle {
                    color: bgLight
                    border.color: newNameInput.activeFocus ? accentBlue : borderColor
                    radius: 4
                }

                onAccepted: renameDialog.accept()
            }
        }

        background: Rectangle {
            color: bgDark
            border.color: borderColor
            radius: 6
        }

        onAccepted: {
            if (!backend) return
            var newName = newNameInput.text.trim()
            if (!newName || newName === renameDialog.itemName) return
            var ok = false
            switch (renameDialog.itemType) {
                case "dataset":
                    ok = backend.renameDataset(renameDialog.itemName, newName)
                    if (ok && browserRoot.selectedDataset === renameDialog.itemName) {
                        browserRoot.selectedDataset = newName
                        browserRoot.selectedRef = "dataset:" + newName
                    }
                    break
                case "map": ok = backend.renameMap(renameDialog.itemId, newName); break
                case "table": ok = backend.renameTable(renameDialog.itemId, newName); break
                case "graph": ok = backend.renameGraph(renameDialog.itemId, newName); break
                case "image": backend.renameImage(renameDialog.itemId, newName); ok = true; break
                case "note": backend.renameNote(renameDialog.itemId, newName); ok = true; break
                case "folder": ok = backend.renameFolder(renameDialog.itemId, newName); break
            }
            if (ok) {
                browserRoot.rebuildRows()
                browserRoot.updateMetadata()
            }
        }
    }

    // -- Tree building & helpers -------------------------------------------

    // Public refresh entry point (refresh button, Connections, onCompleted).
    function refreshBrowser() {
        browserRoot.rebuildRows()
    }

    function isExpanded(folderId) {
        var e = browserRoot.expandedFolders[folderId]
        return e === undefined ? true : e
    }

    function toggleFolder(folderId) {
        var m = browserRoot.expandedFolders
        m[folderId] = !browserRoot.isExpanded(folderId)
        browserRoot.expandedFolders = m  // reassign so the change is observed
        browserRoot.rebuildRows()
    }

    // Collect every browser item (across all types) into a flat array of row
    // dicts with a stable ``ref`` ("<type>:<id>") used for placement & drag.
    function gatherItems() {
        var items = []
        if (!backend) return items
        var i

        var datasets = backend.getDatasetList()
        for (i = 0; i < datasets.length; i++) {
            var info = backend.getDatasetInfo(datasets[i]) || {}
            items.push({
                kind: "item", type: "dataset", id: datasets[i],
                ref: "dataset:" + datasets[i], name: datasets[i],
                displayType: info.type || "Dataset",
                dimensions: info.dimensions || [],
                numSpectra: info.num_spectra || 0,
                numPoints: info.num_points || 0,
                independentVar: info.independent_var || ""
            })
        }

        var maps = backend.getMapList()
        for (i = 0; i < maps.length; i++) {
            items.push({
                kind: "item", type: "map", id: maps[i].id,
                ref: "map:" + maps[i].id, name: maps[i].title,
                displayType: "Map", path: maps[i].path || ""
            })
        }

        var images = backend.getImageList ? backend.getImageList() : []
        for (i = 0; i < images.length; i++) {
            items.push({
                kind: "item", type: "image", id: images[i].id,
                ref: "image:" + images[i].id, name: images[i].name,
                displayType: images[i].mode || "Image"
            })
        }

        var notes = backend.getNotesList ? backend.getNotesList() : []
        for (i = 0; i < notes.length; i++) {
            items.push({
                kind: "item", type: "note", id: notes[i].id,
                ref: "note:" + notes[i].id, name: notes[i].name,
                displayType: notes[i].source || "Note",
                preview: notes[i].preview || ""
            })
        }

        var outputs = backend.getOutputList ? backend.getOutputList() : []
        for (i = 0; i < outputs.length; i++) {
            items.push({
                kind: "item", type: "output", id: outputs[i].id,
                ref: "output:" + outputs[i].id, name: outputs[i].filename,
                displayType: outputs[i].tool || "Output",
                path: outputs[i].path || ""
            })
        }

        // Transient embedded windows (tables/graphs) — best-effort items.
        for (i = 0; i < browserRoot.transientWindows.length; i++) {
            var w = browserRoot.transientWindows[i]
            items.push({
                kind: "item", type: w.type, id: w.id,
                ref: w.type + ":" + w.id, name: w.name,
                displayType: w.type === "table" ? "Table" : "Graph",
                transient: true
            })
        }

        return items
    }

    // Append one row to treeModel with a fixed schema so every row exposes the
    // same roles (consistent roles regardless of folder/item order).
    function appendRow(r) {
        treeModel.append({
            kind: r.kind || "",
            isFolder: r.kind === "folder",
            depth: r.depth || 0,
            expanded: r.expanded === undefined ? true : r.expanded,
            ref: r.ref || "",
            folderId: r.folderId || "",
            type: r.type || "",
            displayType: r.displayType || "",
            name: r.name || "",
            id: r.id || "",
            path: r.path || "",
            preview: r.preview || "",
            icon: r.icon || ""
        })
    }

    // Flatten getBrowserTree() + items into ``treeModel``, the ordered list the
    // ListView renders. Honors per-folder expand state and the current sort.
    function rebuildRows() {
        treeModel.clear()
        if (!backend)
            return

        var items = browserRoot.gatherItems()

        // Search short-circuits the tree: show a flat list of matching items.
        var search = searchField.text.toLowerCase()
        if (search) {
            var matches = items.filter(function(it) {
                return (it.name || "").toLowerCase().indexOf(search) !== -1
            })
            matches.sort(browserRoot.itemComparator)
            for (var k = 0; k < matches.length; k++) {
                matches[k].depth = 0
                browserRoot.appendRow(matches[k])
            }
            return
        }

        var tree = backend.getBrowserTree() || { folders: [], placements: {} }
        var folders = tree.folders || []
        var placements = tree.placements || {}

        var folderById = {}
        var foldersByParent = {}
        var f
        for (f = 0; f < folders.length; f++) {
            folderById[folders[f].id] = folders[f]
            var par = folders[f].parent || ""
            if (!foldersByParent[par]) foldersByParent[par] = []
            foldersByParent[par].push(folders[f])
        }
        // Folders are always ordered by name for a stable layout.
        var parentKey
        for (parentKey in foldersByParent) {
            foldersByParent[parentKey].sort(function(a, b) {
                var an = (a.name || "").toLowerCase()
                var bn = (b.name || "").toLowerCase()
                return an < bn ? -1 : (an > bn ? 1 : 0)
            })
        }

        // Bucket items by their folder ("" = root); missing/stale → root.
        var itemsByFolder = {}
        var j
        for (j = 0; j < items.length; j++) {
            var fid = placements[items[j].ref]
            if (!fid || !folderById[fid]) fid = ""
            if (!itemsByFolder[fid]) itemsByFolder[fid] = []
            itemsByFolder[fid].push(items[j])
        }
        var bucketKey
        for (bucketKey in itemsByFolder)
            itemsByFolder[bucketKey].sort(browserRoot.itemComparator)

        // Depth-first walk: subfolders first, then items, per folder. A
        // collapsed folder contributes its own row but none of its descendants.
        function walk(parentId, depth) {
            var subs = foldersByParent[parentId] || []
            var s
            for (s = 0; s < subs.length; s++) {
                var fol = subs[s]
                var exp = browserRoot.isExpanded(fol.id)
                browserRoot.appendRow({
                    kind: "folder", type: "folder", folderId: fol.id,
                    ref: "folder:" + fol.id, name: fol.name,
                    depth: depth, expanded: exp
                })
                if (exp) walk(fol.id, depth + 1)
            }
            var its = itemsByFolder[parentId] || []
            var t
            for (t = 0; t < its.length; t++) {
                its[t].depth = depth
                // Carry the container folder so a drop on this item files into
                // the same folder (root items carry "" → drop unfiles to root).
                its[t].folderId = parentId
                browserRoot.appendRow(its[t])
            }
        }
        walk("", 0)
    }

    // Per-type placeholder icon so types are visually distinguishable. These
    // are intentional PLACEHOLDERS (short text tokens) — swap them here for the
    // real icon assets when they land. The delegate uses
    // ``row.icon || getDefaultIcon(type)`` so an explicit per-item icon wins.
    function getDefaultIcon(type) {
        switch ((type || "").toLowerCase()) {
            case "dataset": return "[DS]"
            case "table":   return "[TBL]"
            case "graph":   return "[GR]"
            case "map":     return "[MAP]"
            case "image":   return "[IMG]"
            case "note":    return "[TXT]"
            case "output":  return "[OUT]"
            case "folder":  return "[DIR]"
            default:        return "[?]"
        }
    }

    // -- Selection, opening & metadata -------------------------------------

    function selectItem(row) {
        if (!row) return
        browserRoot.selectedRef = row.ref || ""
        browserRoot.selectedDataset = (row.type === "dataset") ? row.id : ""
        if (row.type === "dataset" && backend)
            backend.setActiveDataset(row.id)
        browserRoot.updateMetadataFor(row)
    }

    // Double-click action: open the item in its viewer.
    function openItemRow(row) {
        if (!backend || !row) return
        switch (row.type) {
            case "dataset": backend.openItem(row.id); break
            case "map": backend.openMap(row.id); break
            case "image": backend.openImage(row.id); break
            case "note": backend.openNote(row.id); break
            case "output": backend.openItem(row.path || row.name); break
            default: break  // tables/graphs are already-open embedded windows
        }
    }

    // Re-render the metadata panel for the current selection (used after a
    // rename so the dataset block refreshes).
    function updateMetadata() {
        if (!backend || !browserRoot.selectedDataset) return
        browserRoot.updateMetadataFor({
            type: "dataset", id: browserRoot.selectedDataset,
            name: browserRoot.selectedDataset
        })
    }

    function updateMetadataFor(row) {
        if (!row) {
            metadataText.text = "No item selected"
            return
        }
        var s = ""
        switch (row.type) {
            case "dataset":
                var info = (backend ? backend.getDatasetInfo(row.id) : null) || {}
                s = "Dataset: " + row.name + "\n"
                s += "Type: " + (info.type || "Unknown") + "\n"
                s += "Dimensions: " + (info.dimensions || "N/A") + "\n"
                s += "Spectra: " + (info.num_spectra || 0) + "\n"
                s += "Points: " + (info.num_points || 0) + "\n"
                s += "Independent Variable: " + (info.independent_var || "N/A")
                break
            case "map":
                s = "Map: " + row.name + "\nID: " + row.id
                if (row.path) s += "\nPath: " + row.path
                s += "\n\nDouble-click to open"
                break
            case "image":
                s = "Image: " + row.name + "\nID: " + row.id +
                    "\nType: " + (row.displayType || "Image") +
                    "\n\nDouble-click to open"
                break
            case "note":
                s = "Note: " + row.name + "\nID: " + row.id +
                    "\nSource: " + (row.displayType || "Note")
                if (row.preview) s += "\n\n" + row.preview
                s += "\n\nDouble-click to open"
                break
            case "output":
                s = "Output: " + row.name + "\nTool: " + (row.displayType || "Unknown")
                if (row.path) s += "\nPath: " + row.path
                s += "\n\nDouble-click to open"
                break
            case "table":
                s = "Table: " + row.name + "\nID: " + row.id + "\n\nDouble-click to open"
                break
            case "graph":
                s = "Graph: " + row.name + "\nID: " + row.id + "\n\nDouble-click to open"
                break
            default:
                s = row.name || "No item selected"
        }
        metadataText.text = s
    }

    // -- Transient embedded-window entries (called from Main.qml) -----------

    function addTableEntry(windowId, title) {
        var arr = browserRoot.transientWindows.slice()
        arr.push({ type: "table", id: windowId, name: title })
        browserRoot.transientWindows = arr
        browserRoot.rebuildRows()
    }

    function addGraphEntry(windowId, title) {
        var arr = browserRoot.transientWindows.slice()
        arr.push({ type: "graph", id: windowId, name: title })
        browserRoot.transientWindows = arr
        browserRoot.rebuildRows()
    }

    function removeWindowEntry(windowId) {
        browserRoot.transientWindows = browserRoot.transientWindows.filter(function(w) {
            return w.id !== windowId
        })
        browserRoot.rebuildRows()
    }

    // -- Backend signal wiring ---------------------------------------------
    // Every relevant change just rebuilds the tree from fresh backend state.
    Connections {
        target: backend

        function onDataLoaded(datasetName) { browserRoot.rebuildRows() }
        function onProjectLoaded(projectPath) { browserRoot.rebuildRows() }
        function onBrowserTreeChanged() { browserRoot.rebuildRows() }

        function onMapCreated(mapId, mapTitle) { browserRoot.rebuildRows() }
        function onMapDeleted(mapPath) { browserRoot.rebuildRows() }

        function onImageAdded(imageId, name) { browserRoot.rebuildRows() }
        function onImageDeleted(imageId) { browserRoot.rebuildRows() }
        function onImageRenamed(imageId, newName) { browserRoot.rebuildRows() }

        function onNoteAdded(noteId, name) { browserRoot.rebuildRows() }
        function onNoteDeleted(noteId) { browserRoot.rebuildRows() }
        function onNoteRenamed(noteId, newName) { browserRoot.rebuildRows() }

        function onOutputCreated(outputId, toolName, filePath) { browserRoot.rebuildRows() }

        function onDatasetDeleted(datasetName) {
            if (browserRoot.selectedDataset === datasetName) {
                browserRoot.selectedDataset = ""
                browserRoot.selectedRef = ""
                metadataText.text = "No item selected"
            }
            browserRoot.rebuildRows()
        }
        function onDatasetRenamed(oldName, newName) {
            if (browserRoot.selectedDataset === oldName) {
                browserRoot.selectedDataset = newName
                browserRoot.selectedRef = "dataset:" + newName
            }
            browserRoot.rebuildRows()
        }
    }

    Component.onCompleted: {
        var t0 = Date.now()
        browserRoot.rebuildRows()
        console.log("[TIMING] ProjectBrowser onCompleted: " + (Date.now() - t0) + "ms")
    }
}
