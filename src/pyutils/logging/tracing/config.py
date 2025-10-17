"""Configuration system for structlog backed by OpenTelemetry."""

import asyncio
import functools
import logging
import os
import socket
import sys
import warnings
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import structlog
from structlog._log_levels import add_log_level
from opentelemetry import trace, context as otel_context
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs._internal.export import ConsoleLogExporter, LogExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import set_tracer_provider, Span
from pydantic import BaseModel, Field

from .structlog_exporter import StructlogHandler


class OutputFormat(str, Enum):
    """Available output formats for logs."""
    PRETTY = "pretty"
    JSON = "json"
    PROTO = "proto"
    KEY_VALUE = "key_value"


class ExportTarget(str, Enum):
    """Available export targets for logs."""
    CONSOLE = "console"
    OTLP = "otlp"
    FILE = "file"


class LogLevel(str, Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructlogConfig(BaseModel):
    """Configuration for structlog processors."""

    include_stdlib: bool = Field(default=True, description="Include stdlib logging")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Log level")
    add_logger_name: bool = Field(default=True, description="Add logger name to output")
    add_log_level: bool = Field(default=True, description="Add log level to output")
    add_trace_context: bool = Field(default=True, description="Add trace and span IDs and names to logs for correlation")
    processors: Optional[List[Callable]] = Field(default=None, description="Custom processors")

    class Config:
        arbitrary_types_allowed = True


class OtelConfig(BaseModel):
    """Configuration for OpenTelemetry."""

    service_name: str = Field(description="Service name for telemetry")
    service_version: Optional[str] = Field(default=None, description="Service version")
    service_instance_id: Optional[str] = Field(default=None, description="Service instance ID")
    endpoint: Optional[str] = Field(default=None, description="OTLP endpoint")
    headers: Optional[Dict[str, str]] = Field(default=None, description="OTLP headers")
    insecure: bool = Field(default=False, description="Use insecure connection")
    console_span_export: bool = Field(default=False, description="Export spans to console for debugging")


class LoggingConfig(BaseModel):
    """Main logging configuration."""

    output_format: OutputFormat = Field(default=OutputFormat.PRETTY, description="Output format")
    export_target: ExportTarget = Field(default=ExportTarget.CONSOLE, description="Export target")
    file_path: Optional[str] = Field(default=None, description="File path for file export")
    structlog_config: StructlogConfig = Field(default_factory=StructlogConfig, description="Structlog configuration")
    otel_config: Optional[OtelConfig] = Field(default=None, description="OpenTelemetry configuration")


# Global state
_pyutils_logging_configured = False
_tracer_provider: Optional[TracerProvider] = None
_logger_cache: Dict[str, Any] = {}

# Context key for storing span attributes
_SPAN_ATTRIBUTES_KEY = otel_context.create_key("span_attributes")


def _get_default_service_name() -> str:
    """Get default service name."""
    return os.path.basename(sys.argv[0]) if sys.argv else "unknown-service"


def _get_hostname() -> str:
    """Get hostname for service instance ID."""
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def _add_logger_name(logger, method_name, event_dict):
    """Add logger name to event dict."""
    if hasattr(logger, 'name') and logger.name:
        event_dict['logger'] = logger.name
    return event_dict


def _add_trace_context(logger, method_name, event_dict):
    """Add trace and span IDs, span name, and span attributes to event dict for correlation with OpenTelemetry traces."""
    try:
        current_span:Span = trace.get_current_span()
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            if span_context.trace_id != 0:
                # Format as hex strings with 0x prefix for readability
                event_dict['trace_id'] = f"0x{span_context.trace_id:032x}"
                event_dict['span_id'] = f"0x{span_context.span_id:016x}"
                event_dict['span_name'] = current_span.name

                # Add span attributes from context
                span_attributes = otel_context.get_value(_SPAN_ATTRIBUTES_KEY)
                if span_attributes:
                    for key, value in span_attributes.items():
                        # Avoid overwriting existing log fields
                        if key not in event_dict:
                            # Convert value to string if it's not JSON serializable
                            try:
                                if isinstance(value, (str, int, float, bool)) or value is None:
                                    event_dict[key] = value
                                else:
                                    event_dict[key] = str(value)
                            except Exception:
                                # Skip attributes that can't be serialized
                                continue
    except Exception:
        # Don't fail logging if trace context is unavailable
        pass
    return event_dict


def _create_console_processor(output_format: OutputFormat) -> Callable:
    """Create console processor based on output format."""
    if output_format == OutputFormat.PRETTY:
        return structlog.dev.ConsoleRenderer(colors=True)
    elif output_format == OutputFormat.JSON:
        return structlog.processors.JSONRenderer()
    elif output_format == OutputFormat.KEY_VALUE:
        return structlog.processors.KeyValueRenderer()
    else:
        return structlog.dev.ConsoleRenderer(colors=False)


def _create_log_exporter(config: LoggingConfig) -> LogExporter:
    """Create log exporter based on configuration."""
    if config.export_target == ExportTarget.CONSOLE:
        return ConsoleLogExporter()
    elif config.export_target == ExportTarget.OTLP:
        if not config.otel_config or not config.otel_config.endpoint:
            raise ValueError("OTLP endpoint required for OTLP export target")

        return OTLPLogExporter(
            endpoint=config.otel_config.endpoint,
            headers=config.otel_config.headers or {},
            insecure=config.otel_config.insecure,
        )
    elif config.export_target == ExportTarget.FILE:
        if not config.file_path:
            raise ValueError("File path required for file export target")
        # Note: OpenTelemetry doesn't have a built-in file exporter
        # You might need to implement a custom file exporter
        warnings.warn("File export not yet implemented, falling back to console")
        return ConsoleLogExporter()
    else:
        raise ValueError(f"Unsupported export target: {config.export_target}")


def _setup_otel_tracing(config: Optional[OtelConfig]) -> TracerProvider:
    """Set up OpenTelemetry tracing."""
    global _tracer_provider

    if _tracer_provider is not None:
        return _tracer_provider

    tracer_provider = TracerProvider()

    # Add console span exporter if requested
    if config and config.console_span_export:
        console_processor = BatchSpanProcessor(ConsoleSpanExporter())
        tracer_provider.add_span_processor(console_processor)

    # Add OTLP span exporter if configured
    if config and config.endpoint:
        try:
            otlp_span_exporter = OTLPSpanExporter(
                endpoint=config.endpoint,
                headers=config.headers or {},
                insecure=config.insecure,
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
        except Exception:
            # Do not break logging setup if exporter configuration fails
            warnings.warn("Failed to configure OTLP span exporter; spans will not be exported via OTLP")

    set_tracer_provider(tracer_provider)
    _tracer_provider = tracer_provider
    return tracer_provider


def configure_logging(config: LoggingConfig) -> None:
    """Configure structlog with OpenTelemetry backend."""
    global _pyutils_logging_configured

    if _pyutils_logging_configured:
        warnings.warn("Logging already configured, reconfiguring")
        return

    # Set up OpenTelemetry tracing
    tracer_provider = _setup_otel_tracing(config.otel_config)

    # Create processors list
    processors = []

    # Add standard processors
    if config.structlog_config.add_log_level:
        processors.append(add_log_level)

    if config.structlog_config.add_logger_name:
        processors.append(_add_logger_name)

    # Add timestamp processor
    processors.append(structlog.processors.TimeStamper(fmt="iso"))

    # Add trace context (trace_id, span_id, and span_name) for correlation
    if config.structlog_config.add_trace_context:
        processors.append(_add_trace_context)

    # Add custom processors if provided
    if config.structlog_config.processors:
        processors.extend(config.structlog_config.processors)

    # Set up export target
    if config.export_target in [ExportTarget.OTLP, ExportTarget.FILE]:
        # Use OpenTelemetry exporter
        if not config.otel_config:
            config.otel_config = OtelConfig(
                service_name=_get_default_service_name(),
                service_instance_id=_get_hostname()
            )

        exporter = _create_log_exporter(config)
        otel_processor = StructlogHandler(
            service_name=config.otel_config.service_name,
            server_hostname=config.otel_config.service_instance_id or _get_hostname(),
            exporter=exporter
        )
        processors.append(otel_processor)
    else:
        # Use console output
        processors.append(_create_console_processor(config.output_format))

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.structlog_config.log_level.value)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging if requested
    if config.structlog_config.include_stdlib:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, config.structlog_config.log_level.value),
        )

    _pyutils_logging_configured = True


def dev_config(
    service_name: Optional[str] = None,
    log_level: LogLevel = LogLevel.DEBUG,
    output_format: OutputFormat = OutputFormat.PRETTY
) -> LoggingConfig:
    """Create development configuration."""
    return LoggingConfig(
        output_format=output_format,
        export_target=ExportTarget.CONSOLE,
        structlog_config=StructlogConfig(
            log_level=log_level,
            add_logger_name=True,
            add_log_level=True,
        ),
        otel_config=OtelConfig(
            service_name=service_name or _get_default_service_name(),
            service_instance_id=_get_hostname(),
            console_span_export=False,  # Disable span console output in dev mode
        ) if service_name else None
    )


def prod_config(
    service_name: str,
    otlp_endpoint: str,
    log_level: LogLevel = LogLevel.INFO,
    output_format: OutputFormat = OutputFormat.JSON,
    headers: Optional[Dict[str, str]] = None
) -> LoggingConfig:
    """Create production configuration."""
    return LoggingConfig(
        output_format=output_format,
        export_target=ExportTarget.OTLP,
        structlog_config=StructlogConfig(
            log_level=log_level,
            add_logger_name=True,
            add_log_level=True,
        ),
        otel_config=OtelConfig(
            service_name=service_name,
            service_instance_id=_get_hostname(),
            endpoint=otlp_endpoint,
            headers=headers or {},
            insecure=False,
        )
    )


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger (similar to Rust's tracing)."""
    # removed this in v0.15.0, we should not auto-configure logging
    # if not _pyutils_logging_configured:
    #     # Auto-configure with dev settings
    #     configure_logging(dev_config())

    # if not _pyutils_logging_configured:
    #     if os.getenv("PYUTILS_AUTO_CONFIGURE_LOGGING", "0") == "1":
    #         warnings.warn("Auto-configuring logging using dev_config; set PYUTILS_AUTO_CONFIGURE_LOGGING=0 to disable")
    #         configure_logging(dev_config())
    #     else:
    #         raise RuntimeError(
    #             "Logging is not configured. Call `configure_logging(...)` or use one of the setup_* helpers "
    #             "before calling get_logger(), or set environment variable PYUTILS_AUTO_CONFIGURE_LOGGING=1 to enable auto-configuration."
    #         )

    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'root')

    if name not in _logger_cache:
        _logger_cache[name] = structlog.get_logger(name)

    return _logger_cache[name]


@contextmanager
def span(name: str, **attributes):
    """Create a tracing span (similar to Rust's tracing)."""
    tracer = trace.get_tracer(__name__)

    # Store span attributes in context so they can be accessed by log processor
    current_context = otel_context.get_current()
    context_with_attributes = otel_context.set_value(_SPAN_ATTRIBUTES_KEY, attributes, current_context)

    # Use the context with attributes
    token = otel_context.attach(context_with_attributes)
    try:
        with tracer.start_as_current_span(name, attributes=attributes) as span:
            logger = get_logger()
            logger.debug("span_start", span_name=name, **attributes)
            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error("span_error", span_name=name, error=str(e), **attributes)
                raise
            finally:
                logger.debug("span_end", span_name=name)
    finally:
        otel_context.detach(token)


def instrument(func: Optional[Callable] = None, *, name: Optional[str] = None, **attributes):
    """Decorator to instrument a function with tracing (similar to Rust's tracing)."""
    def decorator(f: Callable) -> Callable:
        span_name = name or f"{f.__module__}.{f.__qualname__}"

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with span(span_name, **attributes):
                return f(*args, **kwargs)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            with span(span_name, **attributes):
                return await f(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(f) else wrapper

    return decorator if func is None else decorator(func)


# Convenience functions for quick setup
def setup_dev(service_name: Optional[str] = None, log_level: LogLevel = LogLevel.DEBUG) -> None:
    """Quick setup for development."""
    configure_logging(dev_config(service_name=service_name, log_level=log_level))


def setup_prod(service_name: str, otlp_endpoint: str, log_level: LogLevel = LogLevel.INFO) -> None:
    """Quick setup for production."""
    configure_logging(prod_config(service_name=service_name, otlp_endpoint=otlp_endpoint, log_level=log_level))


def setup_json_console(service_name: Optional[str] = None, log_level: LogLevel = LogLevel.INFO) -> None:
    """Setup JSON output to console (good for containerized environments)."""
    config = dev_config(service_name=service_name, log_level=log_level, output_format=OutputFormat.JSON)
    configure_logging(config)


def setup_dev_with_spans(service_name: Optional[str] = None, log_level: LogLevel = LogLevel.DEBUG) -> None:
    """Setup development mode with span debugging (shows OpenTelemetry spans in console)."""
    config = dev_config(service_name=service_name, log_level=log_level)
    if config.otel_config:
        config.otel_config.console_span_export = True
    configure_logging(config)


# Re-export for convenience
__all__ = [
    "LoggingConfig",
    "StructlogConfig",
    "OtelConfig",
    "OutputFormat",
    "ExportTarget",
    "LogLevel",
    "configure_logging",
    "dev_config",
    "prod_config",
    "get_logger",
    "span",
    "instrument",
    "setup_dev",
    "setup_dev_with_spans",
    "setup_prod",
    "setup_json_console",
]
