import logging
import os
import sys
from typing import Any, Union, Optional, Sequence, Literal
import threading
from types import FrameType

import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, psutil
from structlog.processors import CallsiteParameter
from structlog.typing import FilteringBoundLogger


AnyLogger = FilteringBoundLogger | structlog.stdlib.AsyncBoundLogger | Any
AnyLoggerFactory = structlog.BytesLoggerFactory | structlog.PrintLoggerFactory | structlog.WriteLoggerFactory | structlog.ReturnLoggerFactory

def getLogger(*args: Any, **initial_values: Any) -> AnyLogger:
    return structlog.get_logger(*args, **initial_values)


def get_logger(*args: Any, **initial_values: Any) -> AnyLogger:
    return getLogger(*args, **initial_values)


def min_log_level_from_env(default: Union[str, int] = logging.NOTSET) -> int:
    """Get the minimum log level from LOG_LEVEL env."""
    env_level = os.environ.get("LOG_LEVEL", "")
    return getattr(logging, env_level.upper(), default)


def uppercase_log_level(logger, log_method, event_dict):
    """Replace the log level with its uppercase version."""
    event_dict["level"] = log_method.upper()
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


class StdStreamToStructlog:
    """
    File-like object that intercepts writes to stdout/stderr and forwards them to structlog.

    - Buffers until a newline to preserve print() semantics.
    - Avoids recursion by writing directly to the original stream when already logging.
    - Writes are logged at a specified level (INFO for stdout, ERROR for stderr by default).
    """

    def __init__(self, level: int, stream_name: str, original_stream):
        self.level = level
        self.stream_name = stream_name
        self._buf = ""
        self._lock = threading.Lock()
        self._orig = original_stream
        self._tls = threading.local()

    def write(self, data):
        if not data:
            return 0
        if not isinstance(data, str):
            data = str(data)
        with self._lock:
            self._buf += data
            # Flush on every newline to preserve typical print behavior
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self._log_line(line)
        return len(data)

    def flush(self):
        with self._lock:
            if self._buf:
                self._log_line(self._buf)
                self._buf = ""
        try:
            self._orig.flush()
        except Exception:
            pass

    def isatty(self):
        # It's not a TTY from Python's perspective
        return False

    def fileno(self):
        # Delegate if possible, otherwise raise
        try:
            return self._orig.fileno()
        except Exception as e:
            raise OSError("No fileno for StdStreamToStructlog") from e

    def _log_line(self, line: str):
        if line is None:
            return
        # Strip trailing carriage returns that may appear on Windows
        line = line.rstrip("\r")
        if line == "":
            return

        # Prevent recursion if structlog itself writes to the intercepted streams
        if getattr(self._tls, "in_log", False):
            try:
                self._orig.write(line + "\n")
            except Exception:
                pass
            return

        try:
            self._tls.in_log = True
            logger = structlog.get_logger("print")
            # Tag prints, actual callsite will be computed by our callsite enricher.
            logger.log(self.level, line, stream=self.stream_name)
        finally:
            self._tls.in_log = False


def _callsite_enricher(logger, log_method, event_dict):
    """Add callsite fields (thread_name, module, func_name, lineno) for the original caller.

    Skips frames that belong to structlog, logging, this module (the print interceptor),
    and builtins.print so that prints show the user function that called print().
    """
    try:
        # Walk the frame stack manually for performance.
        f: FrameType = sys._getframe()
        # Exclude these module prefixes
        exclude_mod_prefixes = (
            "structlog",
            "logging",
            __name__,  # this module (print interceptor)
        )
        exclude_funcs = {"write", "_log_line", "emit", "log", "print"}
        # Step out of structlog processors into the actual call site
        while f is not None:
            f = f.f_back
            if f is None:
                break
            mod = f.f_globals.get("__name__", "")
            func = f.f_code.co_name
            if any(mod.startswith(p) for p in exclude_mod_prefixes):
                continue
            if mod == "builtins" and func == "print":
                continue
            if func in exclude_funcs and (mod.startswith(__name__) or mod.startswith("builtins")):
                continue
            # Found a suitable frame
            event_dict["thread_name"] = threading.current_thread().name
            event_dict["module"] = mod.split(".")[-1]
            event_dict["func_name"] = func
            event_dict["lineno"] = f.f_lineno
            break
    except Exception:
        # Best-effort only
        pass
    return event_dict


def configure(
    service_name: str,
    min_level: Optional[Union[str, int]] = None,
    pretty: Optional[bool] = None,
    exporter: Optional[Union[Literal["oltp"], Literal["console"], SpanExporter]] = "console",
    processors: Optional[Sequence] = None,
    logger_factory: Optional[AnyLoggerFactory] = None,
    wrapper_class: Optional[type] = None,
):
    """
    Configure structlog + OpenTelemetry.
    """

    # --- Logging level ---
    if min_level is None:
        min_level = min_log_level_from_env(logging.NOTSET)
    elif isinstance(min_level, str):
        min_level = getattr(logging, min_level.upper(), logging.NOTSET)

    # --- OpenTelemetry ---
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    if exporter == "otlp":
        exporter_obj = OTLPSpanExporter()
    elif exporter == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        exporter_obj = ConsoleSpanExporter()
    elif isinstance(exporter, SpanExporter):
        exporter_obj = exporter
    else:
        raise ValueError(f"Unsupported exporter: {exporter}")

    provider.add_span_processor(BatchSpanProcessor(exporter_obj))

    # --- Default processors ---
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        _callsite_enricher, # custom callsite enricher to attribute prints to their caller
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        uppercase_log_level,
    ]

    if processors is None:
        processors = _default_renderers(shared_processors, pretty)

    structlog.configure(
        processors=processors,
        wrapper_class=wrapper_class
        or structlog.make_filtering_bound_logger(min_level),
        context_class=dict,
        logger_factory=logger_factory or structlog.WriteLoggerFactory(file=sys.__stdout__),
        cache_logger_on_first_use=False,
    )

    # Intercept Python's print(), redirecting stdout/stderr to structlog-backed streams
    # try:
    #     original_stdout = sys.__stdout__
    # except Exception:
    #     original_stdout = sys.stdout
    # try:
    #     original_stderr = sys.__stderr__
    # except Exception:
    #     original_stderr = sys.stderr

    # sys.stdout = StdStreamToStructlog(logging.INFO, "stdout", original_stdout)
    # sys.stderr = StdStreamToStructlog(logging.ERROR, "stderr", original_stderr)

    # Intercept Python's logging, redirecting to structlog
    logging.basicConfig(
        force=True,
        level=min_level,
        handlers=[
            PythonLoggingInterceptHandler()
        ]
    )


def _default_renderers(shared_processors, pretty: Optional[bool]):
    """Smart default renderer selection, overridable by users."""
    # Force pretty console
    if pretty is True:
        return [*shared_processors, structlog.dev.ConsoleRenderer(colors=True)]
    # Force JSON
    if pretty is False:
        return [*shared_processors,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    # Auto-detect environment
    if sys.stderr.isatty() or os.environ.get("PYCHARM_HOSTED") == "1":
        return [*shared_processors, structlog.dev.ConsoleRenderer(colors=True)]

    # Check IntelliJ
    current = psutil.Process()
    if any("idea" in p.name().lower() for p in current.parents()):
        return [*shared_processors, structlog.dev.ConsoleRenderer(colors=True)]

    # Fallback: JSON
    return [
        *shared_processors,
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]
