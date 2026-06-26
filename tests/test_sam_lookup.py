"""Tests for sam_lookup.lookup_solicitation.

Covers the rate-limit (429) visibility/cooldown behavior added so an exhausted
SAM.gov quota is no longer silently indistinguishable from "no match".
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

import sam_lookup


class _Resp:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def _reset_cooldown(monkeypatch):
    # Isolate the module-level cooldown between tests and ensure a key is set.
    monkeypatch.setattr(sam_lookup, "_rate_limited_until", 0.0)
    monkeypatch.setenv("SAM_API_KEY", "test-key")
    yield


_MATCH = {"opportunitiesData": [{
    "title": "Janitorial Services",
    "type": "Solicitation",
    "responseDeadLine": "2026-09-01",
    "setAside": "SBA",
    "naicsCode": "561720",
    "uiLink": "https://sam.gov/opp/abc",
}]}


def test_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    assert sam_lookup.lookup_solicitation("SOL-1") is None


def test_no_solnum_returns_none():
    assert sam_lookup.lookup_solicitation("") is None


def test_match_returns_fields():
    with patch("sam_lookup.requests.get", return_value=_Resp(200, _MATCH)):
        out = sam_lookup.lookup_solicitation("SOL-1")
    assert out["sam_url"] == "https://sam.gov/opp/abc"
    assert out["sam_naics"] == "561720"


def test_empty_opportunities_returns_none():
    with patch("sam_lookup.requests.get", return_value=_Resp(200, {"opportunitiesData": []})):
        assert sam_lookup.lookup_solicitation("SOL-1") is None


def test_429_logs_and_returns_none(caplog):
    resp = _Resp(429, headers={"Retry-After": "60"})
    with patch("sam_lookup.requests.get", return_value=resp):
        with caplog.at_level(logging.WARNING, logger="ingest"):
            assert sam_lookup.lookup_solicitation("SOL-1") is None
    assert any("rate-limited (429" in r.message for r in caplog.records)


def test_429_trips_cooldown_skips_further_calls():
    """After a 429, subsequent lookups short-circuit without another HTTP call."""
    mock_get = MagicMock(return_value=_Resp(429))
    with patch("sam_lookup.requests.get", mock_get):
        assert sam_lookup.lookup_solicitation("SOL-1") is None  # trips cooldown
        assert sam_lookup.lookup_solicitation("SOL-2") is None  # skipped
        assert sam_lookup.lookup_solicitation("SOL-3") is None  # skipped
    assert mock_get.call_count == 1


def test_auth_error_logged_distinctly(caplog):
    with patch("sam_lookup.requests.get", return_value=_Resp(403)):
        with caplog.at_level(logging.WARNING, logger="ingest"):
            assert sam_lookup.lookup_solicitation("SOL-1") is None
    assert any("auth error (403" in r.message for r in caplog.records)


def test_connection_error_returns_none(caplog):
    with patch("sam_lookup.requests.get", side_effect=Exception("boom")):
        with caplog.at_level(logging.WARNING, logger="ingest"):
            assert sam_lookup.lookup_solicitation("SOL-1") is None
    assert any("connection error" in r.message for r in caplog.records)
