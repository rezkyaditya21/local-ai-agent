"""
agent/main.py

Entrypoint utama Local AI Agent.

Fungsi `create_app` menginisialisasi semua komponen dalam urutan yang benar:
    CredentialVault
    → AuditLogger
    → Blocklist
    → ToolRegistry
    → ConfirmationGate
    → semua built-in tools (didaftarkan ke registry)
    → ModelManager
    → Executor
    → SelfImprovementModule
    → Agent
    → CLI

Fungsi `main` mem-parse argumen CLI, memanggil `create_app`, dan menjalankan
loop REPL. Ctrl+C (SIGINT) ditangani dengan memanggil `agent.stop()` secara
graceful dalam ≤3 detik sebelum keluar.

Requirements yang diimplementasikan: 1.4, 1.5, 1.7, 7.6
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Setup logging dasar (sebelum import modul lain)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Imports semua komponen
# ---------------------------------------------------------------------------

from agent.cli.interface import CLI, CLIConfig
from agent.core.audit_logger import AuditLogger
from agent.core.blocklist import Blocklist
from agent.core.budget import ExecutionBudget
from agent.core.confirmation_gate import ConfirmationGate
from agent.core.credential_vault import CredentialVault
from agent.core.executor import Executor
from agent.core.orchestrator import Agent
from agent.core.scheduler import TaskScheduler
from agent.gateway.telegram_gateway import TelegramGateway
from agent.models.manager import ModelManager
from agent.self_improvement.backup_manager import BackupManager
from agent.self_improvement.module import SelfImprovementModule
from agent.skills.manager import SkillManager
from agent.tools import (
    BenchmarkTool,
    BrowserTool,
    CodeSearchTool,
    DatabaseTool,
    FileSystemTool,
    GitTool,
    HTTPAPITool,
    PluginLoader,
    ProjectInspectTool,
    PythonExecTool,
    ShellTool,
    SystemInspectTool,
    TestRunnerTool,
    ToolRegistry,
    WebSearchTool,
)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_FILENAME = "config.toml"
_DEFAULT_LOG_FILENAME = "audit.log"
_DEFAULT_VAULT_DIR = Path.home() / ".config" / "local-ai-agent"
_DEFAULT_BACKUP_DIR = Path.home() / ".config" / "local-ai-agent" / "backups"

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# create_app
# ---------------------------------------------------------------------------


def create_app(
    config_path: str,
    model: str | None,
    blocklist_path: str | None,
) -> tuple["CLI", "Agent"]:
    """Inisialisasi dan wiring semua komponen Agent.

    Urutan inisialisasi (dari bawah ke atas):
    1.  CredentialVault
    2.  AuditLogger
    3.  Blocklist
    4.  ToolRegistry
    5.  ConfirmationGate
    6.  Built-in tools (FileSystem, Shell, HTTP API, Database, Browser)
        — didaftarkan ke ToolRegistry
    7.  ModelManager
    8.  Executor
    9.  SelfImprovementModule + BackupManager
    10. Agent Orchestrator
    11. CLI

    Args:
        config_path:    Path ke file ``config.toml``.
        model:          Nama model awal (dari flag ``--model``). Jika ``None``,
                        menggunakan ``default_model`` dari konfigurasi.
        blocklist_path: Path opsional ke file blocklist.

    Returns:
        Tuple ``(cli, agent)`` yang siap dijalankan.
    """
    resolved_config = Path(config_path).resolve()

    # ------------------------------------------------------------------ #
    # 1. CredentialVault — enkripsi API key & credential
    # ------------------------------------------------------------------ #
    vault = CredentialVault(vault_path=_DEFAULT_VAULT_DIR)

    # ------------------------------------------------------------------ #
    # 2. AuditLogger — pencatat semua tindakan ke file log
    # ------------------------------------------------------------------ #
    # Baca log_path dari config jika ada; fallback ke cwd/audit.log
    log_path = _read_log_path_from_config(resolved_config)
    audit_logger = AuditLogger(log_path=Path(log_path))

    # ------------------------------------------------------------------ #
    # 3. Blocklist — daftar larangan path/command/domain
    # ------------------------------------------------------------------ #
    blocklist = Blocklist(blocklist_path=blocklist_path)

    # ------------------------------------------------------------------ #
    # 4. ToolRegistry
    # ------------------------------------------------------------------ #
    registry = ToolRegistry()

    # ------------------------------------------------------------------ #
    # 5. ConfirmationGate — meminta konfirmasi pengguna untuk operasi berisiko
    # ------------------------------------------------------------------ #
    confirmation_gate = ConfirmationGate()

    # ------------------------------------------------------------------ #
    # 6. Daftarkan semua built-in tools ke registry
    # ------------------------------------------------------------------ #
    _register_builtin_tools(registry, vault)

    # ------------------------------------------------------------------ #
    # 7. ModelManager — memuat & mengelola model AI
    # ------------------------------------------------------------------ #
    model_manager = ModelManager(config_path=str(resolved_config))

    # Jika flag --model diberikan, switch ke model tersebut setelah startup
    # (dilakukan di main() secara async)
    _initial_model = model  # simpan untuk digunakan di main()

    # ------------------------------------------------------------------ #
    # 8. ExecutionBudget — dari config [execution_budget]
    # ------------------------------------------------------------------ #
    budget = ExecutionBudget.from_config(_read_config_dict(resolved_config))

    # ------------------------------------------------------------------ #
    # 9. Executor — menjalankan tool calls dengan pemeriksaan keamanan
    # ------------------------------------------------------------------ #
    executor = Executor(
        registry=registry,
        confirmation_gate=confirmation_gate,
        blocklist=blocklist,
        audit_logger=audit_logger,
    )

    # ------------------------------------------------------------------ #
    # 10. SelfImprovementModule + BackupManager
    # ------------------------------------------------------------------ #
    backup_manager = BackupManager(backup_dir=_DEFAULT_BACKUP_DIR)
    sim = SelfImprovementModule(
        config_path=resolved_config,
        registry=registry,
        confirmation_gate=confirmation_gate,
        backup_manager=backup_manager,
    )

    # ------------------------------------------------------------------ #
    # 10. Skills Manager & Autonomous Skill Creator
    # ------------------------------------------------------------------ #
    skills_cfg = parsed_config.get("skills", {})
    skill_dirs = [Path(d) for d in skills_cfg.get("directories", ["./skills"])]
    skill_manager = SkillManager(skill_dirs=skill_dirs)

    # ------------------------------------------------------------------ #
    # 11. Agent Orchestrator
    # ------------------------------------------------------------------ #
    agent = Agent(
        model_manager=model_manager,
        executor=executor,
        confirmation_gate=confirmation_gate,
        audit_logger=audit_logger,
        blocklist=blocklist,
        budget=budget,
        skill_manager=skill_manager,
    )

    # ------------------------------------------------------------------ #
    # 12. Task Scheduler & Background Automations
    # ------------------------------------------------------------------ #
    scheduler = TaskScheduler(task_executor=lambda goal: agent.process(goal))

    # ------------------------------------------------------------------ #
    # 13. Telegram Gateway
    # ------------------------------------------------------------------ #
    tg_cfg = parsed_config.get("gateway", {}).get("telegram", {})
    tg_token = tg_cfg.get("token", "")
    tg_allowed = tg_cfg.get("allowed_user_ids", [])
    gateway = None
    if tg_cfg.get("enabled", False) and tg_token and not tg_token.startswith("YOUR_"):
        gateway = TelegramGateway(
            token=tg_token,
            allowed_user_ids=tg_allowed,
            agent_processor=agent.process,
        )

    # ------------------------------------------------------------------ #
    # 14. CLI
    # ------------------------------------------------------------------ #
    cli_config = CLIConfig(model=model, history_limit=1000)
    cli = CLI(
        config=cli_config,
        agent=agent,
        model_manager=model_manager,
        registry=registry,
        self_improvement_module=sim,
        scheduler=scheduler,
        gateway=gateway,
    )

    return cli, agent


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse argumen CLI, inisialisasi komponen, dan jalankan REPL loop.

    Argumen yang didukung:
    - ``--model <nama>``      — nama model yang akan digunakan (opsional)
    - ``--config <path>``     — path ke config.toml (default: config.toml di cwd)
    - ``--blocklist <path>``  — path ke file blocklist (opsional)

    Ctrl+C (SIGINT) ditangani dengan:
    1. Memanggil ``agent.stop()`` untuk menghentikan operasi yang berjalan.
    2. Keluar bersih dalam ≤3 detik.
    """
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Local AI Agent — agen AI berbasis terminal yang berjalan sepenuhnya lokal.",
    )
    parser.add_argument(
        "--model",
        metavar="<nama-model>",
        default=None,
        help="Nama model yang akan digunakan pada sesi ini (opsional).",
    )
    parser.add_argument(
        "--config",
        metavar="<path>",
        default=str(Path.cwd() / _DEFAULT_CONFIG_FILENAME),
        help=f"Path ke file konfigurasi config.toml (default: ./{_DEFAULT_CONFIG_FILENAME}).",
    )
    parser.add_argument(
        "--blocklist",
        metavar="<path>",
        default=None,
        help="Path ke file blocklist (opsional).",
    )

    args = parser.parse_args()

    # Validasi keberadaan file config
    config_path = Path(args.config)
    if not config_path.exists():
        # Buat config.toml minimal jika tidak ada agar agent tetap bisa berjalan
        _create_minimal_config(config_path)

    # Inisialisasi semua komponen
    try:
        cli, agent = create_app(
            config_path=str(config_path),
            model=args.model,
            blocklist_path=args.blocklist,
        )
    except Exception as exc:
        print(f"[ERROR] Gagal menginisialisasi Agent: {exc}", file=sys.stderr)
        sys.exit(1)

    # Jalankan event loop asyncio
    asyncio.run(_run_async(cli, agent, initial_model=args.model))


# ---------------------------------------------------------------------------
# _run_async — inti async: switch model + jalankan CLI
# ---------------------------------------------------------------------------


async def _run_async(cli: "CLI", agent: "Agent", initial_model: str | None) -> None:
    """Coroutine utama yang menjalankan Agent secara async.

    1. Jika ``initial_model`` diberikan, switch model sebelum REPL dimulai.
    2. Setup SIGINT handler untuk penghentian graceful.
    3. Jalankan ``cli.run()`` (blocking REPL).
    4. Cleanup saat selesai.
    """
    loop = asyncio.get_event_loop()

    # ---- start background scheduler & gateway ----
    scheduler = getattr(cli, "_scheduler", None)
    if scheduler:
        scheduler.start()

    gateway = getattr(cli, "_gateway", None)
    if gateway:
        gateway.start()

    # ---- setup SIGINT (Ctrl+C) ----
    def _sigint_handler() -> None:
        """Handle Ctrl+C: set flag berhenti dan panggil agent.stop()."""
        _logger.info("SIGINT diterima — menghentikan Agent.")
        asyncio.create_task(_graceful_stop(cli, agent))

    if sys.platform != "win32":
        try:
            loop.add_signal_handler(signal.SIGINT, _sigint_handler)
        except (NotImplementedError, RuntimeError):
            pass

    # ---- switch model awal jika diminta (Req 1.4) ----
    if initial_model is not None:
        try:
            from agent.core.exceptions import (
                AgentModelNotFoundError,
                AgentModelLoadTimeoutError,
            )
            await agent._model_manager.switch_model(initial_model)
        except AgentModelNotFoundError as exc:
            print(f"[WARNING] {exc}", file=sys.stderr)
        except AgentModelLoadTimeoutError as exc:
            print(f"[WARNING] {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[WARNING] Gagal memuat model '{initial_model}': {exc}", file=sys.stderr)

    # ---- jalankan REPL ----
    try:
        await cli.run()
    except KeyboardInterrupt:
        await _graceful_stop(cli, agent)
    finally:
        # Cleanup
        if scheduler:
            scheduler.stop()
        if gateway:
            gateway.stop()
        if sys.platform != "win32":
            try:
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, RuntimeError):
                pass


async def _graceful_stop(cli: "CLI", agent: "Agent") -> None:
    """Hentikan Agent dan CLI secara graceful dalam ≤3 detik (Req 1.7, 10.3)."""
    cli._running = False
    scheduler = getattr(cli, "_scheduler", None)
    if scheduler:
        scheduler.stop()
    gateway = getattr(cli, "_gateway", None)
    if gateway:
        gateway.stop()

    try:
        await asyncio.wait_for(agent.stop(), timeout=3.0)
    except asyncio.TimeoutError:
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _register_builtin_tools(registry: ToolRegistry, vault: CredentialVault) -> None:
    """Daftarkan semua built-in tools ke registry.

    Tool yang didaftarkan:
    - FileSystemTool
    - ShellTool
    - HTTPAPITool (menggunakan CredentialVault yang disediakan)
    - DatabaseTool
    - BrowserTool

    Kegagalan registrasi satu tool dicatat ke log tetapi tidak menghentikan
    inisialisasi Agent (graceful degradation).
    """
    tools_to_register = [
        (FileSystemTool(), "builtin"),
        (ShellTool(), "builtin"),
        (HTTPAPITool(vault=vault), "builtin"),
        (DatabaseTool(), "builtin"),
        (BrowserTool(), "builtin"),
        (WebSearchTool(), "builtin"),
        (CodeSearchTool(), "builtin"),
        (GitTool(), "builtin"),
        (TestRunnerTool(), "builtin"),
        (PythonExecTool(), "builtin"),
        (SystemInspectTool(), "builtin"),
        (ProjectInspectTool(), "builtin"),
        (BenchmarkTool(), "builtin"),
    ]

    for tool, source in tools_to_register:
        try:
            registry.register(tool, source=source)
            _logger.debug("Tool '%s' berhasil didaftarkan.", tool.name)
        except Exception as exc:
            _logger.warning(
                "Gagal mendaftarkan tool '%s': %s",
                getattr(tool, "name", repr(tool)),
                exc,
            )

    # Temukan & muat plugin dinamis dari folder ./plugins jika ada
    try:
        loader = PluginLoader(registry)
        loader.discover_and_load(Path("plugins"))
    except Exception as exc:
        _logger.warning("Gagal memuat plugin dinamis: %s", exc)


def _read_log_path_from_config(config_path: Path) -> str:
    """Baca nilai ``log_path`` dari config.toml.

    Mengembalikan nilai default jika file tidak ada, tidak valid, atau
    field ``log_path`` tidak ditemukan.

    Args:
        config_path: Path ke file config.toml.

    Returns:
        String path ke file log.
    """
    try:
        import tomllib  # Python 3.11+
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config.get("log_path", _DEFAULT_LOG_FILENAME)
    except Exception:
        return _DEFAULT_LOG_FILENAME


def _read_config_dict(config_path: Path) -> dict:
    """Baca seluruh config.toml sebagai dict.

    Returns:
        Dict konfigurasi, atau dict kosong jika file tidak ada atau tidak valid.
    """
    try:
        import tomllib
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _create_minimal_config(config_path: Path) -> None:
    """Buat file config.toml minimal jika belum ada.

    Berguna agar agent dapat dijalankan tanpa konfigurasi eksplisit.

    Args:
        config_path: Path tempat file config.toml akan dibuat.
    """
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '# Local AI Agent — konfigurasi minimal (dibuat otomatis)\n'
            'default_model = "default"\n'
            "tool_directories = []\n"
            "sandbox_enabled = false\n"
            "shell_timeout_seconds = 30\n"
            f'log_path = "{_DEFAULT_LOG_FILENAME}"\n'
            "max_consecutive_actions = 10\n"
            "\n"
            "[model_parameters]\n"
            "temperature = 0.7\n"
            "context_length = 4096\n",
            encoding="utf-8",
        )
        _logger.info(
            "File config.toml minimal dibuat di '%s'.", config_path
        )
    except OSError as exc:
        _logger.warning("Gagal membuat config.toml: %s", exc)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "create_app",
    "main",
]

if __name__ == "__main__":
    main()
