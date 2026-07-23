"""Focused tests for gate_guard.py fail-closed input type validation.

These cover the bounded hardening that verifies the parsed PreToolUse payload
(and its tool_input) are dictionaries before .get() is used, failing CLOSED for
malformed or unexpected input types, while leaving existing authorized and
denied gate semantics unchanged.

The hook is exercised as a subprocess (its real invocation shape): it reads a
JSON payload on stdin and either prints a JSON deny decision or stays silent
(pass-through). Exit code is always 0; the decision lives in stdout.
"""
import json
import os
import subprocess
import sys

import pytest

HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "hooks", "gate_guard.py",
)


@pytest.fixture(autouse=True)
def isolated_gate_path(tmp_path, monkeypatch):
    """Point the hook at a controlled, guaranteed-absent gate path.

    The denied-behavior tests require the gate to be CLOSED (approval file
    absent). Rather than depending on the real host path
    (/home/michael/.gate_approval) being absent, hand the subprocess a temp
    path that never exists via GATE_APPROVAL_PATH. Tests thus never read,
    create, or remove the real gate file, and the subprocess inherits this env
    override at spawn.
    """
    gate = tmp_path / "gate_approval_absent"
    assert not gate.exists()
    monkeypatch.setenv("GATE_APPROVAL_PATH", str(gate))
    return gate


def _run(stdin_text):
    """Invoke the gate hook with the given raw stdin; return (stdout, decision).

    `decision` is the parsed hookSpecificOutput.permissionDecision, or None for a
    silent pass-through.
    """
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    if not out:
        return out, None
    payload = json.loads(out)
    return out, payload["hookSpecificOutput"]["permissionDecision"]


def _deny(stdin_text):
    _, decision = _run(stdin_text)
    return decision == "deny"


def _passthrough(stdin_text):
    out, decision = _run(stdin_text)
    return out == "" and decision is None


# --- malformed / unexpected top-level types: must fail CLOSED (deny) ---

def test_top_level_json_array_fails_closed():
    assert _deny(json.dumps(["not", "a", "dict"]))


def test_top_level_json_scalar_string_fails_closed():
    assert _deny(json.dumps("just-a-string"))


def test_top_level_json_scalar_number_fails_closed():
    assert _deny(json.dumps(42))


def test_top_level_json_null_fails_closed():
    assert _deny(json.dumps(None))


def test_malformed_json_fails_closed():
    assert _deny("{not valid json")


# --- Bash payloads with bad tool_input: must fail CLOSED (deny) ---

def test_missing_tool_input_fails_closed():
    assert _deny(json.dumps({"tool_name": "Bash"}))


def test_tool_input_array_fails_closed():
    assert _deny(json.dumps({"tool_name": "Bash", "tool_input": ["ls"]}))


def test_tool_input_scalar_fails_closed():
    assert _deny(json.dumps({"tool_name": "Bash", "tool_input": "ls -la"}))


def test_tool_input_dict_missing_command_fails_closed():
    assert _deny(json.dumps({"tool_name": "Bash", "tool_input": {}}))


# --- existing semantics preserved ---

def test_valid_dict_benign_command_passes_through():
    # A well-formed Bash payload with a non-dangerous command is authorized.
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    assert _passthrough(json.dumps(payload))


def test_non_bash_tool_passes_through():
    # Non-Bash tools are never gated on command content.
    payload = {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}
    assert _passthrough(json.dumps(payload))


def test_existing_denied_behavior_git_merge_blocked(isolated_gate_path):
    # Dangerous op with the (controlled) gate absent must still be denied.
    assert not isolated_gate_path.exists(), (
        "test assumes the controlled gate path is absent"
    )
    payload = {"tool_name": "Bash", "tool_input": {"command": "git merge feature"}}
    assert _deny(json.dumps(payload))


def test_existing_denied_behavior_force_push_blocked():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git push --force origin feature"},
    }
    assert _deny(json.dumps(payload))
