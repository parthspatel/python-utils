# tracing_like/api.py
import structlog
import functools
import json
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = structlog.get_logger()
tracer = trace.get_tracer("tracing_like")

# --- Helpers ---
_ALLOWED_ATTR_TYPES = (bool, str, bytes, int, float)

def _convert_value(value, as_string=False):
    """Convert values to OpenTelemetry-compatible types or string representation.

    Args:
        value: The value to convert
        as_string: If True, always return string. If False, return dict for BaseModel.
    """
    try:
        from pydantic import BaseModel
    except ImportError:
        BaseModel = None

    if value is None:
        return "None"
    elif BaseModel and isinstance(value, BaseModel):
        # Always convert BaseModel to JSON string for OpenTelemetry compatibility
        return value.model_dump_json()
    elif isinstance(value, _ALLOWED_ATTR_TYPES):
        return str(value) if as_string else value
    elif isinstance(value, (list, tuple)) and as_string:
        # Convert each element and join (only for string mode)
        converted = [_convert_value(item, as_string=True) for item in value]
        return f"[{', '.join(converted)}]" if isinstance(value, list) else f"({', '.join(converted)})"
    elif isinstance(value, dict):
        # Sanitize dict keys and values, then convert to JSON
        sanitized_dict = {}
        for k, v in value.items():
            # Ensure key is string
            clean_key = str(k) if not isinstance(k, str) else k
            # Recursively sanitize values
            clean_value = _convert_value(v, as_string=True)
            sanitized_dict[clean_key] = clean_value
        return json.dumps(sanitized_dict)
    else:
        return str(value)

def _convert_to_string(value):
    """Smart conversion of values to string representation."""
    return _convert_value(value, as_string=True)

def _sanitize_attributes(fields):
    """Convert field values to OpenTelemetry-compatible types.

    Converts Pydantic BaseModel instances to dicts and ensures all values
    are compatible with OpenTelemetry span attributes.
    """
    sanitized = {}
    for k, v in fields.items():
        sanitized[k] = _convert_value(v, as_string=False)
    return sanitized

# --- Events ---
def info(message, **fields):
    _log("info", message, **fields)

def warn(message, **fields):
    _log("warning", message, **fields)

def error(message, **fields):
    _log("error", message, **fields)

def debug(message, **fields):
    _log("debug", message, **fields)

def _log(level, message, **fields):
    span = trace.get_current_span()
    if span.is_recording():
        safe_attrs = _sanitize_attributes(fields)
        span.add_event(message, attributes=safe_attrs)
    getattr(logger, level)(message, **fields)

# --- Spans ---
@contextmanager
def span(name: str, *args, **fields):
    with tracer.start_as_current_span(name) as otel_span:
        if len(args) > 0 :
            otel_span.set_attribute("args", _convert_to_string(args))

        safe_attrs = _sanitize_attributes(fields)
        for k, v in safe_attrs.items():
            otel_span.set_attribute(k, v)
        try:
            yield otel_span
        except Exception as e:
            otel_span.set_status(StatusCode.ERROR, str(e))
            raise

# --- Instrument ---
def instrument(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with span(func.__name__, *args, **kwargs):
            return func(*args, **kwargs)
    return wrapper
