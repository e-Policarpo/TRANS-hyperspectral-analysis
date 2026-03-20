"""
Solution for Exercise 09_03: JSON Logger

A JSON formatter for Python's logging module with structured output.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for structured logging.

    Each log entry includes:
    - timestamp (ISO 8601 format)
    - level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger name
    - message
    - location (file, line, function)
    - exception info (if present)
    - any extra fields passed to the log call
    """

    def __init__(self, app_name: str = "app", **default_fields):
        """
        Initialize the JSON formatter.

        Parameters:
            app_name: Application name to include in all log entries
            **default_fields: Additional fields to include in every log entry
        """
        super().__init__()
        self.app_name = app_name
        self.default_fields = default_fields

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as a JSON string.

        Parameters:
            record: The log record to format

        Returns:
            JSON-formatted string
        """
        # Base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "app": self.app_name,
        }

        # Add location information
        log_entry["location"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception information if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add any extra fields from the record
        # These are fields passed via extra={} in log calls
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'thread', 'threadName', 'exc_info', 'exc_text',
            'message', 'asctime', 'taskName'
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_entry[key] = value

        # Add default fields
        log_entry.update(self.default_fields)

        # Serialize to JSON with custom encoder for non-serializable types
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def setup_json_logging(
    app_name: str = "app",
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    **extra_fields
) -> logging.Logger:
    """
    Set up JSON logging for the application.

    Parameters:
        app_name: Application name for log entries
        log_file: Optional file path for log output
        level: Logging level (default INFO)
        **extra_fields: Additional fields to include in all log entries

    Returns:
        Configured logger instance

    Example:
        logger = setup_json_logging(
            app_name="trans-qml",
            log_file="app.log",
            level=logging.DEBUG,
            version="1.0.0"
        )
        logger.info("App started", extra={"config": "default"})
    """
    logger = logging.getLogger(app_name)
    logger.setLevel(level)
    logger.handlers.clear()  # Remove existing handlers

    # Create formatter
    formatter = JsonFormatter(app_name=app_name, **extra_fields)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Example usage and test
if __name__ == "__main__":
    # Set up logger
    logger = setup_json_logging(
        app_name="trans-qml",
        level=logging.DEBUG,
        version="1.0.0",
        environment="development"
    )

    # Test different log levels
    logger.debug("Debug message")
    logger.info("Application started")
    logger.info("Data loaded", extra={"dataset": "test.csv", "rows": 1000})
    logger.warning("Low memory", extra={"available_mb": 256})

    # Test exception logging
    try:
        raise ValueError("Invalid input value")
    except ValueError:
        logger.exception("Operation failed", extra={"operation": "parse"})
