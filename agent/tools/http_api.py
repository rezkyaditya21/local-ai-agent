"""
agent/tools/http_api.py

HTTP API Tool — mengirimkan HTTP request ke API eksternal menggunakan httpx.

Fitur utama:
- Mendukung method GET, POST, PUT, PATCH, DELETE.
- Mengikuti redirect secara manual hingga maksimum 10 kali; raise
  AgentRedirectLimitExceededError (E011) jika melebihi batas.
- Timeout 30 detik per request; raise AgentHTTPRequestError (E010) jika melebihi batas.
- Batas body request dan respons: 10 MB.
- Integrasi dengan CredentialVault untuk penyimpanan credential terenkripsi.
  Nilai credential tidak pernah dicatat ke log.

Requirements yang diimplementasikan: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.core.credential_vault import CredentialVault
from agent.core.exceptions import (
    AgentHTTPRequestError,
    AgentRedirectLimitExceededError,
)
from agent.models.schemas import HTTPResponse, ToolResult

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

MAX_BODY_BYTES: int = 10 * 1024 * 1024   # 10 MB
REQUEST_TIMEOUT_SECONDS: int = 30
MAX_REDIRECTS: int = 10

# HTTP methods yang didukung
SUPPORTED_METHODS: frozenset[str] = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE"}
)

# ---------------------------------------------------------------------------
# Logger (hanya untuk metadata, tidak pernah mencatat nilai credential)
# ---------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTPAPITool
# ---------------------------------------------------------------------------


class HTTPAPITool:
    """Tool untuk melakukan HTTP request ke API eksternal.

    Mengimplementasikan :class:`~agent.tools.registry.ToolInterface`.

    Seluruh credential disimpan terenkripsi di :class:`CredentialVault`.
    Nilai credential tidak pernah muncul di log, output terminal, atau
    representasi string objek ini.

    Args:
        vault: Instansi :class:`CredentialVault` yang akan digunakan.
            Jika ``None``, vault baru dibuat dengan lokasi default.
    """

    # ToolInterface attributes
    name: str = "http_api"
    description: str = (
        "Kirimkan HTTP request (GET/POST/PUT/PATCH/DELETE) ke URL eksternal. "
        "Mendukung header kustom, query params, body, dan manajemen credential terenkripsi."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method",
            },
            "url": {"type": "string", "description": "URL tujuan request"},
            "headers": {
                "type": "object",
                "description": "Header HTTP kustom (opsional)",
                "additionalProperties": {"type": "string"},
            },
            "params": {
                "type": "object",
                "description": "Query parameters (opsional)",
                "additionalProperties": {"type": "string"},
            },
            "body": {
                "type": ["string", "null"],
                "description": "Body request dalam bytes atau string (opsional)",
            },
        },
        "required": ["method", "url"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "headers": {"type": "object"},
            "body": {"type": "string", "description": "Body respons (bytes, base64-encoded)"},
            "final_url": {"type": "string"},
            "redirect_count": {"type": "integer"},
        },
    }

    def __init__(self, vault: CredentialVault | None = None) -> None:
        self._vault: CredentialVault = vault if vault is not None else CredentialVault()

    # ------------------------------------------------------------------
    # ToolInterface: run()
    # ------------------------------------------------------------------

    async def run(self, params: dict) -> ToolResult:
        """Dispatch ke method :meth:`request` berdasarkan ``params["method"]``.

        Args:
            params: Dict yang harus memiliki key ``"method"`` dan ``"url"``.
                Key opsional: ``"headers"``, ``"params"``, ``"body"``.

        Returns:
            :class:`ToolResult` dengan ``success=True`` dan ``data`` berisi
            :class:`HTTPResponse`, atau ``success=False`` dengan ``error``
            jika terjadi kegagalan.
        """
        method: str = str(params.get("method", "")).upper()
        url: str = str(params.get("url", ""))
        headers: dict[str, str] | None = params.get("headers")
        query_params: dict[str, str] | None = params.get("params")
        body: bytes | str | None = params.get("body")

        if method not in SUPPORTED_METHODS:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    f"Method '{method}' tidak didukung. "
                    f"Method yang valid: {', '.join(sorted(SUPPORTED_METHODS))}"
                ),
                tool_name=self.name,
            )

        try:
            response = await self.request(
                method=method,
                url=url,
                headers=headers,
                params=query_params,
                body=body,
            )
            return ToolResult(
                success=True,
                data=response,
                tool_name=self.name,
            )
        except AgentRedirectLimitExceededError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except AgentHTTPRequestError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except ValueError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except Exception as exc:  # pragma: no cover
            _logger.error("HTTPAPITool.run() unexpected error: %s", type(exc).__name__)
            return ToolResult(
                success=False,
                data=None,
                error=f"HTTP request gagal: {exc}",
                tool_name=self.name,
            )

    # ------------------------------------------------------------------
    # Core: request()
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        body: bytes | str | None = None,
    ) -> HTTPResponse:
        """Kirimkan HTTP request dan kembalikan :class:`HTTPResponse`.

        Redirect diikuti secara manual hingga :data:`MAX_REDIRECTS` (10).
        Jika melebihi batas, raise :exc:`AgentRedirectLimitExceededError`.

        Args:
            method: HTTP method — ``"GET"``, ``"POST"``, ``"PUT"``,
                ``"PATCH"``, atau ``"DELETE"``. Huruf besar/kecil diabaikan.
            url: URL tujuan.
            headers: Header HTTP kustom (opsional).
            params: Query parameters (opsional).
            body: Body request sebagai ``bytes`` atau ``str`` (opsional).
                Ukuran maksimum :data:`MAX_BODY_BYTES` (10 MB).

        Returns:
            :class:`HTTPResponse` yang berisi ``status_code``, ``headers``,
            ``body``, ``final_url``, dan ``redirect_count``.

        Raises:
            AgentHTTPRequestError: Jika request melebihi timeout 30 detik
                atau gagal karena network error.
            AgentRedirectLimitExceededError: Jika jumlah redirect melebihi 10.
            ValueError: Jika method tidak valid atau body melebihi 10 MB.
        """
        method = method.upper()
        if method not in SUPPORTED_METHODS:
            raise ValueError(
                f"Method '{method}' tidak didukung. "
                f"Method yang valid: {', '.join(sorted(SUPPORTED_METHODS))}"
            )

        # Validasi ukuran body request
        if body is not None:
            body_bytes = body if isinstance(body, bytes) else body.encode()
            if len(body_bytes) > MAX_BODY_BYTES:
                actual_mb = len(body_bytes) / (1024 * 1024)
                limit_mb = MAX_BODY_BYTES / (1024 * 1024)
                raise ValueError(
                    f"Ukuran body request ({actual_mb:.1f} MB) melebihi batas {limit_mb:.1f} MB"
                )
        else:
            body_bytes = None

        # httpx.AsyncClient dengan follow_redirects=False — redirect manual
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)

        redirect_count = 0
        current_url = url
        current_method = method
        current_body = body_bytes

        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
            ) as client:
                while True:
                    try:
                        response = await client.request(
                            method=current_method,
                            url=current_url,
                            headers=headers,
                            params=params if redirect_count == 0 else None,
                            content=current_body,
                        )
                    except httpx.TimeoutException:
                        raise AgentHTTPRequestError(
                            url=current_url,
                            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                        )
                    except httpx.NetworkError as exc:
                        raise AgentHTTPRequestError(
                            url=current_url,
                            reason=str(exc),
                        )

                    # Cek apakah ini redirect
                    if response.is_redirect:
                        redirect_count += 1
                        if redirect_count > MAX_REDIRECTS:
                            raise AgentRedirectLimitExceededError(
                                url=url,
                                redirect_count=redirect_count,
                                last_url=current_url,
                            )

                        location = response.headers.get("location", "")
                        if not location:
                            # Tidak ada header location — hentikan pengalihan
                            break

                        # Selesaikan URL relatif terhadap URL saat ini
                        current_url = str(response.url.copy_with()).rstrip("/")
                        current_url = str(httpx.URL(location, base=response.url))

                        # Untuk 301/302/303 dengan method non-GET:
                        # ubah ke GET dan buang body (sesuai RFC 7231)
                        if response.status_code in (301, 302, 303) and current_method != "GET":
                            current_method = "GET"
                            current_body = None
                        continue

                    # Bukan redirect — ini respons final
                    break

        except (AgentHTTPRequestError, AgentRedirectLimitExceededError):
            raise
        except httpx.TimeoutException:
            raise AgentHTTPRequestError(
                url=url,
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.NetworkError as exc:
            raise AgentHTTPRequestError(
                url=url,
                reason=str(exc),
            )
        except Exception as exc:
            raise AgentHTTPRequestError(
                url=url,
                reason=f"Unexpected error: {exc}",
            )

        # Baca body respons dengan batasan ukuran
        resp_body = response.content
        if len(resp_body) > MAX_BODY_BYTES:
            actual_mb = len(resp_body) / (1024 * 1024)
            limit_mb = MAX_BODY_BYTES / (1024 * 1024)
            raise ValueError(
                f"Ukuran body respons ({actual_mb:.1f} MB) melebihi batas {limit_mb:.1f} MB"
            )

        # Normalisasi headers respons ke dict[str, str]
        resp_headers: dict[str, str] = dict(response.headers)

        return HTTPResponse(
            status_code=response.status_code,
            headers=resp_headers,
            body=resp_body,
            final_url=str(response.url),
            redirect_count=redirect_count,
        )

    # ------------------------------------------------------------------
    # Credential management
    # ------------------------------------------------------------------

    def get_credential(self, key: str) -> str:
        """Ambil credential dari vault berdasarkan key.

        Nilai yang dikembalikan tidak pernah dicatat ke log atau disimpan
        ke atribut apapun pada objek ini.

        Args:
            key: Identifier credential (mis. ``"openai_api_key"``).

        Returns:
            Nilai plaintext credential.

        Raises:
            KeyError: Jika key tidak ditemukan di vault.
        """
        # Dekripsi hanya di local variable — tidak di-log, tidak di-store
        return self._vault.retrieve(key)

    def store_credential(self, key: str, value: str) -> None:
        """Enkripsi dan simpan credential ke vault.

        Nilai plaintext ``value`` di-enkripsi segera dan tidak pernah
        dicatat ke log maupun disimpan sebagai atribut objek ini.

        Args:
            key: Identifier credential.
            value: Nilai plaintext yang akan dienkripsi dan disimpan.
        """
        # Enkripsi terjadi di dalam CredentialVault.store();
        # referensi 'value' di sini tidak di-log sama sekali.
        self._vault.store(key, value)

    # ------------------------------------------------------------------
    # Safety: prevent credential leakage in repr/str
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return f"HTTPAPITool(vault={self._vault!r})"

    def __str__(self) -> str:  # pragma: no cover
        return repr(self)


__all__ = [
    "MAX_BODY_BYTES",
    "REQUEST_TIMEOUT_SECONDS",
    "MAX_REDIRECTS",
    "SUPPORTED_METHODS",
    "HTTPAPITool",
]
