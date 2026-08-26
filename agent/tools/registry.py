"""
agent/tools/registry.py

Tool Registry — menyimpan daftar semua Tool dan Plugin yang tersedia bagi Agent.

Komponen utama:
- `ToolInterface`: Protocol yang harus dipenuhi setiap tool/plugin.
- `ToolEntry`: Pembungkus tool beserta metadata (status aktif, sumber).
- `ToolRegistry`: Registry sentral dengan kapasitas maksimum 200 tool.

Requirements yang diimplementasikan: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent.core.exceptions import (
    AgentCapacityExceededError,
    AgentPluginSchemaError,
    AgentToolNotFoundError,
)
from agent.models.schemas import ToolResult

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_TOOLS = 200
MAX_PLUGIN_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

# Field dan method yang wajib ada pada setiap tool (sesuai ToolInterface)
_REQUIRED_ATTRIBUTES: tuple[str, ...] = (
    "name",
    "description",
    "input_schema",
    "output_schema",
    "run",
)


# ---------------------------------------------------------------------------
# ToolInterface Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolInterface(Protocol):
    """Protocol yang harus dipenuhi oleh setiap Tool atau Plugin.

    Semua tool — baik built-in maupun plugin eksternal — wajib memiliki
    empat atribut deskriptif dan satu coroutine `run()`.

    Attributes:
        name: Identifier unik tool (snake_case direkomendasikan).
        description: Deskripsi singkat fungsi tool; digunakan oleh
            `ToolRegistry.select_best()` untuk pemilihan otomatis.
        input_schema: Skema parameter masukan (format dict, idealnya
            kompatibel dengan JSON Schema).
        output_schema: Skema nilai kembalian (format dict, idealnya
            kompatibel dengan JSON Schema).
    """

    name: str
    description: str
    input_schema: dict
    output_schema: dict

    async def run(self, params: dict) -> ToolResult:
        """Eksekusi tool dengan parameter yang diberikan.

        Args:
            params: Parameter masukan sesuai `input_schema`.

        Returns:
            `ToolResult` dengan `success=True` jika berhasil, atau
            `ToolResult(success=False, error=...)` jika gagal.
        """
        ...


# ---------------------------------------------------------------------------
# ToolEntry dataclass
# ---------------------------------------------------------------------------


@dataclass
class ToolEntry:
    """Pembungkus tool di dalam registry beserta metadata.

    Attributes:
        tool: Instansi tool yang memenuhi `ToolInterface`.
        enabled: Status aktif/nonaktif tool. Hanya tool yang `enabled=True`
            yang dapat diambil via `ToolRegistry.get()`.
        source: Asal tool; salah satu dari ``"builtin"`` atau ``"plugin"``.
    """

    tool: ToolInterface
    enabled: bool = True
    source: str = "builtin"  # "builtin" | "plugin"


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry sentral yang menyimpan semua Tool dan Plugin Agent.

    Kapasitas maksimum adalah 200 tool (Requirement 9.1). Setiap pendaftaran
    melalui `register()` divalidasi terlebih dahulu terhadap `ToolInterface`
    untuk memastikan skema plugin sesuai (Requirement 9.7).

    Attributes:
        _tools: Mapping dari `name` tool ke `ToolEntry`.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, tool: ToolInterface, source: str = "builtin") -> None:
        """Daftarkan tool ke registry.

        Validasi dilakukan sebelum pendaftaran:
        1. Kapasitas registry tidak boleh melebihi `MAX_TOOLS` (E017).
        2. Tool harus memenuhi semua field `ToolInterface` (E014).

        Pendaftaran ulang tool dengan nama yang sama akan menimpa entri lama
        (perilaku update/upgrade plugin yang sah).

        Args:
            tool: Instansi tool yang akan didaftarkan.
            source: Asal tool; ``"builtin"`` atau ``"plugin"``.

        Raises:
            AgentCapacityExceededError: Jika registry sudah penuh (200 tool)
                dan tool dengan nama tersebut belum terdaftar sebelumnya.
            AgentPluginSchemaError: Jika tool tidak memenuhi `ToolInterface`.
        """
        # Validasi skema terlebih dahulu agar pesan error lebih informatif
        missing = self.validate_plugin_schema(tool)
        if missing:
            plugin_name = getattr(tool, "name", repr(tool))
            raise AgentPluginSchemaError(
                plugin_name=str(plugin_name),
                missing_fields=missing,
            )

        # Kapasitas hanya diperiksa untuk tool baru (bukan update)
        if tool.name not in self._tools and len(self._tools) >= MAX_TOOLS:
            raise AgentCapacityExceededError(
                current_count=len(self._tools),
                max_capacity=MAX_TOOLS,
                tool_name=tool.name,
            )

        self._tools[tool.name] = ToolEntry(tool=tool, enabled=True, source=source)

    def get(self, name: str) -> ToolInterface | None:
        """Kembalikan tool aktif berdasarkan nama.

        Args:
            name: Nama tool yang dicari.

        Returns:
            Instansi `ToolInterface` jika tool ditemukan dan aktif,
            atau ``None`` jika tidak ada atau sedang dinonaktifkan.
        """
        entry = self._tools.get(name)
        if entry is None or not entry.enabled:
            return None
        return entry.tool

    def list_all(self) -> list[ToolEntry]:
        """Kembalikan semua tool beserta status aktif/nonaktifnya.

        Returns:
            Daftar `ToolEntry` yang mencakup tool aktif maupun nonaktif,
            diurutkan berdasarkan nama secara alfabetis untuk output yang
            konsisten.
        """
        return sorted(self._tools.values(), key=lambda e: e.tool.name)

    def enable(self, name: str) -> None:
        """Aktifkan tool berdasarkan nama.

        Args:
            name: Nama tool yang akan diaktifkan.

        Raises:
            AgentToolNotFoundError: Jika nama tool tidak ada di registry (E021).
        """
        if name not in self._tools:
            raise AgentToolNotFoundError(tool_name=name)
        self._tools[name].enabled = True

    def disable(self, name: str) -> None:
        """Nonaktifkan tool berdasarkan nama.

        Args:
            name: Nama tool yang akan dinonaktifkan.

        Raises:
            AgentToolNotFoundError: Jika nama tool tidak ada di registry (E021).
        """
        if name not in self._tools:
            raise AgentToolNotFoundError(tool_name=name)
        self._tools[name].enabled = False

    def validate_plugin_schema(self, tool: object) -> list[str]:
        """Validasi bahwa tool memenuhi `ToolInterface`.

        Memeriksa keberadaan semua atribut wajib:
        ``name``, ``description``, ``input_schema``, ``output_schema``, ``run``.

        Args:
            tool: Objek yang akan divalidasi.

        Returns:
            Daftar nama atribut yang kurang atau tidak sesuai.
            Daftar kosong berarti tool lolos validasi.
        """
        missing: list[str] = []
        for attr in _REQUIRED_ATTRIBUTES:
            if not hasattr(tool, attr):
                missing.append(attr)
                continue

            value = getattr(tool, attr)

            # Validasi tipe atribut deskriptif
            if attr == "name" and not isinstance(value, str):
                missing.append(attr)
            elif attr == "description" and not isinstance(value, str):
                missing.append(attr)
            elif attr in ("input_schema", "output_schema") and not isinstance(value, dict):
                missing.append(attr)
            elif attr == "run" and not callable(value):
                missing.append(attr)

        return missing

    def select_best(self, task_description: str) -> ToolInterface | None:
        """Pilih tool paling sesuai untuk deskripsi tugas yang diberikan.

        Algoritma pemilihan menggunakan pencocokan kata kunci sederhana:
        setiap kata dalam `task_description` dicocokkan dengan
        `tool.description` dan `tool.name`. Tool dengan skor kecocokan
        tertinggi dikembalikan. Hanya tool yang aktif (``enabled=True``)
        yang dipertimbangkan.

        Args:
            task_description: Deskripsi tugas yang ingin diselesaikan.

        Returns:
            Tool aktif dengan kecocokan terbaik, atau ``None`` jika tidak ada
            tool aktif yang terdaftar.
        """
        if not task_description or not self._tools:
            return None

        normalized = task_description.lower()
        words = [w for w in normalized.split() if w]

        best_tool: ToolInterface | None = None
        best_score: int = -1

        for entry in self._tools.values():
            if not entry.enabled:
                continue

            tool = entry.tool
            searchable = f"{tool.name} {tool.description}".lower()

            score = sum(1 for word in words if word in searchable)

            if score > best_score:
                best_score = score
                best_tool = tool

        # Kembalikan None jika tidak ada kata yang cocok sama sekali
        # (best_score == 0 tetap valid jika ada tool aktif — fallback ke
        # tool pertama secara alfabetis agar Agent selalu memiliki tool
        # yang dapat dipanggil).
        return best_tool

    # ------------------------------------------------------------------
    # Properties (read-only)
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Jumlah total tool yang terdaftar (aktif maupun nonaktif)."""
        return len(self._tools)

    @property
    def active_count(self) -> int:
        """Jumlah tool yang sedang aktif."""
        return sum(1 for e in self._tools.values() if e.enabled)


__all__ = [
    "MAX_TOOLS",
    "MAX_PLUGIN_FILE_SIZE_BYTES",
    "ToolInterface",
    "ToolEntry",
    "ToolRegistry",
]
