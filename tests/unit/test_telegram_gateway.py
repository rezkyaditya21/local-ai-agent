"""Tests for TelegramGateway."""
import pytest
from agent.gateway.telegram_gateway import TelegramGateway


def test_telegram_gateway_configuration():
    gw_unconfigured = TelegramGateway(token="YOUR_TELEGRAM_BOT_TOKEN_HERE")
    assert gw_unconfigured.is_configured() is False

    gw_configured = TelegramGateway(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", allowed_user_ids=[12345])
    assert gw_configured.is_configured() is True
    assert 12345 in gw_configured._allowed_user_ids


@pytest.mark.asyncio
async def test_telegram_gateway_handle_whitelist():
    sent_messages = []

    class MockGateway(TelegramGateway):
        async def _send_message(self, chat_id, text):
            sent_messages.append((chat_id, text))
            return True

    gw = MockGateway(token="test_token", allowed_user_ids=[100])

    # Pesan dari user yang tidak di-whitelist
    msg_unauthorized = {
        "from": {"id": 999},
        "chat": {"id": 999},
        "text": "halo",
    }
    await gw._handle_message(msg_unauthorized)
    assert len(sent_messages) == 1
    assert "Akses Ditolak" in sent_messages[0][1]

    # Pesan /start dari authorized user
    msg_authorized = {
        "from": {"id": 100},
        "chat": {"id": 100},
        "text": "/start",
    }
    await gw._handle_message(msg_authorized)
    assert len(sent_messages) == 2
    assert "Local AI Agent" in sent_messages[1][1]
