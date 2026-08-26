"""
agent/tools/filesystem.py

FileSystem Tool — menyediakan operasi baca/tulis/buat/hapus/pindah/daftar/cari
untuk file dan direktori di filesystem lokal.

Mengimplementasikan `ToolInterface` sehingga dapat didaftarkan ke `ToolRegistry`
dan dipanggil oleh `Executor`.

Requirements yang diimplementasikan: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.core.exceptions import (
    AgentFileNotFoundError,
    AgentFileSizeExceededError,
    AgentPathConflictError,
    AgentPermissionDeniedError,
)
from agent.models.schemas import FileEntry, ToolResult

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_READ_BYTES = 500 * 1024 * 1024  # 500 MB


# ---------------------------------------------------------------------------
# FileSystemTool
# ---------------------------------------------------------------------------


class FileSystemTool:
    """Tool built-in untuk operasi filesystem lokal.

    Mengimplementasikan `ToolInterface` dan mendukung operasi:
    - Membaca / menulis file (teks dan biner)
    - Membuat file atau direktori
    - Menghapus path (konfirmasi ditangani oleh Executor/ConfirmationGate)
    - Memindahkan / mengganti nama file atau direktori
    - Membuat daftar isi direktori beserta metadata
    - Mencari file berdasarkan pola glob

    Attributes:
        name: Identifier tool; digunakan oleh ToolRegistry.
        description: Deskripsi singkat untuk pemilihan otomatis tool.
        input_schema: Skema parameter masukan (JSON Schema sederhana).
        output_schema: Skema nilai kembalian.
        MAX_READ_BYTES: Batas ukuran file yang dapat dibaca (500 MB).
    """

    name: str = "filesystem"
    description: str = (
        "Read, write, create, delete, move, list, and glob-search "
        "files and directories on the local filesystem."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "read_file",
                    "write_file",
                    "create",
                    "delete",
                    "move",
                    "list_dir",
                    "glob_search",
                ],
                "description": "Operasi filesystem yang akan dieksekusi.",
            },
            "path": {
                "type": "string",
                "description": "Path target untuk operasi.",
            },
            "content": {
                "type": ["string", "null"],
                "description": "Konten yang akan ditulis (untuk write_file). "
                               "Dapat berupa string atau bytes dalam bentuk string base64.",
            },
            "is_dir": {
                "type": "boolean",
                "description": "True untuk membuat direktori (untuk operasi create).",
                "default": False,
            },
            "src": {
                "type": "string",
                "description": "Path sumber (untuk operasi move).",
            },
            "dst": {
                "type": "string",
                "description": "Path tujuan (untuk operasi move).",
            },
            "directory": {
                "type": "string",
                "description": "Direktori dasar (untuk operasi glob_search).",
            },
            "pattern": {
                "type": "string",
                "description": "Pola glob (untuk operasi glob_search).",
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "data": {
                "description": "Hasil operasi: bytes (read), None (write/create/delete/move), "
                               "list[FileEntry] (list_dir), list[str] (glob_search)."
            },
            "error": {"type": ["string", "null"]},
            "tool_name": {"type": "string"},
        },
        "required": ["success"],
    }
    MAX_READ_BYTES: int = MAX_READ_BYTES

    # ------------------------------------------------------------------
    # ToolInterface: method run() sebagai dispatcher
    # ------------------------------------------------------------------

    async def run(self, params: dict) -> ToolResult:
        """Dispatch ke method yang sesuai berdasarkan ``params["operation"]``.

        Args:
            params: Parameter operasi. Wajib menyertakan ``"operation"``.

        Returns:
            ``ToolResult(success=True, data=...)`` jika berhasil, atau
            ``ToolResult(success=False, error=...)`` jika gagal.
        """
        operation = params.get("operation")

        try:
            if operation == "read_file":
                path = _require(params, "path")
                data = await self.read_file(path)
                return ToolResult(success=True, data=data, tool_name=self.name)

            elif operation == "write_file":
                path = _require(params, "path")
                content = params.get("content", b"")
                # Terima bytes langsung maupun string (UTF-8)
                if isinstance(content, str):
                    content = content.encode("utf-8")
                await self.write_file(path, content)
                return ToolResult(success=True, data=None, tool_name=self.name)

            elif operation == "create":
                path = _require(params, "path")
                is_dir: bool = bool(params.get("is_dir", False))
                await self.create(path, is_dir=is_dir)
                return ToolResult(success=True, data=None, tool_name=self.name)

            elif operation == "delete":
                path = _require(params, "path")
                await self.delete(path)
                return ToolResult(success=True, data=None, tool_name=self.name)

            elif operation == "move":
                src = _require(params, "src")
                dst = _require(params, "dst")
                await self.move(src, dst)
                return ToolResult(success=True, data=None, tool_name=self.name)

            elif operation == "list_dir":
                path = _require(params, "path")
                entries = await self.list_dir(path)
                return ToolResult(success=True, data=entries, tool_name=self.name)

            elif operation == "glob_search":
                directory = _require(params, "directory")
                pattern = _require(params, "pattern")
                results = await self.glob_search(directory, pattern)
                return ToolResult(success=True, data=results, tool_name=self.name)

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Operasi tidak dikenal: '{operation}'. "
                          f"Operasi yang valid: read_file, write_file, create, delete, "
                          f"move, list_dir, glob_search.",
                    tool_name=self.name,
                )

        except (
            AgentFileNotFoundError,
            AgentPermissionDeniedError,
            AgentFileSizeExceededError,
            AgentPathConflictError,
        ) as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except (ValueError, KeyError) as exc:
            return ToolResult(
                success=False,
                data=None,
                error=f"Parameter tidak lengkap atau tidak valid: {exc}",
                tool_name=self.name,
            )

    # ------------------------------------------------------------------
    # Operasi Filesystem
    # ------------------------------------------------------------------

    async def read_file(self, path: str) -> bytes:
        """Baca seluruh konten file secara asinkron.

        Args:
            path: Path file yang akan dibaca.

        Returns:
            Konten file sebagai ``bytes``.

        Raises:
            AgentFileNotFoundError: Jika file tidak ditemukan (E001).
            AgentPermissionDeniedError: Jika izin akses ditolak (E002).
            AgentFileSizeExceededError: Jika ukuran file melebihi 500 MB (E003).
        """
        p = Path(path)

        # Periksa keberadaan file
        if not p.exists():
            raise AgentFileNotFoundError(path)

        # Periksa izin baca
        if not os.access(p, os.R_OK):
            raise AgentPermissionDeniedError(path)

        # Periksa ukuran sebelum membaca
        size = p.stat().st_size
        if size > MAX_READ_BYTES:
            raise AgentFileSizeExceededError(
                path=path,
                actual_bytes=size,
                limit_bytes=MAX_READ_BYTES,
            )

        # Jalankan I/O blocking di thread pool agar tidak memblokir event loop
        return await asyncio.get_event_loop().run_in_executor(
            None, p.read_bytes
        )

    async def write_file(self, path: str, content: bytes) -> None:
        """Tulis atau timpa konten file.

        Direktori induk dibuat secara otomatis jika belum ada.

        Args:
            path: Path file tujuan.
            content: Konten yang akan ditulis (bytes).

        Raises:
            AgentPermissionDeniedError: Jika izin tulis ditolak (E002).
        """
        p = Path(path)

        # Buat direktori induk jika belum ada
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise AgentPermissionDeniedError(str(p.parent))

        # Tulis konten
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, p.write_bytes, content
            )
        except PermissionError:
            raise AgentPermissionDeniedError(path)

    async def create(self, path: str, is_dir: bool = False) -> None:
        """Buat file baru atau direktori baru.

        Untuk file: membuat file kosong (seperti ``touch``).
        Untuk direktori: membuat direktori beserta parent-nya jika perlu.

        Args:
            path: Path yang akan dibuat.
            is_dir: Jika ``True``, buat direktori; jika ``False``, buat file.

        Raises:
            AgentPermissionDeniedError: Jika izin pembuatan ditolak (E002).
        """
        p = Path(path)

        try:
            if is_dir:
                p.mkdir(parents=True, exist_ok=True)
            else:
                # Pastikan direktori induk ada
                p.parent.mkdir(parents=True, exist_ok=True)
                # Buat file kosong tanpa menimpa file yang sudah ada
                p.touch(exist_ok=True)
        except PermissionError:
            raise AgentPermissionDeniedError(path)

    async def delete(self, path: str) -> None:
        """Hapus file atau direktori.

        Catatan: Konfirmasi pengguna **tidak** ditangani di sini.
        Konfirmasi adalah tanggung jawab ``Executor`` via ``ConfirmationGate``.
        Method ini hanya menjalankan penghapusan setelah dikonfirmasi.

        Args:
            path: Path yang akan dihapus.

        Raises:
            AgentFileNotFoundError: Jika path tidak ditemukan (E001).
            AgentPermissionDeniedError: Jika izin penghapusan ditolak (E002).
        """
        p = Path(path)

        if not p.exists():
            raise AgentFileNotFoundError(path)

        try:
            if p.is_dir():
                await asyncio.get_event_loop().run_in_executor(
                    None, shutil.rmtree, str(p)
                )
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None, p.unlink
                )
        except PermissionError:
            raise AgentPermissionDeniedError(path)

    async def move(self, src: str, dst: str) -> None:
        """Pindahkan atau ganti nama file / direktori.

        Jika ``dst`` sudah ada, operasi **dibatalkan** tanpa mengubah file
        apapun (Requirement 2.6).

        Args:
            src: Path sumber.
            dst: Path tujuan.

        Raises:
            AgentFileNotFoundError: Jika ``src`` tidak ditemukan (E001).
            AgentPathConflictError: Jika ``dst`` sudah ada (E004).
            AgentPermissionDeniedError: Jika izin akses ditolak (E002).
        """
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.exists():
            raise AgentFileNotFoundError(src)

        if dst_path.exists():
            raise AgentPathConflictError(src=src, dst=dst)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, shutil.move, str(src_path), str(dst_path)
            )
        except PermissionError:
            raise AgentPermissionDeniedError(src)

    async def list_dir(self, path: str) -> list[FileEntry]:
        """Baca daftar isi direktori beserta metadata.

        Args:
            path: Path direktori yang akan dibaca.

        Returns:
            Daftar ``FileEntry`` diurutkan berdasarkan nama secara alfabetis.
            Setiap entri menyertakan:
            - ``path``: path absolut entri
            - ``name``: nama entri
            - ``size_bytes``: ukuran dalam byte (0 untuk direktori)
            - ``modified_at``: tanggal modifikasi dalam format ISO 8601 UTC
            - ``entry_type``: ``"file"`` atau ``"directory"``

        Raises:
            AgentFileNotFoundError: Jika direktori tidak ditemukan (E001).
            AgentPermissionDeniedError: Jika izin baca ditolak (E002).
        """
        p = Path(path)

        if not p.exists():
            raise AgentFileNotFoundError(path)

        if not os.access(p, os.R_OK):
            raise AgentPermissionDeniedError(path)

        def _list() -> list[FileEntry]:
            entries: list[FileEntry] = []
            for item in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                try:
                    stat = item.stat()
                    modified_dt = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    )
                    entries.append(
                        FileEntry(
                            path=str(item.resolve()),
                            name=item.name,
                            size_bytes=stat.st_size if item.is_file() else 0,
                            modified_at=modified_dt.isoformat(),
                            entry_type="directory" if item.is_dir() else "file",
                        )
                    )
                except (OSError, PermissionError):
                    # Lewati entri yang tidak dapat diakses
                    continue
            return entries

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _list)
        except PermissionError:
            raise AgentPermissionDeniedError(path)

    async def glob_search(self, directory: str, pattern: str) -> list[str]:
        """Cari file berdasarkan pola glob di dalam direktori yang ditentukan.

        Pencarian bersifat rekursif (menggunakan ``**`` secara implisit jika
        pola tidak mengandung path separator). Jika pola mengandung ``**``,
        pencarian rekursif menggunakan ``Path.rglob``; jika tidak, menggunakan
        ``Path.glob`` pada direktori yang diberikan.

        Args:
            directory: Direktori dasar pencarian.
            pattern: Pola glob (contoh: ``"*.py"``, ``"**/*.json"``).

        Returns:
            Daftar path (string) yang cocok, diurutkan secara alfabetis.
            Jika tidak ada hasil, kembalikan daftar kosong.

        Raises:
            AgentFileNotFoundError: Jika ``directory`` tidak ditemukan (E001).
            AgentPermissionDeniedError: Jika izin baca ditolak (E002).

        Note:
            Sesuai Requirement 2.8, jika daftar kosong dikembalikan, pemanggil
            bertanggung jawab menginformasikan pengguna bahwa tidak ada hasil.
            ``ToolResult.data`` akan berupa daftar kosong ``[]``.
        """
        d = Path(directory)

        if not d.exists():
            raise AgentFileNotFoundError(directory)

        if not os.access(d, os.R_OK):
            raise AgentPermissionDeniedError(directory)

        def _search() -> list[str]:
            # Gunakan rglob jika pola mengandung "**", glob biasa jika tidak
            if "**" in pattern:
                matched = d.rglob(pattern.replace("**/", ""))
            else:
                matched = d.glob(pattern)

            results = sorted(
                str(p.resolve()) for p in matched if p.is_file()
            )
            return results

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _search)
        except PermissionError:
            raise AgentPermissionDeniedError(directory)


# ---------------------------------------------------------------------------
# Helper internal
# ---------------------------------------------------------------------------


def _require(params: dict[str, Any], key: str) -> Any:
    """Ambil nilai dari dict params; raise ValueError jika key tidak ada."""
    if key not in params or params[key] is None:
        raise ValueError(f"Parameter wajib '{key}' tidak ditemukan")
    return params[key]


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "MAX_READ_BYTES",
    "FileSystemTool",
]
