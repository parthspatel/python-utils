"""Structured logging with OpenTelemetry backend - Rust-like tracing interface."""

from .config import (
    ExportTarget,
    LogLevel,
    LoggingConfig,
    OutputFormat,
    OtelConfig,
    StructlogConfig,
    configure_logging,
    dev_config,
    get_logger,
    get_logger as getLogger,
    instrument,
    prod_config,
    setup_dev,
    setup_dev_with_spans,
    setup_json_console,
    setup_prod,
    span,
)
from .structlog_exporter import StructlogHandler

# Main interface - similar to Rust's tracing
__all__ = [
    # Core logging interface (Rust-like)
    "get_logger",
    "getLogger",
    "span",
    "instrument",

    # Configuration
    "configure_logging",
    "dev_config",
    "prod_config",

    # Quick setup functions
    "setup_dev",
    "setup_dev_with_spans",
    "setup_prod",
    "setup_json_console",

    # Configuration classes
    "LoggingConfig",
    "StructlogConfig",
    "OtelConfig",

    # Enums
    "OutputFormat",
    "ExportTarget",
    "LogLevel",

    # Advanced usage
    "StructlogHandler",
]
