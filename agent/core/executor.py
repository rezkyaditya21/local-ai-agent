"""
agent/core/executor.py

Executor — lapisan tengah yang menjembatani Agent Orchestrator dengan Tool Layer.

Alur eksekusi untuk setiap ToolCall:
  1. Periksa blocklist (jika dikonfigurasi) → tolak jika diblokir (E018).
  2. Ambil tool dari ToolRegistry → tolak jika tool tidak ditemukan atau nonaktif.
  3. Periksa apakah operasi bersifat destruktif via `is_destructive()`.
  4. Jika destruktif, minta konfirmasi via `ConfirmationGate.request()`.
  5. Jalankan `tool.run(params)` — tangkap SEMUA exception agar sesi tidak berhenti.
  6. Catat tindakan (berhasil maupun gagal) ke `AuditLogger` (jika dikonfigurasi).
  7. Kembalikan `ToolResult`.

Requirements yang diimplementasikan: 3.4, 9.8, 10.1, 10.6
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent.core.confirmation_gate import ConfirmationGate, ConfirmationRequest
from agent.core.exceptions import AgentBlocklistViolationError
from agent.models.schemas import ToolCall, ToolResult
from agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from agent.core.audit_logger import AuditLogger
    from agent.core.blocklist import Blocklist, BlocklistEntryType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

# Operasi filesystem yang selalu dianggap destruktif dan memerlukan konfirmasi
_DESTRUCTIVE_FS_OPERATIONS: frozenset[str] = frozenset({"delete"})

# Operasi database yang selalu dianggap destruktif
_DESTRUCTIVE_DB_OPERATIONS: frozenset[str] = frozenset({"execute_dml"})

# Nama tool yang menggunakan sandbox jika tersedia
_SANDBOXED_TOOL_NAMES: frozenset[str] = frozenset({"shell", "browser"})


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class Executor:
    """Menjalankan ToolCall dari Agen dengan pemeriksaan keamanan berlapis.

    Bertanggung jawab atas:
    - Pemeriksaan blocklist sebelum setiap eksekusi.
    - Konfirmasi pengguna untuk operasi destruktif.
    - Isolasi error plugin agar sesi tidak berhenti (Requirement 9.8).
    - Pencatatan setiap tindakan ke AuditLogger (Requirement 10.4).
    - Integrasi sandbox opsional untuk ShellTool dan BrowserTool (Requirement 10.6).

    Args:
        registry:           Registry tool yang terdaftar.
        confirmation_gate:  Mekanisme konfirmasi pengguna untuk operasi destruktif.
        sandbox:            Sandbox opsional (stub untuk saat ini); jika disediakan,
                            ShellTool dan BrowserTool dijalankan dalam konteks sandbox.
        blocklist:          Daftar larangan opsional. Jika ``None``, pemeriksaan
                            blocklist dilewati.
        audit_logger:       Logger audit opsional. Jika ``None``, pencatatan
                            dilewati.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        confirmation_gate: ConfirmationGate,
        sandbox: Any | None = None,
        blocklist: "Blocklist | None" = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        self._registry = registry
        self._confirmation_gate = confirmation_gate
        self._sandbox = sandbox
        self._blocklist = blocklist
        self._audit_logger = audit_logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, call: ToolCall) -> ToolResult:
        """Eksekusi satu ToolCall dengan pemeriksaan keamanan penuh.

        Alur:
        1. Blocklist check → ``ToolResult(success=False)`` jika diblokir.
        2. Registry lookup → ``ToolResult(success=False)`` jika tidak ditemukan.
        3. Destructive check + konfirmasi → ``ToolResult(success=False)`` jika ditolak.
        4. ``tool.run(params)`` dalam try/except total.
        5. Log ke AuditLogger.

        Args:
            call: Deskripsi tool yang akan dieksekusi beserta parameternya.

        Returns:
            ``ToolResult`` dengan ``success=True`` jika berhasil, atau
            ``ToolResult(success=False, error=...)`` untuk semua kondisi gagal.
            Exception yang dilempar oleh plugin **tidak pernah merambat** ke caller.
        """
        # ------------------------------------------------------------------
        # Langkah 1: Pemeriksaan blocklist
        # ------------------------------------------------------------------
        if self._blocklist is not None:
            blocked, violation_msg = self._check_blocklist(call)
            if blocked:
                self._log_error(
                    error=violation_msg,
                    context={"tool_name": call.tool_name, "params": call.params},
                )
                return ToolResult(
                    success=False,
                    data=None,
                    error=violation_msg,
                    tool_name=call.tool_name,
                )

        # ------------------------------------------------------------------
        # Langkah 2: Ambil tool dari registry
        # ------------------------------------------------------------------
        tool = self._registry.get(call.tool_name)
        if tool is None:
            msg = (
                f"Tool '{call.tool_name}' tidak ditemukan atau sedang dinonaktifkan "
                f"dalam ToolRegistry."
            )
            self._log_error(
                error=msg,
                context={"tool_name": call.tool_name, "params": call.params},
            )
            return ToolResult(
                success=False,
                data=None,
                error=msg,
                tool_name=call.tool_name,
            )

        # ------------------------------------------------------------------
        # Langkah 3: Pemeriksaan destruktif + konfirmasi pengguna
        # ------------------------------------------------------------------
        if self.is_destructive(call):
            confirmed = await self._request_confirmation(call)
            if not confirmed:
                msg = (
                    f"Operasi '{call.tool_name}' dibatalkan oleh pengguna "
                    f"atau melebihi batas waktu konfirmasi."
                )
                self._log_action(
                    action=call.tool_name,
                    params=call.params,
                    result="cancelled — user denied or timeout",
                    confirmed=False,
                )
                return ToolResult(
                    success=False,
                    data=None,
                    error=msg,
                    tool_name=call.tool_name,
                )

        # ------------------------------------------------------------------
        # Langkah 4: Eksekusi tool (isolasi total exception)
        # ------------------------------------------------------------------
        result: ToolResult
        try:
            # Sandbox wrapping (stub): sandbox hanya aktif untuk tool tertentu
            if self._sandbox is not None and call.tool_name in _SANDBOXED_TOOL_NAMES:
                result = await self._run_in_sandbox(tool, call)
            else:
                result = await tool.run(call.params)

            # Pastikan tool_name selalu terisi
            if not result.tool_name:
                result.tool_name = call.tool_name

        except Exception as exc:  # noqa: BLE001 — isolasi total, sesi tidak boleh berhenti
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Uncaught exception dari plugin '%s': %s",
                call.tool_name,
                error_msg,
            )
            self._log_error(
                error=error_msg,
                context={
                    "tool_name": call.tool_name,
                    "params": call.params,
                    "exception_type": type(exc).__name__,
                },
            )
            return ToolResult(
                success=False,
                data=None,
                error=error_msg,
                tool_name=call.tool_name,
            )

        # ------------------------------------------------------------------
        # Langkah 5: Log ke AuditLogger
        # ------------------------------------------------------------------
        result_str = "success" if result.success else f"failed: {result.error}"
        self._log_action(
            action=call.tool_name,
            params=call.params,
            result=result_str,
            confirmed=True,
        )

        return result

    def is_destructive(self, call: ToolCall) -> bool:
        """Tentukan apakah eksekusi ToolCall memerlukan konfirmasi pengguna.

        Urutan pemeriksaan:
        1. Jika ``call.requires_confirmation`` adalah ``True``, langsung kembalikan ``True``.
        2. Jika tool memiliki method ``is_destructive(command)``, delegasikan ke tool tersebut
           (berlaku untuk ShellTool yang memeriksa pola regex).
        3. Untuk FileSystemTool dengan operasi ``"delete"``: destruktif.
        4. Untuk DatabaseTool dengan operasi ``"execute_dml"``: destruktif.
        5. Jika tidak memenuhi kriteria apapun di atas, kembalikan ``False``.

        Args:
            call: ToolCall yang akan diperiksa.

        Returns:
            ``True`` jika operasi memerlukan konfirmasi; ``False`` jika tidak.
        """
        # Prioritas 1: flag eksplisit dari caller/planner
        if call.requires_confirmation:
            return True

        # Prioritas 2: delegasi ke tool jika tool memiliki is_destructive()
        # (ShellTool mengimplementasikan is_destructive(command) → bool)
        tool = self._registry.get(call.tool_name)
        if tool is not None and hasattr(tool, "is_destructive") and callable(
            getattr(tool, "is_destructive")
        ):
            # ShellTool: is_destructive(command: str) → bool
            command = call.params.get("command", "")
            if command and call.tool_name == "shell":
                return tool.is_destructive(command)  # type: ignore[return-value]

        # Prioritas 3: operasi destruktif FileSystemTool
        if call.tool_name == "filesystem":
            operation = call.params.get("operation", "")
            if operation in _DESTRUCTIVE_FS_OPERATIONS:
                return True

        # Prioritas 4: operasi destruktif DatabaseTool
        if call.tool_name == "database":
            operation = call.params.get("operation", "")
            if operation in _DESTRUCTIVE_DB_OPERATIONS:
                return True

        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_blocklist(self, call: ToolCall) -> tuple[bool, str]:
        """Periksa apakah ToolCall melanggar aturan blocklist.

        Memeriksa tiga tipe blocklist:
        - ``FILE_PATH``: untuk tool ``filesystem`` dengan parameter ``path``, ``src``, ``dst``.
        - ``COMMAND``:   untuk tool ``shell`` dengan parameter ``command``.
        - ``DOMAIN``:    untuk tool ``http_api`` dan ``browser`` dengan parameter ``url``.

        Returns:
            Tuple ``(is_blocked, violation_message)``.
            ``is_blocked=False`` dan ``violation_message=""`` jika tidak diblokir.
        """
        from agent.core.blocklist import BlocklistEntryType

        # Filesystem: periksa path
        if call.tool_name == "filesystem":
            for param_key in ("path", "src", "dst", "directory"):
                value = call.params.get(param_key, "")
                if value and self._blocklist.is_blocked(  # type: ignore[union-attr]
                    BlocklistEntryType.FILE_PATH, value
                ):
                    exc = AgentBlocklistViolationError(
                        entry_type="file_path",
                        value=value,
                        matched_pattern=value,  # exact match atau glob
                    )
                    return True, str(exc)

        # Shell: periksa command
        elif call.tool_name == "shell":
            command = call.params.get("command", "")
            if command and self._blocklist.is_blocked(  # type: ignore[union-attr]
                BlocklistEntryType.COMMAND, command
            ):
                exc = AgentBlocklistViolationError(
                    entry_type="command",
                    value=command,
                    matched_pattern=command,
                )
                return True, str(exc)

        # HTTP API / Browser: periksa domain via URL
        elif call.tool_name in ("http_api", "browser"):
            url = call.params.get("url", "")
            if url and self._blocklist.is_blocked(  # type: ignore[union-attr]
                BlocklistEntryType.DOMAIN, url
            ):
                exc = AgentBlocklistViolationError(
                    entry_type="domain",
                    value=url,
                    matched_pattern=url,
                )
                return True, str(exc)

        return False, ""

    async def _request_confirmation(self, call: ToolCall) -> bool:
        """Bangun ConfirmationRequest dan minta konfirmasi pengguna.

        Menyertakan perintah shell lengkap di ``full_command`` jika tersedia,
        atau deskripsi operasi dalam bahasa alami jika tidak.

        Args:
            call: ToolCall yang memerlukan konfirmasi.

        Returns:
            ``True`` jika pengguna mengkonfirmasi; ``False`` jika ditolak/timeout.
        """
        full_command: str | None = None
        description: str

        if call.tool_name == "shell":
            full_command = call.params.get("command") or call.params.get(
                "script_path", ""
            )
            description = (
                f"Menjalankan perintah shell: {full_command or '(tidak diketahui)'}"
            )
        elif call.tool_name == "filesystem":
            operation = call.params.get("operation", "")
            path = call.params.get("path", call.params.get("src", ""))
            description = f"Operasi filesystem '{operation}' pada path: {path}"
        elif call.tool_name == "database":
            operation = call.params.get("operation", "")
            query = call.params.get("query", "")
            description = f"Operasi database '{operation}': {query}"
        else:
            description = (
                f"Operasi '{call.tool_name}' dengan parameter: {call.params}"
            )

        req = ConfirmationRequest(
            operation_type=call.tool_name,
            description=description,
            full_command=full_command,
        )

        return await self._confirmation_gate.request(req)

    async def _run_in_sandbox(self, tool: Any, call: ToolCall) -> ToolResult:
        """Jalankan tool di dalam sandbox (stub implementasi).

        Untuk saat ini, sandbox hanya diperlakukan sebagai pass-through.
        Implementasi penuh (Docker SDK atau subprocess dengan restricted env)
        akan ditambahkan di tugas sandbox khusus.

        Args:
            tool: Instansi tool yang akan dieksekusi.
            call: ToolCall yang berisi parameter eksekusi.

        Returns:
            ``ToolResult`` dari eksekusi tool (pass-through untuk saat ini).
        """
        logger.debug(
            "Sandbox aktif untuk tool '%s' — menjalankan dalam konteks sandbox (stub).",
            call.tool_name,
        )
        return await tool.run(call.params)

    def _log_action(
        self,
        action: str,
        params: dict[str, Any],
        result: str,
        confirmed: bool,
    ) -> None:
        """Catat tindakan ke AuditLogger jika tersedia."""
        if self._audit_logger is not None:
            try:
                self._audit_logger.log_action(
                    action=action,
                    params=params,
                    result=result,
                    confirmed=confirmed,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("AuditLogger.log_action gagal: %s", exc)

    def _log_error(self, error: str, context: dict[str, Any]) -> None:
        """Catat error ke AuditLogger jika tersedia."""
        if self._audit_logger is not None:
            try:
                self._audit_logger.log_error(error=error, context=context)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AuditLogger.log_error gagal: %s", exc)


__all__ = [
    "Executor",
]
