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

// A solved state, seen four ways at once, and the tunnelling picture beside
// it.
//
// Self-contained on purpose: the workstation mounts it and says which state
// to show, and everything else — which cut, which view, when to ask the
// backend again — is settled in here. Nothing large crosses the bridge: the
// backend sends three slices and a capped scatter, never the volume.
Item {
    id: root

    // Set by whoever mounts this — the ModelingBackend.
    property var backend: null

    // The state being shown, or -1 for "nothing solved". Remembered so a
    // slice moved by hand can ask for the same state again.
    property int stateIndex: -1

    // Which picture: "states" or "tunneling".
    property string view: "states"

    // The solved energies, in eV. The tunnelling analysis reports rates and
    // assignments but not the ladder they sit on, so these are picked up
    // from the solve below rather than required of whoever mounts this — a
    // level diagram that only appears when the caller remembered to pass a
    // list is a level diagram that is usually missing. Assignable anyway,
    // for a host that has them from somewhere else.
    property var levels: []

    property ToolTheme theme: ToolTheme { win: root.Window.window }

    // Where each cut is taken, in nm. Negative means "the middle of that
    // axis", which is the convention every slice-taking slot in the backend
    // already uses, so an untouched view asks for exactly what it did before.
    property real sliceX: -1.0
    property real sliceY: -1.0
    property real sliceZ: -1.0

    // Only a volume has a hidden axis to cut through — and until one has
    // been drawn the fields read zero, which is the face of the box rather
    // than the middle the negative default asks for. Both are why the row of
    // cut fields does not exist before the first result.
    property bool hasVolume: false

    // The API the workstation calls. Everything here has to survive being
    // called before there is a backend, before anything is solved, and with
    // an index of -1 — all three happen on the way to the first solve.
    function refresh(index) {
        root.stateIndex = index === undefined ? root.stateIndex : index
        // No backend and no solved state are the same picture: the empty,
        // themed placeholder, never a stale plot from the last model.
        if (!root.backend) {
            canvas.setPlots({})
            return
        }
        if (root.view === "tunneling") {
            refreshTunneling()
            return
        }
        if (root.stateIndex < 0) {
            canvas.setPlots({})
            return
        }
        var out = null
        try {
            out = root.backend.statePlots(root.stateIndex, root.sliceX,
                                          root.sliceY, root.sliceZ)
            // A backend that only registered the one-argument form answers
            // an over-long call with nothing rather than an error; the
            // middle of each axis is what it would have used anyway.
            if (!out)
                out = root.backend.statePlots(root.stateIndex)
        } catch (err) {
            canvas.showMessage("This build's backend has no state plots")
            return
        }
        canvas.setPlots(out || {})
        syncSlices(out)
    }

    function refreshTunneling() {
        canvas.selectedState = root.stateIndex
        var out = null
        try {
            out = root.backend.tunneling()
        } catch (err) {
            canvas.showMessage("Tunnelling analysis is unavailable")
            return
        }
        out = out || {}
        // The rate table is all the backend sends today: no ladder of
        // energies and no overlap matrix. Both panels are drawn the moment
        // they arrive — from the analysis itself, or from the level list the
        // workstation already holds, if it hands one down.
        if (out.ok && !out.E_eV && root.levels && root.levels.length > 0)
            out.E_eV = root.levels
        canvas.setTunneling(out)
    }

    // The backend snaps a requested cut to the nearest grid line and reports
    // where it landed. Showing that number rather than the one asked for is
    // what stops the field and the plot disagreeing by half a cell.
    function syncSlices(out) {
        if (!out || !out.ok)
            return
        if (out.yz && out.yz.slice_at !== undefined) {
            root.sliceX = out.yz.slice_at
            sliceXSpin.setRealValue(root.sliceX)
        }
        if (out.xz && out.xz.slice_at !== undefined) {
            root.sliceY = out.xz.slice_at
            sliceYSpin.setRealValue(root.sliceY)
        }
        if (out.xy && out.xy.slice_at !== undefined) {
            root.sliceZ = out.xy.slice_at
            sliceZSpin.setRealValue(root.sliceZ)
        }
        var domain = root.backend ? root.backend.getDomain() : null
        if (domain && domain.length >= 3) {
            sliceXSpin.to = Math.round(domain[0] * 10)
            sliceYSpin.to = Math.round(domain[1] * 10)
            sliceZSpin.to = Math.round(domain[2] * 10)
        }
        root.hasVolume = out.z_nm !== undefined && out.z_nm !== null
                         && out.z_nm.length > 0
    }

    // Which axis a field cuts. Three unlabelled boxes in a row is a puzzle
    // rather than a control.
    component CutLabel: Text {
        color: root.theme.textMuted
        font.pixelSize: 11
    }

    // `to` is replaced with the model's own size as soon as there is a
    // result; until then it is wide enough for any box someone is likely to
    // have built.
    component CutField: ToolSpinBox {
        property string axis: "x"
        decimals: 1
        from: 0
        to: 2000
        implicitWidth: 96
        implicitHeight: 30
        // valueModified, not valueChanged: only a hand on the field is a new
        // cut, and filling one in from a result is not. `value / factor`
        // rather than `realValue` — that is a binding, and it still holds the
        // previous value while this handler runs, which put every cut at zero.
        onValueModified: root.moveCut(axis, value / factor)
    }

    function moveCut(axis, nm) {
        if (axis === "x")
            root.sliceX = nm
        else if (axis === "y")
            root.sliceY = nm
        else
            root.sliceZ = nm
        sliceChanged()
    }

    // Straight from the solve, because that is the only place the energies
    // are published: `tunneling()` does not carry them, and asking the
    // backend for them one state at a time would rebuild a volume per level.
    // A new solve replaces them rather than merging — the old ladder belongs
    // to a model that no longer exists.
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onSolveCompleted(result) {
            root.levels = (result && result.E_eV) ? result.E_eV : []
            if (root.view === "tunneling")
                root.refresh(root.stateIndex)
        }
    }

    // A cut is dragged, not typed: three fields moving together would ask
    // the backend for three volumes on the way to one. Same 200 ms as the
    // other canvases in this project.
    Timer {
        id: sliceTimer
        interval: 200
        repeat: false
        onTriggered: root.refresh(root.stateIndex)
    }

    function sliceChanged() {
        if (root.hasVolume)
            sliceTimer.restart()
    }

    Rectangle { anchors.fill: parent; color: root.theme.bgDark }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            // Both views named on screen rather than hidden in a combo:
            // there are two of them and which is showing is the first thing
            // to know when reading the plot.
            ToolSegmented {
                model: ["Wavefunction", "Tunnelling"]
                currentIndex: root.view === "tunneling" ? 1 : 0
                onActivated: function (index) {
                    root.view = index === 1 ? "tunneling" : "states"
                    root.refresh(root.stateIndex)
                }
            }

            Item { Layout.fillWidth: true }

            RowLayout {
                id: sliceRow
                visible: root.view === "states" && root.hasVolume
                spacing: 4

                Text {
                    text: "Cuts (nm)"
                    color: root.theme.textMuted
                    font.pixelSize: 11
                }

                CutLabel { text: "x" }
                CutField { id: sliceXSpin; axis: "x" }
                CutLabel { text: "y" }
                CutField { id: sliceYSpin; axis: "y" }
                CutLabel { text: "z" }
                CutField { id: sliceZSpin; axis: "z" }
            }
        }

        StatesCanvas {
            id: canvas
            Layout.fillWidth: true
            Layout.fillHeight: true
            backgroundColor: root.theme.bgDark
            foregroundColor: root.theme.textMuted
            // gridColor draws the spines and the gridlines. borderColor —
            // which is what a rule IS in this scheme — and NOT bgLight.
            // bgLight was chosen to dodge the advisory borderColor pairing,
            // but measured on all 22 schemes bgLight-on-bgDark runs
            // 1.12:1 to 1.54:1, so the frame was fainter than either
            // candidate and the painted gridline came out at 1.02–1.08:1:
            // no visible box at all, on every scheme. borderColor is the
            // higher-contrast choice in 21 of the 22.
            gridColor: root.theme.borderColor
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
            mode: root.view
        }
    }

    // A figure held past its window keeps its Agg buffer alive, like every
    // other canvas here.
    Component.onDestruction: if (canvas) canvas.cleanup()
}
