import logging
import logging
import os

from tests import FileSystemTester
import dotenv
import pytest

_logger = logging.getLogger(__name__)
dotenv.load_dotenv()


def test_gcs() -> None:
    logging.configure(logging.INFO)

    root = os.getenv("GCS_ROOT")
    if not root:
        return pytest.skip("GCS_ROOT environment variable not set.")

    tester = FileSystemTester.apply(root)
    tester.test()
    if len(tester.errors) != 0:
        for error in tester.errors:
            _logger.error(error)
        raise Exception("GCS test failed.")
    else:
        _logger.info("GCS test completed successfully.")
        return None
