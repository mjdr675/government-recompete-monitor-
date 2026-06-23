"""Domain layer for access entitlement (pure, no web/routing concerns).

This module answers a single question — "what is this account's billing
entitlement?" — and nothing else. It contains NO URLs, redirects, Flask
imports, or I/O. It is deterministic and side-effect free: the only external
input is the current time, which is injectable for testing.

Unification: a single function folds the (legacy) user-level subscription/trial
signals and the (new) workspace-level signals into one of four states. The
workspace is the billing principal; user-level fields are honoured as a
migration-era fallback so behaviour matches the system being replaced.
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
    """Return the entitlement state for an account.

    Args:
        user:      user dict (may carry legacy subscription_status / trial_ends_at)
        workspace: workspace billing dict (subscription_status / trial_end_at)
        now:       injectable current time (defaults to UTC now) for determinism

    Returns one of ACCESS_STATES. Precedence (first match wins):
        1. active subscription on either principal      -> "allowed"
        2. a live trial window on either principal       -> "trialing"
        3. a trial marker exists but has elapsed         -> "expired"
        4. no entitlement signal at all                  -> "billing_required"
    """
    now = now or datetime.now(timezone.utc)

    if _is_active(workspace) or _is_active(user):
        return ALLOWED

    trial_ends = [
        ts for ts in (_parse_ts(_trial_end_raw(workspace)),
                      _parse_ts(_trial_end_raw(user)))
        if ts is not None
    ]
    if any(now <= end for end in trial_ends):
        return TRIALING
    if trial_ends:
        return EXPIRED
    return BILLING_REQUIRED


def is_access_granted(state):
    """True when the state permits product access (allowed or trialing)."""
    return state in (ALLOWED, TRIALING)
