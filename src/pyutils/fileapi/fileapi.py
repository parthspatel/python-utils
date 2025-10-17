from fsspec.spec import AbstractBufferedFile
import logging
import tempfile
# noinspection PyProtectedMember
from io import TextIOWrapper
from typing import Union, TypeVar

import fsspec
import os
from contextlib import contextmanager

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from typing_extensions import Iterator, Optional, List, Generator, Tuple, Callable, Any, Dict, Self

from . import storage_options as lib_storage_options

_FileLike = TypeVar("_FileLike", bound=TextIOWrapper | AbstractBufferedFile)


# noinspection PyRedeclaration
class FileAPI:
    __logger__ = logging.getLogger(__name__)

    def __init__(
            self,
            path: str,
            *,
            fs: Optional[fsspec.AbstractFileSystem] = None,
            resolved_path: Optional[str] = None,
            storage_options: Optional[lib_storage_options.StorageOptions | dict] = None,
    ):
        """
        :param path: The path to the file or directory
        :param fs: The filesystem object.  If None, it will be inferred from the path.
        :param resolved_path: The resolved path.  If None, it will be inferred from the path.
        :param storage_options: The storage options.  If None, it will be inferred from the path and will supplement the default storage options.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> my_file = FileAPI("s3://bucket/path/to/file", storage_options={"auto_mkdir": True})
        >>> s3fs = fsspec.filesystem("s3")
        >>> my_file = FileAPI("s3://bucket/path/to/file", fs=s3fs)
        >>> my_file = FileAPI("s3://bucket/path/to/file", resolved_path="path/to/file")
        >>> my_file = FileAPI("s3://bucket/path/to/file", fs=s3fs, resolved_path="path/to/file")
        >>> my_file = FileAPI("s3://bucket/path/to/file", storage_options={"auto_mkdir": True}, resolved_path="path/to/file")
        >>> my_file = FileAPI("s3://bucket/path/to/file", fs=s3fs, storage_options={"auto_mkdir": True}, resolved_path="path/to/file")
        >>> my_file = FileAPI("s3://bucket/path/to/file", fs=s3fs, storage_options={"auto_mkdir": True})
        """

        self.path: str
        self.fs: fsspec.AbstractFileSystem
        self.resolved_path: str
        self.storage_options: lib_storage_options.StorageOptions

        if storage_options is None:
            storage_options = lib_storage_options.default()

        if isinstance(path, FileAPI):
            resolved_storage_options = {**path.storage_options, **storage_options}
            self.path = path.path_string
            self.fs = path.fs
            self.resolved_path = path.resolved_path
            self.storage_options = resolved_storage_options

        elif fs is None and resolved_path is None:
            self.path = path
            resolved_storage_options = lib_storage_options.default() if storage_options is None else storage_options
            self.fs, self.resolved_path = _get_fs_and_path(path, storage_options=resolved_storage_options)
            self.storage_options = resolved_storage_options

        else:
            self.path = path
            self.storage_options = storage_options

            if fs is None:
                if resolved_path is None:
                    self.fs, self.resolved_path = _get_fs_and_path(path, storage_options=storage_options)
                else:
                    self.resolved_path = resolved_path
                    self.fs, _ = _get_fs_and_path(path, storage_options=storage_options)
            elif resolved_path is None:
                self.fs = fs
                self.resolved_path = _get_path(fs, path)
            else:
                self.fs = fs
                self.resolved_path = resolved_path
                if "auto_mkdir" in self.storage_options:
                    self.fs.auto_mkdir = storage_options["auto_mkdir"]
                if "cache_type" in self.storage_options:
                    self.fs.cache_type = storage_options["cache_type"]

    @classmethod
    def apply(cls, path: Union[str, "FileAPI"], storage_options: Optional[Dict] = None) -> "FileAPI":
        """
        Create a FileAPI object from a path or another FileAPI object.
        A more optimized version of the constructor.
        :param path: The path to the file or directory, or a FileAPI object.
        :param storage_options: The storage options.  If None, it will be inferred from the path and will supplement the default storage options.
        :return: A FileAPI object.
        """
        if isinstance(path, FileAPI):
            resolved_storage_options = {**path.storage_options, **storage_options}
            return cls(
                path=path.path, fs=path.fs, resolved_path=path.resolved_path, storage_options=resolved_storage_options
            )
        else:
            resolved_storage_options = lib_storage_options.default() if storage_options is None else storage_options
            return cls(path=path, fs=None, resolved_path=None, storage_options=resolved_storage_options)

    def __str__(self):
        """
        Will return the path string.
        :return: The path string.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file)
        "s3://bucket/path/to/file"
        """
        return self.path_string

    def is_resolved_path(self) -> bool:
        """
        Checks if the path is resolved.
        :return: Boolean value, True if the path is resolved, False otherwise.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.is_resolved_path())
        False
        """
        return os.path.isabs(self.path)

    def mk_dirs(self):
        """
        Create the directories in the path.
        :return: None

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> my_file.mk_dirs()
        """
        self.fs.makedirs(self.resolved_path, exist_ok=True)

    def is_relative_path(self) -> bool:
        """
        Checks if the path is relative.
        :return: Boolean value, True if the path is relative, False otherwise.
        """
        return not os.path.isabs(self.path)

    def __truediv__(self, child_name: str) -> "FileAPI":
        """
        Concatenates the path with a child name.
        :param child_name:  The child name to concatenate.
        :return:  A new FileAPI object with the concatenated path.
        """
        return FileAPI(
            os.path.join(self.path, child_name), fs=self.fs, resolved_path=None, storage_options=self.storage_options
        )

    def __floordiv__(self, child_name: str) -> "FileAPI":
        """
        Concatenates the path with a child name.
        :param child_name: The child name to concatenate.
        :return: A new FileAPI object with the concatenated path.
        """
        return self.__truediv__(child_name)

    def delete(self) -> bool:
        """
        Delete the file.
        :return: True if the file was deleted, False otherwise.
        """
        try:
            self.fs.delete(self.resolved_path, recursive=True)
            return True
        except Exception as e:
            self.__logger__.error(f"Failed to delete file {self} due to exception {e}")
            return False

    def list_generator(self) -> Generator["FileAPI", None, None]:
        """
        List the files in the directory.
        :return: A list of FileAPI objects.
        """
        # noinspection PyProtectedMember
        path = self.fs._strip_protocol(self.resolved_path)
        for full_path in self.fs.ls(path, detail=False):
            self.fs.unstrip_protocol(full_path)
            yield FileAPI(
                full_path,
                fs=self.fs,
                resolved_path=full_path,
                storage_options=self.storage_options,
            )

    def list(self) -> List["FileAPI"]:
        """
        List the files in the directory.
        :return: A list of FileAPI objects.
        """
        return list(self.list_generator())

    def list_children_generator(
            self, max_depth=None, storage_options: Optional[lib_storage_options.StorageOptions] = None
    ) -> Generator["FileAPI", None, None]:
        """
        List the children of the file or directory.  If the file is a directory, it will list all the files in the directory.  If the file is a file, it will return the file itself.
        :param max_depth: The maximum depth to list the children.
        :param storage_options: The storage options.  If None, it will be inferred from the path and will supplement the default storage options.
        :return: A generator of FileAPI objects.
        """
        # noinspection PyProtectedMember
        path = self.fs._strip_protocol(self.resolved_path)

        if self.is_directory():
            resolved_storage_options = (
                {**self.storage_options, **storage_options} if storage_options else self.storage_options
            )
            for parent, dirs, files in self.fs.walk(path, maxdepth=max_depth, detail=False):
                for f in files:
                    full_path: str = str(os.path.join(parent, f))
                    full_qualified_path: str = self.fs.unstrip_protocol(full_path)
                    yield FileAPI(
                        full_qualified_path,
                        fs=self.fs,
                        resolved_path=full_path,
                        storage_options=resolved_storage_options,
                    )
        else:
            # if not a directory, return the file itself
            yield self

    def list_children(
            self, max_depth=None, storage_options: Optional[lib_storage_options.StorageOptions] = None
    ) -> List["FileAPI"]:
        """
        List the children of the file or directory.  If the file is a directory, it will list all the files in the directory.  If the file is a file, it will return the file itself.
        :param max_depth: The maximum depth to list the children.
        :param storage_options: The storage options.  If None, it will be inferred from the path and will supplement the default storage options.
        :return: A list of FileAPI objects.
        """
        return list(self.list_children_generator(max_depth, storage_options))

    def find_children(self, prefix: str) -> Iterator["FileAPI"]:
        self.__logger__.warning("find_children is untested")
        paths = self.fs.glob(os.path.join(self.resolved_path, prefix))
        for path in paths:
            yield FileAPI(path)

    def size(self) -> int:
        """
        Get the size of the file.
        :return: The size of the file in bytes.
        """
        self.__logger__.warning("find_children is untested")
        return self.fs.size(self.resolved_path)

    def md5(self) -> Optional[str]:
        """
        Get the MD5 checksum of the file.
        :return: The MD5 checksum of the file.
        """
        self.__logger__.warning("find_children is untested")
        return self.fs.checksum(self.resolved_path)

    @contextmanager
    def create_output_stream(self, mode="wb") -> Generator[_FileLike, None, None]:
        """
        Create an output stream for writing to the file.  This is a manged context, so the file will be closed automatically.
        :param mode: The mode to open the file in.
        :return: A file stream.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> with my_file.create_output_stream() as stream:
        >>>     stream.write("Hello, world!")
        """
        with self.fs.open(self.resolved_path, mode) as f:
            yield f

    @contextmanager
    def create_input_stream(self, mode="rb") -> Generator[_FileLike, None, None]:
        """
        Create an input stream for reading from the file.  This is a manged context, so the file will be closed automatically.
        :param mode: The mode to open the file in.
        :return: A file stream.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> with my_file.create_input_stream() as stream:
        >>>     print(stream.read())
        "Hello, world!"
        """
        with self.fs.open(self.resolved_path, mode) as f:
            yield f

    def read(self, codec: str = "utf-8") -> str:
        """
        Read the file and return the content as a string.
        :param codec: The codec to use for decoding the file.
        :return: The content of the file as a string.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> content = my_file.read()
        >>> print(content)
        "Hello, world!"
        """
        with self.create_input_stream() as stream:
            return stream.read().decode(codec)

    def create_input_stream_lines(self, codec: str = "utf-8") -> Generator[str, None, None]:
        """
        Create an input stream for reading from the file.  This is a manged context, so the file will be closed automatically.
        :param codec: The codec to use for decoding the file.
        :return: A generator of lines from the file.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> for _line in my_file.create_input_stream_lines():
        >>>     print(_line)
        "Hello, world!"
        """
        if self.is_directory():
            for child in self.list_children_generator():
                with child.create_input_stream() as source:
                    for line in source:
                        yield line.decode(codec)
        else:
            with self.create_input_stream() as source:
                for line in source:
                    yield line.decode(codec)

    def write(self, string: str) -> None:
        """
        Write a string to the file.
        :param string: The string to write.
        :return: None

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> my_file.write("Hello, world!")
        """
        with self.create_output_stream() as f:
            f.write(string.encode())

    def write_error(self, t: Exception):
        """
        Write the error to the file.
        :param t: The exception to write.
        :return: None

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> try:
        >>>     1/0
        >>> except Exception as e:
        >>>     my_file.write_error(e)
        """
        self.write(str(t))

    def with_output(self, f: Callable[[_FileLike], Any]):
        """
        Open an output stream and pass it to a function.
        :param f: The function to pass the stream to.
        :return: The return value of the function.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> def write_to_stream(_stream):
        >>>     _stream.write("Hello, world!")
        >>> my_file.with_output(write_to_stream)
        """
        with self.create_output_stream() as stream:
            return f(stream)

    def with_input(self, f: Callable[[_FileLike], Any]):
        """
        Open an input stream and pass it to a function.
        :param f: The function to pass the stream to.
        :return: The return value of the function.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> def read_from_stream(in_stream: _FileLike) -> Any:
        >>>     return in_stream.read()
        >>> content = my_file.with_input(read_from_stream)
        >>> print(content)
        "Hello, world!"
        """
        with self.create_input_stream() as stream:
            return f(stream)

    def exist(self) -> bool:
        """
        Check if the file exists.
        :return: True if the file exists, False otherwise.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.exist())
        True
        """
        return self.fs.exists(self.resolved_path)

    def exists(self) -> bool:
        """
        Check if the file exists.
        :return: True if the file exists, False otherwise.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.exists())
        True
        """
        return self.exist()

    def is_directory(self) -> bool:
        """
        Check if the file is a directory.
        :return: True if the file is a directory, False otherwise.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.is_directory())
        False
        """
        return self.fs.isdir(self.resolved_path)

    def is_file(self) -> bool:
        """
        Check if the file is a file.
        :return: True if the file is a file, False otherwise.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.is_file())
        True
        """
        return self.fs.isfile(self.resolved_path)

    def concat_from(self, source: Iterator["FileAPI"]) -> bool:
        """
        Concatenate the files from an iterator of FileAPI objects.
        :param source: The iterator of FileAPI objects to concatenate.
        :return: True if the files were concatenated, False otherwise.
        """
        with self.create_output_stream() as dest_stream:
            for src in source:
                with src.create_input_stream() as src_stream:
                    dest_stream.write(src_stream.read())
        return True

    def relativized(self, base: "FileAPI") -> str:
        """
        Get the relative path from the base path.
        :param base: The base path.
        :return: The relative path.

        :Example:
        >>> _base = FileAPI("s3://bucket/path")
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> print(my_file.relativized(_base))
        "to/file"
        """
        rel_name = self.path_string[self.path_string.index(base.path_string) + len(base.path_string):]
        rel_name = rel_name.lstrip("/")
        return rel_name

    def copy_to(self, dest: Union["FileAPI", str]) -> bool:
        """
        Copy the file to another file.
        Will throw a RuntimeError if the copy fails to copy any number of files, the copy operation will partially complete.
        :param dest: The destination file.
        :return: True if the file was copied, False otherwise.
        """
        errs = []
        dest = FileAPI.apply(dest, self.storage_options) if not isinstance(dest, FileAPI) else dest
        child = None
        dest_child = None
        if self.is_directory():
            listing = self.list_children()
            for child in listing:
                rel_name = child.path_string[child.path_string.index(self.path_string) + len(self.path_string):]
                rel_name = rel_name.lstrip("/")
                dest_child = dest / rel_name

                self.__logger__.debug(
                    f"Copying file from {{src = {child}, rel = {rel_name}, dest = {dest}, final = {dest_child}}}", )

                try:
                    with child.create_input_stream() as src_stream:
                        with dest_child.create_output_stream() as dest_stream:
                            dest_stream.write(src_stream.read())
                except Exception as e:
                    errs.append(e)
        else:
            try:
                with self.create_input_stream() as src_stream:
                    with dest.create_output_stream() as dest_stream:
                        dest_stream.write(src_stream.read())
            except Exception as e:
                errs.append(e)

        if len(errs) > 0:
            for e in errs:
                self.__logger__.error(f"Failed to copy file {child} to {dest_child} due to exception {e}")
            raise RuntimeError(
                f"Failed to copy file {child} to {dest_child} due to {len(errs)} exception{'s' if len(errs) > 1 else ''}")

        return True

    def move_to(self, dest: "FileAPI") -> bool:
        """
        Move the file to another file.  Performs a copy and delete.
        :param dest: The destination file.
        :return: True if the file was moved, False otherwise.
        """
        if self.copy_to(dest):
            return self.delete()
        return False

    def wc(self) -> Tuple[int, int, int]:
        """
        Get the line, word, and character count of the file.
        :return: A tuple of the line, word, and character count.

        :Example:
        >>> my_file = FileAPI("s3://bucket/path/to/file")
        >>> _lines, _words, _chars = my_file.wc()
        >>> print(_lines, _words, _chars)
        (1, 2, 13)
        """
        # stream the file and count the lines, words, and characters
        lines = 0
        words = 0
        chars = 0
        with self.create_input_stream() as stream:
            for byte in stream:
                chars += 1
                if byte == b"\n":
                    lines += 1
                if byte in b" \n":
                    words += 1

        return lines, words, chars

    @property
    def path_string(self) -> str:
        """
        Get the path string.
        :return: The path string.
        """
        return self.path

    @property
    def file_name(self) -> str:
        """
        Get the file name from the path.
        :return: The file name.
        """
        return os.path.basename(self.path_string)

    @property
    def directory_name(self) -> str:
        """
        Get the directory name from the path.
        :return: The directory name.
        """
        return os.path.dirname(self.path_string)

    @property
    def parent(self) -> "FileAPI":
        """
        Get the parent directory as a FileAPI object.
        :return: The parent directory as a FileAPI object.
        """
        path = self.fs._parent(self.path_string)
        return FileAPI(path, fs=self.fs, resolved_path=path, storage_options=self.storage_options)

    def stage_temp_file(self, dest: Optional["FileAPI"] = None) -> "FileAPI":
        """
        Stage the file to a temporary file.
        :return: A FileAPI object of the temporary file.
        """
        # logging.fatal("stage_temp_file does not work, temp file is immediately cleaned up")

        if dest:
            os.makedirs(dest.resolved_path, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dest.resolved_path, delete=False) as tmp_file:
                local_path = tmp_file.name
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                local_path = tmp_file.name
        local_fs = fsspec.filesystem("file")
        local_file_api = FileAPI(
            local_path, fs=local_fs, resolved_path=local_path, storage_options=self.storage_options
        )
        self.copy_to(local_file_api)

        if local_file_api.exist():
            return local_file_api
        else:
            raise Exception(f"Failed to stage file {self} to {local_file_api}")

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
            raise ValueError(f"Invalid FileAPI: {value}. Error: {e}")


# @lru_cache(maxsize=None)
def _get_fs_and_path(
        path: str, *, storage_options: Optional[lib_storage_options.StorageOptions] = None
) -> Tuple[fsspec.AbstractFileSystem, str]:
    fs, _, paths = fsspec.get_fs_token_paths(path, storage_options=storage_options)
    return fs, paths[0]


def _get_path(fs: fsspec.AbstractFileSystem, path: str) -> str:
    # noinspection PyProtectedMember
    return fs._strip_protocol(path)


def _make_hashable(d: Optional[Dict]) -> Tuple:
    return tuple(sorted(d.items())) if d else tuple()

# if __name__ == "__main__":
#     file = "gs://ontology-releases/ontology-releases/co5v23.3"
#     fileAPI = FileAPI.apply(file)
#     local = fileAPI.copy_to("/Users/parth/Documents/projects/ai/projects/agentic-resolve-demo/orchestrator/tmp/ont")
