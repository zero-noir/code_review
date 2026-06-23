from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReviewStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    uploaded_filename TEXT NOT NULL,
                    extracted_path TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    detected_stack TEXT NOT NULL,
                    default_targets TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    session_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    PRIMARY KEY(session_id, path)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_session(self, repo_name: str, uploaded_filename: str, extracted_path: Path, files: list[dict[str, Any]], default_targets: list[str], detected_stack: list[str]) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as con:
            con.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, repo_name, uploaded_filename, str(extracted_path), len(files), json.dumps(detected_stack), json.dumps(default_targets), now),
            )
            con.executemany(
                "INSERT INTO files VALUES (?, ?, ?, ?)",
                [(session_id, f["path"], int(f["size"]), f["kind"]) for f in files],
            )
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["detected_stack"] = json.loads(d["detected_stack"])
            d["default_targets"] = json.loads(d["default_targets"])
            return d

    def list_files(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT path, size, kind FROM files WHERE session_id=? ORDER BY path", (session_id,)).fetchall()]

    def save_review(self, session_id: str, objective: str, result: dict[str, Any]) -> str:
        review_id = result.get("review_id") or str(uuid.uuid4())
        result["review_id"] = review_id
        with self._connect() as con:
            con.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?, ?)",
                (review_id, session_id, objective, json.dumps(result), datetime.now(timezone.utc).isoformat()),
            )
            con.execute(
                "INSERT INTO memory VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, "last_review_summary", result.get("summary", ""), datetime.now(timezone.utc).isoformat()),
            )
        return review_id

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT s.session_id, s.repo_name, s.created_at, s.file_count, COUNT(r.review_id) AS review_count
                FROM sessions s LEFT JOIN reviews r ON r.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.created_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def counts(self) -> tuple[int, int]:
        with self._connect() as con:
            uploads = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            reviews = con.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        return int(uploads), int(reviews)

    def memory(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT key, value, created_at FROM memory WHERE session_id=? ORDER BY created_at DESC", (session_id,)).fetchall()]
