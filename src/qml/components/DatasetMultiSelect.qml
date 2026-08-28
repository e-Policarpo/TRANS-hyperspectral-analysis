/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * DatasetMultiSelect - dataset list allowing several datasets to be picked
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 *
 * Ctrl/Cmd-click toggles one entry, Shift-click extends from the last one
 * clicked, a plain click selects a single entry — the usual file-list rules.
 * The picked datasets are reported in click order via `selectedDatasets`,
 * and tools process them in exactly that order.
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    // ---- API -------------------------------------------------------------
    property var model: []                 // list of dataset names
    property var selectedDatasets: []      // names, in the order they were picked
    property string placeholderText: "No datasets available"
    property int visibleRows: 5
    property bool showHeader: true

    signal selectionChanged()

    // Same knobs as DatasetComboBox so tools can theme both alike.
    // follow the scheme, which is what a control dropped into a tool
    // panel needs — these were the 2018 defaults, so an unoverridden
    // combo painted itself in a palette the app no longer has.
    property color bgColor: Theme.bgLight
    property color borderColorNormal: Theme.borderColor
    property color borderColorFocus: Theme.accentPink
    property color textColor: Theme.textLight
    property color textMutedColor: Theme.textMuted
    property color selectionColor: Theme.accentPink

    implicitHeight: layout.implicitHeight
    implicitWidth: 220

    function selectAll() {
        var all = []
        for (var i = 0; i < (root.model ? root.model.length : 0); i++)
            all.push(root.model[i])
        _apply(all)
    }

    function clearSelection() { _apply([]) }

    function setSelection(names) { _apply(names || []) }

    // Append names that aren't picked yet, keeping existing order. Used by
    // drops from the project browser, which add to the selection rather than
    // replacing it.
    function addToSelection(names) {
        if (!names || names.length === 0) return
        var current = root.selectedDatasets.slice()
        for (var i = 0; i < names.length; i++) {
            if (current.indexOf(names[i]) < 0 && _indexOfName(names[i]) >= 0)
                current.push(names[i])
        }
        _apply(current)
    }

    // Drop names that no longer exist (called after the model is refreshed),
    // so a stale pick can never be handed to a tool as a missing dataset.
    function pruneSelection() {
        var kept = []
        for (var i = 0; i < root.selectedDatasets.length; i++) {
            if (_indexOfName(root.selectedDatasets[i]) >= 0)
                kept.push(root.selectedDatasets[i])
        }
        if (kept.length !== root.selectedDatasets.length)
            _apply(kept)
    }

    // ---- internals -------------------------------------------------------
    property int _anchorIndex: -1

    function _apply(names) {
        root.selectedDatasets = names
        root.selectionChanged()
    }

    function _indexOfName(name) {
        if (!root.model) return -1
        for (var i = 0; i < root.model.length; i++)
            if (root.model[i] === name) return i
        return -1
    }

    function isSelected(name) {
        return root.selectedDatasets.indexOf(name) >= 0
    }

    function _handleClick(index, name, modifiers) {
        var current = root.selectedDatasets.slice()

        if (modifiers & (Qt.ControlModifier | Qt.MetaModifier)) {
            var at = current.indexOf(name)
            if (at >= 0) current.splice(at, 1)
            else current.push(name)
            root._anchorIndex = index
        } else if ((modifiers & Qt.ShiftModifier) && root._anchorIndex >= 0) {
            // Extend from the anchor, keeping earlier picks and list order
            // inside the range so the run order stays predictable.
            var lo = Math.min(root._anchorIndex, index)
            var hi = Math.max(root._anchorIndex, index)
            for (var i = lo; i <= hi; i++) {
                var entry = root.model[i]
                if (current.indexOf(entry) < 0) current.push(entry)
            }
        } else {
            current = [name]
            root._anchorIndex = index
        }

        _apply(current)
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            visible: root.showHeader
            spacing: 6

            Text {
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                elide: Text.ElideRight
                color: root.selectedDatasets.length > 0 ? root.textColor : root.textMutedColor
                font.pixelSize: 11
                text: {
                    var total = root.model ? root.model.length : 0
                    if (total === 0) return root.placeholderText
                    if (root.selectedDatasets.length === 0)
                        return "Select one or more (Ctrl/Cmd or Shift-click)"
                    if (root.selectedDatasets.length === 1)
                        return "1 dataset selected"
                    return root.selectedDatasets.length + " of " + total + " datasets selected"
                }
            }

            Button {
                text: "All"
                flat: true
                implicitHeight: 22
                font.pixelSize: 10
                enabled: root.model && root.model.length > 0
                onClicked: root.selectAll()
            }

            Button {
                text: "None"
                flat: true
                implicitHeight: 22
                font.pixelSize: 10
                enabled: root.selectedDatasets.length > 0
                onClicked: root.clearSelection()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 24 * root.visibleRows + 2
            color: root.bgColor
            border.color: listView.activeFocus ? root.borderColorFocus : root.borderColorNormal
            border.width: 1
            radius: 4
            clip: true

            ListView {
                id: listView
                anchors.fill: parent
                anchors.margins: 1
                model: root.model
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    id: row
                    width: ListView.view.width
                    height: 24

                    required property int index
                    required property var modelData

                    readonly property bool picked: root.isSelected(row.modelData)

                    color: row.picked ? Qt.rgba(root.selectionColor.r,
                                                root.selectionColor.g,
                                                root.selectionColor.b, 0.30)
                                      : (hover.hovered ? Qt.rgba(1, 1, 1, 0.06) : "transparent")

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        spacing: 6

                        // Run-order badge: with several datasets picked, the
                        // number is the order they will be processed in.
                        Text {
                            visible: root.selectedDatasets.length > 1 && row.picked
                            text: (root.selectedDatasets.indexOf(row.modelData) + 1) + "."
                            color: root.selectionColor
                            font.pixelSize: 10
                            font.bold: true
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            text: row.modelData
                            color: row.picked ? root.textColor : root.textMutedColor
                            font.pixelSize: 11
                            elide: Text.ElideMiddle
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    HoverHandler { id: hover }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: function(mouse) {
                            listView.forceActiveFocus()
                            root._handleClick(row.index, row.modelData, mouse.modifiers)
                        }
                    }

                    ToolTip.visible: hover.hovered && row.modelData.length > 30
                    ToolTip.text: row.modelData
                    ToolTip.delay: 600
                }
            }

            Text {
                anchors.centerIn: parent
                visible: !root.model || root.model.length === 0
                text: root.placeholderText
                color: root.textMutedColor
                font.pixelSize: 11
            }
        }
    }
}
