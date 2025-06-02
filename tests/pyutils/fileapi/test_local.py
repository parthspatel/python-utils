import logging

from tests import FileSystemTester

_logger = logging.getLogger(__name__)


def test_local():
    logging.configure(logging.INFO)

    tester = FileSystemTester.apply("file://./tmp")
    tester.test()
    if len(tester.errors) != 0:
        for error in tester.errors:
            _logger.error(error)
        raise Exception("Local test failed.")
    else:
        _logger.info("Local test completed successfully.")
