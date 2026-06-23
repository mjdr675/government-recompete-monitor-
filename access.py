"""Domain layer for access entitlement (pure, no web/routing concerns).

This module answers a single question — "what is this account's billing
entitlement?" — and nothing else. It contains NO URLs, redirects, Flask
imports, or I/O. It is deterministic and side-effect free: the only external
input is the current time, which is injectable for testing.

Authority model (LOCKED): the **workspace is the single source of truth** for
billing entitlement. Billing is company-scoped — the workspace pays and all of
its members inherit access. Therefore:

  - A user's own (legacy) subscription/trial state NEVER grants or denies
    access to a workspace.
  - get_access_state evaluates the WORKSPACE only. The `user` argument is
    accepted for signature stability and telemetry, but it has no effect on the
    returned state.

This deliberately replaces the earlier hybrid (OR-across-principals) behaviour,
where a user-level entitlement could rescue an unpaid workspace.
"""
from datetime import datetime, timezone

# The only four states the rest of the system may branch on.
ALLOWED = "allowed"
TRIALING = "trialing"
BILLING_REQUIRED = "billing_required"
EXPIRED = "expired"

ACCESS_STATES = (ALLOWED, TRIALING, BILLING_REQUIRED, EXPIRED)


def _subscription_status(principal):
    return (principal or {}).get("subscription_status")


def _is_active(principal):
    return _subscription_status(principal) == "active"


def _trial_end_raw(principal):
    """Workspaces store trial_end_at; users store trial_ends_at."""
    principal = principal or {}
    return principal.get("trial_end_at") or principal.get("trial_ends_at")


def _parse_ts(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_access_state(user, workspace, now=None):
    """Return the entitlement state for an account — workspace is the authority.

    Args:
        user:      accepted for signature/telemetry compatibility ONLY; it does
                   not influence the decision (see module docstring).
        workspace: workspace billing dict (subscription_status / trial_end_at).
        now:       injectable current time (defaults to UTC now) for determinism.

    Returns one of ACCESS_STATES, evaluated on the workspace alone
    (first match wins):
        1. active workspace subscription          -> "allowed"
        2. workspace trial window still open       -> "trialing"
        3. workspace trial marker exists, elapsed  -> "expired"
        4. no workspace / no entitlement signal    -> "billing_required"
    """
    now = now or datetime.now(timezone.utc)

    if _is_active(workspace):
        return ALLOWED

    trial_end = _parse_ts(_trial_end_raw(workspace))
    if trial_end is not None:
        return TRIALING if now <= trial_end else EXPIRED
    return BILLING_REQUIRED


def is_access_granted(state):
    """True when the state permits product access (allowed or trialing)."""
    return state in (ALLOWED, TRIALING)
