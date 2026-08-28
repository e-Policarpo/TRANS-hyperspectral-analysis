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
import TransQML 1.0
import "../components"

// Quantum Dot Solver: 0D confinement, where the spectrum is discrete.
//
// A well confines in one or two directions and leaves continuous sub-bands
// in the rest; a dot confines in all of them, so the levels group into
// shells like an atom's and the addition energy peaks where one closes —
// the signature a Coulomb-blockade measurement shows.
Item {
    id: root
    property var closeWindow: null

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
    // The rule colour. Declared because the canvas below binds gridColor to
    // it — undeclared, that binding assigns `undefined`, which QML reports
    // once at load and then leaves the canvas on its default grid forever.
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    property var targets: []
    property var result: ({})
    property int stateIndex: 0

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // The model's key IS its coordinate system, which is why the designer's
    // 0D candidates name it directly and nothing has to be mapped.
    readonly property var modelKeys: ["spherical", "disc", "parabolic"]
    readonly property var modelLabels: [
        "Spherical — a colloidal nanocrystal",
        "Disc / lens — a flattened self-assembled dot",
        "Parabolic — an electrostatically defined dot"
    ]
    function modelKey() { return modelKeys[Math.max(0, modelCombo.currentIndex)] }

    function solverParams() {
        return {
            "model": modelKey(),
            "R_nm": radiusSpin.realValue,
            "Lz_nm": heightSpin.realValue,
            "hw_xy_meV": hwXySpin.realValue,
            "hw_z_meV": hwZSpin.realValue,
            "meff": massSpin.realValue,
            "V0_eV": barrierSpin.realValue,
            "channels": channelsSpin.value,
            "n_per_channel": perChannelSpin.value,
            "state_index": root.stateIndex,
            "charging_eV": chargingSpin.realValue,
            "targets": root.targets
        }
    }

    function solve() {
        var out = backend.solveQuantumDot(solverParams())
        root.result = out
        levelModel.clear()
        if (!out || !out.ok) {
            canvas.showMessage(out && out.error ? out.error : "Nothing solved")
            statusLabel.text = out && out.error ? out.error : "Nothing solved"
            return
        }
        for (var i = 0; i < out.levels.length; i++) {
            var level = out.levels[i]
            levelModel.append({
                "rowIndex": i,
                "label": level.label,
                "energy": level.E_eV.toFixed(5),
                "holds": level.occupancy
            })
        }
        canvas.showDot(out, root.stateIndex)

        var comparison = out.comparison || {}
        var shells = out.shells ? out.shells.length : 0
        statusLabel.text = out.levels.length + " level(s) in " + shells + " shell(s)"
            + (comparison.rrmse_pct !== undefined && !isNaN(comparison.rrmse_pct)
               ? " — " + comparison.rrmse_pct.toFixed(3) + "% against the measured levels"
               : "")
    }

    function showState(index) {
        root.stateIndex = index
        // The radial function belongs to one level, so the solve is repeated
        // for it; a dot is milliseconds, and caching every radial state would
        // cost more memory than the recompute costs time.
        solve()
    }

    function applyPending() {
        if (!parentWindow || !parentWindow.pendingSolverParams) return false
        var p = parentWindow.pendingSolverParams
        if (p.model !== undefined) {
            var index = modelKeys.indexOf(p.model)
            if (index >= 0) modelCombo.currentIndex = index
        }
        if (p.R_nm !== undefined) radiusSpin.setRealValue(p.R_nm)
        if (p.Lz_nm !== undefined) heightSpin.setRealValue(p.Lz_nm)
        if (p.hw_xy_meV !== undefined) hwXySpin.setRealValue(p.hw_xy_meV)
        if (p.hw_z_meV !== undefined) hwZSpin.setRealValue(p.hw_z_meV)
        if (p.meff !== undefined) massSpin.setRealValue(p.meff)
        if (p.V0_eV !== undefined) barrierSpin.setRealValue(p.V0_eV)
        if (p.channels !== undefined) channelsSpin.value = p.channels
        root.targets = parentWindow.pendingSolverTargets || []
        parentWindow.pendingSolverParams = null
        parentWindow.pendingSolverTargets = []
        return true
    }

    Component.onCompleted: {
        var fromDesigner = applyPending()
        solve()
        if (fromDesigner) {
            statusLabel.text = "From the designer — " + statusLabel.text
        }
    }

    Component.onDestruction: { if (canvas) canvas.cleanup() }

    ListModel { id: levelModel }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        ScrollView {
            id: paramsScroll
            Layout.preferredWidth: 320
            Layout.minimumWidth: 320
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

                Label {
                    Layout.fillWidth: true
                    text: "Confinement in every direction, so the spectrum is discrete: " +
                          "levels group into shells and the addition energy peaks where " +
                          "one closes."
                    wrapMode: Text.Wrap
                    color: accentPurple
                }

                ToolSection {
                    title: "The dot"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Model:"; color: textLight }
                        ToolComboBox {
                            id: modelCombo
                            Layout.fillWidth: true
                            model: modelLabels
                        }

                        Label {
                            text: "Radius (nm):"
                            color: modelKey() === "parabolic" ? textMuted : textLight
                        }
                        ToolSpinBox {
                            id: radiusSpin
                            from: 1; to: 100000; value: 500; stepSize: 25; decimals: 2
                            enabled: modelKey() !== "parabolic"
                        }

                        Label {
                            text: "Height Lz (nm):"
                            color: modelKey() === "disc" ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: heightSpin
                            from: 1; to: 100000; value: 300; stepSize: 25; decimals: 2
                            enabled: modelKey() === "disc"
                        }

                        Label {
                            text: "ħω_xy (meV):"
                            color: modelKey() === "parabolic" ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: hwXySpin
                            from: 1; to: 100000; value: 3000; stepSize: 100; decimals: 2
                            enabled: modelKey() === "parabolic"
                        }

                        Label {
                            text: "ħω_z (meV):"
                            color: modelKey() === "parabolic" ? textLight : textMuted
                        }
                        ToolSpinBox {
                            id: hwZSpin
                            from: 1; to: 100000; value: 10000; stepSize: 100; decimals: 2
                            enabled: modelKey() === "parabolic"
                        }

                        Label { text: "m*:"; color: textLight }
                        ToolSpinBox {
                            id: massSpin
                            from: 1; to: 100000; value: 670; stepSize: 10; decimals: 4
                        }

                        Label {
                            text: "Barrier V₀ (eV):"
                            color: modelKey() === "parabolic" ? textMuted : textLight
                        }
                        ToolSpinBox {
                            id: barrierSpin
                            from: 0; to: 100000; value: 0; stepSize: 50; decimals: 2
                            enabled: modelKey() !== "parabolic"
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: modelKey() === "parabolic"
                                  ? "A harmonic dot has no wall to be finite: the " +
                                    "confinement energies are the geometry."
                                  : "V₀ = 0 is a hard wall, and then the levels are " +
                                    "exact — the zeros of the Bessel functions. A " +
                                    "finite barrier is solved on a radial grid, and " +
                                    "states above it are not bound and not reported."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "How far to solve"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Channels:"; color: textLight }
                        ToolSpinBox {
                            id: channelsSpin
                            from: 0; to: 10; value: 3
                        }

                        Label { text: "Per channel:"; color: textLight }
                        ToolSpinBox {
                            id: perChannelSpin
                            from: 1; to: 10; value: 4
                        }

                        Label { text: "Charging (eV):"; color: textLight }
                        ToolSpinBox {
                            id: chargingSpin
                            from: 0; to: 100000; value: 0; stepSize: 10; decimals: 4
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: "Channels is l for the sphere and |m| for the disc — " +
                                  "how many angular-momentum ladders to open. The " +
                                  "charging energy shifts every addition by the same " +
                                  "amount; at 0 only the level spacings are left, and " +
                                  "the peaks are the shell closings."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Levels"

                    Rectangle {
                        anchors.fill: parent
                        color: bgDark
                        border.color: bgLight
                        radius: 4
                        implicitHeight: 170

                        ListView {
                            id: levelList
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true
                            model: levelModel

                            delegate: Rectangle {
                                width: levelList.width
                                height: 22
                                color: index === root.stateIndex ? root.accentPink
                                                                 : "transparent"
                                radius: 3

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 6
                                    spacing: 6

                                    Label {
                                        text: model.label
                                        color: index === root.stateIndex
                                               ? root.bgDark : root.textLight
                                        font.pixelSize: 11
                                    }
                                    Item { Layout.fillWidth: true }
                                    Label {
                                        text: "holds " + model.holds
                                        color: index === root.stateIndex
                                               ? root.bgDark : root.textMuted
                                        font.pixelSize: 10
                                    }
                                    Label {
                                        text: model.energy + " eV"
                                        color: index === root.stateIndex
                                               ? root.bgDark : root.accentBlue
                                        font.pixelSize: 11
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

                Label {
                    id: statusLabel
                    Layout.fillWidth: true
                    text: "Ready"
                    color: textMuted
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Solve"
                        highlighted: true
                        onClicked: root.solve()
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "Close"
                        onClicked: {
                            if (root.closeWindow) { root.closeWindow() }
                            else { var win = Window.window; if (win) win.close() }
                        }
                    }
                }
            }
        }

        SolverCanvas {
            id: canvas
            Layout.fillWidth: true
            Layout.fillHeight: true
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
        }
    }
}
