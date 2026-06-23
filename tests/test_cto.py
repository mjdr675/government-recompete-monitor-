"""Tests for ai_agent/cto.py — AI CTO strategic planning module."""

import json
from pathlib import Path

import pytest

from ai_agent.cto import (
    CTORecommendation,
    CTOReport,
    QueueEntry,
    RepositorySnapshot,
    TechDebtItem,
    _build_dependency_index,
    collect_repo_state,
    generate_cto_report,
    parse_task_file,
    recommend_next_task,
    scan_queue,
    scan_tech_debt,
    score_task,
    update_roadmap,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    number: int = 56,
    filename: str = "056-min-value-filter.md",
    title: str = "Add min_value filter",
    complexity: str = "S",
    dependencies: list[int] = None,
) -> QueueEntry:
    return QueueEntry(
        filename=filename,
        number=number,
        title=title,
        complexity=complexity,
        dependencies=dependencies or [],
        raw_content="",
    )


def _make_snapshot(
    queued: list[QueueEntry] = None,
    completed: set[int] = None,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        queued_tasks=queued or [],
        completed_task_numbers=completed or set(),
        failed_task_numbers=set(),
        git_log=[],
        test_count=0,
        tech_debt=[],
        generated_at="2026-06-20T12:00:00Z",
    )


def _write_task(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# parse_task_file
# ---------------------------------------------------------------------------

class TestParseTaskFile:
    def test_extracts_number_from_filename(self, tmp_path):
        f = tmp_path / "056-min-value-filter.md"
        f.write_text("# Task 056 — Add min_value filter\n")
        entry = parse_task_file(f)
        assert entry.number == 56

    def test_extracts_title_from_h1(self, tmp_path):
        f = tmp_path / "057-health-test.md"
        f.write_text("# Task 057 — Add /health unit test\n")
        entry = parse_task_file(f)
        assert entry.title == "Add /health unit test"

    def test_extracts_complexity_xs(self, tmp_path):
        f = tmp_path / "057-health-test.md"
        f.write_text("# Task 057 — Health test\n\n**Complexity:** XS\n")
        entry = parse_task_file(f)
        assert entry.complexity == "XS"

    def test_extracts_complexity_xl(self, tmp_path):
        f = tmp_path / "062-schema.md"
        f.write_text("# Task 062 — Schema\n\n**Complexity:** XL\n")
        entry = parse_task_file(f)
        assert entry.complexity == "XL"

    def test_unknown_complexity_when_not_present(self, tmp_path):
        f = tmp_path / "055-ai-cto.md"
        f.write_text("# Task 055 — AI CTO\n\nBuild strategic planning.\n")
        entry = parse_task_file(f)
        assert entry.complexity == "unknown"

    def test_extracts_hard_dependencies(self, tmp_path):
        content = (
            "# Task 062 — Schema Migration\n\n"
            "**Complexity:** XL\n\n"
            "## Hard Dependencies\n"
            "- Task 061: PostgreSQL provision — must be DONE before this task starts\n"
        )
        f = tmp_path / "062-schema-migration.md"
        f.write_text(content)
        entry = parse_task_file(f)
        assert 61 in entry.dependencies

    def test_no_dependencies_when_none(self, tmp_path):
        content = (
            "# Task 056 — min_value\n\n"
            "**Complexity:** S\n\n"
            "## Hard Dependencies\n"
            "- None\n"
        )
        f = tmp_path / "056-min-value-filter.md"
        f.write_text(content)
        entry = parse_task_file(f)
        assert entry.dependencies == []

    def test_multiple_dependencies(self, tmp_path):
        content = (
            "# Task 065 — Celery Ingest\n\n"
            "**Complexity:** M\n\n"
            "## Hard Dependencies\n"
            "- Task 063: Redis provision — must be DONE before this task starts\n"
            "- Task 064: Celery worker in Procfile — must be DONE before this task starts\n"
        )
        f = tmp_path / "065-celery-ingest.md"
        f.write_text(content)
        entry = parse_task_file(f)
        assert 63 in entry.dependencies
        assert 64 in entry.dependencies

    def test_filename_stored(self, tmp_path):
        f = tmp_path / "056-min-value-filter.md"
        f.write_text("# Task 056 — foo\n")
        entry = parse_task_file(f)
        assert entry.filename == "056-min-value-filter.md"

    def test_raw_content_stored(self, tmp_path):
        content = "# Task 056 — foo\nsome body text\n"
        f = tmp_path / "056-min-value-filter.md"
        f.write_text(content)
        entry = parse_task_file(f)
        assert "some body text" in entry.raw_content


# ---------------------------------------------------------------------------
# scan_queue
# ---------------------------------------------------------------------------

class TestScanQueue:
    def test_returns_empty_when_dir_missing(self, tmp_path):
        result = scan_queue(tmp_path / "nonexistent")
        assert result == []

    def test_returns_entries_sorted_by_number(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        (queue / "060-pagination.md").write_text("# Task 060 — Pagination\n")
        (queue / "056-filter.md").write_text("# Task 056 — Filter\n")
        entries = scan_queue(queue)
        assert [e.number for e in entries] == [56, 60]

    def test_ignores_non_md_files(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        (queue / "056-filter.md").write_text("# Task 056 — Filter\n")
        (queue / "README.txt").write_text("not a task")
        entries = scan_queue(queue)
        assert len(entries) == 1

    def test_returns_correct_count(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        for i in [56, 57, 58]:
            (queue / f"0{i}-task.md").write_text(f"# Task {i} — Task {i}\n")
        assert len(scan_queue(queue)) == 3


# ---------------------------------------------------------------------------
# score_task
# ---------------------------------------------------------------------------

class TestScoreTask:
    def _dep_index(self, entries: list[QueueEntry]) -> dict[int, list[int]]:
        return _build_dependency_index(entries)

    def test_xs_scores_higher_than_xl(self):
        xs = _make_entry(number=57, complexity="XS")
        xl = _make_entry(number=62, complexity="XL")
        dep_index = self._dep_index([xs, xl])
        assert score_task(xs, set(), dep_index) > score_task(xl, set(), dep_index)

    def test_s_scores_higher_than_m(self):
        s = _make_entry(number=56, complexity="S")
        m = _make_entry(number=64, complexity="M")
        dep_index = self._dep_index([s, m])
        assert score_task(s, set(), dep_index) > score_task(m, set(), dep_index)

    def test_unmet_dep_penalizes(self):
        entry = _make_entry(number=62, complexity="XS", dependencies=[61])
        dep_index = self._dep_index([entry])
        score_with_unmet = score_task(entry, set(), dep_index)
        score_with_met = score_task(entry, {61}, dep_index)
        assert score_with_met > score_with_unmet

    def test_blocking_bonus_applied(self):
        blocker = _make_entry(number=61, complexity="S")
        blocked = _make_entry(number=62, complexity="S", dependencies=[61])
        dep_index = self._dep_index([blocker, blocked])
        base_s = 4  # S complexity base score
        assert score_task(blocker, set(), dep_index) > base_s

    def test_no_penalty_when_all_deps_met(self):
        entry = _make_entry(number=62, complexity="S", dependencies=[61])
        dep_index = self._dep_index([entry])
        s = score_task(entry, {61}, dep_index)
        assert s >= 4  # at least base S score

    def test_multiple_unmet_deps_stacks_penalty(self):
        entry = _make_entry(number=65, complexity="XS", dependencies=[63, 64])
        dep_index = self._dep_index([entry])
        score_no_deps = score_task(entry, set(), dep_index)
        score_one_dep = score_task(entry, {63}, dep_index)
        assert score_one_dep > score_no_deps

    def test_score_is_float(self):
        entry = _make_entry()
        result = score_task(entry, set(), {})
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# recommend_next_task
# ---------------------------------------------------------------------------

class TestRecommendNextTask:
    def test_returns_none_for_empty_queue(self):
        assert recommend_next_task([], set()) is None

    def test_picks_xs_over_xl(self):
        xs = _make_entry(number=57, filename="057-xs.md", complexity="XS")
        xl = _make_entry(number=62, filename="062-xl.md", complexity="XL")
        rec = recommend_next_task([xs, xl], set())
        assert rec is not None
        assert rec.task_filename == "057-xs.md"

    def test_picks_high_blocker_over_small_task(self):
        # Task 61 (S) unblocks 62, 63, 64, 65 (4 tasks)
        t61 = _make_entry(number=61, filename="061-pg.md", complexity="S")
        t62 = _make_entry(number=62, filename="062-schema.md", complexity="XL", dependencies=[61])
        t63 = _make_entry(number=63, filename="063-redis.md", complexity="S", dependencies=[61])
        t64 = _make_entry(number=64, filename="064-worker.md", complexity="M", dependencies=[63])
        t65 = _make_entry(number=65, filename="065-ingest.md", complexity="M", dependencies=[63, 64])
        t57 = _make_entry(number=57, filename="057-xs.md", complexity="XS")

        entries = [t57, t61, t62, t63, t64, t65]
        rec = recommend_next_task(entries, set())
        assert rec is not None
        assert rec.task_filename == "061-pg.md"

    def test_recommendation_has_rationale(self):
        entry = _make_entry()
        rec = recommend_next_task([entry], set())
        assert rec is not None
        assert rec.rationale

    def test_recommendation_task_filename_matches(self):
        entry = _make_entry(filename="057-health-test.md")
        rec = recommend_next_task([entry], set())
        assert rec is not None
        assert rec.task_filename == "057-health-test.md"

    def test_avoids_task_with_all_unmet_deps_when_alternative_exists(self):
        blocked = _make_entry(number=62, filename="062.md", complexity="XS", dependencies=[61])
        free = _make_entry(number=57, filename="057.md", complexity="M")
        rec = recommend_next_task([blocked, free], set())
        assert rec is not None
        assert rec.task_filename == "057.md"

    def test_tasks_unblocked_list_correct(self):
        t61 = _make_entry(number=61, filename="061.md")
        t62 = _make_entry(number=62, filename="062.md", dependencies=[61])
        t63 = _make_entry(number=63, filename="063.md", dependencies=[61])
        rec = recommend_next_task([t61, t62, t63], set())
        assert rec is not None
        # rec should be t61 since it unblocks t62 and t63
        assert 62 in rec.tasks_unblocked
        assert 63 in rec.tasks_unblocked

    def test_returns_cto_recommendation_type(self):
        entry = _make_entry()
        rec = recommend_next_task([entry], set())
        assert isinstance(rec, CTORecommendation)


# ---------------------------------------------------------------------------
# scan_tech_debt
# ---------------------------------------------------------------------------

class TestScanTechDebt:
    def test_detects_subprocess_popen(self, tmp_path):
        (tmp_path / "app.py").write_text("subprocess.Popen(['python', 'script.py'])\n")
        items = scan_tech_debt(tmp_path)
        assert any("subprocess.Popen" in i.description for i in items)

    def test_detects_sqlite_connect(self, tmp_path):
        (tmp_path / "db.py").write_text("conn = sqlite3.connect('test.db')\n")
        items = scan_tech_debt(tmp_path)
        assert any("sqlite3.connect" in i.description for i in items)

    def test_detects_todo_comment(self, tmp_path):
        (tmp_path / "app.py").write_text("# TODO: fix this later\n")
        items = scan_tech_debt(tmp_path)
        assert any("TODO" in i.description for i in items)

    def test_no_debt_in_clean_file(self, tmp_path):
        (tmp_path / "clean.py").write_text("def add(a, b): return a + b\n")
        items = scan_tech_debt(tmp_path)
        assert items == []

    def test_location_includes_filename(self, tmp_path):
        (tmp_path / "app.py").write_text("subprocess.Popen(['cmd'])\n")
        items = scan_tech_debt(tmp_path)
        popen_item = next(i for i in items if "subprocess.Popen" in i.description)
        assert "app.py" in popen_item.location

    def test_severity_set(self, tmp_path):
        (tmp_path / "db.py").write_text("conn = sqlite3.connect('x')\n")
        items = scan_tech_debt(tmp_path)
        for item in items:
            assert item.severity in ("low", "medium", "high")

    def test_returns_list(self, tmp_path):
        result = scan_tech_debt(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# collect_repo_state
# ---------------------------------------------------------------------------

class TestCollectRepoState:
    def test_returns_repository_snapshot(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        (agent_dir / "queue").mkdir()
        (agent_dir / "done").mkdir()
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert isinstance(snap, RepositorySnapshot)

    def test_queued_tasks_empty_when_no_queue(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert snap.queued_tasks == []

    def test_completed_numbers_from_done_dir(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        (agent_dir / "done").mkdir(parents=True)
        (agent_dir / "done" / "053-escalation.md").write_text("done")
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert 53 in snap.completed_task_numbers

    def test_queued_tasks_parsed(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        (agent_dir / "queue").mkdir(parents=True)
        (agent_dir / "queue" / "056-filter.md").write_text("# Task 056 — Filter\n")
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert len(snap.queued_tasks) == 1

    def test_tech_debt_returned(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        (tmp_path / "app.py").write_text("subprocess.Popen(['cmd'])\n")
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert isinstance(snap.tech_debt, list)

    def test_generated_at_is_string(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        snap = collect_repo_state(tmp_path, agent_dir, count_tests=False)
        assert isinstance(snap.generated_at, str)
        assert len(snap.generated_at) > 0


# ---------------------------------------------------------------------------
# generate_cto_report
# ---------------------------------------------------------------------------

class TestGenerateCtoReport:
    def test_returns_cto_report(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        report = generate_cto_report(tmp_path, agent_dir, count_tests=False)
        assert isinstance(report, CTOReport)

    def test_recommendation_is_none_when_queue_empty(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        report = generate_cto_report(tmp_path, agent_dir, count_tests=False)
        assert report.recommendation is None

    def test_recommendation_present_when_queue_has_tasks(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        (agent_dir / "queue").mkdir(parents=True)
        (agent_dir / "queue" / "056-filter.md").write_text("# Task 056 — Filter\n**Complexity:** S\n")
        report = generate_cto_report(tmp_path, agent_dir, count_tests=False)
        assert report.recommendation is not None

    def test_roadmap_notes_is_list(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        report = generate_cto_report(tmp_path, agent_dir, count_tests=False)
        assert isinstance(report.roadmap_notes, list)

    def test_snapshot_included_in_report(self, tmp_path):
        agent_dir = tmp_path / "ai_agent"
        agent_dir.mkdir()
        report = generate_cto_report(tmp_path, agent_dir, count_tests=False)
        assert isinstance(report.snapshot, RepositorySnapshot)


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

class TestWriteReport:
    def _simple_report(self) -> CTOReport:
        return CTOReport(
            snapshot=_make_snapshot(),
            recommendation=CTORecommendation(
                task_filename="056-filter.md",
                task_title="Add min_value filter",
                rationale="Fast, no deps.",
                estimated_complexity="S",
                score=4.0,
                tasks_unblocked=[],
            ),
            roadmap_notes=[],
            generated_at="2026-06-20 12:00 UTC",
        )

    def test_creates_file(self, tmp_path):
        report = self._simple_report()
        path = tmp_path / "CTO_REPORT.md"
        write_report(report, path)
        assert path.exists()

    def test_returns_path(self, tmp_path):
        report = self._simple_report()
        path = tmp_path / "report.md"
        result = write_report(report, path)
        assert result == path

    def test_starts_with_header(self, tmp_path):
        path = tmp_path / "r.md"
        write_report(self._simple_report(), path)
        assert path.read_text().startswith("# CTO Strategic Report")

    def test_includes_recommended_task(self, tmp_path):
        path = tmp_path / "r.md"
        write_report(self._simple_report(), path)
        assert "056-filter.md" in path.read_text()

    def test_includes_complexity_in_report(self, tmp_path):
        path = tmp_path / "r.md"
        write_report(self._simple_report(), path)
        assert "S" in path.read_text()

    def test_includes_none_when_no_recommendation(self, tmp_path):
        report = CTOReport(
            snapshot=_make_snapshot(),
            recommendation=None,
            roadmap_notes=[],
            generated_at="2026-06-20 12:00 UTC",
        )
        path = tmp_path / "r.md"
        write_report(report, path)
        content = path.read_text()
        assert "empty" in content.lower() or "None" in content or "queue" in content

    def test_includes_tech_debt_section(self, tmp_path):
        snap = _make_snapshot()
        snap.tech_debt = [TechDebtItem("TODO found", "app.py:10", "low")]
        report = CTOReport(snapshot=snap, recommendation=None, roadmap_notes=[], generated_at="now")
        path = tmp_path / "r.md"
        write_report(report, path)
        assert "Technical Debt" in path.read_text()

    def test_includes_advisory_notice(self, tmp_path):
        path = tmp_path / "r.md"
        write_report(self._simple_report(), path)
        assert "advisory" in path.read_text().lower()

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "report.md"
        write_report(self._simple_report(), path)
        assert path.exists()

    def test_queue_table_included_when_tasks_present(self, tmp_path):
        entry = _make_entry(number=56, filename="056.md", title="Filter", complexity="S")
        snap = _make_snapshot(queued=[entry])
        report = CTOReport(snapshot=snap, recommendation=None, roadmap_notes=[], generated_at="now")
        path = tmp_path / "r.md"
        write_report(report, path)
        assert "Task Queue" in path.read_text()

    def test_roadmap_notes_included(self, tmp_path):
        snap = _make_snapshot()
        report = CTOReport(
            snapshot=snap,
            recommendation=None,
            roadmap_notes=["Fix the debt first."],
            generated_at="now",
        )
        path = tmp_path / "r.md"
        write_report(report, path)
        assert "Fix the debt first." in path.read_text()


# ---------------------------------------------------------------------------
# update_roadmap
# ---------------------------------------------------------------------------

class TestUpdateRoadmap:
    def _simple_report(self) -> CTOReport:
        return CTOReport(
            snapshot=_make_snapshot(),
            recommendation=CTORecommendation(
                task_filename="056-filter.md",
                task_title="Add min_value filter",
                rationale="Fast, no deps.",
                estimated_complexity="S",
                score=4.0,
                tasks_unblocked=[],
            ),
            roadmap_notes=["Do task 061 next to unchain infra."],
            generated_at="2026-06-20 12:00 UTC",
        )

    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        assert path.exists()

    def test_returns_path(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        result = update_roadmap(self._simple_report(), path)
        assert result == path

    def test_appends_to_existing_content(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        path.write_text("# Existing Roadmap\n\nSome content.\n")
        update_roadmap(self._simple_report(), path)
        content = path.read_text()
        assert "Existing Roadmap" in content
        assert "CTO Review" in content

    def test_includes_recommended_task(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        assert "056-filter.md" in path.read_text()

    def test_includes_roadmap_notes(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        assert "Do task 061" in path.read_text()

    def test_includes_task_counts(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        content = path.read_text()
        assert "queue" in content.lower() or "Tasks" in content

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        assert path.exists()

    def test_handles_empty_recommendation(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        report = CTOReport(
            snapshot=_make_snapshot(),
            recommendation=None,
            roadmap_notes=[],
            generated_at="2026-06-20 12:00 UTC",
        )
        update_roadmap(report, path)
        content = path.read_text()
        assert "CTO Review" in content
        assert "empty" in content.lower()

    def test_cto_review_section_added(self, tmp_path):
        path = tmp_path / "ROADMAP.md"
        update_roadmap(self._simple_report(), path)
        assert "## CTO Review" in path.read_text()


# ---------------------------------------------------------------------------
# build_dependency_index
# ---------------------------------------------------------------------------

class TestBuildDependencyIndex:
    def test_empty_when_no_deps(self):
        entries = [_make_entry(number=57), _make_entry(number=58)]
        idx = _build_dependency_index(entries)
        assert idx == {}

    def test_single_dep_indexed(self):
        blocker = _make_entry(number=61)
        blocked = _make_entry(number=62, dependencies=[61])
        idx = _build_dependency_index([blocker, blocked])
        assert 61 in idx
        assert 62 in idx[61]

    def test_multiple_tasks_depend_on_same_task(self):
        t61 = _make_entry(number=61)
        t62 = _make_entry(number=62, dependencies=[61])
        t63 = _make_entry(number=63, dependencies=[61])
        idx = _build_dependency_index([t61, t62, t63])
        assert set(idx[61]) == {62, 63}

    def test_chain_dependency(self):
        t61 = _make_entry(number=61)
        t63 = _make_entry(number=63, dependencies=[61])
        t64 = _make_entry(number=64, dependencies=[63])
        idx = _build_dependency_index([t61, t63, t64])
        assert 62 not in idx
        assert 63 in idx[61]
        assert 64 in idx[63]
