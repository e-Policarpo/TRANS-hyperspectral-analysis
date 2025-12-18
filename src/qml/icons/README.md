# Icons Directory

This directory contains PNG icon files used throughout the application.

## Directory Structure

```
icons/
├── README.md          # This file
├── icons.qrc          # Qt Resource file (icon manifest)
├── menu/              # Menu bar icons (16x16 px)
├── toolbar/           # Toolbar button icons (20x20 or 24x24 px)
├── status/            # Status bar icons (16x16 px)
└── general/           # General UI icons (various sizes)
```

## Adding New Icons

1. **Place your PNG file** in the appropriate subdirectory:
   - `menu/` - Menu item icons
   - `toolbar/` - Toolbar button icons
   - `status/` - Status indicator icons
   - `general/` - Other UI icons

2. **Edit icons.qrc** to register the new icon:
   ```xml
   <file alias="menu/my-new-icon.png">menu/my-new-icon.png</file>
   ```

3. **Compile resources** (choose one method):

   **Method A: Load QRC directly in Python (Recommended)**
   - Already set up in `main.py`
   - No compilation needed
   - Just restart the application

   **Method B: Compile to Python file**
   ```bash
   python3 compile_icons.py
   ```

4. **Use in QML:**
   ```qml
   icon.source: "qrc:/icons/menu/my-new-icon.png"
   ```

## Icon Specifications

### Size Recommendations
- **Menu items**: 16x16 or 20x20 pixels
- **Toolbar buttons**: 20x20 or 24x24 pixels
- **Status bar**: 16x16 pixels
- **List items**: 16x16 or 18x18 pixels

### Format Requirements
- **File type**: PNG
- **Background**: Transparent (alpha channel)
- **Color**: White or light colors for dark theme
- **High-DPI**: Optionally provide @2x versions (e.g., `icon.png` and `icon@2x.png`)

## Required Icons for This Application

### File Menu (menu/)
- [ ] file-new.png - New project
- [ ] file-open.png - Open project
- [ ] file-save.png - Save project
- [ ] file-save-as.png - Save as
- [ ] import.png - Import measurement
- [ ] exit.png - Exit application
- [ ] table.png - New table
- [ ] graph.png - New graph/plot

### Tools Menu (menu/)
- [ ] tools.png - Tools menu icon
- [ ] fft.png - FFT analysis
- [ ] smooth.png - Smoothing tools
- [ ] derivative.png - Derivative calculator
- [ ] fitting.png - Curve fitting
- [ ] integration.png - Integration utility
- [ ] workflow.png - Workflow icon

### Window Menu (menu/)
- [ ] window.png - Window menu icon
- [ ] browser.png - Project browser
- [ ] console.png - Debug console
- [ ] layout-save.png - Save layout
- [ ] layout-load.png - Load layout
- [ ] layout-reset.png - Reset layout

### Help Menu (menu/)
- [ ] help.png - Documentation
- [ ] about.png - About dialog

### Toolbar (toolbar/)
- [ ] add.png - Add item
- [ ] remove.png - Remove item
- [ ] refresh.png - Refresh
- [ ] settings.png - Settings
- [ ] play.png - Start/run operation
- [ ] stop.png - Stop operation

### Status Bar (status/)
- [ ] success.png - Success/ready state
- [ ] error.png - Error occurred
- [ ] warning.png - Warning
- [ ] info.png - Information/busy

### General UI (general/)
- [ ] folder.png - Folder/category
- [ ] dataset.png - Dataset item
- [ ] table.png - Table window
- [ ] graph.png - Graph/plot window
- [ ] map.png - Map item
- [ ] output.png - Output file

## Where to Get Icons

### Free Icon Resources
- **Feather Icons** - https://feathericons.com/ (Recommended - clean, minimal)
- **Heroicons** - https://heroicons.com/ (Beautiful, modern)
- **Material Design Icons** - https://materialdesignicons.com/ (Comprehensive)
- **Flaticon** - https://www.flaticon.com/ (Large collection)
- **Icons8** - https://icons8.com/ (Various styles)

### Converting SVG to PNG

Many icon libraries provide SVG. To convert to PNG:

**Using Inkscape (GUI):**
1. Open SVG in Inkscape
2. File → Export PNG Image
3. Set width/height (e.g., 16x16, 32x32)
4. Export

**Using ImageMagick (Command line):**
```bash
# Install: brew install imagemagick (macOS)
convert -background none -size 16x16 icon.svg icon.png
convert -background none -size 32x32 icon.svg icon@2x.png
```

**Using CairoSVG (Python):**
```bash
pip install cairosvg
cairosvg -W 16 -H 16 icon.svg -o icon.png
```

## Example Usage in QML

### Menu Item
```qml
MenuItem {
    text: "New Project"
    icon.source: "qrc:/icons/menu/file-new.png"
    icon.color: "transparent"
    icon.width: 16
    icon.height: 16
    onTriggered: backend.newProject()
}
```

### Toolbar Button
```qml
Button {
    text: "Add"
    icon.source: "qrc:/icons/toolbar/add.png"
    icon.color: "transparent"
    icon.width: 20
    icon.height: 20
    display: AbstractButton.TextBesideIcon
}
```

### List Item
```qml
RowLayout {
    Image {
        source: "qrc:/icons/general/dataset.png"
        Layout.preferredWidth: 16
        Layout.preferredHeight: 16
    }
    Text {
        text: "Dataset Name"
    }
}
```

## Troubleshooting

**Icons don't appear:**
1. Check icon file exists in correct directory
2. Verify icon is listed in `icons.qrc`
3. Check path in QML: `"qrc:/icons/..."`
4. Restart application after adding new icons

**Icons are blurry:**
- Provide @2x versions for high-DPI displays
- Or use SVG icons instead of PNG

**Wrong icon size:**
- Set both `sourceSize` and display size in QML
- Create icons at recommended pixel dimensions

For complete documentation, see: `ADDING_ICONS_GUIDE.md` in the project root.
