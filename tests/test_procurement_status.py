"""Tests for procurement_status — the canonical procurement-status classifier.

Procurement status (Open / Closed-Awarded / Closed-Expired / Cancelled) is
independent of recompete lifecycle. Covers:
- Open solicitation (live SAM notice type) → Open.
- Award record (no open notice) → Closed (Awarded).
- Expired contract (days_remaining < 0) → Closed (Expired).
- SAM award notice → Closed (Awarded).
- Cancellation notice → Cancelled.
- Status is NEVER inferred from a favourable lifecycle window.
"""

import procurement_status as ps


class TestStatusCode:
    def test_open_solicitation(self):
        row = {"sam_type": "Solicitation", "sam_url": "https://sam.gov/opp/x", "days_remaining": 200}
        assert ps.status_code(row) == ps.OPEN
        assert ps.procurement_status(row)["is_open"] is True

    def test_combined_synopsis_open(self):
        assert ps.status_code({"sam_type": "Combined Synopsis/Solicitation"}) == ps.OPEN

    def test_award_notice_is_closed_awarded(self):
        assert ps.status_code({"sam_type": "Award Notice", "days_remaining": 200}) == ps.CLOSED_AWARDED

    def test_no_sam_notice_defaults_to_awarded(self):
        # A plain USASpending award (no SAM opportunity signal), still running.
        assert ps.status_code({"sam_type": "", "days_remaining": 200}) == ps.CLOSED_AWARDED

    def test_expired_contract_is_closed_expired(self):
        assert ps.status_code({"sam_type": "", "days_remaining": -5}) == ps.CLOSED_EXPIRED

    def test_cancelled_notice(self):
        assert ps.status_code({"sam_type": "Cancellation"}) == ps.CANCELLED

    def test_status_never_inferred_from_lifecycle_window(self):
        # Lifecycle "Early/Prepare" (200 days) with no open SAM notice must NOT
        # be Open — it is the incumbent's award we hold on file.
        row = {"sam_type": "", "days_remaining": 200}
        assert ps.status_code(row) != ps.OPEN
        assert ps.procurement_status(row)["is_open"] is False


class TestIntentToBundleIsNotAwardEvidence:
    """"Intent to Bundle Requirements" is a pre-solicitation/planning notice,
    not evidence of an award. It must not force closed_awarded — it falls
    through to the days_remaining-based fallback like any other unmatched
    sam_type, so real expiry evidence still wins.
    """

    def test_not_in_award_sam_types(self):
        assert "intent to bundle requirements" not in ps.AWARD_SAM_TYPES

    def test_alone_with_expired_days_is_not_closed_awarded(self):
        # Previously this sam_type was in AWARD_SAM_TYPES, which forced
        # closed_awarded and ignored days_remaining entirely — an already
        # expired contract would still be reported as "already been awarded".
        row = {"sam_type": "Intent to Bundle Requirements", "days_remaining": -15}
        assert ps.status_code(row) == ps.CLOSED_EXPIRED
        assert ps.status_code(row) != ps.CLOSED_AWARDED

    def test_alone_produces_no_award_cta(self):
        row = {"sam_type": "Intent to Bundle Requirements", "days_remaining": -15}
        result = ps.procurement_status(row)
        assert result["code"] != ps.CLOSED_AWARDED
        assert result["label"] != ps.STATUS_LABELS[ps.CLOSED_AWARDED]
        assert "already been awarded" not in result["explanation"].lower()

    def test_distinct_from_actual_award_notice(self):
        # A real award notice still forces closed_awarded regardless of days —
        # "intent to bundle" is no longer treated the same way.
        bundle = {"sam_type": "Intent to Bundle Requirements", "days_remaining": -15}
        award = {"sam_type": "Award Notice", "days_remaining": -15}
        assert ps.status_code(bundle) != ps.status_code(award)
        assert ps.status_code(award) == ps.CLOSED_AWARDED

    def test_existing_award_classifications_still_pass(self):
        for sam_type in [
            "Award Notice",
            "Justification",
            "Fair Opportunity / Limited Sources Justification",
            "Modification/Amendment",
        ]:
            assert ps.status_code({"sam_type": sam_type, "days_remaining": 200}) == ps.CLOSED_AWARDED
            assert ps.status_code({"sam_type": sam_type, "days_remaining": -10}) == ps.CLOSED_AWARDED


class TestClassificationDict:
    def test_labels_and_badges(self):
        assert ps.procurement_status({"sam_type": "Solicitation"})["label"] == "Open"
        assert ps.procurement_status({"sam_type": "Award Notice"})["label"] == "Closed (Awarded)"
        assert ps.procurement_status({"days_remaining": -1})["label"] == "Closed (Expired)"
        assert ps.procurement_status({"sam_type": "Cancellation"})["label"] == "Cancelled"
        # Compact card badge collapses both closed variants to "Closed".
        assert ps.procurement_status({"sam_type": "Award Notice"})["badge"] == "Closed"
        assert ps.procurement_status({"days_remaining": -1})["badge"] == "Closed"
        assert ps.procurement_status({"sam_type": "Solicitation"})["badge"] == "Open"

    def test_awarded_explanation_does_not_imply_proposal(self):
        expl = ps.procurement_status({"sam_type": "Award Notice"})["explanation"].lower()
        assert "already been awarded" in expl
        assert "cannot submit" in expl

    def test_is_awarded_flag(self):
        assert ps.procurement_status({"sam_type": "Award Notice"})["is_awarded"] is True
        assert ps.procurement_status({"days_remaining": -2})["is_awarded"] is True
        assert ps.procurement_status({"sam_type": "Solicitation"})["is_awarded"] is False
