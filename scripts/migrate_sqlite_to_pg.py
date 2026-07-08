#!/usr/bin/env python3
"""One-time SQLite-snapshot → Postgres data loader for the Recompete cutover.

This copies row data from a **read-only SQLite snapshot** into an already-migrated
Postgres database. It never mutates the source snapshot (opened `mode=ro`) and it
never touches the live production SQLite volume — always run it against a *copy*
(e.g. a `scripts/backup_db.sh` snapshot pulled from R2).

Ordering is topological (parents before children) so foreign keys are satisfied
during load without needing superuser privileges to disable constraint checks.
Everything runs inside a single transaction: on any error — including a row-count
mismatch — the whole load rolls back and Postgres is left untouched.

Usage:
    python scripts/migrate_sqlite_to_pg.py --source <snapshot.db> \
        --target "$DATABASE_URL" [--dry-run] [--fresh] \
        [--tables users,contracts] [--batch-size 1000]

See docs/PG_MIGRATION_LOADER.md for when this runs relative to PR #53.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("pg_migration_loader")

# Tables that must never be copied: the migration ledger is owned by
# db._apply_migrations on the target, and SQLite's internal/FTS shadow tables
# have no place in Postgres (FTS is rebuilt by the app/migrations).
DEFAULT_EXCLUDE = frozenset({"schema_migrations"})


class LoaderError(RuntimeError):
    """Raised for any preflight or verification failure (triggers rollback)."""


def quote_ident(name: str) -> str:
    """Double-quote an SQL identifier (valid in both SQLite and Postgres)."""
    return '"' + name.replace('"', '""') + '"'


def is_excluded(table: str, exclude: frozenset[str]) -> bool:
    return (
        table in exclude
        or table.startswith("sqlite_")
        or table.endswith("_fts")
        or "_fts_" in table  # FTS5 shadow tables: <name>_fts_data, _fts_idx, ...
    )


def topo_sort(tables: list[str], edges: dict[str, set[str]]) -> list[str]:
    """Return `tables` ordered parents-first given child->parents FK `edges`.

    Only edges pointing at tables within `tables` matter. Self-references are
    ignored. Any nodes left in a cycle are appended in input order (best effort;
    the Recompete schema is a DAG so this path is not expected).
    """
    remaining = list(tables)
    tset = set(tables)
    resolved: list[str] = []
    done: set[str] = set()
    # Guard against unbounded looping on a cycle.
    while remaining:
        progress = False
        still: list[str] = []
        for t in remaining:
            parents = {p for p in edges.get(t, set()) if p in tset and p != t}
            if parents <= done:
                resolved.append(t)
                done.add(t)
                progress = True
            else:
                still.append(t)
        remaining = still
        if not progress:
            # Cycle (or missing parent): emit the rest in input order.
            resolved.extend(remaining)
            break
    return resolved


def build_truncate_sql(dialect: str, table: str) -> str:
    """DDL to empty a target table before a --fresh load."""
    if dialect == "postgresql":
        return f"TRUNCATE TABLE {quote_ident(table)} RESTART IDENTITY CASCADE"
    return f"DELETE FROM {quote_ident(table)}"


def build_seq_reset_sql(table: str, pk: str) -> str:
    """Postgres: advance the SERIAL sequence past the max copied id (no-op if
    the column has no owned sequence)."""
    return (
        "SELECT setval("
        f"pg_get_serial_sequence('{table}', '{pk}'), "
        f"COALESCE((SELECT MAX({quote_ident(pk)}) FROM {quote_ident(table)}), 1)"
        ") WHERE pg_get_serial_sequence('" + table + "', '" + pk + "') IS NOT NULL"
    )


@dataclass
class TablePlan:
    name: str
    columns: list[str]
    pk: str | None
    dropped_source_only: list[str] = field(default_factory=list)
    dropped_target_only: list[str] = field(default_factory=list)
    source_rows: int = 0


def build_plan(
    source: Engine,
    target: Engine,
    only_tables: set[str] | None,
    exclude: frozenset[str],
) -> list[TablePlan]:
    """Introspect both sides, intersect tables + columns, order topologically."""
    s_insp = inspect(source)
    t_insp = inspect(target)
    s_tables = set(s_insp.get_table_names())
    t_tables = set(t_insp.get_table_names())

    shared = {
        t
        for t in (s_tables & t_tables)
        if not is_excluded(t, exclude) and (only_tables is None or t in only_tables)
    }
    if only_tables:
        missing = only_tables - shared
        if missing:
            raise LoaderError(
                f"requested --tables not present on both sides: {sorted(missing)}"
            )
    if not shared:
        raise LoaderError("no shared tables to migrate (is the target schema built?)")

    # FK edges (child -> set of parent tables) from the TARGET schema.
    edges: dict[str, set[str]] = {}
    for t in shared:
        parents = {
            fk["referred_table"]
            for fk in t_insp.get_foreign_keys(t)
            if fk.get("referred_table") in shared
        }
        edges[t] = parents

    ordered = topo_sort(sorted(shared), edges)

    plans: list[TablePlan] = []
    with source.connect() as sconn:
        for t in ordered:
            s_cols = [c["name"] for c in s_insp.get_columns(t)]
            t_cols = [c["name"] for c in t_insp.get_columns(t)]
            s_set, t_set = set(s_cols), set(t_cols)
            shared_cols = [c for c in t_cols if c in s_set]  # target column order
            pk_cols = t_insp.get_pk_constraint(t).get("constrained_columns") or []
            pk = pk_cols[0] if len(pk_cols) == 1 else None
            n = sconn.execute(
                text(f"SELECT COUNT(*) FROM {quote_ident(t)}")
            ).scalar_one()
            plans.append(
                TablePlan(
                    name=t,
                    columns=shared_cols,
                    pk=pk,
                    dropped_source_only=sorted(s_set - t_set),
                    dropped_target_only=sorted(t_set - s_set),
                    source_rows=int(n),
                )
            )
    return plans


def _source_engine(path: str) -> Engine:
    if not os.path.isfile(path):
        raise LoaderError(f"source snapshot not found: {path}")

    # Read-only URI open via a creator so the `mode=ro` URI reaches sqlite3
    # verbatim (SQLAlchemy would otherwise consume the `?mode=ro` query string).
    # This guarantees the snapshot is never mutated.
    def _creator():
        import sqlite3

        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    return create_engine("sqlite://", creator=_creator)


def _dialect(engine: Engine) -> str:
    return engine.dialect.name


def load(
    source_url_path: str,
    target_url: str,
    *,
    dry_run: bool = False,
    fresh: bool = False,
    only_tables: set[str] | None = None,
    batch_size: int = 1000,
) -> list[TablePlan]:
    """Run the migration. Returns the executed plan. Raises LoaderError on any
    guard/verification failure (transaction rolled back)."""
    source = _source_engine(source_url_path)
    target = create_engine(target_url)
    try:
        plans = build_plan(source, target, only_tables, exclude=DEFAULT_EXCLUDE)
        tdialect = _dialect(target)

        for p in plans:
            logger.info(
                "plan %-28s rows=%-7d cols=%d%s",
                p.name,
                p.source_rows,
                len(p.columns),
                (
                    f" dropped_source_only={p.dropped_source_only}"
                    if p.dropped_source_only
                    else ""
                ),
            )

        if dry_run:
            logger.info("dry-run: no writes performed")
            return plans

        # Guard: refuse a non-empty target unless --fresh was passed.
        with target.connect() as tconn:
            nonempty = [
                p.name
                for p in plans
                if tconn.execute(
                    text(f"SELECT COUNT(*) FROM {quote_ident(p.name)}")
                ).scalar_one()
                > 0
            ]
        if nonempty and not fresh:
            raise LoaderError(
                "target tables already contain rows; pass --fresh to truncate "
                f"and reload: {nonempty}"
            )

        # Single atomic transaction: truncate → load → seq reset → verify.
        with source.connect() as sconn, target.begin() as tconn:
            if fresh:
                for p in reversed(plans):  # children first for FK-safe truncate
                    tconn.execute(text(build_truncate_sql(tdialect, p.name)))

            for p in plans:
                if not p.columns:
                    continue
                collist = ", ".join(quote_ident(c) for c in p.columns)
                placeholders = ", ".join(f":{c}" for c in p.columns)
                insert_sql = text(
                    f"INSERT INTO {quote_ident(p.name)} ({collist}) "
                    f"VALUES ({placeholders})"
                )
                select_sql = text(f"SELECT {collist} FROM {quote_ident(p.name)}")
                result = sconn.execution_options(stream_results=True).execute(
                    select_sql
                )
                copied = 0
                while True:
                    rows = result.fetchmany(batch_size)
                    if not rows:
                        break
                    tconn.execute(insert_sql, [dict(r._mapping) for r in rows])
                    copied += len(rows)
                logger.info("loaded %-28s %d rows", p.name, copied)

            if tdialect == "postgresql":
                for p in plans:
                    if p.pk:
                        tconn.execute(text(build_seq_reset_sql(p.name, p.pk)))

            # Verify row counts INSIDE the transaction so a mismatch rolls back.
            mismatches = []
            for p in plans:
                tgt_n = tconn.execute(
                    text(f"SELECT COUNT(*) FROM {quote_ident(p.name)}")
                ).scalar_one()
                if int(tgt_n) != p.source_rows:
                    mismatches.append((p.name, p.source_rows, int(tgt_n)))
            if mismatches:
                raise LoaderError(f"row-count verification failed: {mismatches}")

        logger.info("migration committed: %d tables verified", len(plans))
        return plans
    finally:
        source.dispose()
        target.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="path to SQLite snapshot")
    parser.add_argument(
        "--target",
        default=os.environ.get("DATABASE_URL", ""),
        help="target SQLAlchemy URL (defaults to $DATABASE_URL)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="TRUNCATE target tables before load (required if target non-empty)",
    )
    parser.add_argument("--tables", default="", help="comma-separated subset")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if not args.target:
        logger.error("no target: pass --target or set DATABASE_URL")
        return 2

    only = {t.strip() for t in args.tables.split(",") if t.strip()} or None
    try:
        load(
            args.source,
            args.target,
            dry_run=args.dry_run,
            fresh=args.fresh,
            only_tables=only,
            batch_size=args.batch_size,
        )
    except LoaderError as exc:
        logger.error("migration failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
