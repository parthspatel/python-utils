from enum import Enum
from typing_extensions import TypedDict, NotRequired


class FileCache(Enum):
    SIMPLE = "simplecache"
    FILE = "filecache"
    # noinspection SpellCheckingInspection
    BLOCK = "blockcache"
    NONE = None  # use for eg FTP


_DEFAULT_CACHE_TYPE = FileCache.NONE


class StorageOptions(TypedDict):
    auto_mkdir: NotRequired[bool]
    cache_type: NotRequired[FileCache]


def create(auto_mkdir: bool = True, cache_type: FileCache = _DEFAULT_CACHE_TYPE) -> "StorageOptions":
    return {"auto_mkdir": auto_mkdir, "cache_type": cache_type}


def default() -> "StorageOptions":
    return create()
