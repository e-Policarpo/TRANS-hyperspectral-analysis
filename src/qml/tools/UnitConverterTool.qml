/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * Contact: eduardapolicarpo.fisica@gmail.com
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"
import "../map_editor/Fmt.js" as Fmt

// Unit Converter (formerly Spectral Axis Converter). Three things, all over
// a whole selection of datasets at once:
//
//  1. Relabel — say what the numbers already are (units, quantity names)
//     without touching them. In place.
//  2. Convert axis — nm ↔ eV ↔ cm⁻¹ ↔ Raman shift. The values change, so a
//     new dataset is produced.
//  3. Set values — a formula for the axis and/or every spectrum, previewed
//     before it runs (qtiplot / Origin "Set Column Values", aware of the
//     spectral layout). New datasets, or in place when asked.
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    property bool datasetDropActive: false

    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color successColor: (parentWindow && parentWindow.successColor !== undefined) ? parentWindow.successColor : Theme.successColor
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // The native style paints these light, which is unreadable here.
    component Section: GroupBox {
        id: sectionRoot
        Layout.fillWidth: true
        topPadding: 28
        background: Rectangle {
            y: sectionRoot.topPadding - 24
            width: parent.width
            height: parent.height - sectionRoot.topPadding + 24
            color: root.bgMedium
            border.color: root.bgLight
            border.width: 1
            radius: 4
        }
        label: Text {
            text: sectionRoot.title
            color: root.accentPink
            font.bold: true
            font.pixelSize: 12
            padding: 4
        }
    }

    component Field: TextField {
        id: fieldRoot
        Layout.fillWidth: true
        color: root.textLight
        placeholderTextColor: root.textMuted
        selectionColor: root.accentBlue
        font.family: "Menlo, Consolas, monospace"
        background: Rectangle {
            implicitHeight: 30
            color: root.bgDark
            border.color: fieldRoot.activeFocus ? root.accentBlue : root.bgLight
            border.width: 1
            radius: 4
        }
    }

    readonly property var axisUnitOptions: [
        { label: "Wavelength (nm)",        unit: "nm",          needsExcitation: false },
        { label: "Energy (eV)",            unit: "eV",          needsExcitation: false },
        { label: "Wavenumber (cm⁻¹)",       unit: "cm-1",        needsExcitation: false },
        { label: "Raman shift (cm⁻¹)",      unit: "raman_cm-1",  needsExcitation: true  }
    ]
    function selectedAxisUnit() { return axisUnitOptions[axisUnitCombo.currentIndex] }

    // Common labels offered in the unit boxes; anything else can be typed.
    readonly property var xUnitSuggestions: ["V", "mV", "nm", "eV", "meV", "cm-1", "raman_cm-1", "s", "Hz", "µm"]
    readonly property var yUnitSuggestions: ["A", "nA", "pA", "S", "nS", "a.u.", "counts", "V", "nm", "%"]

    property string previewName: ""

    // ---------------------------------------------------------------------

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
        updateCurrent()
    }

    function updateCurrent() {
        var picks = datasetList.selectedDatasets
        previewName = picks.length > 0 ? picks[0] : ""
        if (!previewName) {
            currentLabel.text = "Select one or more datasets."
            return
        }
        var info = backend.getDatasetInfo(previewName)
        if (!info || !info.type) { currentLabel.text = ""; return }
        var rng = (info.x_min !== undefined)
            ? "  ·  " + Fmt.sci(info.x_min, 4) + " … " + Fmt.sci(info.x_max, 4) : ""
        currentLabel.text = (picks.length > 1 ? picks.length + " datasets; showing " : "") +
            previewName + "\n" +
            "x: " + info.independent_var + (info.x_unit ? " [" + info.x_unit + "]" : " [no unit]") + rng + "\n" +
            "y: " + info.num_spectra + " spectra" + (info.y_unit ? " [" + info.y_unit + "]" : " [no unit]") +
            ", " + info.num_points + " samples"
        queuePreview()
    }

    Timer {
        id: previewTimer
        interval: 250
        repeat: false
        onTriggered: root.updatePreview()
    }
    function queuePreview() { previewTimer.restart() }

    ListModel { id: previewModel }

    function updatePreview() {
        previewModel.clear()
        if (modeTabs.currentIndex !== 2 || !previewName) {
            previewStatus.text = ""
            return
        }
        var r = backend.previewFormula(previewName, xFormulaField.text, yFormulaField.text, 14)
        if (!r || !r.ok) {
            previewStatus.text = r && r.error ? "⚠ " + r.error : "Preview unavailable"
            previewStatus.color = accentMagenta
            return
        }
        for (var i = 0; i < r.rows.length; i++) {
            var row = r.rows[i]
            previewModel.append({ idx: row[0], x0: Fmt.sci(row[1], 5), x1: Fmt.sci(row[2], 5),
                                  y0: Fmt.sci(row[3], 5), y1: Fmt.sci(row[4], 5) })
        }
        var txt = "x: " + (r.x_range.length ? Fmt.sci(r.x_range[0], 4) + " … " + Fmt.sci(r.x_range[1], 4) : "—") +
                  "  →  " + (r.new_x_range.length ? Fmt.sci(r.new_x_range[0], 4) + " … " + Fmt.sci(r.new_x_range[1], 4) : "—") +
                  "\ny: " + (r.y_range.length ? Fmt.sci(r.y_range[0], 4) + " … " + Fmt.sci(r.y_range[1], 4) : "—") +
                  "  →  " + (r.new_y_range.length ? Fmt.sci(r.new_y_range[0], 4) + " … " + Fmt.sci(r.new_y_range[1], 4) : "—") +
                  "   (" + r.n_spectra + " spectra × " + r.n_samples + " samples; first spectrum shown)"
        if (r.non_finite > 0)
            txt += "\n⚠ " + r.non_finite + " value(s) come out NaN or infinite"
        previewStatus.text = txt
        previewStatus.color = r.non_finite > 0 ? accentMagenta : textMuted
    }

    function applyRelabel() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return
        var n = backend.relabelDatasets(picks, {
            "x_unit": xUnitField.editText,
            "y_unit": yUnitField.editText,
            "x_name": xNameField.text,
            "y_name": yNameField.text
        })
        statusLabel.text = n > 0 ? "Relabelled " + n + " dataset(s) in place — the data are unchanged."
                                 : "Nothing to change — fill in at least one field."
        statusLabel.color = n > 0 ? successColor : accentMagenta
        updateCurrent()
    }

    function applyAxisConvert() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return
        var sel = selectedAxisUnit()
        var lam = sel.needsExcitation ? parseFloat(excitationField.text) : 0.0
        statusLabel.text = "Converting..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("axis_convert", picks, {
            "target_unit": sel.unit,
            "excitation_nm": isNaN(lam) ? 0.0 : lam
        })
    }

    function applyFormula() {
        var picks = datasetList.selectedDatasets
        if (picks.length === 0) return
        if (xFormulaField.text.trim() === "" && yFormulaField.text.trim() === "") {
            statusLabel.text = "Enter a formula for x, for y, or both."
            statusLabel.color = accentMagenta
            return
        }
        statusLabel.text = replaceCheck.checked ? "Replacing values in place..." : "Creating datasets..."
        statusLabel.color = accentBlue
        root.runningTaskName = backend.runToolOnDatasets("unit_formula", picks, {
            "x_formula": xFormulaField.text,
            "y_formula": yFormulaField.text,
            "x_unit": fxUnitField.editText,
            "y_unit": fyUnitField.editText,
            "x_name": fxNameField.text,
            "y_name": fyNameField.text,
            "replace": replaceCheck.checked
        })
    }

    Component.onCompleted: refreshDatasets()

    Connections {
        target: backend
        function onDataLoaded(name) { refreshDatasets() }
        function onToolCompleted(toolName, path) {
            if (toolName === "Unit Converter") {
                root.runningTaskName = ""
                statusLabel.text = "Done — see the project browser (" + path + ")."
                statusLabel.color = successColor
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Unit Converter") >= 0 || title.indexOf("Conversion") >= 0) {
                root.runningTaskName = ""
                statusLabel.text = "Error: " + message
                statusLabel.color = accentMagenta
            }
        }
        // A cancelled task reaches neither of the two handlers above, so
        // without this the panel goes on saying "Converting...".
        function onOperationCancelled(name) {
            if (name !== root.runningTaskName) return
            root.runningTaskName = ""
            statusLabel.text = "Cancelled"
            statusLabel.color = textMuted
        }
    }

    // =====================================================================

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        ScrollView {
            id: leftScroll
            SplitView.preferredWidth: 420
            SplitView.minimumWidth: 360
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: leftScroll.availableWidth
                spacing: 8

                Label {
                    text: "Unit Converter"
                    font.pixelSize: 18
                    font.bold: true
                    color: textLight
                }

                Label {
                    text: "Say what the numbers are, change the axis unit, or set the values " +
                          "by formula — across every selected dataset at once."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    color: accentPurple
                }

                Section {
                    title: "Datasets"
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        DatasetMultiSelect {
                            id: datasetList
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                            model: backend.getDatasetList()

                            bgColor: root.bgDark
                            borderColorNormal: root.datasetDropActive ? accentBlue : bgLight
                            borderColorFocus: accentPink
                            textColor: textLight
                            textMutedColor: textMuted
                            selectionColor: accentPink
                            onSelectionChanged: updateCurrent()
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
                                text: root.datasetDropActive
                                      ? "Drop to add to the selection"
                                      : "…or drag datasets here from the project browser"
                                font.pixelSize: 10
                                color: root.datasetDropActive ? accentBlue : textMuted
                                elide: Text.ElideRight
                            }
                            ToolButton {
                                text: "Refresh list"
                                flat: true
                                font.pixelSize: 10
                                onClicked: root.refreshDatasets()
                            }
                        }

                        Label {
                            id: currentLabel
                            Layout.fillWidth: true
                            text: ""
                            font.pixelSize: 10
                            font.family: "Menlo, Consolas, monospace"
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                TabBar {
                    id: modeTabs
                    Layout.fillWidth: true
                    onCurrentIndexChanged: { statusLabel.text = ""; queuePreview() }
                    background: Rectangle { color: root.bgMedium; radius: 4 }

                    component ModeTab: TabButton {
                        id: tabRoot
                        contentItem: Text {
                            text: tabRoot.text
                            color: tabRoot.checked ? root.bgDark : root.textLight
                            font.bold: tabRoot.checked
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            implicitHeight: 30
                            radius: 4
                            color: tabRoot.checked ? root.accentPink : "transparent"
                        }
                    }
                    ModeTab { text: "Relabel" }
                    ModeTab { text: "Convert axis" }
                    ModeTab { text: "Set values" }
                }

                // ---- 1. Relabel -------------------------------------------
                Section {
                    title: "Relabel — data unchanged, applied in place"
                    visible: modeTabs.currentIndex === 0
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "x unit:"; color: textLight }
                        ComboBox {
                            id: xUnitField
                            Layout.fillWidth: true
                            editable: true
                            model: xUnitSuggestions
                            editText: ""
                            Component.onCompleted: editText = ""
                        }

                        Label { text: "x name:"; color: textLight }
                        Field { id: xNameField; placeholderText: "e.g. Bias, Wavelength (leave blank to keep)" }

                        Label { text: "y unit:"; color: textLight }
                        ComboBox {
                            id: yUnitField
                            Layout.fillWidth: true
                            editable: true
                            model: yUnitSuggestions
                            Component.onCompleted: editText = ""
                        }

                        Label { text: "y quantity:"; color: textLight }
                        Field { id: yNameField; placeholderText: "e.g. dI/dV, Current, Intensity" }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Use this when a file was loaded with the wrong unit or none: " +
                                  "the values are what the instrument wrote, and this records " +
                                  "what they are. Blank fields are left as they are. Exports " +
                                  "and axis labels pick the new units up immediately."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                // ---- 2. Convert axis --------------------------------------
                Section {
                    title: "Convert axis — new dataset per input"
                    visible: modeTabs.currentIndex === 1
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        ToolComboBox {
                            id: axisUnitCombo
                            Layout.fillWidth: true
                            model: axisUnitOptions.map(function(o) { return o.label })
                            currentIndex: 1
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Excitation λ (nm):"
                                color: selectedAxisUnit().needsExcitation ? textLight : textMuted
                                Layout.preferredWidth: 130
                            }
                            Field {
                                id: excitationField
                                text: "532"
                                enabled: selectedAxisUnit().needsExcitation
                                validator: DoubleValidator { bottom: 0.0; decimals: 4; notation: DoubleValidator.StandardNotation }
                                placeholderText: "e.g. 532, 633, 785"
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: "The source unit is read from each dataset's metadata (set it with " +
                                  "Relabel if it is missing). nm ↔ eV ↔ cm⁻¹ are exact reciprocals; " +
                                  "Raman shift needs the laser line. The result is '<name> (<unit>)'."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                // ---- 3. Set values ----------------------------------------
                Section {
                    title: "Set values by formula"
                    visible: modeTabs.currentIndex === 2
                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "x ="; color: textLight; font.family: "Menlo, Consolas, monospace" }
                        Field {
                            id: xFormulaField
                            placeholderText: "e.g. x * 1e3   (blank keeps the axis)"
                            onTextChanged: queuePreview()
                        }

                        Label { text: "y ="; color: textLight; font.family: "Menlo, Consolas, monospace" }
                        Field {
                            id: yFormulaField
                            placeholderText: "e.g. y / 1e-9,   y - min(y),   log10(abs(y))"
                            onTextChanged: queuePreview()
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "x is the axis, y every spectrum at once (x broadcasts), i the " +
                                  "sample index. Both formulas see the ORIGINAL x and y. " +
                                  "Functions: sqrt log log10 exp abs sin cos tan clip where " +
                                  "min max mean median std sum cumsum gradient … " +
                                  "Constants: pi e h hbar c kB q hc_eVnm. ^ works as power."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label { text: "new x unit:"; color: textLight }
                        ComboBox {
                            id: fxUnitField
                            Layout.fillWidth: true
                            editable: true
                            model: xUnitSuggestions
                            Component.onCompleted: editText = ""
                        }
                        Label { text: "new x name:"; color: textLight }
                        Field { id: fxNameField; placeholderText: "blank keeps the current name" }

                        Label { text: "new y unit:"; color: textLight }
                        ComboBox {
                            id: fyUnitField
                            Layout.fillWidth: true
                            editable: true
                            model: yUnitSuggestions
                            Component.onCompleted: editText = ""
                        }
                        Label { text: "new y quantity:"; color: textLight }
                        Field { id: fyNameField; placeholderText: "blank keeps the current one" }

                        CheckBox {
                            id: replaceCheck
                            Layout.columnSpan: 2
                            text: "Replace the originals in place (otherwise '<name> · x=…, y=…' is created)"
                            checked: false
                            contentItem: Text {
                                text: replaceCheck.text
                                color: textMuted
                                font.pixelSize: 10
                                leftPadding: replaceCheck.indicator.width + replaceCheck.spacing
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                Item { Layout.preferredHeight: 4 }
            }
        }

        // ---- right: preview ----------------------------------------------
        ColumnLayout {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 320
            spacing: 6

            Label {
                text: modeTabs.currentIndex === 2 ? "Preview — before / after (first spectrum)"
                    : modeTabs.currentIndex === 1 ? "Axis conversion"
                    : "Relabel"
                font.bold: true
                color: accentPink
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: bgMedium
                border.color: bgLight
                border.width: 1
                radius: 4

                // Formula preview table
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    visible: modeTabs.currentIndex === 2
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "#";       color: textMuted; font.pixelSize: 10; Layout.preferredWidth: 40 }
                        Text { text: "x";       color: textMuted; font.pixelSize: 10; Layout.fillWidth: true }
                        Text { text: "x'";      color: accentBlue; font.pixelSize: 10; Layout.fillWidth: true }
                        Text { text: "y";       color: textMuted; font.pixelSize: 10; Layout.fillWidth: true }
                        Text { text: "y'";      color: accentBlue; font.pixelSize: 10; Layout.fillWidth: true }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: borderColor }

                    ListView {
                        id: previewView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: previewModel
                        delegate: RowLayout {
                            width: previewView.width
                            spacing: 8
                            Text { text: model.idx; color: textMuted; font.pixelSize: 11; font.family: "Menlo, Consolas, monospace"; Layout.preferredWidth: 40 }
                            Text { text: model.x0; color: textLight; font.pixelSize: 11; font.family: "Menlo, Consolas, monospace"; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: model.x1; color: accentBlue; font.pixelSize: 11; font.family: "Menlo, Consolas, monospace"; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: model.y0; color: textLight; font.pixelSize: 11; font.family: "Menlo, Consolas, monospace"; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: model.y1; color: accentBlue; font.pixelSize: 11; font.family: "Menlo, Consolas, monospace"; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                        ScrollIndicator.vertical: ScrollIndicator { }
                    }

                    Label {
                        id: previewStatus
                        Layout.fillWidth: true
                        text: ""
                        font.pixelSize: 10
                        font.family: "Menlo, Consolas, monospace"
                        color: textMuted
                        wrapMode: Text.Wrap
                    }
                }

                Label {
                    anchors.fill: parent
                    anchors.margins: 10
                    visible: modeTabs.currentIndex !== 2
                    wrapMode: Text.Wrap
                    color: textMuted
                    font.pixelSize: 11
                    text: modeTabs.currentIndex === 0
                        ? "Relabelling edits the metadata of every selected dataset in place. " +
                          "Nothing is copied and no value changes — only what the axis and the " +
                          "spectra are said to be, which is what exports, axis labels and the " +
                          "axis conversion read.\n\nCurrent selection:\n" + currentLabel.text
                        : "Each selected dataset gets a converted copy named '<name> (<unit>)'. " +
                          "The axis is recomputed and the spectra reordered so the axis stays " +
                          "increasing; the values themselves are unchanged.\n\nCurrent selection:\n" +
                          currentLabel.text
                }
            }

            Label {
                id: statusLabel
                Layout.fillWidth: true
                text: ""
                color: textMuted
                wrapMode: Text.Wrap
                visible: text !== ""
            }

            RowLayout {
                Layout.fillWidth: true

                Button {
                    id: applyButton
                    text: {
                        var n = datasetList.selectedDatasets.length
                        var suffix = n > 1 ? " (" + n + ")" : ""
                        return modeTabs.currentIndex === 0 ? "Relabel" + suffix
                             : modeTabs.currentIndex === 1 ? "Convert" + suffix
                             : (replaceCheck.checked ? "Replace values" : "Apply formula") + suffix
                    }
                    enabled: datasetList.selectedDatasets.length > 0 &&
                             (modeTabs.currentIndex !== 1 || !selectedAxisUnit().needsExcitation ||
                              parseFloat(excitationField.text) > 0)
                    onClicked: {
                        if (modeTabs.currentIndex === 0) applyRelabel()
                        else if (modeTabs.currentIndex === 1) applyAxisConvert()
                        else applyFormula()
                    }
                    contentItem: Text {
                        text: applyButton.text
                        color: applyButton.enabled ? root.bgDark : root.textMuted
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 160
                        implicitHeight: 34
                        radius: 4
                        color: !applyButton.enabled ? root.bgMedium
                             : applyButton.pressed ? root.accentMagenta : accentPink
                        border.color: applyButton.enabled ? accentPink : root.bgLight
                        border.width: 1
                    }
                }

                ToolButton {
                    text: "Cancel"
                    visible: modeTabs.currentIndex !== 0
                    onClicked: backend.cancelCurrentOperation()
                }

                Item { Layout.fillWidth: true }

                Button {
                    id: closeButton
                    text: "Close"
                    contentItem: Text {
                        text: closeButton.text
                        color: textLight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        implicitWidth: 90
                        implicitHeight: 34
                        radius: 4
                        color: closeButton.pressed ? bgLight : bgMedium
                        border.color: bgLight
                        border.width: 1
                    }
                    onClicked: {
                        if (root.closeWindow) { root.closeWindow() }
                        else { var win = Window.window; if (win) win.close() }
                    }
                }
            }
        }
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
