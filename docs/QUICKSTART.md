# TRANS-QML Quick Start Guide

## Installation

### 1. Install Python Dependencies

```bash
cd /Users/eduardapolicarpo/Documents/Doutorado/TRANS_QML
pip install -r requirements.txt
```

### 2. Nanosurf file support

NSFopen (by Nanosurf AG, MIT licensed) is bundled with TRANS — no separate installation needed. Nanosurf `.nid` and `.nhf` files are supported out of the box.

## Running the Application

### Launch the Application

```bash
python main.py
```

You should see the main window with three tabs:
- STS Analysis
- SNOM Analysis
- Map Editor

## Loading Data

### Option 1: Single File

1. Click **File** → **Import Data...**
2. Select **Yes** when asked "Import single file or entire folder?"
3. Navigate to your data file:
   - For Nanosurf: Select any `.nid` file
   - For NeaSpec: Select a `.txt` file
4. Click **Open**

### Option 2: Entire Folder

1. Click **File** → **Import Data...**
2. Select **No** when asked "Import single file or entire folder?"
3. Navigate to your data directory
4. Click **Select Folder**

The loader will:
- For Nanosurf: Load all `.nid` files in alphabetical order
- For NeaSpec: Load the first `.txt` file found

### What Happens During Loading

**Nanosurf (.nid) Files:**
- Extracts grid dimensions from metadata
- Loads Forward, Backward, and Mixed (average) channels
- Applies zigzag correction automatically
- Extracts topography data (if available)

**NeaSpec (.txt) Files:**
- Parses header for pixel area (grid dimensions)
- Splits concatenated data into measurement blocks
- Creates separate datasets for each harmonic (O0A, O0P, O1A, etc.)
- Creates datasets for both Wavenumber and Omega independent variables

### Check Loaded Data

After loading, the status bar shows:
- Current status message
- Active dataset name

## Using Tools

### Open a Tool

1. Select the appropriate tab (STS/SNOM/Map Editor)
2. Click **Tools** menu
3. Select a tool from the list

The tool window will open as a floating, draggable panel.

### Example: Integration Utility

1. Open **Tools** → **Integration Utility**
2. Select your dataset from the dropdown
3. Click **Add Interval** to add integration ranges
4. Enter lower and upper X values for each interval
5. Click **Calculate Integration**
6. Results are saved to `outputs/integrated/`

### Example: Spatial Average

1. Open **Tools** → **Spatial Average**
2. Select your dataset
3. See original grid dimensions
4. Set **Discrete X** and **Discrete Y** for target grid
5. View the transformation preview
6. Click **Calculate Spatial Average**
7. Results are saved to `outputs/curves/`

### Window Management

Each tool window can be:

**Moved**: Click and drag the title bar

**Resized**: Drag the bottom-right corner

**Brought to Front**: Click the ▲ button or click anywhere on the window

**Sent to Back**: Click the ▼ button

**Minimized**: Click the _ button

**Maximized**: Click the □ button

**Closed**: Click the × button

## Output Organization

All analysis results are saved in the `outputs/` directory:

```
outputs/
├── curves/          # Spectral data exports
├── derivatives/     # Derivative calculations
├── fft/            # FFT analysis
├── integrated/     # Integration results
├── maps/           # Generated map images
└── smoothed/       # Smoothed data
```

Each tool creates its own subdirectory within these folders.

## Data Format

### Input Data Requirements

**Nanosurf .nid Files:**
- Standard Nanosurf NID format
- Must contain spectroscopy data
- Grid dimensions extracted from `Map0` line in metadata
- Multiple files processed in alphabetical order

**NeaSpec .txt Files:**
- Must have NeaSpec header with `# Pixel Area` line
- Tab-separated columns
- Required columns: Row, Column, Wavenumber (or Omega), and harmonic channels (O0A, O0P, etc.)

### Output Data Format

**CSV Files:**
- First column: Independent variable (V, Wavenumber, etc.)
- Subsequent columns: Spectral data or processed results
- Column names indicate spatial position or processing

**TIFF Images:**
- Generated maps and visualizations
- Grayscale or false-color
- Dimensions match grid size

## Common Workflows

### STS Analysis Workflow

1. **Load Data**: Import `.nid` files
2. **Inspect**: View loaded data info in status bar
3. **Smooth**: Open Curve Smoothing tool
4. **Derive**: Calculate derivatives
5. **Integrate**: Define energy ranges and integrate
6. **Map**: Generate maps from integrated values
7. **Discretize**: Apply spatial averaging if needed

### SNOM Analysis Workflow

1. **Load Data**: Import `.txt` file
2. **Select Channel**: Choose appropriate harmonic (O1A, O2A, etc.)
3. **Smooth**: Apply curve or image smoothing
4. **Analyze**: FFT, derivatives, or other analysis
5. **Map**: Generate spatial maps
6. **Export**: Save results

## Troubleshooting

### Application Won't Start

**Problem**: QML errors or Python errors

**Solution**:
1. Check all dependencies installed: `pip list`
2. Verify PySide6 version: `pip show PySide6`
3. Check console output for specific errors
4. Ensure you're in the correct directory

### Data Won't Load

**Problem**: "Loader Error" dialog

**Solutions**:

For Nanosurf files:
1. Check file is valid `.nid` format
2. Try loading single file instead of folder

For NeaSpec files:
1. Check file has NeaSpec header (`# www.neaspec.com`)
2. Verify `# Pixel Area` line exists
3. Check file is tab-separated

### Tool Window Won't Open

**Problem**: Tool menu item clicked but nothing happens

**Solutions**:
1. Check console for QML errors
2. Verify tool QML file exists in `src/qml/tools/`
3. Try restarting application

### No Data in Dataset Dropdown

**Problem**: Tool opens but dataset dropdown is empty

**Solution**:
1. Load data first (File → Import Data)
2. Wait for "Data loaded" status message
3. Refresh tool window (close and reopen)

## Advanced Usage

### Loading Specific Channels

After loading Nanosurf data, you have access to:
- `DatasetName_Forward`: Forward scan only
- `DatasetName_Backward`: Backward scan only
- `DatasetName_Mixed`: Average of forward and backward

After loading NeaSpec data, you have access to:
- `DatasetName_Wavenumber_O0A`: Wavenumber vs O0A
- `DatasetName_Wavenumber_O1A`: Wavenumber vs O1A
- `DatasetName_Omega_O0A`: Omega vs O0A
- etc.

### Manual Grid Dimensions

If automatic detection fails, you can modify the loader code to specify dimensions manually.

### Custom Tools

To create your own tool:
1. Copy `GenericToolUI.qml` to `MyTool.qml`
2. Edit the UI components
3. Add to `ToolWindow.qml` mapping
4. Implement backend processing function

## Getting Help

### Documentation

- **PROJECT_OVERVIEW.md**: Detailed architecture and implementation details
- **README.md**: Project description and features
- **This file**: Quick start guide

### Logs

Application logs are saved to `trans_qml.log` in the application directory.

### Console Output

Run the application from terminal to see real-time debug messages:
```bash
python main.py
```

## Next Steps

1. **Explore the Tools Menu**: Each tab has different tools available
2. **Try Different Datasets**: Load various data types to see how loaders work
3. **Experiment with Parameters**: Adjust tool settings to understand their effects
4. **Review Outputs**: Check the `outputs/` directory to see generated files
5. **Read PROJECT_OVERVIEW.md**: Learn about the architecture and how to extend it

## Keyboard Shortcuts

(To be implemented)

- Ctrl+O: Open data
- Ctrl+S: Save current state
- Ctrl+Q: Quit application
- F1: Help

## Tips and Tricks

1. **Multiple Windows**: You can open the same tool multiple times with different parameters
2. **Window Arrangement**: Arrange tool windows side-by-side for comparison
3. **Dataset Management**: Keep track of active dataset in status bar
4. **Batch Processing**: Load entire folders for automated processing
5. **Output Organization**: Results are automatically organized by tool type

## Example Data

If you don't have data files yet:

1. Ask your microscope operator for sample files
2. Use the example data in the original TRANS project
3. Test with publicly available STM/SNOM datasets

## Updates and Maintenance

To update the application:
1. Pull latest code changes
2. Update dependencies: `pip install -r requirements.txt --upgrade`
3. Check PROJECT_OVERVIEW.md for new features

## Contact

For questions, bugs, or feature requests, contact the development team or check the project repository.
