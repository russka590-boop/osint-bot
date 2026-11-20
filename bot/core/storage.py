from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
"""


class Storage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
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
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                user_id,
                username,
                kind,
                target,
                plugins,
                found,
                elapsed,
                status,
            ),
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
