import logging
import os
import sys
from contextvars import Token
from typing import Any, Mapping, Dict, Union, Optional, Iterable

import psutil
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
from structlog.processors import CallsiteParameter
from structlog.typing import FilteringBoundLogger

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Span, SpanContext

try:  # Optional dependency
    import logfire  # type: ignore
except Exception:  # pragma: no cover - optional
    logfire = None  # type: ignore

_AnyLogger = FilteringBoundLogger | structlog.stdlib.AsyncBoundLogger | Any


def configure_logfire(service_name: Optional[str] = None) -> None:
    """Initialize Logfire as the primary logging backbone if available.

    - Picks service name from parameter or OTEL_SERVICE_NAME env var, defaulting to "pyutils".
    - Instruments stdlib logging so that logging.* is captured by Logfire.
    """
    if logfire is None:  # pragma: no cover - optional
        raise RuntimeError("logfire is not installed")

    svc = service_name or os.environ.get("OTEL_SERVICE_NAME") or "pyutils"

    # Configure logfire, be tolerant to API shape across versions
    configured = False
    try:
        logfire.configure(service_name=svc)  # type: ignore[arg-type]
        configured = True
    except Exception:
        # Fall back to simplest call
        logfire.configure()  # type: ignore[call-arg]
        configured = True

    # Best-effort stdlib logging instrumentation so 3rd-party logs go to Logfire
    try:
        inst = getattr(logfire, "instrument_logging", None)
        if callable(inst):
            inst()
    except Exception:
        pass


# noinspection PyPep8Naming
def getLogger(*args: Any, **initial_values: Any) -> _AnyLogger:
    return structlog.get_logger(*args, **initial_values)


class _Trace:
    tokens: Mapping[str, Token[Any]]
    kwargs: Dict[str, Any]

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        self.tokens = bind_contextvars(**self.kwargs)

    def __exit__(self, exc_type, exc_val, exc_tb):
        unbind_contextvars(*self.tokens)

    def __aenter__(self):
        self.tokens = bind_contextvars(**self.kwargs)

    def __aexit__(self, exc_type, exc_val, exc_tb):
        unbind_contextvars(*self.tokens)


def trace(**kwargs):
    return _Trace(**kwargs)


# noinspection PyUnusedLocal
def uppercase_log_level(logger, log_method, event_dict):
    # Replace the level with its uppercase version
    event_dict["level"] = log_method.upper()
    return event_dict


def _format_trace_id(ctx: SpanContext) -> str:
    return f"{ctx.trace_id:032x}"


def _format_span_id(ctx: SpanContext) -> str:
    return f"{ctx.span_id:016x}"


# noinspection PyUnusedLocal
def opentelemetry_context(logger, log_method, event_dict):
    """
    structlog processor that adds OpenTelemetry trace/span identifiers if a valid span is active.
    Fields added (when available):
    - otel.trace_id
    - otel.span_id
    - otel.trace_flags
    """
    try:
        span: Span = otel_trace.get_current_span()
        ctx: SpanContext = span.get_span_context()  # type: ignore[assignment]
        if ctx is not None and ctx.is_valid:
            event_dict.setdefault("otel.trace_id", _format_trace_id(ctx))
            event_dict.setdefault("otel.span_id", _format_span_id(ctx))
            # Represent trace flags as two-digit hex (e.g., 01 for sampled)
            event_dict.setdefault("otel.trace_flags", f"{int(ctx.trace_flags):02x}")
    except Exception:
        # Avoid breaking logging if OTel is misconfigured
        pass
    return event_dict


class PythonLoggingInterceptHandler(logging.Handler):
    """
    A logging handler that intercepts standard logging records and re-emits them via structlog.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Retrieve the corresponding structlog logging using the record’s name.
        logger = structlog.get_logger(record.name)

        # Re-emit the logging record’s message along with any extra context.
        level = record.levelno
        ctx = record.__dict__
        msg = record.getMessage()
        logger.log(level, msg, **ctx)



# noinspection PyUnusedLocal
def min_log_level_from_env(min_level):
    env_level = os.environ.get("LOG_LEVEL", "")
    match env_level.upper():
        case "CRITICAL":
            min_level = logging.CRITICAL
        case "FATAL":
            min_level = logging.CRITICAL
        case "ERROR":
            min_level = logging.ERROR
        case "WARNING":
            min_level = logging.WARNING
        case "WARN":
            min_level = logging.WARNING
        case "INFO":
            min_level = logging.INFO
        case "DEBUG":
            min_level = logging.DEBUG
        case _:
            min_level = logging.NOTSET
    return min_level


# noinspection PyUnusedLocal
def configure(min_level: Union[str, int, None] = logging.NOTSET, pretty: Optional[bool] = None):
    if min_level is None:
        min_level = min_log_level_from_env(min_level)

    # Prefer Logfire as the logging backbone when available (and not disabled)
    use_logfire = bool(logfire) and os.environ.get("LOGFIRE_ENABLED", "1") != "0"
    if use_logfire:
        try:
            configure_logfire()
        except Exception:
            # Fall back silently to structlog-only if Logfire setup fails
            use_logfire = False

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        opentelemetry_context,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.THREAD_NAME,
                CallsiteParameter.MODULE,
                CallsiteParameter.FUNC_NAME,
                CallsiteParameter.LINENO
            ]),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        uppercase_log_level,
    ]

    if pretty is not None and pretty:
        # If pretty is set to True, use PrettyPrinter
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True, sort_keys=True),
        ]
    if pretty is not None and not pretty:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Check if stderr is a TTY (terminal)
        if sys.stderr.isatty():
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]

        # Check if the debugger is running
        elif "pydevd" in globals():
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]

        # Check if this is running in a jupyter notebook
        elif hasattr(sys.modules["__main__"], "__file__") and sys.modules["__main__"].__file__.endswith(".ipynb"):
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]

        # Check if this is running in PyCharm
        elif os.environ.get("PYCHARM_HOSTED", "") == "1":
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]

        # Otherwise, use JSON renderer
        else:
            is_idea = False
            current = psutil.Process()
            for parent in current.parents():
                if "idea" in parent.name().lower():
                    is_idea = True
            if is_idea:
                processors = shared_processors + [
                    structlog.dev.ConsoleRenderer(colors=True),
                ]

            else:
                processors = shared_processors + [
                    structlog.processors.dict_tracebacks,
                    structlog.processors.JSONRenderer(),
                ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        # wrapper_class=structlog.stdlib.AsyncBoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )

    # If Logfire is active, avoid intercepting stdlib logging to structlog to prevent duplicate emission.
    if not use_logfire:
        logging.basicConfig(
            force=True,
            level=min_level,
            handlers=[
                PythonLoggingInterceptHandler()
            ]
        )


def get_tracer(name: Optional[str] = None):
    """Return a global OpenTelemetry tracer.

    If no name is provided, uses the caller module name when available.
    """
    if name is None:
        # Fallback to this module's name to avoid expensive stack inspection
        name = __name__
    return otel_trace.get_tracer(name)


class _Span:
    def __init__(self, name: str, attributes: Optional[Mapping[str, Any]] = None, kind: Optional[Any] = None):
        self.name = name
        self.attributes = attributes or {}
        self.kind = kind
        self._cm = None

    def __enter__(self):
        tracer = get_tracer()
        kw = {}
        if self.kind is not None:
            kw["kind"] = self.kind
        self._cm = tracer.start_as_current_span(self.name, attributes=dict(self.attributes), **kw)
        span = self._cm.__enter__()
        return span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._cm is not None:
            self._cm.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)


def start_span(name: str, *, attributes: Optional[Mapping[str, Any]] = None, kind: Optional[Any] = None):
    """Convenience context manager to start an OTel span.

    Usage:
        with start_span("operation", attributes={"key": "value"}):
            ...
    """
    return _Span(name, attributes=attributes, kind=kind)


def configure_tracing(
    *,
    service_name: Optional[str] = None,
    exporter: str = "console",
    endpoint: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    resource_attributes: Optional[Mapping[str, Any]] = None,
    use_batch: bool = True,
) -> None:
    """Configure a global OpenTelemetry TracerProvider and exporter.

    - exporter: "console" (default) or "otlp". If "otlp" is selected but the OTLP exporter is not available,
      falls back to console.
    - endpoint and headers are used only for the OTLP exporter when provided.

    Environment fallbacks:
    - service_name defaults to OTEL_SERVICE_NAME or "pyutils".
    - endpoint defaults to OTEL_EXPORTER_OTLP_ENDPOINT when not provided.
    """
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SimpleSpanProcessor,
        ConsoleSpanExporter,
    )

    service_name = service_name or os.environ.get("OTEL_SERVICE_NAME") or "pyutils"

    # Build resource with provided and default attributes
    attrs: Dict[str, Any] = {"service.name": service_name}
    if resource_attributes:
        attrs.update(resource_attributes)
    resource = Resource.create(attrs)

    provider = TracerProvider(resource=resource)

    processor_cls = BatchSpanProcessor if use_batch else SimpleSpanProcessor

    span_exporter = None
    if exporter.lower() == "otlp":
        try:
            # Prefer HTTP/proto exporter for portability
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore

            span_exporter = OTLPSpanExporter(
                endpoint=(endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")),
                headers=headers,
            )
        except Exception:
            # Fall back to console exporter if OTLP exporter is unavailable/misconfigured
            span_exporter = ConsoleSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()

    provider.add_span_processor(processor_cls(span_exporter))

    # Set the global provider
    otel_trace.set_tracer_provider(provider)
