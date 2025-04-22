import contextlib
import logging
import os
import sys
from contextvars import Token
from typing import Any, Mapping, Dict, Union, Optional

import psutil
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
from structlog.processors import CallsiteParameter


class _Trace:
    tokens: Mapping[str, Token[Any]]
    kwargs: Dict[str, Any]

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        self.tokens = bind_contextvars(**self.kwargs)

    def __exit__(self, exc_type, exc_val, exc_tb):
        unbind_contextvars(*self.tokens)


def trace(**kwargs):
    return _Trace(**kwargs)


def uppercase_log_level(logger, log_method, event_dict):
    # Replace the level with its uppercase version
    event_dict["level"] = log_method.upper()
    return event_dict


def configure(min_level: Union[str, int] = logging.NOTSET, pretty: Optional[bool] = None):
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.CallsiteParameterAdder(
            parameters=[CallsiteParameter.THREAD_NAME, CallsiteParameter.MODULE, CallsiteParameter.FUNC_NAME,
                        CallsiteParameter.LINENO]),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        uppercase_log_level,
    ]

    if pretty is not None and pretty:
        # If pretty is set to True, use PrettyPrinter
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True, sort_keys=True),
        ]
    else:
        # Check if stderr is a TTY (terminal)
        if sys.stderr.isatty():
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]

        # Check if debugger is running
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
