import itertools
import logging
from typing import *

_logger = logging.getLogger(__name__)

_TResult = TypeVar("_TResult")


def flatten(*lists):
    return itertools.chain(*lists)


def flatmap(func, *iterable):
    return itertools.chain.from_iterable(map(func, *iterable))


# noinspection SpellCheckingInspection
def groupby(iterable, key_fx, sort_keys: bool = True, inner_sort_fx: Optional[Callable] = None) -> Dict[_TResult, List[_TResult]]:
    if sort_keys:
        iterable.sort(key=key_fx)

    if inner_sort_fx:
        def __inner(v: iterable) -> list:
            data = list(v)
            data.sort(key=inner_sort_fx)
            return data
    else:
        def __inner(v: iterable) -> list:
            return list(v)

    return {k: __inner(v) for k, v in itertools.groupby(iterable, key_fx)}


# noinspection SpellCheckingInspection
def groupbylist(iterable: object, key_fx: object, sort_keys: bool = True, inner_sort_fx: Optional[Callable] = None) -> Dict[_TResult, List[_TResult]]:
    return groupby(iterable, key_fx, sort_keys, inner_sort_fx)


# noinspection SpellCheckingInspection
def groupbyset(iterable, key_fx, sort: bool = True) -> Dict[_TResult, Set[_TResult]]:
    if sort:
        iterable.sort(key=key_fx)
    return {k: set(v) for k, v in itertools.groupby(iterable, key_fx)}


# iterate over items in chunks
def chunk(iterable, size=10):
    iterator = iter(iterable)
    for first in iterator:
        yield itertools.chain([first], itertools.islice(iterator, size - 1))


async def chunk_async(iterable, size=10):
    iterator = iter(iterable)
    async for first in iterator:
        yield itertools.chain([first], itertools.islice(iterator, size - 1))


def put_and_get_existing(key, value, lookup: Dict):
    if key in lookup:
        return lookup[key]
    lookup[key] = value
    return value
