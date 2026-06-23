"""Access-decision observability (pure instrumentation, no enforcement).

This layer only *records* access decisions in a structured, queryable form so we
can validate legacy-vs-unified parity and debug "why was I redirected?" before
removing the legacy gates (Step E). It makes NO authorization decisions and
never alters control flow — logging failures are swallowed so instrumentation
can never break a request.

Record shape (one JSON object per decision):
    {
      "event": "access_decision",
      "mode": "legacy" | "unified" | "shadow",
      "request_path": "/dashboard",
      "user_id": "...", "workspace_id": "...",
      "state": "allowed|trialing|billing_required|expired",
      "granted": true|false,
      "redirect_path": "/settings/billing" | null
    }
"""
import json
import logging

_GRANTED_STATES = {"allowed", "trialing"}

# Dedicated logger so decisions are easy to filter (logger == "access.audit").
_logger = logging.getLogger("access.audit")


def _normalize_state(state):
    """Accept a plain state string or a dict carrying a 'state' key."""
    if isinstance(state, dict):
        return state.get("state")
    return state


def build_access_record(user_id, workspace_id, state, redirect_path, mode,
                        request_path):
    """Return the structured access-decision record (pure, deterministic)."""
    state_value = _normalize_state(state)
    return {
        "event": "access_decision",
        "mode": mode,
        "request_path": request_path,
        "user_id": str(user_id) if user_id is not None else None,
        "workspace_id": str(workspace_id) if workspace_id is not None else None,
        "state": state_value,
        "granted": state_value in _GRANTED_STATES,
        "redirect_path": redirect_path,
    }


def log_access_decision(user_id, workspace_id, state, redirect_path, mode,
                        request_path):
    """Emit a structured access-decision log line. Never raises."""
    try:
        record = build_access_record(
            user_id, workspace_id, state, redirect_path, mode, request_path
        )
        _logger.info(json.dumps(record))
        return record
    except Exception:  # instrumentation must never break a request
        logging.getLogger(__name__).debug("access decision logging failed", exc_info=True)
        return None
