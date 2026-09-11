"""Schema inspection and the SQL safety layer for the vendor-risk database.

Adapted from 9_ai_agents_practically/2_data_analyst_agent/db.py. Two separate
checks, both needed:

- ``looks_safe()`` is a keyword screen. It gives the agent a specific,
  actionable error to correct on the next attempt. It is NOT a security
  boundary.
- ``read_only_connection()`` is the guarantee: SQLite opened with ``mode=ro``,
  so a write is refused by the engine itself even if the screen were removed.
"""

import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "vendors.db"

DEFAULT_ROW_LIMIT = 200
QUERY_TIMEOUT_SECONDS = 5.0

_WRITE_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "truncate", "attach", "detach", "pragma", "vacuum", "reindex",
)


class UnsafeQuery(Exception):
    """The query was rejected before it reached the database."""


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def looks_safe(sql: str) -> str:
    """Screen a query and return it with a LIMIT applied.

    Raises UnsafeQuery with a message written to be read by the agent - it goes
    straight back into the conversation as the retry prompt.
    """
    bare = _strip_sql_comments(sql).strip().rstrip(";").strip()

    if not bare:
        raise UnsafeQuery("The query was empty. Write a single SELECT statement.")

    if ";" in bare:
        raise UnsafeQuery(
            "Multiple statements are not allowed. Send exactly one SELECT statement, "
            "with no semicolons."
        )

    lowered = bare.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise UnsafeQuery(
            f"Only SELECT queries are allowed - this one starts with "
            f"'{bare.split()[0]}'. Rewrite it as a read-only SELECT."
        )

    for kw in _WRITE_KEYWORDS:
        if re.search(rf"\b{kw}\b", lowered):
            raise UnsafeQuery(
                f"The query contains '{kw.upper()}', which modifies data. "
                f"This database is read-only. Answer the question with a SELECT."
            )

    if not re.search(r"\blimit\b", lowered):
        bare = f"{bare}\nLIMIT {DEFAULT_ROW_LIMIT}"

    return bare


def read_only_connection() -> sqlite3.Connection:
    """A connection the database itself will not let you write through."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS

    def _watchdog() -> int:
        return 1 if time.monotonic() > deadline else 0

    con.set_progress_handler(_watchdog, 10_000)
    return con


def run_query(sql: str) -> tuple[list[str], list[tuple]]:
    """Screen, then execute. Returns (column_names, rows)."""
    safe_sql = looks_safe(sql)
    con = read_only_connection()
    try:
        cur = con.execute(safe_sql)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        return columns, [tuple(r) for r in rows]
    finally:
        con.close()


def get_schema() -> str:
    """The full schema as CREATE statements, plus a few sample rows per table."""
    con = read_only_connection()
    try:
        tables = [
            r["name"]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        parts = []
        for table in tables:
            ddl = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()["sql"]
            rows = con.execute(f"SELECT * FROM {table} LIMIT 3").fetchall()
            sample = "\n".join("  " + " | ".join(str(v) for v in tuple(r)) for r in rows)
            parts.append(f"{ddl};\n-- sample rows:\n{sample}")
        return "\n\n".join(parts)
    finally:
        con.close()
