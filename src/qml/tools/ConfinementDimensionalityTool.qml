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

// Confinement Dimensionality: is this 0D, 1D or 2D — and is the tail the
// sample or the thermometer?
//
// Two measurements per spectrum. The band edge is located as the BREAKPOINT
// between the steep in-gap tail and the shallower regime outside it, because
// a single exponential arm cannot give one: in ln g = c - |V - V0|/E0 the
// pair (c, V0) is exactly degenerate. And the states are ranked against the
// dimensionless level ladders of five geometries — ratios that do not depend
// on the object's size, on the effective mass, or on how badly the
// measurement was broadened, because a symmetric kernel preserves feature
// positions even where it destroys onset shapes.
//
// Temperature is the parameter that matters most, which is why it is first
// and why the panel says what it buys. Without it nothing can be called
// resolution-limited, and a curve at the thermal ceiling is a picture of the
// Fermi function rather than of the sample.
Item {
    id: root
    property var closeWindow: null

    // Dropping datasets from the project browser onto the window adds them to
    // the selection; declaring these two makes it a drop target.
    property bool datasetDropActive: false
    function acceptDatasetDrop(names) {
        datasetList.addToSelection(names)
        updateDatasetInfo()
    }

    property var parentWindow: Window.window
    // Each colour is resolved explicitly and named as a literal rather than
    // looked up by string: a subscript is not something QML can register as a
    // binding dependency, so a themeColor(name) helper evaluates once and
    // never updates, and the tool stays dark inside a light window.
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted
    property color accentMagenta: (parentWindow && parentWindow.accentMagenta !== undefined) ? parentWindow.accentMagenta : Theme.accentMagenta
    property color borderColor: (parentWindow && parentWindow.borderColor !== undefined) ? parentWindow.borderColor : Theme.borderColor

    property int spectrumCount: 0
    property bool running: false

    Rectangle { anchors.fill: parent; color: root.bgDark; z: -1 }

    // ---------------------------------------------------------------------
    // Resolution, live. The whole point of asking for a temperature.
    // ---------------------------------------------------------------------

    readonly property real kBoltzEv: 8.617333262e-5
    readonly property real temperatureK: tempSpin.realValue
    // FWHM of -df/dE is 4 ln(1 + sqrt 2) k_B T, not the 3.5251 usually quoted.
    readonly property real thermalFwhm: temperatureK > 0
        ? 3.5254943480781717 * kBoltzEv * temperatureK : NaN
    // The lock-in convolves dI/dV with a semi-ellipse whose FWHM is exactly
    // sqrt(3) * V_mod for a ZERO-TO-PEAK amplitude. Instruments disagree about
    // which they report, and getting it wrong is a 40% error in the resolution.
    readonly property real modFactor: modCombo.currentIndex === 0 ? 1.7320508075688772
                                    : modCombo.currentIndex === 1 ? 2.449489742783178
                                                                  : 0.8660254037844386
    readonly property real modFwhm: modFactor * modSpin.realValue
    readonly property real totalFwhm: temperatureK > 0
        ? Math.sqrt(thermalFwhm * thermalFwhm + modFwhm * modFwhm) : NaN
    // A thermally broadened edge can never fall faster than this.
    readonly property real slopeCeiling: temperatureK > 0
        ? 1.0 / (Math.LN10 * kBoltzEv * temperatureK) : NaN

    function resolutionText() {
        if (!(temperatureK > 0))
            return "No temperature: the tail energies are still measured, but " +
                   "nothing can be called resolution-limited."
        var txt = "Resolution " + (totalFwhm * 1000).toFixed(1) + " meV" +
                  "  ·  ceiling " + slopeCeiling.toFixed(1) + " decades/V"
        if (modFwhm < 0.25 * thermalFwhm)
            txt += "\nThermally limited — the modulation contributes nothing here."
        else
            txt += "\nModulation contributes " + (modFwhm * 1000).toFixed(1) +
                   " meV of the total."
        return txt
    }

    function analysisParams() {
        return {
            "temperature_k": tempSpin.realValue,
            "v_mod": modSpin.realValue,
            "mod_convention": ["zero_to_peak", "rms", "peak_to_peak"][modCombo.currentIndex],
            "n_kt": nKtSpin.realValue,
            "max_skips": maxSkipsSpin.value,
            "use_edge_as_offset": edgeOffsetCheck.checked,
            "height": heightSpin.realValue,
            "height_mode": "noise",
            "baseline": "arpls"
        }
    }

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        updateDatasetInfo()
    }

    function updateDatasetInfo() {
        var picked = datasetList.selectedDatasets
        if (!picked || picked.length === 0) { root.spectrumCount = 0; return }
        var info = backend.getDatasetInfo(picked[0])
        root.spectrumCount = (info && info.num_spectra) ? info.num_spectra : 0
    }

    function runAnalysis() {
        var picked = datasetList.selectedDatasets
        if (!picked || picked.length === 0) return
        root.running = true
        statusLabel.text = "Fitting " + root.spectrumCount + " spectra…"
        resultLabel.text = ""
        backend.runToolOnDatasets("confinement_dimensionality", picked,
                                  analysisParams())
    }

    Connections {
        target: backend
        function onDataLoaded(name) { datasetList.model = backend.getDatasetList() }

        function onToolCompleted(toolName, output) {
            if (toolName !== "Confinement Dimensionality") return
            root.running = false
            statusLabel.text = "Done — the table is in the project browser."
            // The whole-set verdicts are properties of the SET and cannot be
            // columns, so they arrive on the status line and would otherwise
            // go unread.
            resultLabel.text = backend.status || ""
        }
    }

    Component.onCompleted: refreshDatasets()

    // ---------------------------------------------------------------------

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        ScrollView {
            id: paramsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            // Pin the content to the viewport: a ScrollView's child otherwise
            // takes its own implicit width — the widest unwrapped label — and
            // everything past the edge is clipped.
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: paramsScroll.availableWidth
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: "Fits each spectrum's band edge and ranks the confinement " +
                          "geometry from its level ratios. The ratios are independent " +
                          "of size, effective mass and broadening — which is what makes " +
                          "them readable at all on a warm, disordered sample."
                    wrapMode: Text.Wrap
                    color: accentPurple
                }

                ToolSection {
                    title: "Datasets"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        DatasetMultiSelect {
                            id: datasetList
                            Layout.fillWidth: true
                            Layout.preferredHeight: 118
                            visibleRows: 4
                            model: []

                            bgColor: bgDark
                            borderColorNormal: root.datasetDropActive ? accentBlue
                                                                      : accentPurple
                            borderColorFocus: accentPink
                            textColor: textLight
                            textMutedColor: textMuted
                            selectionColor: accentPink

                            onSelectionChanged: updateDatasetInfo()
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: {
                                if (datasetList.selectedDatasets.length > 1)
                                    return datasetList.selectedDatasets.length +
                                           " datasets — analysed one after another"
                                if (root.spectrumCount > 0)
                                    return root.spectrumCount + " spectra"
                                return root.datasetDropActive
                                       ? "Drop to add to the selection"
                                       : "Pick a dataset — or drag one here from " +
                                         "the project browser"
                            }
                            font.pixelSize: 10
                            color: root.datasetDropActive ? accentBlue : textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Measurement conditions"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2

                            Label { text: "Temperature (K):"; color: textLight }
                            ToolSpinBox {
                                id: tempSpin
                                from: 0; to: 100000; value: 9400; stepSize: 100; decimals: 2
                            }

                            Label { text: "Modulation V_mod (V):"; color: textLight }
                            ToolSpinBox {
                                id: modSpin
                                from: 0; to: 5000; value: 0; stepSize: 5; decimals: 4
                            }

                            Label { text: "Amplitude convention:"; color: textLight }
                            ToolComboBox {
                                id: modCombo
                                Layout.fillWidth: true
                                model: ["Zero-to-peak", "RMS", "Peak-to-peak"]
                                currentIndex: 0
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: root.resolutionText()
                            font.pixelSize: 10
                            color: (root.temperatureK > 0) ? accentBlue : accentMagenta
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "The convention is not cosmetic: the lock-in kernel's " +
                                  "FWHM is sqrt(3)·V_mod zero-to-peak but sqrt(6)·V_rms, " +
                                  "so picking the wrong one is a 40% error in the " +
                                  "resolution. Check what your instrument reports."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Band-edge fit"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2

                            Label { text: "Exclude below (× k_B T):"; color: textLight }
                            ToolSpinBox {
                                id: nKtSpin
                                from: 0; to: 2000; value: 300; stepSize: 25; decimals: 2
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "Near zero bias the curve is rounded by the thermal " +
                                  "kernel, so that window is dropped before fitting. " +
                                  "The band edge is the breakpoint between the two " +
                                  "slope regimes — and no edge is reported at all when " +
                                  "the regimes cannot be told apart, because a " +
                                  "segmented fit always finds a best split even on a " +
                                  "featureless curve."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ToolSection {
                    title: "Geometry ranking"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2

                            Label { text: "Peak threshold (× σ):"; color: textLight }
                            ToolSpinBox {
                                id: heightSpin
                                from: 50; to: 2000; value: 200; stepSize: 25; decimals: 2
                            }

                            Label { text: "Unresolved levels allowed:"; color: textLight }
                            ToolSpinBox {
                                id: maxSkipsSpin
                                from: 0; to: 6; value: 2; stepSize: 1; decimals: 0
                            }
                        }

                        ToolCheckBox {
                            id: edgeOffsetCheck
                            text: "Fix the offset to the measured band edge"
                            checked: false
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "Fixing it buys back a degree of freedom, so three " +
                                  "levels become two — but only do it where the edge " +
                                  "fit is trustworthy. Otherwise the offset is fitted, " +
                                  "and three levels are the minimum: with two free " +
                                  "parameters, two levels are reproduced exactly by " +
                                  "every geometry and nothing is measured."
                            font.pixelSize: 10
                            color: textMuted
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "E₂/E₁ — 1D well 4.00 · square 2D 2.50 · 2D disc 2.54 " +
                                  "· cubic 3D 2.00 · sphere 2.05. Expect most single " +
                                  "spectra to come back 'ambiguous': 1D separates " +
                                  "cleanly, 2D against 3D does not, and that answer " +
                                  "lives in the distribution across the map."
                            font.pixelSize: 10
                            color: accentPurple
                            wrapMode: Text.Wrap
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    ToolButton {
                        text: root.running ? "Analysing…" : "Analyse"
                        enabled: !root.running &&
                                 datasetList.selectedDatasets.length > 0
                        onClicked: runAnalysis()
                    }

                    ToolButton {
                        text: "Refresh"
                        enabled: !root.running
                        onClicked: refreshDatasets()
                    }
                }

                Label {
                    id: statusLabel
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: ""
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                }

                Label {
                    id: resultLabel
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: ""
                    font.pixelSize: 11
                    color: accentBlue
                    wrapMode: Text.Wrap
                }

                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    visible: resultLabel.text !== ""
                    text: "Map 'confined_dims' for the dimensionality and read it " +
                          "beside 'verdict_code' — a confident-looking dimension on an " +
                          "underdetermined pixel means nothing. 'e0_neg' is the " +
                          "disorder amplitude and 'v_edge_neg' the local band edge."
                    font.pixelSize: 10
                    color: textMuted
                    wrapMode: Text.Wrap
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
