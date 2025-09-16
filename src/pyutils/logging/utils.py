import logging
import os
import sys
import inspect
from functools import wraps
from contextvars import Token
from typing import Any, Mapping, Dict, Union, Optional, Iterable

import psutil
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
from structlog.processors import CallsiteParameter
from structlog.typing import FilteringBoundLogger

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Span, SpanContext

_AnyLogger = FilteringBoundLogger | structlog.stdlib.AsyncBoundLogger | Any


# noinspection PyPep8Naming
def getLogger(*args: Any, **initial_values: Any) -> _AnyLogger:
    return structlog.get_logger(*args, **initial_values)


def _to_set(items: Optional[Iterable[str]]) -> Optional[set[str]]:
    if items is None:
        return None
    return set(items)


def _filter_attrs(attrs: Mapping[str, Any], whitelist: Optional[Iterable[str]], blacklist: Optional[Iterable[str]]) -> Dict[str, Any]:
    wl = _to_set(whitelist)
    bl = _to_set(blacklist)

    # If whitelist is empty/None => allow all keys
    if not wl:
        allowed = set(attrs.keys())
    else:
        allowed = wl

    # If blacklist is empty/None => block none
    denied = bl or set()

    keys = (allowed - denied) & set(attrs.keys())
    return {k: attrs[k] for k in keys}


class _Trace:
    tokens: Mapping[str, Token[Any]]
    name: str
    attributes: Dict[str, Any]
    kind: Optional[Any]
    _span_cm: Any

    def __init__(self, *, name: Optional[str] = None, attributes: Optional[Mapping[str, Any]] = None, kind: Optional[Any] = None, **kwargs: Any):
        # kwargs are included as attributes and bound to contextvars
        self.name = name or "trace"
        base_attrs: Dict[str, Any] = dict(attributes or {})
        base_attrs.update(kwargs)
        self.attributes = base_attrs
        self.kind = kind
        self._span_cm = None

    def __enter__(self):
        # Bind context for structlog
        self.tokens = bind_contextvars(**self.attributes)
        # Start OTel span
        tracer = get_tracer()
        kw = {}
        if self.kind is not None:
            kw["kind"] = self.kind
        self._span_cm = tracer.start_as_current_span(self.name, attributes=dict(self.attributes), **kw)
        self._span_cm.__enter__()
        # Return the active span for convenience
        return otel_trace.get_current_span()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._span_cm is not None:
                self._span_cm.__exit__(exc_type, exc_val, exc_tb)
        finally:
            # Always unbind context vars
            unbind_contextvars(*self.tokens)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)


def _make_trace_decorator(*, name: Optional[str] = None, whitelist: Optional[Iterable[str]] = None, blacklist: Optional[Iterable[str]] = None):
    def decorator(func):
        span_name = name or f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"

        def build_attrs(args, kwargs):
            try:
                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                arg_map = dict(bound.arguments)
            except Exception:
                arg_map = {}

            # Drop common first parameter names that are not useful as attributes
            if arg_map:
                first_key = next(iter(arg_map))
                if first_key in ("self", "cls"):
                    arg_map.pop(first_key, None)

            return _filter_attrs(arg_map, whitelist, blacklist)

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def awrapper(*args, **kwargs):
                attrs = build_attrs(args, kwargs)
                async with _Trace(name=span_name, attributes=attrs):
                    return await func(*args, **kwargs)

            return awrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                attrs = build_attrs(args, kwargs)
                with _Trace(name=span_name, attributes=attrs):
                    return func(*args, **kwargs)

            return wrapper

    return decorator


def trace(func=None, /, *, name: Optional[str] = None, whitelist: Optional[Iterable[str]] = None, blacklist: Optional[Iterable[str]] = None, **attrs: Any):
    """Tracing utility that supports two forms:
    - Context manager: with trace(k=v, ...): starts an OTel span (default name "trace") and binds k=v into log context.
    - Decorator: @trace(whitelist=[...], blacklist=[...]) or @trace: wraps the function, starts a span named after it,
      and sets span attributes from function arguments filtered by the lists.

    Semantics:
    - If whitelist is empty or None => all args/attrs allowed.
    - If blacklist is empty or None => nothing is blacklisted.
    """
    # If used as @trace without parentheses (decorator on function)
    if callable(func):
        return _make_trace_decorator(name=name, whitelist=whitelist, blacklist=blacklist)(func)

    # If decorator parameters are provided (whitelist/blacklist), act as decorator factory
    if whitelist is not None or blacklist is not None or name is not None:
        return _make_trace_decorator(name=name, whitelist=whitelist, blacklist=blacklist)

    # Otherwise, act as context manager using provided attributes
    return _Trace(name=None, attributes=attrs)


def _make_instrument_decorator(*, name: Optional[str] = None, skip: Optional[Iterable[str]] = None, fields: Optional[Mapping[str, Any]] = None):
    skip_set = set(skip or [])
    fields = dict(fields or {})

    def decorator(func):
        span_name = name or f"{func.__module__}.{getattr(func, '__qualname__', func.__name__)}"

        def build_attrs(args, kwargs):
            try:
                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                arg_map = dict(bound.arguments)
            except Exception:
                arg_map = {}

            # Drop common receiver parameter names
            if arg_map:
                first_key = next(iter(arg_map))
                if first_key in ("self", "cls"):
                    arg_map.pop(first_key, None)

            # Apply skip
            for k in list(arg_map.keys()):
                if k in skip_set:
                    arg_map.pop(k, None)

            # Merge constant fields (explicit fields override arg_map)
            arg_map.update(fields)
            return arg_map

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def awrapper(*args, **kwargs):
                attrs = build_attrs(args, kwargs)
                async with _Trace(name=span_name, attributes=attrs):
                    return await func(*args, **kwargs)

            return awrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                attrs = build_attrs(args, kwargs)
                with _Trace(name=span_name, attributes=attrs):
                    return func(*args, **kwargs)

            return wrapper

    return decorator


def instrument(func=None, /, *, name: Optional[str] = None, skip: Optional[Iterable[str]] = None, fields: Optional[Mapping[str, Any]] = None):
    """Rust-like instrument decorator.

    Usage:
    - @instrument
    - @instrument()
    - @instrument(name="custom", skip=["password"], fields={"component": "db"})

    Works with both sync and async functions.
    """
    if callable(func):
        return _make_instrument_decorator(name=name, skip=skip, fields=fields)(func)
    return _make_instrument_decorator(name=name, skip=skip, fields=fields)


def span(name: str, /, **fields: Any):
    """Create a Rust-like span context manager.

    Example:
        with span("http.request", method="GET", path="/users"):
            ...
    """
    return _Trace(name=name, attributes=fields)


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
