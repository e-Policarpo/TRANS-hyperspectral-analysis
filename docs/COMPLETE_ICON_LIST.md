# Complete Icon List for TRANS-QML

This is a comprehensive list of **every UI element** in your application that can have an icon.

---

## 📋 Menu Bar

### File Menu (9 items)
- [ ] **File Menu** itself (menu bar item)
- [ ] **New Project** - Create new project
- [ ] **Open Project...** - Open existing project
- [ ] **Save Project** - Save current project
- [ ] **Save Project As...** - Save project with new name
- [ ] **Import Measurement...** - Import data from file
- [ ] **New Table** - Create new table window
- [ ] **New Graph** - Create new plot window
- [ ] **Exit** - Quit application

**Suggested icons:**
```
menu/file-menu.png (folder or file icon)
menu/file-new.png (document with plus)
menu/file-open.png (folder opening)
menu/file-save.png (floppy disk or save icon)
menu/file-save-as.png (floppy disk with arrow)
menu/import.png (arrow into folder)
menu/table-new.png (table grid)
menu/graph-new.png (line chart)
menu/exit.png (door with arrow or X)
```

### Tools Menu (16+ items)
- [ ] **Tools Menu** itself (menu bar item)

**STS Analysis Tools (9 tools):**
- [ ] **1D FFT** - Fast Fourier Transform
- [ ] **Curve Smoothing** - Smooth spectral curves
- [ ] **Derivative Calculator** - Calculate derivatives
- [ ] **Curve Fitting** - Fit curves to data
- [ ] **Integration Utility** - Integrate curves
- [ ] **Map Generator** - Generate spatial maps
- [ ] **Spatial Average** - Spatial averaging
- [ ] **Truncate Data** - Truncate dataset
- [ ] **Curve Analysis** - Analyze curves

**SNOM Analysis Tools (10 tools):**
- [ ] **1D FFT** - Fast Fourier Transform
- [ ] **2D FFT** - 2D Fast Fourier Transform
- [ ] **Curve Smoothing** - Smooth spectral curves
- [ ] **Image Smoothing** - Smooth images
- [ ] **Derivative Calculator** - Calculate derivatives
- [ ] **Gradient Filter** - Apply gradient filter
- [ ] **Integration Utility** - Integrate curves
- [ ] **Map Generator** - Generate spatial maps
- [ ] **Truncate Data** - Truncate dataset
- [ ] **Curve Analysis** - Analyze curves

**Map Editor Tools (4 tools):**
- [ ] **2D FFT** - 2D Fast Fourier Transform
- [ ] **Image Smoothing** - Smooth images
- [ ] **Gradient Filter** - Apply gradient filter
- [ ] **Map Discretizer** - Discretize maps

**Suggested icons:**
```
menu/tools-menu.png (wrench or toolbox)
menu/fft-1d.png (sine wave)
menu/fft-2d.png (2D wave pattern)
menu/smooth-curve.png (smooth curve)
menu/smooth-image.png (blur effect)
menu/derivative.png (df/dx symbol)
menu/gradient.png (gradient arrow)
menu/fitting.png (curve with fit line)
menu/integration.png (integral symbol)
menu/map-generator.png (grid or heatmap)
menu/spatial-average.png (averaging icon)
menu/truncate.png (scissors)
menu/curve-analysis.png (magnifying glass on curve)
menu/map-discretizer.png (pixelated grid)
menu/peak-indexing.png (peaks with markers)
```

### Workflows Menu (5+ items)
- [ ] **Workflows Menu** itself (menu bar item)
- [ ] **New Workflow...** - Create new workflow
- [ ] **STS Analysis Workflow** - STS workflow preset
- [ ] **SNOM Analysis Workflow** - SNOM workflow preset
- [ ] **Project Workflows** - Section header (disabled)
- [ ] **(Dynamic workflow list)** - Each saved workflow
- [ ] **Load Workflow...** - Load from file
- [ ] **Refresh List** - Refresh workflow list

**Suggested icons:**
```
menu/workflows-menu.png (flowchart)
menu/workflow-new.png (flowchart with plus)
menu/workflow-sts.png (STS workflow icon)
menu/workflow-snom.png (SNOM workflow icon)
menu/workflow-load.png (flowchart with arrow)
menu/workflow-refresh.png (circular arrows)
```

### Window Menu (11 items)
- [ ] **Window Menu** itself (menu bar item)
- [ ] **Toggle Project Browser** - Show/hide browser
- [ ] **Toggle Debug Console** - Show/hide console
- [ ] **Save Layout...** - Save current layout
- [ ] **Load Layout...** - Load saved layout
- [ ] **Reset Layout** - Reset to default
- [ ] **Cascade Windows** - Arrange windows cascaded
- [ ] **Tile Windows** - Arrange windows tiled
- [ ] **Open Tools** - Section header (disabled)
- [ ] **(Dynamic tool list)** - Each open tool window

**Suggested icons:**
```
menu/window-menu.png (window icon)
menu/browser-toggle.png (sidebar icon)
menu/console-toggle.png (terminal icon)
menu/layout-save.png (save layout)
menu/layout-load.png (load layout)
menu/layout-reset.png (reset icon)
menu/cascade.png (cascaded windows)
menu/tile.png (tiled grid)
```

### Help Menu (3 items)
- [ ] **Help Menu** itself (menu bar item)
- [ ] **Documentation** - Open docs
- [ ] **About** - About dialog

**Suggested icons:**
```
menu/help-menu.png (question mark)
menu/documentation.png (book or document)
menu/about.png (info icon or app logo)
```

---

## 🔄 Workflow Editor (NEW)

### Workflow Toolbox
The workflow toolbox now shows port type indicators next to each tool name.
These are colored circles (not icons) rendered programmatically with golden ratio spacing.

**Port Type Colors:**
- Dataset (blue `#66b3ff`)
- Flat Data (light cyan `#99ddff`)
- Image (pink `#ff66b2`)
- Map (orange `#ff9966`)
- Table (green `#66ff99`)
- Number (orange `#ffaa66`)
- String (purple `#aa66ff`)
- Intervals (yellow `#ffff66`)
- Peaks (pink `#ff6699`)
- Any (gray `#cccccc`)

### Workflow Node Actions
- [ ] **Run Workflow** - Execute workflow
- [ ] **Save Workflow** - Save workflow to file
- [ ] **Delete Node** - Delete selected node
- [ ] **Duplicate Node** - Duplicate node
- [ ] **Connect Nodes** - Create connection
- [ ] **Disconnect** - Remove connection

**Suggested icons:**
```
workflow/run.png (play button)
workflow/save.png (floppy disk)
workflow/delete-node.png (node with X)
workflow/duplicate.png (two nodes)
workflow/connect.png (link icon)
workflow/disconnect.png (broken link)
```

---

## 🔧 Toolbar / Workspace Area

### Workspace Toolbar
- [ ] **Workspace** label (could have icon)
- [ ] **Dock Position Selector** dropdown (left/right/top/bottom)

**Suggested icons:**
```
toolbar/workspace.png (grid layout)
toolbar/dock-left.png (dock to left)
toolbar/dock-right.png (dock to right)
toolbar/dock-top.png (dock to top)
toolbar/dock-bottom.png (dock to bottom)
```

### Tab Bar (3 tabs)
- [ ] **STS Analysis** tab
- [ ] **SNOM Analysis** tab
- [ ] **Map Editor** tab

**Suggested icons:**
```
toolbar/tab-sts.png (spectroscopy icon)
toolbar/tab-snom.png (near-field icon)
toolbar/tab-map.png (map/heatmap icon)
```

---

## 📁 Project Browser

### Browser Header
- [ ] **Project Browser** title (could have icon)
- [ ] **Refresh Button** - Refresh browser

**Suggested icons:**
```
general/browser.png (folder tree)
general/refresh.png (circular arrows)
```

### Search Box
- [ ] **Search field** - Could have search icon inside

**Suggested icons:**
```
general/search.png (magnifying glass)
```

### Browser Categories
Each category in the browser can have an icon:

- [ ] **Datasets** - Dataset category
- [ ] **Tables** - Open tables category
- [ ] **Graphs** - Open graphs category
- [ ] **Maps** - Generated maps category
- [ ] **Outputs** - Output files category

**Suggested icons:**
```
general/folder-datasets.png (folder with data)
general/folder-tables.png (folder with table)
general/folder-graphs.png (folder with chart)
general/folder-maps.png (folder with map)
general/folder-outputs.png (folder with file)
```

### Browser Items
Individual items in each category:

- [ ] **Dataset item** - Individual dataset
- [ ] **Table item** - Individual table window
- [ ] **Graph item** - Individual graph window
- [ ] **Map item** - Individual map
- [ ] **Output item** - Individual output file

**Suggested icons:**
```
general/dataset.png (data icon)
general/table.png (table grid)
general/graph.png (line chart)
general/map.png (heatmap)
general/output.png (document/file)
```

### Browser Item Actions
Context menu or hover actions for items:

- [ ] **Open** - Open item
- [ ] **Rename** - Rename item
- [ ] **Delete** - Delete item
- [ ] **Export** - Export item
- [ ] **Duplicate** - Duplicate item

**Suggested icons:**
```
actions/open.png (folder opening)
actions/rename.png (pencil)
actions/delete.png (trash can)
actions/export.png (arrow out of box)
actions/duplicate.png (two documents)
```

---

## 📊 Status Bar

### Status Indicators
- [ ] **Success/Ready** - System ready
- [ ] **Error** - Error occurred
- [ ] **Warning** - Warning state
- [ ] **Info/Busy** - Processing/busy
- [ ] **Loading** - Loading indicator

**Suggested icons:**
```
status/success.png (green checkmark)
status/error.png (red X or exclamation)
status/warning.png (yellow warning triangle)
status/info.png (blue info icon)
status/loading.png (spinner or hourglass)
```

### Status Actions
- [ ] **Cancel Operation** - Cancel current task
- [ ] **View Details** - Show operation details

**Suggested icons:**
```
status/cancel.png (X or stop sign)
status/details.png (list or menu)
```

---

## 🪟 Dialogs

### Import Measurement Dialog
- [ ] **Import Dialog** title
- [ ] **Browse** button
- [ ] **OK** button
- [ ] **Cancel** button

**Suggested icons:**
```
dialog/import.png (arrow into folder)
dialog/browse.png (folder)
dialog/ok.png (checkmark)
dialog/cancel.png (X)
```

### Save/Load Layout Dialogs
- [ ] **Save Layout** dialog
- [ ] **Load Layout** dialog
- [ ] **Layout list items** - Each saved layout

**Suggested icons:**
```
dialog/save-layout.png (save icon)
dialog/load-layout.png (load icon)
dialog/layout-item.png (layout icon)
```

### About Dialog
- [ ] **About** dialog title
- [ ] **Application logo** (large icon)

**Suggested icons:**
```
dialog/about.png (info or app logo)
general/app-logo.png (application logo, 64x64 or larger)
```

### Error Dialog
- [ ] **Error** dialog title

**Suggested icons:**
```
dialog/error.png (error icon)
```

### Progress Dialog
- [ ] **Progress** dialog title
- [ ] **Loading** indicator

**Suggested icons:**
```
dialog/progress.png (progress bar or spinner)
```

---

## 🛠️ Tool Windows

Each tool window can have icons in its title bar and buttons:

### Generic Tool Window Elements
- [ ] **Tool Window** title/icon
- [ ] **Minimize** button
- [ ] **Maximize** button
- [ ] **Close** button
- [ ] **Dock/Undock** button

**Suggested icons:**
```
window/tool.png (wrench or tool icon)
window/minimize.png (minus or down arrow)
window/maximize.png (square or expand arrows)
window/close.png (X)
window/dock.png (pin icon)
window/undock.png (unpin icon)
```

### Tool-Specific Buttons
- [ ] **Apply** - Apply operation
- [ ] **Reset** - Reset to defaults
- [ ] **Preview** - Preview result
- [ ] **Export** - Export result
- [ ] **Settings** - Tool settings
- [ ] **Help** - Tool help

**Suggested icons:**
```
tool/apply.png (checkmark or play)
tool/reset.png (circular arrow)
tool/preview.png (eye icon)
tool/export.png (arrow out)
tool/settings.png (gear)
tool/help.png (question mark)
```

### Individual Tool Icons

**1D FFT Tool:**
- [ ] Tool window icon
- [ ] Apply FFT button
- [ ] Inverse FFT button

**Curve Smoothing Tool:**
- [ ] Tool window icon
- [ ] Apply smoothing button
- [ ] Preview button

**Derivative Tool:**
- [ ] Tool window icon
- [ ] Calculate derivative button
- [ ] Order selector (1st, 2nd, etc.)

**Curve Fitting Tool:**
- [ ] Tool window icon
- [ ] Fit button
- [ ] Function selector icons

**Integration Tool:**
- [ ] Tool window icon
- [ ] Integrate button
- [ ] Set limits button

**Map Generator Tool:**
- [ ] Tool window icon
- [ ] Generate map button
- [ ] Parameter selector

**Spatial Average Tool:**
- [ ] Tool window icon
- [ ] Calculate average button

**Truncate Tool:**
- [ ] Tool window icon
- [ ] Truncate button
- [ ] Set range button

**Curve Analysis Tool:**
- [ ] Tool window icon
- [ ] Analyze button
- [ ] Export results button

**2D FFT Tool:**
- [ ] Tool window icon
- [ ] Apply 2D FFT button

**Image Smoothing Tool:**
- [ ] Tool window icon
- [ ] Apply smoothing button
- [ ] Filter type selector

**Gradient Filter Tool:**
- [ ] Tool window icon
- [ ] Apply gradient button
- [ ] Direction selector

**Map Discretizer Tool:**
- [ ] Tool window icon
- [ ] Discretize button

**Peak Indexing Tool:**
- [ ] Tool window icon
- [ ] Find peaks button
- [ ] Index peaks button

**Suggested tool-specific icons:**
```
tools/fft-1d.png (sine wave)
tools/fft-2d.png (2D wave)
tools/smooth-curve.png (smooth line)
tools/smooth-image.png (blur)
tools/derivative.png (d/dx)
tools/gradient.png (gradient arrow)
tools/fitting.png (curve fit)
tools/integration.png (integral)
tools/map-gen.png (grid generation)
tools/average.png (averaging)
tools/truncate.png (scissors)
tools/analysis.png (magnifying glass)
tools/discretizer.png (pixelate)
tools/peak-index.png (peaks)
```

---

## 📈 Plot/Graph Windows

### Enhanced Plot Window Toolbar
- [ ] **Add Curve** - Add curve to plot
- [ ] **Remove Curve** - Remove selected curve
- [ ] **Clear All** - Clear all curves
- [ ] **Zoom In** - Zoom in
- [ ] **Zoom Out** - Zoom out
- [ ] **Reset Zoom** - Reset zoom to default
- [ ] **Pan** - Pan tool
- [ ] **Auto Scale** - Auto scale axes
- [ ] **Grid Toggle** - Show/hide grid
- [ ] **Legend Toggle** - Show/hide legend
- [ ] **Export Plot** - Export as image
- [ ] **Copy to Clipboard** - Copy plot
- [ ] **Print** - Print plot
- [ ] **Plot Settings** - Plot configuration

**Suggested icons:**
```
plot/add-curve.png (plus on line)
plot/remove-curve.png (minus on line)
plot/clear.png (X or eraser)
plot/zoom-in.png (magnifying glass +)
plot/zoom-out.png (magnifying glass -)
plot/zoom-reset.png (magnifying glass =)
plot/pan.png (hand icon)
plot/autoscale.png (expand arrows)
plot/grid.png (grid)
plot/legend.png (legend box)
plot/export.png (save image)
plot/copy.png (copy icon)
plot/print.png (printer)
plot/settings.png (gear)
```

### Plot Window Actions
- [ ] **Dataset Selector** - Dropdown icon
- [ ] **Save Plot** - Save plot data
- [ ] **Load Plot** - Load plot data

**Suggested icons:**
```
plot/dataset.png (database)
plot/save-plot.png (save)
plot/load-plot.png (load)
```

---

## 📋 Table Windows

### Enhanced Table Window Toolbar
- [ ] **Add Row** - Add new row
- [ ] **Add Column** - Add new column
- [ ] **Delete Row** - Delete selected row
- [ ] **Delete Column** - Delete selected column
- [ ] **Sort Ascending** - Sort A-Z
- [ ] **Sort Descending** - Sort Z-A
- [ ] **Filter** - Filter data
- [ ] **Clear Filter** - Clear filters
- [ ] **Export Table** - Export as CSV/Excel
- [ ] **Copy Selection** - Copy selected cells
- [ ] **Paste** - Paste data
- [ ] **Find/Replace** - Search in table
- [ ] **Table Settings** - Table configuration

**Suggested icons:**
```
table/add-row.png (row with plus)
table/add-column.png (column with plus)
table/delete-row.png (row with X)
table/delete-column.png (column with X)
table/sort-asc.png (A-Z arrow up)
table/sort-desc.png (Z-A arrow down)
table/filter.png (funnel)
table/clear-filter.png (funnel with X)
table/export.png (table with arrow)
table/copy.png (copy icon)
table/paste.png (clipboard)
table/find.png (magnifying glass)
table/settings.png (gear)
```

---

## 🎨 General UI Elements

### Buttons
- [ ] **OK** - Confirm action
- [ ] **Cancel** - Cancel action
- [ ] **Apply** - Apply changes
- [ ] **Close** - Close window
- [ ] **Save** - Save changes
- [ ] **Load** - Load data
- [ ] **Delete** - Delete item
- [ ] **Add** - Add new item
- [ ] **Remove** - Remove item
- [ ] **Edit** - Edit item
- [ ] **Refresh** - Refresh/reload
- [ ] **Settings** - Open settings
- [ ] **Help** - Show help
- [ ] **Back** - Go back
- [ ] **Forward** - Go forward
- [ ] **Up** - Navigate up
- [ ] **Down** - Navigate down

**Suggested icons:**
```
buttons/ok.png (checkmark)
buttons/cancel.png (X)
buttons/apply.png (checkmark in circle)
buttons/close.png (X)
buttons/save.png (floppy disk)
buttons/load.png (folder opening)
buttons/delete.png (trash can)
buttons/add.png (plus sign)
buttons/remove.png (minus sign)
buttons/edit.png (pencil)
buttons/refresh.png (circular arrows)
buttons/settings.png (gear)
buttons/help.png (question mark)
buttons/back.png (left arrow)
buttons/forward.png (right arrow)
buttons/up.png (up arrow)
buttons/down.png (down arrow)
```

### Input Controls
- [ ] **File Picker** - Browse for file
- [ ] **Folder Picker** - Browse for folder
- [ ] **Color Picker** - Choose color
- [ ] **Date Picker** - Choose date
- [ ] **Time Picker** - Choose time

**Suggested icons:**
```
inputs/file-browse.png (folder)
inputs/folder-browse.png (folder open)
inputs/color.png (palette)
inputs/date.png (calendar)
inputs/time.png (clock)
```

### Notifications
- [ ] **Success Notification** - Success message
- [ ] **Error Notification** - Error message
- [ ] **Warning Notification** - Warning message
- [ ] **Info Notification** - Info message

**Suggested icons:**
```
notifications/success.png (green checkmark)
notifications/error.png (red X)
notifications/warning.png (yellow triangle)
notifications/info.png (blue i)
```

---

## 📱 Application Icons

### App-Level Icons
- [ ] **Application Icon** - Main app icon (shown in dock/taskbar)
  - Multiple sizes: 16x16, 32x32, 64x64, 128x128, 256x256, 512x512
- [ ] **Window Icon** - Default window icon
- [ ] **Splash Screen** - Startup screen (optional)

**Suggested icons:**
```
app/icon-16.png
app/icon-32.png
app/icon-64.png
app/icon-128.png
app/icon-256.png
app/icon-512.png
app/window-icon.png
app/splash.png (larger, e.g., 800x600)
```

---

## 🎯 Data Type Icons

### File Type Icons
Different icons for different data types:

- [ ] **STS Data** - Scanning Tunneling Spectroscopy
- [ ] **SNOM Data** - Scanning Near-field Optical Microscopy
- [ ] **Generic Spectral Data**
- [ ] **Image Data**
- [ ] **CSV File**
- [ ] **HDF5 File**
- [ ] **NPY File**
- [ ] **Project File**

**Suggested icons:**
```
filetypes/sts.png
filetypes/snom.png
filetypes/spectral.png
filetypes/image.png
filetypes/csv.png
filetypes/hdf5.png
filetypes/npy.png
filetypes/project.png
```

---

## 🔢 Summary Count

### By Category:
- **Menu Bar Items**: ~50 items
- **Toolbar/Workspace**: ~10 items
- **Project Browser**: ~20 items
- **Status Bar**: ~7 items
- **Dialogs**: ~15 items
- **Tool Windows**: ~30 items (base) + tool-specific
- **Plot Windows**: ~20 items
- **Table Windows**: ~15 items
- **General UI Elements**: ~35 items
- **Application Icons**: ~10 variants
- **Data Type Icons**: ~8 items

**Total: ~220+ icon opportunities**

---

## 🎨 Priority Levels

### HIGH Priority (Start Here) - ~30 icons
Essential icons users will see immediately:
- File menu items (New, Open, Save, Exit)
- Most-used tools (FFT, Smoothing, Map Generator)
- Browser category icons (Datasets, Tables, Graphs)
- Status icons (Success, Error, Warning, Info)
- Plot toolbar basics (Add Curve, Zoom, Export)
- Basic buttons (OK, Cancel, Apply, Close)

### MEDIUM Priority - ~50 icons
Frequently used features:
- All tool menu items
- Window menu items
- Table toolbar
- Tool window buttons
- Browser item icons
- Tab bar icons

### LOW Priority - ~140 icons
Nice-to-have polish:
- Context menu actions
- Advanced plot features
- Specialized tool buttons
- File type icons
- Notification icons
- Multiple size variants

---

## 📥 Recommended Icon Sets

For complete coverage, download these icon sets:

1. **Feather Icons** (feathericons.com)
   - Covers: UI basics, file operations, arrows, common actions
   - ~280 icons, minimal style

2. **Material Design Icons** (materialdesignicons.com)
   - Covers: Everything, very comprehensive
   - ~7000+ icons

3. **Heroicons** (heroicons.com)
   - Covers: Modern UI elements
   - ~200+ icons

4. **Octicons** (primer.style/octicons)
   - Covers: Development and file operations
   - ~200+ icons

5. **Font Awesome Free** (fontawesome.com)
   - Covers: Comprehensive set
   - ~1500+ free icons

---

## 💡 Tips

1. **Start with high-priority icons** (30 icons)
2. **Use consistent icon style** (all from same set)
3. **Create @2x versions** for high-DPI displays
4. **Use 16x16 for menus**, 20-24x24 for toolbars
5. **Keep transparent backgrounds**
6. **Use white/light icons** for your dark theme
7. **Test icon visibility** at small sizes

---

## ✅ Quick Start Checklist

1. Download icon set (Feather Icons recommended)
2. Start with 30 high-priority icons
3. Place in appropriate folders (menu/, toolbar/, etc.)
4. Register in icons.qrc
5. Compile: `python3 compile_icons.py`
6. Import in main.py: `import src.qml.icons.icons_rc`
7. Add to QML: `icon.source: "qrc:/icons/..."`
8. Test and iterate

**You can add icons gradually - start with the high-priority 30, then expand!**
