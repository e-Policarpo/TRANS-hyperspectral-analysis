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

// Quantum Well Solver: a geometry in, its levels out.
//
// The other direction from the designer. That one asks which well would
// produce a set of measured energies and answers analytically; this one
// solves a given well numerically on a grid. Running a candidate through
// here is how a real solution is told from an alias that only matched the
// arithmetic.
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

    // The measured energies a candidate was fitted to, when the window was
    // opened from the designer. Drawn across the well so the numerical
    // levels can be compared with them by eye.
    property var targets: []
    property var result: ({})
    property int stateIndex: 0

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    function solverParams() {
        return {
            "L_nm": widthSpin.realValue,
            "N": gridSpin.value,
            "n_states": statesSpin.value,
            "meff": massSpin.realValue,
            "V0_eV": barrierSpin.realValue,
            "bc": bcCombo.currentIndex === 0 ? "dirichlet"
                                             : (bcCombo.currentIndex === 1 ? "neumann"
                                                                           : "periodic"),
            "targets": root.targets
        }
    }

    function solve() {
        var out = backend.solveQuantumWell(solverParams())
        root.result = out
        levelModel.clear()
        if (!out || !out.ok) {
            canvas.showMessage(out && out.error ? out.error : "Nothing solved")
            statusLabel.text = out && out.error ? out.error : "Nothing solved"
            return
        }
        for (var i = 0; i < out.E_eV.length; i++) {
            levelModel.append({
                "rowIndex": i,
                "label": "E" + (i + 1),
                "energy": out.E_eV[i].toFixed(5)
            })
        }
        root.stateIndex = 0
        canvas.showWell(out, 0)

        var comparison = out.comparison || {}
        if (comparison.rrmse_pct !== undefined && !isNaN(comparison.rrmse_pct)) {
            statusLabel.text = out.E_eV.length + " state(s) — "
                + comparison.rrmse_pct.toFixed(3) + "% against the measured levels"
                + (comparison.covered === false
                   ? " (a target sits above the last level solved — raise States)"
                   : "")
        } else {
            statusLabel.text = out.E_eV.length + " bound state(s)"
        }
    }

    function showState(index) {
        root.stateIndex = index
        if (root.result && root.result.ok) canvas.showWell(root.result, index)
    }

    // Opened from the designer's "Simulate" button: the geometry it found,
    // handed over through the application window because WindowManager owns
    // the instantiation.
    function applyPending() {
        if (!parentWindow || !parentWindow.pendingSolverParams) return false
        var p = parentWindow.pendingSolverParams
        if (p.L_nm !== undefined) widthSpin.setRealValue(p.L_nm)
        if (p.meff !== undefined) massSpin.setRealValue(p.meff)
        if (p.V0_eV !== undefined) barrierSpin.setRealValue(p.V0_eV)
        if (p.n_states !== undefined) statesSpin.value = p.n_states
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

                Label {
                    Layout.fillWidth: true
                    text: "Solves a 1-D well on a finite-difference grid: the levels " +
                          "it really has, not the ones an analytic formula assumes."
                    wrapMode: Text.Wrap
                    color: accentPurple
                }

                ToolSection {
                    title: "The well"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Width (nm):"; color: textLight }
                        ToolSpinBox {
                            id: widthSpin
                            from: 1; to: 100000; value: 1000; stepSize: 50; decimals: 2
                        }

                        Label { text: "m*:"; color: textLight }
                        ToolSpinBox {
                            id: massSpin
                            from: 1; to: 100000; value: 670; stepSize: 10; decimals: 4
                        }

                        Label { text: "Barrier V₀ (eV):"; color: textLight }
                        ToolSpinBox {
                            id: barrierSpin
                            from: 0; to: 100000; value: 0; stepSize: 50; decimals: 2
                        }

                        Label {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            text: barrierSpin.realValue > 0
                                  ? "Finite barrier: the box is widened around the " +
                                    "well to leave room for the evanescent tail, or " +
                                    "the walls would give the box's levels instead."
                                  : "V₀ = 0 means an infinite barrier — the box walls " +
                                    "do the confining and the levels are the textbook " +
                                    "ladder."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "The grid"

                    GridLayout {
                        anchors.fill: parent
                        columns: 2

                        Label { text: "Points:"; color: textLight }
                        ToolSpinBox {
                            id: gridSpin
                            from: 64; to: 8000; value: 800; stepSize: 100
                        }

                        Label { text: "States:"; color: textLight }
                        ToolSpinBox {
                            id: statesSpin
                            from: 1; to: 40; value: 8
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
                            text: "More points is a finer answer and a slower one; the " +
                                  "error falls as the square of the spacing, so 800 is " +
                                  "already better than four decimal places on a 10 nm " +
                                  "well."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Levels"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                            color: bgDark
                            border.color: bgLight
                            radius: 4

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

                                        Label {
                                            text: model.label
                                            color: index === root.stateIndex
                                                   ? root.bgDark : root.textMuted
                                            font.pixelSize: 11
                                        }
                                        Item { Layout.fillWidth: true }
                                        Label {
                                            text: model.energy + " eV"
                                            color: index === root.stateIndex
                                                   ? root.bgDark : root.textLight
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

                        Label {
                            Layout.fillWidth: true
                            visible: root.targets.length > 0
                            text: root.targets.length + " measured level(s) drawn " +
                                  "across the well for comparison"
                            font.pixelSize: 10
                            color: accentBlue
                            wrapMode: Text.Wrap
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
