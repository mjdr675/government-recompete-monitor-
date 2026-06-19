"""
Engineering Memory — automatically maintained documentation of the autonomous
engineering system.

Five markdown documents are kept in ai_agent/ and updated after every completed
task so the AI has persistent context across sessions:

  ARCHITECTURE.md  — system design, components, data flow
  CURRENT_STATE.md — what is built, active features, test counts
  DECISIONS.md     — architectural decisions and their rationale
  ROADMAP.md       — planned work and priorities
  KNOWN_BUGS.md    — known issues and workarounds

Before starting work the loop calls build_context() and injects the result into
the task body so the LLM knows the current system state.  After a task
completes, update_from_llm() asks the LLM to revise whichever documents changed.

Usage:
  mem = EngineeringMemory()
  ctx = mem.build_context()                   # inject before LLM plan call

  result = mem.update_from_llm(               # call after task completes
      task_filename="045-feature.md",
      task_content="...",
      outcome_summary="Added X. 300 tests pass.",
  )
  # On LLM failure, fall back to structured append:
  if result.error:
      mem.append_task_completion(task_filename, outcome_summary)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_AGENT_DIR = Path(__file__).parent

ALL_DOCS = ["ARCHITECTURE", "CURRENT_STATE", "DECISIONS", "ROADMAP", "KNOWN_BUGS"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class UpdateResult:
    """Outcome of a memory update operation."""
    docs_updated: list[str] = field(default_factory=list)
    docs_unchanged: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# EngineeringMemory
# ---------------------------------------------------------------------------

class EngineeringMemory:
    """
    Manages the 5 engineering knowledge documents.

    All methods are safe to call even when documents are missing — missing
    docs read as empty strings and are created on first write.

    Thread-safety: single-writer assumed (the autonomous loop is sequential).
    """

    def __init__(self, agent_dir: Path = _AGENT_DIR) -> None:
        self.agent_dir = agent_dir
        self._paths: dict[str, Path] = {
            doc: agent_dir / f"{doc}.md" for doc in ALL_DOCS
        }

    def path(self, doc: str) -> Path:
        """Return the filesystem path for a document name."""
        return self._paths[doc]

    # -- Reading -----------------------------------------------------------

    def read(self, doc: str) -> str:
        """Read a single document. Returns '' if the file does not exist."""
        p = self._paths[doc]
        return p.read_text() if p.exists() else ""

    def read_all(self) -> dict[str, str]:
        """Read all 5 documents. Keys are doc names (e.g. 'ARCHITECTURE')."""
        return {doc: self.read(doc) for doc in ALL_DOCS}

    def build_context(self) -> str:
        """
        Build a context block for injection into LLM plan prompts.
        Returns '' when all documents are empty or missing.
        """
        sections: list[str] = []
        for doc in ALL_DOCS:
            content = self.read(doc).strip()
            if content:
                sections.append(f"## {doc}.md\n\n{content}")
        if not sections:
            return ""
        return "# Engineering Memory\n\n" + "\n\n".join(sections) + "\n"

    # -- Initialization ----------------------------------------------------

    def initialize_if_missing(self) -> list[str]:
        """
        Create documents with starter content for any that do not yet exist.
        Returns the list of document names that were created.
        """
        created: list[str] = []
        for doc in ALL_DOCS:
            p = self._paths[doc]
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(_starter_content(doc))
                created.append(doc)
        return created

    # -- Updates -----------------------------------------------------------

    def apply_updates(self, updates: dict[str, str]) -> UpdateResult:
        """
        Write new content to documents that have changed.

        `updates` maps doc_name -> new_content.  Only docs whose new content
        differs from the current content are written.  Unknown keys are ignored.
        """
        result = UpdateResult()
        for doc, new_content in updates.items():
            if doc not in ALL_DOCS:
                continue
            current = self.read(doc)
            if new_content.strip() and new_content.strip() != current.strip():
                self._paths[doc].parent.mkdir(parents=True, exist_ok=True)
                self._paths[doc].write_text(new_content)
                result.docs_updated.append(doc)
            else:
                result.docs_unchanged.append(doc)
        return result

    def append_task_completion(
        self,
        task_filename: str,
        task_summary: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Structured (non-LLM) append to CURRENT_STATE after task completion.

        Used as a fallback when the LLM update fails.  Always succeeds as long
        as the filesystem is writable.
        """
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        stem = task_filename.removesuffix(".md")
        entry = f"\n### {stem} — {ts}\n\n{task_summary}\n"

        content = self.read(CURRENT_STATE)
        if "## Completed Tasks" in content:
            content = content.replace("## Completed Tasks", f"## Completed Tasks{entry}", 1)
        else:
            content += f"\n## Completed Tasks{entry}"

        self._paths[CURRENT_STATE].parent.mkdir(parents=True, exist_ok=True)
        self._paths[CURRENT_STATE].write_text(content)

    def update_from_llm(
        self,
        task_filename: str,
        task_content: str,
        outcome_summary: str,
        llm_fn: Optional[Callable[[str], str]] = None,
    ) -> UpdateResult:
        """
        Ask the LLM to update whichever documents need changing after a task.

        `llm_fn` is any callable that accepts a prompt string and returns the
        LLM's text response.  Defaults to ai_agent.llm.call when not provided.

        Parses the response for fenced code blocks keyed by document name::

            ```ARCHITECTURE
            <full new content>
            ```

        Only documents included in the response are written; others are left
        unchanged.  Returns UpdateResult with error set on any exception.
        """
        if llm_fn is None:
            from ai_agent import llm as _llm
            llm_fn = _llm.call

        current = self.read_all()
        prompt = _build_update_prompt(task_filename, task_content, outcome_summary, current)

        try:
            response = llm_fn(prompt)
        except Exception as exc:
            return UpdateResult(error=str(exc))

        updates = _parse_update_response(response)
        return self.apply_updates(updates)


# ---------------------------------------------------------------------------
# Prompt construction and response parsing
# ---------------------------------------------------------------------------

CURRENT_STATE = "CURRENT_STATE"  # shorthand used in append_task_completion


def _build_update_prompt(
    task_filename: str,
    task_content: str,
    outcome_summary: str,
    current_docs: dict[str, str],
) -> str:
    doc_blocks = "\n".join(
        f"### {doc}.md\n```\n{content.strip() or '(empty)'}\n```"
        for doc, content in current_docs.items()
    )
    return f"""You are maintaining engineering memory documents for an autonomous AI development system.

A task just completed. Update the memory documents to reflect what was built and learned.

## Completed Task
**File:** {task_filename}

{task_content[:2000]}

## Outcome
{outcome_summary}

## Current Document Contents
{doc_blocks}

## Instructions

Review each document and update only those that need changing.  Output updates
as fenced code blocks using the document name as the language identifier:

```ARCHITECTURE
<full new content of ARCHITECTURE.md>
```

```CURRENT_STATE
<full new content of CURRENT_STATE.md>
```

Rules per document:
- **ARCHITECTURE.md**: Update only when the task added/removed components, changed interfaces, or altered the system structure.
- **CURRENT_STATE.md**: Always update — record the task completion, any new features active, and current test count.
- **DECISIONS.md**: Add an entry only when the task involved a non-obvious design decision.
- **ROADMAP.md**: Remove/check-off completed items; add newly discovered work.
- **KNOWN_BUGS.md**: Add bugs discovered during implementation; remove bugs that were fixed.

Omit unchanged documents entirely.  Do not add commentary outside the fenced blocks."""


_DOC_FENCE_RE = re.compile(
    r"```(" + "|".join(ALL_DOCS) + r")\s*\n(.*?)```",
    re.DOTALL,
)


def _parse_update_response(response: str) -> dict[str, str]:
    """
    Extract doc updates from an LLM response.
    Returns {doc_name: new_content} for each fenced block found.
    """
    updates: dict[str, str] = {}
    for match in _DOC_FENCE_RE.finditer(response):
        doc_name = match.group(1)
        content = match.group(2)
        if doc_name in ALL_DOCS:
            updates[doc_name] = content
    return updates


# ---------------------------------------------------------------------------
# Starter content
# ---------------------------------------------------------------------------

def _starter_content(doc: str) -> str:
    _starters = {
        "ARCHITECTURE": (
            "# Architecture\n\n"
            "## Overview\n\n"
            "Government contract recompete monitoring platform.  Flask web app backed\n"
            "by SQLite.  Autonomous AI engineering loop in ai_agent/.\n\n"
            "## Components\n\n"
            "- **app.py** — Flask routes and template rendering\n"
            "- **db.py** — SQLite schema, ingest, FTS\n"
            "- **analytics.py** — query layer (dashboard, vendor/agency profiles)\n"
            "- **ai_agent/loop.py** — autonomous task execution loop\n"
            "- **ai_agent/manager.py** — queue manager + LLM orchestration\n"
            "- **ai_agent/recovery.py** — retry tracking and failure reports\n"
            "- **ai_agent/eng_memory.py** — engineering knowledge documents\n"
            "- **ai_agent/memory.py** — SQLite-backed code index (RepoMemory)\n"
            "- **ai_agent/patcher.py** — patch application engine\n"
            "- **ai_agent/reviewer.py** — dangerous-pattern safety check\n"
        ),
        "CURRENT_STATE": (
            "# Current State\n\n"
            "## Active Features\n\n"
            "- Flask web app with dashboard, vendor/agency intelligence pages\n"
            "- Full-text search on contracts via SQLite FTS5\n"
            "- Autonomous AI engineering loop with 3-attempt recovery\n"
            "- Engineering memory (this document and 4 sibling docs)\n\n"
            "## Test Suite\n\n"
            "Run `pytest -q` to get current count.\n\n"
            "## Completed Tasks\n"
        ),
        "DECISIONS": (
            "# Decisions\n\n"
            "## 2026-06-19 — SQLite over Postgres\n"
            "Single-file DB sufficient for current scale; no infra overhead.\n\n"
            "## 2026-06-19 — Queue-based task system (ai_agent/queue/)\n"
            "Separate from backlog/ LLM orchestration to allow autonomous loop\n"
            "without modifying the existing manager pipeline.\n\n"
            "## 2026-06-19 — RecoveryTracker per task (not per attempt)\n"
            "Accumulates failure history across all attempts so each retry prompt\n"
            "includes the full context of what was tried before.\n"
        ),
        "ROADMAP": (
            "# Roadmap\n\n"
            "## In Progress\n\n"
            "_(none)_\n\n"
            "## Planned\n\n"
            "- Unify backlog/ and ai_agent/queue/ task systems\n"
            "- GitHub PR creation after successful task apply\n"
            "- Scheduled morning runs via cron or systemd timer\n"
            "- Per-specialist prompt tuning based on success/failure rates\n"
        ),
        "KNOWN_BUGS": (
            "# Known Bugs\n\n"
            "_(none currently tracked)_\n"
        ),
    }
    return _starters.get(doc, f"# {doc}\n\n")
