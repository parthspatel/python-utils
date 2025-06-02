import logging
import threading

from fileapi import FileAPI


class FileSystemTester(object):
    """
    Tests the FileAPI class with different file systems
    """

    __logger = logging.getLogger(__name__)
    local_stage_lock = threading.Lock()

    class Config(object):
        """
        Configuration for the test,
        """

        def __init__(self, root: str):
            self.local_tmp = FileAPI("file://./tmp")
            self.local_stage = self.local_tmp / "stage.json"

            self.dir_00: FileAPI = FileAPI(root)
            self.file_01: FileAPI = self.dir_00 / "sample-file-01.json"

            self.dir_01: FileAPI = self.dir_00 / "sample-dir-01"
            self.file_02: FileAPI = self.dir_01 / "sample-file-02.json"
            self.file_03: FileAPI = self.dir_01 / "sample-file-03.json"

            self.dir_02: FileAPI = self.dir_01 / "sample-dir-02"
            self.file_04: FileAPI = self.dir_02 / "sample-file-04.json"
            self.file_05: FileAPI = self.dir_02 / "sample-file-05.json"

    def __init__(self, config: Config):
        self.config = config
        self.errors = list()

    @classmethod
    def apply(cls, prefix: str):
        config = cls.Config(prefix)
        return cls(config)

    def test(self, persist: bool = False):
        self.make_dirs()
        self.upload_files()
        self.read_file(self.config.file_01)
        self.list_dir(self.config.dir_00)
        self.list_file(self.config.file_01)
        self.list_dir(self.config.dir_01)
        self.list_dir(self.config.dir_02)
        self.stage_locally(self.config.file_01)

        if not persist:
            self.__logger.info("> Cleaning up")
            self.delete_file(self.config.file_01)
            self.delete_dir(self.config.dir_00)

    def make_dirs(self):
        self.__logger.info("> Making dirs")
        dirs = [self.config.dir_01, self.config.dir_02]
        for dir_ in dirs:
            dir_.mk_dirs()
        # Validation checks are not necessary here, not all file systems support mkdirs
        # GCS, for example, does not support mkdirs
        pass

    def upload_files(self):
        self.__logger.info("> Uploading files")
        files = [
            self.config.file_01,
            self.config.file_02,
            self.config.file_03,
            self.config.file_04,
            self.config.file_05,
        ]
        for file in files:
            file.write("> Hello, World!")
            if file.exists():
                self.__logger.info(f"> Created file {file}")
            else:
                self.errors.append(f"> Failed to create file {file}")
                self.__logger.error(f"> Failed to create file {file}")

    def read_file(self, file: FileAPI):
        self.__logger.info(f"> Reading {file}")
        contents = file.read()
        self.__logger.info(f"> Read {file}: {contents}")

    def delete_file(self, file: FileAPI):
        self.__logger.info(f"> Deleting {file}")
        file.delete()
        if not file.exists():
            self.__logger.info(f"> Deleted {file}")
        else:
            self.errors.append(f"> Failed to delete {file}")
            self.__logger.error(f"> Failed to delete {file}")

    def delete_dir(self, dir_: FileAPI):
        self.__logger.info(f"> Deleting {dir_}")
        dir_.delete()
        if not dir_.exists():
            self.__logger.info(f"> Deleted {dir_}")
        else:
            self.errors.append(f"> Failed to delete {dir_}")
            self.__logger.error(f"> Failed to delete {dir_}")

    def list_file(self, file: FileAPI):
        self.__logger.info(f"> Listing file {file}")
        children = file.list_children()
        if len(children) == 0:
            self.errors.append(f"> Failed to list children of file {file}, it should return itself")
            self.__logger.error(f"> Failed to list children of file {file}, it should return itself")
        else:
            for file in children:
                self.__logger.info(f"> Found file {file}")

    def list_dir(self, dir_: FileAPI):
        self.__logger.info(f"> Listing dir {dir_}")
        children = dir_.list_children()
        if len(children) == 0:
            self.errors.append(f"> Failed to list children of dir {dir_}")
            self.__logger.error(f"> Failed to list children of dir {dir_}")
        else:
            for file in dir_.list_children():
                self.__logger.info(f"> Found file {file}")

    def stage_locally(self, file: FileAPI):
        self.__logger.info(f"> Staging {file} locally")

        try:
            with self.local_stage_lock:
                file.stage_temp_file(self.config.local_stage)
            if self.config.local_stage.exists():
                self.__logger.info(f"> Staged {file} locally")
            else:
                self.errors.append(f"> Failed to stage {file} locally")
                self.__logger.error(f"> Failed to stage {file} locally")

            self.config.local_stage.delete()
            if not self.config.local_stage.exists():
                self.__logger.info(f"> Deleted {self.config.local_stage}")
            else:
                self.errors.append(f"> Failed to delete {self.config.local_stage}")
                self.__logger.error(f"> Failed to delete {self.config.local_stage}")
        except Exception as e:
            self.errors.append(f"> Failed to stage {file} locally: {e}")
            self.__logger.error(f"> Failed to stage {file} locally: {e}")
            raise e
