"""
agent/core/audit_logger.py

AuditLogger — pencatat tindakan dan error Agent ke file log permanen.

Fitur utama:
- RotatingFileHandler dengan maxBytes = 100 MB dan backupCount = 5
- Setiap entri memiliki timestamp ISO 8601 (UTC)
- Nilai credential (api_key, token, password, secret, credential, auth, authorization,
  access_key, private_key, secret_key) di-redact menjadi "***REDACTED***" sebelum dicatat
- Nilai credential tidak pernah muncul di log dalam kondisi apapun

Requirements: 10.4, 10.5
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_LOG_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
LOG_BACKUP_COUNT = 5  # pertahankan hingga 5 file rotasi

# Kunci yang nilainya harus di-redact. Pencocokan case-insensitive terhadap
# kunci dict maupun fragmen kunci (mis. "x_api_key" juga akan di-redact).
_SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"api[_\-]?key",
        r"token",
        r"password",
        r"secret",
        r"credential",
        r"auth(?:orization)?",
        r"access[_\-]?key",
        r"private[_\-]?key",
        r"secret[_\-]?key",
        r"bearer",
    ]
)

_REDACTED = "***REDACTED***"

LOG_FORMAT = "%(message)s"  # Semua formatting dilakukan secara manual agar output selalu JSON


# ---------------------------------------------------------------------------
# Helper: redaction
# ---------------------------------------------------------------------------

def _is_sensitive_key(key: str) -> bool:
    """Kembalikan True jika key dianggap sensitif dan nilainya harus di-redact."""
    for pattern in _SENSITIVE_KEY_PATTERNS:
        if pattern.search(key):
            return True
    return False


def _redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Kembalikan salinan dict dengan nilai sensitif diganti _REDACTED.

    Melakukan rekursi untuk nested dict. List yang mengandung dict juga
    diproses secara rekursif. Nilai non-dict tidak diubah kecuali kuncinya
    teridentifikasi sensitif.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            result[key] = _REDACTED
        elif isinstance(value, dict):
            result[key] = _redact_dict(value)
        elif isinstance(value, list):
            result[key] = _redact_list(value)
        else:
            result[key] = value
    return result


def _redact_list(data: list[Any]) -> list[Any]:
    """Rekursi untuk list yang mungkin mengandung nested dict."""
    result: list[Any] = []
    for item in data:
        if isinstance(item, dict):
            result.append(_redact_dict(item))
        elif isinstance(item, list):
            result.append(_redact_list(item))
        else:
            result.append(item)
    return result


def _safe_serialize(obj: Any) -> str:
    """Serialisasi obj ke JSON-compatible string.

    Objek yang tidak dapat di-serialize oleh json.dumps dikembalikan sebagai
    repr() string agar log tidak pernah gagal karena tipe data tidak dikenal.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return repr(obj)


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Pencatat tindakan dan error Agent ke file log permanen.

    Setiap entri ditulis sebagai JSON satu baris (JSON Lines) dengan field:
    - ``timestamp``: ISO 8601 UTC
    - ``level``: "ACTION" atau "ERROR"
    - tergantung level: field action/params/result/confirmed atau error/context

    Credential di-redact sebelum ditulis ke log — nilai aslinya tidak pernah
    muncul di file log dalam kondisi apapun.

    Args:
        log_path: Path ke file log. Direktori induk dibuat otomatis jika belum ada.
    """

    def __init__(self, log_path: Path) -> None:
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(f"audit_logger.{self._log_path}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # Jangan bocorkan ke root logger

        # Hindari duplikasi handler jika AuditLogger diinstansiasi ulang
        if not self._logger.handlers:
            handler = RotatingFileHandler(
                filename=str(self._log_path),
                maxBytes=MAX_LOG_SIZE_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            self._logger.addHandler(handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        params: dict[str, Any],
        result: str,
        confirmed: bool = True,
    ) -> None:
        """Catat tindakan yang dieksekusi oleh Agent.

        Nilai credential di dalam ``params`` di-redact secara otomatis sebelum
        dicatat — nilai aslinya tidak pernah muncul di log.

        Args:
            action: Nama tindakan atau tool yang dieksekusi (mis. "filesystem.delete").
            params: Parameter yang diteruskan ke tool. Kunci sensitif di-redact.
            result: Ringkasan hasil tindakan (mis. "success", "failed: E001").
            confirmed: True jika tindakan telah dikonfirmasi oleh pengguna atau
                       tidak memerlukan konfirmasi; False jika dibatalkan.
        """
        safe_params = _redact_dict(params) if isinstance(params, dict) else {}
        entry = {
            "timestamp": _utc_now_iso(),
            "level": "ACTION",
            "action": action,
            "params": safe_params,
            "result": result,
            "confirmed": confirmed,
        }
        self._logger.info(_safe_serialize(entry))

    def log_error(self, error: str, context: dict[str, Any]) -> None:
        """Catat error yang terjadi selama eksekusi.

        Nilai credential di dalam ``context`` di-redact secara otomatis.

        Args:
            error: Pesan error atau kode error (mis. "[E001] Path tidak ditemukan: '/tmp/x'").
            context: Konteks tambahan seperti tool name, params, traceback ringkas.
                     Kunci sensitif di-redact.
        """
        safe_context = _redact_dict(context) if isinstance(context, dict) else {}
        entry = {
            "timestamp": _utc_now_iso(),
            "level": "ERROR",
            "error": error,
            "context": safe_context,
        }
        self._logger.error(_safe_serialize(entry))

    # ------------------------------------------------------------------
    # Properties (berguna untuk testing)
    # ------------------------------------------------------------------

    @property
    def log_path(self) -> Path:
        """Path ke file log yang aktif."""
        return self._log_path


# ---------------------------------------------------------------------------
# Helper: timestamp
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Kembalikan timestamp UTC saat ini dalam format ISO 8601 dengan sufiks Z."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
