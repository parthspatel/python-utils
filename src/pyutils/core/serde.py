import base64
import binascii
import inspect
import pickle
import uuid
from typing import Callable, Optional, Literal, Dict, Any

import cloudpickle

import logging

_logger = logging.getLogger(__name__)


def serialize_callable(cb: Callable) -> str:
    """
    Serialize a callable using CloudPickle and return it as a base64-encoded string.
    This is useful for sending functions over the network or storing them in a database.

    Example usage:
        Serialize a function:
        >>> def my_function(x, y):
        ...     return x + y
        >>> serialized = serialize_callable(my_function)
        >>> print(serialized)   # This will print a base64-encoded string representation of the function.
        gAWVRgIAAAAAAACMF2Nsb3VkcGlja2xlLmNsb3VkcGlja2xllIwOX21ha2VfZnVuY3Rpb26Uk5QoaACMDV9idWlsdGluX3R5cGWUk5SMCENvZGVUeXBllIWUUpQoSwJLAEsASwJLAksDQwqVAFgBLQAAACQAlE6FlCmMAXiUjAF5lIaUjCo8ZG9jdGVzdCBjb3JlLnNlcmRlLnNlcmlhbGl6ZV9jYWxsYWJsZVswXT6UjAtteV9mdW5jdGlvbpSMC215X2Z1bmN0aW9ulEsBQwmAANgLDIk1gEyUQwCUKSl0lFKUfZQojAtfX3BhY2thZ2VfX5SMBGNvcmWUjAhfX25hbWVfX5SMCmNvcmUuc2VyZGWUjAhfX2ZpbGVfX5SMSC9Vc2Vycy9wYXJ0aHBhdGVsL0RvY3VtZW50cy9wcm9qZWN0cy9weXRob24tdXRpbHMvY29yZS9zcmMvY29yZS9zZXJkZS5weZR1Tk5OdJRSlGgAjBJfZnVuY3Rpb25fc2V0c3RhdGWUk5RoHH2UfZQoaBeMC215X2Z1bmN0aW9ulIwMX19xdWFsbmFtZV9flIwLbXlfZnVuY3Rpb26UjA9fX2Fubm90YXRpb25zX1+UfZSMDl9fa3dkZWZhdWx0c19flE6MDF9fZGVmYXVsdHNfX5ROjApfX21vZHVsZV9flGgYjAdfX2RvY19flE6MC19fY2xvc3VyZV9flE6MF19jbG91ZHBpY2tsZV9zdWJtb2R1bGVzlF2UjAtfX2dsb2JhbHNfX5R9lHWGlIZSMC4=

    """
    raw_bytes = cloudpickle.dumps(cb)
    return base64.b64encode(raw_bytes).decode()


def _exec_in_module(
        code: str,
        inject: Optional[Dict[str, Any]] = None,
        pretend_main: bool = False,  # NEW
) -> Dict[str, Any]:
    """
    Execute *code* in its own synthetic module and return the globals dict.
    If pretend_main is False (default), then we set __name__ to a random module
    name so that `if __name__ == "__main__": …` blocks stay dormant.
    """
    module_globals: Dict[str, Any] = {}
    if inject:
        module_globals.update(inject)

    if pretend_main:
        module_globals["__name__"] = "__main__"
    else:
        module_globals["__name__"] = f"_probe_{uuid.uuid4().hex}"  # <-- changed

    exec(compile(code, "<deserialized>", "exec"), module_globals)
    return module_globals


def deserialize_callable(
        text: str,
        *,
        entrypoint: str = "main",
        pass_args_as: str | Literal["global_args"] = "global_args",  # or "global_args" to match your earlier helper
        pass_kwargs_as: str | Literal["global_kwargs"] = "global_kwargs",
) -> Callable:
    """
    Accepts a lambda, a lone *def*, or a full script and always returns a Callable.

    • Lambdas / expressions – compiled with ``eval`` and returned directly.
    • Single-function modules – the function is returned (or *entrypoint* if present).
    • Full scripts – a thin wrapper re-execs the code each time with
      (*args, **kwargs*) available under *pass_args_as* / *pass_kwargs_as*.

    Example usage:
        >>> _body = '''
        ... def foo(x, y, key=None):
        ...     return x + y, key
        ...
        ... def main(*args, **kwargs):
        ...     res = foo(*args, **kwargs)
        ...     return res
        ...
        ... if __name__ == "__main__":
        ...     main(*global_args, **global_kwargs)
        ...
        ... '''

        Deserializing a callable from a string body with the default entrypoint "main":
        >>> _deserialized_callable = deserialize_callable(_body)
        >>> assert _deserialized_callable(1, 2, key='value_1') == (3, 'value_1')

        Deserializing a callable from a string body with a specific entrypoint "main":
        >>> _deserialized_callable = deserialize_callable(_body, entrypoint="main")
        >>> assert _deserialized_callable(1, 2, key='value_2') == (3, 'value_2')

        Deserializing a callable from a string body with a different specified entrypoint "foo":
        >>> _deserialized_callable = deserialize_callable(_body, entrypoint="foo")
        >>> assert _deserialized_callable(1, 2, key='value_3') == (3, 'value_3')

    """

    # 1) If the text is a base64-encoded CloudPickle payload, decode and return it.
    try:
        raw = base64.b64decode(text, validate=True)  # <-- use *text*
        return cloudpickle.loads(raw)
    except (binascii.Error, pickle.UnpicklingError):
        # not a valid CloudPickle payload – fall through to “string code”
        pass

    text = inspect.cleandoc(text) + "\n"  # remove common indent, ensure trailing NL

    # 2) Can we treat it as an *expression* (covers lambdas)?
    try:
        expr_code = compile(text, "<expr>", "eval")
        result = eval(expr_code, {})  # safe: no built-ins; user gives code anyway
        if callable(result):
            return result  # ✅ lambda or `partial(...)`, etc.
    except SyntaxError:
        pass  # Not an expression – fall through.

    # 3) It's *not* just an expression – exec it once to see what's inside.
    globs = _exec_in_module(text)  # ← guard stays OFF

    # Prefer an explicitly named entry point if present.
    if entrypoint in globs and callable(globs[entrypoint]):
        return globs[entrypoint]

    # If exactly one user-defined callable exists, return it.
    user_callables = [
        obj for name, obj in globs.items()
        if callable(obj) and not name.startswith("_")  # skip dunders
    ]
    if len(user_callables) == 1:
        return user_callables[0]

    # 4) Otherwise we treat the text as a *script*. Build a runner that re-execs it.
    code_obj = compile(text, "<script>", "exec")
    module_name = f"_deserialized_{uuid.uuid4().hex}"

    def runner(*args, **kwargs):
        ns = {
            "__name__": "__main__",  # guard ON for the real run
            pass_args_as: args,
            pass_kwargs_as: kwargs,
        }
        exec(code_obj, ns)

    runner.__name__ = f"{module_name}_runner"
    runner.__doc__ = f"Dynamic runner for <script> (entrypoint undetermined)"
    return runner
