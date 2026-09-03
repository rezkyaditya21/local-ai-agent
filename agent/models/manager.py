"""
agent/models/manager.py

Model Manager â€” mengelola pemilihan, pemuatan, konfigurasi, dan penggantian
model AI yang digunakan oleh Agent.

Mendukung dua jenis model:
- **GGUF lokal**: dimuat via ``llama-cpp-python`` dari path file.
- **API endpoint**: dihubungkan ke Ollama / llama.cpp server via ``httpx``
  menggunakan endpoint kompatibel Ollama (POST /api/generate).

Fitur utama:
- Hot-swap model tanpa restart Agent (â‰¤30 detik).
- Validasi rentang parameter (temperature 0.0â€“2.0, context_length 128â€“131072).
- Graceful degradation: jika llama-cpp-python tidak terinstal, model GGUF
  tidak dapat dimuat tetapi Agent tetap berjalan.
- Simpan model default ke config.toml menggunakan ``tomli_w``.

Requirements yang diimplementasikan: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8,
8.5, 8.6
"""

from __future__ import annotations

import asyncio
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Any

import tomli_w

from agent.core.exceptions import (
    AgentModelLoadTimeoutError,
    AgentModelNotFoundError,
    AgentModelParameterRangeError,
)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_GGUF_SIZE_BYTES: int = 100 * 1024 * 1024 * 1024  # 100 GB
MODEL_LOAD_TIMEOUT_SECONDS: int = 120
MODEL_SWITCH_TIMEOUT_SECONDS: int = 120

# Rentang valid untuk parameter model
TEMPERATURE_MIN: float = 0.0
TEMPERATURE_MAX: float = 2.0
CONTEXT_LENGTH_MIN: int = 128
CONTEXT_LENGTH_MAX: int = 131072

# Logger internal
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Konfigurasi satu model yang terdaftar.

    Attributes:
        name: Identifier unik model (digunakan di ``/model use <name>``).
        model_type: Tipe model â€” ``"gguf"`` untuk file lokal,
            ``"api"`` untuk API endpoint.
        path_or_url: Path absolut/relatif ke file GGUF (untuk ``"gguf"``)
            atau URL ke Ollama / llama.cpp server (untuk ``"api"``).
        size_bytes: Ukuran file dalam byte (opsional; ``None`` untuk model API).
    """

    name: str
    model_type: str       # "gguf" | "api"
    path_or_url: str
    size_bytes: int | None = None


@dataclass
class ModelParameters:
    """Parameter runtime yang diterapkan ke model aktif.

    Attributes:
        temperature: Nilai antara 0.0â€“2.0 yang mengontrol tingkat keacakan
            output model. Nilai lebih rendah = lebih deterministik.
        context_length: Panjang konteks dalam token (128â€“131072).
    """

    temperature: float    # 0.0 â€“ 2.0
    context_length: int   # 128 â€“ 131072


# ---------------------------------------------------------------------------
# ModelManager
# ---------------------------------------------------------------------------


class ModelManager:
    """Mengelola daftar model, model aktif, dan streaming token.

    Satu instansi ``ModelManager`` menyimpan:
    - Daftar ``ModelConfig`` yang diambil dari ``config.toml``.
    - Model yang sedang aktif (``_active_model``).
    - Handle LLM yang sedang dimuat (``_llm_handle``) â€” bisa berupa
      instansi ``llama_cpp.Llama`` atau ``None`` (untuk model API).
    - Parameter runtime aktif (``_parameters``).

    Args:
        config_path: Path ke file ``config.toml`` yang akan dibaca.
    """

    def __init__(self, config_path: str) -> None:
        self._config_path: Path = Path(config_path)
        self._models: list[ModelConfig] = []
        self._active_model: ModelConfig | None = None
        self._llm_handle: Any = None   # llama_cpp.Llama | None
        self._parameters: ModelParameters = ModelParameters(
            temperature=0.7,
            context_length=4096,
        )
        # Muat konfigurasi saat inisialisasi
        self.load_config()

    # ------------------------------------------------------------------
    # load_config() â€” muat konfigurasi dari config.toml
    # ------------------------------------------------------------------

    def load_config(self) -> None:
        """Muat (atau muat ulang) konfigurasi dari ``config.toml``.

        Membaca:
        - ``[[models]]``: daftar model yang terdaftar.
        - ``default_model``: nama model default.
        - ``[model_parameters]``: parameter runtime aktif (temperature,
          context_length).

        Jika file tidak ditemukan atau tidak dapat di-parse, ``_models``
        dikosongkan dan ``_parameters`` diatur ke nilai default.

        Tidak melempar exception â€” kegagalan dicatat ke log dan didegradasi
        secara graceful.
        """
        if not self._config_path.exists():
            _logger.warning(
                "Config file tidak ditemukan: '%s'. ModelManager berjalan "
                "tanpa model terdaftar.",
                self._config_path,
            )
            self._models = []
            return

        try:
            with open(self._config_path, "rb") as f:
                config: dict = tomllib.load(f)
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "Gagal mem-parse config.toml '%s': %s",
                self._config_path,
                exc,
            )
            self._models = []
            return

        # Baca daftar [[models]]
        raw_models: list[dict] = config.get("models", [])
        loaded: list[ModelConfig] = []
        for entry in raw_models:
            name = entry.get("name", "")
            model_type = entry.get("model_type", "")
            path_or_url = entry.get("path_or_url", "")
            if not name or not model_type or not path_or_url:
                _logger.warning(
                    "Entri model tidak lengkap dilewati: %s", entry
                )
                continue
            size_bytes: int | None = entry.get("size_bytes")
            loaded.append(
                ModelConfig(
                    name=name,
                    model_type=model_type,
                    path_or_url=path_or_url,
                    size_bytes=size_bytes,
                )
            )
        self._models = loaded

        # Baca [model_parameters]
        params_section: dict = config.get("model_parameters", {})
        temperature: float = float(params_section.get("temperature", 0.7))
        context_length: int = int(params_section.get("context_length", 4096))

        # Clamp nilai ke rentang valid tanpa raise â€” load_config bersifat
        # permisif; validasi ketat hanya di update_parameters().
        temperature = max(TEMPERATURE_MIN, min(TEMPERATURE_MAX, temperature))
        context_length = max(
            CONTEXT_LENGTH_MIN, min(CONTEXT_LENGTH_MAX, context_length)
        )
        self._parameters = ModelParameters(
            temperature=temperature,
            context_length=context_length,
        )

        # Tetapkan model aktif berdasarkan default_model
        default_name: str = config.get("default_model", "")
        if default_name and self._active_model is None:
            # Hanya tetapkan default saat pertama kali memuat config
            # (tidak menimpa model yang sudah aktif karena hot-swap)
            for m in self._models:
                if m.name == default_name:
                    self._active_model = m
                    break

        _logger.info(
            "Config dimuat: %d model terdaftar, model aktif: %s",
            len(self._models),
            self._active_model.name if self._active_model else "tidak ada",
        )

    # ------------------------------------------------------------------
    # list_models() â€” daftar semua model (â‰¤2 detik)
    # ------------------------------------------------------------------

    def list_models(self) -> list[ModelConfig]:
        """Kembalikan semua model yang terdaftar dalam konfigurasi.

        Operasi ini berjalan sinkron dari cache in-memory dan dijamin
        selesai dalam < 1 ms (jauh di bawah batas 2 detik â€” Req 7.3).

        Returns:
            Salinan dangkal daftar ``ModelConfig``. Daftar kosong jika
            tidak ada model yang dikonfigurasi.
        """
        return list(self._models)

    # ------------------------------------------------------------------
    # get_active_model() â€” model yang sedang aktif
    # ------------------------------------------------------------------

    def get_active_model(self) -> ModelConfig | None:
        """Kembalikan ``ModelConfig`` dari model yang sedang aktif.

        Returns:
            ``ModelConfig`` aktif, atau ``None`` jika tidak ada model aktif.
        """
        return self._active_model

    def get_parameters(self) -> ModelParameters:
        """Kembalikan parameter runtime model yang sedang aktif."""
        return self._parameters

    # ------------------------------------------------------------------
    # switch_model() â€” hot-swap model aktif (â‰¤30 detik)
    # ------------------------------------------------------------------

    async def switch_model(self, name: str) -> None:
        """Ganti model aktif ke model dengan ``name``.

        Alur:
        1. Cari model ``name`` dalam daftar terdaftar.
        2. Jika tidak ada â†’ raise :exc:`AgentModelNotFoundError` (E012).
        3. Muat model dalam batas ``MODEL_LOAD_TIMEOUT_SECONDS`` (10 detik).
        4. Jika timeout â†’ raise :exc:`AgentModelLoadTimeoutError` (E013);
           model sebelumnya tetap aktif.
        5. Jika berhasil â†’ perbarui ``_active_model`` dan ``_llm_handle``.

        Args:
            name: Nama model tujuan (harus ada dalam daftar terdaftar).

        Raises:
            AgentModelNotFoundError: Jika model tidak ditemukan (E012).
            AgentModelLoadTimeoutError: Jika pemuatan melebihi 10 detik (E013).
        """
        # Langkah 1: Temukan model dalam registry
        target: ModelConfig | None = None
        for m in self._models:
            if m.name == name:
                target = m
                break

        if target is None:
            raise AgentModelNotFoundError(name)

        # Simpan model dan handle lama untuk rollback
        previous_model = self._active_model
        previous_handle = self._llm_handle

        # Langkah 2: Muat model dengan batas waktu MODEL_LOAD_TIMEOUT_SECONDS
        try:
            new_handle = await asyncio.wait_for(
                self._load_model(target),
                timeout=MODEL_LOAD_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # Rollback ke model sebelumnya
            self._active_model = previous_model
            self._llm_handle = previous_handle
            raise AgentModelLoadTimeoutError(
                model_name=name,
                timeout_seconds=MODEL_LOAD_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            # Error tak terduga â€” rollback dan log
            self._active_model = previous_model
            self._llm_handle = previous_handle
            _logger.error(
                "Gagal memuat model '%s': %s. Model sebelumnya dipertahankan.",
                name,
                exc,
            )
            raise AgentModelLoadTimeoutError(
                model_name=name,
                timeout_seconds=MODEL_LOAD_TIMEOUT_SECONDS,
            )

        # Langkah 3: Perbarui model aktif
        self._active_model = target
        self._llm_handle = new_handle
        _logger.info("Model aktif diganti ke '%s'.", name)

    # ------------------------------------------------------------------
    # generate() â€” streaming token dari model aktif
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        history: list,
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream token dari model aktif satu per satu.

        Mendukung dua jalur:
        - **GGUF** (``model_type == "gguf"``): panggil
          ``llama_cpp.Llama`` secara sinkron di thread pool, streaming
          token lewat ``asyncio.Queue``.
        - **API** (``model_type == "api"``): POST ke endpoint Ollama
          ``/api/generate`` dengan ``stream=True`` menggunakan ``httpx``,
          parsing setiap baris JSON.

        Jika tidak ada model aktif, yield satu string error dan hentikan.

        Args:
            prompt: Teks prompt yang akan dikirim ke model.
            history: Riwayat percakapan (list of dicts atau
                :class:`~agent.models.schemas.InteractionRecord`).
                Format disesuaikan masing-masing backend.
            model_name: Nama model spesifik untuk call ini. Jika None,
                gunakan model aktif. Jika diberikan, gunakan model
                tersebut (untuk model routing).

        Yields:
            String token satu per satu.
        """
        # Tentukan model yang akan digunakan
        model = self._active_model

        if model_name and model_name != (self._active_model.name if self._active_model else ""):
            # Cari model berdasarkan nama
            for m in self._models:
                if m.name == model_name:
                    model = m
                    break
            else:
                yield f"[Warning: Model '{model_name}' tidak ditemukan, menggunakan model aktif]"

        if model is None:
            yield "[Error: Tidak ada model aktif. Gunakan /model use <nama>]"
            return

        if model.model_type == "gguf":
            async for token in self._generate_gguf(prompt, history, model=model):
                yield token
        elif model.model_type == "api":
            async for token in self._generate_api(prompt, history):
                yield token
        else:
            yield f"[Error: model_type tidak dikenal '{model.model_type}']"

    # ------------------------------------------------------------------
    # update_parameters() — validasi dan simpan parameter baru
    # ------------------------------------------------------------------

    def update_parameters(self, params: ModelParameters) -> None:
        """Validasi dan perbarui parameter runtime model.

        Validasi rentang:
        - ``temperature``: 0.0 – 2.0
        - ``context_length``: 128 – 131072

        Setelah validasi berhasil, parameter disimpan ke ``_parameters``
        dan ke ``[model_parameters]`` di ``config.toml``.

        Args:
            params: :class:`ModelParameters` baru yang akan diterapkan.

        Raises:
            AgentModelParameterRangeError: Jika salah satu nilai di luar
                rentang yang valid (E016).
        """
        # Validasi temperature
        if not (TEMPERATURE_MIN <= params.temperature <= TEMPERATURE_MAX):
            raise AgentModelParameterRangeError(
                parameter_name="temperature",
                value=params.temperature,
                min_value=TEMPERATURE_MIN,
                max_value=TEMPERATURE_MAX,
            )

        # Validasi context_length
        if not (CONTEXT_LENGTH_MIN <= params.context_length <= CONTEXT_LENGTH_MAX):
            raise AgentModelParameterRangeError(
                parameter_name="context_length",
                value=params.context_length,
                min_value=CONTEXT_LENGTH_MIN,
                max_value=CONTEXT_LENGTH_MAX,
            )

        self._parameters = params
        self._save_parameters_to_config(params)
        _logger.info(
            "Parameter model diperbarui: temperature=%.2f, context_length=%d",
            params.temperature,
            params.context_length,
        )

    # ------------------------------------------------------------------
    # set_default() — simpan model default ke config.toml
    # ------------------------------------------------------------------

    def set_default(self, name: str) -> None:
        """Simpan model ``name`` sebagai ``default_model`` di ``config.toml``.

        Tidak memvalidasi apakah model tersebut ada dalam daftar — pemanggil
        bertanggung jawab memastikan nama valid sebelum memanggil method ini.

        Args:
            name: Nama model yang akan dijadikan default.
        """
        self._update_config_key("default_model", name)
        _logger.info("Model default disimpan ke config.toml: '%s'.", name)

    # ------------------------------------------------------------------
    # Internal: _load_model()
    # ------------------------------------------------------------------

    async def _load_model(self, model: ModelConfig) -> Any:
        """Muat model ke memori secara asinkron.

        - Untuk GGUF: lazy import ``llama_cpp``, muat di thread pool agar
          tidak memblokir event loop.
        - Untuk API: tidak ada pemuatan sebenarnya — cukup verifikasi
          konektivitas dengan HEAD request ringan (opsional).

        Args:
            model: ``ModelConfig`` yang akan dimuat.

        Returns:
            Handle LLM (instansi ``llama_cpp.Llama`` untuk GGUF,
            ``None`` untuk API).
        """
        if model.model_type == "gguf":
            return await asyncio.get_event_loop().run_in_executor(
                None, self._load_gguf_sync, model
            )
        elif model.model_type == "api":
            # Untuk model API, tidak ada pemuatan model ke memori.
            # Verifikasi URL tersedia (best-effort, gagal diabaikan).
            await self._ping_api_endpoint(model.path_or_url)
            return None
        else:
            _logger.warning(
                "model_type tidak dikenal '%s'; model dianggap dimuat.",
                model.model_type,
            )
            return None

    def _load_gguf_sync(self, model: ModelConfig) -> Any:
        """Muat model GGUF secara sinkron (dijalankan di thread pool)."""
        try:
            import llama_cpp  # noqa: PLC0415 — lazy import by design
        except ImportError:
            _logger.warning(
                "llama-cpp-python tidak terinstal. Model GGUF '%s' tidak "
                "dapat dimuat. Pasang dengan: pip install llama-cpp-python",
                model.name,
            )
            return None

        model_path = model.path_or_url
        _logger.info("Memuat model GGUF dari '%s' ...", model_path)

        try:
            import os
            cpu_threads = max(2, min(4, (os.cpu_count() or 4) // 2))
            llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=self._parameters.context_length,
                n_gpu_layers=-1,
                n_threads=cpu_threads,
                n_batch=512,
                verbose=False,
            )
            _logger.info("Model GGUF '%s' berhasil dimuat.", model.name)
            return llm
        except Exception as exc:
            _logger.warning("Gagal memuat dengan GPU (-1), mencoba di CPU: %s", exc)
            try:
                llm = llama_cpp.Llama(
                    model_path=model_path,
                    n_ctx=self._parameters.context_length,
                    n_gpu_layers=0,
                    n_threads=cpu_threads,
                    n_batch=512,
                    verbose=False,
                )
                return llm
            except Exception as e2:
                _logger.error("Gagal memuat model GGUF: %s", e2)
                return None

    async def _ping_api_endpoint(self, base_url: str) -> None:
        """Verifikasi API endpoint dapat dijangkau (best-effort)."""
        try:
            import httpx  # noqa: PLC0415
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(base_url)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Internal: _generate_gguf()
    # ------------------------------------------------------------------

    async def _generate_gguf(
        self,
        prompt: str,
        history: list,
        model: ModelConfig | None = None,
    ) -> AsyncIterator[str]:
        """Stream token dari model GGUF via llama-cpp-python."""
        target_model = model or self._active_model
        if self._llm_handle is None and target_model and target_model.model_type == "gguf":
            yield f"[Memuat model GGUF '{target_model.name}' ke memori...]\n"
            self._llm_handle = await self._load_model(target_model)
            if self._llm_handle:
                yield f"[Model GGUF '{target_model.name}' siap!]\n\n"

        if self._llm_handle is None:
            yield "[Error: Model GGUF belum dimuat. Pastikan file model .gguf ada dan valid.]"
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        # Batasi output generasi per langkah agar tidak melebihi konteks
        gen_max_tokens = min(1024, max(256, self._parameters.context_length // 2))

        def _run_inference() -> None:
            """Jalankan inferensi GGUF dan masukkan token ke queue."""
            try:
                generator = self._llm_handle(
                    prompt,
                    max_tokens=300,
                    temperature=self._parameters.temperature,
                    stop=["<|im_end|>", "<|endoftext|>"],
                    stream=True,)
                for chunk in generator:
                    token_text: str = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                        or chunk.get("choices", [{}])[0]
                        .get("text", "")
                    )
                    if token_text:
                        loop.call_soon_threadsafe(queue.put_nowait, token_text)
            except Exception as exc:  # noqa: BLE001
                error_msg = f"[Error GGUF: {exc}]"
                loop.call_soon_threadsafe(queue.put_nowait, error_msg)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        # Jalankan inference di background thread pool
        loop.run_in_executor(None, _run_inference)

        # Yield token dari queue
        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

    # ------------------------------------------------------------------
    # Internal: _generate_api()
    # ------------------------------------------------------------------

    async def _generate_api(
        self,
        prompt: str,
        history: list,
    ) -> AsyncIterator[str]:
        """Stream token dari model API (Ollama) menggunakan /api/chat dengan system prompt tools."""
        import json as json_module  # noqa: PLC0415

        try:
            import httpx  # noqa: PLC0415
        except ImportError:
            yield "[Error: httpx tidak terinstall]"
            return

        if self._active_model is None:
            yield "[Error: Tidak ada model aktif.]"
            return

        base_url = self._active_model.path_or_url.rstrip("/")
        model_name = self._active_model.name

        from datetime import datetime
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        from agent.core.prompting import TOOL_CALL_INSTRUCTIONS

        system_prompt = f"""Waktu/Tanggal saat ini: {current_date_str}.
{TOOL_CALL_INSTRUCTIONS}"""

        # Bangun messages untuk /api/chat
        messages = [{"role": "system", "content": system_prompt}]

        # Tambah history percakapan
        from agent.models.schemas import InteractionRecord
        for record in history[-10:]:  # maks 10 terakhir
            if isinstance(record, InteractionRecord):
                messages.append({"role": "user", "content": record.instruction})
                messages.append({"role": "assistant", "content": record.response})

        # Tambah instruksi saat ini
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self._parameters.temperature,
                "num_ctx": self._parameters.context_length,
            },
        }

        url = f"{base_url}/api/chat"
        api_timeout = httpx.Timeout(180.0, connect=60.0)

        try:
            async with httpx.AsyncClient(timeout=api_timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json_module.loads(line)
                        except json_module.JSONDecodeError:
                            continue

                        # /api/chat response format
                        token: str = data.get("message", {}).get("content", "")
                        if token:
                            yield token

                        if data.get("done", False):
                            break

        except httpx.TimeoutException:
            yield f"[Error: timeout setelah {api_timeout.connect}s connect / {api_timeout.read}s read]"
        except httpx.HTTPStatusError as exc:
            yield f"[Error: HTTP {exc.response.status_code}]"
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception as exc:  # noqa: BLE001
            yield f"[Error API: {exc}]"

    # ------------------------------------------------------------------
    # Internal: _save_parameters_to_config()
    # ------------------------------------------------------------------

    def _save_parameters_to_config(self, params: ModelParameters) -> None:
        """Simpan parameter ke ``[model_parameters]`` di ``config.toml``.

        Membaca file saat ini, memperbarui hanya section ``model_parameters``,
        dan menulis kembali menggunakan ``tomli_w``.

        Args:
            params: Parameter yang akan disimpan.
        """
        self._update_config_section("model_parameters", {
            "temperature": params.temperature,
            "context_length": params.context_length,
        })

    def _update_config_key(self, key: str, value: Any) -> None:
        """Perbarui satu key di root ``config.toml``.

        Args:
            key: Nama key.
            value: Nilai baru.
        """
        config = self._read_raw_config()
        config[key] = value
        self._write_raw_config(config)

    def _update_config_section(self, section: str, values: dict) -> None:
        """Perbarui atau buat section di ``config.toml``.

        Args:
            section: Nama section (mis. ``"model_parameters"``).
            values: Dict nilai baru untuk section tersebut.
        """
        config = self._read_raw_config()
        existing = config.get(section, {})
        existing.update(values)
        config[section] = existing
        self._write_raw_config(config)

    def _read_raw_config(self) -> dict:
        """Baca ``config.toml`` sebagai dict mentah.

        Returns:
            Dict konfigurasi, atau dict kosong jika file tidak ada.
        """
        if not self._config_path.exists():
            return {}
        try:
            with open(self._config_path, "rb") as f:
                return tomllib.load(f)
        except Exception as exc:  # noqa: BLE001
            _logger.error("Gagal membaca config.toml: %s", exc)
            return {}

    def _write_raw_config(self, config: dict) -> None:
        """Tulis dict konfigurasi ke ``config.toml`` menggunakan tomli_w.

        Args:
            config: Dict konfigurasi yang akan ditulis.
        """
        try:
            with open(self._config_path, "wb") as f:
                tomli_w.dump(config, f)
        except Exception as exc:  # noqa: BLE001
            _logger.error("Gagal menulis config.toml: %s", exc)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "MAX_GGUF_SIZE_BYTES",
    "MODEL_LOAD_TIMEOUT_SECONDS",
    "MODEL_SWITCH_TIMEOUT_SECONDS",
    "ModelConfig",
    "ModelParameters",
    "ModelManager",
]
