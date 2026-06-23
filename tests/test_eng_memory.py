"""
Unit tests for ai_agent/eng_memory.py.

Covers: initialization, reading, context building, apply_updates,
append_task_completion, update_from_llm, prompt construction, and
response parsing.  All tests use tmp_path for filesystem isolation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_agent.eng_memory import (
    ALL_DOCS,
    UpdateResult,
    EngineeringMemory,
    _build_update_prompt,
    _parse_update_response,
    _starter_content,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem(tmp_path: Path) -> EngineeringMemory:
    return EngineeringMemory(agent_dir=tmp_path)


@pytest.fixture
def mem_with_docs(tmp_path: Path) -> EngineeringMemory:
    m = EngineeringMemory(agent_dir=tmp_path)
    m.initialize_if_missing()
    return m


# ---------------------------------------------------------------------------
# path()
# ---------------------------------------------------------------------------

def test_path_returns_agent_dir_slash_doc_md(mem: EngineeringMemory, tmp_path: Path) -> None:
    for doc in ALL_DOCS:
        assert mem.path(doc) == tmp_path / f"{doc}.md"


# ---------------------------------------------------------------------------
# read() and read_all()
# ---------------------------------------------------------------------------

def test_read_missing_returns_empty(mem: EngineeringMemory) -> None:
    assert mem.read("ARCHITECTURE") == ""


def test_read_returns_file_content(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n\ncontent")
    assert mem.read("ARCHITECTURE") == "# Arch\n\ncontent"


def test_read_all_returns_all_five_keys(mem: EngineeringMemory) -> None:
    result = mem.read_all()
    assert set(result.keys()) == set(ALL_DOCS)


def test_read_all_missing_docs_are_empty(mem: EngineeringMemory) -> None:
    result = mem.read_all()
    assert all(v == "" for v in result.values())


def test_read_all_reflects_written_content(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "DECISIONS.md").write_text("## Decision: use SQLite")
    result = mem.read_all()
    assert "use SQLite" in result["DECISIONS"]


# ---------------------------------------------------------------------------
# build_context()
# ---------------------------------------------------------------------------

def test_build_context_empty_when_all_missing(mem: EngineeringMemory) -> None:
    assert mem.build_context() == ""


def test_build_context_empty_when_all_blank(mem: EngineeringMemory, tmp_path: Path) -> None:
    for doc in ALL_DOCS:
        (tmp_path / f"{doc}.md").write_text("   ")
    assert mem.build_context() == ""


def test_build_context_starts_with_header(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n\nsome content")
    ctx = mem.build_context()
    assert ctx.startswith("# Engineering Memory")


def test_build_context_includes_nonempty_doc(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n\n- item A")
    ctx = mem.build_context()
    assert "## ROADMAP.md" in ctx
    assert "item A" in ctx


def test_build_context_excludes_empty_docs(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n\nhas content")
    ctx = mem.build_context()
    assert "CURRENT_STATE" not in ctx
    assert "DECISIONS" not in ctx


def test_build_context_includes_multiple_docs(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("arch content")
    (tmp_path / "KNOWN_BUGS.md").write_text("bug content")
    ctx = mem.build_context()
    assert "## ARCHITECTURE.md" in ctx
    assert "## KNOWN_BUGS.md" in ctx


# ---------------------------------------------------------------------------
# initialize_if_missing()
# ---------------------------------------------------------------------------

def test_initialize_creates_all_docs(mem: EngineeringMemory, tmp_path: Path) -> None:
    created = mem.initialize_if_missing()
    assert set(created) == set(ALL_DOCS)
    for doc in ALL_DOCS:
        assert (tmp_path / f"{doc}.md").exists()


def test_initialize_skips_existing(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("existing content")
    created = mem.initialize_if_missing()
    assert "ARCHITECTURE" not in created
    assert (tmp_path / "ARCHITECTURE.md").read_text() == "existing content"


def test_initialize_starter_content_nonempty(mem: EngineeringMemory, tmp_path: Path) -> None:
    mem.initialize_if_missing()
    for doc in ALL_DOCS:
        content = (tmp_path / f"{doc}.md").read_text()
        assert content.strip(), f"{doc}.md starter content should not be blank"


def test_initialize_idempotent(mem: EngineeringMemory) -> None:
    mem.initialize_if_missing()
    created_second = mem.initialize_if_missing()
    assert created_second == []


# ---------------------------------------------------------------------------
# apply_updates()
# ---------------------------------------------------------------------------

def test_apply_updates_writes_changed_docs(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ARCHITECTURE.md").write_text("old content")
    result = mem.apply_updates({"ARCHITECTURE": "new content"})
    assert "ARCHITECTURE" in result.docs_updated
    assert (tmp_path / "ARCHITECTURE.md").read_text() == "new content"


def test_apply_updates_skips_unchanged_docs(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "ROADMAP.md").write_text("# same content")
    result = mem.apply_updates({"ROADMAP": "# same content"})
    assert "ROADMAP" in result.docs_unchanged
    assert "ROADMAP" not in result.docs_updated


def test_apply_updates_ignores_unknown_doc(mem: EngineeringMemory) -> None:
    result = mem.apply_updates({"UNKNOWN_DOC": "some content"})
    assert result.docs_updated == []
    assert result.docs_unchanged == []


def test_apply_updates_skips_empty_new_content(mem: EngineeringMemory, tmp_path: Path) -> None:
    (tmp_path / "DECISIONS.md").write_text("original")
    result = mem.apply_updates({"DECISIONS": "   "})
    assert "DECISIONS" in result.docs_unchanged
    assert (tmp_path / "DECISIONS.md").read_text() == "original"


def test_apply_updates_returns_result_dataclass(mem: EngineeringMemory) -> None:
    result = mem.apply_updates({"ARCHITECTURE": "new content"})
    assert isinstance(result, UpdateResult)


def test_apply_updates_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "subdir"
    m = EngineeringMemory(agent_dir=nested)
    m.apply_updates({"ARCHITECTURE": "content"})
    assert (nested / "ARCHITECTURE.md").exists()


# ---------------------------------------------------------------------------
# append_task_completion()
# ---------------------------------------------------------------------------

def test_append_task_completion_creates_section(mem: EngineeringMemory, tmp_path: Path) -> None:
    mem.append_task_completion("045-feature.md", "Added feature X")
    content = (tmp_path / "CURRENT_STATE.md").read_text()
    assert "## Completed Tasks" in content
    assert "045-feature" in content


def test_append_task_completion_uses_custom_timestamp(mem: EngineeringMemory, tmp_path: Path) -> None:
    mem.append_task_completion("001.md", "summary", timestamp="2026-01-01 10:00 UTC")
    content = (tmp_path / "CURRENT_STATE.md").read_text()
    assert "2026-01-01 10:00 UTC" in content


def test_append_task_completion_inserts_after_existing_section(
    mem: EngineeringMemory, tmp_path: Path
) -> None:
    (tmp_path / "CURRENT_STATE.md").write_text(
        "# Current State\n\n## Completed Tasks\n\nOld entry here.\n"
    )
    mem.append_task_completion("002.md", "new task done", timestamp="2026-06-01 UTC")
    content = (tmp_path / "CURRENT_STATE.md").read_text()
    # New entry should appear; old entry still present
    assert "Old entry here" in content
    assert "002" in content


def test_append_task_completion_strips_md_extension_from_stem(
    mem: EngineeringMemory, tmp_path: Path
) -> None:
    mem.append_task_completion("045-feature.md", "done")
    content = (tmp_path / "CURRENT_STATE.md").read_text()
    assert "045-feature" in content
    # The .md extension should not appear in the heading
    assert "045-feature.md —" not in content


# ---------------------------------------------------------------------------
# update_from_llm()
# ---------------------------------------------------------------------------

def test_update_from_llm_calls_llm_fn_with_prompt(mem: EngineeringMemory) -> None:
    calls = []

    def fake_llm(prompt: str) -> str:
        calls.append(prompt)
        return ""

    mem.update_from_llm("045.md", "task body", "done", llm_fn=fake_llm)
    assert len(calls) == 1
    assert "045.md" in calls[0]


def test_update_from_llm_prompt_contains_outcome(mem: EngineeringMemory) -> None:
    captured = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return ""

    mem.update_from_llm("045.md", "body", "Implemented and committed abc123", llm_fn=fake_llm)
    assert "abc123" in captured[0]


def test_update_from_llm_parses_fenced_architecture_block(
    mem: EngineeringMemory, tmp_path: Path
) -> None:
    response = "```ARCHITECTURE\n# New Architecture\n\nUpdated content.\n```"

    result = mem.update_from_llm(
        "045.md", "body", "done",
        llm_fn=lambda _: response,
    )
    assert "ARCHITECTURE" in result.docs_updated
    assert (tmp_path / "ARCHITECTURE.md").read_text() == "# New Architecture\n\nUpdated content.\n"


def test_update_from_llm_parses_multiple_doc_blocks(
    mem: EngineeringMemory, tmp_path: Path
) -> None:
    response = (
        "```CURRENT_STATE\n# State\n\nall good\n```\n"
        "```ROADMAP\n# Roadmap\n\n- next item\n```"
    )
    result = mem.update_from_llm("045.md", "body", "done", llm_fn=lambda _: response)
    assert "CURRENT_STATE" in result.docs_updated
    assert "ROADMAP" in result.docs_updated


def test_update_from_llm_ignores_unknown_doc_in_response(mem: EngineeringMemory) -> None:
    response = "```NONEXISTENT\nsome content\n```"
    result = mem.update_from_llm("045.md", "body", "done", llm_fn=lambda _: response)
    assert result.docs_updated == []


def test_update_from_llm_handles_llm_error(mem: EngineeringMemory) -> None:
    def bad_llm(_: str) -> str:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    result = mem.update_from_llm("045.md", "body", "done", llm_fn=bad_llm)
    assert result.error is not None
    assert "ANTHROPIC_API_KEY" in result.error


def test_update_from_llm_unchanged_when_response_same_as_current(
    mem: EngineeringMemory, tmp_path: Path
) -> None:
    existing = "# Architecture\n\nexisting content\n"
    (tmp_path / "ARCHITECTURE.md").write_text(existing)
    response = f"```ARCHITECTURE\n{existing}```"
    result = mem.update_from_llm("045.md", "body", "done", llm_fn=lambda _: response)
    assert "ARCHITECTURE" in result.docs_unchanged
    assert "ARCHITECTURE" not in result.docs_updated


# ---------------------------------------------------------------------------
# _build_update_prompt()
# ---------------------------------------------------------------------------

def test_build_update_prompt_contains_task_filename() -> None:
    prompt = _build_update_prompt("045-feature.md", "body", "done", {d: "" for d in ALL_DOCS})
    assert "045-feature.md" in prompt


def test_build_update_prompt_contains_outcome_summary() -> None:
    prompt = _build_update_prompt("x.md", "body", "Committed as abc123", {d: "" for d in ALL_DOCS})
    assert "abc123" in prompt


def test_build_update_prompt_mentions_all_docs() -> None:
    prompt = _build_update_prompt("x.md", "body", "done", {d: "" for d in ALL_DOCS})
    for doc in ALL_DOCS:
        assert doc in prompt


def test_build_update_prompt_includes_current_content() -> None:
    docs = {**{d: "" for d in ALL_DOCS}, "KNOWN_BUGS": "# Bugs\n\nbug one\n"}
    prompt = _build_update_prompt("x.md", "body", "done", docs)
    assert "bug one" in prompt


# ---------------------------------------------------------------------------
# _parse_update_response()
# ---------------------------------------------------------------------------

def test_parse_update_response_single_doc() -> None:
    response = "```ARCHITECTURE\n# Arch\n\nnew content\n```"
    updates = _parse_update_response(response)
    assert "ARCHITECTURE" in updates
    assert "new content" in updates["ARCHITECTURE"]


def test_parse_update_response_multiple_docs() -> None:
    response = (
        "```DECISIONS\ndecision one\n```\n"
        "```KNOWN_BUGS\nbug list\n```"
    )
    updates = _parse_update_response(response)
    assert set(updates.keys()) == {"DECISIONS", "KNOWN_BUGS"}


def test_parse_update_response_empty_response() -> None:
    assert _parse_update_response("") == {}


def test_parse_update_response_unknown_doc_ignored() -> None:
    response = "```UNKNOWN_THING\nsome content\n```"
    assert _parse_update_response(response) == {}


def test_parse_update_response_does_not_include_unmentioned_docs() -> None:
    response = "```ROADMAP\n- new item\n```"
    updates = _parse_update_response(response)
    assert "ARCHITECTURE" not in updates
    assert "CURRENT_STATE" not in updates


# ---------------------------------------------------------------------------
# _starter_content()
# ---------------------------------------------------------------------------

def test_starter_content_nonempty_for_all_docs() -> None:
    for doc in ALL_DOCS:
        content = _starter_content(doc)
        assert content.strip(), f"starter for {doc} must not be blank"


def test_starter_content_starts_with_heading_for_all_docs() -> None:
    for doc in ALL_DOCS:
        content = _starter_content(doc)
        assert content.startswith("#"), f"starter for {doc} should start with a heading"
