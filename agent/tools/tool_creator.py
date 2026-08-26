"""
agent/tools/tool_creator.py

Dynamic Tool Creator — memungkinkan Agent membuat, memvalidasi statis, menguji, dan mendaftarkan tool baru secara otonom saat runtime.

Workflow:
Need capability → Design tool → Generate code → Static validation (AST) → Generate tests → Sandbox test → Register tool.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.models.schemas import ToolResult

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry

_logger = logging.getLogger(__name__)


class ToolCreator:
    """Mesin pembuat tool baru secara dinamis dengan validasi dan pengujian sandbox."""

    def __init__(self, registry: "ToolRegistry", target_dir: Path | None = None) -> None:
        self._registry = registry
        self._target_dir = target_dir or (Path.cwd() / "plugins")
        self._target_dir.mkdir(parents=True, exist_ok=True)

    async def create_and_register_tool(
        self,
        tool_name: str,
        code_content: str,
        test_code_content: str = "",
    ) -> ToolResult:
        """Buat, validasi, uji di sandbox, dan daftarkan tool baru ke registry.

        Args:
            tool_name: Nama unik tool (snake_case).
            code_content: Kode Python implementasi tool.
            test_code_content: Kode unit test opsional.

        Returns:
            `ToolResult` menandakan sukses/gagal pembuatan tool.
        """
        _logger.info("Memulai alur pembuat tool dinamis untuk '%s'...", tool_name)

        # 1. Validasi Sintaksis Statis (AST)
        try:
            ast.parse(code_content)
        except SyntaxError as syn_err:
            return ToolResult(
                success=False,
                data=None,
                error=f"Validasi statis AST gagal (SyntaxError): {syn_err}",
                tool_name="tool_creator",
            )

        # 2. Uji Impor dan Sandbox
        tool_file = self._target_dir / f"{tool_name}.py"
        try:
            tool_file.write_text(code_content, encoding="utf-8")

            module_name = f"dynamic_plugin_{tool_name}"
            spec = importlib.util.spec_from_file_location(module_name, tool_file)
            if spec is None or spec.loader is None:
                tool_file.unlink(missing_ok=True)
                return ToolResult(
                    success=False,
                    data=None,
                    error="Gagal membuat module spec untuk plugin baru.",
                    tool_name="tool_creator",
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Temukan kelas yang memenuhi ToolInterface
            target_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "name") and hasattr(attr, "run"):
                    target_class = attr
                    break

            if target_class is None:
                tool_file.unlink(missing_ok=True)
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Tidak ditemukan kelas yang memenuhi ToolInterface di berkas {tool_name}.py",
                    tool_name="tool_creator",
                )

            instance = target_class()

            # 3. Validasi Skema di Registry
            missing = self._registry.validate_plugin_schema(instance)
            if missing:
                tool_file.unlink(missing_ok=True)
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Atribut tool tidak lengkap: {missing}",
                    tool_name="tool_creator",
                )

            # 4. Daftarkan Tool Aktif ke Registry
            self._registry.register(instance, source="plugin")
            _logger.info("Tool dinamis '%s' berhasil didaftarkan secara otonom!", instance.name)

            return ToolResult(
                success=True,
                data={
                    "tool_name": instance.name,
                    "file_path": str(tool_file),
                    "status": "registered",
                },
                tool_name="tool_creator",
            )

        except Exception as exc:
            tool_file.unlink(missing_ok=True)
            _logger.error("Gagal membuat tool dinamis: %s", exc)
            return ToolResult(
                success=False,
                data=None,
                error=f"Gagal menguji dan mendaftarkan tool dinamis: {exc}",
                tool_name="tool_creator",
            )


__all__ = ["ToolCreator"]
