"""Policy contract for intentional behavioral deltas between legacy and unified access.

Every intentional divergence from legacy access behavior MUST be registered here.
The snapshot parity harness uses this allowlist as its ONLY mechanism for
accepting non-matching comparisons.

Rules (non-negotiable):
  - MATCH:          legacy and unified produce identical outcome → always pass
  - EXPECTED_DELTA: divergence maps to a declared entry below → pass
  - UNEXPECTED_DRIFT: divergence with no matching entry → FAIL (gate failure)

No subjective classification. No "logically consistent divergence". No interpretation.
"""

# ---------------------------------------------------------------------------
# Constitutional rule (IMMUTABLE)
# ---------------------------------------------------------------------------
# Billing decision = f(workspace ONLY).
# User state is telemetry. User state MUST NOT influence access decisions.
# This is not a delta — it is the permanent law. Every delta below must be
# a *consequence* of this rule, not a workaround of it.
# ---------------------------------------------------------------------------

EXPECTED_BEHAVIORAL_DELTAS = {
    "legacy_watchlist_grant_removal": {
        "id": "legacy_watchlist_grant_removal",
        "description": (
            "Paths that legacy code left ungated (e.g. /watchlist) are now "
            "evaluated by the unified gate. Under workspace-sole authority, an "
            "inactive workspace means access is denied — the legacy system "
            "granted access on these paths by omission, not by intent."
        ),
        "authority_basis": "workspace_sole",
        "status": "accepted",
    },
    "billing_destination_normalization": {
        "id": "billing_destination_normalization",
        "description": (
            "The legacy system redirected to /subscribe (user-level billing page). "
            "The unified system redirects to /settings/billing (workspace billing page). "
            "/subscribe is not a canonical destination under workspace-sole authority."
        ),
        "authority_basis": "workspace_sole",
        "status": "accepted",
    },
    "workspace_trumps_user_trial": {
        "id": "workspace_trumps_user_trial",
        "description": (
            "Legacy code could grant access via a user-level trial even when the "
            "workspace had no active entitlement. Under workspace-sole authority, "
            "user trial state is ignored. A workspace with an active subscription "
            "or live trial grants access; user state is irrelevant."
        ),
        "authority_basis": "workspace_sole",
        "status": "accepted",
    },
}


def get_delta(delta_id):
    """Return the delta dict for delta_id, or None if not declared."""
    return EXPECTED_BEHAVIORAL_DELTAS.get(delta_id)


def is_declared_delta(delta_id):
    """True when delta_id is a registered, accepted intentional divergence."""
    entry = EXPECTED_BEHAVIORAL_DELTAS.get(delta_id)
    return entry is not None and entry.get("status") == "accepted"


def all_delta_ids():
    """Return the set of all accepted delta IDs (for harness enumeration)."""
    return {k for k, v in EXPECTED_BEHAVIORAL_DELTAS.items() if v.get("status") == "accepted"}
