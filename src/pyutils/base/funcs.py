import abc
import asyncio
import enum
from typing import List, TypeVar, Callable, Optional

from pydantic import Field, field_validator

from pyutils.pydantic import BaseModel

_TInput1 = TypeVar("_TInput1")
_TResult = TypeVar("_TResult")


class Function(BaseModel, abc.ABC):

    @abc.abstractmethod
    def __call__(self, data: _TInput1) -> _TResult:
        """
        Applies a function to each element in the data list.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    def __le__(self, other) -> '_Pipe':
        return pipe(functions=[other, self])

    def __ge__(self, other) -> '_Pipe':
        return pipe(functions=[self, other])


class _Head(Function):
    """
    A class that represents the head function, which returns the first element of a list.
    """

    def __call__(self, data: List[_TResult]) -> _TResult:
        if data:
            return data[0]
        else:
            raise ValueError("Data list is empty, cannot return head.")


class _Tail(Function):
    """
    A class that represents the tail function, which returns all elements of a list except the first one.
    """

    def __call__(self, data: List[_TResult]) -> List[_TResult]:
        if data:
            return data[1:]
        else:
            raise ValueError("Data list is empty, cannot return tail.")


class _Last(Function):
    """
    A class that represents the last function, which returns the last element of a list.
    """

    def __call__(self, data: List[_TResult]) -> _TResult:
        if data:
            return data[-1]
        else:
            raise ValueError("Data list is empty, cannot return last.")


class UnaryOps(enum.Enum):
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"

    @classmethod
    def from_string(cls, op_str: str) -> 'UnaryOps':
        """
        Converts a string representation of an operator to the corresponding UnaryOps enum.
        """
        try:
            return cls[op_str]
        except KeyError:
            match op_str:
                case "==" | "=" | "eq":
                    return cls.EQ
                case "!=" | "<>" | "ne":
                    return cls.NE
                case "<" | "lt":
                    return cls.LT
                case "<=" | "le":
                    return cls.LE
                case ">" | "gt":
                    return cls.GT
                case ">=" | "ge":
                    return cls.GE
                case "in" | "contains":
                    return cls.IN
                case "not in" | "not_contains":
                    return cls.NOT_IN
                case "is":
                    return cls.IS
                case "is not":
                    return cls.IS_NOT
                case _:
                    raise ValueError(f"Invalid operator: {op_str}")

    def __call__(self, a, b) -> bool:
        """
        Applies the operator to the two operands.
        """
        if self == UnaryOps.EQ:
            return a == b
        elif self == UnaryOps.NE:
            return a != b
        elif self == UnaryOps.LT:
            return a < b
        elif self == UnaryOps.LE:
            return a <= b
        elif self == UnaryOps.GT:
            return a > b
        elif self == UnaryOps.GE:
            return a >= b
        elif self == UnaryOps.IN:
            return a in b
        elif self == UnaryOps.NOT_IN:
            return a not in b
        elif self == UnaryOps.IS:
            return a is b
        elif self == UnaryOps.IS_NOT:
            return a is not b
        else:
            raise ValueError(f"Invalid operator: {self}")


class _AssertQuantity(Function):
    """
    A class that represents the assert_quantity function, which asserts that the length of a list is equal to a given number.
    """
    op: UnaryOps | str = Field(UnaryOps.EQ, description="The operator to use for the assertion.")
    n: int

    def __init__(self, op, n, **kwargs):
        if op is not None:
            if isinstance(op, str):
                op = UnaryOps.from_string(op)
            kwargs["op"] = op
        if n is not None:
            kwargs["n"] = n
        super().__init__(**kwargs)

    @classmethod
    @field_validator("op", mode="plain")
    def validate_op(cls, v):
        if isinstance(v, str):
            return UnaryOps.from_string(v)
        elif isinstance(v, UnaryOps):
            return v
        else:
            raise ValueError(f"Invalid operator: {v}")

    def __call__(self, data: List[_TResult]) -> _TResult:
        if self.op(len(data), self.n):
            return data
        else:
            raise ValueError(f"Data list contains {len(data)} elements, expected {self.op} {self.n}.")


class _Map(Function):
    """
    Applies a unary function to each element in the list.
    """
    func: Callable[[_TInput1], _TResult]

    def __init__(self, func, **kwargs):
        super().__init__(func=func, **kwargs)

    def __call__(self, data: _TInput1) -> _TResult:
        return self.func(data)


class _MapList(Function):
    """
    Applies a unary function to each element in the list.
    """
    func: Callable[[_TInput1], _TResult]

    def __init__(self, func, **kwargs):
        super().__init__(func=func, **kwargs)

    def __call__(self, data: List[_TInput1]) -> List[_TResult]:
        return [self.func(x) for x in data]


class _FlatMap(Function):
    """
    Applies a function to each element, flattening the result.
    """
    func: Callable[[_TInput1], List[_TResult]]

    def __init__(self, func, **kwargs):
        super().__init__(func=func, **kwargs)

    def __call__(self, data: List[_TInput1]) -> List[_TResult]:
        return [y for x in data for y in self.func(x)]


class _Filter(Function):
    """
    A class that represents the filter function, which filters elements in a list based on a predicate function.
    """

    func: Callable[[List[_TInput1]], bool]

    def __init__(self, func, **kwargs) -> None:
        if func is not None:
            kwargs["func"] = func
        super().__init__(**kwargs)

    def __call__(self, data: List[_TInput1]) -> List[_TInput1]:
        return [item for item in data if self.func(item)]


class _Reduce(Function):
    """
    A class that represents the reduce function, which reduces a list to a single value using a binary function.
    """

    func: Callable[[List[_TInput1], List[_TInput1]], _TResult]

    def __init__(self, func, **kwargs) -> None:
        if func is not None:
            kwargs["func"] = func
        super().__init__(**kwargs)

    def __call__(self, data: List[_TInput1]) -> _TResult:
        if not data:
            raise ValueError("Data list is empty, cannot reduce.")
        result = data[0]
        for item in data[1:]:
            result = self.func(result, item)
        return result


class Try(Function):
    """
    A class that represents the try function, which attempts to apply a function and returns the exception if it fails.
    It should have an optional function to handle the exception.
    """
    func: Callable[[_TInput1], _TResult]
    ex_handler: Optional[Callable[[Exception], _TResult]] = Field(None, description="A function to handle exceptions.")

    def __init__(self, func, ex_handler=None, **kwargs):
        if func is not None:
            kwargs["func"] = func
        if ex_handler is not None:
            kwargs["ex_handler"] = ex_handler
        super().__init__(**kwargs)

    @classmethod
    def as_optional(cls, func: Callable[[_TInput1], _TResult],
                    ex_handler: Optional[Callable[[Exception], _TResult]] = None) -> 'Try':
        """
        Creates a Try instance that returns None if the function raises an exception.
        """

        def _ex_handler(ex: Exception) -> _TResult:
            if ex_handler is not None:
                return ex_handler(ex)
            else:
                return None

        return cls(func=func, ex_handler=_ex_handler)

    def __call__(self, data: _TInput1) -> _TResult:
        try:
            return self.func(data)
        except Exception as e:
            if self.ex_handler is not None:
                return self.ex_handler(e)
            else:
                raise e


class _Pipe(Function):
    """
    A class that represents the pipe function, which chains multiple functions together.
    """
    functions: List[Function]

    def __init__(self, functions, **kwargs) -> None:
        if functions is not None:
            kwargs["functions"] = functions
        super().__init__(**kwargs)

    def __call__(self, data: List[_TInput1]) -> _TResult:
        for func in self.functions:
            data = func(data)
        return data


class _AsyncFunctionABC(Function, abc.ABC):
    @abc.abstractmethod
    async def __call__(self, *args, **kwargs) -> _TResult:
        raise NotImplementedError("Subclasses must implement this method.")

    def __le__(self, other):
        return _AsyncSeq(functions=[other, self])

    def __ge__(self, other):
        return _AsyncSeq(functions=[self, other])

    def __and__(self, other):
        return _AsyncGather(functions=[self, other])

    def and_(self, other):
        return _AsyncGather(functions=[self, other])

    def __or__(self, other):
        return _AsyncRace(functions=[self, other])

    def or_(self, other):
        return _AsyncRace(functions=[self, other])


class _AsyncFunction(Function):
    """
    A class that represents an asynchronous function adapter.
    Wraps a synchronous or asynchronous function; always executes as async.
    """

    func: Callable

    def __init__(self, func, **kwargs):
        if func is not None:
            kwargs["func"] = func
        super().__init__(**kwargs)
        # Inspect whether it's async/awaitable
        self._is_async = asyncio.iscoroutinefunction(self.func)

    async def __call__(self, *args, **kwargs):
        """
        Awaits asynchronous functions, calls synchronous functions in a thread.
        """
        if self._is_async:
            return await self.func(*args, **kwargs)
        else:
            async def __run__():
                return self.func(*args, **kwargs)

            return await __run__()


class _AsyncSeq(Function):
    """
    A class that represents the async seq function, which chains multiple asynchronous functions together.
    """
    functions: List[Function]

    def __init__(self, functions, **kwargs) -> None:
        if functions is not None:
            kwargs["functions"] = functions
        super().__init__(**kwargs)

    async def __call__(self, data: List[_TInput1]) -> _TResult:
        for func in self.functions:
            data = await func(data)
        return data


class _AsyncGather(Function):
    """
    A class that represents the async join function, which joins multiple asynchronous functions together.
    """
    functions: List[Function]

    def __init__(self, functions, **kwargs) -> None:
        if functions is not None:
            kwargs["functions"] = functions
        super().__init__(**kwargs)

    async def __call__(self, data: List[_TInput1]) -> _TResult:
        tasks = [func(data) for func in self.functions]
        return await asyncio.gather(*tasks)


class _AsyncRace(Function):
    """
    A class that represents the async race to the first function that returns.
    """
    functions: List[Function]

    def __init__(self, functions, **kwargs) -> None:
        if functions is not None:
            kwargs["functions"] = functions
        super().__init__(**kwargs)

    async def __call__(self, data: List[_TInput1]) -> _TResult:
        tasks = [func(data) for func in self.functions]
        return await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)


# Aliases for convenience
head = _Head
tail = _Tail
first = _Head
last = _Last
assert_quantity = _AssertQuantity
map = _Map
map_list = _MapList
flat_map = _FlatMap
filter = _Filter
reduce = _Reduce
pipe = _Pipe
future = _AsyncFunction
apipe = _AsyncSeq
gather = _AsyncGather
race = _AsyncRace


def _main():
    # Example usage of the classes
    data = [1, 2, 3, 4, 5]

    # Create a pipe with functions

    pipeline = Try.as_optional(
        map_list(lambda x: x * 2) +
        filter(lambda x: x > 5) +
        assert_quantity(">", 2)
    )

    # Apply the pipeline to the data
    result = pipeline(data)
    print(result)  # Output: [6, 8, 10]


if __name__ == "__main__":
    asyncio.run(future(_main)())
