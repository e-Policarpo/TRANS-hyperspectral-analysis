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

    // Selected dataset tracking
    property string selectedDataset: ""
    property string selectedCategory: ""

    // Sort state for browser items (right-click a category header to change).
    // "name" or "type"; applied when (re)populating the per-category models.
    property string sortKey: "name"
    property bool sortAsc: true

    // Comparator over item dicts ({name/title, type}). When sorting by type,
    // ties fall back to name so the order is stable.
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

    // Sort an array of item dicts then (re)fill a ListModel from it.
    function populateSorted(model, items) {
        var arr = items.slice()
        arr.sort(browserRoot.itemComparator)
        model.clear()
        for (var i = 0; i < arr.length; i++)
            model.append(arr[i])
    }

    // Change sort and re-apply across categories.
    function setSort(key) {
        if (browserRoot.sortKey === key)
            browserRoot.sortAsc = !browserRoot.sortAsc
        else {
            browserRoot.sortKey = key
            browserRoot.sortAsc = true
        }
        refreshBrowser()
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

                // Refresh button
                Button {
                    text: "↻"
                    font.pixelSize: 16
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: browserRoot.refreshBrowser()

                    background: Rectangle {
                        color: parent.pressed ? accentPink : (parent.hovered ? bgDark : "transparent")
                        radius: 4
                        opacity: parent.pressed ? 0.3 : (parent.hovered ? 0.5 : 1)
                    }

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
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
                placeholderText: "Search datasets..."
                color: textLight
                placeholderTextColor: textMuted
                background: Rectangle { color: "transparent" }
                selectByMouse: true

                onTextChanged: {
                    filterModel()
                }
            }
        }

        // Tree view
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ListView {
                id: categoryListView
                model: categoryModel
                spacing: 4

                delegate: Item {
                    width: categoryListView.width
                    height: categoryHeader.height + (model.expanded ? itemRepeater.height : 0)

                    Column {
                        width: parent.width
                        spacing: 2

                        // Category header
                        Rectangle {
                            id: categoryHeader
                            width: parent.width
                            height: 32
                            color: categoryMouseArea.containsMouse ? bgLight : "transparent"
                            radius: 4

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                Text {
                                    text: model.expanded ? "▼" : "▶"
                                    font.pixelSize: 10
                                    color: textMuted
                                }

                                Text {
                                    text: model.name
                                    font.pixelSize: 13
                                    font.bold: true
                                    color: textLight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: {
                                        // Show count based on category
                                        switch(model.name) {
                                            case "Datasets": return datasetsModel.count
                                            case "Tables": return tablesModel.count
                                            case "Graphs": return graphsModel.count
                                            case "Maps": return mapsModel.count
                                            case "Images": return imagesModel.count
                                            case "Notes": return notesModel.count
                                            default: return 0
                                        }
                                    }
                                    font.pixelSize: 11
                                    color: textMuted
                                }
                            }

                            MouseArea {
                                id: categoryMouseArea
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: (mouse) => {
                                    if (mouse.button === Qt.RightButton) {
                                        sortMenu.popup()
                                    } else {
                                        categoryModel.setProperty(index, "expanded", !model.expanded)
                                    }
                                }
                            }

                            // Right-click a category header to sort all items.
                            Menu {
                                id: sortMenu
                                MenuItem {
                                    text: "Sort by Name" +
                                          (browserRoot.sortKey === "name"
                                              ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
                                    onTriggered: browserRoot.setSort("name")
                                }
                                MenuItem {
                                    text: "Sort by Type" +
                                          (browserRoot.sortKey === "type"
                                              ? (browserRoot.sortAsc ? "  ↑" : "  ↓") : "")
                                    onTriggered: browserRoot.setSort("type")
                                }
                            }
                        }

                        // Category items
                        Column {
                            id: itemRepeater
                            width: parent.width
                            height: childrenRect.height
                            visible: model.expanded
                            spacing: 1

                            property string categoryName: model.name

                            Repeater {
                                model: {
                                    if (!parent.visible) return 0
                                    // Return appropriate model based on category name
                                    switch(parent.categoryName) {
                                        case "Datasets": return datasetsModel
                                        case "Tables": return tablesModel
                                        case "Graphs": return graphsModel
                                        case "Maps": return mapsModel
                                        case "Images": return imagesModel
                                        case "Notes": return notesModel
                                        default: return 0
                                    }
                                }

                                delegate: Rectangle {
                                    width: itemRepeater.width
                                    height: 28
                                    color: {
                                        var itemName = model.name || model.title || ""
                                        var isSelected = (itemRepeater.categoryName === browserRoot.selectedCategory &&
                                                         itemName === browserRoot.selectedDataset)
                                        if (isSelected) {
                                            return Qt.rgba(1, 0.7, 0.85, 0.3)  // Selected
                                        } else if (itemMouseArea.containsMouse) {
                                            return Qt.rgba(1, 0.7, 0.85, 0.2)  // Hover
                                        } else {
                                            return "transparent"
                                        }
                                    }
                                    radius: 3

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 32
                                        anchors.rightMargin: 8
                                        spacing: 8

                                        Text {
                                            text: model.icon || getDefaultIcon(itemRepeater.categoryName)
                                            font.pixelSize: 12
                                            color: "#e0e0e0"
                                            renderType: Text.NativeRendering
                                        }

                                        // Item name. When the name is too
                                        // long it elides with "…"; on hover,
                                        // if it actually overflows, it scrolls
                                        // (marquee) so the full name is
                                        // readable without resizing the panel.
                                        Item {
                                            id: nameClip
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: nameText.implicitHeight
                                            clip: true

                                            readonly property bool overflowing: nameText.implicitWidth > width
                                            readonly property bool scrolling: itemMouseArea.containsMouse && overflowing

                                            Text {
                                                id: nameText
                                                text: model.title || model.name || ""
                                                font.pixelSize: 12
                                                font.bold: false
                                                color: "#e0e0e0"
                                                renderType: Text.NativeRendering
                                                // Full width while scrolling so nothing is elided;
                                                // otherwise constrained + elided to the container.
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

                                        Text {
                                            text: model.type || ""
                                            font.pixelSize: 10
                                            color: "#999999"
                                            renderType: Text.NativeRendering
                                        }
                                    }

                                    // Drag support for Maps category
                                    Drag.active: itemMouseArea.drag.active && itemRepeater.categoryName === "Maps"
                                    Drag.hotSpot.x: width / 2
                                    Drag.hotSpot.y: height / 2
                                    Drag.mimeData: {
                                        "text/plain": model.name || model.id || "",
                                        "application/x-trans-map": JSON.stringify({
                                            name: model.name || "",
                                            id: model.id || "",
                                            path: model.path || "",
                                            category: itemRepeater.categoryName
                                        })
                                    }
                                    Drag.dragType: Drag.Automatic

                                    MouseArea {
                                        id: itemMouseArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        drag.target: itemRepeater.categoryName === "Maps" ? parent : undefined
                                        drag.threshold: 10

                                        onClicked: (mouse) => {
                                            if (mouse.button === Qt.RightButton) {
                                                // Create itemData object from model
                                                contextMenu.itemData = {
                                                    "name": model.name || "",
                                                    "id": model.id || "",
                                                    "icon": model.icon || "",
                                                    "type": model.type || "",
                                                    "title": model.title || "",
                                                    "category": itemRepeater.categoryName
                                                }
                                                contextMenu.popup()
                                            } else if (mouse.button === Qt.LeftButton) {
                                                // Select the item - works for ALL categories
                                                browserRoot.selectedCategory = itemRepeater.categoryName
                                                browserRoot.selectedDataset = model.name || model.title || ""

                                                // Update metadata based on category
                                                switch(itemRepeater.categoryName) {
                                                    case "Datasets":
                                                        if (model.name) {
                                                            backend.setActiveDataset(model.name)
                                                            updateMetadata()
                                                        }
                                                        break
                                                    case "Tables":
                                                        updateMetadataForTable(model)
                                                        break
                                                    case "Graphs":
                                                        updateMetadataForGraph(model)
                                                        break
                                                    case "Maps":
                                                        updateMetadataForMap(model)
                                                        break
                                                    case "Notes":
                                                        updateMetadataForNote(model)
                                                        break
                                                }
                                            }
                                        }

                                        onDoubleClicked: {
                                            if (!backend) return

                                            // Open item based on category
                                            switch(itemRepeater.categoryName) {
                                                case "Datasets":
                                                    if (model.name) {
                                                        backend.openItem(model.name)
                                                    }
                                                    break
                                                case "Maps":
                                                    if (model.id || model.path) {
                                                        backend.openMap(model.id || model.path)
                                                    }
                                                    break
                                                case "Images":
                                                    if (model.id) {
                                                        backend.openImage(model.id)
                                                    }
                                                    break
                                                case "Graphs":
                                                    console.log("Graphs are now embedded windows")
                                                    break
                                                case "Tables":
                                                    console.log("Tables are now embedded windows")
                                                    break
                                                case "Notes":
                                                    if (model.id) {
                                                        backend.openNote(model.id)
                                                    } else if (model.path) {
                                                        backend.openItem(model.path)
                                                    }
                                                    break
                                                default:
                                                    console.log("No action for category:", itemRepeater.categoryName)
                                            }
                                        }
                                    }
                                }
                            }
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
                    text: "No dataset selected"
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
                text: parent.text
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

    // Category model
    ListModel {
        id: categoryModel

        ListElement {
            name: "Datasets"
            expanded: true
        }

        ListElement {
            name: "Tables"
            expanded: false
        }

        ListElement {
            name: "Graphs"
            expanded: false
        }

        ListElement {
            name: "Maps"
            expanded: false
        }

        ListElement {
            name: "Images"
            expanded: false
        }

        ListElement {
            name: "Notes"
            expanded: false
        }
    }

    // Datasets model (populated dynamically)
    ListModel {
        id: datasetsModel
    }

    // Tables model (populated dynamically)
    ListModel {
        id: tablesModel
    }

    // Graphs model (populated dynamically)
    ListModel {
        id: graphsModel
    }

    // Maps model (populated dynamically)
    ListModel {
        id: mapsModel
    }

    // Images model (populated dynamically — refreshed via Connections below).
    ListModel {
        id: imagesModel
    }

    // Outputs model (populated dynamically)
    ListModel {
        id: outputsModel
    }

    // Notes model (populated dynamically)
    ListModel {
        id: notesModel
    }

    // Context menu
    Menu {
        id: contextMenu
        property var itemData: null

        MenuItem {
            text: "Open"
            onTriggered: {
                if (!backend || !contextMenu.itemData) return

                // Call appropriate method based on category
                switch(contextMenu.itemData.category) {
                    case "Datasets":
                        if (contextMenu.itemData.name) {
                            backend.setActiveDataset(contextMenu.itemData.name)
                        }
                        break
                    case "Maps":
                        if (contextMenu.itemData.id) {
                            backend.openMap(contextMenu.itemData.id)
                        }
                        break
                    case "Images":
                        if (contextMenu.itemData.id) {
                            backend.openImage(contextMenu.itemData.id)
                        }
                        break
                    case "Notes":
                        if (contextMenu.itemData.id) {
                            backend.openNote(contextMenu.itemData.id)
                        }
                        break
                    case "Graphs":
                        console.log("Graphs are now embedded windows")
                        break
                    case "Tables":
                        console.log("Tables are now embedded windows")
                        break
                }
            }
        }

        MenuItem {
            text: "Convert to Image (raw)"
            visible: contextMenu.itemData && contextMenu.itemData.category === "Maps"
            onTriggered: {
                if (backend && contextMenu.itemData && contextMenu.itemData.id) {
                    backend.convertMapChannelToImage(contextMenu.itemData.id, "")
                }
            }
        }

        MenuItem {
            text: "Convert to Map (TIFF)"
            visible: contextMenu.itemData && contextMenu.itemData.category === "Images"
            onTriggered: {
                if (backend && contextMenu.itemData && contextMenu.itemData.id) {
                    backend.convertImageToMap(contextMenu.itemData.id)
                }
            }
        }

        MenuItem {
            text: "Open in OS viewer…"
            visible: contextMenu.itemData && contextMenu.itemData.category === "Images"
            onTriggered: {
                if (backend && contextMenu.itemData && contextMenu.itemData.id) {
                    backend.openImageInOS(contextMenu.itemData.id)
                }
            }
        }

        MenuItem {
            text: "Open in OS editor…"
            visible: contextMenu.itemData && contextMenu.itemData.category === "Notes"
            onTriggered: {
                if (backend && contextMenu.itemData && contextMenu.itemData.id) {
                    backend.openNoteInOS(contextMenu.itemData.id)
                }
            }
        }

        MenuItem {
            text: "Rename..."
            visible: contextMenu.itemData && (contextMenu.itemData.category === "Datasets" ||
                     contextMenu.itemData.category === "Maps" ||
                     contextMenu.itemData.category === "Tables" ||
                     contextMenu.itemData.category === "Graphs" ||
                     contextMenu.itemData.category === "Images")
            onTriggered: {
                if (contextMenu.itemData) {
                    renameDialog.itemCategory = contextMenu.itemData.category
                    renameDialog.itemName = contextMenu.itemData.name
                    renameDialog.itemId = contextMenu.itemData.id || ""
                    renameDialog.newNameField.text = contextMenu.itemData.name
                    renameDialog.open()
                }
            }
        }

        MenuSeparator { }

        MenuItem {
            text: "Delete"
            visible: contextMenu.itemData && (contextMenu.itemData.category === "Datasets" ||
                     contextMenu.itemData.category === "Maps" ||
                     contextMenu.itemData.category === "Tables" ||
                     contextMenu.itemData.category === "Graphs" ||
                     contextMenu.itemData.category === "Images")
            onTriggered: {
                if (contextMenu.itemData) {
                    deleteConfirmDialog.itemCategory = contextMenu.itemData.category
                    deleteConfirmDialog.itemName = contextMenu.itemData.name
                    deleteConfirmDialog.itemId = contextMenu.itemData.id || ""
                    deleteConfirmDialog.open()
                }
            }
        }

        MenuItem {
            text: "Properties..."
            onTriggered: {
                if (contextMenu.itemData) {
                    // Show dataset info in console
                    var info = backend.getDatasetInfo(contextMenu.itemData.name)
                    if (info && info.type) {
                        console.log("Dataset Info:", JSON.stringify(info, null, 2))
                    }
                }
            }
        }
    }

    // Delete confirmation dialog
    Dialog {
        id: deleteConfirmDialog
        property string itemCategory: ""
        property string itemName: ""
        property string itemId: ""

        title: "Delete " + itemCategory.slice(0, -1)  // Remove trailing 's' (Datasets -> Dataset)
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        width: 300

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
                text: "This action cannot be undone."
                color: textMuted
                font.pixelSize: 11
            }
        }

        background: Rectangle {
            color: bgDark
            border.color: borderColor
            radius: 6
        }

        onAccepted: {
            if (backend && itemName) {
                var success = false
                switch (itemCategory) {
                    case "Datasets":
                        success = backend.deleteDataset(itemName)
                        if (success && browserRoot.selectedDataset === itemName) {
                            browserRoot.selectedDataset = ""
                            metadataText.text = "No dataset selected"
                        }
                        break
                    case "Maps":
                        success = backend.deleteMap(itemId || itemName)
                        break
                    case "Tables":
                        success = backend.deleteTable(itemId || itemName)
                        break
                    case "Graphs":
                        success = backend.deleteGraph(itemId || itemName)
                        break
                }
                if (success) {
                    refreshBrowser()
                }
            }
        }
    }

    // Rename dialog
    Dialog {
        id: renameDialog
        property string itemCategory: ""
        property string itemName: ""
        property string itemId: ""
        property alias newNameField: newNameInput

        title: "Rename " + itemCategory.slice(0, -1)  // Remove trailing 's'
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 350

        contentItem: ColumnLayout {
            spacing: 10

            Text {
                text: "Rename " + renameDialog.itemCategory.slice(0, -1).toLowerCase() + ":"
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
            if (backend && itemName && newNameInput.text) {
                var newName = newNameInput.text.trim()
                if (newName && newName !== itemName) {
                    var success = false
                    switch (itemCategory) {
                        case "Datasets":
                            success = backend.renameDataset(itemName, newName)
                            if (success && browserRoot.selectedDataset === itemName) {
                                browserRoot.selectedDataset = newName
                            }
                            break
                        case "Maps":
                            success = backend.renameMap(itemId || itemName, newName)
                            break
                        case "Tables":
                            success = backend.renameTable(itemId || itemName, newName)
                            break
                        case "Graphs":
                            success = backend.renameGraph(itemId || itemName, newName)
                            break
                    }
                    if (success) {
                        refreshBrowser()
                        updateMetadata()
                    }
                }
            }
        }
    }

    // Functions
    function refreshBrowser() {
        if (!backend) {
            return
        }

        // Each category is collected into an array, then sorted + appended via
        // populateSorted() so the current sort (name/type) applies uniformly.
        var i

        // Datasets
        var datasets = backend.getDatasetList()
        var datasetItems = []
        for (i = 0; i < datasets.length; i++) {
            var datasetInfo = backend.getDatasetInfo(datasets[i])
            datasetItems.push({
                name: datasets[i],
                icon: "",
                type: datasetInfo.type || "Unknown",
                dimensions: datasetInfo.dimensions || [],
                numSpectra: datasetInfo.num_spectra || 0
            })
        }
        populateSorted(datasetsModel, datasetItems)

        // Tables and graphs are now embedded windows managed by WindowManager
        tablesModel.clear()
        graphsModel.clear()

        // Maps
        var maps = backend.getMapList()
        var mapItems = []
        for (i = 0; i < maps.length; i++) {
            mapItems.push({
                id: maps[i].id,
                title: maps[i].title,
                name: maps[i].title,
                path: maps[i].path,
                icon: "",
                type: "Map"
            })
        }
        populateSorted(mapsModel, mapItems)

        // Images (RGB previews, optical/video frames, raw map channels)
        var images = backend.getImageList ? backend.getImageList() : []
        var imageItems = []
        for (i = 0; i < images.length; i++) {
            imageItems.push({
                id: images[i].id,
                title: images[i].name,
                name: images[i].name,
                icon: "",
                type: images[i].mode || "Image"
            })
        }
        populateSorted(imagesModel, imageItems)

        // Notes (text annotations from measurement files + user notes)
        var notes = backend.getNotesList ? backend.getNotesList() : []
        var noteItems = []
        for (i = 0; i < notes.length; i++) {
            noteItems.push({
                id: notes[i].id,
                title: notes[i].name,
                name: notes[i].name,
                icon: "",
                type: notes[i].source || "Note"
            })
        }
        populateSorted(notesModel, noteItems)

        // Outputs
        var outputs = backend.getOutputList()
        var outputItems = []
        for (i = 0; i < outputs.length; i++) {
            outputItems.push({
                id: outputs[i].id,
                title: outputs[i].filename,
                name: outputs[i].filename,
                icon: "",
                type: outputs[i].tool
            })
        }
        populateSorted(outputsModel, outputItems)
    }

    // Per-type icon for browser items so types are visually distinguishable.
    // PLACEHOLDERS for now — short text tokens per type; replace these with the
    // real icon assets when provided (single spot to swap). The delegate uses
    // ``model.icon || getDefaultIcon(category)`` so an explicit per-item icon
    // still wins. Reused by the unified-tree delegate.
    function getDefaultIcon(categoryName) {
        switch (categoryName) {
            case "Datasets": return "[DS]"
            case "Tables":   return "[TBL]"
            case "Graphs":   return "[GR]"
            case "Maps":     return "[MAP]"
            case "Images":   return "[IMG]"
            case "Notes":    return "[TXT]"
            case "Outputs":  return "[OUT]"
            case "Folder":   return "[DIR]"
            default:          return "[?]"
        }
    }

    function updateMetadata() {
        if (!backend || !browserRoot.selectedDataset) {
            metadataText.text = "No item selected"
            return
        }

        var info = backend.getDatasetInfo(browserRoot.selectedDataset)
        if (!info || !info.type) {
            metadataText.text = "No item selected"
            return
        }

        var metaStr = "Dataset: " + browserRoot.selectedDataset + "\n"
        metaStr += "Type: " + info.type + "\n"
        metaStr += "Dimensions: " + (info.dimensions || "N/A") + "\n"
        metaStr += "Spectra: " + (info.num_spectra || "0") + "\n"
        metaStr += "Points: " + (info.num_points || "0") + "\n"
        metaStr += "Independent Variable: " + (info.independent_var || "N/A")

        metadataText.text = metaStr
    }

    // Add/remove entries from Main.qml when embedded windows open/close
    function addTableEntry(windowId, title) {
        tablesModel.append({
            id: windowId,
            title: title,
            name: title,
            icon: "",
            type: "Table"
        })
    }

    function addGraphEntry(windowId, title) {
        graphsModel.append({
            id: windowId,
            title: title,
            name: title,
            icon: "",
            type: "Graph"
        })
    }

    function removeWindowEntry(windowId) {
        var i
        for (i = 0; i < tablesModel.count; i++) {
            if (tablesModel.get(i).id === windowId) {
                tablesModel.remove(i)
                return
            }
        }
        for (i = 0; i < graphsModel.count; i++) {
            if (graphsModel.get(i).id === windowId) {
                graphsModel.remove(i)
                return
            }
        }
    }

    function updateMetadataForTable(model) {
        var metaStr = "Table: " + (model.title || model.name || "Untitled") + "\n"
        metaStr += "ID: " + (model.id || "N/A") + "\n"
        metaStr += "Type: Table\n"
        metaStr += "\nDouble-click to open"
        metadataText.text = metaStr
    }

    function updateMetadataForGraph(model) {
        var metaStr = "Graph: " + (model.title || model.name || "Untitled") + "\n"
        metaStr += "ID: " + (model.id || "N/A") + "\n"
        metaStr += "Type: Graph\n"
        metaStr += "\nDouble-click to open"
        metadataText.text = metaStr
    }

    function updateMetadataForMap(model) {
        var metaStr = "Map: " + (model.title || model.name || "Untitled") + "\n"
        metaStr += "ID: " + (model.id || "N/A") + "\n"
        metaStr += "Type: Map Image\n"
        if (model.path) {
            metaStr += "Path: " + model.path + "\n"
        }
        metaStr += "\nDouble-click to open"
        metadataText.text = metaStr
    }

    function updateMetadataForOutput(model) {
        var metaStr = "Output: " + (model.title || model.name || "Untitled") + "\n"
        metaStr += "Tool: " + (model.type || "Unknown") + "\n"
        if (model.id) {
            metaStr += "ID: " + model.id + "\n"
        }
        metaStr += "\nDouble-click to open"
        metadataText.text = metaStr
    }

    function updateMetadataForNote(model) {
        var metaStr = "Note: " + (model.title || model.name || "Untitled") + "\n"
        if (model.path) {
            metaStr += "Path: " + model.path + "\n"
        }
        metaStr += "Type: Note\n"
        metaStr += "\nDouble-click to open"
        metadataText.text = metaStr
    }

    function filterModel() {
        var searchText = searchField.text.toLowerCase()

        if (!searchText) {
            // Refresh all lists if search is empty
            refreshDatasetsList()
            refreshOutputsList()
            return
        }

        // Filter datasets
        var datasetList = backend.getDatasetList()
        datasetsModel.clear()
        for (var i = 0; i < datasetList.length; i++) {
            var name = datasetList[i]
            if (name.toLowerCase().includes(searchText)) {
                datasetsModel.append({
                    "name": name,
                    "title": name,
                    "type": "data",
                    "icon": "📊"
                })
            }
        }

        // Filter outputs
        var outputs = backend.getOutputFilesList()
        outputsModel.clear()
        for (var j = 0; j < outputs.length; j++) {
            var outputName = outputs[j].path
            if (outputName.toLowerCase().includes(searchText)) {
                outputsModel.append({
                    name: outputName,
                    title: outputs[j].path,
                    icon: "",
                    type: outputs[j].tool
                })
            }
        }
    }

    // Auto-refresh when data is loaded
    Connections {
        target: backend
        function onDataLoaded(datasetName) {
            browserRoot.refreshBrowser()
        }
        function onProjectLoaded(projectPath) {
            // Full refresh after project load to catch all restored state (maps, outputs, etc.)
            browserRoot.refreshBrowser()
        }

        function onMapCreated(mapId, mapTitle) {
            mapsModel.append({
                id: mapId,
                title: mapTitle,
                name: mapTitle,
                icon: "",
                type: "Map"
            })
        }

        function onImageAdded(imageId, name) {
            imagesModel.append({
                id: imageId,
                title: name,
                name: name,
                icon: "",
                type: "Image"
            })
        }

        function onImageDeleted(imageId) {
            for (var i = 0; i < imagesModel.count; i++) {
                if (imagesModel.get(i).id === imageId) {
                    imagesModel.remove(i)
                    break
                }
            }
        }

        function onImageRenamed(imageId, newName) {
            for (var i = 0; i < imagesModel.count; i++) {
                if (imagesModel.get(i).id === imageId) {
                    imagesModel.setProperty(i, "name", newName)
                    imagesModel.setProperty(i, "title", newName)
                    break
                }
            }
        }

        function onNoteAdded(noteId, name) {
            notesModel.append({
                id: noteId,
                title: name,
                name: name,
                icon: "",
                type: "Note"
            })
        }
        function onNoteDeleted(noteId) {
            for (var i = 0; i < notesModel.count; i++) {
                if (notesModel.get(i).id === noteId) {
                    notesModel.remove(i)
                    break
                }
            }
        }
        function onNoteRenamed(noteId, newName) {
            for (var i = 0; i < notesModel.count; i++) {
                if (notesModel.get(i).id === noteId) {
                    notesModel.setProperty(i, "name", newName)
                    notesModel.setProperty(i, "title", newName)
                    break
                }
            }
        }
        function onOutputCreated(outputId, toolName, filePath) {
            var fileName = filePath.split('/').pop()
            outputsModel.append({
                id: outputId,
                title: fileName,
                name: fileName,
                icon: "",
                type: toolName
            })
        }
        function onDatasetDeleted(datasetName) {
            // Remove from model
            for (var i = 0; i < datasetsModel.count; i++) {
                if (datasetsModel.get(i).name === datasetName) {
                    datasetsModel.remove(i)
                    break
                }
            }
            // Clear selection if this was selected
            if (browserRoot.selectedDataset === datasetName) {
                browserRoot.selectedDataset = ""
                metadataText.text = "No dataset selected"
            }
        }
        function onDatasetRenamed(oldName, newName) {
            // Update model
            for (var i = 0; i < datasetsModel.count; i++) {
                if (datasetsModel.get(i).name === oldName) {
                    datasetsModel.setProperty(i, "name", newName)
                    break
                }
            }
            // Update selection if this was selected
            if (browserRoot.selectedDataset === oldName) {
                browserRoot.selectedDataset = newName
                updateMetadata()
            }
        }
        function onWindowClosed(windowType, windowId) {
            if (windowType === "table") {
                for (var i = 0; i < tablesModel.count; i++) {
                    if (tablesModel.get(i).id === windowId) {
                        tablesModel.remove(i)
                        break
                    }
                }
            } else if (windowType === "graph") {
                for (i = 0; i < graphsModel.count; i++) {
                    if (graphsModel.get(i).id === windowId) {
                        graphsModel.remove(i)
                        break
                    }
                }
            }
        }
        function onMapDeleted(mapPath) {
            // Remove map from model
            for (var i = 0; i < mapsModel.count; i++) {
                var mapItem = mapsModel.get(i)
                if (mapItem.path === mapPath || mapItem.id === mapPath) {
                    mapsModel.remove(i)
                    break
                }
            }
        }
    }

    Component.onCompleted: {
        var t0 = Date.now()
        refreshBrowser()
        console.log("[TIMING] ProjectBrowser onCompleted: " + (Date.now() - t0) + "ms")
    }
}
