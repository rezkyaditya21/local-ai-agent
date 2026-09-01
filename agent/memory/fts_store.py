"""
agent/memory/fts_store.py

SQLite FTS5 Full-Text Search Store — menyediakan penyimpanan memori terindeks
dan pencarian teks cepat lintas sesi interaksi dan pengetahuan agen.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

DEFAULT_DB_FILENAME = "agent_memory.db"


@dataclass
class SearchResult:
    """Hasil pencarian teks dari database FTS5."""

    id: int
    category: str
    title: str
    content: str
    metadata: str
    created_at: str
    rank: float = 0.0


class SQLiteFTSStore:
    """Penyimpanan memori terindeks dengan SQLite FTS5 (Full-Text Search).

    Fitur:
    - Indexing interaksi percakapan (user prompt + agent response).
    - Indexing fakta, solusi bug, dan pengetahuan proyek.
    - Pencarian BM25 instan berbasis kata kunci dan frasa.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            config_dir = Path.home() / ".config" / "local-ai-agent"
            config_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = config_dir / DEFAULT_DB_FILENAME
        elif isinstance(db_path, str) and db_path == ":memory:":
            self._db_path = ":memory:"
        else:
            self._db_path = Path(db_path)
            if isinstance(self._db_path, Path):
                self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            path_str = str(self._db_path)
            self._conn = sqlite3.connect(path_str, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Inisialisasi tabel SQLite standar dan tabel virtual FTS5."""
        conn = self._get_connection()
        with conn:
            # Tabel dasar untuk entri memori
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            # Tabel virtual FTS5 untuk pencarian full-text
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    title,
                    content,
                    category UNINDEXED,
                    metadata UNINDEXED,
                    content='memory_records',
                    content_rowid='id'
                )
                """
            )
            # Trigger sinkronisasi otomatis antara memory_records dan memory_fts
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_records BEGIN
                    INSERT INTO memory_fts(rowid, title, content, category, metadata)
                    VALUES (new.id, new.title, new.content, new.category, new.metadata);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_records BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, title, content, category, metadata)
                    VALUES ('delete', old.id, old.title, old.content, old.category, old.metadata);
                END;
                """
            )

    def add_entry(
        self,
        category: str,
        title: str,
        content: str,
        metadata: str = "",
        created_at: str | None = None,
    ) -> int:
        """Tambahkan entri memori ke database dan indeks FTS5."""
        if created_at is None:
            created_at = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO memory_records (category, title, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category, title, content, metadata, created_at),
            )
            return cursor.lastrowid or 0

    def add_interaction(self, instruction: str, response: str) -> int:
        """Index interaksi percakapan pengguna dan respons agen."""
        title = instruction[:100].strip()
        content = f"Instruksi: {instruction}\nRespons: {response}"
        return self.add_entry(category="conversation", title=title, content=content)

    def add_fact(self, key: str, value: str, category: str = "fact") -> int:
        """Simpan fakta atau pengetahuan ke FTS5."""
        return self.add_entry(category=category, title=key, content=value)

    def search(self, query: str, limit: int = 5, category: str | None = None) -> list[SearchResult]:
        """Cari entri memori menggunakan query Full-Text Search FTS5."""
        clean_query = query.replace('"', '""').strip()
        if not clean_query:
            return []

        conn = self._get_connection()
        try:
            # Query pencarian FTS5 dengan BM25 ranking
            if category:
                sql = """
                    SELECT r.id, r.category, r.title, r.content, r.metadata, r.created_at, f.rank
                    FROM memory_fts f
                    JOIN memory_records r ON f.rowid = r.id
                    WHERE memory_fts MATCH ? AND r.category = ?
                    ORDER BY f.rank
                    LIMIT ?
                """
                params = (f'"{clean_query}" OR {clean_query}*', category, limit)
            else:
                sql = """
                    SELECT r.id, r.category, r.title, r.content, r.metadata, r.created_at, f.rank
                    FROM memory_fts f
                    JOIN memory_records r ON f.rowid = r.id
                    WHERE memory_fts MATCH ?
                    ORDER BY f.rank
                    LIMIT ?
                """
                params = (f'"{clean_query}" OR {clean_query}*', limit)

            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [
                SearchResult(
                    id=row["id"],
                    category=row["category"],
                    title=row["title"],
                    content=row["content"],
                    metadata=row["metadata"],
                    created_at=row["created_at"],
                    rank=float(row["rank"]) if "rank" in row.keys() else 0.0,
                )
                for row in rows
            ]
        except sqlite3.OperationalError as exc:
            _logger.debug("FTS5 search query fallback on '%s': %s", query, exc)
            return self._fallback_like_search(clean_query, limit, category)

    def _fallback_like_search(
        self, query: str, limit: int, category: str | None = None
    ) -> list[SearchResult]:
        """Pencarian cadangan menggunakan LIKE jika ekspresi FTS5 mengalami sintaks error."""
        conn = self._get_connection()
        like_pattern = f"%{query}%"
        if category:
            sql = """
                SELECT id, category, title, content, metadata, created_at, 0.0 as rank
                FROM memory_records
                WHERE (title LIKE ? OR content LIKE ?) AND category = ?
                ORDER BY id DESC
                LIMIT ?
            """
            cursor = conn.execute(sql, (like_pattern, like_pattern, category, limit))
        else:
            sql = """
                SELECT id, category, title, content, metadata, created_at, 0.0 as rank
                FROM memory_records
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY id DESC
                LIMIT ?
            """
            cursor = conn.execute(sql, (like_pattern, like_pattern, limit))

        rows = cursor.fetchall()
        return [
            SearchResult(
                id=row["id"],
                category=row["category"],
                title=row["title"],
                content=row["content"],
                metadata=row["metadata"],
                created_at=row["created_at"],
                rank=0.0,
            )
            for row in rows
        ]

    def get_recent(self, limit: int = 10, category: str | None = None) -> list[SearchResult]:
        """Ambil entri memori terbaru."""
        conn = self._get_connection()
        if category:
            sql = """
                SELECT id, category, title, content, metadata, created_at, 0.0 as rank
                FROM memory_records
                WHERE category = ?
                ORDER BY id DESC
                LIMIT ?
            """
            cursor = conn.execute(sql, (category, limit))
        else:
            sql = """
                SELECT id, category, title, content, metadata, created_at, 0.0 as rank
                FROM memory_records
                ORDER BY id DESC
                LIMIT ?
            """
            cursor = conn.execute(sql, (limit,))

        rows = cursor.fetchall()
        return [
            SearchResult(
                id=row["id"],
                category=row["category"],
                title=row["title"],
                content=row["content"],
                metadata=row["metadata"],
                created_at=row["created_at"],
                rank=0.0,
            )
            for row in rows
        ]

    def count(self) -> int:
        """Jumlah total entri memori."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM memory_records")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        """Tutup koneksi database."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


__all__ = ["SQLiteFTSStore", "SearchResult"]
