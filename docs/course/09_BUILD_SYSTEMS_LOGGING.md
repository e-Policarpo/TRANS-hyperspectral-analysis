# Module 9: Build Systems, Executables, and JSON Logging

## From Development to Production

This module covers the essential skills for packaging and distributing your PySide6/QML applications, along with structured logging for debugging and monitoring.

---

## Learning Objectives

By the end of this module, you will be able to:
- Create Makefiles for automating build tasks
- Package applications into standalone executables
- Implement structured JSON logging
- Set up proper entry points and configuration
- Handle platform-specific build requirements

---

## 9.1 Makefile Fundamentals

### Why Makefiles?

Even for Python projects, Makefiles provide:
- **Consistent commands** - Same interface across team members
- **Dependency tracking** - Only rebuild what changed
- **Task automation** - Run tests, lint, build, deploy with single commands
- **Documentation** - Self-documenting build process

### Basic Makefile Structure

```makefile
# Makefile for TRANS-QML

# Variables
PYTHON := python3
PIP := pip3
APP_NAME := TRANS-QML
VERSION := 1.0.0

# Default target
.DEFAULT_GOAL := help

# Phony targets (not actual files)
.PHONY: help install run test lint clean build dist

# Help target
help:
	@echo "Available targets:"
	@echo "  install   - Install dependencies"
	@echo "  run       - Run the application"
	@echo "  test      - Run all tests"
	@echo "  lint      - Run code linters"
	@echo "  clean     - Remove build artifacts"
	@echo "  build     - Build standalone executable"
	@echo "  dist      - Create distribution package"

# Install dependencies
install:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

# Run the application
run:
	$(PYTHON) src/main.py

# Run tests
test:
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=html

# Run linters
lint:
	$(PYTHON) -m flake8 src/
	$(PYTHON) -m mypy src/

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build executable
build: clean
	$(PYTHON) -m PyInstaller trans_qml.spec

# Create distribution
dist: build
	mkdir -p dist/$(APP_NAME)-$(VERSION)
	cp -r build/$(APP_NAME)/* dist/$(APP_NAME)-$(VERSION)/
	cd dist && zip -r $(APP_NAME)-$(VERSION).zip $(APP_NAME)-$(VERSION)
```

### Pattern Rules

```makefile
# Compile Python bytecode for faster startup
%.pyc: %.py
	$(PYTHON) -m py_compile $<

# Generate QML type info
qmltypes: src/widgets/*.py
	$(PYTHON) -m PySide6.scripts.pyside_tool qmltyperegistrar \
		--output src/qml/plugins.qmltypes \
		src/widgets/

# Process all .ui files to Python
UI_FILES := $(wildcard src/ui/*.ui)
PY_UI_FILES := $(UI_FILES:.ui=_ui.py)

ui: $(PY_UI_FILES)

%_ui.py: %.ui
	pyside6-uic $< -o $@
```

### Conditional Logic

```makefile
# Detect OS
UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Linux)
    PLATFORM := linux
    ICON_EXT := png
endif
ifeq ($(UNAME_S),Darwin)
    PLATFORM := macos
    ICON_EXT := icns
endif
ifeq ($(OS),Windows_NT)
    PLATFORM := windows
    ICON_EXT := ico
endif

# Platform-specific build
build-$(PLATFORM):
	$(PYTHON) -m PyInstaller --name $(APP_NAME) \
		--icon=resources/icon.$(ICON_EXT) \
		--add-data "src/qml:qml" \
		src/main.py
```

---

## 9.2 PyInstaller for Standalone Executables

### Why PyInstaller?

PyInstaller bundles Python applications into standalone executables:
- **No Python installation required** - Users don't need Python
- **All dependencies included** - Creates self-contained package
- **Cross-platform** - Works on Windows, macOS, Linux

### Basic Usage

```bash
# Simple one-file build
pyinstaller --onefile --windowed src/main.py

# Named application with icon
pyinstaller --name TRANS-QML --icon=icon.icns --windowed src/main.py
```

### Spec File Configuration

For complex applications, use a `.spec` file:

```python
# trans_qml.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Application info
APP_NAME = 'TRANS-QML'
MAIN_SCRIPT = 'src/main.py'
ICON = 'resources/icon.icns'

# Collect all data files
def collect_data_files():
    data_files = []

    # QML files
    qml_path = Path('src/qml')
    for qml_file in qml_path.rglob('*.qml'):
        rel_path = qml_file.relative_to('src')
        data_files.append((str(qml_file), str(rel_path.parent)))

    # QML dir files
    for qmldir in qml_path.rglob('qmldir'):
        rel_path = qmldir.relative_to('src')
        data_files.append((str(qmldir), str(rel_path.parent)))

    # Resources
    data_files.append(('resources/', 'resources'))

    return data_files

# Hidden imports for PySide6
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuickControls2',
    'numpy',
    'pandas',
    'scipy',
    'matplotlib',
    'matplotlib.backends.backend_agg',
]

# Analysis
a = Analysis(
    [MAIN_SCRIPT],
    pathex=['.'],
    binaries=[],
    datas=collect_data_files(),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
    ],
    noarchive=False,
)

# Remove unnecessary files
a.binaries = [x for x in a.binaries if not x[0].startswith('libQt5')]

# Create PYZ archive
pyz = PYZ(a.pure, a.zipped_data)

# Create executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

# Collect all files
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=ICON,
        bundle_identifier='com.example.trans-qml',
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0',
            'NSHighResolutionCapable': True,
            'NSPrincipalClass': 'NSApplication',
            'LSBackgroundOnly': False,
        },
    )
```

### Building with Spec File

```bash
# Build using spec file
pyinstaller trans_qml.spec

# Clean build
pyinstaller --clean trans_qml.spec

# Debug mode (shows console)
pyinstaller --debug all trans_qml.spec
```

---

## 9.3 QML Resource Handling

### The QML Import Path Problem

When bundling PySide6/QML apps, QML files must be findable at runtime:

```python
# src/main.py
import sys
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication


def get_qml_path():
    """Get QML path that works both in development and bundled app"""
    if getattr(sys, 'frozen', False):
        # Running as bundled executable
        base_path = Path(sys._MEIPASS)
    else:
        # Running in development
        base_path = Path(__file__).parent

    return base_path / 'qml'


def main():
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()

    # Add QML import paths
    qml_path = get_qml_path()
    engine.addImportPath(str(qml_path))
    engine.addImportPath(str(qml_path / 'components'))

    # Load main QML
    main_qml = qml_path / 'main' / 'Main.qml'
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        sys.exit(-1)

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
```

### Resource File Pattern

For smaller apps, embed QML as Qt resources:

```python
# generate_resources.py
"""Generate Qt resource file from QML directory"""
import os
from pathlib import Path


def generate_qrc(qml_dir: Path, output: Path):
    """Generate .qrc file from directory"""
    lines = ['<RCC>', '  <qresource prefix="/qml">']

    for root, dirs, files in os.walk(qml_dir):
        rel_root = Path(root).relative_to(qml_dir)
        for f in files:
            if f.endswith(('.qml', 'qmldir')):
                rel_path = rel_root / f
                lines.append(f'    <file>{rel_path}</file>')

    lines.extend(['  </qresource>', '</RCC>'])

    output.write_text('\n'.join(lines))
    print(f"Generated {output}")


if __name__ == '__main__':
    generate_qrc(Path('src/qml'), Path('resources/qml.qrc'))
```

---

## 9.4 Structured JSON Logging

### Why JSON Logging?

JSON-structured logs provide:
- **Machine-parseable** - Easy to process with tools
- **Consistent format** - Same structure for all log entries
- **Rich context** - Include arbitrary metadata
- **Analysis-ready** - Import directly into log aggregators

### Basic JSON Logger

```python
# src/utils/json_logger.py
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings.

    Includes standard fields plus any extra context passed.
    """

    def __init__(self, app_name: str = "trans-qml", **kwargs):
        super().__init__()
        self.app_name = app_name
        self.default_keys = kwargs

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "app": self.app_name,
        }

        # Add location info
        log_entry["location"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add any extra fields from record
        for key, value in record.__dict__.items():
            if key not in (
                'name', 'msg', 'args', 'created', 'filename',
                'funcName', 'levelname', 'levelno', 'lineno',
                'module', 'msecs', 'pathname', 'process',
                'processName', 'relativeCreated', 'stack_info',
                'thread', 'threadName', 'exc_info', 'exc_text',
                'message'
            ):
                log_entry[key] = value

        # Add default keys
        log_entry.update(self.default_keys)

        return json.dumps(log_entry, default=str)


def setup_json_logging(
    app_name: str = "trans-qml",
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    **extra_fields
) -> logging.Logger:
    """
    Set up JSON logging for the application.

    Parameters:
        app_name: Application name for log entries
        log_file: Optional file path for log output
        level: Logging level
        **extra_fields: Additional fields to include in all log entries

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(app_name)
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers

    # Create formatter
    formatter = JsonFormatter(app_name=app_name, **extra_fields)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
```

### Using the JSON Logger

```python
# src/main.py
from utils.json_logger import setup_json_logging

# Set up logging at application start
logger = setup_json_logging(
    app_name="trans-qml",
    log_file="trans_qml.log",
    level=logging.DEBUG,
    version="1.0.0",
    environment="development"
)

# Basic logging
logger.info("Application started")
logger.debug("Loading configuration", extra={"config_file": "settings.json"})

# Logging with context
logger.info(
    "Dataset loaded",
    extra={
        "dataset_name": "STS_sample",
        "num_points": 1024,
        "file_size_mb": 2.5
    }
)

# Error logging with exception
try:
    raise ValueError("Invalid input")
except Exception as e:
    logger.exception("Operation failed", extra={"operation": "load_file"})
```

### Log Output Example

```json
{"timestamp": "2024-01-15T10:30:45.123456Z", "level": "INFO", "logger": "trans-qml", "message": "Application started", "app": "trans-qml", "location": {"file": "src/main.py", "line": 25, "function": "main"}, "version": "1.0.0", "environment": "development"}
{"timestamp": "2024-01-15T10:30:45.234567Z", "level": "INFO", "logger": "trans-qml", "message": "Dataset loaded", "app": "trans-qml", "location": {"file": "src/backend/app_backend.py", "line": 142, "function": "loadFile"}, "dataset_name": "STS_sample", "num_points": 1024, "file_size_mb": 2.5}
{"timestamp": "2024-01-15T10:30:46.345678Z", "level": "ERROR", "logger": "trans-qml", "message": "Operation failed", "app": "trans-qml", "exception": {"type": "ValueError", "message": "Invalid input", "traceback": "..."}, "operation": "load_file"}
```

---

## 9.5 Log Rotation and Management

### Rotating File Handler

```python
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler


def setup_production_logging(
    app_name: str,
    log_dir: str,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Set up production logging with rotation.

    Features:
    - JSON formatting
    - Size-based rotation
    - Compressed backups
    """
    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    formatter = JsonFormatter(app_name=app_name)

    # Rotating file handler
    log_file = Path(log_dir) / f"{app_name}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Also log errors to separate file
    error_file = Path(log_dir) / f"{app_name}.error.log"
    error_handler = RotatingFileHandler(
        error_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


def setup_daily_logging(app_name: str, log_dir: str) -> logging.Logger:
    """Set up logging with daily rotation"""
    logger = logging.getLogger(app_name)
    logger.setLevel(logging.INFO)

    formatter = JsonFormatter(app_name=app_name)

    log_file = Path(log_dir) / f"{app_name}.log"
    handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30  # Keep 30 days
    )
    handler.setFormatter(formatter)
    handler.suffix = "%Y-%m-%d"
    logger.addHandler(handler)

    return logger
```

---

## 9.6 Performance Logging

### Timing Decorator

```python
import functools
import time
from typing import Callable


def log_performance(logger: logging.Logger):
    """
    Decorator that logs function execution time.

    Usage:
        @log_performance(logger)
        def slow_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            try:
                result = func(*args, **kwargs)
                success = True
                error = None
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                elapsed = time.perf_counter() - start_time

                logger.info(
                    f"Function executed: {func.__name__}",
                    extra={
                        "function": func.__name__,
                        "elapsed_seconds": round(elapsed, 4),
                        "success": success,
                        "error": error
                    }
                )

            return result
        return wrapper
    return decorator


# Usage
logger = setup_json_logging("trans-qml")

@log_performance(logger)
def process_large_dataset(data):
    # ... processing
    time.sleep(1)  # Simulated work
    return result
```

### Context Manager for Timing

```python
from contextlib import contextmanager


@contextmanager
def log_timing(logger: logging.Logger, operation: str, **extra):
    """
    Context manager for timing code blocks.

    Usage:
        with log_timing(logger, "data_processing", dataset="test"):
            process_data()
    """
    start_time = time.perf_counter()
    extra_fields = {"operation": operation, **extra}

    logger.debug(f"Starting: {operation}", extra=extra_fields)

    try:
        yield
        success = True
    except Exception as e:
        success = False
        extra_fields["error"] = str(e)
        raise
    finally:
        elapsed = time.perf_counter() - start_time
        extra_fields["elapsed_seconds"] = round(elapsed, 4)
        extra_fields["success"] = success

        level = logging.INFO if success else logging.ERROR
        logger.log(level, f"Completed: {operation}", extra=extra_fields)


# Usage
with log_timing(logger, "fft_calculation", input_size=1024):
    result = np.fft.fft(data)
```

---

## 9.7 Application Entry Point

### Proper Entry Point Structure

```python
# src/main.py
"""
TRANS-QML Application Entry Point

This module sets up the application environment, logging,
and launches the Qt/QML application.
"""

import sys
import os
from pathlib import Path


def setup_environment():
    """Configure environment before Qt initialization"""
    # High DPI support
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    # Disable Qt's default logging (we use our own)
    os.environ["QT_LOGGING_RULES"] = "qt.*=false"

    # Set application paths
    if getattr(sys, 'frozen', False):
        # Running as bundled app
        os.environ["TRANS_QML_ROOT"] = str(Path(sys._MEIPASS))
    else:
        os.environ["TRANS_QML_ROOT"] = str(Path(__file__).parent.parent)


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success)
    """
    # Setup environment first
    setup_environment()

    # Now import Qt (after environment is configured)
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication

    from backend.app_backend import AppBackend
    from utils.json_logger import setup_json_logging
    from widgets import register_qml_types

    # Setup logging
    log_dir = Path.home() / ".trans_qml" / "logs"
    logger = setup_json_logging(
        app_name="trans-qml",
        log_file=str(log_dir / "trans_qml.log"),
        level=os.environ.get("LOG_LEVEL", "INFO")
    )

    logger.info("Starting TRANS-QML", extra={"version": "1.0.0"})

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("TRANS-QML")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("TRANS")

    # Set icon
    icon_path = Path(os.environ["TRANS_QML_ROOT"]) / "resources" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Register custom QML types
    register_qml_types()

    # Create backend
    backend = AppBackend()

    # Create QML engine
    engine = QQmlApplicationEngine()

    # Add import paths
    qml_path = Path(os.environ["TRANS_QML_ROOT"]) / "src" / "qml"
    engine.addImportPath(str(qml_path))
    engine.addImportPath(str(qml_path / "components"))
    engine.addImportPath(str(qml_path / "workflow"))

    # Expose backend to QML
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty(
        "workflowManager", backend.workflow_manager
    )

    # Load main QML
    main_qml = qml_path / "main" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        logger.error("Failed to load QML")
        return -1

    logger.info("Application ready")

    # Run event loop
    exit_code = app.exec()

    logger.info("Application exiting", extra={"exit_code": exit_code})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

---

## 9.8 Configuration Management

### Config File Pattern

```python
# src/utils/config.py
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "json"
    file: Optional[str] = None
    max_size_mb: int = 10
    backup_count: int = 5


@dataclass
class UIConfig:
    """UI configuration"""
    theme: str = "dark"
    font_size: int = 12
    show_toolbar: bool = True


@dataclass
class AppConfig:
    """Main application configuration"""
    app_name: str = "TRANS-QML"
    version: str = "1.0.0"
    debug: bool = False
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        """Load configuration from file"""
        if config_path is None:
            config_path = Path.home() / ".trans_qml" / "config.json"

        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)

            # Handle nested configs
            if "logging" in data:
                data["logging"] = LoggingConfig(**data["logging"])
            if "ui" in data:
                data["ui"] = UIConfig(**data["ui"])

            return cls(**data)

        return cls()

    def save(self, config_path: Optional[Path] = None):
        """Save configuration to file"""
        if config_path is None:
            config_path = Path.home() / ".trans_qml" / "config.json"

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = asdict(self)
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)


# Environment variable overrides
def apply_env_overrides(config: AppConfig) -> AppConfig:
    """Apply environment variable overrides to config"""
    if "LOG_LEVEL" in os.environ:
        config.logging.level = os.environ["LOG_LEVEL"]
    if "TRANS_DEBUG" in os.environ:
        config.debug = os.environ["TRANS_DEBUG"].lower() == "true"
    if "TRANS_THEME" in os.environ:
        config.ui.theme = os.environ["TRANS_THEME"]
    return config
```

---

## 9.9 Summary

### Key Concepts

1. **Makefiles** - Automate build, test, and deployment tasks
2. **PyInstaller** - Bundle Python apps into executables
3. **QML Resources** - Handle QML files in bundled apps
4. **JSON Logging** - Structured, machine-parseable logs
5. **Log Rotation** - Manage log file sizes and retention
6. **Entry Points** - Clean application startup patterns

### Build Checklist

| Task | Tool/Method |
|------|-------------|
| Install dependencies | `make install` |
| Run tests | `make test` |
| Lint code | `make lint` |
| Build executable | `pyinstaller *.spec` |
| Create distribution | `make dist` |
| Run application | `python src/main.py` |

---

## Exercises

### Exercise 9.1: Basic Makefile
Create a Makefile with install, run, test, and clean targets.

### Exercise 9.2: PyInstaller Spec
Write a PyInstaller spec file for a PySide6/QML application.

### Exercise 9.3: JSON Logger
Implement a JSON formatter for Python's logging module.

### Exercise 9.4: Performance Decorator
Create a decorator that logs function execution time as JSON.

### Exercise 9.5: Config Manager
Build a configuration system with file persistence and environment overrides.

---

*Module 9 of 10 | TRANS-QML Course*
