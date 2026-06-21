"""
Shared pytest fixtures and configuration for the Recompete.us test suite.

Two autouse fixtures handle test isolation:

1. _mock_email_task_delay: send_email_task.delay() hangs for ~20 seconds in
   CI/dev when Redis is not running (Celery retries 20× at 1s intervals).
   Patching it to a no-op keeps every registration fast without affecting
   tests that call .apply() directly (test_email_task.py).

2. _reset_rate_limiter: the in-memory rate limit counter accumulates across
   tests. Resetting it before each test prevents the 11th+ registration from
   being rejected with 429, which would leave test clients unauthenticated.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_email_task_delay():
    with patch("tasks.send_email_task.delay", MagicMock(return_value=None)):
        yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    import app as flask_app
    flask_app.limiter.reset()
    yield
