from collections.abc import Callable
from typing import AnyStr, TypeVar, Self

from jsonpath_ng import DatumInContext, jsonpath
from jsonpath_ng.ext import \
    parse  # use the extension for more features to the parser the default parser is jsonpath_ng.parser
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

_TResult = TypeVar("_TResult")


class JPath:
    """Wrapper for JSONPath library. Can apply a function to objects at a given JSON path.
    Json Path Spec: https://goessner.net/articles/JsonPath/
    """

    def __init__(self, jpath: AnyStr, fx_expression: Callable[[list[jsonpath.DatumInContext]], _TResult] = None):
        super(JPath, self).__init__()
        self.__jpath = jpath
        self.__expression = parse(self.__jpath)
        self.__fx_expression = fx_expression if fx_expression else (lambda x: x)

    @property
    def get_json_path(self) -> AnyStr:
        return self.__jpath

    def apply(self, this_dict: dict) -> list[jsonpath.DatumInContext]:
        res = self.__expression.find(this_dict)
        return res

    def apply_expression(self, this_dict: dict) -> _TResult:
        res_list: list[DatumInContext] = self.apply(this_dict)
        res_expr = self.__fx_expression(res_list)
        return res_expr

    def get_jpath_expression(self) -> jsonpath.JSONPath:
        return self.__expression

    def __str__(self):
        return self.__jpath

    def __repr__(self):
        return f"JPath({self.__jpath})"

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.no_info_after_validator_function(
                    cls._validate,
                    core_schema.str_schema()
                ),
                core_schema.is_instance_schema(cls),
            ]
        )

    @classmethod
    def _validate(cls, value: str) -> Self:
        try:
            return cls(value)
        except Exception as e:
            raise ValueError(f"Invalid JSONPath: {value}. Error: {e}")