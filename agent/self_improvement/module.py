"""
agent/self_improvement/module.py

SelfImprovementModule — mengelola proses modifikasi diri Agent, termasuk
pembaruan konfigurasi, plugin baru, dan rollback ke versi sebelumnya.

Konstanta:
    MAX_BACKUP_VERSIONS        = 10
    MAX_PLUGIN_DOWNLOAD_BYTES  = 500 MB
    APPLY_TIMEOUT_SECONDS      = 30

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9
"""

from __future__ import annotations

import asyncio
import difflib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import tomllib
import tomli_w

from agent.core.confirmation_gate import ConfirmationGate, ConfirmationRequest
from agent.core.exceptions import (
    AgentModelParameterRangeError,
    AgentPluginSchemaError,
    AgentPluginSizeExceededError,
    AgentSelfImprovementApplyError,
)
from agent.models.schemas import ConfigProposal
from agent.self_improvement.backup_manager import BackupManager
from agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_BACKUP_VERSIONS = 10
MAX_PLUGIN_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
APPLY_TIMEOUT_SECONDS = 30

# Rentang nilai parameter model yang valid (Requirements 8.5, 8.6)
TEMPERATURE_MIN: float = 0.0
TEMPERATURE_MAX: float = 2.0
CONTEXT_LENGTH_MIN: int = 128
CONTEXT_LENGTH_MAX: int = 131072


# ---------------------------------------------------------------------------
# SelfImprovementModule
# ---------------------------------------------------------------------------


class SelfImprovementModule:
    """Subsistem yang mengelola modifikasi konfigurasi dan plugin Agent.

    Args:
        config_path:       Path ke file ``config.toml`` yang aktif.
        registry:          Instance ``ToolRegistry`` tempat plugin baru didaftarkan.
        confirmation_gate: Instance ``ConfirmationGate`` untuk meminta konfirmasi
                           sebelum menerapkan perubahan.
        backup_manager:    Instance ``BackupManager`` untuk membuat dan memulihkan
                           backup konfigurasi.
    """

    def __init__(
        self,
        config_path: Path,
        registry: ToolRegistry,
        confirmation_gate: ConfirmationGate,
        backup_manager: BackupManager,
    ) -> None:
        self._config_path = Path(config_path)
        self._registry = registry
        self._confirmation_gate = confirmation_gate
        self._backup_manager = backup_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_config(self) -> dict:
        """Baca file ``config.toml`` yang aktif dan kembalikan sebagai dict.

        Returns:
            Dict representasi konfigurasi Agent saat ini.

        Raises:
            FileNotFoundError: Jika ``config_path`` tidak ada.
            tomllib.TOMLDecodeError: Jika file bukan TOML yang valid.
        """
        with self._config_path.open("rb") as fh:
            return tomllib.load(fh)

    async def propose_change(self, instruction: str) -> ConfigProposal:
        """Analisis instruksi dan hasilkan ``ConfigProposal`` dengan diff.

        Mendukung pengenalan instruksi berbasis kata kunci untuk parameter
        model dan pengaturan umum.  Contoh instruksi yang dikenali:

        - "set temperature to 0.5"
        - "set temperature 0.5"
        - "set context_length to 8192"
        - "set context length to 8192"
        - "set shell_timeout_seconds to 60"
        - "set max_consecutive_actions to 15"
        - "set sandbox_enabled to true"

        Args:
            instruction: Instruksi bahasa alami dari pengguna.

        Returns:
            ``ConfigProposal`` yang berisi diff, konfigurasi lama/baru,
            dan flag ``requires_restart``.

        Raises:
            AgentModelParameterRangeError: Jika nilai parameter di luar rentang
                yang valid (temperature 0.0–2.0, context_length 128–131072).
            ValueError: Jika instruksi tidak dapat diparsing atau nilai tidak valid.
        """
        old_config = self.read_config()
        new_config = _deep_copy_config(old_config)

        # --- Parsing instruksi berbasis kata kunci ---
        normalized = instruction.strip().lower()

        # Deteksi "set <key> [to] <value>"
        changed_key, new_value = _parse_set_instruction(normalized)

        if changed_key is not None and new_value is not None:
            new_config = _apply_key_value(new_config, changed_key, new_value)

        # Validasi parameter model setelah perubahan
        _validate_model_parameters(new_config)

        # --- Hasilkan unified diff ---
        old_toml = _dict_to_toml_str(old_config)
        new_toml = _dict_to_toml_str(new_config)
        diff = _make_unified_diff(old_toml, new_toml, "config.toml")

        description = (
            f"Perubahan dari instruksi: '{instruction}'" if changed_key
            else f"Instruksi tidak mengubah konfigurasi: '{instruction}'"
        )

        return ConfigProposal(
            description=description,
            diff=diff,
            old_config=old_config,
            new_config=new_config,
            requires_restart=False,
        )

    async def apply_change(self, proposal: ConfigProposal) -> None:
        """Terapkan ``ConfigProposal`` ke file konfigurasi.

        Alur:
        1. Buat backup konfigurasi saat ini via ``backup_manager``.
        2. Tampilkan diff ke pengguna via ``ConfirmationGate``.
        3. Jika pengguna menolak → hentikan tanpa perubahan.
        4. Terapkan konfigurasi baru ke file dalam batas waktu
           ``APPLY_TIMEOUT_SECONDS`` (30 detik).
        5. Jika gagal → rollback otomatis ke backup yang baru dibuat.

        Args:
            proposal: ``ConfigProposal`` yang dihasilkan oleh ``propose_change``.

        Raises:
            AgentSelfImprovementApplyError: Jika penerapan gagal dan rollback
                berhasil dipicu. Rollback yang gagal juga di-raise dengan
                ``rollback_triggered=False``.
        """
        # Langkah 1: Buat backup konfigurasi saat ini
        current_config = self.read_config()
        backup_path = self._backup_manager.create_backup(current_config)

        # Langkah 2: Tampilkan diff dan minta konfirmasi
        req = ConfirmationRequest(
            operation_type="apply_change",
            description=proposal.description,
            diff=proposal.diff if proposal.diff else None,
        )
        confirmed = await self._confirmation_gate.request(req)

        # Langkah 3: Jika ditolak → hentikan
        if not confirmed:
            return

        # Langkah 4: Terapkan perubahan dalam batas waktu 30 detik
        try:
            await asyncio.wait_for(
                self._write_config(proposal.new_config),
                timeout=APPLY_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            # Langkah 5: Rollback otomatis
            rollback_ok = await self._restore_from_path(backup_path)
            reason = (
                f"timeout melebihi {APPLY_TIMEOUT_SECONDS} detik"
                if isinstance(exc, asyncio.TimeoutError)
                else str(exc)
            )
            raise AgentSelfImprovementApplyError(
                description=proposal.description,
                reason=reason,
                rollback_triggered=rollback_ok,
            ) from exc

    async def download_plugin(self, url: str, name: str) -> None:
        """Unduh plugin dari URL, validasi skema, dan daftarkan ke registry.

        Batasan:
        - Ukuran file plugin maksimum 500 MB (``MAX_PLUGIN_DOWNLOAD_BYTES``).
        - Plugin wajib memenuhi ``ToolInterface`` (validasi via ``registry``).

        Alur:
        1. Unduh file dari ``url`` menggunakan streaming httpx.
        2. Periksa ukuran kumulatif — batalkan jika melebihi 500 MB.
        3. Simpan ke file sementara di direktori temp OS.
        4. Import modul secara dinamis via ``importlib``.
        5. Validasi skema plugin via ``registry.validate_plugin_schema()``.
        6. Daftarkan plugin ke registry sebagai ``source="plugin"``.
        7. Bersihkan file sementara jika terjadi kegagalan.

        Args:
            url:  URL tempat file plugin dapat diunduh.
            name: Nama yang ditetapkan untuk plugin ini (digunakan sebagai
                  nama modul saat import dinamis).

        Raises:
            AgentPluginSizeExceededError: Jika ukuran file melebihi 500 MB.
            AgentPluginSchemaError: Jika plugin tidak memenuhi ``ToolInterface``.
            httpx.HTTPError: Untuk kegagalan jaringan/HTTP.
            ImportError: Jika file yang diunduh bukan modul Python yang valid.
        """
        tmp_path: Path | None = None
        try:
            # Langkah 1–3: Unduh dengan streaming, periksa ukuran
            tmp_path = await _download_to_temp(url, name, MAX_PLUGIN_DOWNLOAD_BYTES)

            # Langkah 4: Import dinamis
            plugin_instance = _import_plugin(tmp_path, name)

            # Langkah 5: Validasi skema
            missing_fields = self._registry.validate_plugin_schema(plugin_instance)
            if missing_fields:
                raise AgentPluginSchemaError(
                    plugin_name=name,
                    missing_fields=missing_fields,
                )

            # Langkah 6: Daftarkan ke registry
            self._registry.register(plugin_instance, source="plugin")

        except Exception:
            # Langkah 7: Bersihkan file sementara saat ada kegagalan
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    async def rollback(self) -> None:
        """Pulihkan konfigurasi Agent ke versi backup terakhir.

        Operasi harus selesai dalam batas waktu 30 detik.

        Raises:
            FileNotFoundError: Jika tidak ada backup yang tersedia.
            AgentSelfImprovementApplyError: Jika rollback gagal atau melampaui
                batas waktu.
        """
        latest = self._backup_manager.get_latest()
        if latest is None:
            raise FileNotFoundError(
                "Tidak ada backup yang tersedia untuk rollback."
            )

        try:
            await asyncio.wait_for(
                self._write_config(latest),
                timeout=APPLY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise AgentSelfImprovementApplyError(
                description="rollback ke backup terakhir",
                reason=f"timeout melebihi {APPLY_TIMEOUT_SECONDS} detik",
                rollback_triggered=False,
            ) from exc
        except Exception as exc:
            raise AgentSelfImprovementApplyError(
                description="rollback ke backup terakhir",
                reason=str(exc),
                rollback_triggered=False,
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_config(self, config: dict) -> None:
        """Tulis dict konfigurasi ke ``config_path`` menggunakan tomli_w."""
        toml_bytes = tomli_w.dumps(config).encode("utf-8")
        self._config_path.write_bytes(toml_bytes)

    async def _restore_from_path(self, backup_path: str) -> bool:
        """Pulihkan konfigurasi dari path backup yang diberikan.

        Returns:
            ``True`` jika rollback berhasil, ``False`` jika gagal.
        """
        try:
            src = Path(backup_path)
            self._config_path.write_bytes(src.read_bytes())
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Fungsi pembantu (modul-level, tidak di-export)
# ---------------------------------------------------------------------------


def _deep_copy_config(config: dict) -> dict:
    """Buat salinan mendalam dari dict konfigurasi menggunakan TOML round-trip."""
    import json
    return json.loads(json.dumps(config))


def _parse_set_instruction(normalized: str) -> tuple[str | None, str | None]:
    """Parsing instruksi 'set <key> [to] <value>' dari teks yang sudah dinormalisasi.

    Mendukung nama kunci dengan spasi, misalnya "context length" → "context_length".

    Strategi:
    - Jika ada kata "to" sebagai separator, pisahkan kunci sebelum " to " dan nilai sesudahnya.
    - Jika tidak ada "to", ambil token pertama sebagai kunci dan sisa sebagai nilai.

    Returns:
        Tuple ``(key, value_str)`` atau ``(None, None)`` jika tidak dikenali.
    """
    import re

    text = normalized.strip()

    # Harus dimulai dengan "set "
    if not text.startswith("set "):
        return None, None

    body = text[4:].strip()  # buang "set " di depan

    # Coba pisahkan dengan " to " (separator eksplisit, prioritas utama)
    to_pattern = re.compile(r"^(?P<key>.+?)\s+to\s+(?P<value>\S.*)$")
    m = to_pattern.match(body)
    if m:
        key_raw = m.group("key").strip()
        value_str = m.group("value").strip()
        key = re.sub(r"\s+", "_", key_raw)
        return key, value_str

    # Fallback: ambil token pertama sebagai kunci, sisanya sebagai nilai
    parts = body.split(maxsplit=1)
    if len(parts) == 2:
        key = re.sub(r"\s+", "_", parts[0].strip())
        return key, parts[1].strip()

    return None, None


def _apply_key_value(config: dict, key: str, value_str: str) -> dict:
    """Terapkan key=value_str ke konfigurasi.

    Penanganan:
    - ``temperature`` dan ``context_length`` ada di bawah ``model_parameters``.
    - Kunci lainnya ada di level atas.

    Args:
        config:    Dict konfigurasi yang akan dimodifikasi (salinannya).
        key:       Nama kunci (snake_case).
        value_str: Nilai baru sebagai string.

    Returns:
        Dict konfigurasi yang sudah diperbarui.

    Raises:
        ValueError: Jika tipe nilai tidak dapat dikonversi.
    """
    # Konversi nilai ke tipe Python yang tepat
    parsed_value = _coerce_value(value_str)

    # Parameter model ada di bawah sub-tabel ``model_parameters``
    _MODEL_PARAM_KEYS = {"temperature", "context_length"}
    if key in _MODEL_PARAM_KEYS:
        if "model_parameters" not in config:
            config["model_parameters"] = {}
        config["model_parameters"][key] = parsed_value
    else:
        config[key] = parsed_value

    return config


def _coerce_value(value_str: str):
    """Konversi string nilai ke tipe Python: bool, int, float, atau str."""
    lower = value_str.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    # Coba int
    try:
        return int(value_str)
    except ValueError:
        pass
    # Coba float
    try:
        return float(value_str)
    except ValueError:
        pass
    # Kembalikan sebagai string (hapus kutip jika ada)
    return value_str.strip("\"'")


def _validate_model_parameters(config: dict) -> None:
    """Validasi rentang nilai di bawah ``model_parameters``.

    Raises:
        AgentModelParameterRangeError: Jika temperature atau context_length
            di luar rentang yang diizinkan.
    """
    params = config.get("model_parameters", {})

    temperature = params.get("temperature")
    if temperature is not None:
        if not isinstance(temperature, (int, float)) or not (
            TEMPERATURE_MIN <= float(temperature) <= TEMPERATURE_MAX
        ):
            raise AgentModelParameterRangeError(
                parameter_name="temperature",
                value=temperature,
                min_value=TEMPERATURE_MIN,
                max_value=TEMPERATURE_MAX,
            )

    context_length = params.get("context_length")
    if context_length is not None:
        if not isinstance(context_length, int) or not (
            CONTEXT_LENGTH_MIN <= context_length <= CONTEXT_LENGTH_MAX
        ):
            raise AgentModelParameterRangeError(
                parameter_name="context_length",
                value=context_length,
                min_value=CONTEXT_LENGTH_MIN,
                max_value=CONTEXT_LENGTH_MAX,
            )


def _dict_to_toml_str(config: dict) -> str:
    """Serialisasi dict ke string TOML."""
    return tomli_w.dumps(config)


def _make_unified_diff(old_text: str, new_text: str, filename: str) -> str:
    """Hasilkan unified diff antara dua teks TOML.

    Args:
        old_text: Konten konfigurasi lama sebagai string.
        new_text: Konten konfigurasi baru sebagai string.
        filename: Nama file untuk header diff.

    Returns:
        String unified diff. Kosong jika tidak ada perubahan.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    return "".join(diff_lines)


async def _download_to_temp(
    url: str,
    name: str,
    max_bytes: int,
) -> Path:
    """Unduh file dari URL ke file sementara dengan pemeriksaan ukuran streaming.

    Args:
        url:       URL sumber file plugin.
        name:      Nama plugin (digunakan sebagai prefix file temp).
        max_bytes: Batas ukuran maksimum dalam bytes.

    Returns:
        Path ke file sementara yang berhasil diunduh.

    Raises:
        AgentPluginSizeExceededError: Jika ukuran konten melebihi ``max_bytes``.
        httpx.HTTPStatusError: Untuk kode HTTP 4xx/5xx.
        httpx.RequestError:    Untuk kegagalan jaringan.
    """
    # Nama file sementara dengan ekstensi .py
    suffix = ".py"
    tmp_fd, tmp_path_str = tempfile.mkstemp(prefix=f"plugin_{name}_", suffix=suffix)
    tmp_path = Path(tmp_path_str)

    total_bytes = 0
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", url, timeout=60.0) as response:
                response.raise_for_status()

                with open(tmp_fd, "wb") as fh:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise AgentPluginSizeExceededError(
                                plugin_name=name,
                                actual_bytes=total_bytes,
                                limit_bytes=max_bytes,
                            )
                        fh.write(chunk)
    except AgentPluginSizeExceededError:
        # File descriptor sudah ditutup oleh context manager 'with open'
        # Hapus file parsial
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except Exception:
        try:
            import os
            os.close(tmp_fd)
        except OSError:
            pass
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return tmp_path


def _import_plugin(plugin_path: Path, name: str) -> object:
    """Import modul Python secara dinamis dari path file.

    Args:
        plugin_path: Path ke file ``.py`` plugin.
        name:        Nama modul yang akan didaftarkan ke ``sys.modules``.

    Returns:
        Instance kelas pertama yang ditemukan dalam modul yang baru diimport,
        atau modul itu sendiri jika tidak ada kelas yang tersedia.

    Raises:
        ImportError: Jika file tidak dapat diimport sebagai modul Python.
        AttributeError: Jika modul tidak memiliki objek yang bisa di-instantiate.
    """
    module_name = f"_agent_plugin_{name}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Tidak dapat membuat module spec dari file: '{plugin_path}'"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    # Cari kelas Tool di dalam modul: prioritaskan yang memiliki atribut 'name'
    import inspect

    candidates = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module_name and hasattr(obj, "name")
    ]

    if candidates:
        # Instantiasi kelas pertama tanpa argumen
        return candidates[0]()

    # Fallback: kembalikan modul langsung (ToolRegistry akan validasi nanti)
    return module


__all__ = [
    "MAX_BACKUP_VERSIONS",
    "MAX_PLUGIN_DOWNLOAD_BYTES",
    "APPLY_TIMEOUT_SECONDS",
    "SelfImprovementModule",
]
