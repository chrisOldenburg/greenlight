"""SQLite-Schicht. Duenn gehalten: SQL rein, dict raus."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    done_at    TEXT,
    source     TEXT    NOT NULL DEFAULT 'api'
);
CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks (done, created_at, id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Reihenfolge ueberall gleich: offene zuerst, neueste zuletzt.
ORDER = "ORDER BY done ASC, created_at ASC, id ASC"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """ISO-8601 UTC mit Z-Suffix, Sekundengenauigkeit."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def add_task(conn: sqlite3.Connection, text: str, source: str) -> dict:
    created = iso(utcnow())
    cur = conn.execute(
        "INSERT INTO tasks (text, done, created_at, done_at, source) VALUES (?, 0, ?, NULL, ?)",
        (text, created, source),
    )
    conn.commit()
    return get_task(conn, int(cur.lastrowid))


def list_tasks(conn: sqlite3.Connection, done: bool | None = None) -> list[dict]:
    if done is None:
        rows = conn.execute(f"SELECT * FROM tasks {ORDER}").fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE done = ? {ORDER}", (1 if done else 0,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_task(conn: sqlite3.Connection, task_id: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


def set_done(conn: sqlite3.Connection, task_id: int, done: bool) -> dict | None:
    """Idempotent: erneutes Abhaken laesst done_at unveraendert."""
    task = get_task(conn, task_id)
    if task is None:
        return None
    if bool(task["done"]) == done:
        return task
    done_at = iso(utcnow()) if done else None
    conn.execute(
        "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
        (1 if done else 0, done_at, task_id),
    )
    conn.commit()
    return get_task(conn, task_id)


def delete_task(conn: sqlite3.Connection, task_id: int) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0


def purge_done(conn: sqlite3.Connection, keep_days: int) -> int:
    """Loescht erledigte Aufgaben, die laenger als keep_days abgehakt sind."""
    if keep_days <= 0:
        return 0
    cutoff = iso(utcnow() - timedelta(days=keep_days))
    cur = conn.execute(
        "DELETE FROM tasks WHERE done = 1 AND done_at IS NOT NULL AND done_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


def meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else None


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
