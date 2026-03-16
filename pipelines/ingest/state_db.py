"""Pipeline de autoingesta — Base de datos de estado (SQLite WAL)."""

import sqlite3
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateDB:
    """SQLite con WAL mode para trackeo de URLs vistas, hashes y documentos."""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_urls (
                url         TEXT PRIMARY KEY,
                source_name TEXT,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seen_hashes (
                hash        TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                first_seen  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS docs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT NOT NULL,
                title       TEXT,
                source_name TEXT,
                score       REAL DEFAULT 0,
                status      TEXT DEFAULT 'pending',  -- pending, indexed, quarantine, rejected
                collection  TEXT,
                fetched_at  TEXT NOT NULL,
                indexed_at  TEXT,
                raw_path    TEXT,
                chunks      INTEGER DEFAULT 0,
                error       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_docs_status ON docs(status);
            CREATE INDEX IF NOT EXISTS idx_docs_url ON docs(url);
        """)
        self.conn.commit()

    # ── URL tracking ─────────────────────────────────

    def is_url_seen(self, url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_urls WHERE url = ?", (url,)
        ).fetchone()
        return row is not None

    def mark_url_seen(self, url: str, source_name: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO seen_urls (url, source_name, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET last_seen = ?""",
            (url, source_name, now, now, now),
        )
        self.conn.commit()

    # ── Hash dedup ───────────────────────────────────

    @staticmethod
    def text_hash(text: str) -> str:
        """SHA-256 del texto normalizado."""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    def is_hash_seen(self, text_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_hashes WHERE hash = ?", (text_hash,)
        ).fetchone()
        return row is not None

    def mark_hash_seen(self, text_hash: str, url: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_hashes (hash, url, first_seen) VALUES (?, ?, ?)",
            (text_hash, url, now),
        )
        self.conn.commit()

    # ── Document tracking ────────────────────────────

    def add_doc(
        self,
        url: str,
        title: str,
        source_name: str,
        score: float,
        status: str,
        collection: str | None = None,
        raw_path: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            """INSERT INTO docs (url, title, source_name, score, status,
                                collection, fetched_at, raw_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, title, source_name, score, status, collection, now, raw_path),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_doc_indexed(self, doc_id: int, collection: str, chunks: int):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """UPDATE docs SET status = 'indexed', collection = ?,
                              chunks = ?, indexed_at = ?
               WHERE id = ?""",
            (collection, chunks, now, doc_id),
        )
        self.conn.commit()

    def update_doc_error(self, doc_id: int, error: str):
        self.conn.execute(
            "UPDATE docs SET status = 'error', error = ? WHERE id = ?",
            (error, doc_id),
        )
        self.conn.commit()

    def get_today_stats(self) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM docs WHERE fetched_at LIKE ? GROUP BY status",
            (f"{today}%",),
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}

    def get_today_indexed(self) -> list[dict]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            """SELECT url, title, source_name, score, collection, chunks
               FROM docs WHERE status = 'indexed' AND fetched_at LIKE ?
               ORDER BY score DESC""",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
