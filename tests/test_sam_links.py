"""Regression tests for sam_links — the canonical SAM.gov Apply/View destination.

Covers:
- Exact stored SAM.gov URL wins when present and safe.
- A canonical solicitation identifier generates a narrow prefilled search.
- Missing exact identifier falls back to a narrow search on the strongest id.
- No solicitation id → general agency/description search (final fallback only).
- Invalid / unsafe URLs (non-https, non-sam host, javascript:, userinfo) are
  rejected and never used as the exact destination.
- Internal ids are never placed in the outbound URL.
"""

import pytest

from sam_links import is_safe_external_url, resolve_apply_destination


# ── URL safety ───────────────────────────────────────────────────────────────

class TestSafeUrl:
    @pytest.mark.parametrize("url", [
        "https://sam.gov/opp/abc123/view",
        "https://www.sam.gov/opp/abc123/view",
        "https://SAM.GOV/opp/abc",              # case-insensitive host
    ])
    def test_accepts_sam_https(self, url):
        assert is_safe_external_url(url) is True

    @pytest.mark.parametrize("url", [
        "",
        None,
        "http://sam.gov/opp/abc",               # not https
        "javascript:alert(1)",
        "data:text/html,<script>",
        "https://evil.com/opp/abc",             # wrong host
        "https://sam.gov.evil.com/opp",         # suffix-spoof host
        "https://evil.com@sam.gov/opp",         # embedded userinfo
        "ftp://sam.gov/x",
        "//sam.gov/opp",                        # scheme-relative
        "notaurl",
    ])
    def test_rejects_unsafe(self, url):
        assert is_safe_external_url(url) is False


# ── Destination resolution precedence ────────────────────────────────────────

class TestResolveDestination:
    def test_exact_stored_url_wins(self):
        row = {
            "sam_url": "https://sam.gov/opp/deadbeef/view",
            "solicitation_id": "SOL-123",
            "agency": "DEFENSE",
            "description": "janitorial",
        }
        d = resolve_apply_destination(row)
        assert d["kind"] == "exact"
        assert d["is_exact"] is True
        assert d["url"] == "https://sam.gov/opp/deadbeef/view"

    def test_unsafe_stored_url_ignored_falls_to_solicitation(self):
        row = {
            "sam_url": "javascript:alert(1)",
            "solicitation_id": "SOL-123",
        }
        d = resolve_apply_destination(row)
        assert d["is_exact"] is False
        assert d["kind"] == "narrow_search"
        assert "SOL-123" in d["url"]
        assert d["url"].startswith("https://sam.gov/search/?keywords=")

    def test_solicitation_narrow_search_when_no_url(self):
        d = resolve_apply_destination({"solicitation_id": "ABC-2024-99"})
        assert d["kind"] == "narrow_search"
        assert "ABC-2024-99" in d["url"]

    def test_general_search_final_fallback(self):
        d = resolve_apply_destination({"agency": "DEFENSE", "description": "guard services"})
        assert d["kind"] == "general_search"
        assert d["is_exact"] is False
        assert d["url"].startswith("https://sam.gov/search/?keywords=")
        assert "DEFENSE" in d["url"]

    def test_internal_id_never_in_url(self):
        row = {
            "internal_id": "CONT_SECRET_INTERNAL_42",
            "agency": "NASA",
            "description": "launch support",
        }
        d = resolve_apply_destination(row)
        assert "CONT_SECRET_INTERNAL_42" not in d["url"]

    def test_deterministic(self):
        row = {"solicitation_id": "SOL-9"}
        assert resolve_apply_destination(row) == resolve_apply_destination(row)
