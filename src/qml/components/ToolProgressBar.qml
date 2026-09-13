/*
 * T.R.A.N.S. — progress of one long-running tool, with its time estimate.
 *
 * Listens to backend.toolProgress for `toolName` only, so a panel shows its
 * own run and not the import that happens to be going on beside it. Shows
 * while a run is in flight (`active`), fills from the tool's own counts, and
 * the message carries the rate and the estimate the backend computed.
 */
import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Item {
    id: root
    property string toolName: ""
    property bool active: false
    property int current: 0
    property int total: 0
    property string message: ""

    property ToolTheme theme: ToolTheme { win: root.Window.window }

    implicitHeight: active ? column.implicitHeight : 0
    visible: active
    Layout.fillWidth: true

    function reset() { current = 0; total = 0; message = "" }

    Connections {
        target: backend
        function onToolProgress(tool, done, count, text) {
            if (tool !== root.toolName) return
            root.current = done
            root.total = count
            root.message = text
        }
    }

    ColumnLayout {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 3

        Rectangle {
            id: track
            Layout.fillWidth: true
            Layout.preferredHeight: 8
            radius: 4
            color: root.theme.bgDark
            border.color: root.theme.bgLight
            border.width: 1

            Rectangle {
                width: root.total > 0 ? Math.max(0, Math.min(1, root.current / root.total)) * (track.width - 2) : 0
                anchors.left: parent.left
                anchors.leftMargin: 1
                anchors.verticalCenter: parent.verticalCenter
                height: parent.height - 2
                radius: 3
                color: root.theme.accentBlue
                Behavior on width { NumberAnimation { duration: 150 } }
            }

            // Indeterminate shimmer until the first count arrives.
            Rectangle {
                visible: root.total === 0
                width: track.width * 0.2
                height: track.height - 2
                anchors.verticalCenter: parent.verticalCenter
                radius: 3
                color: root.theme.accentBlue
                opacity: 0.5
                SequentialAnimation on x {
                    running: root.active && root.total === 0
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: track.width * 0.8; duration: 900 }
                    NumberAnimation { from: track.width * 0.8; to: 1; duration: 900 }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.message !== "" ? root.message : "Starting…"
            color: root.theme.textMuted
            font.pixelSize: 10
            font.family: "Menlo, Consolas, monospace"
            elide: Text.ElideRight
        }
    }
}
