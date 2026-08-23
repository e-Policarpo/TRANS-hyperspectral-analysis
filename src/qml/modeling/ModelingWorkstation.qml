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
import Qt.labs.platform 1.1 as Platform
import TransQML 1.0
import "../components"

// The Modeling workstation: build a potential, then solve it.
//
// A workstation rather than a tool window, like the Map Editor: the model is
// a thing you keep working on, and the canvas is where the work happens.
// Features are placed by dragging them, because placing them by typing
// coordinates is how you end up with a potential nobody can picture.
Item {
    id: root

    property var parentWindow: Window.window
    function themeColor(name, fallback) {
        return (parentWindow && parentWindow[name] !== undefined
                && parentWindow[name] !== null) ? parentWindow[name] : fallback
    }
    property color bgDark: themeColor("bgDark", "#1a1a2e")
    property color bgMedium: themeColor("bgMedium", "#2a2a3e")
    property color bgLight: themeColor("bgLight", "#3a3a4e")
    property color accentPink: themeColor("accentPink", "#F5A9B8")
    property color accentBlue: themeColor("accentBlue", "#5BCEFA")
    property color accentPurple: themeColor("accentPurple", "#9B4F96")
    property color textLight: themeColor("textLight", "#ffffff")
    property color textMuted: themeColor("textMuted", "#cccccc")

    // Exposed so Main.qml can hand the backend the app reference, the same
    // way the Map Editor's is registered.
    property alias modelingBackend: modelBackend

    property bool solving: false
    property var levels: []
    property int stateIndex: -1

    Rectangle { anchors.fill: parent; color: root.bgDark }

    ModelingBackend {
        id: modelBackend

        onFeaturesChanged: {
            canvas.setFeatures(modelBackend.getFeatures())
            refreshFeatureList()
            refreshPreview()
        }

        onSelectedIndexChanged: {
            canvas.selectedIndex = modelBackend.selectedIndex
            refreshFields()
        }

        onDomainChanged: {
            canvas.setDomain(modelBackend.getDomain())
            refreshPreview()
        }

        onModeChanged: {
            kindCombo.model = modelBackend.availableKinds().map(function (k) { return k.label })
            projectionRow.visible = modelBackend.mode === "3d"
            refreshPreview()
        }

        onSolveStarted: root.solving = true

        onSolveCompleted: function (result) {
            root.solving = false
            levelModel.clear()
            root.levels = (result && result.E_eV) ? result.E_eV : []
            for (var i = 0; i < root.levels.length; i++) {
                levelModel.append({"rowIndex": i,
                                   "label": "E" + (i + 1),
                                   "energy": root.levels[i].toFixed(5)})
            }
            root.stateIndex = root.levels.length > 0 ? 0 : -1
            showState(root.stateIndex)
            refreshTunneling()
        }
    }

    ListModel { id: levelModel }
    ListModel { id: featureModel }
    ListModel { id: tunnelModel }

    // Which state sits in which feature, and how fast it leaks next door.
    // Only meaningful with more than one feature — a single well has nowhere
    // to tunnel to, and the backend says so rather than returning zeros.
    function refreshTunneling() {
        tunnelModel.clear()
        tunnelNote.text = ""
        var out = modelBackend.tunneling()
        if (!out.ok) { tunnelNote.text = out.error; return }
        for (var i = 0; i < Math.min(out.rates.length, 12); i++) {
            var r = out.rates[i]
            tunnelModel.append({
                "pair": "E" + (r.from_state + 1) + " → E" + (r.to_state + 1),
                "path": "F" + r.from_feature + " → F" + r.to_feature,
                "rate": r.rate_Hz.toExponential(2) + " Hz"
            })
        }
        tunnelNote.text = out.unlocalised > 0
            ? out.unlocalised + " state(s) are not localised in any feature"
            : ""
    }

    // The layout is built before the non-visual children are, so every
    // binding that reads the backend has to survive it being null for one
    // pass. These three are the readings the layout does.
    function isThreeD() { return modelBackend ? modelBackend.mode === "3d" : false }
    function modelSelectedIndex() { return modelBackend ? modelBackend.selectedIndex : -1 }
    function statusText() { return modelBackend ? modelBackend.status : "" }

    function kindKey(index) {
        var kinds = modelBackend.availableKinds()
        return (index >= 0 && index < kinds.length) ? kinds[index].key : ""
    }

    function projection() {
        return root.isThreeD()
               ? ["xy", "xz", "yz"][Math.max(0, projectionCombo.currentIndex)]
               : "xy"
    }

    function refreshPreview() {
        canvas.projection = projection()
        canvas.setPotential(modelBackend.previewPotential(projection(), -1.0))
    }

    function refreshFeatureList() {
        var features = modelBackend.getFeatures()
        featureModel.clear()
        for (var i = 0; i < features.length; i++) {
            featureModel.append({
                "rowIndex": i,
                "kind": features[i].kind,
                "depth": Number(features[i].V0).toFixed(3)
            })
        }
    }

    // The editable fields are per kind, so the form is rebuilt rather than
    // written out: a sphere has a radius where a box has three sides, and a
    // fixed form would either hide fields or invent them.
    function refreshFields() {
        fieldModel.clear()
        var index = modelBackend.selectedIndex
        var features = modelBackend.getFeatures()
        if (index < 0 || index >= features.length) return
        var spec = features[index]
        var fields = modelBackend.fieldsFor(spec.kind)
        for (var i = 0; i < fields.length; i++) {
            fieldModel.append({"name": fields[i].name,
                               "label": fields[i].label,
                               "value": String(spec[fields[i].name])})
        }
    }

    ListModel { id: fieldModel }

    function applyField(name, text) {
        var value = parseFloat(text)
        if (isNaN(value)) return
        var values = {}
        values[name] = value
        modelBackend.updateFeature(modelBackend.selectedIndex, values)
    }

    function showState(index) {
        root.stateIndex = index
        canvas.setDensity(index >= 0
                          ? modelBackend.densityFor(index, projection(), -1.0)
                          : ({}))
    }

    function solve() {
        var params = {
            "Nx": nxSpin.value, "Ny": nySpin.value, "Nz": nzSpin.value,
            "n_states": statesSpin.value,
            "meff": massSpin.realValue,
            "V_background_eV": backgroundSpin.realValue,
            "bc": bcCombo.currentIndex === 0 ? "dirichlet"
                                             : (bcCombo.currentIndex === 1 ? "neumann"
                                                                           : "periodic")
        }
        var cost = modelBackend.gridCost(params)
        if (cost.too_big) {
            // The backend refuses it too; saying so here saves the round trip
            // and names the number that is wrong.
            return
        }
        modelBackend.solve(params)
    }

    Component.onCompleted: {
        modelBackend.setDomain(domainXSpin.realValue, domainYSpin.realValue,
                        domainZSpin.realValue)
        kindCombo.model = modelBackend.availableKinds().map(function (k) { return k.label })
        canvas.setDomain(modelBackend.getDomain())
        canvas.setFeatures(modelBackend.getFeatures())
        refreshPreview()
    }

    Component.onDestruction: { if (canvas) canvas.cleanup() }

    // =====================================================================
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // A header strip, like the Map Editor's: it separates the workstation
        // from the tab selector directly above it, and says what this tab is
        // without spending the top of the parameter column on a paragraph.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            color: root.bgMedium

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: root.bgLight
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                Label {
                    text: "Modeling"
                    color: root.textLight
                    font.pixelSize: 16
                    font.bold: true
                }

                Label {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 0
                    text: "Place wells and barriers in a box, then solve for the " +
                          "states they hold. Drag a feature to move it; drag its " +
                          "corner to resize; double-click empty space to add one."
                    color: root.textMuted
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }

                Label {
                    text: root.statusText()
                    color: root.accentBlue
                    font.pixelSize: 11
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 8
            spacing: 8

        // ---------------- the model ----------------
        ScrollView {
            id: paramsScroll
            Layout.preferredWidth: 300
            Layout.minimumWidth: 300
            Layout.fillHeight: true
            clip: true
            // Pin the content to the viewport: a ScrollView's child
            // otherwise takes its own implicit width — the widest
            // unwrapped label — and everything past the edge is clipped.
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: paramsScroll.availableWidth
                spacing: 8

                ToolSection {
                    title: "The box"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Dimensions:"; color: textLight }
                        ToolComboBox {
                            id: modeCombo
                            Layout.fillWidth: true
                            model: ["2D — a plane", "3D — a volume"]
                            onCurrentIndexChanged: {
                                // Switching starts a new model: a 2D feature
                                // has no meaning in a 3D box. The id rather
                                // than a property of the root: `model` inside
                                // a ComboBox is the combo's own.
                                modelBackend.mode = currentIndex === 1 ? "3d" : "2d"
                            }
                        }

                        Label { text: "Lx (nm):"; color: textLight }
                        ToolSpinBox {
                            id: domainXSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            onValueChanged: modelBackend.setDomain(realValue, domainYSpin.realValue,
                                                            domainZSpin.realValue)
                        }

                        Label { text: "Ly (nm):"; color: textLight }
                        ToolSpinBox {
                            id: domainYSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            onValueChanged: modelBackend.setDomain(domainXSpin.realValue, realValue,
                                                            domainZSpin.realValue)
                        }

                        Label {
                            text: "Lz (nm):"
                            color: root.isThreeD() ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: domainZSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            enabled: root.isThreeD()
                            onValueChanged: modelBackend.setDomain(domainXSpin.realValue,
                                                            domainYSpin.realValue, realValue)
                        }

                        RowLayout {
                            id: projectionRow
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: root.isThreeD()

                            Label { text: "Showing:"; color: textLight }
                            ToolComboBox {
                                id: projectionCombo
                                Layout.fillWidth: true
                                model: ["XY (from above)", "XZ (from the side)",
                                        "YZ (from the front)"]
                                onCurrentIndexChanged: {
                                    refreshPreview()
                                    showState(root.stateIndex)
                                }
                            }
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: root.isThreeD()
                            text: "A volume is edited one plane at a time: a drag " +
                                  "moves the two coordinates you can see and leaves " +
                                  "the third where it was."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Features"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true

                            ToolComboBox {
                                id: kindCombo
                                Layout.fillWidth: true
                                model: []
                            }
                            Button {
                                text: "Add"
                                onClicked: {
                                    var domain = modelBackend.getDomain()
                                    modelBackend.addFeature(kindKey(kindCombo.currentIndex),
                                                     domain[0] / 2, domain[1] / 2)
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 120
                            color: bgDark
                            border.color: bgLight
                            radius: 4

                            ListView {
                                id: featureList
                                anchors.fill: parent
                                anchors.margins: 4
                                clip: true
                                model: featureModel

                                delegate: Rectangle {
                                    width: featureList.width
                                    height: 22
                                    radius: 3
                                    color: index === root.modelSelectedIndex() ? root.accentPink
                                                                         : "transparent"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 6
                                        anchors.rightMargin: 6

                                        Label {
                                            text: "F" + index + "  " + kind
                                            color: index === root.modelSelected()
                                                   ? root.bgDark : root.textLight
                                            font.pixelSize: 11
                                        }
                                        Item { Layout.fillWidth: true }
                                        Label {
                                            text: depth + " eV"
                                            color: index === root.modelSelected()
                                                   ? root.bgDark : root.textMuted
                                            font.pixelSize: 10
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: root.selectFeature(index)
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            Button {
                                text: "Duplicate"
                                enabled: root.modelSelectedIndex() >= 0
                                onClicked: modelBackend.duplicateFeature(modelBackend.selectedIndex)
                            }
                            Button {
                                text: "Remove"
                                enabled: root.modelSelectedIndex() >= 0
                                onClicked: modelBackend.removeFeature(modelBackend.selectedIndex)
                            }
                            Item { Layout.fillWidth: true }
                            Button {
                                text: "Clear"
                                enabled: featureModel.count > 0
                                onClicked: modelBackend.clearFeatures()
                            }
                        }
                    }
                }

                ToolSection {
                    title: "Selected feature"
                    visible: fieldModel.count > 0

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 2

                        Repeater {
                            model: fieldModel

                            RowLayout {
                                Layout.fillWidth: true

                                Label {
                                    text: label
                                    color: root.textLight
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 110
                                }
                                TextField {
                                    Layout.fillWidth: true
                                    text: value
                                    color: root.textLight
                                    font.pixelSize: 11
                                    background: Rectangle {
                                        color: root.bgDark
                                        border.color: root.bgLight
                                        radius: 3
                                    }
                                    onEditingFinished: root.applyField(name, text)
                                }
                            }
                        }
                    }
                }

                ToolSection {
                    title: "Solve"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Nx:"; color: textLight }
                        ToolSpinBox { id: nxSpin; from: 8; to: 600; value: 80 }

                        Label { text: "Ny:"; color: textLight }
                        ToolSpinBox { id: nySpin; from: 8; to: 600; value: 80 }

                        Label {
                            text: "Nz:"
                            color: root.isThreeD() ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: nzSpin
                            from: 6; to: 200; value: 24
                            enabled: root.isThreeD()
                        }

                        Label { text: "States:"; color: textLight }
                        ToolSpinBox { id: statesSpin; from: 1; to: 40; value: 6 }

                        Label { text: "m*:"; color: textLight }
                        ToolSpinBox {
                            id: massSpin
                            from: 1; to: 100000; value: 670; stepSize: 10; decimals: 4
                        }

                        Label { text: "Background (eV):"; color: textLight }
                        ToolSpinBox {
                            id: backgroundSpin
                            from: -100000; to: 100000; value: 0; stepSize: 50; decimals: 3
                        }

                        Label { text: "Boundary:"; color: textLight }
                        ToolComboBox {
                            id: bcCombo
                            Layout.fillWidth: true
                            model: ["Dirichlet (hard walls)", "Neumann", "Periodic"]
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: {
                                if (!modelBackend) return ""
                                var cost = modelBackend.gridCost({"Nx": nxSpin.value,
                                                           "Ny": nySpin.value,
                                                           "Nz": nzSpin.value})
                                return cost.points.toLocaleString(Qt.locale("en_GB"), "f", 0)
                                       + " grid points"
                                       + (cost.too_big
                                          ? " — past the limit, coarsen the grid"
                                          : (root.isThreeD()
                                             ? " (3D cost is the product of the three)"
                                             : ""))
                            }
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Tunnelling"
                    visible: tunnelModel.count > 0 || tunnelNote.text !== ""

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 2

                        Label {
                            id: tunnelNote
                            Layout.fillWidth: true
                            text: ""
                            font.pixelSize: 10
                            color: root.textMuted
                            wrapMode: Text.Wrap
                        }

                        Repeater {
                            model: tunnelModel

                            RowLayout {
                                Layout.fillWidth: true

                                Label {
                                    text: pair
                                    color: root.textLight
                                    font.pixelSize: 10
                                    Layout.preferredWidth: 70
                                }
                                Label {
                                    text: path
                                    color: root.textMuted
                                    font.pixelSize: 10
                                    Layout.preferredWidth: 70
                                }
                                Label {
                                    text: rate
                                    color: root.accentBlue
                                    font.pixelSize: 10
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: tunnelModel.count > 0
                            text: "WKB rates along the line between two features' " +
                                  "centres. They span orders of magnitude — read one " +
                                  "against another, not on its own."
                            font.pixelSize: 10
                            color: root.textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }


                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: root.solving ? "Solving…" : "Solve"
                        enabled: !root.solving
                        highlighted: true
                        onClicked: root.solve()
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "Save…"
                        onClicked: saveDialog.open()
                    }
                    Button {
                        text: "Load…"
                        onClicked: loadDialog.open()
                    }
                }
            }
        }

        // ---------------- the model, drawn ----------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 6

            PotentialCanvas {
                id: canvas
                Layout.fillWidth: true
                Layout.fillHeight: true
                backgroundColor: root.bgDark
                foregroundColor: root.textMuted

                onFeatureSelected: function (index) { root.selectFeature(index) }

                onFeatureMoved: function (index, u, v) {
                    modelBackend.moveFeature(index, u, v, root.projection())
                }

                onFeatureResized: function (index, du, dv) {
                    modelBackend.resizeFeature(index, du, dv, root.projection())
                }

                onFeatureAdded: function (u, v) {
                    modelBackend.addFeature(root.kindKey(kindCombo.currentIndex), u, v)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                color: bgMedium
                border.color: bgLight
                radius: 4

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 2

                    Label {
                        text: root.levels.length > 0
                              ? "States — the selected one is contoured over the model"
                              : "No states yet: place features and solve"
                        color: textMuted
                        font.pixelSize: 10
                    }

                    ListView {
                        id: levelList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        orientation: ListView.Horizontal
                        spacing: 4
                        model: levelModel

                        delegate: Rectangle {
                            width: 120
                            height: levelList.height
                            radius: 3
                            color: index === root.stateIndex ? root.accentPink : root.bgDark
                            border.color: root.bgLight

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 1

                                Label {
                                    text: label
                                    color: index === root.stateIndex ? root.bgDark
                                                                     : root.textMuted
                                    font.pixelSize: 11
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                Label {
                                    text: energy + " eV"
                                    color: index === root.stateIndex ? root.bgDark
                                                                     : root.textLight
                                    font.pixelSize: 11
                                    Layout.alignment: Qt.AlignHCenter
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.showState(index)
                            }
                        }
                    }
                }
            }
        }
    }

    }

    // Kept as functions so the delegates above do not each need a reference
    // to the backend — a delegate's `model` is the ListView's, not this one.
    function modelSelected() { return root.modelSelectedIndex() }
    function selectFeature(index) { if (modelBackend) modelBackend.selectedIndex = index }

    // A model is a box and a list of features — text, and small. Saving it
    // beside the project rather than inside it keeps a model portable
    // between projects, which is how they actually get reused.
    Platform.FileDialog {
        id: saveDialog
        title: "Save model"
        nameFilters: ["Model files (*.json)"]
        fileMode: Platform.FileDialog.SaveFile
        onAccepted: modelBackend.saveModel(root.localPath(file))
    }

    Platform.FileDialog {
        id: loadDialog
        title: "Load model"
        nameFilters: ["Model files (*.json)"]
        fileMode: Platform.FileDialog.OpenFile
        onAccepted: modelBackend.loadModel(root.localPath(file))
    }

    // Qt hands back a URL; everything on the Python side takes a path. The
    // prefix is three slashes on Windows and two elsewhere, which is why
    // this is not a substring of fixed length.
    function localPath(fileUrl) {
        var path = fileUrl.toString()
        if (path.startsWith("file:///")) {
            return path.charAt(9) === ":" ? path.substring(8) : path.substring(7)
        }
        return path.startsWith("file://") ? path.substring(7) : path
    }
}
