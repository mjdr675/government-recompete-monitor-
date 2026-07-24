"""Focused tests for gate_guard.py bound, channel-neutral approval validation.

These prove the remediation for RC-GOV-REMOVE-DISCORD-APPROVAL-REMEDIATION-01:
the gate no longer opens on bare file existence, is channel-neutral (Discord is
not universally required), and fails CLOSED on any missing/malformed/stale/
mismatched binding or non-human provenance -- while a fully-bound, current,
Michael-issued token delivered through ANY channel is accepted.

The hook is exercised as a subprocess (its real invocation shape): it reads a
PreToolUse JSON payload on stdin and either prints a JSON deny decision or stays
silent (pass-through). All bindings are verified against a hermetic throwaway git
repo built under tmp_path; the real repo and the real host gate file
(/home/michael/.gate_approval) are never read, created, or modified.
"""
import json
import os
import subprocess
import sys
import time

import pytest

HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "hooks", "gate_guard.py",
)

REPO_ID = "mjdr675/government-recompete-monitor-"


def _git(cwd, *args):
    out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A hermetic git repo: origin=REPO_ID, `main` at commit A, HEAD (branch
    `work`) at a later commit B, and a remote-tracking ref origin/pr-branch=B."""
    d = tmp_path / "repo"
    d.mkdir()
    p = str(d)
    _git(p, "init", "-q")
    _git(p, "config", "user.email", "t@example.com")
    _git(p, "config", "user.name", "T")
    _git(p, "config", "commit.gpgsign", "false")
    _git(p, "remote", "add", "origin", "git@github.com:mjdr675/government-recompete-monitor-.git")
    (d / "CLAUDE.md").write_text("a\n")
    _git(p, "add", "CLAUDE.md")
    _git(p, "commit", "-q", "-m", "A")
    _git(p, "branch", "-M", "main")
    base = _git(p, "rev-parse", "main")
    _git(p, "switch", "-q", "-c", "work")
    (d / "CLAUDE.md").write_text("b\n")
    _git(p, "commit", "-q", "-am", "B")
    head = _git(p, "rev-parse", "HEAD")
    _git(p, "update-ref", "refs/remotes/origin/pr-branch", head)
    return {"path": p, "head": head, "base": base}


def _future():
    return time.time() + 3600


def _token(head, base, **over):
    """A fully-valid `git merge` approval token; override fields per test."""
    tok = {
        "repo": REPO_ID,
        "operation": "git merge",
        "base_ref": "main",
        "base_sha": base,
        "head_sha": head,
        "scope": ["CLAUDE.md"],
        "method": "merge",
        "approved_by": "michael",
        "provenance": {"human": True, "source": "manual"},
        "expires_at": _future(),
    }
    tok.update(over)
    return tok


def _run(command, repo, token=None, gate_path=None):
    """Invoke the hook for `command` in `repo`; write `token` to the gate file
    (unless None). Returns (decision_or_None, stdout, gate_path)."""
    if gate_path is None:
        gate_path = os.path.join(repo["path"], "..", "gate.json")
    if token is not None:
        with open(gate_path, "w", encoding="utf-8") as fh:
            json.dump(token, fh)
    env = dict(os.environ)
    env["GATE_APPROVAL_PATH"] = gate_path
    env.pop("GATE_APPROVAL_AUTHORITY", None)  # default 'michael'
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": repo["path"]}
    proc = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    decision = None
    if out:
        decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    return decision, out, gate_path


def _accepts(command, repo, token):
    decision, _, _ = _run(command, repo, token)
    return decision is None


def _denies(command, repo, token):
    decision, _, _ = _run(command, repo, token)
    return decision == "deny"


# --- Req 8: a fully-bound, human, non-Discord token is accepted -----------------

def test_valid_bound_manual_token_accepted(repo):
    assert _accepts("git merge work", repo, _token(repo["head"], repo["base"]))


def test_valid_bound_gh_pr_merge_accepted(repo):
    tok = _token(
        repo["head"], repo["base"], operation="gh pr merge", method="squash",
        pr="81", branch="pr-branch",
    )
    assert _accepts("gh pr merge 81 --squash", repo, tok)


# --- Req 1 + 10: channel-neutral (Discord neither required nor broken) ----------

def test_discord_not_required_manual_channel_works(repo):
    # provenance carries no Discord anything -> still accepted.
    assert _accepts("git merge work", repo, _token(repo["head"], repo["base"]))


def test_existing_discord_channel_authorization_not_broken(repo):
    tok = _token(repo["head"], repo["base"], channel="discord",
                 provenance={"human": True, "source": "discord", "actor": "michael"})
    assert _accepts("git merge work", repo, tok)


def test_bare_existence_no_longer_opens_gate(repo, tmp_path):
    # A legacy bare/empty file must now fail closed (core defect fixed).
    gate = tmp_path / "bare_gate"
    gate.write_text("")
    decision, _, _ = _run("git merge work", repo, token=None, gate_path=str(gate))
    assert decision == "deny"


# --- Req 4: missing authorization fails closed ----------------------------------

def test_missing_gate_file_fails_closed(repo, tmp_path):
    gate = tmp_path / "absent_gate"
    assert not gate.exists()
    decision, _, _ = _run("git merge work", repo, token=None, gate_path=str(gate))
    assert decision == "deny"
    assert not gate.exists()  # Req 11: never created


# --- Req 2 + 3: generated prompt / self-authorization is never approval ---------

def test_model_generated_provenance_denied(repo):
    tok = _token(repo["head"], repo["base"],
                 provenance={"human": True, "source": "claude"})
    assert _denies("git merge work", repo, tok)


def test_generated_flag_denied(repo):
    tok = _token(repo["head"], repo["base"],
                 provenance={"human": True, "source": "manual", "generated": True})
    assert _denies("git merge work", repo, tok)


def test_claude_cannot_self_authorize_authority(repo):
    tok = _token(repo["head"], repo["base"], approved_by="claude")
    assert _denies("git merge work", repo, tok)


def test_non_human_provenance_denied(repo):
    tok = _token(repo["head"], repo["base"],
                 provenance={"source": "manual"})  # human flag absent
    assert _denies("git merge work", repo, tok)


# --- Req 5: incomplete bindings fail closed -------------------------------------

@pytest.mark.parametrize("drop", ["repo", "operation", "base_sha", "head_sha",
                                   "scope", "approved_by", "provenance", "expires_at"])
def test_missing_required_binding_fails_closed(repo, drop):
    tok = _token(repo["head"], repo["base"])
    tok.pop(drop)
    assert _denies("git merge work", repo, tok)


def test_missing_method_for_merge_fails_closed(repo):
    tok = _token(repo["head"], repo["base"])
    tok.pop("method")
    assert _denies("git merge work", repo, tok)


def test_empty_scope_fails_closed(repo):
    assert _denies("git merge work", repo, _token(repo["head"], repo["base"], scope=[]))


# --- Req 6: SHA mismatch fails closed -------------------------------------------

def test_head_sha_mismatch_fails_closed(repo):
    assert _denies("git merge work", repo, _token("0" * 40, repo["base"]))


def test_base_sha_mismatch_fails_closed(repo):
    assert _denies("git merge work", repo, _token(repo["head"], "0" * 40))


# --- Req 7: repo / operation / PR / method / scope mismatch fail closed ---------

def test_repo_mismatch_fails_closed(repo):
    assert _denies("git merge work", repo, _token(repo["head"], repo["base"], repo="evil/repo"))


def test_operation_mismatch_fails_closed(repo):
    # token authorizes a PR merge, but the command is a git merge.
    tok = _token(repo["head"], repo["base"], operation="gh pr merge")
    assert _denies("git merge work", repo, tok)


def test_pr_number_mismatch_fails_closed(repo):
    tok = _token(repo["head"], repo["base"], operation="gh pr merge", method="squash",
                 pr="80", branch="pr-branch")
    assert _denies("gh pr merge 81 --squash", repo, tok)


def test_merge_method_mismatch_fails_closed(repo):
    tok = _token(repo["head"], repo["base"], operation="gh pr merge", method="merge",
                 pr="81", branch="pr-branch")
    assert _denies("gh pr merge 81 --squash", repo, tok)


def test_scope_mismatch_fails_closed(repo):
    # gated csv add, but the approved scope does not include that path.
    tok = _token(repo["head"], repo["base"],
                 operation="git add integration/recompete_report.csv",
                 scope=["docs/OTHER.md"])
    tok.pop("method")  # not a merge op
    assert _denies("git add integration/recompete_report.csv", repo, tok)


# --- Freshness: stale approval fails closed -------------------------------------

def test_stale_expiry_fails_closed(repo):
    tok = _token(repo["head"], repo["base"], expires_at=time.time() - 1)
    assert _denies("git merge work", repo, tok)


def test_unparseable_expiry_fails_closed(repo):
    tok = _token(repo["head"], repo["base"], expires_at="not-a-date")
    assert _denies("git merge work", repo, tok)


# --- Req 9: denial message is channel-neutral -----------------------------------

def test_denial_message_channel_neutral(repo, tmp_path):
    gate = tmp_path / "absent"
    _, out, _ = _run("git merge work", repo, token=None, gate_path=str(gate))
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "without Discord approval" not in reason
    assert "optional, not required" in reason


# --- Req 11: valid-path acceptance never mutates the gate file -------------------

def test_accept_does_not_mutate_gate_file(repo):
    tok = _token(repo["head"], repo["base"])
    decision, _, gate_path = _run("git merge work", repo, tok)
    assert decision is None
    with open(gate_path, encoding="utf-8") as fh:
        after = json.load(fh)
    assert after == tok  # unchanged by the hook (read-only)
