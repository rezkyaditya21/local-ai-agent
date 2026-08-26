"""
agent/tools/database.py

DatabaseTool — Tool untuk mengakses dan memanipulasi database lokal.

Mendukung:
- SQLite via stdlib `sqlite3` (dijalankan di thread pool agar tidak memblokir event loop)
- PostgreSQL / MySQL via SQLAlchemy async engine

Komponen utama:
- `DatabaseTool`: Mengimplementasikan `ToolInterface`; menyediakan connect, select,
  execute_dml, get_schema, dan disconnect.

Requirements yang diimplementasikan: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from agent.core.exceptions import (
    AgentDatabaseConnectionError,
    AgentQueryExecutionError,
)
from agent.models.schemas import (
    ColumnInfo,
    DatabaseSchema,
    TableSchema,
    ToolResult,
)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_SELECT_ROWS = 1000

# Ekstensi yang dianggap sebagai file SQLite
_SQLITE_EXTENSIONS = (".db", ".sqlite", ".sqlite3")

# Prefix skema URL yang mengindikasikan koneksi non-SQLite (mis. PostgreSQL/MySQL)
_URL_SCHEMES = (
    "postgresql://",
    "postgresql+",
    "postgres://",
    "mysql://",
    "mysql+",
    "mariadb://",
    "mariadb+",
    "mssql://",
    "mssql+",
    "oracle://",
    "oracle+",
)


# ---------------------------------------------------------------------------
# Helper: deteksi tipe connection string
# ---------------------------------------------------------------------------


def _is_sqlite_connection(connection_string: str) -> bool:
    """Tentukan apakah connection_string mengarah ke file SQLite.

    Sebuah string dianggap SQLite jika:
    - Diawali dengan "sqlite://" atau "sqlite:///"
    - Diakhiri dengan ekstensi SQLite yang dikenal (.db, .sqlite, .sqlite3)
    - Tidak diawali dengan skema URL database lain

    Args:
        connection_string: Path file atau URL koneksi database.

    Returns:
        True jika koneksi adalah SQLite, False jika tidak.
    """
    cs = connection_string.strip()

    # Eksplisit SQLite URL
    if cs.startswith("sqlite://"):
        return True

    # Eksplisit non-SQLite URL
    for scheme in _URL_SCHEMES:
        if cs.lower().startswith(scheme):
            return False

    # Tidak ada skema URL → anggap path file; periksa ekstensi
    lower = cs.lower()
    if any(lower.endswith(ext) for ext in _SQLITE_EXTENSIONS):
        return True

    # Tidak ada ekstensi dikenal tapi juga tidak ada skema → anggap SQLite
    return True


def _sqlite_path_from_connection_string(connection_string: str) -> str:
    """Ekstrak path file dari connection string SQLite.

    Args:
        connection_string: Path file atau sqlite:// URL.

    Returns:
        Path file absolut atau relatif ke database SQLite.
    """
    cs = connection_string.strip()

    # "sqlite:///path/to/db.sqlite" → "/path/to/db.sqlite"
    if cs.startswith("sqlite:///"):
        return cs[len("sqlite:///"):]
    # "sqlite:///:memory:" → ":memory:"
    if cs.startswith("sqlite://"):
        return cs[len("sqlite://"):]

    return cs


# ---------------------------------------------------------------------------
# DatabaseTool
# ---------------------------------------------------------------------------


class DatabaseTool:
    """Tool untuk koneksi dan operasi database lokal.

    Mendukung SQLite (via stdlib sqlite3) dan database lain melalui
    SQLAlchemy (PostgreSQL, MySQL, dll.) jika SQLAlchemy tersedia.

    Attributes:
        name: Identifier tool.
        description: Deskripsi singkat untuk pemilihan otomatis oleh Agent.
        input_schema: Skema parameter masukan (JSON Schema kompatibel).
        output_schema: Skema nilai kembalian (JSON Schema kompatibel).
    """

    name = "database"
    description = (
        "Menghubungkan ke database SQLite atau database relasional (PostgreSQL/MySQL) "
        "dan menjalankan query SQL SELECT, DML (INSERT/UPDATE/DELETE), serta mengambil "
        "skema tabel."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["connect", "select", "execute_dml", "get_schema", "disconnect"],
                "description": "Operasi yang akan dijalankan.",
            },
            "connection_string": {
                "type": "string",
                "description": "Path SQLite atau URL koneksi database (untuk 'connect').",
            },
            "query": {
                "type": "string",
                "description": "Query SQL yang akan dieksekusi (untuk 'select' atau 'execute_dml').",
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "data": {"description": "Hasil operasi (rows, schema, atau None)."},
            "error": {"type": ["string", "null"]},
        },
    }

    def __init__(self) -> None:
        # Koneksi SQLite aktif (stdlib)
        self._sqlite_conn: sqlite3.Connection | None = None
        # Koneksi string aktif (untuk referensi error)
        self._active_connection_string: str | None = None
        # Tipe koneksi aktif: "sqlite" | "sqlalchemy"
        self._connection_type: str | None = None
        # SQLAlchemy engine/connection (lazy-import)
        self._sa_engine: Any = None
        self._sa_conn: Any = None
        # Lock agar tidak ada dua operasi concurrent pada koneksi yang sama
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # ToolInterface: run() dispatcher
    # ------------------------------------------------------------------

    async def run(self, params: dict) -> ToolResult:
        """Eksekusi operasi database berdasarkan `params["operation"]`.

        Operasi yang didukung:
        - ``"connect"``: Buka koneksi ke database.
        - ``"select"``: Jalankan query SELECT.
        - ``"execute_dml"``: Jalankan query DML (INSERT/UPDATE/DELETE).
        - ``"get_schema"``: Ambil skema database.
        - ``"disconnect"``: Tutup koneksi aktif.

        Args:
            params: Dict yang setidaknya mengandung key ``"operation"``.

        Returns:
            `ToolResult` dengan `success=True` dan `data` berisi hasil operasi,
            atau `ToolResult(success=False, error=...)` jika terjadi kegagalan.
        """
        operation = params.get("operation", "")

        try:
            if operation == "connect":
                conn_str = params.get("connection_string", "")
                await self.connect(conn_str)
                return ToolResult(
                    success=True,
                    data={"message": f"Terhubung ke database: {conn_str}"},
                    tool_name=self.name,
                )

            elif operation == "select":
                query = params.get("query", "")
                rows = await self.select(query)
                return ToolResult(success=True, data=rows, tool_name=self.name)

            elif operation == "execute_dml":
                query = params.get("query", "")
                await self.execute_dml(query)
                return ToolResult(
                    success=True,
                    data={"message": "DML berhasil dieksekusi."},
                    tool_name=self.name,
                )

            elif operation == "get_schema":
                schema = await self.get_schema()
                return ToolResult(success=True, data=schema, tool_name=self.name)

            elif operation == "disconnect":
                await self.disconnect()
                return ToolResult(
                    success=True,
                    data={"message": "Koneksi database ditutup."},
                    tool_name=self.name,
                )

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Operasi tidak dikenal: '{operation}'. "
                          "Operasi yang didukung: connect, select, execute_dml, get_schema, disconnect.",
                    tool_name=self.name,
                )

        except (AgentDatabaseConnectionError, AgentQueryExecutionError) as exc:
            return ToolResult(success=False, data=None, error=str(exc), tool_name=self.name)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                data=None,
                error=f"Error tidak terduga pada operasi '{operation}': {exc}",
                tool_name=self.name,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self, connection_string: str) -> None:
        """Buka koneksi ke database.

        Untuk SQLite:
        - Validasi bahwa file ada dan merupakan database SQLite yang valid
          (dengan mencoba membaca ``sqlite_master``).
        - Tidak membuat file baru jika path tidak ada (Requirement 5.2).

        Untuk non-SQLite (PostgreSQL/MySQL/dll.):
        - Gunakan SQLAlchemy async engine.
        - SQLAlchemy harus tersedia; jika tidak, raise ``AgentDatabaseConnectionError``.

        Args:
            connection_string: Path file SQLite, sqlite:// URL, atau
                connection URL SQLAlchemy.

        Raises:
            AgentDatabaseConnectionError: Jika koneksi gagal (E008).
        """
        if not connection_string or not connection_string.strip():
            raise AgentDatabaseConnectionError(
                connection_string=connection_string,
                reason="connection string tidak boleh kosong",
            )

        async with self._lock:
            # Tutup koneksi sebelumnya jika ada
            await self._close_current_connection()

            if _is_sqlite_connection(connection_string):
                await self._connect_sqlite(connection_string)
            else:
                await self._connect_sqlalchemy(connection_string)

            self._active_connection_string = connection_string

    async def select(self, query: str) -> list[dict]:
        """Jalankan query SQL SELECT dan kembalikan hasilnya.

        Membatasi hasil hingga `MAX_SELECT_ROWS` (1.000) baris. Jika query
        mengembalikan lebih banyak baris, hanya 1.000 baris pertama yang dikembalikan.

        Args:
            query: Query SQL SELECT yang akan dieksekusi.

        Returns:
            Daftar dict dengan pemetaan nama kolom ke nilai. Daftar kosong jika
            tidak ada hasil.

        Raises:
            AgentDatabaseConnectionError: Jika tidak ada koneksi aktif (E008).
            AgentQueryExecutionError: Jika query gagal dieksekusi (E009).
        """
        self._require_connection()

        async with self._lock:
            if self._connection_type == "sqlite":
                return await self._select_sqlite(query)
            else:
                return await self._select_sqlalchemy(query)

    async def execute_dml(self, query: str) -> None:
        """Jalankan query DML (INSERT, UPDATE, DELETE, DDL, dsb.).

        Operasi ini dieksekusi di dalam transaksi. Jika terjadi error, transaksi
        di-rollback sehingga state database tidak berubah (Requirement 5.6).

        Catatan: Caller (Executor/Agent) bertanggung jawab untuk meminta konfirmasi
        via ConfirmationGate sebelum memanggil method ini (Requirement 5.4).

        Args:
            query: Query SQL DML/DDL yang akan dieksekusi.

        Raises:
            AgentDatabaseConnectionError: Jika tidak ada koneksi aktif (E008).
            AgentQueryExecutionError: Jika query gagal dieksekusi (E009).
        """
        self._require_connection()

        async with self._lock:
            if self._connection_type == "sqlite":
                await self._execute_dml_sqlite(query)
            else:
                await self._execute_dml_sqlalchemy(query)

    async def get_schema(self) -> DatabaseSchema:
        """Ambil skema lengkap database aktif.

        Untuk SQLite: gunakan ``sqlite_master`` dan ``PRAGMA table_info``.
        Untuk SQLAlchemy: gunakan ``inspect()`` dari SQLAlchemy.

        Returns:
            `DatabaseSchema` berisi daftar `TableSchema`, setiap tabel berisi
            daftar `ColumnInfo` dengan nama, tipe data, dan constraint.

        Raises:
            AgentDatabaseConnectionError: Jika tidak ada koneksi aktif (E008).
            AgentQueryExecutionError: Jika pengambilan skema gagal (E009).
        """
        self._require_connection()

        async with self._lock:
            if self._connection_type == "sqlite":
                return await self._get_schema_sqlite()
            else:
                return await self._get_schema_sqlalchemy()

    async def disconnect(self) -> None:
        """Tutup koneksi database aktif.

        Aman untuk dipanggil meski tidak ada koneksi aktif (no-op).
        """
        async with self._lock:
            await self._close_current_connection()

    # ------------------------------------------------------------------
    # Internal: koneksi SQLite
    # ------------------------------------------------------------------

    async def _connect_sqlite(self, connection_string: str) -> None:
        """Buka dan validasi koneksi SQLite.

        Raises:
            AgentDatabaseConnectionError: Jika file tidak ada, bukan SQLite valid,
                atau terjadi error lain saat koneksi (E008).
        """
        path = _sqlite_path_from_connection_string(connection_string)

        # Jangan buat file baru — validasi keberadaan file (Requirement 5.2)
        import os
        if path != ":memory:" and not os.path.exists(path):
            raise AgentDatabaseConnectionError(
                connection_string=connection_string,
                reason=f"file tidak ditemukan: '{path}'",
            )

        loop = asyncio.get_event_loop()

        def _open_and_validate() -> sqlite3.Connection:
            try:
                # isolation_level=None → autocommit mode; kita kelola transaksi manual
                conn = sqlite3.connect(path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                # Validasi bahwa ini adalah file SQLite yang valid
                conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                return conn
            except sqlite3.DatabaseError as exc:
                raise AgentDatabaseConnectionError(
                    connection_string=connection_string,
                    reason=f"invalid_sqlite_file: {exc}",
                ) from exc
            except Exception as exc:
                raise AgentDatabaseConnectionError(
                    connection_string=connection_string,
                    reason=str(exc),
                ) from exc

        try:
            conn = await loop.run_in_executor(None, _open_and_validate)
        except AgentDatabaseConnectionError:
            raise
        except Exception as exc:
            raise AgentDatabaseConnectionError(
                connection_string=connection_string,
                reason=str(exc),
            ) from exc

        self._sqlite_conn = conn
        self._connection_type = "sqlite"

    async def _select_sqlite(self, query: str) -> list[dict]:
        """Eksekusi SELECT pada koneksi SQLite aktif."""
        conn = self._sqlite_conn
        loop = asyncio.get_event_loop()

        def _run() -> list[dict]:
            try:
                cursor = conn.execute(query)  # type: ignore[union-attr]
                rows = cursor.fetchmany(MAX_SELECT_ROWS)
                return [dict(row) for row in rows]
            except sqlite3.Error as exc:
                raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

        try:
            return await loop.run_in_executor(None, _run)
        except AgentQueryExecutionError:
            raise
        except Exception as exc:
            raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

    async def _execute_dml_sqlite(self, query: str) -> None:
        """Eksekusi DML dalam transaksi SQLite; rollback otomatis jika gagal."""
        conn = self._sqlite_conn
        loop = asyncio.get_event_loop()

        def _run() -> None:
            try:
                with conn:  # type: ignore[union-attr]
                    # Context manager `with conn` otomatis commit jika berhasil,
                    # rollback jika exception (Requirement 5.6)
                    conn.execute(query)  # type: ignore[union-attr]
            except sqlite3.Error as exc:
                raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

        try:
            await loop.run_in_executor(None, _run)
        except AgentQueryExecutionError:
            raise
        except Exception as exc:
            raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

    async def _get_schema_sqlite(self) -> DatabaseSchema:
        """Ambil skema dari SQLite menggunakan sqlite_master dan PRAGMA table_info."""
        conn = self._sqlite_conn
        loop = asyncio.get_event_loop()

        def _run() -> DatabaseSchema:
            try:
                # Daftar semua tabel
                cursor = conn.execute(  # type: ignore[union-attr]
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                table_names = [row[0] for row in cursor.fetchall()]

                table_schemas: list[TableSchema] = []
                for table_name in table_names:
                    # PRAGMA table_info mengembalikan:
                    # cid, name, type, notnull, dflt_value, pk
                    info_cursor = conn.execute(  # type: ignore[union-attr]
                        f"PRAGMA table_info({table_name})"
                    )
                    columns: list[ColumnInfo] = []
                    for row in info_cursor.fetchall():
                        col = ColumnInfo(
                            name=row["name"],
                            data_type=row["type"] or "TEXT",
                            is_primary_key=bool(row["pk"]),
                            is_nullable=not bool(row["notnull"]),
                            is_unique=False,  # PRAGMA table_info tidak expose UNIQUE secara langsung
                        )
                        columns.append(col)

                    # Cek UNIQUE constraints dari sqlite_master (index unik)
                    unique_cols = _get_sqlite_unique_columns(conn, table_name)
                    for col in columns:
                        if col.name in unique_cols or col.is_primary_key:
                            col.is_unique = True

                    table_schemas.append(TableSchema(name=table_name, columns=columns))

                return DatabaseSchema(tables=table_schemas)

            except sqlite3.Error as exc:
                raise AgentQueryExecutionError(
                    query="GET_SCHEMA",
                    reason=str(exc),
                ) from exc

        try:
            return await loop.run_in_executor(None, _run)
        except AgentQueryExecutionError:
            raise
        except Exception as exc:
            raise AgentQueryExecutionError(query="GET_SCHEMA", reason=str(exc)) from exc

    # ------------------------------------------------------------------
    # Internal: koneksi SQLAlchemy (PostgreSQL/MySQL/dll.)
    # ------------------------------------------------------------------

    async def _connect_sqlalchemy(self, connection_string: str) -> None:
        """Buka koneksi melalui SQLAlchemy.

        Raises:
            AgentDatabaseConnectionError: Jika SQLAlchemy tidak tersedia atau
                koneksi gagal (E008).
        """
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError:
            raise AgentDatabaseConnectionError(
                connection_string=connection_string,
                reason=(
                    "SQLAlchemy tidak tersedia; install dengan "
                    "`pip install sqlalchemy[asyncio]` untuk dukungan database non-SQLite"
                ),
            )

        try:
            engine = create_async_engine(connection_string, echo=False)
            # Uji koneksi
            async with engine.connect() as conn:
                await conn.execute(_sa_text("SELECT 1"))
            self._sa_engine = engine
            self._connection_type = "sqlalchemy"
        except Exception as exc:
            raise AgentDatabaseConnectionError(
                connection_string=connection_string,
                reason=str(exc),
            ) from exc

    async def _select_sqlalchemy(self, query: str) -> list[dict]:
        """Eksekusi SELECT via SQLAlchemy."""
        try:
            from sqlalchemy import text as _text
        except ImportError:
            raise AgentDatabaseConnectionError(
                connection_string=self._active_connection_string or "",
                reason="SQLAlchemy tidak tersedia",
            )

        try:
            async with self._sa_engine.connect() as conn:
                result = await conn.execute(_text(query))
                rows = result.fetchmany(MAX_SELECT_ROWS)
                keys = list(result.keys())
                return [dict(zip(keys, row)) for row in rows]
        except Exception as exc:
            raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

    async def _execute_dml_sqlalchemy(self, query: str) -> None:
        """Eksekusi DML via SQLAlchemy dalam transaksi; rollback otomatis jika gagal."""
        try:
            from sqlalchemy import text as _text
        except ImportError:
            raise AgentDatabaseConnectionError(
                connection_string=self._active_connection_string or "",
                reason="SQLAlchemy tidak tersedia",
            )

        try:
            async with self._sa_engine.begin() as conn:
                # begin() otomatis commit jika tidak ada exception, rollback jika ada
                await conn.execute(_text(query))
        except Exception as exc:
            raise AgentQueryExecutionError(query=query, reason=str(exc)) from exc

    async def _get_schema_sqlalchemy(self) -> DatabaseSchema:
        """Ambil skema database via SQLAlchemy Inspector."""
        try:
            from sqlalchemy import inspect as sa_inspect, text as _text
            from sqlalchemy.ext.asyncio import AsyncConnection
        except ImportError:
            raise AgentDatabaseConnectionError(
                connection_string=self._active_connection_string or "",
                reason="SQLAlchemy tidak tersedia",
            )

        try:
            async with self._sa_engine.connect() as conn:
                # run_sync diperlukan karena Inspector adalah synchronous
                def _inspect(sync_conn: Any) -> DatabaseSchema:
                    inspector = sa_inspect(sync_conn)
                    table_names = inspector.get_table_names()
                    table_schemas: list[TableSchema] = []

                    for table_name in sorted(table_names):
                        pk_cols = set(inspector.get_pk_constraint(table_name).get("constrained_columns", []))
                        unique_constraints = inspector.get_unique_constraints(table_name)
                        unique_cols: set[str] = set()
                        for uc in unique_constraints:
                            unique_cols.update(uc.get("column_names", []))

                        columns: list[ColumnInfo] = []
                        for col in inspector.get_columns(table_name):
                            col_name = col["name"]
                            columns.append(
                                ColumnInfo(
                                    name=col_name,
                                    data_type=str(col["type"]),
                                    is_primary_key=col_name in pk_cols,
                                    is_nullable=col.get("nullable", True),
                                    is_unique=col_name in unique_cols or col_name in pk_cols,
                                )
                            )
                        table_schemas.append(TableSchema(name=table_name, columns=columns))

                    return DatabaseSchema(tables=table_schemas)

                return await conn.run_sync(_inspect)
        except AgentDatabaseConnectionError:
            raise
        except Exception as exc:
            raise AgentQueryExecutionError(query="GET_SCHEMA", reason=str(exc)) from exc

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    async def _close_current_connection(self) -> None:
        """Tutup koneksi aktif (SQLite atau SQLAlchemy). Thread-safe."""
        if self._sqlite_conn is not None:
            conn = self._sqlite_conn
            self._sqlite_conn = None
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, conn.close)

        if self._sa_engine is not None:
            engine = self._sa_engine
            self._sa_engine = None
            self._sa_conn = None
            try:
                await engine.dispose()
            except Exception:  # noqa: BLE001
                pass

        self._connection_type = None
        self._active_connection_string = None

    def _require_connection(self) -> None:
        """Periksa bahwa ada koneksi aktif.

        Raises:
            AgentDatabaseConnectionError: Jika tidak ada koneksi aktif (E008).
        """
        if self._connection_type is None:
            raise AgentDatabaseConnectionError(
                connection_string="",
                reason="tidak ada koneksi database aktif; panggil connect() terlebih dahulu",
            )


# ---------------------------------------------------------------------------
# Modul-level helper (di luar kelas agar dapat diuji secara independen)
# ---------------------------------------------------------------------------


def _get_sqlite_unique_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """Kembalikan set nama kolom yang memiliki UNIQUE index pada tabel SQLite.

    Menggunakan ``PRAGMA index_list`` dan ``PRAGMA index_info`` untuk menemukan
    semua single-column UNIQUE index pada tabel yang diberikan.

    Args:
        conn: Koneksi SQLite yang sudah terbuka.
        table_name: Nama tabel yang akan diperiksa.

    Returns:
        Set nama kolom yang memiliki UNIQUE constraint/index.
    """
    unique_cols: set[str] = set()
    try:
        idx_cursor = conn.execute(f"PRAGMA index_list({table_name})")
        for idx_row in idx_cursor.fetchall():
            is_unique = bool(idx_row["unique"])
            if not is_unique:
                continue
            idx_name = idx_row["name"]
            info_cursor = conn.execute(f"PRAGMA index_info({idx_name})")
            info_rows = info_cursor.fetchall()
            # Hanya tandai UNIQUE jika index ini adalah single-column
            if len(info_rows) == 1:
                unique_cols.add(info_rows[0]["name"])
    except sqlite3.Error:
        pass  # Graceful — gagal memeriksa UNIQUE tidak menghentikan get_schema
    return unique_cols


# Lazy import helper untuk SQLAlchemy text() agar tidak gagal import jika SA tidak ada
def _sa_text(sql: str) -> Any:
    from sqlalchemy import text
    return text(sql)


__all__ = [
    "MAX_SELECT_ROWS",
    "DatabaseTool",
]
