"""
tests/unit/test_model_manager.py

Unit tests untuk ModelManager, ModelConfig, dan ModelParameters.

Memverifikasi perilaku:
- list_models() dari config yang valid dan kosong
- switch_model() ke model yang ada dan yang tidak ada
- update_parameters() dengan nilai valid, terlalu kecil, dan terlalu besar
- set_default() menyimpan ke config.toml
- load_config() membaca ulang config.toml
- Agent tetap berjalan saat model gagal dimuat (E013)

Requirements yang diuji: 7.3, 7.4, 7.5, 7.6, 7.7, 8.5, 8.6
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tomllib
import tomli_w

from agent.core.exceptions import (
    AgentModelLoadTimeoutError,
    AgentModelNotFoundError,
    AgentModelParameterRangeError,
)
from agent.models.manager import (
    MODEL_LOAD_TIMEOUT_SECONDS,
    ModelConfig,
    ModelManager,
    ModelParameters,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _write_config(path: Path, content: str) -> None:
    """Tulis konten string ke path sebagai config.toml (UTF-8)."""
    path.write_text(content, encoding="utf-8")


def _make_config_with_models(tmp_path: Path, models: list[dict]) -> Path:
    """Buat config.toml dengan satu atau lebih [[models]] entry."""
    config_path = tmp_path / "config.toml"
    lines = ['default_model = ""\n']
    for m in models:
        lines.append("[[models]]\n")
        lines.append(f'name = "{m["name"]}"\n')
        lines.append(f'model_type = "{m["model_type"]}"\n')
        lines.append(f'path_or_url = "{m["path_or_url"]}"\n')
        if "size_bytes" in m:
            lines.append(f'size_bytes = {m["size_bytes"]}\n')
    lines.append("\n[model_parameters]\n")
    lines.append("temperature = 0.7\n")
    lines.append("context_length = 4096\n")
    config_path.write_text("".join(lines), encoding="utf-8")
    return config_path


@pytest.fixture
def config_no_models(tmp_path: Path) -> Path:
    """Config.toml tanpa [[models]] entries."""
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        'default_model = ""\n'
        "tool_directories = []\n"
        "sandbox_enabled = false\n"
        "\n"
        "[model_parameters]\n"
        "temperature = 0.5\n"
        "context_length = 2048\n",
    )
    return config_path


@pytest.fixture
def config_two_models(tmp_path: Path) -> Path:
    """Config.toml dengan dua model: satu GGUF, satu API."""
    return _make_config_with_models(
        tmp_path,
        [
            {
                "name": "local-llama",
                "model_type": "gguf",
                "path_or_url": "/models/llama.gguf",
                "size_bytes": 4000000000,
            },
            {
                "name": "ollama-api",
                "model_type": "api",
                "path_or_url": "http://localhost:11434",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Tests: load_config() dan inisialisasi
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_config_reads_models(self, config_two_models: Path):
        """load_config() membaca dua model dari config.toml."""
        mm = ModelManager(str(config_two_models))
        models = mm.list_models()
        assert len(models) == 2

    def test_load_config_no_models_returns_empty(self, config_no_models: Path):
        """list_models() mengembalikan [] jika tidak ada [[models]] entries."""
        mm = ModelManager(str(config_no_models))
        assert mm.list_models() == []

    def test_load_config_missing_file_graceful(self, tmp_path: Path):
        """ModelManager tidak crash jika config.toml tidak ditemukan."""
        missing = tmp_path / "nonexistent_config.toml"
        mm = ModelManager(str(missing))
        assert mm.list_models() == []
        assert mm.get_active_model() is None

    def test_load_config_sets_default_model(self, tmp_path: Path):
        """default_model di config.toml menjadi model aktif awal."""
        config_path = tmp_path / "config.toml"
        _write_config(
            config_path,
            'default_model = "ollama-api"\n'
            "[[models]]\n"
            'name = "ollama-api"\n'
            'model_type = "api"\n'
            'path_or_url = "http://localhost:11434"\n'
            "\n"
            "[model_parameters]\n"
            "temperature = 0.7\n"
            "context_length = 4096\n",
        )
        mm = ModelManager(str(config_path))
        active = mm.get_active_model()
        assert active is not None
        assert active.name == "ollama-api"

    def test_load_config_reads_parameters(self, tmp_path: Path):
        """load_config() membaca temperature dan context_length dari config."""
        config_path = tmp_path / "config.toml"
        _write_config(
            config_path,
            'default_model = ""\n'
            "\n"
            "[model_parameters]\n"
            "temperature = 1.5\n"
            "context_length = 8192\n",
        )
        mm = ModelManager(str(config_path))
        # Akses parameter melalui update dan baca kembali (tidak ada getter publik)
        # Verifikasi tidak crash; parameter tersimpan internal
        assert mm._parameters.temperature == 1.5
        assert mm._parameters.context_length == 8192

    def test_reload_config_picks_new_models(self, tmp_path: Path):
        """load_config() ulang membaca model baru yang ditambahkan ke file."""
        config_path = tmp_path / "config.toml"
        _write_config(
            config_path,
            'default_model = ""\n'
            "\n"
            "[model_parameters]\n"
            "temperature = 0.7\n"
            "context_length = 4096\n",
        )
        mm = ModelManager(str(config_path))
        assert mm.list_models() == []

        # Tambahkan model ke file dan muat ulang
        _write_config(
            config_path,
            'default_model = "new-model"\n'
            "[[models]]\n"
            'name = "new-model"\n'
            'model_type = "api"\n'
            'path_or_url = "http://localhost:11434"\n'
            "\n"
            "[model_parameters]\n"
            "temperature = 0.7\n"
            "context_length = 4096\n",
        )
        mm.load_config()
        assert len(mm.list_models()) == 1
        assert mm.list_models()[0].name == "new-model"

    def test_load_config_skips_incomplete_model_entries(self, tmp_path: Path):
        """Entry model tanpa name/model_type/path_or_url dilewati."""
        config_path = tmp_path / "config.toml"
        _write_config(
            config_path,
            'default_model = ""\n'
            "[[models]]\n"
            'name = ""\n'              # nama kosong
            'model_type = "api"\n'
            'path_or_url = "http://localhost:11434"\n'
            "\n"
            "[model_parameters]\n"
            "temperature = 0.7\n"
            "context_length = 4096\n",
        )
        mm = ModelManager(str(config_path))
        assert mm.list_models() == []


# ---------------------------------------------------------------------------
# Tests: list_models() — Requirement 7.3
# ---------------------------------------------------------------------------


class TestListModels:
    def test_list_models_returns_all_registered(self, config_two_models: Path):
        """list_models() mengembalikan semua model terdaftar."""
        mm = ModelManager(str(config_two_models))
        models = mm.list_models()
        names = {m.name for m in models}
        assert names == {"local-llama", "ollama-api"}

    def test_list_models_returns_copy(self, config_two_models: Path):
        """list_models() mengembalikan salinan — modifikasi tidak merusak state."""
        mm = ModelManager(str(config_two_models))
        models = mm.list_models()
        models.clear()
        assert len(mm.list_models()) == 2

    def test_list_models_model_type_preserved(self, config_two_models: Path):
        """model_type tiap model terbaca dengan benar."""
        mm = ModelManager(str(config_two_models))
        by_name = {m.name: m for m in mm.list_models()}
        assert by_name["local-llama"].model_type == "gguf"
        assert by_name["ollama-api"].model_type == "api"

    def test_list_models_size_bytes_preserved(self, config_two_models: Path):
        """size_bytes terbaca jika ada di config."""
        mm = ModelManager(str(config_two_models))
        by_name = {m.name: m for m in mm.list_models()}
        assert by_name["local-llama"].size_bytes == 4000000000
        assert by_name["ollama-api"].size_bytes is None


# ---------------------------------------------------------------------------
# Tests: switch_model() — Requirements 7.4, 7.5, 7.7
# ---------------------------------------------------------------------------


class TestSwitchModel:
    @pytest.mark.asyncio
    async def test_switch_to_existing_api_model(self, config_two_models: Path):
        """switch_model() berhasil ke model API yang terdaftar."""
        mm = ModelManager(str(config_two_models))

        # Patch _load_model agar tidak perlu koneksi jaringan nyata
        with patch.object(mm, "_load_model", new_callable=AsyncMock, return_value=None):
            await mm.switch_model("ollama-api")

        assert mm.get_active_model() is not None
        assert mm.get_active_model().name == "ollama-api"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_switch_to_nonexistent_raises_model_not_found(
        self, config_two_models: Path
    ):
        """switch_model() ke nama yang tidak ada → AgentModelNotFoundError (E012)."""
        mm = ModelManager(str(config_two_models))
        with pytest.raises(AgentModelNotFoundError) as exc_info:
            await mm.switch_model("nonexistent-model")
        assert exc_info.value.error_code == "E012"
        assert "nonexistent-model" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_switch_preserves_old_model_on_not_found(
        self, config_two_models: Path
    ):
        """Model aktif lama dipertahankan saat switch_model gagal (E012)."""
        mm = ModelManager(str(config_two_models))
        # Set model aktif awal via mock
        with patch.object(mm, "_load_model", new_callable=AsyncMock, return_value=None):
            await mm.switch_model("ollama-api")

        previous = mm.get_active_model()

        with pytest.raises(AgentModelNotFoundError):
            await mm.switch_model("ghost-model")

        assert mm.get_active_model() is previous

    @pytest.mark.asyncio
    async def test_switch_model_timeout_raises_load_timeout_error(
        self, config_two_models: Path
    ):
        """switch_model() timeout saat muat → AgentModelLoadTimeoutError (E013)."""
        mm = ModelManager(str(config_two_models))

        # Simulasikan pemuatan yang tidak pernah selesai
        async def _never_finish(_model: ModelConfig) -> None:
            await asyncio.sleep(9999)

        with patch.object(mm, "_load_model", side_effect=_never_finish):
            # Kurangi timeout agar test cepat
            with patch("agent.models.manager.MODEL_LOAD_TIMEOUT_SECONDS", 0.05):
                with pytest.raises(AgentModelLoadTimeoutError) as exc_info:
                    await mm.switch_model("ollama-api")

        assert exc_info.value.error_code == "E013"
        assert "ollama-api" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_switch_model_timeout_preserves_old_active_model(
        self, config_two_models: Path
    ):
        """Model aktif lama dipertahankan jika pemuatan model baru timeout (Req 7.7)."""
        mm = ModelManager(str(config_two_models))

        # Set model aktif awal
        with patch.object(mm, "_load_model", new_callable=AsyncMock, return_value=None):
            await mm.switch_model("ollama-api")

        previous_model = mm.get_active_model()

        async def _slow_load(_model: ModelConfig) -> None:
            await asyncio.sleep(9999)

        with patch.object(mm, "_load_model", side_effect=_slow_load):
            with patch("agent.models.manager.MODEL_LOAD_TIMEOUT_SECONDS", 0.05):
                with pytest.raises(AgentModelLoadTimeoutError):
                    await mm.switch_model("local-llama")

        # Model aktif harus tetap "ollama-api"
        assert mm.get_active_model() is previous_model

    @pytest.mark.asyncio
    async def test_switch_model_updates_llm_handle(self, config_two_models: Path):
        """Setelah switch berhasil, _llm_handle diperbarui."""
        mm = ModelManager(str(config_two_models))
        fake_handle = object()

        with patch.object(mm, "_load_model", new_callable=AsyncMock, return_value=fake_handle):
            await mm.switch_model("ollama-api")

        assert mm._llm_handle is fake_handle


# ---------------------------------------------------------------------------
# Tests: update_parameters() — Requirements 8.5, 8.6
# ---------------------------------------------------------------------------


class TestUpdateParameters:
    def test_valid_parameters_accepted(self, config_no_models: Path):
        """update_parameters() dengan nilai valid tidak raise exception."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=1.0, context_length=2048)
        mm.update_parameters(params)  # tidak raise
        assert mm._parameters.temperature == 1.0
        assert mm._parameters.context_length == 2048

    def test_temperature_boundary_low(self, config_no_models: Path):
        """temperature = 0.0 adalah nilai minimum yang valid."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=0.0, context_length=512)
        mm.update_parameters(params)
        assert mm._parameters.temperature == 0.0

    def test_temperature_boundary_high(self, config_no_models: Path):
        """temperature = 2.0 adalah nilai maksimum yang valid."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=2.0, context_length=512)
        mm.update_parameters(params)
        assert mm._parameters.temperature == 2.0

    def test_context_length_boundary_low(self, config_no_models: Path):
        """context_length = 128 adalah nilai minimum yang valid."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=0.5, context_length=128)
        mm.update_parameters(params)
        assert mm._parameters.context_length == 128

    def test_context_length_boundary_high(self, config_no_models: Path):
        """context_length = 131072 adalah nilai maksimum yang valid."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=0.5, context_length=131072)
        mm.update_parameters(params)
        assert mm._parameters.context_length == 131072

    def test_temperature_too_low_raises_parameter_range_error(
        self, config_no_models: Path
    ):
        """temperature < 0.0 → AgentModelParameterRangeError (E016)."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=-0.1, context_length=512)
        with pytest.raises(AgentModelParameterRangeError) as exc_info:
            mm.update_parameters(params)
        err = exc_info.value
        assert err.error_code == "E016"
        assert err.parameter_name == "temperature"
        assert err.value == -0.1

    def test_temperature_too_high_raises_parameter_range_error(
        self, config_no_models: Path
    ):
        """temperature > 2.0 → AgentModelParameterRangeError (E016)."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=2.01, context_length=512)
        with pytest.raises(AgentModelParameterRangeError) as exc_info:
            mm.update_parameters(params)
        assert exc_info.value.parameter_name == "temperature"
        assert exc_info.value.value == 2.01

    def test_context_length_too_low_raises_parameter_range_error(
        self, config_no_models: Path
    ):
        """context_length < 128 → AgentModelParameterRangeError (E016)."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=0.5, context_length=64)
        with pytest.raises(AgentModelParameterRangeError) as exc_info:
            mm.update_parameters(params)
        err = exc_info.value
        assert err.error_code == "E016"
        assert err.parameter_name == "context_length"
        assert err.value == 64

    def test_context_length_too_high_raises_parameter_range_error(
        self, config_no_models: Path
    ):
        """context_length > 131072 → AgentModelParameterRangeError (E016)."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=0.5, context_length=200000)
        with pytest.raises(AgentModelParameterRangeError) as exc_info:
            mm.update_parameters(params)
        assert exc_info.value.parameter_name == "context_length"

    def test_invalid_temperature_does_not_update_parameters(
        self, config_no_models: Path
    ):
        """Jika validasi gagal, _parameters tidak berubah."""
        mm = ModelManager(str(config_no_models))
        original_temperature = mm._parameters.temperature

        with pytest.raises(AgentModelParameterRangeError):
            mm.update_parameters(ModelParameters(temperature=3.0, context_length=512))

        assert mm._parameters.temperature == original_temperature

    def test_update_parameters_saves_to_config(self, config_no_models: Path):
        """update_parameters() menyimpan nilai baru ke config.toml."""
        mm = ModelManager(str(config_no_models))
        params = ModelParameters(temperature=1.2, context_length=8192)
        mm.update_parameters(params)

        # Baca ulang file untuk verifikasi
        with open(config_no_models, "rb") as f:
            saved = tomllib.load(f)

        assert saved["model_parameters"]["temperature"] == 1.2
        assert saved["model_parameters"]["context_length"] == 8192


# ---------------------------------------------------------------------------
# Tests: set_default() — Requirement 7.6
# ---------------------------------------------------------------------------


class TestSetDefault:
    def test_set_default_saves_to_config_toml(self, config_two_models: Path):
        """set_default() menyimpan nama model ke 'default_model' di config.toml."""
        mm = ModelManager(str(config_two_models))
        mm.set_default("ollama-api")

        with open(config_two_models, "rb") as f:
            saved = tomllib.load(f)

        assert saved["default_model"] == "ollama-api"

    def test_set_default_updates_value_after_change(self, config_two_models: Path):
        """set_default() dapat mengubah default_model yang sudah ada."""
        mm = ModelManager(str(config_two_models))
        mm.set_default("local-llama")
        mm.set_default("ollama-api")

        with open(config_two_models, "rb") as f:
            saved = tomllib.load(f)

        assert saved["default_model"] == "ollama-api"

    def test_set_default_does_not_affect_models_list(self, config_two_models: Path):
        """set_default() tidak mengubah daftar [[models]] di config.toml."""
        mm = ModelManager(str(config_two_models))
        mm.set_default("ollama-api")

        with open(config_two_models, "rb") as f:
            saved = tomllib.load(f)

        assert len(saved.get("models", [])) == 2


# ---------------------------------------------------------------------------
# Tests: ModelConfig dataclass
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_model_config_defaults(self):
        """size_bytes default ke None jika tidak disertakan."""
        m = ModelConfig(
            name="test",
            model_type="api",
            path_or_url="http://localhost:11434",
        )
        assert m.size_bytes is None

    def test_model_config_with_size(self):
        """ModelConfig menyimpan size_bytes dengan benar."""
        m = ModelConfig(
            name="big-model",
            model_type="gguf",
            path_or_url="/models/big.gguf",
            size_bytes=10_000_000_000,
        )
        assert m.size_bytes == 10_000_000_000


# ---------------------------------------------------------------------------
# Tests: ModelParameters dataclass
# ---------------------------------------------------------------------------


class TestModelParameters:
    def test_model_parameters_stores_values(self):
        """ModelParameters menyimpan temperature dan context_length."""
        p = ModelParameters(temperature=0.8, context_length=4096)
        assert p.temperature == 0.8
        assert p.context_length == 4096


# ---------------------------------------------------------------------------
# Tests: get_active_model()
# ---------------------------------------------------------------------------


class TestGetActiveModel:
    def test_get_active_model_none_when_no_default(self, config_no_models: Path):
        """get_active_model() mengembalikan None jika tidak ada model aktif."""
        mm = ModelManager(str(config_no_models))
        assert mm.get_active_model() is None

    @pytest.mark.asyncio
    async def test_get_active_model_returns_switched_model(
        self, config_two_models: Path
    ):
        """get_active_model() mengembalikan model yang dipilih via switch_model()."""
        mm = ModelManager(str(config_two_models))
        with patch.object(mm, "_load_model", new_callable=AsyncMock, return_value=None):
            await mm.switch_model("local-llama")
        active = mm.get_active_model()
        assert active is not None
        assert active.name == "local-llama"
