"""
agent/gateway/telegram_gateway.py

TelegramGateway — Gateway bot Telegram untuk mengendalikan agen lokal dari jarak jauh (ponsel/laptop).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Coroutine

_logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramGateway:
    """Gateway Bot Telegram berbasis HTTP Long-Polling asinkron via httpx.

    Fitur:
    - Autentikasi Whitelist: Hanya User ID yang diizinkan yang dapat mengakses agen.
    - Forward pesan langsung ke `agent.process()` dan mengirimkan balasan ke chat Telegram.
    - Menangani /status, /model, /help, dan eksekusi tugas.
    """

    def __init__(
        self,
        token: str,
        allowed_user_ids: list[int] | None = None,
        agent_processor: Callable[[str], AsyncIterator[str]] | None = None,
    ) -> None:
        self._token = token.strip()
        self._allowed_user_ids = set(allowed_user_ids or [])
        self._agent_processor = agent_processor
        self._running = False
        self._last_update_id = 0
        self._task: asyncio.Task | None = None

    def set_processor(self, processor: Callable[[str], AsyncIterator[str]]) -> None:
        """Set generator pemroses pesan agen."""
        self._agent_processor = processor

    def is_configured(self) -> bool:
        """Cek apakah token bot sudah dikonfigurasi."""
        return bool(self._token and not self._token.startswith("YOUR_"))

    async def _send_message(self, chat_id: int | str, text: str) -> bool:
        """Kirim pesan teks ke Telegram chat."""
        try:
            import httpx
            url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
            # Telegram batas 4096 karakter per pesan
            chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)] or ["(pesan kosong)"]
            async with httpx.AsyncClient(timeout=15.0) as client:
                for chunk in chunks:
                    await client.post(url, json={"chat_id": chat_id, "text": chunk})
            return True
        except Exception as exc:
            _logger.error("Gagal mengirim pesan Telegram ke %s: %s", chat_id, exc)
            return False

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Proses satu pesan masuk dari Telegram."""
        user = message.get("from", {})
        user_id = user.get("id")
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not chat_id or not text:
            return

        # Pemeriksaan Keamanan Whitelist
        if self._allowed_user_ids and user_id not in self._allowed_user_ids:
            _logger.warning("Akses Telegram ditolak untuk User ID: %s", user_id)
            await self._send_message(
                chat_id,
                f"⛔ Akses Ditolak.\nID Telegram Anda ({user_id}) tidak terdaftar di daftar aman agen.",
            )
            return

        # Perintah Dasar
        if text == "/start" or text == "/help":
            welcome_msg = (
                "☤ *Local AI Agent Telegram Gateway*\n\n"
                "Anda terhubung langsung ke agen AI lokal Anda!\n"
                "Ketik pesan atau instruksi apa pun untuk menjalankan tugas terminal, pencarian web, atau obrolan santai."
            )
            await self._send_message(chat_id, welcome_msg)
            return

        if text == "/status":
            await self._send_message(chat_id, "🟢 Agen Lokal Aktif & Siap Menerima Perintah.")
            return

        # Jalankan pemrosesan agen
        if self._agent_processor is not None:
            await self._send_message(chat_id, "⏳ Sedang memproses...")
            try:
                full_response_parts: list[str] = []
                async for token in self._agent_processor(text):
                    full_response_parts.append(token)
                full_response = "".join(full_response_parts).strip()
                if not full_response:
                    full_response = "✅ Tugas selesai (tidak ada output teks tambahan)."
                await self._send_message(chat_id, full_response)
            except Exception as exc:
                await self._send_message(chat_id, f"❌ Error saat memproses: {exc}")
        else:
            await self._send_message(chat_id, "⚠️ Agen processor belum terhubung.")

    async def _poll_updates(self) -> None:
        """Loop polling pembaruan pesan dari Telegram Bot API."""
        try:
            import httpx
        except ImportError:
            _logger.error("Httpx tidak terinstal, gateway Telegram dinonaktifkan.")
            return

        url = f"{TELEGRAM_API_BASE}/bot{self._token}/getUpdates"
        _logger.info("Telegram Gateway polling dimulai.")

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.get(
                        url,
                        params={"offset": self._last_update_id + 1, "timeout": 30},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            self._last_update_id = max(self._last_update_id, update.get("update_id", 0))
                            if "message" in update:
                                await self._handle_message(update["message"])
                    elif resp.status_code in (401, 404):
                        _logger.error("Token bot Telegram tidak valid: HTTP %s", resp.status_code)
                        await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _logger.debug("Telegram polling timeout/error: %s", exc)
                await asyncio.sleep(3)

    def start(self) -> None:
        """Mulai gateway di background asyncio task."""
        if not self.is_configured():
            _logger.info("Telegram gateway tidak dimulai: Token belum dikonfigurasi.")
            return
        if not self._running:
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._poll_updates())
            except RuntimeError:
                pass

    def stop(self) -> None:
        """Hentikan gateway Telegram."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None


__all__ = ["TelegramGateway"]
