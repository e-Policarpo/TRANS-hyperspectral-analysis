/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * DockPanel - Collapsible, tabbed dock panel component
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: dockPanel

    // Position determines resize handle location and layout behavior
    // Values: "left", "right", "top", "bottom"
    property string position: "left"

    // Size constraints
    property real minimumSize: 150
    property real maximumSize: 600
    property real preferredSize: 280

    // Collapse state
    property bool collapsed: false
    property real collapsedSize: 32  // Width/height when collapsed (shows tabs only)

    // Tab management
    property alias tabModel: tabRepeater.model
    property int currentTabIndex: 0
    property alias contentLoader: contentLoader

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: mainWin ? mainWin.bgDark : "#1a1a2e"
    property color bgMedium: mainWin ? mainWin.bgMedium : "#2a2a3e"
    property color bgLight: mainWin ? mainWin.bgLight : "#3a3a4e"
    property color textLight: mainWin ? mainWin.textLight : "#ffffff"
    property color textMuted: mainWin ? mainWin.textMuted : "#cccccc"
    property color accentPink: mainWin ? mainWin.accentPink : "#F5A9B8"
    property color accentBlue: mainWin ? mainWin.accentBlue : "#5BCEFA"
    property color borderColor: mainWin ? mainWin.borderColor : "#9B4F96"

    // Font scaling - reactive bindings to main window
    property int fontSizeSmall: mainWin ? mainWin.fontSizeSmall : 10
    property int fontSizeMedium: mainWin ? mainWin.fontSizeMedium : 12

    // Signals
    signal tabSelected(int index, string tabId)
    signal tabClosed(int index, string tabId)
    signal panelResized(real newSize)
    signal collapseToggled(bool collapsed)

    // Computed properties
    property bool isHorizontal: position === "left" || position === "right"
    property real actualSize: collapsed ? collapsedSize : preferredSize

    // Panel sizing
    implicitWidth: isHorizontal ? actualSize : parent.width
    implicitHeight: isHorizontal ? parent.height : actualSize

    color: bgLight
    border.color: borderColor
    border.width: 1
    clip: true

    // Collapse/expand animation
    Behavior on preferredSize {
        NumberAnimation {
            duration: 150
            easing.type: Easing.OutQuad
        }
    }

    Behavior on actualSize {
        NumberAnimation {
            duration: 150
            easing.type: Easing.OutQuad
        }
    }

    // Main layout
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header with tabs and collapse button
        Rectangle {
            id: headerArea
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: bgMedium

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                spacing: 2

                // Collapse/expand button
                Rectangle {
                    id: collapseBtn
                    width: 20
                    height: 20
                    color: collapseBtnArea.containsMouse ? Qt.lighter(bgMedium, 1.3) : "transparent"
                    radius: 3

                    Text {
                        anchors.centerIn: parent
                        text: {
                            if (collapsed) {
                                return isHorizontal ?
                                    (position === "left" ? "▶" : "◀") :
                                    (position === "top" ? "▼" : "▲")
                            } else {
                                return isHorizontal ?
                                    (position === "left" ? "◀" : "▶") :
                                    (position === "top" ? "▲" : "▼")
                            }
                        }
                        font.pixelSize: fontSizeSmall
                        color: textMuted
                    }

                    MouseArea {
                        id: collapseBtnArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            collapsed = !collapsed
                            collapseToggled(collapsed)
                        }
                    }
                }

                // Tabs
                Row {
                    id: tabRow
                    Layout.fillWidth: true
                    spacing: 2
                    clip: true

                    Repeater {
                        id: tabRepeater
                        model: ListModel {}

                        delegate: Rectangle {
                            id: tabDelegate
                            width: Math.min(tabLabel.implicitWidth + 30, 120)
                            height: 22
                            color: index === currentTabIndex ? bgLight : "transparent"
                            radius: 3

                            property string tabId: model.tabId || ""
                            property string tabTitle: model.title || "Tab"
                            property var tabComponent: model.component || null

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: 4
                                spacing: 4

                                Text {
                                    id: tabLabel
                                    Layout.fillWidth: true
                                    text: tabDelegate.tabTitle
                                    font.pixelSize: fontSizeSmall + 1
                                    color: index === currentTabIndex ? textLight : textMuted
                                    elide: Text.ElideRight
                                }

                                // Close button
                                Rectangle {
                                    width: 14
                                    height: 14
                                    color: closeArea.containsMouse ? Qt.rgba(1, 0.3, 0.3, 0.5) : "transparent"
                                    radius: 2
                                    visible: tabRepeater.count > 1

                                    Text {
                                        anchors.centerIn: parent
                                        text: "×"
                                        font.pixelSize: fontSizeMedium
                                        font.bold: true
                                        color: closeArea.containsMouse ? textLight : textMuted
                                    }

                                    MouseArea {
                                        id: closeArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            tabClosed(index, tabDelegate.tabId)
                                        }
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                z: -1  // Behind close button
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    currentTabIndex = index
                                    tabSelected(index, tabDelegate.tabId)
                                }
                            }
                        }
                    }
                }
            }
        }

        // Separator line
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: borderColor
        }

        // Content area
        Item {
            id: contentArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !collapsed

            Loader {
                id: contentLoader
                anchors.fill: parent
                anchors.margins: 4

                // Load component from current tab if available
                sourceComponent: {
                    if (tabRepeater.count > 0 && currentTabIndex >= 0 && currentTabIndex < tabRepeater.count) {
                        var item = tabRepeater.itemAt(currentTabIndex)
                        if (item && item.tabComponent) {
                            return item.tabComponent
                        }
                    }
                    return null
                }
            }

            // Placeholder when no content
            Text {
                anchors.centerIn: parent
                visible: !contentLoader.item && tabRepeater.count === 0
                text: "No content"
                font.pixelSize: fontSizeMedium
                color: textMuted
            }
        }
    }

    // Resize handle
    Rectangle {
        id: resizeHandle
        color: resizeArea.containsMouse ? accentBlue : "transparent"
        opacity: 0.5

        // Position based on panel position
        anchors.top: isHorizontal ? parent.top : undefined
        anchors.bottom: position === "top" ? parent.bottom : (isHorizontal ? parent.bottom : undefined)
        anchors.left: position === "right" ? parent.left : (isHorizontal ? undefined : parent.left)
        anchors.right: position === "left" ? parent.right : (isHorizontal ? undefined : parent.right)
        anchors.topMargin: position === "bottom" ? 0 : undefined

        width: isHorizontal ? 4 : parent.width
        height: isHorizontal ? parent.height : 4

        visible: !collapsed

        MouseArea {
            id: resizeArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: isHorizontal ? Qt.SizeHorCursor : Qt.SizeVerCursor

            property real startPos: 0
            property real startSize: 0

            onPressed: function(mouse) {
                startPos = isHorizontal ? mouse.x : mouse.y
                startSize = preferredSize
            }

            onPositionChanged: function(mouse) {
                if (!pressed) return

                var delta = isHorizontal ?
                    (position === "left" ? mouse.x - startPos : startPos - mouse.x) :
                    (position === "top" ? mouse.y - startPos : startPos - mouse.y)

                var newSize = startSize + delta
                newSize = Math.max(minimumSize, Math.min(maximumSize, newSize))

                if (newSize !== preferredSize) {
                    preferredSize = newSize
                    panelResized(newSize)
                }
            }
        }
    }

    // Public functions
    function addTab(tabId, title, component) {
        tabModel.append({
            "tabId": tabId,
            "title": title,
            "component": component
        })
        // Switch to new tab
        currentTabIndex = tabModel.count - 1
        return tabModel.count - 1
    }

    function removeTab(index) {
        if (index >= 0 && index < tabModel.count) {
            var tabId = tabModel.get(index).tabId
            tabModel.remove(index)

            // Adjust current index
            if (currentTabIndex >= tabModel.count) {
                currentTabIndex = Math.max(0, tabModel.count - 1)
            }
            return tabId
        }
        return ""
    }

    function clearTabs() {
        tabModel.clear()
        currentTabIndex = 0
    }

    function setContent(component) {
        // For single-content mode (no tabs)
        clearTabs()
        addTab("default", "", component)
    }

    Component.onCompleted: {
        console.log("DockPanel created at position:", position)
    }
}
