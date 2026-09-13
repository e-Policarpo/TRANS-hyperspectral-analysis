/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * ToolPalettePanel - Standalone tool palette for workspace left panel
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: December 2025
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: toolPalettePanel

    // Tool list to display (string array of tool names). Kept for callers
    // that hand over a flat list; the palette itself is built from
    // `sections` when those are given.
    property var tools: []

    // Sections from ToolCatalog.sectionsForTab(): [{title, level, blurb,
    // tools: [names]}]. Rendered as collapsible groups, ordered by complexity.
    property var sections: []

    // Collapsed section titles, so a long palette can be folded up.
    property var collapsed: ({})

    // Signal emitted when a tool is activated (double-click)
    signal toolActivated(string toolName)

    // Theme colors - reactive bindings to main window
    property var mainWin: ApplicationWindow.window
    property color bgDark: (mainWin && mainWin.bgDark !== undefined) ? mainWin.bgDark : Theme.bgDark
    property color bgDarker: (mainWin && mainWin.bgDarker !== undefined) ? mainWin.bgDarker : Theme.bgDarker
    property color bgMedium: (mainWin && mainWin.bgMedium !== undefined) ? mainWin.bgMedium : Theme.bgMedium
    property color bgLight: (mainWin && mainWin.bgLight !== undefined) ? mainWin.bgLight : Theme.bgLight
    property color accentPink: (mainWin && mainWin.accentPink !== undefined) ? mainWin.accentPink : Theme.accentPink
    property color accentBlue: (mainWin && mainWin.accentBlue !== undefined) ? mainWin.accentBlue : Theme.accentBlue
    property color textLight: (mainWin && mainWin.textLight !== undefined) ? mainWin.textLight : Theme.textLight
    property color textMuted: (mainWin && mainWin.textMuted !== undefined) ? mainWin.textMuted : Theme.textMuted
    property color borderColor: (mainWin && mainWin.borderColor !== undefined) ? mainWin.borderColor : Theme.borderColor

    // Font scaling
    property int fontSizeSmall: mainWin ? mainWin.fontSizeSmall : 10
    property int fontSizeMedium: mainWin ? mainWin.fontSizeMedium : 12

    color: bgMedium

    onToolsChanged: rebuildModel()
    onSectionsChanged: rebuildModel()

    // One flat model with header rows and tool rows, so a single ListView
    // draws both and the search filter sees every tool regardless of its
    // section's fold state.
    function rebuildModel() {
        toolModel.clear()
        if (sections && sections.length) {
            for (var i = 0; i < sections.length; i++) {
                var sec = sections[i]
                toolModel.append({ "kind": "header", "name": sec.title,
                                   "level": sec.level || "", "blurb": sec.blurb || "",
                                   "section": sec.title, "count": sec.tools.length })
                for (var j = 0; j < sec.tools.length; j++)
                    toolModel.append({ "kind": "tool", "name": sec.tools[j], "level": "",
                                       "blurb": "", "section": sec.title, "count": 0 })
            }
            return
        }
        if (!tools) return
        for (var k = 0; k < tools.length; k++) {
            toolModel.append({ "kind": "tool", "name": tools[k], "level": "", "blurb": "",
                               "section": "", "count": 0 })
        }
    }

    function isCollapsed(title) { return collapsed[title] === true }

    function toggleSection(title) {
        var c = {}
        for (var k in collapsed) c[k] = collapsed[k]
        c[title] = !c[title]
        collapsed = c
    }

    function levelColor(level) {
        if (level === "advanced") return accentPink
        if (level === "intermediate") return accentBlue
        return textMuted
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        // Header
        Text {
            text: "Tools"
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
            placeholderTextColor: Qt.rgba(textMuted.r, textMuted.g, textMuted.b, 0.5)
            Layout.fillWidth: true
            color: textLight
            font.pixelSize: fontSizeMedium

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
            spacing: 2

            model: ListModel { id: toolModel }

            delegate: Rectangle {
                id: row
                required property int index
                required property string kind
                required property string name
                required property string level
                required property string blurb
                required property string section
                required property int count

                readonly property bool searching: toolSearch.text !== ""
                readonly property bool isHeader: kind === "header"
                // A search flattens the palette: headers hide, every match
                // shows. Without a search a folded section hides its tools.
                visible: isHeader ? !searching
                       : (searching ? name.toLowerCase().includes(toolSearch.text.toLowerCase())
                                    : !toolPalettePanel.isCollapsed(section))

                width: toolList.width
                height: visible ? (isHeader ? (index === 0 ? 30 : 36) : 30) : 0
                color: !isHeader && toolMouseArea.containsMouse ? bgLight : "transparent"
                radius: 3

                // Section header: title, level tag, fold arrow, and the
                // blurb as a tooltip so the list stays one line per entry.
                RowLayout {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 6
                    anchors.rightMargin: 8
                    height: 24
                    spacing: 6
                    visible: row.isHeader

                    Text {
                        text: toolPalettePanel.isCollapsed(row.section) ? "▸" : "▾"
                        color: textMuted
                        font.pixelSize: fontSizeSmall
                    }
                    Text {
                        text: row.name
                        color: accentPink
                        font.pixelSize: fontSizeSmall + 1
                        font.bold: true
                        font.capitalization: Font.AllUppercase
                        font.letterSpacing: 0.6
                    }
                    Rectangle {
                        visible: row.level !== ""
                        radius: 3
                        color: "transparent"
                        border.color: toolPalettePanel.levelColor(row.level)
                        border.width: 1
                        implicitWidth: levelText.implicitWidth + 8
                        implicitHeight: levelText.implicitHeight + 3
                        Text {
                            id: levelText
                            anchors.centerIn: parent
                            text: row.level
                            color: toolPalettePanel.levelColor(row.level)
                            font.pixelSize: fontSizeSmall - 1
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: row.count
                        color: textMuted
                        font.pixelSize: fontSizeSmall
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.topMargin: 4
                    height: 1
                    color: borderColor
                    visible: row.isHeader && row.index > 0
                }

                // Tool row
                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: row.searching || row.section === "" ? 10 : 22
                    anchors.rightMargin: 10
                    visible: !row.isHeader
                    text: row.name
                    color: textLight
                    font.pixelSize: fontSizeMedium
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: toolMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (row.isHeader) toolPalettePanel.toggleSection(row.section)
                    onDoubleClicked: if (!row.isHeader) toolActivated(row.name)

                    ToolTip.visible: row.isHeader && containsMouse && row.blurb !== ""
                    ToolTip.text: row.blurb
                    ToolTip.delay: 600
                }
            }

            ScrollBar.vertical: ScrollBar {
                active: true
            }
        }

        // Help text
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: bgDark
            radius: 5

            Text {
                anchors.fill: parent
                anchors.margins: 6
                text: sections && sections.length
                      ? "Double-click to open · click a header to fold it"
                      : "Double-click to open a tool"
                color: textMuted
                font.pixelSize: fontSizeSmall
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Component.onCompleted: {
        rebuildModel()
    }
}
