import json
import traceback
from typing import Any, Dict, Optional


class ExceptionSerializer:
    """Serialize Python exceptions to JSON."""

    @staticmethod
    def to_dict(exc: BaseException, include_traceback: bool = True) -> Dict[str, Any]:
        """Serialize exception to dictionary."""
        result = {
            "type": type(exc).__name__,
            "module": type(exc).__module__,
            "message": str(exc),
            "args": exc.args,
        }

        # Add custom attributes
        custom_attrs = {}
        for attr in dir(exc):
            if not attr.startswith('_') and attr not in ['args', 'with_traceback']:
                try:
                    value = getattr(exc, attr)
                    if not callable(value):
                        json.dumps(value)  # Test if serializable
                        custom_attrs[attr] = value
                except (TypeError, AttributeError):
                    continue

        if custom_attrs:
            result["attributes"] = custom_attrs

        # Add traceback
        if include_traceback and exc.__traceback__:
            result["traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            result["traceback_frames"] = [
                {
                    "filename": frame.filename,
                    "line_number": frame.lineno,
                    "function": frame.name,
                    "code": frame.line,
                }
                for frame in traceback.extract_tb(exc.__traceback__)
            ]

        # Handle chained exceptions
        if exc.__cause__:
            result["cause"] = ExceptionSerializer.to_dict(exc.__cause__, include_traceback)
        elif exc.__context__ and not exc.__suppress_context__:
            result["context"] = ExceptionSerializer.to_dict(exc.__context__, include_traceback)

        return result

    @staticmethod
    def to_json(exc: BaseException, include_traceback: bool = True, **json_dumps_kwargs) -> str:
        """Convert exception to JSON string."""
        data = ExceptionSerializer.to_dict(exc, include_traceback)
        return json.dumps(data, **json_dumps_kwargs)


def test_exception_serializer():
    # Usage examples
    try:
        raise ValueError("Test error")
    except ValueError as e:
        print(ExceptionSerializer.to_json(e))
