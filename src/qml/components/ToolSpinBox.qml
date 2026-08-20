/*
 * T.R.A.N.S. — editable numeric field for tool panels.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

SpinBox {
    id: spinRoot

    property ToolTheme theme: ToolTheme { win: spinRoot.Window.window }

    // Decimal places. SpinBox counts in integers, so a decimal field stores
    // value = realValue * 10^decimals and reads back through `realValue`.
    //
    // The validator MUST be replaced when decimals > 0: SpinBox's default is
    // an IntValidator, which silently drops the decimal point — typing "4.5"
    // became "45", i.e. a tenth of the intended value once scaled back.
    property int decimals: 0
    readonly property real factor: Math.pow(10, spinRoot.decimals)
    readonly property real realValue: spinRoot.value / spinRoot.factor

    function setRealValue(v) {
        spinRoot.value = Math.round(v * spinRoot.factor)
    }

    validator: spinRoot.decimals > 0 ? doubleValidator : intValidator

    property var doubleValidator: DoubleValidator {
        bottom: Math.min(spinRoot.from, spinRoot.to) / spinRoot.factor
        top: Math.max(spinRoot.from, spinRoot.to) / spinRoot.factor
        decimals: spinRoot.decimals
        notation: DoubleValidator.StandardNotation
        // "C" so the separator always matches what textFromValue writes;
        // a comma-decimal locale would otherwise reject its own output.
        locale: "C"
    }

    property var intValidator: IntValidator {
        bottom: Math.min(spinRoot.from, spinRoot.to)
        top: Math.max(spinRoot.from, spinRoot.to)
    }

    textFromValue: function(value, locale) {
        return spinRoot.decimals > 0
                ? Number(value / spinRoot.factor).toFixed(spinRoot.decimals)
                : String(value)
    }

    valueFromText: function(text, locale) {
        // Accept a comma as well: the keyboard layout may produce one even
        // though the field writes a dot.
        var parsed = Number(String(text).replace(",", "."))
        if (isNaN(parsed))
            return spinRoot.value
        return Math.round(parsed * spinRoot.factor)
    }

    editable: true

    contentItem: TextInput {
        leftPadding: 26
        rightPadding: 26
        text: spinRoot.textFromValue(spinRoot.value, spinRoot.locale)
        font: spinRoot.font
        color: spinRoot.enabled ? spinRoot.theme.textLight : spinRoot.theme.textMuted
        selectionColor: spinRoot.theme.accentBlue
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !spinRoot.editable
        validator: spinRoot.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
    }

    background: Rectangle {
        implicitWidth: 132
        color: spinRoot.theme.bgDark
        border.color: spinRoot.activeFocus ? spinRoot.theme.accentBlue : spinRoot.theme.bgLight
        border.width: 1
        radius: 4
    }

    up.indicator: Rectangle {
        x: spinRoot.width - width
        height: spinRoot.height
        implicitWidth: 24
        color: spinRoot.up.pressed ? spinRoot.theme.bgLight : spinRoot.theme.bgMedium
        border.color: spinRoot.theme.bgLight
        radius: 4
        Text {
            text: "+"
            color: spinRoot.enabled ? spinRoot.theme.textLight : spinRoot.theme.textMuted
            anchors.centerIn: parent
            font.pixelSize: 15
        }
    }

    down.indicator: Rectangle {
        height: spinRoot.height
        implicitWidth: 24
        color: spinRoot.down.pressed ? spinRoot.theme.bgLight : spinRoot.theme.bgMedium
        border.color: spinRoot.theme.bgLight
        radius: 4
        Text {
            text: "−"
            color: spinRoot.enabled ? spinRoot.theme.textLight : spinRoot.theme.textMuted
            anchors.centerIn: parent
            font.pixelSize: 15
        }
    }
}
