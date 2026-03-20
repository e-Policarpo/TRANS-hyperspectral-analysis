# Scientific Desktop Application Development with PySide6 and QML

## A Comprehensive Course Using TRANS-QML as Reference Implementation

---

## Course Overview

This course teaches you how to build professional scientific desktop applications using Python (PySide6) and QML. You'll learn through a real-world implementation: **TRANS-QML** (Tools for Research and Analysis for Nano Spectroscopy), a hyperspectral data analysis application.

By the end of this course, you will be able to:
- Build modern, responsive desktop UIs with QML
- Integrate Python backends with QML frontends
- Implement thread-safe multithreading for long-running computations
- Create custom visualization widgets using matplotlib
- Design signal-based architectures for loose coupling
- Build workflow engines for scientific data processing

---

## Prerequisites

- **Python**: Intermediate level (classes, decorators, type hints)
- **Basic UI concepts**: Understanding of windows, buttons, events
- **Optional**: Familiarity with NumPy/Pandas for scientific modules

---

## Course Structure

### Module 1: Introduction and Project Setup
*Estimated time: 2 hours*

- Understanding the Qt/QML ecosystem
- PySide6 vs PyQt6
- Project structure for large applications
- Setting up the development environment
- Your first QML application with Python backend

### Module 2: QML-Python Integration Fundamentals
*Estimated time: 3 hours*

- Registering Python types for QML
- Exposing Python objects to QML context
- Calling Python methods from QML
- Type conversion between Python and QML
- The QML engine and component lifecycle

### Module 3: Signals, Slots, and Properties
*Estimated time: 4 hours*

- Qt's signal/slot mechanism in Python
- Defining signals with parameters
- Creating slots with @Slot decorator
- The Property system for reactive bindings
- Connecting signals across components
- QML Connections component

### Module 4: Multithreading for Responsive UIs
*Estimated time: 4 hours*

- Why multithreading matters for scientific apps
- QThread basics
- The Worker pattern
- Thread-safe signal communication
- Task queues and cancellation
- Progress reporting

### Module 5: Custom QML Components with Python
*Estimated time: 5 hours*

- QQuickPaintedItem for custom rendering
- Integrating matplotlib with QML
- Mouse and keyboard event handling
- Coordinate transformations
- Building interactive visualization widgets

### Module 6: Scientific Computing Integration
*Estimated time: 4 hours*

- NumPy/Pandas with Qt
- Data models (QAbstractTableModel)
- Formula engines and cell references
- Statistical computations
- File format handling (binary parsing)

### Module 7: Advanced UI Patterns
*Estimated time: 4 hours*

- Floating/dockable windows
- Workspace management
- Theme systems and styling
- Context menus and dialogs
- Drag and drop

### Module 8: Application Architecture
*Estimated time: 3 hours*

- Backend/Frontend separation
- State management
- Project save/load
- Plugin and workflow systems
- Testing strategies

### Module 9: Build Systems, Executables, and JSON Logging
*Estimated time: 3 hours*

- Makefile fundamentals for Python projects
- PyInstaller for standalone executables
- QML resource handling in bundled apps
- Structured JSON logging
- Configuration management
- Application entry points

### Module 10: Code Complexity Analysis
*Estimated time: 3 hours*

- Cyclomatic complexity measurement
- Nesting depth analysis
- Cognitive complexity
- Building AST-based code analyzers
- Automated quality reports
- CI/CD integration for code quality

---

## Reference Implementation: TRANS-QML

Throughout this course, we'll reference the TRANS-QML codebase:

```
TRANS/
├── src/
│   ├── main.py                 # Application entry point
│   ├── backend/
│   │   ├── app_backend.py      # Main backend (QObject)
│   │   ├── worker.py           # Multithreading infrastructure
│   │   ├── workflow_manager.py # Workflow execution
│   │   └── workflow_engine.py  # Tool definitions
│   ├── widgets/
│   │   ├── qml_graph_canvas.py # Matplotlib graph widget
│   │   ├── qml_map_canvas.py   # 2D map visualization
│   │   └── qml_profile_canvas.py # 1D profile plotting
│   ├── models/
│   │   ├── table_data_model.py # Spreadsheet model
│   │   ├── spectral_data.py    # Scientific data structures
│   │   └── map_channel.py      # Multi-channel maps
│   ├── data_loaders/
│   │   └── *.py                # Various instrument formats
│   └── qml/
│       ├── main/Main.qml       # Main application window
│       ├── components/         # Reusable QML components
│       ├── tools/              # Processing tool UIs
│       └── workflow/           # Node-based workflow editor
├── tests/                      # Test suite
└── docs/                       # Documentation
```

---

## How to Use This Course

### For Self-Study
1. Read each module in order
2. Study the referenced code files
3. Complete the exercises at the end of each module
4. Build the mini-projects to reinforce learning

### For Instructors
- Each module is designed for a 2-4 hour session
- Code examples can be live-coded
- Exercises can be assigned as homework
- The final project ties everything together

---

## Module Index

| Module | Topic | Key Files |
|--------|-------|-----------|
| [01](./01_INTRODUCTION.md) | Introduction & Setup | `main.py` |
| [02](./02_QML_PYTHON_BASICS.md) | QML-Python Integration | `app_backend.py` |
| [03](./03_SIGNALS_SLOTS_PROPERTIES.md) | Signals, Slots, Properties | `app_backend.py`, `Main.qml` |
| [04](./04_MULTITHREADING.md) | Multithreading | `worker.py` |
| [05](./05_CUSTOM_COMPONENTS.md) | Custom QML Components | `qml_*.py` widgets |
| [06](./06_SCIENTIFIC_COMPUTING.md) | Scientific Computing | `table_data_model.py` |
| [07](./07_ADVANCED_UI.md) | Advanced UI Patterns | QML components |
| [08](./08_ARCHITECTURE.md) | Application Architecture | Full codebase |
| [09](./09_BUILD_SYSTEMS_LOGGING.md) | Build Systems & Logging | Makefile, `*.spec` |
| [10](./10_CODE_COMPLEXITY_ANALYSIS.md) | Code Complexity Analysis | `grading_framework.py` |

---

## Exercises and Grading

Each module includes practical exercises with an automated grading system:

### Exercise Types
- **Python exercises**: Implement specific patterns and functionality
- **QML exercises**: Build UI components with proper structure
- **Makefile exercises**: Create build automation scripts
- **Spec file exercises**: Configure PyInstaller for packaging
- **Analysis exercises**: Apply code quality tools to real code

### Grading System

The grading framework evaluates submissions on:
- **Correctness (40%)**: Passes functional test cases
- **Required Patterns (20%)**: Uses expected code patterns/APIs
- **Best Practices (25%)**: Follows PEP 8, has docstrings, type hints
- **Code Quality (15%)**: Reasonable complexity and organization

```bash
# Grade a single submission
python evaluators/grading_framework.py --exercise 01_01 --submission ./my_code.py

# Batch grade all submissions
python evaluators/grading_framework.py --batch ./submissions/ --module 01
```

### Extra Exercises Pack
A bonus pack of advanced exercises (`exercises/extra/`) covers:
- Complete mini-applications
- Cross-module integration challenges
- Real-world TRANS-QML feature implementations

---

## Quick Start

Before starting the modules, ensure you have:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install PySide6 numpy pandas matplotlib scipy

# Verify installation
python -c "from PySide6.QtQuick import QQuickView; print('PySide6 OK')"
```

---

*Course Version: 2.0 (10 Modules with Exercises and Grading)*
*Based on TRANS-QML Implementation*
*Last Updated: January 2026*
