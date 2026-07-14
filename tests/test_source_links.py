"""Tests for source_links — the canonical, source-aware outbound link resolver.

Covers PM decisions A (source-aware destination), B (labels), C (URL safety):
- Stored exact SAM.gov opportunity URL resolves directly.
- Stored exact USASpending award URL resolves directly (source routed by host).
- A USASpending-originated award (generated_internal_id) resolves to USASpending,
  never to SAM.gov, even when a solicitation number is also present.
- The N6274219F0181 fixture exercises the strongest safe supported path.
- Solicitation fallback uses a source-specific SAM search.
- General SAM search is only the final fallback.
- Unknown source produces no fabricated link.
- HTTP, spoofed hosts, javascript:, data:, malformed and credential-bearing
  URLs are rejected.
- Destination-aware CTA labels match the record/source type.
"""

import pytest

from source_links import (
    is_safe_source_url,
    resolve_source_destination,
    SAM,
    USASPENDING,
)


# ── URL safety (PM decision C) ────────────────────────────────────────────────

class TestSafeUrl:
    @pytest.mark.parametrize("url", [
        "https://sam.gov/opp/abc123/view",
        "https://www.sam.gov/opp/abc123/view",
        "https://SAM.GOV/opp/abc",
        "https://www.usaspending.gov/award/CONT_AWD_X",
        "https://usaspending.gov/award/CONT_AWD_X",
    ])
    def test_accepts_supported_https(self, url):
        assert is_safe_source_url(url) is True

    @pytest.mark.parametrize("url", [
        "", None,
        "http://sam.gov/opp/abc",                 # not https
        "http://www.usaspending.gov/award/x",     # not https
        "javascript:alert(1)",
        "data:text/html,<script>",
        "https://evil.com/opp/abc",               # wrong host
        "https://sam.gov.evil.com/opp",           # suffix-spoof host
        "https://usaspending.gov.evil.com/award", # suffix-spoof host
        "https://evil.com@sam.gov/opp",           # embedded userinfo
        "ftp://sam.gov/x",
        "//sam.gov/opp",                          # scheme-relative
        "notaurl",
    ])
    def test_rejects_unsafe(self, url):
        assert is_safe_source_url(url) is False


# ── Destination resolution precedence (PM decision A) ─────────────────────────

class TestResolution:
    def test_stored_sam_opportunity_wins(self):
        d = resolve_source_destination({
            "sam_url": "https://sam.gov/opp/deadbeef/view",
            "generated_internal_id": "CONT_AWD_X_1_Y_1",
            "solicitation_id": "SOL-123",
            "agency": "DEFENSE",
            "description": "janitorial",
        })
        assert d["tier"] == 1
        assert d["source"] == SAM
        assert d["destination_type"] == "opportunity"
        assert d["is_exact"] is True
        assert d["url"] == "https://sam.gov/opp/deadbeef/view"
        assert d["label"] == "View Opportunity"

    def test_stored_usaspending_award_url_resolves_to_usaspending(self):
        d = resolve_source_destination({
            "sam_url": "https://www.usaspending.gov/award/CONT_AWD_STORED",
        })
        assert d["tier"] == 1
        assert d["source"] == USASPENDING
        assert d["destination_type"] == "award"
        assert d["url"] == "https://www.usaspending.gov/award/CONT_AWD_STORED"
        assert d["label"] == "View Award"

    def test_usaspending_award_from_generated_id_not_sam(self):
        # No stored sam_url: a USASpending-originated award must resolve to its
        # USASpending award page, NOT a SAM search — even with a solicitation id.
        d = resolve_source_destination({
            "sam_url": "",
            "generated_internal_id": "CONT_AWD_N6274219F0181_9700_N6274215D1818_9700",
            "solicitation_id": "N6274214R1888",
            "agency": "DEPARTMENT OF DEFENSE",
            "description": "base operations support",
        })
        assert d["tier"] == 2
        assert d["source"] == USASPENDING
        assert d["destination_type"] == "award"
        assert d["is_exact"] is True
        assert d["url"] == (
            "https://www.usaspending.gov/award/"
            "CONT_AWD_N6274219F0181_9700_N6274215D1818_9700"
        )
        assert d["label"] == "View Award"
        assert "sam.gov" not in d["url"]

    def test_piid_n6274219f0181_strongest_safe_path(self):
        # The exact record the walkthrough flagged: strongest safe path is the
        # USASpending award page derived from the stable permalink id.
        d = resolve_source_destination({
            "sam_url": "",
            "generated_internal_id": "CONT_AWD_N6274219F0181_9700_N6274215D1818_9700",
            "solicitation_id": "N6274214R1888",
        })
        assert d["source"] == USASPENDING
        assert d["destination_type"] == "award"
        assert d["url"].endswith("CONT_AWD_N6274219F0181_9700_N6274215D1818_9700")

    def test_solicitation_fallback_is_source_specific_search(self):
        d = resolve_source_destination({
            "sam_url": "",
            "generated_internal_id": "",
            "solicitation_id": "ABC-2024-99",
        })
        assert d["tier"] == 3
        assert d["source"] == SAM
        assert d["destination_type"] == "search"
        assert d["is_exact"] is False
        assert d["url"].startswith("https://sam.gov/search/?keywords=")
        assert "ABC-2024-99" in d["url"]
        assert d["label"] == "View Source"

    def test_general_search_is_final_fallback(self):
        d = resolve_source_destination({
            "agency": "DEFENSE", "description": "guard services",
        })
        assert d["tier"] == 4
        assert d["destination_type"] == "search"
        assert d["url"].startswith("https://sam.gov/search/?keywords=")
        assert "DEFENSE" in d["url"]

    def test_unknown_source_no_fabricated_link(self):
        d = resolve_source_destination({})
        assert d["tier"] == 5
        assert d["url"] is None
        assert d["destination_type"] is None
        assert d["label"] is None

    def test_bad_generated_id_not_fabricated_into_url(self):
        # A generated_internal_id with unexpected characters is refused rather
        # than pasted into a URL — falls through to the search fallback.
        d = resolve_source_destination({
            "generated_internal_id": "CONT_AWD X/../evil",
            "solicitation_id": "SOL-9",
        })
        assert d["source"] == SAM
        assert d["destination_type"] == "search"
        assert "evil" not in d["url"]

    def test_unsafe_stored_url_ignored_falls_through(self):
        for bad in ("javascript:alert(1)", "http://sam.gov/x", "https://evil.com@sam.gov/x"):
            d = resolve_source_destination({"sam_url": bad, "solicitation_id": "SOL-1"})
            assert d["url"].startswith("https://sam.gov/search/?keywords=")
            assert d["is_exact"] is False

    def test_internal_id_never_in_url(self):
        d = resolve_source_destination({
            "internal_id": "CONT_SECRET_INTERNAL_42",
            "agency": "NASA", "description": "launch support",
        })
        assert "CONT_SECRET_INTERNAL_42" not in (d["url"] or "")

    def test_deterministic(self):
        row = {"generated_internal_id": "CONT_AWD_Z_1_Z_1"}
        assert resolve_source_destination(row) == resolve_source_destination(row)
