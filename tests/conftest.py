"""Pytest configuration and shared fixtures."""
import logging

import pytest


@pytest.fixture(autouse=True)
def cleanup_logging_handlers():
    """
    Automatically clean up logging handlers after each test.

    This fixture runs after every test to ensure all file handlers are closed,
    which is critical on Windows where open file handles prevent file deletion.
    This is a safety net in addition to the runtime cleanup in the main application.
    """
    yield  # Let the test run first

    # After the test completes, shut down all logging
    logging.shutdown()
