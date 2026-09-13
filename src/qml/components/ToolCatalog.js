/*
 * T.R.A.N.S. - Tools for Research and Analysis for Nano Spectroscopy
 * Made by Eduarda Policarpo, with love 🩵🩷🤍🩷🩵
 * License: GPL
 */
.pragma library

// The one list of tools the Tools menu and the tool palette are built from.
//
// Sections group by TYPE (what the tool acts on and produces) and are
// ordered by COMPLEXITY: the first sections are one-operation tools with a
// handful of knobs; the last run a whole analysis with decisions between
// its steps. `level` names that explicitly. `tabs` says which workspace tabs
// list the tool: 0 = Spectral, 1 = Hyperspectral (the Modeling tab has its
// own workstation and lists nothing).
//
// Adding a tool: one entry here, plus its file in Main.qml's toolMap.

var LEVEL_LABELS = { basic: "basic", intermediate: "intermediate", advanced: "advanced" }

var SECTIONS = [
    {
        title: "Prepare",
        level: "basic",
        blurb: "Clean and shape spectra before anything is measured on them.",
        tools: [
            { name: "Unit Converter",               tabs: [0] },
            { name: "Truncate Data",                tabs: [0] },
            { name: "Curve Smoothing",              tabs: [0] },
            { name: "Cosmic Ray Filter",            tabs: [0] },
            { name: "Subtract Detector Background", tabs: [0] },
            { name: "Filter Bad Data",              tabs: [0] },
            { name: "Average Curves",               tabs: [0] }
        ]
    },
    {
        title: "Transform",
        level: "basic",
        blurb: "One operation on every spectrum; a new dataset per input.",
        tools: [
            { name: "Derivative Calculator",        tabs: [0] },
            { name: "Curve Background Flattening",  tabs: [0] },
            { name: "Integration Utility",          tabs: [0] },
            { name: "1D FFT",                       tabs: [0] }
        ]
    },
    {
        title: "View",
        level: "basic",
        blurb: "Look, without writing anything.",
        tools: [
            { name: "Curve Plotting",               tabs: [0] }
        ]
    },
    {
        title: "Fit and features",
        level: "intermediate",
        blurb: "Reduce every spectrum to numbers: peak parameters, a feature row.",
        tools: [
            { name: "Multi-Peak Fitting",           tabs: [0] },
            { name: "Spectral Features",            tabs: [0, 1] }
        ]
    },
    {
        title: "Maps",
        level: "intermediate",
        blurb: "From spectra to spatial maps, and operations on maps and images.",
        tools: [
            { name: "Map Generator",                tabs: [0] },
            { name: "Map Discretizer",              tabs: [1] },
            { name: "Map Processing",               tabs: [1] },
            { name: "Gradient Filter",              tabs: [0, 1] }
        ]
    },
    {
        title: "Confinement",
        level: "advanced",
        blurb: "Levels, their geometry, and the physics behind them — whole analyses in one run.",
        tools: [
            { name: "Confinement Analysis",         tabs: [0, 1] },
            { name: "Confinement Dimensionality",   tabs: [0, 1] },
            { name: "Confinement Designer",         tabs: [0] },
            { name: "Line Scan Designer",           tabs: [0] },
            { name: "Quantum Well Solver",          tabs: [0] },
            { name: "Quantum Dot Solver",           tabs: [0] }
        ]
    }
]

// Sections with only the tools listed on `tab`, empty sections dropped.
function sectionsForTab(tab) {
    var out = []
    for (var i = 0; i < SECTIONS.length; i++) {
        var s = SECTIONS[i]
        var tools = []
        for (var j = 0; j < s.tools.length; j++)
            if (s.tools[j].tabs.indexOf(tab) >= 0) tools.push(s.tools[j].name)
        if (tools.length)
            out.push({ title: s.title, level: s.level, blurb: s.blurb, tools: tools })
    }
    return out
}

// Flat list of tool names for `tab`, in section order.
function toolsForTab(tab) {
    var names = []
    var secs = sectionsForTab(tab)
    for (var i = 0; i < secs.length; i++)
        names = names.concat(secs[i].tools)
    return names
}

// Every tool, whichever tab, in section order — for the menu.
function allEntries() {
    var out = []
    for (var i = 0; i < SECTIONS.length; i++)
        for (var j = 0; j < SECTIONS[i].tools.length; j++)
            out.push({ section: SECTIONS[i].title, level: SECTIONS[i].level,
                       name: SECTIONS[i].tools[j].name, tabs: SECTIONS[i].tools[j].tabs })
    return out
}

function isListedOnTab(name, tab) {
    for (var i = 0; i < SECTIONS.length; i++)
        for (var j = 0; j < SECTIONS[i].tools.length; j++)
            if (SECTIONS[i].tools[j].name === name)
                return SECTIONS[i].tools[j].tabs.indexOf(tab) >= 0
    return false
}

// Rows for a menu: a header per section (its `tabs` is the union of its
// tools', so a header hides when none of its tools is listed on the tab),
// then that section's tools.
function menuRows() {
    var rows = []
    for (var i = 0; i < SECTIONS.length; i++) {
        var s = SECTIONS[i]
        var tabs = []
        for (var j = 0; j < s.tools.length; j++)
            for (var t = 0; t < s.tools[j].tabs.length; t++)
                if (tabs.indexOf(s.tools[j].tabs[t]) < 0) tabs.push(s.tools[j].tabs[t])
        rows.push({ kind: "header", name: s.title, level: s.level, tabs: tabs, first: i === 0 })
        for (var k = 0; k < s.tools.length; k++)
            rows.push({ kind: "tool", name: s.tools[k].name, level: "", tabs: s.tools[k].tabs, first: false })
    }
    return rows
}
