"""
tests/unit/test_database_tool.py

Unit tests untuk DatabaseTool.

Mencakup:
- Deteksi tipe connection string (SQLite vs non-SQLite)
- connect(): validasi file ada, validasi file SQLite valid, error file tidak ada
- select(): hasil baris, batas 1000 baris, error query invalid
- execute_dml(): INSERT/UPDATE berhasil, rollback otomatis saat gagal
- get_schema(): struktur TableSchema dan ColumnInfo yang dihasilkan
- disconnect(): idempoten (aman dipanggil tanpa koneksi aktif)
- run() dispatcher: semua operasi dan operasi tidak dikenal
- _require_connection(): error saat tidak ada koneksi aktif

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
from pathlib import Path

import pytest

from agent.tools.database import DatabaseTool, MAX_SELECT_ROWS, _is_sqlite_connection
from agent.core.exceptions import AgentDatabaseConnectionError, AgentQueryExecutionError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool() -> DatabaseTool:
    """DatabaseTool instance baru untuk setiap test."""
    return DatabaseTool()


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> str:
    """Buat file SQLite sementara yang valid dengan tabel dan data awal."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, age INTEGER)"
    )
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def empty_sqlite_db_path(tmp_path: Path) -> str:
    """Buat file SQLite sementara yang valid namun tanpa tabel."""
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def invalid_sqlite_path(tmp_path: Path) -> str:
    """Buat file yang bukan SQLite (isi teks biasa)."""
    bad_path = str(tmp_path / "bad.db")
    with open(bad_path, "w") as f:
        f.write("ini bukan SQLite file")
    return bad_path


# ---------------------------------------------------------------------------
# Tests: _is_sqlite_connection
# ---------------------------------------------------------------------------


class TestIsSqliteConnection:
    def test_sqlite_url_prefix(self):
        assert _is_sqlite_connection("sqlite:///path/to/db.sqlite") is True

    def test_sqlite_memory(self):
        assert _is_sqlite_connection("sqlite:///:memory:") is True

    def test_db_extension(self):
        assert _is_sqlite_connection("/home/user/data.db") is True

    def test_sqlite_extension(self):
        assert _is_sqlite_connection("relative/path/data.sqlite") is True

    def test_sqlite3_extension(self):
        assert _is_sqlite_connection("data.sqlite3") is True

    def test_postgresql_url(self):
        assert _is_sqlite_connection("postgresql://user:pass@localhost/mydb") is False

    def test_mysql_url(self):
        assert _is_sqlite_connection("mysql://user:pass@localhost/mydb") is False

    def test_postgres_short(self):
        assert _is_sqlite_connection("postgres://localhost/db") is False

    def test_unknown_no_extension_treated_as_sqlite(self):
        # Path tanpa ekstensi dikenal → anggap SQLite (fallback)
        assert _is_sqlite_connection("/some/path/mydb") is True


# ---------------------------------------------------------------------------
# Tests: connect()
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_valid_sqlite(self, tool, sqlite_db_path):
        """Requirement 5.1: koneksi ke SQLite path yang valid berhasil."""
        await tool.connect(sqlite_db_path)
        assert tool._connection_type == "sqlite"
        assert tool._sqlite_conn is not None
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_connect_nonexistent_file_raises_e008(self, tool, tmp_path):
        """Requirement 5.2: file tidak ada → E008, tidak membuat file baru."""
        nonexistent = str(tmp_path / "does_not_exist.db")
        with pytest.raises(AgentDatabaseConnectionError) as exc_info:
            await tool.connect(nonexistent)
        assert "E008" in str(exc_info.value)
        assert nonexistent in str(exc_info.value) or "tidak ditemukan" in str(exc_info.value)
        # Pastikan file tidak dibuat
        assert not os.path.exists(nonexistent)

    @pytest.mark.asyncio
    async def test_connect_invalid_sqlite_file_raises_e008(self, tool, invalid_sqlite_path):
        """Requirement 5.2: file ada tapi bukan SQLite valid → E008."""
        with pytest.raises(AgentDatabaseConnectionError) as exc_info:
            await tool.connect(invalid_sqlite_path)
        assert "E008" in str(exc_info.value)
        assert "invalid_sqlite_file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_empty_string_raises_e008(self, tool):
        """String kosong tidak valid → E008."""
        with pytest.raises(AgentDatabaseConnectionError):
            await tool.connect("")

    @pytest.mark.asyncio
    async def test_connect_replaces_existing_connection(self, tool, sqlite_db_path, empty_sqlite_db_path):
        """Koneksi kedua menutup koneksi pertama dan membuka yang baru."""
        await tool.connect(sqlite_db_path)
        first_conn = tool._sqlite_conn
        await tool.connect(empty_sqlite_db_path)
        assert tool._sqlite_conn is not first_conn
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_connect_sqlite_url_format(self, tool, sqlite_db_path):
        """Mendukung format sqlite:///path."""
        url = f"sqlite:///{sqlite_db_path}"
        await tool.connect(url)
        assert tool._connection_type == "sqlite"
        await tool.disconnect()


# ---------------------------------------------------------------------------
# Tests: select()
# ---------------------------------------------------------------------------


class TestSelect:
    @pytest.mark.asyncio
    async def test_select_returns_list_of_dicts(self, tool, sqlite_db_path):
        """Requirement 5.3: SELECT mengembalikan list[dict] dengan nama kolom."""
        await tool.connect(sqlite_db_path)
        rows = await tool.select("SELECT id, name, age FROM users ORDER BY id")
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert rows[0] == {"id": 1, "name": "Alice", "age": 30}
        assert rows[1] == {"id": 2, "name": "Bob", "age": 25}
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_select_empty_result(self, tool, sqlite_db_path):
        """SELECT tanpa hasil mengembalikan list kosong."""
        await tool.connect(sqlite_db_path)
        rows = await tool.select("SELECT * FROM users WHERE age > 100")
        assert rows == []
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_select_max_rows_limit(self, tool, tmp_path):
        """Requirement 5.3: batas 1000 baris — tidak mengembalikan lebih dari MAX_SELECT_ROWS."""
        db_path = str(tmp_path / "big.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE nums (n INTEGER)")
        conn.executemany("INSERT INTO nums VALUES (?)", [(i,) for i in range(1500)])
        conn.commit()
        conn.close()

        await tool.connect(db_path)
        rows = await tool.select("SELECT n FROM nums")
        assert len(rows) <= MAX_SELECT_ROWS
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_select_invalid_query_raises_e009(self, tool, sqlite_db_path):
        """Requirement 5.6: query tidak valid → E009, state DB tidak berubah."""
        await tool.connect(sqlite_db_path)
        with pytest.raises(AgentQueryExecutionError) as exc_info:
            await tool.select("SELECT * FROM nonexistent_table")
        assert "E009" in str(exc_info.value)
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_select_without_connection_raises_e008(self, tool):
        """Tidak ada koneksi aktif → E008 dari _require_connection."""
        with pytest.raises(AgentDatabaseConnectionError):
            await tool.select("SELECT 1")


# ---------------------------------------------------------------------------
# Tests: execute_dml()
# ---------------------------------------------------------------------------


class TestExecuteDml:
    @pytest.mark.asyncio
    async def test_insert_data(self, tool, sqlite_db_path):
        """INSERT berhasil dan data tersimpan."""
        await tool.connect(sqlite_db_path)
        await tool.execute_dml("INSERT INTO users VALUES (3, 'Charlie', 35)")
        rows = await tool.select("SELECT id, name FROM users WHERE id = 3")
        assert len(rows) == 1
        assert rows[0]["name"] == "Charlie"
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_update_data(self, tool, sqlite_db_path):
        """UPDATE berhasil dan data berubah."""
        await tool.connect(sqlite_db_path)
        await tool.execute_dml("UPDATE users SET age = 31 WHERE id = 1")
        rows = await tool.select("SELECT age FROM users WHERE id = 1")
        assert rows[0]["age"] == 31
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_delete_data(self, tool, sqlite_db_path):
        """DELETE berhasil dan baris terhapus."""
        await tool.connect(sqlite_db_path)
        await tool.execute_dml("DELETE FROM users WHERE id = 2")
        rows = await tool.select("SELECT * FROM users WHERE id = 2")
        assert rows == []
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_dml_rollback_on_error(self, tool, sqlite_db_path):
        """Requirement 5.6: DML yang gagal di-rollback — state DB tidak berubah."""
        await tool.connect(sqlite_db_path)
        # Ambil jumlah baris sebelum operasi gagal
        rows_before = await tool.select("SELECT * FROM users")
        count_before = len(rows_before)

        # Coba INSERT dengan UNIQUE violation — harus gagal
        with pytest.raises(AgentQueryExecutionError):
            await tool.execute_dml("INSERT INTO users VALUES (1, 'Alice', 99)")

        # Jumlah baris harus sama (rollback terjadi)
        rows_after = await tool.select("SELECT * FROM users")
        assert len(rows_after) == count_before
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_dml_invalid_sql_raises_e009(self, tool, sqlite_db_path):
        """SQL tidak valid → E009."""
        await tool.connect(sqlite_db_path)
        with pytest.raises(AgentQueryExecutionError) as exc_info:
            await tool.execute_dml("INSERT INTO nonexistent VALUES (1)")
        assert "E009" in str(exc_info.value)
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_dml_without_connection_raises_e008(self, tool):
        """Tidak ada koneksi aktif → E008."""
        with pytest.raises(AgentDatabaseConnectionError):
            await tool.execute_dml("INSERT INTO t VALUES (1)")


# ---------------------------------------------------------------------------
# Tests: get_schema()
# ---------------------------------------------------------------------------


class TestGetSchema:
    @pytest.mark.asyncio
    async def test_schema_has_correct_tables(self, tool, sqlite_db_path):
        """Requirement 5.5: get_schema mengembalikan DatabaseSchema dengan tabel yang benar."""
        from agent.models.schemas import DatabaseSchema, TableSchema
        await tool.connect(sqlite_db_path)
        schema = await tool.get_schema()
        assert isinstance(schema, DatabaseSchema)
        assert len(schema.tables) == 1
        assert schema.tables[0].name == "users"
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_schema_columns(self, tool, sqlite_db_path):
        """Requirement 5.5: kolom memiliki nama, tipe data, dan constraint yang benar."""
        from agent.models.schemas import ColumnInfo
        await tool.connect(sqlite_db_path)
        schema = await tool.get_schema()
        table = schema.tables[0]
        col_map = {c.name: c for c in table.columns}

        assert "id" in col_map
        assert col_map["id"].is_primary_key is True

        assert "name" in col_map
        assert col_map["name"].is_nullable is False  # NOT NULL
        assert col_map["name"].is_unique is True     # UNIQUE

        assert "age" in col_map
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_schema_empty_db(self, tool, empty_sqlite_db_path):
        """Database tanpa tabel → DatabaseSchema dengan daftar tabel kosong."""
        await tool.connect(empty_sqlite_db_path)
        schema = await tool.get_schema()
        assert schema.tables == []
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_schema_multiple_tables(self, tool, tmp_path):
        """Beberapa tabel dikembalikan semua."""
        db_path = str(tmp_path / "multi.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE a (x INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE b (y TEXT, z REAL)")
        conn.commit()
        conn.close()

        await tool.connect(db_path)
        schema = await tool.get_schema()
        names = {t.name for t in schema.tables}
        assert "a" in names
        assert "b" in names
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_schema_without_connection_raises_e008(self, tool):
        """Tidak ada koneksi aktif → E008."""
        with pytest.raises(AgentDatabaseConnectionError):
            await tool.get_schema()


# ---------------------------------------------------------------------------
# Tests: disconnect()
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self, tool, sqlite_db_path):
        """Setelah disconnect, _connection_type menjadi None."""
        await tool.connect(sqlite_db_path)
        await tool.disconnect()
        assert tool._connection_type is None
        assert tool._sqlite_conn is None

    @pytest.mark.asyncio
    async def test_disconnect_without_connection_is_noop(self, tool):
        """Disconnect tanpa koneksi aktif tidak menimbulkan error (idempoten)."""
        await tool.disconnect()  # Tidak boleh raise exception

    @pytest.mark.asyncio
    async def test_double_disconnect_is_safe(self, tool, sqlite_db_path):
        """Disconnect ganda aman dilakukan."""
        await tool.connect(sqlite_db_path)
        await tool.disconnect()
        await tool.disconnect()  # Tidak boleh raise exception


# ---------------------------------------------------------------------------
# Tests: run() dispatcher
# ---------------------------------------------------------------------------


class TestRunDispatcher:
    @pytest.mark.asyncio
    async def test_run_connect(self, tool, sqlite_db_path):
        """run() dengan operation='connect' berhasil."""
        result = await tool.run({"operation": "connect", "connection_string": sqlite_db_path})
        assert result.success is True
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_run_select(self, tool, sqlite_db_path):
        """run() dengan operation='select' mengembalikan baris."""
        await tool.connect(sqlite_db_path)
        result = await tool.run({"operation": "select", "query": "SELECT * FROM users"})
        assert result.success is True
        assert isinstance(result.data, list)
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_run_execute_dml(self, tool, sqlite_db_path):
        """run() dengan operation='execute_dml' menjalankan DML."""
        await tool.connect(sqlite_db_path)
        result = await tool.run({
            "operation": "execute_dml",
            "query": "INSERT INTO users VALUES (10, 'Test', 20)",
        })
        assert result.success is True
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_run_get_schema(self, tool, sqlite_db_path):
        """run() dengan operation='get_schema' mengembalikan DatabaseSchema."""
        from agent.models.schemas import DatabaseSchema
        await tool.connect(sqlite_db_path)
        result = await tool.run({"operation": "get_schema"})
        assert result.success is True
        assert isinstance(result.data, DatabaseSchema)
        await tool.disconnect()

    @pytest.mark.asyncio
    async def test_run_disconnect(self, tool, sqlite_db_path):
        """run() dengan operation='disconnect' menutup koneksi."""
        await tool.connect(sqlite_db_path)
        result = await tool.run({"operation": "disconnect"})
        assert result.success is True
        assert tool._connection_type is None

    @pytest.mark.asyncio
    async def test_run_unknown_operation(self, tool):
        """Operasi tidak dikenal → success=False dengan pesan error."""
        result = await tool.run({"operation": "unknown_op"})
        assert result.success is False
        assert result.error is not None
        assert "unknown_op" in result.error

    @pytest.mark.asyncio
    async def test_run_connect_failure_returns_false(self, tool, tmp_path):
        """run() yang gagal connect mengembalikan ToolResult(success=False)."""
        nonexistent = str(tmp_path / "nope.db")
        result = await tool.run({"operation": "connect", "connection_string": nonexistent})
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_sets_tool_name(self, tool, sqlite_db_path):
        """ToolResult.tool_name harus berisi nama tool."""
        result = await tool.run({"operation": "connect", "connection_string": sqlite_db_path})
        assert result.tool_name == "database"
        await tool.disconnect()


# ---------------------------------------------------------------------------
# Tests: ToolInterface compliance
# ---------------------------------------------------------------------------


class TestToolInterfaceCompliance:
    def test_has_required_attributes(self, tool):
        """DatabaseTool memenuhi semua field ToolInterface."""
        assert isinstance(tool.name, str)
        assert isinstance(tool.description, str)
        assert isinstance(tool.input_schema, dict)
        assert isinstance(tool.output_schema, dict)
        assert callable(tool.run)

    def test_name_is_database(self, tool):
        assert tool.name == "database"

    def test_max_select_rows_constant(self):
        assert MAX_SELECT_ROWS == 1000
