"""
Tests for ai_agent/escalation.py — human escalation triggers and reporting.
"""

from pathlib import Path

import pytest

from ai_agent.escalation import (
    AMBIGUOUS_TASK,
    REPEATED_FAILURES,
    RISKY_CODE,
    EscalationTrigger,
    check_repeated_failures,
    check_risky_code,
    check_task_ambiguity,
    should_escalate,
    write_escalation_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(title: str = "Do something", body: str = "Implement feature X in app.py.") -> dict:
    return {"title": title, "body": body, "source": "053-test.md", "status": "OPEN"}


# ---------------------------------------------------------------------------
# check_task_ambiguity
# ---------------------------------------------------------------------------

class TestCheckTaskAmbiguity:
    def test_returns_none_for_clear_task(self):
        task = _task(body="Add a /health endpoint that returns JSON with status OK and uptime.")
        assert check_task_ambiguity(task) is None

    def test_triggers_on_empty_body(self):
        task = _task(body="")
        t = check_task_ambiguity(task)
        assert t is not None
        assert t.reason == AMBIGUOUS_TASK

    def test_triggers_on_very_short_body(self):
        task = _task(body="Fix it")
        t = check_task_ambiguity(task)
        assert t is not None
        assert any("character" in d for d in t.details)

    def test_triggers_on_few_words(self):
        task = _task(body="Do the thing now")  # only 4 words
        t = check_task_ambiguity(task)
        assert t is not None

    def test_triggers_on_vague_only_body(self):
        task = _task(body="improve")
        t = check_task_ambiguity(task)
        assert t is not None
        assert t.reason == AMBIGUOUS_TASK

    def test_vague_variants_trigger(self):
        for body in ["enhance.", "refactor!", "make it better", "optimize"]:
            task = _task(body=body)
            t = check_task_ambiguity(task)
            assert t is not None, f"should trigger for body={body!r}"

    def test_uses_task_title_in_message(self):
        task = _task(title="My Vague Task", body="")
        t = check_task_ambiguity(task)
        assert "My Vague Task" in t.message

    def test_uses_source_as_task_filename(self):
        task = _task(body="")
        task["source"] = "053-escalation.md"
        t = check_task_ambiguity(task)
        assert t.task_filename == "053-escalation.md"

    def test_returns_none_when_body_is_missing_key(self):
        # dict without 'body' key should not crash
        task = {"title": "No body key", "source": "x.md"}
        t = check_task_ambiguity(task)
        assert t is not None   # missing body → ambiguous

    def test_min_body_length_configurable(self):
        # 24 chars, 5 words — fails default length (30) but passes custom (5)
        task = _task(body="Do this task now please.")
        assert check_task_ambiguity(task, min_body_length=5) is None

    def test_details_list_is_non_empty_on_trigger(self):
        task = _task(body="")
        t = check_task_ambiguity(task)
        assert len(t.details) > 0


# ---------------------------------------------------------------------------
# check_repeated_failures
# ---------------------------------------------------------------------------

class TestCheckRepeatedFailures:
    def test_returns_none_below_threshold(self):
        errors = ["error 1", "error 2"]
        assert check_repeated_failures(errors, threshold=3) is None

    def test_triggers_at_threshold(self):
        errors = ["err 1", "err 2", "err 3"]
        t = check_repeated_failures(errors, threshold=3)
        assert t is not None
        assert t.reason == REPEATED_FAILURES

    def test_triggers_above_threshold(self):
        errors = ["e"] * 5
        t = check_repeated_failures(errors, threshold=3)
        assert t is not None

    def test_returns_none_for_empty_list(self):
        assert check_repeated_failures([]) is None

    def test_details_include_all_errors(self):
        errors = ["err A", "err B", "err C"]
        t = check_repeated_failures(errors, threshold=3)
        for err in errors:
            assert any(err in d for d in t.details)

    def test_message_includes_count(self):
        errors = ["e1", "e2", "e3"]
        t = check_repeated_failures(errors, threshold=3)
        assert "3" in t.message

    def test_message_includes_task_filename(self):
        errors = ["e1", "e2", "e3"]
        t = check_repeated_failures(errors, threshold=3, task_filename="053-task.md")
        assert "053-task.md" in t.message

    def test_threshold_one_triggers_on_single_error(self):
        t = check_repeated_failures(["one error"], threshold=1)
        assert t is not None

    def test_error_messages_truncated_in_details(self):
        long_error = "x" * 200
        t = check_repeated_failures([long_error] * 3, threshold=3)
        for detail in t.details:
            assert len(detail) <= 130  # label + truncated msg


# ---------------------------------------------------------------------------
# check_risky_code
# ---------------------------------------------------------------------------

class TestCheckRiskyCode:
    def test_returns_none_for_routine_patch(self):
        patch = "def add(a, b):\n    return a + b\n"
        assert check_risky_code(patch) is None

    def test_triggers_on_alter_table(self):
        patch = "cursor.execute('ALTER TABLE users ADD COLUMN age INT')"
        t = check_risky_code(patch)
        assert t is not None
        assert t.reason == RISKY_CODE
        assert any("ALTER TABLE" in d or "schema" in d for d in t.details)

    def test_triggers_on_create_table(self):
        patch = "cursor.execute('CREATE TABLE subscriptions (id INT)')"
        t = check_risky_code(patch)
        assert t is not None

    def test_triggers_on_drop_column(self):
        patch = "op.drop_column('users', 'legacy_field')"
        t = check_risky_code(patch)
        assert t is not None

    def test_triggers_on_stripe(self):
        patch = "import stripe\nstripe.Charge.create(amount=1000)"
        t = check_risky_code(patch)
        assert t is not None
        assert any("payment" in d or "stripe" in d.lower() for d in t.details)

    def test_triggers_on_secret_key(self):
        patch = "app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')"
        t = check_risky_code(patch)
        assert t is not None

    def test_triggers_on_alembic(self):
        patch = "from alembic import op\nop.execute('...')"
        t = check_risky_code(patch)
        assert t is not None

    def test_triggers_on_boto3(self):
        patch = "import boto3\ns3_client = boto3.client('s3')"
        t = check_risky_code(patch)
        assert t is not None

    def test_triggers_on_login_required(self):
        patch = "@login_required\ndef dashboard(): ..."
        t = check_risky_code(patch)
        assert t is not None

    def test_multiple_patterns_all_reported(self):
        patch = (
            "ALTER TABLE users ADD COLUMN x INT;\n"
            "import stripe\n"
            "stripe.Charge.create(amount=500)\n"
        )
        t = check_risky_code(patch)
        assert t is not None
        assert len(t.details) >= 2

    def test_task_filename_in_message(self):
        patch = "ALTER TABLE users ADD COLUMN x INT"
        t = check_risky_code(patch, task_filename="099-migration.md")
        assert "099-migration.md" in t.message

    def test_case_insensitive_matching(self):
        patch = "alter table products add column price DECIMAL(10,2)"
        t = check_risky_code(patch)
        assert t is not None

    def test_returns_none_for_empty_patch(self):
        assert check_risky_code("") is None


# ---------------------------------------------------------------------------
# should_escalate
# ---------------------------------------------------------------------------

class TestShouldEscalate:
    def test_false_when_all_none(self):
        assert should_escalate([None, None, None]) is False

    def test_false_for_empty_list(self):
        assert should_escalate([]) is False

    def test_true_when_one_trigger(self):
        t = EscalationTrigger(RISKY_CODE, "msg", "file.md")
        assert should_escalate([None, t, None]) is True

    def test_true_when_all_triggers(self):
        triggers = [
            EscalationTrigger(AMBIGUOUS_TASK, "a", "f"),
            EscalationTrigger(REPEATED_FAILURES, "b", "f"),
            EscalationTrigger(RISKY_CODE, "c", "f"),
        ]
        assert should_escalate(triggers) is True


# ---------------------------------------------------------------------------
# write_escalation_report
# ---------------------------------------------------------------------------

class TestWriteEscalationReport:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        t = EscalationTrigger(RISKY_CODE, "risky patch", "052-daemon.md", ["ALTER TABLE"])
        write_escalation_report([t], path=path)
        assert path.exists()

    def test_file_starts_with_header(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        write_escalation_report([EscalationTrigger(RISKY_CODE, "m", "f")], path=path)
        assert path.read_text().startswith("# Escalation Notice")

    def test_includes_all_trigger_reasons(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        triggers = [
            EscalationTrigger(AMBIGUOUS_TASK, "msg A", "f"),
            EscalationTrigger(RISKY_CODE, "msg B", "g"),
        ]
        write_escalation_report(triggers, path=path)
        content = path.read_text()
        assert "Ambiguous Task" in content or "ambiguous_task" in content
        assert "Risky Code" in content or "risky_code" in content

    def test_includes_task_filename(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        t = EscalationTrigger(RISKY_CODE, "msg", "099-migration.md", [])
        write_escalation_report([t], path=path)
        assert "099-migration.md" in path.read_text()

    def test_includes_details(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        t = EscalationTrigger(RISKY_CODE, "msg", "f", ["ALTER TABLE", "stripe"])
        write_escalation_report([t], path=path)
        content = path.read_text()
        assert "ALTER TABLE" in content
        assert "stripe" in content

    def test_includes_resolution_steps(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        write_escalation_report([EscalationTrigger(RISKY_CODE, "m", "f")], path=path)
        assert "Resolution" in path.read_text()

    def test_includes_delete_instruction(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        write_escalation_report([EscalationTrigger(RISKY_CODE, "m", "f")], path=path)
        assert "Delete this file" in path.read_text()

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "ESCALATE.md"
        write_escalation_report([EscalationTrigger(RISKY_CODE, "m", "f")], path=path)
        assert path.exists()

    def test_overwrites_by_default(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        t1 = EscalationTrigger(AMBIGUOUS_TASK, "first", "a.md")
        t2 = EscalationTrigger(RISKY_CODE, "second", "b.md")
        write_escalation_report([t1], path=path)
        write_escalation_report([t2], path=path)
        content = path.read_text()
        assert "second" in content
        assert "first" not in content

    def test_append_mode_keeps_previous(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        t1 = EscalationTrigger(AMBIGUOUS_TASK, "first trigger", "a.md")
        t2 = EscalationTrigger(RISKY_CODE, "second trigger", "b.md")
        write_escalation_report([t1], path=path)
        write_escalation_report([t2], path=path, append=True)
        content = path.read_text()
        assert "first trigger" in content
        assert "second trigger" in content

    def test_returns_path(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        result = write_escalation_report(
            [EscalationTrigger(RISKY_CODE, "m", "f")], path=path
        )
        assert result == path

    def test_trigger_count_in_header(self, tmp_path):
        path = tmp_path / "ESCALATE.md"
        triggers = [
            EscalationTrigger(AMBIGUOUS_TASK, "a", "f"),
            EscalationTrigger(RISKY_CODE, "b", "g"),
        ]
        write_escalation_report(triggers, path=path)
        assert "Triggers (2)" in path.read_text()
