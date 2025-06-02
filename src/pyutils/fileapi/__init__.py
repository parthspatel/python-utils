from .fileapi import *
from .storage_options import *


# noinspection PyShadowingBuiltins
@contextmanager
def open(path: Union[str, FileAPI], mode: str):
    """
    Open a file with the given path and mode.
    """
    with FileAPI.apply(path=path).create_input_stream(mode=mode) as io_stream:
        yield io_stream
