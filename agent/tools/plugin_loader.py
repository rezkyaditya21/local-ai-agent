"""
agent/tools/plugin_loader.py

Plugin Loader — menemukan dan memuat plugin/tool secara dinamis dari direktori tanpa mengubah kode inti agent.

Komponen utama:
- `PluginLoader`: Penemu dan pemuat plugin otomatis.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry

_logger = logging.getLogger(__name__)


class PluginLoader:
    """Mekanisme untuk menemukan dan mendaftarkan plugin eksternal secara dinamis."""

    def __init__(self, registry: "ToolRegistry") -> None:
        self._registry = registry

    def discover_and_load(self, plugin_dir: Path) -> list[str]:
        """Pindai direktori `plugin_dir` dan daftarkan semua kelas tool yang valid.

        Args:
            plugin_dir: Path direktori plugin.

        Returns:
            Daftar nama tool yang berhasil didaftarkan.
        """
        loaded_tools: list[str] = []

        if not plugin_dir.exists() or not plugin_dir.is_dir():
            _logger.debug("Plugin directory '%s' tidak ditemukan.", plugin_dir)
            return loaded_tools

        for filepath in plugin_dir.glob("*.py"):
            if filepath.name.startswith("_"):
                continue

            try:
                module_name = f"agent_plugin_{filepath.stem}"
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Cari atribut yang memenuhi ToolInterface
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and hasattr(attr, "name") and hasattr(attr, "run"):
                        try:
                            instance = attr()
                            missing = self._registry.validate_plugin_schema(instance)
                            if not missing:
                                self._registry.register(instance, source="plugin")
                                loaded_tools.append(instance.name)
                                _logger.info("Plugin '%s' berhasil dimuat dari %s", instance.name, filepath.name)
                        except Exception as exc:
                            _logger.warning("Gagal menginisialisasi plugin %s: %s", attr_name, exc)

            except Exception as exc:
                _logger.warning("Gagal memuat berkas plugin %s: %s", filepath, exc)

        return loaded_tools


__all__ = ["PluginLoader"]
