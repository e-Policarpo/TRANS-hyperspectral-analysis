/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Filter Bad Data Tool
 * Algorithms adapted from ststools by Rafael Reis (https://github.com/rafinhareis/ststools)
 * Made by Eduarda Policarpo
 * Contact: eduardapolicarpo.fisica@gmail.com
 * Date: January 2026
 * License: GPL
 */

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "../components"

// Filter Bad Data Tool
Item {
    id: root
    property var closeWindow: null

    // The task name the backend hands back when this panel submits a run.
    // Closing the window cancels that run BY NAME: there is one worker thread,
    // so the task in flight when a panel closes is very often somebody else's,
    // and a blind cancelCurrentOperation() would kill it.
    property string runningTaskName: ""

    // Set by WindowManager while a browser drag hovers this tool, so the
    // drop target is visible before the mouse is released.
    property bool datasetDropActive: false

    // Datasets dropped from the project browser join the selection (the tool
    // never consumes them) — see WindowManager.deliverDatasetDrop.
    function acceptDatasetDrop(names) {
        root.refreshDatasets()
        datasetList.addToSelection(names)
        datasetDropActive = false
    }

    // Theme colors
    // `Window.window`, not `ApplicationWindow.window`: a tool is hosted
    // either by the embedded window (whose root IS the ApplicationWindow) or
    // by ToolWindow, whose root is a plain Window. The ApplicationWindow
    // attached property resolves to null in the second case, and every colour
    // below then falls through to the singleton instead of following the
    // host. Window.window resolves in both.
    property var parentWindow: Window.window
    property color bgDark: (parentWindow && parentWindow.bgDark !== undefined) ? parentWindow.bgDark : Theme.bgDark
    property color bgMedium: (parentWindow && parentWindow.bgMedium !== undefined) ? parentWindow.bgMedium : Theme.bgMedium
    property color bgLight: (parentWindow && parentWindow.bgLight !== undefined) ? parentWindow.bgLight : Theme.bgLight
    property color accentPink: (parentWindow && parentWindow.accentPink !== undefined) ? parentWindow.accentPink : Theme.accentPink
    property color accentBlue: (parentWindow && parentWindow.accentBlue !== undefined) ? parentWindow.accentBlue : Theme.accentBlue
    property color accentPurple: (parentWindow && parentWindow.accentPurple !== undefined) ? parentWindow.accentPurple : Theme.accentPurple
    property color textLight: (parentWindow && parentWindow.textLight !== undefined) ? parentWindow.textLight : Theme.textLight
    property color textMuted: (parentWindow && parentWindow.textMuted !== undefined) ? parentWindow.textMuted : Theme.textMuted

    implicitWidth: 420
    implicitHeight: 640

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Label {
            text: "Filter Bad Data"
            font.pixelSize: 18
            font.bold: true
            color: textLight
        }

        Label {
            text: "Separate usable spectra from saturated, noisy, linear, periodic and featureless ones."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            Layout.minimumWidth: 0
            color: accentPurple
        }

        ToolSection {
            title: "Datasets"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                DatasetMultiSelect {
                    id: datasetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 110
                    model: backend ? backend.getDatasetList() : []

                    bgColor: bgLight
                    borderColorNormal: root.datasetDropActive ? accentBlue : accentPurple
                    borderColorFocus: accentPink
                    textColor: textLight
                    textMutedColor: textMuted
                    selectionColor: accentPink
                }

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 0
                        Layout.minimumWidth: 0
                        text: root.datasetDropActive
                              ? "Drop to add to the selection"
                              : "…or drag datasets here from the project browser"
                        font.pixelSize: 10
                        color: root.datasetDropActive ? accentBlue : textMuted
                        elide: Text.ElideRight
                    }

                    ToolButton {
                        text: "Refresh"
                        flat: true
                        font.pixelSize: 10
                        onClicked: root.refreshDatasets()
                    }
                }
            }
        }

        Connections {
            target: backend
            enabled: backend !== null
            function onDataLoaded(name) { root.refreshDatasets() }
        }

        // Scrollable so the parameter blocks stay reachable in a short window.
        ScrollView {
            id: parameterScroll
            Layout.fillWidth: true
            // Width comes from the window, never from what is inside: a long
            // line of text must wrap, not widen the tool.
            Layout.preferredWidth: 0
            Layout.minimumWidth: 0
            Layout.preferredHeight: Math.min(contentHeight, 340)
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parameterScroll.availableWidth
                spacing: 8

                ToolSection {
                    title: "Detector Weights"
                    Layout.fillWidth: true

                    GridLayout {
                        anchors.fill: parent
                        columns: 3
                        columnSpacing: 8
                        rowSpacing: 2

                        Label { text: "Saturation:"; color: textLight }
                        ToolSlider { id: satSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: satSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }

                        Label { text: "Noise:"; color: textLight }
                        ToolSlider { id: noiseSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: noiseSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }

                        Label { text: "Linear:"; color: textLight }
                        ToolSlider { id: linearSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: linearSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }

                        Label { text: "Periodic:"; color: textLight }
                        ToolSlider { id: periodicSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: periodicSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }

                        Label { text: "Partial noise:"; color: textLight }
                        ToolSlider { id: partialNoiseSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: partialNoiseSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }

                        Label { text: "Featureless:"; color: accentBlue }
                        ToolSlider { id: featurelessSlider; Layout.fillWidth: true; from: 0.0; to: 1.0; value: 1.0; stepSize: 0.05 }
                        Label { text: featurelessSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }
                    }
                }

                ToolSection {
                    title: "Quality Threshold"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent

                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Threshold:"; color: textLight }
                            ToolSlider {
                                id: thresholdSlider
                                Layout.fillWidth: true
                                from: 0.0; to: 1.0; value: 0.5; stepSize: 0.05
                            }
                            Label { text: thresholdSlider.value.toFixed(2); color: textMuted; Layout.preferredWidth: 32 }
                        }

                        Label {
                            text: "A spectrum is bad when its highest weighted score reaches this. " +
                                  "Set a weight to 0 to switch that detector off."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }
                    }
                }

                ToolSection {
                    title: "Featureless Spectra"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 4

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 8

                            Label { text: "Min structure ratio:"; color: textLight }
                            ToolSpinBox {
                                id: structureRatioSpin
                                Layout.fillWidth: true
                                from: 10; to: 200; value: 30; decimals: 1; stepSize: 5
                            }

                            Label { text: "Min coherence:"; color: textLight }
                            ToolSpinBox {
                                id: coherenceSpin
                                Layout.fillWidth: true
                                from: 1; to: 100; value: 12; decimals: 2; stepSize: 1
                            }
                        }

                        Label {
                            text: "A dI/dV curve that sits flat above the noise floor carries no LDOS, " +
                                  "but passes every other test. Two things flag it: an amplitude no larger " +
                                  "than its own noise could produce (structure ratio), and a curve that " +
                                  "wanders without ever going anywhere (coherence — a band edge scores " +
                                  "near 1, dead 1/f noise near 0.05). Raise either to filter harder."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }
                    }
                }

                ToolSection {
                    title: "Outliers"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        Label {
                            text: "⚠  For overview datasets only."
                            font.bold: true
                            color: accentPink
                        }

                        Label {
                            text: "An outlier is a curve that is sound on its own but wrong to " +
                                  "average in. That only means something for a set of repetitions " +
                                  "of the same measurement. On a line scan, where every position " +
                                  "is supposed to differ, this will call the ends of the line " +
                                  "outliers. Nothing stops you — just know what you are asking."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Compare within:"; color: textLight }
                            ToolComboBox {
                                id: outlierGroupCombo
                                Layout.fillWidth: true
                                model: ["Each point's repetitions", "The whole dataset"]
                                currentIndex: 0
                            }
                        }

                        Label {
                            text: outlierGroupCombo.currentIndex === 0
                                  ? "Curves are compared only against others taken at the same point, " +
                                    "read from the dataset's own per-spectrum metadata. A dataset that " +
                                    "records none is compared as a whole, and the report says so."
                                  : "Every curve is compared against every other. Correct only if the " +
                                    "whole dataset really is repetitions of one measurement."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }

                        // Each kind is removed on its own terms: the counter is
                        // the most that can be removed *per group* before the
                        // set stops looking like outliers and starts looking
                        // like a distribution — at which point none go.
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 3
                            columnSpacing: 8
                            rowSpacing: 2

                            ToolCheckBox {
                                id: offsetOutlierCheck
                                text: "Offset"
                                checked: false
                                Layout.columnSpan: 1
                            }
                            Label { text: "max"; color: textMuted; font.pixelSize: 10 }
                            ToolSpinBox {
                                id: offsetOutlierMax
                                from: 0; to: 999; value: 5
                                enabled: offsetOutlierCheck.checked
                                Layout.fillWidth: true
                            }

                            ToolCheckBox {
                                id: bandgapOutlierCheck
                                text: "Band gap"
                                checked: false
                            }
                            Label { text: "max"; color: textMuted; font.pixelSize: 10 }
                            ToolSpinBox {
                                id: bandgapOutlierMax
                                from: 0; to: 999; value: 5
                                enabled: bandgapOutlierCheck.checked
                                Layout.fillWidth: true
                            }

                            ToolCheckBox {
                                id: saturationOutlierCheck
                                text: "Saturation"
                                checked: false
                            }
                            Label { text: "max"; color: textMuted; font.pixelSize: 10 }
                            ToolSpinBox {
                                id: saturationOutlierMax
                                from: 0; to: 999; value: 5
                                enabled: saturationOutlierCheck.checked
                                Layout.fillWidth: true
                            }
                        }

                        Label {
                            text: "Offset — displaced across the whole sweep (a gain or zero that " +
                                  "was not the same); this is the one that wrecks an average.\n" +
                                  "Band gap — departs only over part of the sweep, e.g. an edge " +
                                  "that rises earlier. May be real physics, so it is off by default.\n" +
                                  "Saturation — covers far less bias range than the rest, because " +
                                  "the loader turned its railed samples into NaN.\n\n" +
                                  "Find more than the maximum and none are removed: that many is a " +
                                  "distribution, not a few odd curves. The report says so and asks " +
                                  "you to look by eye."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }

                        // Two columns, not four: a spin box is ~130 px wide,
                        // and four of these across do not fit the tool.
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 8
                            visible: offsetOutlierCheck.checked || bandgapOutlierCheck.checked
                                     || saturationOutlierCheck.checked

                            Label { text: "Sub-intervals:"; color: textLight }
                            ToolSpinBox {
                                id: outlierIntervalsSpin
                                from: 2; to: 64; value: 8
                                Layout.fillWidth: true
                            }
                            Label { text: "z threshold:"; color: textLight }
                            ToolSpinBox {
                                id: outlierZSpin
                                from: 10; to: 200; value: 35; decimals: 1; stepSize: 5
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                ToolSection {
                    title: "Periodic Noise Correction"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent

                        ToolCheckBox {
                            id: correctPeriodicCheck
                            text: "Correct periodic noise in good spectra"
                            checked: false
                        }

                        Label {
                            text: "Sharp FFT lines are replaced by interpolation, removing the artifact " +
                                  "from the spectra kept as good."
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            font.pixelSize: 10
                            color: textMuted
                        }
                    }
                }

                ToolSection {
                    title: "Information"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent

                        Label {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            Layout.minimumWidth: 0
                            text: "Each input dataset produces 'Good Data', 'Bad Data', 'FFT Spectra' " +
                                  "and 'Point Averages', plus a report listing every spectrum's " +
                                  "scores, its structure ratio, coherence and noise σ.\n\n" +
                                  "A spectrum with too few finite points is rejected outright, " +
                                  "whatever the weights say — there is nothing in it to measure.\n\n" +
                                  "'Point Averages' is one curve per point, each the average of the " +
                                  "repetitions that survived — with outlier filtering on, of the " +
                                  "ones that survived that too. It is skipped only when the dataset " +
                                  "records no point index, since there is then no way to tell " +
                                  "repetitions of one point from different points.\n\n" +
                                  "Select several datasets to filter them one after another."
                            wrapMode: Text.Wrap
                            font.pixelSize: 10
                            color: textMuted
                        }
                    }
                }
            }
        }

        Label {
            id: statusLabel
            text: ""
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            Layout.minimumWidth: 0
            color: accentBlue
            visible: text !== ""
        }

        RowLayout {
            Layout.fillWidth: true

            ToolButton {
                text: datasetList.selectedDatasets.length > 1
                      ? "Filter (" + datasetList.selectedDatasets.length + ")"
                      : "Filter"
                enabled: datasetList.selectedDatasets.length > 0
                primary: true
                onClicked: performFilter()
            }

            ToolButton {
                text: "Cancel"
                onClicked: backend.cancelCurrentOperation()
            }

            Item { Layout.fillWidth: true }

            ToolButton {
                text: "Close"
                onClicked: {
                    if (root.closeWindow) { root.closeWindow() } else { var win = Window.window; if (win) win.close() }
                }
            }
        }
    }

    Connections {
        target: backend
        enabled: backend !== null
        function onToolCompleted(toolName, outputPath) {
            if (toolName === "Filter Bad Data") {
                root.runningTaskName = ""
                statusLabel.text = "Filter complete. Check the project browser for output datasets. See report for details."
            }
        }
        function onErrorOccurred(title, message) {
            if (title.indexOf("Filter") >= 0) {
                root.runningTaskName = ""
                statusLabel.text = "Error: " + message
            }
        }
        // A cancelled task reaches neither of the two handlers above, so
        // without this the panel goes on saying "Filtering...".
        function onOperationCancelled(name) {
            if (name !== root.runningTaskName) return
            root.runningTaskName = ""
            statusLabel.text = "Cancelled"
        }
    }

    function refreshDatasets() {
        datasetList.model = backend.getDatasetList()
        datasetList.pruneSelection()
    }

    function performFilter() {
        var datasets = datasetList.selectedDatasets
        if (datasets.length === 0)
            return

        statusLabel.text = "Filtering..."
        console.log("Filtering bad data for:", datasets.join(", "))

        // One batch task: the datasets are processed in the order they were
        // picked, each yielding its own Good/Bad/FFT outputs and report.
        root.runningTaskName = backend.runToolOnDatasets("filter_bad_data", datasets, {
            "weight_saturation": satSlider.value,
            "weight_noise": noiseSlider.value,
            "weight_linear": linearSlider.value,
            "weight_periodic": periodicSlider.value,
            "weight_partial_noise": partialNoiseSlider.value,
            "weight_featureless": featurelessSlider.value,
            "threshold": thresholdSlider.value,
            "min_structure_ratio": structureRatioSpin.realValue,
            "min_coherence": coherenceSpin.realValue,
            "correct_periodic": correctPeriodicCheck.checked,
            "filter_offset_outliers": offsetOutlierCheck.checked,
            "filter_bandgap_outliers": bandgapOutlierCheck.checked,
            "filter_saturation_outliers": saturationOutlierCheck.checked,
            "max_offset_outliers": offsetOutlierMax.value,
            "max_bandgap_outliers": bandgapOutlierMax.value,
            "max_saturation_outliers": saturationOutlierMax.value,
            "outlier_group_by": outlierGroupCombo.currentIndex === 0 ? "point" : "dataset",
            "outlier_intervals": outlierIntervalsSpin.value,
            "outlier_z": outlierZSpin.realValue
        })
    }

    Component.onDestruction: {
        // A panel that is gone cannot show a result, so its run is abandoned
        // work — stop it. cancelOperation only fires when the named task is
        // the one running, so a stale name here is a no-op.
        if (root.runningTaskName) backend.cancelOperation(root.runningTaskName)
    }
}
