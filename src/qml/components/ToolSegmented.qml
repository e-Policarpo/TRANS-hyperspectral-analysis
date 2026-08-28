/*
 * T.R.A.N.S. — N-way segmented choice for tool panels, styled for the dark
 * palette.
 *
 * For a short, fixed set of alternatives that are looked at constantly: a
 * ComboBox costs two clicks and hides the options that were not picked,
 * which for something like a viewing plane means the user has to open the
 * list to remember what else there is.
 *
 * It is drawn rather than assembled out of Buttons, for the reason spelled
 * out in ToolButton: the Basic style's Button is 100 px wide whatever its
 * label says, so three in a row demand 310 px and the parameter column has
 * 291. This one is as wide as its own labels, and a caller that sets
 * Layout.fillWidth can shrink it further — the labels elide rather than the
 * control overflowing its panel.
 */
import QtQuick 2.15
import QtQuick.Window 2.15

Item {
    id: segmentedRoot

    // The labels, one per segment.
    property var model: []
    property int currentIndex: 0

    // Emitted only when a segment is pressed, never when currentIndex is
    // assigned — a caller restoring a remembered choice would otherwise
    // re-trigger the work it is restoring.
    signal activated(int index)

    // Resolved from the control itself: Window.window is an Item attached
    // property, so it cannot be read inside the QtObject. It is also null
    // for the first pass of a layout built before its window is known,
    // which is exactly what pick()'s fallbacks are there to survive.
    property ToolTheme theme: ToolTheme { win: segmentedRoot.Window.window }

    property int fontPixelSize: 12

    readonly property int count: model ? model.length : 0

    // 2 px of the container's own colour between segments. Rounded corners
    // meeting flush leave a notch of background showing at the join; a gap
    // that is there on purpose reads as a separator instead of an artefact.
    readonly property int gap: 2
    readonly property int inset: 2

    // Segments are placed from the rounded *cumulative* fraction, not from
    // width/count: three segments of 97.33 px each round to 291 px inside a
    // 292 px control, and the pixel that goes missing shows up as a seam
    // that moves as the panel is resized.
    function edgeAt(index) {
        var span = Math.max(0, segmentedRoot.width - 2 * inset)
        return Math.round(span * index / Math.max(1, count))
    }

    implicitHeight: 28
    implicitWidth: labelWidth + 2 * inset

    // Measured rather than guessed, so the control asks for the width its
    // own text needs — and no more, so it is not the child that stops a row
    // from shrinking.
    property real labelWidth: 0

    TextMetrics { id: metrics; font.pixelSize: segmentedRoot.fontPixelSize }

    function measure() {
        var total = 0
        for (var i = 0; i < count; i++) {
            metrics.text = String(model[i])
            total += metrics.width + 18 + gap
        }
        labelWidth = total
    }

    onModelChanged: measure()
    onFontPixelSizeChanged: measure()
    Component.onCompleted: measure()

    Rectangle {
        anchors.fill: parent
        radius: 5
        color: segmentedRoot.theme.bgDark
        border.color: segmentedRoot.theme.bgLight
        border.width: 1
    }

    Repeater {
        model: segmentedRoot.count

        Rectangle {
            id: segment

            readonly property bool selected: index === segmentedRoot.currentIndex
            readonly property string label: segmentedRoot.model
                                            ? String(segmentedRoot.model[index]) : ""

            x: segmentedRoot.inset + segmentedRoot.edgeAt(index)
            y: segmentedRoot.inset
            width: segmentedRoot.edgeAt(index + 1) - segmentedRoot.edgeAt(index)
                   - (index < segmentedRoot.count - 1 ? segmentedRoot.gap : 0)
            height: Math.max(0, segmentedRoot.height - 2 * segmentedRoot.inset)
            radius: 3

            // The same "this is the active one" language ToolButton uses for
            // `primary`: filled with the accent, its label in the dark
            // background colour so it stays readable against it.
            color: {
                if (!segmentedRoot.enabled)
                    return segmentedRoot.theme.bgMedium
                if (selected)
                    return hover.pressed ? Qt.darker(segmentedRoot.theme.accentBlue, 1.25)
                         : hover.containsMouse ? Qt.lighter(segmentedRoot.theme.accentBlue, 1.1)
                         : segmentedRoot.theme.accentBlue
                return hover.pressed ? segmentedRoot.theme.bgLight
                     : hover.containsMouse ? Qt.lighter(segmentedRoot.theme.bgMedium, 1.4)
                     : segmentedRoot.theme.bgMedium
            }

            Text {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                text: segment.label
                font.pixelSize: segmentedRoot.fontPixelSize
                color: !segmentedRoot.enabled ? segmentedRoot.theme.textMuted
                       : (segment.selected ? segmentedRoot.theme.bgDark
                                           : segmentedRoot.theme.textLight)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }

            MouseArea {
                id: hover
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    if (segmentedRoot.currentIndex !== index)
                        segmentedRoot.currentIndex = index
                    segmentedRoot.activated(index)
                }
            }

            Accessible.role: Accessible.RadioButton
            Accessible.name: segment.label
            Accessible.checkable: true
            Accessible.checked: segment.selected
            Accessible.onPressAction: {
                segmentedRoot.currentIndex = index
                segmentedRoot.activated(index)
            }
        }
    }
}
