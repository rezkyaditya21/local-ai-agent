"""
agent/core/exceptions.py

Semua kelas exception kustom untuk Local AI Agent.
Setiap exception memiliki kode error (E001–E020), nama, dan pesan deskriptif
yang menyertakan entitas yang terlibat (path, URL, query, nama model, dsb.).

Untuk menghindari konflik dengan built-in Python (FileNotFoundError, PermissionError, dsb.),
semua kelas diberi awalan "Agent".
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Base Exception
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Kelas dasar untuk semua exception kustom Agent.

    Attributes:
        error_code: Kode error internal (contoh: "E001").
        description: Deskripsi singkat kelas error.
        message: Pesan detail termasuk entitas yang terlibat.
    """

    error_code: str = "E000"
    description: str = "Terjadi kesalahan pada Agent"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.description}: {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(error_code={self.error_code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# E001 – FileSystem
# ---------------------------------------------------------------------------

class AgentFileNotFoundError(AgentError):
    """E001 – Path file/direktori tidak ditemukan.

    Args:
        path: Path yang tidak ditemukan.
    """

    error_code = "E001"
    description = "Path file/direktori tidak ditemukan"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path tidak ditemukan: '{path}'")


# ---------------------------------------------------------------------------
# E002 – FileSystem / Shell
# ---------------------------------------------------------------------------

class AgentPermissionDeniedError(AgentError):
    """E002 – Izin akses file/shell ditolak OS.

    Args:
        path: Path atau perintah yang aksesnya ditolak.
    """

    error_code = "E002"
    description = "Izin akses ditolak"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Izin akses ditolak untuk: '{path}'")


# ---------------------------------------------------------------------------
# E003 – FileSystem
# ---------------------------------------------------------------------------

class AgentFileSizeExceededError(AgentError):
    """E003 – Ukuran file melampaui batas maksimum.

    Args:
        path: Path file yang terlalu besar.
        actual_bytes: Ukuran aktual file (bytes).
        limit_bytes: Batas ukuran yang diizinkan (bytes).
    """

    error_code = "E003"
    description = "Ukuran file melampaui batas maksimum"

    def __init__(self, path: str, actual_bytes: int, limit_bytes: int) -> None:
        self.path = path
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        actual_mb = actual_bytes / (1024 * 1024)
        limit_mb = limit_bytes / (1024 * 1024)
        super().__init__(
            f"File '{path}' berukuran {actual_mb:.1f} MB melebihi batas {limit_mb:.1f} MB"
        )


# ---------------------------------------------------------------------------
# E004 – FileSystem
# ---------------------------------------------------------------------------

class AgentPathConflictError(AgentError):
    """E004 – Path tujuan operasi move/rename sudah ada.

    Args:
        src: Path sumber.
        dst: Path tujuan yang sudah ada.
    """

    error_code = "E004"
    description = "Path tujuan operasi move/rename sudah ada"

    def __init__(self, src: str, dst: str) -> None:
        self.src = src
        self.dst = dst
        super().__init__(
            f"Tidak dapat memindahkan '{src}' ke '{dst}': path tujuan sudah ada"
        )


# ---------------------------------------------------------------------------
# E005 – Shell
# ---------------------------------------------------------------------------

class AgentShellTimeoutError(AgentError):
    """E005 – Perintah shell melampaui batas waktu.

    Args:
        command: Perintah shell yang dijalankan.
        timeout_seconds: Batas waktu dalam detik.
    """

    error_code = "E005"
    description = "Perintah shell melampaui batas waktu"

    def __init__(self, command: str, timeout_seconds: int) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Perintah '{command}' melebihi batas waktu {timeout_seconds} detik dan dihentikan paksa"
        )


# ---------------------------------------------------------------------------
# E006 – Shell (internal safeguard)
# ---------------------------------------------------------------------------

class AgentDestructiveCommandError(AgentError):
    """E006 – Perintah destruktif dieksekusi tanpa konfirmasi (internal safeguard).

    Seharusnya tidak pernah terjadi dalam alur normal karena ConfirmationGate
    selalu dipanggil terlebih dahulu. Digunakan sebagai lapisan perlindungan terakhir.

    Args:
        command: Perintah destruktif yang terdeteksi.
    """

    error_code = "E006"
    description = "Perintah destruktif tanpa konfirmasi terdeteksi"

    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(
            f"Perintah destruktif '{command}' tidak dapat dieksekusi tanpa konfirmasi eksplisit"
        )


# ---------------------------------------------------------------------------
# E007 – Browser
# ---------------------------------------------------------------------------

class AgentBrowserFetchError(AgentError):
    """E007 – Gagal mengambil URL (HTTP error / timeout / koneksi).

    Args:
        url: URL yang gagal diambil.
        reason: Alasan kegagalan (contoh: "HTTP 404", "timeout", "connection refused").
    """

    error_code = "E007"
    description = "Gagal mengambil URL dari browser"

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Gagal mengambil '{url}': {reason}")


# ---------------------------------------------------------------------------
# E008 – Database
# ---------------------------------------------------------------------------

class AgentDatabaseConnectionError(AgentError):
    """E008 – Path SQLite tidak valid atau connection string tidak dapat dijangkau.

    Args:
        connection_string: Connection string atau path SQLite yang gagal.
        reason: Alasan kegagalan (contoh: "file tidak ada", "bukan file SQLite valid",
                "invalid_sqlite_file").
    """

    error_code = "E008"
    description = "Koneksi database gagal"

    def __init__(self, connection_string: str, reason: str) -> None:
        self.connection_string = connection_string
        self.reason = reason
        super().__init__(
            f"Gagal terhubung ke database '{connection_string}': {reason}"
        )


# ---------------------------------------------------------------------------
# E009 – Database
# ---------------------------------------------------------------------------

class AgentQueryExecutionError(AgentError):
    """E009 – Query SQL gagal dieksekusi oleh database engine.

    State database tidak berubah saat error ini terjadi.

    Args:
        query: Query SQL yang gagal dieksekusi.
        reason: Pesan error dari database engine.
    """

    error_code = "E009"
    description = "Eksekusi query SQL gagal"

    def __init__(self, query: str, reason: str) -> None:
        self.query = query
        self.reason = reason
        # Potong query panjang agar pesan tidak terlalu verbose
        short_query = query if len(query) <= 200 else query[:200] + "..."
        super().__init__(f"Query gagal dieksekusi — '{short_query}': {reason}")


# ---------------------------------------------------------------------------
# E010 – HTTP API
# ---------------------------------------------------------------------------

class AgentHTTPRequestError(AgentError):
    """E010 – HTTP request timeout atau network error.

    Args:
        url: URL yang dituju.
        timeout_seconds: Batas waktu dalam detik (jika relevan).
        reason: Alasan kegagalan jaringan.
    """

    error_code = "E010"
    description = "HTTP request gagal (timeout atau network error)"

    def __init__(self, url: str, timeout_seconds: int | None = None, reason: str = "") -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.reason = reason
        if timeout_seconds is not None:
            msg = f"Request ke '{url}' melebihi batas waktu {timeout_seconds} detik"
        else:
            msg = f"Request ke '{url}' gagal: {reason}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# E011 – HTTP API
# ---------------------------------------------------------------------------

class AgentRedirectLimitExceededError(AgentError):
    """E011 – Jumlah redirect melebihi batas maksimum (10).

    Args:
        url: URL awal yang diminta.
        redirect_count: Jumlah redirect yang terjadi sebelum berhenti.
        last_url: URL terakhir yang dikunjungi sebelum berhenti.
    """

    error_code = "E011"
    description = "Jumlah redirect melebihi batas maksimum"

    def __init__(self, url: str, redirect_count: int, last_url: str) -> None:
        self.url = url
        self.redirect_count = redirect_count
        self.last_url = last_url
        super().__init__(
            f"Request ke '{url}' menghasilkan {redirect_count} redirect (melebihi batas 10); "
            f"URL terakhir: '{last_url}'"
        )


# ---------------------------------------------------------------------------
# E012 – Model Manager
# ---------------------------------------------------------------------------

class AgentModelNotFoundError(AgentError):
    """E012 – Nama model tidak ada dalam registry.

    Model aktif sebelumnya tetap dipertahankan.

    Args:
        model_name: Nama model yang tidak ditemukan.
    """

    error_code = "E012"
    description = "Model tidak ditemukan dalam registry"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(
            f"Model '{model_name}' tidak ditemukan dalam registry; model aktif dipertahankan"
        )


# ---------------------------------------------------------------------------
# E013 – Model Manager
# ---------------------------------------------------------------------------

class AgentModelLoadTimeoutError(AgentError):
    """E013 – Model gagal dimuat dalam batas waktu yang ditentukan.

    Model aktif sebelumnya tetap dipertahankan.

    Args:
        model_name: Nama model yang gagal dimuat.
        timeout_seconds: Batas waktu pemuatan dalam detik.
    """

    error_code = "E013"
    description = "Pemuatan model melampaui batas waktu"

    def __init__(self, model_name: str, timeout_seconds: int) -> None:
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Model '{model_name}' gagal dimuat dalam {timeout_seconds} detik; "
            f"model sebelumnya tetap aktif"
        )


# ---------------------------------------------------------------------------
# E014 – Plugin / Self-Improvement
# ---------------------------------------------------------------------------

class AgentPluginSchemaError(AgentError):
    """E014 – Plugin tidak memenuhi skema ToolInterface.

    Args:
        plugin_name: Nama plugin (atau path file plugin).
        missing_fields: Daftar field/method yang tidak ada atau tidak sesuai.
    """

    error_code = "E014"
    description = "Plugin tidak memenuhi skema ToolInterface"

    def __init__(self, plugin_name: str, missing_fields: list[str]) -> None:
        self.plugin_name = plugin_name
        self.missing_fields = missing_fields
        fields_str = ", ".join(f"'{f}'" for f in missing_fields)
        super().__init__(
            f"Plugin '{plugin_name}' tidak memenuhi ToolInterface; field yang kurang: {fields_str}"
        )


# ---------------------------------------------------------------------------
# E015 – Plugin / Self-Improvement
# ---------------------------------------------------------------------------

class AgentPluginSizeExceededError(AgentError):
    """E015 – File plugin melampaui batas ukuran yang diizinkan.

    Args:
        plugin_name: Nama atau URL plugin.
        actual_bytes: Ukuran aktual file plugin (bytes).
        limit_bytes: Batas ukuran yang diizinkan (bytes).
    """

    error_code = "E015"
    description = "File plugin melampaui batas ukuran"

    def __init__(self, plugin_name: str, actual_bytes: int, limit_bytes: int) -> None:
        self.plugin_name = plugin_name
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        actual_mb = actual_bytes / (1024 * 1024)
        limit_mb = limit_bytes / (1024 * 1024)
        super().__init__(
            f"Plugin '{plugin_name}' berukuran {actual_mb:.1f} MB melebihi batas {limit_mb:.1f} MB"
        )


# ---------------------------------------------------------------------------
# E016 – Model Manager
# ---------------------------------------------------------------------------

class AgentModelParameterRangeError(AgentError):
    """E016 – Nilai parameter model di luar rentang yang valid.

    Args:
        parameter_name: Nama parameter yang tidak valid (contoh: "temperature").
        value: Nilai yang diberikan.
        min_value: Nilai minimum yang diizinkan.
        max_value: Nilai maksimum yang diizinkan.
    """

    error_code = "E016"
    description = "Nilai parameter model di luar rentang valid"

    def __init__(
        self,
        parameter_name: str,
        value: float | int,
        min_value: float | int,
        max_value: float | int,
    ) -> None:
        self.parameter_name = parameter_name
        self.value = value
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(
            f"Parameter '{parameter_name}' bernilai {value} di luar rentang valid "
            f"[{min_value}, {max_value}]"
        )


# ---------------------------------------------------------------------------
# E017 – Tool Registry
# ---------------------------------------------------------------------------

class AgentCapacityExceededError(AgentError):
    """E017 – ToolRegistry sudah penuh (maksimum 200 tools).

    Args:
        current_count: Jumlah tool yang sudah terdaftar saat ini.
        max_capacity: Kapasitas maksimum registry.
        tool_name: Nama tool yang gagal didaftarkan.
    """

    error_code = "E017"
    description = "ToolRegistry sudah penuh"

    def __init__(self, current_count: int, max_capacity: int, tool_name: str) -> None:
        self.current_count = current_count
        self.max_capacity = max_capacity
        self.tool_name = tool_name
        super().__init__(
            f"Tidak dapat mendaftarkan tool '{tool_name}': registry sudah penuh "
            f"({current_count}/{max_capacity} tools)"
        )


# ---------------------------------------------------------------------------
# E018 – Blocklist
# ---------------------------------------------------------------------------

class AgentBlocklistViolationError(AgentError):
    """E018 – Operasi ditolak karena entri dalam blocklist.

    Args:
        entry_type: Tipe entri blocklist (contoh: "file_path", "command", "domain").
        value: Nilai yang cocok dengan entri blocklist.
        matched_pattern: Pola blocklist yang cocok dengan nilai.
    """

    error_code = "E018"
    description = "Operasi ditolak karena masuk dalam blocklist"

    def __init__(self, entry_type: str, value: str, matched_pattern: str) -> None:
        self.entry_type = entry_type
        self.value = value
        self.matched_pattern = matched_pattern
        super().__init__(
            f"Operasi ditolak: {entry_type} '{value}' cocok dengan pola blocklist '{matched_pattern}'"
        )


# ---------------------------------------------------------------------------
# E019 – Confirmation Gate
# ---------------------------------------------------------------------------

class AgentConfirmationTimeoutError(AgentError):
    """E019 – Pengguna tidak merespons konfirmasi dalam batas waktu yang ditentukan.

    Operasi dibatalkan secara otomatis.

    Args:
        operation_type: Tipe operasi yang memerlukan konfirmasi (contoh: "delete", "dml").
        timeout_seconds: Batas waktu menunggu respons pengguna.
    """

    error_code = "E019"
    description = "Konfirmasi pengguna melebihi batas waktu, operasi dibatalkan"

    def __init__(self, operation_type: str, timeout_seconds: int) -> None:
        self.operation_type = operation_type
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Operasi '{operation_type}' dibatalkan: pengguna tidak merespons dalam "
            f"{timeout_seconds} detik"
        )


# ---------------------------------------------------------------------------
# E020 – Self-Improvement
# ---------------------------------------------------------------------------

class AgentSelfImprovementApplyError(AgentError):
    """E020 – Gagal menerapkan perubahan konfigurasi; rollback otomatis dipicu.

    Args:
        description: Deskripsi perubahan yang gagal diterapkan.
        reason: Alasan kegagalan.
        rollback_triggered: True jika rollback otomatis berhasil dipicu.
    """

    error_code = "E020"
    description = "Gagal menerapkan perubahan konfigurasi Agent, rollback otomatis dipicu"

    def __init__(
        self,
        description: str,
        reason: str,
        rollback_triggered: bool = True,
    ) -> None:
        self.change_description = description
        self.reason = reason
        self.rollback_triggered = rollback_triggered
        rollback_status = "rollback berhasil dipicu" if rollback_triggered else "rollback GAGAL"
        super().__init__(
            f"Gagal menerapkan perubahan '{description}': {reason}; {rollback_status}"
        )


# ---------------------------------------------------------------------------
# E021 – Tool Registry
# ---------------------------------------------------------------------------

class AgentToolNotFoundError(AgentError):
    """E021 – Tool dengan nama yang diberikan tidak ditemukan dalam registry.

    Dipicu oleh `enable()` dan `disable()` pada `ToolRegistry` ketika nama
    tool tidak terdaftar.

    Args:
        tool_name: Nama tool yang tidak ditemukan.
    """

    error_code = "E021"
    description = "Tool tidak ditemukan dalam registry"

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"Tool '{tool_name}' tidak ditemukan dalam registry; "
            f"status tool lainnya tidak berubah"
        )


# ---------------------------------------------------------------------------
# Convenience mapping: error_code → exception class
# ---------------------------------------------------------------------------

ERROR_CODE_MAP: dict[str, type[AgentError]] = {
    "E001": AgentFileNotFoundError,
    "E002": AgentPermissionDeniedError,
    "E003": AgentFileSizeExceededError,
    "E004": AgentPathConflictError,
    "E005": AgentShellTimeoutError,
    "E006": AgentDestructiveCommandError,
    "E007": AgentBrowserFetchError,
    "E008": AgentDatabaseConnectionError,
    "E009": AgentQueryExecutionError,
    "E010": AgentHTTPRequestError,
    "E011": AgentRedirectLimitExceededError,
    "E012": AgentModelNotFoundError,
    "E013": AgentModelLoadTimeoutError,
    "E014": AgentPluginSchemaError,
    "E015": AgentPluginSizeExceededError,
    "E016": AgentModelParameterRangeError,
    "E017": AgentCapacityExceededError,
    "E018": AgentBlocklistViolationError,
    "E019": AgentConfirmationTimeoutError,
    "E020": AgentSelfImprovementApplyError,
    "E021": AgentToolNotFoundError,
}

__all__ = [
    "AgentError",
    # FileSystem
    "AgentFileNotFoundError",
    "AgentPermissionDeniedError",
    "AgentFileSizeExceededError",
    "AgentPathConflictError",
    # Shell
    "AgentShellTimeoutError",
    "AgentDestructiveCommandError",
    # Browser
    "AgentBrowserFetchError",
    # Database
    "AgentDatabaseConnectionError",
    "AgentQueryExecutionError",
    # HTTP API
    "AgentHTTPRequestError",
    "AgentRedirectLimitExceededError",
    # Model Manager
    "AgentModelNotFoundError",
    "AgentModelLoadTimeoutError",
    "AgentModelParameterRangeError",
    # Plugin / Self-Improvement
    "AgentPluginSchemaError",
    "AgentPluginSizeExceededError",
    "AgentSelfImprovementApplyError",
    # Tool Registry
    "AgentCapacityExceededError",
    # Blocklist
    "AgentBlocklistViolationError",
    # Confirmation Gate
    "AgentConfirmationTimeoutError",
    # Tool Registry
    "AgentToolNotFoundError",
    # Mapping
    "ERROR_CODE_MAP",
]
