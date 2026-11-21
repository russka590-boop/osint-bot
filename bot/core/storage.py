from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    plugins TEXT NOT NULL,
    found INTEGER NOT NULL DEFAULT 0,
    elapsed REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries (created_at DESC);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    greeted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    kind TEXT NOT NULL,
    content TEXT,
    file_id TEXT,
    created_at TEXT NOT NULL,
    edited_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_ref ON messages (chat_id, message_id);

CREATE TABLE IF NOT EXISTS message_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_row INTEGER NOT NULL,
    old_content TEXT,
    edited_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("storage is not connected")
        return self._db

    async def log_query(
        self,
        *,
        user_id: int,
        username: str | None,
        kind: str,
        target: str,
        plugins: str,
        found: int,
        elapsed: float,
        status: str = "ok",
    ) -> None:
        db = self._conn()
        await db.execute(
            "INSERT INTO queries (created_at, user_id, username, kind, target, plugins, found, elapsed, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), user_id, username, kind, target, plugins, found, elapsed, status),
        )
        await db.commit()

    async def recent(self, limit: int = 20) -> list[tuple]:
        db = self._conn()
        cursor = await db.execute(
            "SELECT created_at, user_id, username, kind, target, found, elapsed, status"
            " FROM queries ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return list(rows)

    async def stats(self, user_id: int) -> tuple[int, int]:
        db = self._conn()
        cursor = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(found), 0) FROM queries WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return (int(row[0]), int(row[1])) if row else (0, 0)

    async def register_user(
        self, user_id: int, username: str | None, first_name: str | None
    ) -> tuple[bool, bool, str]:
        db = self._conn()
        cursor = await db.execute(
            "SELECT greeted, role FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        now = _now()
        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, role, created_at, last_seen, greeted)"
                " VALUES (?, ?, ?, 'user', ?, ?, 0)",
                (user_id, username, first_name, now, now),
            )
            await db.commit()
            return True, False, "user"
        await db.execute(
            "UPDATE users SET username = ?, first_name = ?, last_seen = ? WHERE user_id = ?",
            (username, first_name, now, user_id),
        )
        await db.commit()
        return False, bool(row[0]), str(row[1])

    async def mark_greeted(self, user_id: int) -> None:
        db = self._conn()
        await db.execute("UPDATE users SET greeted = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

    async def get_role(self, user_id: int) -> str | None:
        db = self._conn()
        cursor = await db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return str(row[0]) if row else None

    async def set_role(self, user_id: int, role: str) -> bool:
        db = self._conn()
        cursor = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        await cursor.close()
        if not exists:
            return False
        await db.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        await db.commit()
        return True

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def find_user(self, query: str) -> dict[str, Any] | None:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        cleaned = query.strip().lstrip("@")
        cursor = await db.execute(
            "SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? OR CAST(user_id AS TEXT) = ?"
            " ORDER BY last_seen DESC LIMIT 1",
            (f"%{cleaned}%", f"%{cleaned}%", cleaned),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def list_users(self, query: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        if query:
            cleaned = query.strip().lstrip("@")
            cursor = await db.execute(
                "SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ?"
                " OR CAST(user_id AS TEXT) LIKE ? ORDER BY last_seen DESC LIMIT ?",
                (f"%{cleaned}%", f"%{cleaned}%", f"%{cleaned}%", limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]

    async def save_message(
        self,
        *,
        chat_id: int,
        message_id: int,
        user_id: int,
        username: str | None,
        kind: str,
        content: str | None,
        file_id: str | None,
    ) -> int:
        db = self._conn()
        cursor = await db.execute(
            "INSERT INTO messages (chat_id, message_id, user_id, username, kind, content, file_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, user_id, username, kind, content, file_id, _now()),
        )
        await db.commit()
        return int(cursor.lastrowid or 0)

    async def record_edit(
        self, chat_id: int, message_id: int, new_content: str | None
    ) -> tuple[str | None, int | None]:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content FROM messages WHERE chat_id = ? AND message_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (chat_id, message_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None, None
        old_content = row["content"]
        edit_cursor = await db.execute(
            "INSERT INTO message_edits (message_row, old_content, edited_at) VALUES (?, ?, ?)",
            (row["id"], old_content, _now()),
        )
        await db.execute(
            "UPDATE messages SET content = ?, edited_at = ? WHERE id = ?",
            (new_content, _now(), row["id"]),
        )
        await db.commit()
        return old_content, int(edit_cursor.lastrowid or 0)

    async def get_edit(self, edit_id: int) -> dict[str, Any] | None:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM message_edits WHERE id = ?", (edit_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def user_messages(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        db = self._conn()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]

    async def get_setting(self, key: str) -> str | None:
        db = self._conn()
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        await cursor.close()
        return str(row[0]) if row else None

    async def set_setting(self, key: str, value: str | None) -> None:
        db = self._conn()
        if value:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        else:
            await db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await db.commit()
