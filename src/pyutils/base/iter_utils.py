import itertools
import logging
from typing import *

log = logging.Logger(__name__)

_TResult = TypeVar("_TResult")


def flatten(*lists):
    return itertools.chain(*lists)


def flatmap(func, *iterable):
    return itertools.chain.from_iterable(map(func, *iterable))


def groupby(iterable, key_fx, sort: bool = True) -> Dict[_TResult, List[_TResult]]:
    if sort:
        iterable.sort(key=key_fx)
    return {k: list(v) for k, v in itertools.groupby(iterable, key_fx)}


def groupbylist(iterable: object, key_fx: object, sort: bool = True) -> Dict[_TResult, List[_TResult]]:
    return groupby(iterable, key_fx, sort)


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


def put_and_get_existing(key, value, map: Dict):
    if key in map:
        return map[key]
    map[key] = value
    return value
