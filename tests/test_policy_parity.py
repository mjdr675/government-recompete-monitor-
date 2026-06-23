"""Snapshot parity harness: legacy access model vs. unified (workspace-sole) model.

Classification rules (strict, no interpretation):
    MATCH           — legacy and unified produce identical (state, redirect) outcome.
    EXPECTED_DELTA  — divergence is declared in access_contract.EXPECTED_BEHAVIORAL_DELTAS.
    UNEXPECTED_DRIFT — any divergence with no matching delta entry → test FAILS.

UNEXPECTED_DRIFT == 0 is the gate. A single unclassified divergence is a
regression, not a discussion.

Snapshot contract:
    Each snapshot is a frozen dict evaluated ONCE by both policies on the SAME
    immutable input. No DB reads, no clock reads outside the injected NOW.
    This eliminates nondeterminism: both evaluators see identical facts.
"""
from datetime import datetime, timedelta, timezone

import pytest

import access_contract
from access import (
    get_access_state,
    is_access_granted,
    ALLOWED, TRIALING, BILLING_REQUIRED, EXPIRED,
)
from access_contract import (
    EXPECTED_BEHAVIORAL_DELTAS,
    all_delta_ids,
    is_declared_delta,
)

# ---------------------------------------------------------------------------
# Harness clock — injected into every evaluation; never reads the real clock
# ---------------------------------------------------------------------------
NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _ts(days):
    return (NOW + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Legacy policy evaluator
#
# Mirrors the pre-workspace-authority logic: user OR workspace can grant access.
# Also mirrors the legacy redirect map (/subscribe for user billing, /settings/billing
# for workspace billing redirect, None when granted).
# ---------------------------------------------------------------------------

_LEGACY_SUBSCRIBE_PATHS = {"/subscribe", "/subscribe?expired=1"}
_LEGACY_PROTECTED_PATHS = {
    "/contracts", "/dashboard", "/watchlist", "/pipeline",
    "/settings", "/settings/billing",
}
_LEGACY_GATED_PATHS = {"/contracts", "/dashboard", "/pipeline", "/settings"}


def _legacy_access_state(user, workspace, now):
    """Hybrid OR-across-principals: user OR workspace can grant access."""
    user = user or {}
    workspace = workspace or {}

    # Workspace active subscription
    if workspace.get("subscription_status") == "active":
        return ALLOWED

    # Workspace trial
    ws_trial_end = workspace.get("trial_end_at")
    if ws_trial_end:
        try:
            dt = datetime.fromisoformat(ws_trial_end)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return TRIALING if now <= dt else EXPIRED
        except (ValueError, TypeError):
            pass

    # User active subscription (legacy fallback)
    if user.get("subscription_status") == "active":
        return ALLOWED

    # User trial (legacy fallback)
    user_trial_end = user.get("trial_ends_at")
    if user_trial_end:
        try:
            dt = datetime.fromisoformat(user_trial_end)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return TRIALING if now <= dt else EXPIRED
        except (ValueError, TypeError):
            pass

    return BILLING_REQUIRED


def _legacy_redirect(state, path):
    """Legacy redirect logic: denied workspace → /settings/billing; denied user → /subscribe."""
    if state in (ALLOWED, TRIALING):
        return None
    # The redirect destination in legacy code depends on which gate fired;
    # we model the observable output: paths in _LEGACY_GATED_PATHS redirect
    # to /subscribe for user-level denial, but legacy workspace gate redirects
    # to /settings/billing (the legacy workspace billing gate was already unified).
    if state == EXPIRED:
        return "/settings/billing?expired=1"
    return "/subscribe"


def _unified_redirect(state):
    """Unified redirect map (web layer): no /subscribe, only /settings/billing."""
    if state in (ALLOWED, TRIALING):
        return None
    if state == EXPIRED:
        return "/settings/billing?expired=1"
    return "/settings/billing"


# ---------------------------------------------------------------------------
# Delta classifier
# ---------------------------------------------------------------------------

MATCH = "MATCH"
EXPECTED_DELTA = "EXPECTED_DELTA"
UNEXPECTED_DRIFT = "UNEXPECTED_DRIFT"


def _classify(legacy_state, legacy_redirect, unified_state, unified_redirect_path, path):
    """Return (classification, delta_id_or_None)."""
    if (legacy_state == unified_state and legacy_redirect == unified_redirect_path):
        return MATCH, None

    # Check which declared deltas apply to this divergence
    matched_delta = None

    # billing_destination_normalization: /subscribe → /settings/billing
    if (
        unified_redirect_path in ("/settings/billing", "/settings/billing?expired=1")
        and legacy_redirect in ("/subscribe", "/subscribe?expired=1")
        and is_declared_delta("billing_destination_normalization")
    ):
        matched_delta = "billing_destination_normalization"

    # workspace_trumps_user_trial covers two scenarios caused by user state driving legacy:
    # (a) grant/deny flip: legacy granted via user entitlement, unified correctly denies
    #     (or workspace active grants where user-alone would deny)
    # (b) denial-reason shift: user's expired trial made legacy say EXPIRED, but unified
    #     sees no workspace at all and says BILLING_REQUIRED — different denial, same cause
    if matched_delta is None and (
        (
            is_access_granted(unified_state) != is_access_granted(legacy_state)
            or (legacy_state == EXPIRED and unified_state == BILLING_REQUIRED)
        )
        and is_declared_delta("workspace_trumps_user_trial")
    ):
        matched_delta = "workspace_trumps_user_trial"

    # legacy_watchlist_grant_removal: previously ungated paths now evaluated
    if matched_delta is None and (
        path not in _LEGACY_GATED_PATHS
        and unified_state != legacy_state
        and is_declared_delta("legacy_watchlist_grant_removal")
    ):
        matched_delta = "legacy_watchlist_grant_removal"

    if matched_delta is not None:
        return EXPECTED_DELTA, matched_delta

    return UNEXPECTED_DRIFT, None


# ---------------------------------------------------------------------------
# Frozen snapshot corpus
#
# Each entry: (label, user_dict, workspace_dict, request_path)
# Snapshots are immutable — they represent a moment in time with fixed inputs.
# Adding a new behavioral divergence requires a new delta, not a new snapshot
# workaround.
# ---------------------------------------------------------------------------

_SNAPSHOTS = [
    # --- Workspace: active subscription ---
    ("active_ws_no_user",
     {},
     {"subscription_status": "active"},
     "/dashboard"),
    ("active_ws_expired_user",
     {"subscription_status": "trialing", "trial_ends_at": _ts(-5)},
     {"subscription_status": "active"},
     "/contracts"),
    ("active_ws_active_user",
     {"subscription_status": "active"},
     {"subscription_status": "active"},
     "/pipeline"),

    # --- Workspace: live trial ---
    ("live_ws_trial_no_user",
     {},
     {"subscription_status": "trialing", "trial_end_at": _ts(3)},
     "/dashboard"),
    ("live_ws_trial_expired_user",
     {"subscription_status": "trialing", "trial_ends_at": _ts(-2)},
     {"subscription_status": "trialing", "trial_end_at": _ts(3)},
     "/contracts"),

    # --- Workspace: expired trial ---
    ("expired_ws_trial_no_user",
     {},
     {"subscription_status": "trialing", "trial_end_at": _ts(-1)},
     "/dashboard"),
    ("expired_ws_trial_active_user",
     {"subscription_status": "active"},
     {"subscription_status": "trialing", "trial_end_at": _ts(-1)},
     "/contracts"),
    ("expired_ws_trial_live_user_trial",
     {"subscription_status": "trialing", "trial_ends_at": _ts(2)},
     {"subscription_status": "trialing", "trial_end_at": _ts(-1)},
     "/pipeline"),

    # --- No workspace (None) ---
    ("no_workspace_active_user",
     {"subscription_status": "active"},
     None,
     "/dashboard"),
    ("no_workspace_live_user_trial",
     {"subscription_status": "trialing", "trial_ends_at": _ts(1)},
     None,
     "/contracts"),
    ("no_workspace_expired_user_trial",
     {"subscription_status": "trialing", "trial_ends_at": _ts(-3)},
     None,
     "/dashboard"),
    ("no_workspace_no_user",
     {},
     None,
     "/contracts"),

    # --- Empty workspace dict ---
    ("empty_ws_active_user",
     {"subscription_status": "active"},
     {},
     "/dashboard"),
    ("empty_ws_no_user",
     {},
     {},
     "/pipeline"),

    # --- Previously ungated paths (legacy_watchlist_grant_removal) ---
    ("watchlist_expired_ws",
     {},
     {"subscription_status": "trialing", "trial_end_at": _ts(-1)},
     "/watchlist"),
    ("watchlist_no_ws_active_user",
     {"subscription_status": "active"},
     None,
     "/watchlist"),
    ("settings_expired_ws",
     {},
     {"subscription_status": "trialing", "trial_end_at": _ts(-1)},
     "/settings"),

    # --- Routing: billing destination ---
    ("billing_required_on_gated_path",
     {},
     None,
     "/contracts"),
    ("billing_required_on_dashboard",
     {},
     None,
     "/dashboard"),
    ("expired_ws_on_contracts",
     {},
     {"subscription_status": "canceled", "trial_end_at": _ts(-1)},
     "/contracts"),
]


# ---------------------------------------------------------------------------
# Harness execution + parameterized test
# ---------------------------------------------------------------------------

def _run_snapshot(label, user, workspace, path):
    """Evaluate one snapshot under both policies. Returns result dict."""
    legacy_state = _legacy_access_state(user, workspace, NOW)
    legacy_redir = _legacy_redirect(legacy_state, path)

    unified_state = get_access_state(user, workspace, now=NOW)
    unified_redir = _unified_redirect(unified_state)

    classification, delta_id = _classify(
        legacy_state, legacy_redir, unified_state, unified_redir, path
    )

    return {
        "label": label,
        "legacy_state": legacy_state,
        "legacy_redirect": legacy_redir,
        "unified_state": unified_state,
        "unified_redirect": unified_redir,
        "classification": classification,
        "delta_id": delta_id,
    }


@pytest.mark.parametrize("label,user,workspace,path", _SNAPSHOTS,
                         ids=[s[0] for s in _SNAPSHOTS])
def test_snapshot_no_unexpected_drift(label, user, workspace, path):
    """Every snapshot must be MATCH or a declared EXPECTED_DELTA. UNEXPECTED_DRIFT = failure."""
    result = _run_snapshot(label, user, workspace, path)
    assert result["classification"] != UNEXPECTED_DRIFT, (
        f"[{label}] UNEXPECTED_DRIFT: "
        f"legacy=({result['legacy_state']}, {result['legacy_redirect']!r}) "
        f"vs unified=({result['unified_state']}, {result['unified_redirect']!r}) "
        f"on path={path!r}. "
        "Either declare a delta in access_contract.EXPECTED_BEHAVIORAL_DELTAS "
        "or fix the regression."
    )


@pytest.mark.parametrize("label,user,workspace,path", _SNAPSHOTS,
                         ids=[s[0] for s in _SNAPSHOTS])
def test_expected_delta_maps_to_declared_id(label, user, workspace, path):
    """Any EXPECTED_DELTA result must carry a valid delta ID from the contract."""
    result = _run_snapshot(label, user, workspace, path)
    if result["classification"] == EXPECTED_DELTA:
        assert result["delta_id"] is not None, (
            f"[{label}] classified EXPECTED_DELTA but delta_id is None."
        )
        assert is_declared_delta(result["delta_id"]), (
            f"[{label}] delta_id={result['delta_id']!r} is not in EXPECTED_BEHAVIORAL_DELTAS "
            "or its status is not 'accepted'."
        )


# ---------------------------------------------------------------------------
# Contract integrity tests (do not depend on snapshot corpus)
# ---------------------------------------------------------------------------

class TestContractIntegrity:
    def test_all_deltas_have_required_fields(self):
        for delta_id, entry in EXPECTED_BEHAVIORAL_DELTAS.items():
            assert entry.get("id") == delta_id, f"{delta_id}: id field must match dict key"
            assert entry.get("description"), f"{delta_id}: description must not be empty"
            assert entry.get("authority_basis") == "workspace_sole", (
                f"{delta_id}: authority_basis must be 'workspace_sole' — "
                "all deltas must be consequences of the constitutional rule"
            )
            assert entry.get("status") == "accepted", (
                f"{delta_id}: only 'accepted' deltas are valid in the harness"
            )

    def test_all_declared_ids_are_valid_strings(self):
        for delta_id in all_delta_ids():
            assert isinstance(delta_id, str) and delta_id.strip(), \
                f"Delta ID must be a non-empty string, got: {delta_id!r}"

    def test_three_expected_deltas_declared(self):
        ids = all_delta_ids()
        assert "legacy_watchlist_grant_removal" in ids
        assert "billing_destination_normalization" in ids
        assert "workspace_trumps_user_trial" in ids

    def test_get_delta_returns_none_for_unknown(self):
        assert access_contract.get_delta("nonexistent_delta") is None

    def test_is_declared_delta_false_for_unknown(self):
        assert not is_declared_delta("made_up_delta_id")

    def test_is_declared_delta_true_for_all_accepted(self):
        for delta_id in all_delta_ids():
            assert is_declared_delta(delta_id)


class TestWorkspaceSoleAuthorityIsConstitutional:
    """Verify that user state never reaches the access decision under unified policy."""

    def test_active_user_cannot_rescue_no_workspace(self):
        state = get_access_state({"subscription_status": "active"}, None, now=NOW)
        assert state == BILLING_REQUIRED, (
            "Active user sub must not grant access when workspace is absent"
        )

    def test_live_user_trial_cannot_rescue_no_workspace(self):
        state = get_access_state(
            {"subscription_status": "trialing", "trial_ends_at": _ts(5)},
            None, now=NOW
        )
        assert state == BILLING_REQUIRED

    def test_active_user_cannot_rescue_expired_workspace(self):
        expired_ws = {"subscription_status": "trialing", "trial_end_at": _ts(-1)}
        state = get_access_state({"subscription_status": "active"}, expired_ws, now=NOW)
        assert state == EXPIRED, (
            "Active user sub must not override an expired workspace"
        )

    def test_live_user_trial_cannot_rescue_expired_workspace(self):
        expired_ws = {"subscription_status": "trialing", "trial_end_at": _ts(-2)}
        user = {"subscription_status": "trialing", "trial_ends_at": _ts(10)}
        state = get_access_state(user, expired_ws, now=NOW)
        assert state == EXPIRED

    def test_workspace_active_grants_regardless_of_user_state(self):
        for user in [
            {},
            {"subscription_status": "active"},
            {"subscription_status": "trialing", "trial_ends_at": _ts(-5)},
            None,
        ]:
            state = get_access_state(user, {"subscription_status": "active"}, now=NOW)
            assert state == ALLOWED, f"Active workspace must grant regardless of user={user!r}"

    def test_user_arg_variation_does_not_change_outcome(self):
        """Changing only the user dict must never change the returned state."""
        workspace = {"subscription_status": "trialing", "trial_end_at": _ts(2)}
        results = {
            get_access_state({}, workspace, now=NOW),
            get_access_state({"subscription_status": "active"}, workspace, now=NOW),
            get_access_state({"subscription_status": "trialing", "trial_ends_at": _ts(-10)}, workspace, now=NOW),
            get_access_state(None, workspace, now=NOW),
        }
        assert len(results) == 1, (
            f"User arg variation changed access outcome: {results}"
        )


class TestNoSubjectiveClassification:
    """Verify the harness has no interpretation-based escape hatches."""

    def test_unexpected_drift_is_a_real_category(self):
        # The UNEXPECTED_DRIFT sentinel must exist and the harness must use it.
        from tests.test_policy_parity import UNEXPECTED_DRIFT as sentinel
        assert sentinel == "UNEXPECTED_DRIFT"

    def test_classify_returns_unexpected_drift_for_undeclared_divergence(self):
        # Manufacture a divergence that matches no registered delta.
        # Both states grant access (redirects are both None), but unified says TRIALING
        # while legacy says ALLOWED — a denial-reason mismatch with no matching delta:
        # - billing_destination: no (both redirect None, no /subscribe involved)
        # - workspace_trumps_user_trial: no (same grant level, and not EXPIRED/BILLING_REQUIRED)
        # - legacy_watchlist_grant_removal: no (/dashboard is a gated path)
        classification, delta_id = _classify(
            legacy_state=ALLOWED,
            legacy_redirect=None,
            unified_state=TRIALING,
            unified_redirect_path=None,
            path="/dashboard",
        )
        assert classification == UNEXPECTED_DRIFT
        assert delta_id is None

    def test_classify_returns_match_for_identical_outcomes(self):
        classification, delta_id = _classify(
            legacy_state=ALLOWED,
            legacy_redirect=None,
            unified_state=ALLOWED,
            unified_redirect_path=None,
            path="/dashboard",
        )
        assert classification == MATCH
        assert delta_id is None

    def test_classify_expected_delta_billing_destination(self):
        classification, delta_id = _classify(
            legacy_state=BILLING_REQUIRED,
            legacy_redirect="/subscribe",
            unified_state=BILLING_REQUIRED,
            unified_redirect_path="/settings/billing",
            path="/contracts",
        )
        assert classification == EXPECTED_DELTA
        assert delta_id == "billing_destination_normalization"

    def test_classify_expected_delta_workspace_trumps_user(self):
        # Unified grants (active workspace), legacy denied (no workspace, no user sub).
        # This maps to workspace_trumps_user_trial because grant/deny flips.
        classification, delta_id = _classify(
            legacy_state=BILLING_REQUIRED,
            legacy_redirect="/subscribe",
            unified_state=ALLOWED,
            unified_redirect_path=None,
            path="/dashboard",
        )
        assert classification == EXPECTED_DELTA
        assert delta_id == "workspace_trumps_user_trial"
