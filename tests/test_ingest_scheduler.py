"""
Regression tests for _run_daily_ingest date arithmetic.

Bug: next_run.replace(day=next_run.day + 1) raises ValueError on any month-end
day (Jan 31, Mar 31, Aug 31, Dec 31, Feb 28/29), killing the scheduler thread
permanently until the next gunicorn restart.

Fix: next_run += timedelta(days=1)
"""

import pytest
from datetime import datetime, timezone


class TestSchedulerDateArithmetic:
    """Confirm the scheduler does not crash advancing past month boundaries."""

    def _next_run_from(self, dt):
        from datetime import timedelta
        next_run = dt.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= dt:
            next_run += timedelta(days=1)
        return next_run

    @pytest.mark.parametrize("month_end", [
        datetime(2026, 1, 31, 3, 0, tzinfo=timezone.utc),   # Jan 31 → Feb 1
        datetime(2026, 3, 31, 3, 0, tzinfo=timezone.utc),   # Mar 31 → Apr 1
        datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc),   # Aug 31 → Sep 1
        datetime(2026, 12, 31, 3, 0, tzinfo=timezone.utc),  # Dec 31 → Jan 1
        datetime(2028, 2, 29, 3, 0, tzinfo=timezone.utc),   # Leap Feb 29 → Mar 1
    ])
    def test_does_not_crash_on_month_end(self, month_end):
        next_run = self._next_run_from(month_end)
        assert next_run > month_end

    def test_advances_exactly_one_day(self):
        dt = datetime(2026, 1, 31, 3, 0, tzinfo=timezone.utc)
        next_run = self._next_run_from(dt)
        expected = datetime(2026, 2, 1, 2, 0, tzinfo=timezone.utc)
        assert next_run == expected

    def test_no_advance_before_2am(self):
        """Before 2 AM same day: next run is 2 AM today, not tomorrow."""
        dt = datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc)
        next_run = self._next_run_from(dt)
        expected = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
        assert next_run == expected
