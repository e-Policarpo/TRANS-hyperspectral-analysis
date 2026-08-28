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
    // Each colour is resolved explicitly, and the property is named as a
    // literal rather than looked up by string.
    //
    // That distinction is the whole point. This used to read
    // parentWindow[name] inside a themeColor() helper, and a subscript is
    // something QML cannot register as a binding dependency — so the binding
    // was evaluated once and never again. Measured: switching the scheme from
    // "Just Dark Mode" to a light one moved the window's own bgDark from
    // #1a1a1a to #f5f0f8 while this tool's bgDark stayed #1a1a1a, and the
    // canvases under it stayed dark inside a light window. Naming the
    // property directly makes it a real dependency, so a scheme change
    // arrives here the moment the window sees it.
    //
    // The `!== undefined` guard stays: reading a colour the host does not
    // carry yields undefined, which lands as an invalid QColor and paints
    // text black-on-black. Theme is the fallback — a singleton nothing has to
    // locate, so it cannot be missing.
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    // The rule colour. Declared because the canvases below bind gridColor to
    // it — without the declaration that binding assigned `undefined`, which is
    // a load-time complaint and a canvas silently left on its default grid.
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    // Exposed so Main.qml can hand the backend the app reference, the same
    // way the Map Editor's is registered.
    property alias modelingBackend: modelBackend

    property bool solving: false
    property var levels: []
    property int stateIndex: -1

    // Whether the box is a volume, held as a property rather than read off
    // the backend where it is needed. The layout is built before the
    // non-visual children are, so a binding that reaches modelBackend on its
    // first pass captures nothing and then never re-evaluates — which is why
    // the mode used to be pushed into `projectionRow.visible` by hand. Every
    // `visible:` and `enabled:` in the form hangs off this instead, and it is
    // assigned where the mode actually changes.
    property bool threeD: false

    // Which of the two things the canvas area is showing: the editable model
    // (0) or the solved state (1).
    property int viewMode: 0

    // The grid the box is replaced by, and what its three counts are called
    // there. Nx is a radius on a polar grid and Ny is an angle, so a panel
    // that keeps calling them Nx and Ny is asking for a grid the user cannot
    // see. Both are assigned rather than bound: they change together, when
    // the mode or the grid does.
    property var coordOptions: []
    property var axisNames: ["Nx", "Ny", "Nz"]

    function coordsKey() {
        var index = coordsCombo ? coordsCombo.currentIndex : 0
        return (index >= 0 && index < root.coordOptions.length)
                ? root.coordOptions[index].key : "cartesian"
    }

    function refreshCoords() {
        if (!modelBackend) return
        root.coordOptions = modelBackend.availableCoords()
        if (coordsCombo) {
            coordsCombo.model = root.coordOptions.map(function (c) { return c.label })
            if (coordsCombo.currentIndex >= root.coordOptions.length)
                coordsCombo.currentIndex = 0
        }
        var names = modelBackend.gridCost({"coords": root.coordsKey()}).labels
        root.axisNames = [names[0] || "Nx", names[1] || "Ny", names[2] || "Nz"]
    }

    // Where the volume is cut, one remembered position per axis, with -1
    // meaning "never moved — put it in the middle". One number per axis
    // rather than one shared: the old app carried two separate scales for
    // precisely this reason. z and y hold separate places, and a single
    // shared number silently moves your cut when you switch plane and switch
    // back.
    property var slicePos: [-1, -1, -1]

    // The readout beside the slider, written rather than bound: it has to
    // follow the handle while a drag is in flight and the grid position the
    // backend actually cut at once one lands, and a binding covering both
    // would depend on ids that do not exist yet on the first pass.
    property string sliceAxisName: "z"
    property string sliceText: ""

    Rectangle { anchors.fill: parent; color: root.bgDark }

    // Every numeric parameter is the same shape: it fills the second column
    // of its grid, so the fields share one right edge instead of ending
    // wherever their digits happen to, and it stands as tall as the combo
    // boxes beside it — a bare SpinBox is 16 px tall here, which reads as a
    // different kind of control rather than the same form.
    component ParamSpin: ToolSpinBox {
        Layout.fillWidth: true
        Layout.preferredHeight: 30
    }

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
            // A resized box moves the walls the cut is measured between, so
            // the slider is re-ranged onto the new one before anything is
            // drawn through it.
            root.retuneSlice()
            refreshPreview()
        }

        onModeChanged: {
            root.threeD = modelBackend.mode === "3d"
            kindCombo.model = modelBackend.availableKinds().map(function (k) { return k.label })
            // A plane has no hidden axis and no states view; switching to one
            // leaves both behind.
            if (!root.threeD) root.setViewMode(0)
            // A polar grid is a 2-D idea and a spherical one is not, so the
            // choices change with the mode.
            root.refreshCoords()
            root.retuneSlice()
            refreshPreview()
        }

        onSolveStarted: root.solving = true

        // A new mode, a cleared model or a loaded one throws the last solve
        // away. Without this the ladder keeps listing energies that no
        // longer belong to anything, the Edit|States switch stays up over an
        // empty model, and the old state's contour stays drawn on the canvas.
        onResultCleared: {
            root.levels = []
            levelModel.clear()
            root.stateIndex = -1
            root.setViewMode(0)
            canvas.setDensity({})
            tunnelModel.clear()
            tunnelNote.text = ""
        }

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
            if (root.levels.length === 0) root.setViewMode(0)
            // The solved grid is the one the cuts are taken on now, so the
            // slider is re-ranged onto it — the old app re-ranged its scales
            // on every solve for the same reason.
            root.retuneSlice()
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
    function isThreeD() { return root.threeD }
    function modelSelectedIndex() { return modelBackend ? modelBackend.selectedIndex : -1 }
    function statusText() { return modelBackend ? modelBackend.status : "" }

    function kindKey(index) {
        var kinds = modelBackend.availableKinds()
        return (index >= 0 && index < kinds.length) ? kinds[index].key : ""
    }

    function projection() {
        var index = planeSegmented ? planeSegmented.currentIndex : 0
        return root.isThreeD() ? ["xy", "xz", "yz"][Math.max(0, index)] : "xy"
    }

    // The axis the shown plane does not contain: XY hides z, XZ hides y, YZ
    // hides x. It is the axis the cut is taken along.
    function hiddenAxis() {
        var plane = projection()
        return plane === "xy" ? 2 : (plane === "xz" ? 1 : 0)
    }

    function hiddenLength() {
        if (!modelBackend) return 0
        var domain = modelBackend.getDomain()
        return (domain && domain.length === 3) ? domain[hiddenAxis()] : 0
    }

    // Where to cut: the position remembered for this axis, or the middle of
    // the box while there is none. Negative in 2-D, which is already how the
    // backend is told there is no hidden axis to cut along.
    function sliceAt() {
        if (!root.threeD) return -1.0
        var remembered = root.slicePos[hiddenAxis()]
        return remembered >= 0 ? remembered : hiddenLength() / 2.0
    }

    // Re-range the slider onto whichever axis is hidden now, and put it back
    // where that axis was left. A position remembered from a larger box is
    // dropped rather than clamped: once the walls have moved, the middle is
    // the only place that still means the same thing.
    function retuneSlice() {
        root.sliceAxisName = ["x", "y", "z"][hiddenAxis()]
        var length = hiddenLength()
        if (root.slicePos[hiddenAxis()] > length) {
            var reset = root.slicePos.slice()
            reset[hiddenAxis()] = -1
            root.slicePos = reset
        }
        var position = sliceAt()
        if (sliceSlider) {
            sliceSlider.to = length > 0 ? length : 1
            sliceSlider.value = position
        }
        updateSliceText(position)
    }

    function sliceMoved(position) {
        var positions = root.slicePos.slice()
        positions[hiddenAxis()] = position
        root.slicePos = positions
        updateSliceText(position)
        // Restarted rather than merely started. A drag emits this as fast as
        // the mouse moves, and one redraw costs ~107 ms at any resolution
        // (the canvas rebuilds its whole figure per frame), so drawing every
        // step would leave the plot several redraws behind the pointer. 150 ms
        // is the resize debounce this codebase already uses and sits
        // comfortably past one redraw; restarting is what guarantees the
        // position that finally renders is the last one moved to, rather than
        // the last one that happened to fall on a tick.
        sliceTimer.restart()
    }

    function updateSliceText(position) {
        var length = hiddenLength()
        root.sliceText = Number(position).toFixed(length >= 100 ? 1 : 2) + " nm"
    }

    // The switch below keeps its own currentIndex once it has been clicked,
    // so forcing the view back has to move both.
    function setViewMode(index) {
        root.viewMode = index
        if (viewSwitch) viewSwitch.currentIndex = index
    }

    Timer {
        id: sliceTimer
        interval: 150
        repeat: false
        onTriggered: {
            root.refreshPreview()
            root.showState(root.stateIndex)
        }
    }

    function refreshPreview() {
        canvas.projection = projection()
        // The canvas sizes the grid from its own pixels: a preview built
        // coarser than the plot it is drawn on looks low-resolution however
        // smoothly its edges are interpolated.
        var preview = modelBackend.previewPotential(
                          projection(), root.sliceAt(), canvas.previewPoints())
        // The backend snaps the cut onto its own grid and reports where it
        // landed. Showing that, rather than the number under the handle,
        // keeps the readout from naming a plane that was never drawn — but
        // not mid-drag, where the handle is the thing to follow.
        if (preview && preview.slice_at !== undefined
                && (!sliceTimer || !sliceTimer.running))
            root.updateSliceText(preview.slice_at)
        canvas.setPotential(preview)
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
                          ? modelBackend.densityFor(index, projection(), root.sliceAt())
                          : ({}))
        // Only while it is the view on screen. setPlots() builds its whole
        // 2x2 figure synchronously — a 3-D scatter, three cuts, three
        // colorbars and a wireframe per feature, ~80 ms — and nothing about
        // that is deferred to paint(), so refreshing it from behind the
        // editable canvas doubles every slider settle for a picture nobody
        // is looking at. Switching to it refreshes it (see viewSwitch).
        if (statesView && root.viewMode === 1) statesView.refresh(index)
    }

    function solve() {
        var params = {
            "Nx": nxSpin.value, "Ny": nySpin.value, "Nz": nzSpin.value,
            "n_states": statesSpin.value,
            "coords": root.coordsKey(),
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
        root.threeD = modelBackend.mode === "3d"
        modelBackend.setDomain(domainXSpin.realValue, domainYSpin.realValue,
                        domainZSpin.realValue)
        kindCombo.model = modelBackend.availableKinds().map(function (k) { return k.label })
        refreshCoords()
        canvas.setDomain(modelBackend.getDomain())
        canvas.setFeatures(modelBackend.getFeatures())
        retuneSlice()
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
        //
        // The column keeps a width of its own — the sections in it are a
        // form, and a form that stretches with the window leaves a hand's
        // width between a label and the field it names. Its children are
        // written at this indentation, as the RowLayout above writes its
        // own, so that wrapping the scroll area did not reindent 350 lines.
        ColumnLayout {
            objectName: "parameterColumn"
            // A nested layout fills by default, which would hand it the
            // whole row and leave the canvas nothing.
            Layout.fillWidth: false
            Layout.preferredWidth: 320
            Layout.minimumWidth: 280
            Layout.maximumWidth: 320
            Layout.fillHeight: true
            spacing: 8

        ScrollView {
            id: paramsScroll
            Layout.fillWidth: true
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
                        ParamSpin {
                            id: domainXSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            // `value / factor`, not `realValue`: realValue
                            // is a binding on value and still holds the
                            // previous one while this handler runs, so the
                            // box was always one edit behind the field. The
                            // siblings are safe — their value did not change.
                            onValueChanged: modelBackend.setDomain(value / factor,
                                                            domainYSpin.realValue,
                                                            domainZSpin.realValue)
                        }

                        Label { text: "Ly (nm):"; color: textLight }
                        ParamSpin {
                            id: domainYSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            onValueChanged: modelBackend.setDomain(domainXSpin.realValue,
                                                            value / factor,
                                                            domainZSpin.realValue)
                        }

                        Label {
                            text: "Lz (nm):"
                            color: root.isThreeD() ? textLight : textMuted
                        }
                        ParamSpin {
                            id: domainZSpin
                            from: 10; to: 1000000; value: 2000; stepSize: 100; decimals: 2
                            enabled: root.isThreeD()
                            onValueChanged: modelBackend.setDomain(domainXSpin.realValue,
                                                            domainYSpin.realValue,
                                                            value / factor)
                        }

                        // The plane and the cut through it, together: they
                        // are one question — which slice of the volume am I
                        // looking at — and the old app asked it as one row of
                        // radio buttons and a scale beneath them. A dropdown
                        // costs two clicks and hides the planes you did not
                        // pick, on a control that is touched constantly.
                        ColumnLayout {
                            id: projectionRow
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            // These two cut the editable canvas, and only it:
                            // the states view carries its own three cut
                            // fields, so leaving them up beside it puts two
                            // slice controls on screen that disagree, the
                            // more prominent one inert.
                            visible: root.isThreeD() && root.viewMode === 0
                            spacing: 4

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Label {
                                    text: "Plane:"  // (see projectionRow)
                                    color: textLight
                                    Layout.preferredWidth: 52
                                }
                                ToolSegmented {
                                    id: planeSegmented
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 0
                                    Layout.minimumWidth: 0
                                    model: ["XY", "XZ", "YZ"]
                                    onActivated: function (index) {
                                        // Each plane hides a different axis,
                                        // so the slider is re-ranged and put
                                        // back where that axis was left
                                        // before anything is drawn.
                                        root.retuneSlice()
                                        root.refreshPreview()
                                        root.showState(root.stateIndex)
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Label {
                                    text: "Slice " + root.sliceAxisName + ":"
                                    color: textLight
                                    Layout.preferredWidth: 52
                                }
                                ToolSlider {
                                    id: sliceSlider
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 0
                                    Layout.minimumWidth: 0
                                    from: 0
                                    to: 1
                                    // `moved` rather than `valueChanged`:
                                    // re-ranging the slider writes its value,
                                    // and that must not be mistaken for the
                                    // user having chosen a cut.
                                    onMoved: root.sliceMoved(value)
                                }
                                Label {
                                    text: root.sliceText
                                    color: root.accentBlue
                                    font.pixelSize: 11
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 72
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
                            ToolButton {
                                text: "Add"
                                Layout.preferredWidth: 64
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

                        // The three share the row rather than each taking
                        // a width of its own: a row is never narrower than
                        // the sum of the children that do not fill, so
                        // fixed-width buttons are what pushed the last one
                        // off the edge of the column.
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            ToolButton {
                                text: "Duplicate"
                                enabled: root.modelSelectedIndex() >= 0
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
                                onClicked: modelBackend.duplicateFeature(modelBackend.selectedIndex)
                            }
                            ToolButton {
                                text: "Remove"
                                enabled: root.modelSelectedIndex() >= 0
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
                                onClicked: modelBackend.removeFeature(modelBackend.selectedIndex)
                            }
                            ToolButton {
                                text: "Clear"
                                enabled: featureModel.count > 0
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
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

                        Label { text: "Grid:"; color: textLight }
                        ToolComboBox {
                            id: coordsCombo
                            Layout.fillWidth: true
                            model: []
                            // A round wall is a staircase on a square grid.
                            // Solving the disc, the cylinder or the ball that
                            // is inscribed in the box puts the samples where
                            // the shape is instead — the features keep the
                            // same nm frame either way, so the same model
                            // means the same thing on both.
                            onActivated: root.refreshCoords()
                        }

                        Label { text: root.axisNames[0] + ":"; color: textLight }
                        ParamSpin { id: nxSpin; from: 8; to: 600; value: 80 }

                        Label { text: root.axisNames[1] + ":"; color: textLight }
                        ParamSpin { id: nySpin; from: 8; to: 600; value: 80 }

                        Label {
                            text: root.axisNames[2] + ":"
                            color: root.isThreeD() ? textLight : textMuted
                        }
                        ParamSpin {
                            id: nzSpin
                            from: 6; to: 200; value: 24
                            enabled: root.isThreeD()
                        }

                        Label { text: "States:"; color: textLight }
                        ParamSpin { id: statesSpin; from: 1; to: 40; value: 6 }

                        Label { text: "m*:"; color: textLight }
                        ParamSpin {
                            id: massSpin
                            from: 1; to: 100000; value: 670; stepSize: 10; decimals: 4
                        }

                        Label { text: "Background (eV):"; color: textLight }
                        ParamSpin {
                            id: backgroundSpin
                            from: -100000; to: 100000; value: 0; stepSize: 50; decimals: 3
                        }

                        // A row of its own: in the second column the name of
                        // the condition elides to "Dirichlet (hard w…", and a
                        // boundary condition you cannot read is not a choice.
                        RowLayout {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true

                            Label { text: "Boundary:"; color: textLight }
                            ToolComboBox {
                                id: bcCombo
                                Layout.fillWidth: true
                                model: ["Dirichlet (hard walls)", "Neumann", "Periodic"]
                            }
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: {
                                if (!modelBackend) return ""
                                var cost = modelBackend.gridCost({"Nx": nxSpin.value,
                                                           "Ny": nySpin.value,
                                                           "Nz": nzSpin.value,
                                                           "coords": root.coordsKey()})
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


            }
        }

        // The actions sit outside the scroll area: Solve is what the panel
        // is for, and with the selected-feature and tunnelling sections
        // both open it would otherwise be scrolled out of reach.
        RowLayout {
            objectName: "modelActions"
            Layout.fillWidth: true
            spacing: 6

            ToolButton {
                text: root.solving ? "Solving…" : "Solve"
                enabled: !root.solving
                primary: true
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                onClicked: root.solve()
            }
            ToolButton {
                text: "Save…"
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                onClicked: saveDialog.open()
            }
            ToolButton {
                text: "Load…"
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                onClicked: loadDialog.open()
            }
        }

        }

        // ---------------- the model, drawn ----------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 6

            // Edit and States swap in the same space rather than splitting
            // it. A split would halve the plot features are dragged around
            // in, and a 2x2 grid of cuts through a volume needs the whole
            // area to be worth looking at; this costs the editable canvas
            // one 28 px strip, and only once there is a solved volume to
            // switch to. Nothing is torn down either — the canvas keeps its
            // features and its selection while it is hidden.
            RowLayout {
                Layout.fillWidth: true
                visible: root.threeD && root.levels.length > 0
                spacing: 8

                ToolSegmented {
                    id: viewSwitch
                    Layout.preferredWidth: 150
                    model: ["Edit", "States"]
                    onActivated: function (index) {
                        root.viewMode = index
                        if (index === 1) statesView.refresh(root.stateIndex)
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 0
                    text: root.viewMode === 1
                          ? "The selected state, cut three ways through the box — "
                            + "and where its density actually sits."
                          : ""
                    color: root.textMuted
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                PotentialCanvas {
                    id: canvas
                    anchors.fill: parent
                    visible: root.viewMode === 0
                    backgroundColor: root.bgDark
                    foregroundColor: root.textMuted
                    // gridColor draws the spines and the gridlines. borderColor —
                    // which is what a rule IS in this scheme — and NOT bgLight.
                    // bgLight was chosen to dodge the advisory borderColor pairing,
                    // but measured on all 22 schemes bgLight-on-bgDark runs
                    // 1.12:1 to 1.54:1, so the frame was fainter than either
                    // candidate and the painted gridline came out at 1.02–1.08:1:
                    // no visible box at all, on every scheme. borderColor is the
                    // higher-contrast choice in 21 of the 22.
                    gridColor: root.borderColor
                    // The semantic scale. These four were added to FigureCanvasItem and
                    // bound at no site at all, so every canvas painted the class defaults
                    // (#5BCEFA / #2ECC71 / #FF9800 / #FF6B6B) whatever the scheme said —
                    // dark-tuned marks at 1.6:1 to 2.6:1 on a light scheme's near-white
                    // ground, and #5BCEFA is byte-identical to a series colour it is
                    // meant to be read against.
                    //
                    // They bind to the Theme singleton directly rather than through the
                    // host: these are meanings, not decoration, and no window overrides
                    // them. The canvas guards them — if a scheme's three scale colours
                    // are too close to tell apart it keeps the fixed triple instead.
                    accentColor: Theme.accentPink
                    successColor: Theme.successColor
                    warningColor: Theme.warningColor
                    errorColor: Theme.errorColor

                    onFeatureSelected: function (index) { root.selectFeature(index) }

                    onFeatureMoved: function (index, u, v) {
                        modelBackend.moveFeature(index, u, v, root.projection())
                    }

                    onFeatureResized: function (index, du, dv) {
                        modelBackend.resizeFeature(index, du, dv, root.projection())
                    }

                    onFeatureAdded: function (u, v) {
                        // With the plane, like the two handlers above it: in
                        // XZ the second coordinate is z, and taking it as y
                        // put the feature 8 nm off the cut it was drawn on.
                        modelBackend.addFeature(root.kindKey(kindCombo.currentIndex),
                                                u, v, root.projection())
                    }
                }

                StatesView {
                    id: statesView
                    anchors.fill: parent
                    visible: root.viewMode === 1
                    backend: modelBackend
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
