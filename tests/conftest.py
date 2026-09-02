import logging
import sys

import pytest
from loguru import logger


@pytest.fixture(autouse=True, scope="session")
def enable_debug_logging():
    logger.remove()
    sink_id = logger.add(sys.stderr, level=logging.DEBUG)

    yield

    logger.remove(sink_id)
    # TODO: restore the actual real logger here? This is just guessing?
    logger.add(sys.stderr, level="INFO")
