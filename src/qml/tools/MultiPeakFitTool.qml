/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Multi-Peak Fitting — fit a sum of Gaussians / Lorentzians / pseudo-Voigts
 * plus a polynomial baseline to one spectrum of a dataset. Backed by
 * AppBackend.multiPeakFit(...).
 *
 * Made by Eduarda Policarpo, with love
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: May 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

Item {
    id: root
    property var closeWindow: null

    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    // Map ComboBox label → backend shape string.
    readonly property var shapeOptions: [
        { label: "Gaussian",      value: "gaussian"     },
        { label: "Lorentzian",    value: "lorentzian"   },
        { label: "Pseudo-Voigt",  value: "pseudo_voigt" }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        Label {
            text: "Multi-Peak Fitting"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Detect peaks and fit a sum of Gaussian / Lorentzian /\n" +
                  "pseudo-Voigt line shapes plus a polynomial baseline.\n" +
                  "A new dataset with the fit components and residuals is created."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: accentPurple
        }

        GroupBox {
            title: "Source"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                spacing: 6

                DatasetComboBox {
                    id: datasetCombo
                    Layout.fillWidth: true
                    model: backend.getDatasetList()
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Spectrum index:"; Layout.preferredWidth: 130 }
                    SpinBox {
                        id: spectrumSpin
                        from: 0
                        to: 9999
                        value: 0
                    }
                    Label {
                        text: "(0 = first column after the axis)"
                        color: textMuted
                        font.pixelSize: 10
                    }
                }
            }
        }

        GroupBox {
            title: "Fit parameters"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Peak shape:"; Layout.preferredWidth: 130 }
                    ComboBox {
                        id: shapeCombo
                        Layout.fillWidth: true
                        model: shapeOptions.map(function(o) { return o.label })
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Max peaks (0 = auto):"; Layout.preferredWidth: 130 }
                    SpinBox {
                        id: nPeaksSpin
                        from: 0
                        to: 50
                        value: 0
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Baseline degree:"; Layout.preferredWidth: 130 }
                    SpinBox {
                        id: baselineSpin
                        from: -1
                        to: 6
                        value: 1
                    }
                    Label {
                        text: "(-1 = none, 0 = const, 1 = linear, …)"
                        color: textMuted
                        font.pixelSize: 10
                    }
                }
            }
        }

        GroupBox {
            title: "Fit summary"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ScrollView {
                anchors.fill: parent
                clip: true

                TextArea {
                    id: summaryArea
                    readOnly: true
                    text: "Run a fit to see peak parameters and R²."
                    color: textLight
                    background: Rectangle { color: bgDark }
                    font.family: "Menlo, Consolas, monospace"
                    font.pixelSize: 11
                    wrapMode: TextArea.Wrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Run Fit"
                enabled: datasetCombo.currentIndex >= 0
                highlighted: true
                onClicked: doFit()
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

    function doFit() {
        var shape = shapeOptions[shapeCombo.currentIndex].value
        summaryArea.text = "Fitting…"
        var result = backend.multiPeakFit(
            datasetCombo.currentText, shape,
            nPeaksSpin.value, baselineSpin.value,
            spectrumSpin.value
        )
        summaryArea.text = formatSummary(result)
    }

    function formatSummary(r) {
        if (!r || !r.success) {
            return "Fit failed: " + (r ? r.message : "no result")
        }
        var lines = []
        lines.push("R² = " + r.rsq.toFixed(5) + "    RSS = " + r.rss.toExponential(3))
        lines.push("")
        lines.push("Peaks (" + r.peaks.length + "):")
        for (var i = 0; i < r.peaks.length; i++) {
            var p = r.peaks[i]
            var line = "  #" + (i + 1) + "  shape=" + p.shape +
                       "  center=" + p.center.toFixed(4) +
                       "  amp=" + p.amplitude.toExponential(3) +
                       "  width=" + p.width.toFixed(4) +
                       "  FWHM=" + p.fwhm.toFixed(4)
            if (p.eta !== undefined && p.eta >= 0) {
                line += "  η=" + p.eta.toFixed(3)
            }
            lines.push(line)
        }
        if (r.baseline_coeffs && r.baseline_coeffs.length) {
            lines.push("")
            lines.push("Baseline (highest-order first):")
            lines.push("  " + r.baseline_coeffs.map(function(c) {
                return Number(c).toExponential(3)
            }).join(", "))
        }
        return lines.join("\n")
    }
}
