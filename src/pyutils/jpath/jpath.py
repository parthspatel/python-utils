import base64
import json
from collections.abc import Callable
from typing import TypeVar, Optional, Union

import cloudpickle
from jsonpath_ng import DatumInContext, jsonpath
from jsonpath_ng.ext import parse
from pydantic import Field, field_serializer, field_validator, ConfigDict

from src.pyutils.pydantic import BaseModel

_TResult = TypeVar("_TResult")

class PyFunc:
    """Wraps conversion of strings (lambda/def/base64) to callables for Pydantic field validation."""
    def __init__(self, func: Callable):
        if not callable(func):
            raise TypeError("Value must be callable")
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        import pydantic_core

        def validate_pyfunc(value):
            if callable(value):
                return cls(value)
            if isinstance(value, str):
                try:
                    # Try base64 decode
                    raw_bytes = base64.b64decode(value.encode())
                    func = cloudpickle.loads(raw_bytes)
                    return cls(func)
                except Exception:
                    if value.strip().startswith("lambda"):
                        return cls(eval(value, {"DatumInContext": DatumInContext}))
                    if value.strip().startswith("def "):
                        namespace = {"DatumInContext": DatumInContext}
                        exec(value, namespace)
                        func_objs = [v for v in namespace.values() if callable(v)]
                        if not func_objs:
                            raise ValueError("No function found in source string.")
                        return cls(func_objs[0])
                    raise ValueError("String could not be parsed as a callable.")
            raise TypeError("Value must be a callable or a supported string.")
        return pydantic_core.core_schema.no_info_plain_validator_function(validate_pyfunc)

    def __repr__(self):
        return f"PyFunc({self.func})"

    def __eq__(self, other):
        # For test/dump purposes: two PyFuncs are "equal" if the repr of their code objects matches
        if isinstance(other, PyFunc):
            return repr(self.func) == repr(other.func)
        return False

class JPath(BaseModel):
    expression: str = Field(
        ...,
        description="The Json Path expression to apply"
    )
    fx: Optional[PyFunc] = Field(
        default=None,
        description="A function to apply to the result of the expression.  During serde, this is serialized with cloudpickle and base64 encoded.",
    )

    # model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__expression = parse(self.expression)

    def apply(self, this_dict: dict) -> list[jsonpath.DatumInContext]:
        res = self.__expression.find(this_dict)
        return res

    def apply_expression(self, this_dict: dict) -> _TResult:
        res_list: list[DatumInContext] = self.apply(this_dict)
        if self.fx is None:
            return res_list
        else:
            res_expr = self.fx(res_list)
            return res_expr

    def get_jpath_expression(self) -> jsonpath.JSONPath:
        return self.__expression

    @field_serializer("fx")
    def _serialize_fx(self, value):
        if value is None:
            return None
        return serialize_callable(value.func)

    def model_dump(self, *args, **kwargs):
        kwargs["exclude_none"] = True
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args, **kwargs):
        kwargs["exclude_none"] = True
        return super().model_dump_json(*args, **kwargs)


def serialize_callable(cb: Callable) -> str:
    raw_bytes = cloudpickle.dumps(cb)
    return base64.b64encode(raw_bytes).decode()


def deserialize_callable(data: str) -> Callable:
    # Try base64 decode first
    try:
        raw_bytes = base64.b64decode(data.encode())
        return cloudpickle.loads(raw_bytes)
    except Exception:
        pass  # Not base64? try as source code

    import ast

    # Try to evaluate as a lambda, or exec as a function def
    # very simple and unsafe version!
    try:
        if data.strip().startswith("lambda"):
            # Evaluate the lambda
            return eval(data, {"DatumInContext": DatumInContext})
        elif data.strip().startswith("def "):
            local_namespace = {}
            exec(data, {"DatumInContext": DatumInContext}, local_namespace)
            # Return the first function defined in locals
            funcs = [val for val in local_namespace.values() if callable(val)]
            if not funcs:
                raise ValueError("No function definition found.")
            return funcs[0]
        else:
            raise ValueError("Unsupported function source code format.")
    except Exception as e:
        raise ValueError(f"Could not parse function: {e}")

    # def __repr__(self):
    #     return self.to_dict()
    #
    # def __str__(self):
    #     return self.expression

def main():
    # Example usage
    jpath = JPath(expression="$.store.book[*].author")
    data = {
        "store": {
            "book": [
                {"author": "Author1"},
                {"author": "Author2"},
            ]
        }
    }
    result = jpath.apply(data)
    for r in result:
        print(r)

    print("=" * 20)

    jpath_dict = jpath.to_dict()
    print(jpath_dict)
    jpath_json = json.dumps(jpath_dict)
    print(jpath_json)
    jpath_dict2 = json.loads(jpath_json)
    print(jpath_dict2)
    print(jpath_dict == jpath_dict2)

    print("=" * 20)

    jpath_dict = jpath.to_dict(exclude_none=True)
    print(jpath_dict)
    jpath_json = json.dumps(jpath_dict)
    print(jpath_json)
    jpath_dict2 = json.loads(jpath_json)
    print(jpath_dict2)
    print(jpath_dict == jpath_dict2)


    print("=" * 20)

    jpath_dict_3 = {
        "expression": "$.store.book[*].author",
        "fx": "lambda x: [i.value for i in x]"
    }

    jpath_3 = JPath.model_validate(jpath_dict_3)
    print(jpath_3.to_dict())
    print(jpath_3.apply_expression(data))


if __name__ == '__main__':
    main()
