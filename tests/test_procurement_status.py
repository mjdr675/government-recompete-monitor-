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
