"""
agent/tools/browser.py

Browser Tool — mengakses dan berinteraksi dengan halaman web menggunakan
Playwright headless browser.

Komponen utama:
- `BrowserTool`: Implementasi `ToolInterface` untuk semua operasi web.

Fitur:
- `fetch_html`: Ambil konten HTML sebagai string UTF-8 (timeout 30 detik).
- `extract_content`: Ekstrak teks, tautan, dan JSON-LD dari HTML (tanpa browser).
- `fill_form`: Isi formulir menggunakan headless browser.
- `click_element`: Klik elemen CSS selector pada halaman.
- `screenshot`: Ambil screenshot halaman sebagai PNG.
- `set_cookies`: Simpan cookies untuk domain tertentu; diterapkan sebelum navigasi.

Requirements yang diimplementasikan: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any

from agent.core.exceptions import AgentBrowserFetchError
from agent.models.schemas import ExtractedContent, ToolResult

# ---------------------------------------------------------------------------
# Graceful import untuk Playwright
# ---------------------------------------------------------------------------

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PLAYWRIGHT_AVAILABLE = False
    Browser = None  # type: ignore[assignment,misc]
    BrowserContext = None  # type: ignore[assignment,misc]
    PlaywrightTimeoutError = Exception  # type: ignore[assignment,misc]
    async_playwright = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT_MS = 30_000   # 30 detik dalam milidetik (untuk Playwright API)
REQUEST_TIMEOUT_SECONDS = 30  # Referensi manusia-baca


# ---------------------------------------------------------------------------
# HTML parser ringan (tanpa BeautifulSoup)
# ---------------------------------------------------------------------------

class _ContentExtractor(HTMLParser):
    """Parser HTML internal untuk mengekstrak teks, tautan, dan JSON-LD.

    Diimplementasikan dengan `html.parser` dari stdlib agar tidak
    memerlukan dependensi tambahan (BeautifulSoup).
    """

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._links: list[str] = []
        self._structured_data: list[dict] = []

        # State untuk JSON-LD
        self._in_jsonld_script: bool = False
        self._jsonld_buffer: list[str] = []

        # Tag yang kontennya tidak perlu dikumpulkan sebagai teks terlihat
        self._skip_tags: set[str] = {"script", "style", "head", "meta", "link"}
        self._skip_depth: int = 0

    # ------------------------------------------------------------------ #
    # HTMLParser callbacks
    # ------------------------------------------------------------------ #

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        # Deteksi script JSON-LD
        if tag == "script":
            if attr_dict.get("type") == "application/ld+json":
                self._in_jsonld_script = True
                self._jsonld_buffer = []
            else:
                self._skip_depth += 1
            return

        if tag in self._skip_tags:
            self._skip_depth += 1
            return

        # Kumpulkan href dari <a>
        if tag == "a":
            href = attr_dict.get("href")
            if href and href.strip() and not href.startswith(("#", "javascript:")):
                self._links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._in_jsonld_script:
                raw = "".join(self._jsonld_buffer).strip()
                if raw:
                    try:
                        data = json.loads(raw)
                        if isinstance(data, list):
                            self._structured_data.extend(
                                item for item in data if isinstance(item, dict)
                            )
                        elif isinstance(data, dict):
                            self._structured_data.append(data)
                    except json.JSONDecodeError:
                        pass
                self._in_jsonld_script = False
                self._jsonld_buffer = []
            else:
                self._skip_depth = max(0, self._skip_depth - 1)
            return

        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        # Tambahkan pemisah baris untuk elemen blok
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                   "li", "tr", "br", "section", "article", "header", "footer"}:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_jsonld_script:
            self._jsonld_buffer.append(data)
            return

        if self._skip_depth > 0:
            return

        stripped = data.strip()
        if stripped:
            self._text_parts.append(stripped + " ")

    # ------------------------------------------------------------------ #
    # Hasil
    # ------------------------------------------------------------------ #

    @property
    def text(self) -> str:
        raw = "".join(self._text_parts)
        # Normalkan spasi dan baris kosong berlebih
        raw = re.sub(r" {2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()

    @property
    def links(self) -> list[str]:
        # Deduplikasi sambil menjaga urutan
        seen: set[str] = set()
        result: list[str] = []
        for link in self._links:
            if link not in seen:
                seen.add(link)
                result.append(link)
        return result

    @property
    def structured_data(self) -> list[dict]:
        return self._structured_data


# ---------------------------------------------------------------------------
# BrowserTool
# ---------------------------------------------------------------------------

class BrowserTool:
    """Tool untuk mengakses dan berinteraksi dengan halaman web.

    Menggunakan Playwright dalam mode headless (tanpa display) untuk
    semua operasi yang memerlukan browser nyata, dan `html.parser`
    stdlib untuk `extract_content` (tanpa browser).

    Browser instance di-lazy-init saat pertama kali dibutuhkan dan
    digunakan kembali di seluruh panggilan dalam satu sesi Agent.

    Attributes:
        name: Identifier tool dalam ToolRegistry.
        description: Deskripsi untuk pemilihan tool otomatis.
        input_schema: Skema parameter masukan (JSON Schema subset).
        output_schema: Skema nilai kembalian (JSON Schema subset).
    """

    name = "browser"
    description = (
        "Akses dan berinteraksi dengan halaman web: ambil HTML, ekstrak konten, "
        "isi formulir, klik elemen, tangkap screenshot, dan kelola cookies."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "fetch_html",
                    "extract_content",
                    "fill_form",
                    "click_element",
                    "screenshot",
                    "set_cookies",
                ],
                "description": "Operasi browser yang akan dijalankan.",
            },
            "url": {"type": "string", "description": "URL target."},
            "html": {"type": "string", "description": "Konten HTML (untuk extract_content)."},
            "selectors": {
                "type": "object",
                "description": "Mapping CSS selector → nilai (untuk fill_form).",
            },
            "selector": {"type": "string", "description": "CSS selector elemen (untuk click_element)."},
            "output_path": {"type": "string", "description": "Path output file PNG (untuk screenshot)."},
            "domain": {"type": "string", "description": "Domain target (untuk set_cookies)."},
            "cookies": {
                "type": "object",
                "description": "Mapping nama cookie → nilai (untuk set_cookies).",
            },
        },
        "required": ["operation"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "data": {},
            "error": {"type": ["string", "null"]},
            "tool_name": {"type": "string"},
        },
    }

    def __init__(self) -> None:
        self._playwright_ctx: Any = None   # async_playwright context manager
        self._browser: Any = None           # Browser instance (lazy)
        # Cookie storage: {domain: [{"name": ..., "value": ..., "domain": ...}]}
        self._cookies: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _require_playwright(self) -> None:
        """Raise ImportError dengan pesan jelas jika Playwright tidak tersedia."""
        if not _PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright tidak terinstal. Jalankan: "
                "pip install playwright && playwright install chromium"
            )

    async def _get_browser(self) -> Any:
        """Kembalikan browser instance yang sudah diinisialisasi (lazy init).

        Browser dijalankan dalam mode headless agar kompatibel dengan
        lingkungan tanpa display grafis (Requirement 4.7).
        """
        self._require_playwright()
        if self._browser is None or not self._browser.is_connected():
            self._playwright_ctx = await async_playwright().start()
            self._browser = await self._playwright_ctx.chromium.launch(headless=True)
        return self._browser

    async def _new_context(self) -> Any:
        """Buat BrowserContext baru, terapkan semua cookies yang tersimpan."""
        browser = await self._get_browser()
        context: BrowserContext = await browser.new_context()
        # Terapkan cookies untuk semua domain yang tersimpan
        all_cookies: list[dict] = []
        for domain_cookies in self._cookies.values():
            all_cookies.extend(domain_cookies)
        if all_cookies:
            await context.add_cookies(all_cookies)
        return context

    async def _close(self) -> None:
        """Tutup browser dan playwright instance (dipanggil saat sesi berakhir)."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright_ctx is not None:
            try:
                await self._playwright_ctx.stop()
            except Exception:
                pass
            self._playwright_ctx = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def fetch_html(self, url: str) -> str:
        """Ambil konten HTML halaman sebagai string UTF-8.

        Menggunakan Playwright headless browser. Timeout 30 detik.

        Args:
            url: URL halaman yang akan diambil.

        Returns:
            Konten HTML sebagai string UTF-8.

        Raises:
            AgentBrowserFetchError: Jika request gagal, timeout, atau
                menghasilkan HTTP error (E007).
            ImportError: Jika Playwright tidak terinstal.
        """
        self._require_playwright()
        context = None
        try:
            context = await self._new_context()
            page = await context.new_page()
            try:
                response = await page.goto(url, timeout=REQUEST_TIMEOUT_MS, wait_until="load")
                if response is None:
                    raise AgentBrowserFetchError(url=url, reason="tidak ada respons dari server")
                if not response.ok:
                    raise AgentBrowserFetchError(
                        url=url,
                        reason=f"HTTP {response.status} {response.status_text}",
                    )
                html_content = await page.content()
                return html_content
            except PlaywrightTimeoutError:
                raise AgentBrowserFetchError(
                    url=url,
                    reason=f"tidak mendapat respons dalam {REQUEST_TIMEOUT_SECONDS} detik",
                )
        except AgentBrowserFetchError:
            raise
        except Exception as exc:
            raise AgentBrowserFetchError(url=url, reason=str(exc)) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def extract_content(self, html: str) -> ExtractedContent:
        """Ekstrak teks, tautan, dan data terstruktur dari HTML.

        Operasi murni berbasis string — tidak memerlukan browser.
        Menggunakan html.parser stdlib dan JSON untuk JSON-LD.

        Args:
            html: String konten HTML yang akan diproses.

        Returns:
            `ExtractedContent` dengan teks, daftar tautan, dan data
            terstruktur (JSON-LD schema.org).
        """
        parser = _ContentExtractor()
        try:
            parser.feed(html)
        except Exception:
            # Kembalikan hasil parsial jika HTML malformed
            pass

        return ExtractedContent(
            text=parser.text,
            links=parser.links,
            structured_data=parser.structured_data,
        )

    async def fill_form(self, url: str, selectors: dict[str, str]) -> None:
        """Isi formulir web menggunakan headless browser.

        Setiap key dalam `selectors` adalah CSS selector elemen input,
        dan value adalah teks yang akan diisi.

        Args:
            url: URL halaman yang memuat formulir.
            selectors: Mapping ``{css_selector: nilai_yang_diisi}``.

        Raises:
            AgentBrowserFetchError: Jika halaman gagal dimuat atau elemen
                tidak ditemukan (E007).
            ImportError: Jika Playwright tidak terinstal.
        """
        self._require_playwright()
        context = None
        try:
            context = await self._new_context()
            page = await context.new_page()
            try:
                response = await page.goto(url, timeout=REQUEST_TIMEOUT_MS, wait_until="load")
                if response is None or not response.ok:
                    status = response.status if response else "unknown"
                    raise AgentBrowserFetchError(
                        url=url, reason=f"gagal memuat halaman (HTTP {status})"
                    )
                for css_selector, value in selectors.items():
                    await page.fill(css_selector, value, timeout=REQUEST_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                raise AgentBrowserFetchError(
                    url=url,
                    reason=f"timeout saat mengisi formulir setelah {REQUEST_TIMEOUT_SECONDS} detik",
                )
        except AgentBrowserFetchError:
            raise
        except Exception as exc:
            raise AgentBrowserFetchError(url=url, reason=str(exc)) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def click_element(self, url: str, selector: str) -> None:
        """Klik elemen pada halaman web menggunakan headless browser.

        Args:
            url: URL halaman target.
            selector: CSS selector elemen yang akan diklik.

        Raises:
            AgentBrowserFetchError: Jika halaman gagal dimuat, selector
                tidak ditemukan, atau timeout (E007).
            ImportError: Jika Playwright tidak terinstal.
        """
        self._require_playwright()
        context = None
        try:
            context = await self._new_context()
            page = await context.new_page()
            try:
                response = await page.goto(url, timeout=REQUEST_TIMEOUT_MS, wait_until="load")
                if response is None or not response.ok:
                    status = response.status if response else "unknown"
                    raise AgentBrowserFetchError(
                        url=url, reason=f"gagal memuat halaman (HTTP {status})"
                    )
                await page.click(selector, timeout=REQUEST_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                raise AgentBrowserFetchError(
                    url=url,
                    reason=f"timeout saat mengklik elemen '{selector}' setelah {REQUEST_TIMEOUT_SECONDS} detik",
                )
        except AgentBrowserFetchError:
            raise
        except Exception as exc:
            raise AgentBrowserFetchError(url=url, reason=str(exc)) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def screenshot(self, url: str, output_path: str) -> str:
        """Tangkap screenshot halaman web dan simpan sebagai PNG.

        Args:
            url: URL halaman yang akan di-screenshot.
            output_path: Path file output PNG (dibuat atau ditimpa).

        Returns:
            Path absolut file PNG yang disimpan.

        Raises:
            AgentBrowserFetchError: Jika halaman gagal dimuat atau
                screenshot gagal disimpan (E007).
            ImportError: Jika Playwright tidak terinstal.
        """
        self._require_playwright()
        context = None
        try:
            context = await self._new_context()
            page = await context.new_page()
            try:
                response = await page.goto(url, timeout=REQUEST_TIMEOUT_MS, wait_until="load")
                if response is None or not response.ok:
                    status = response.status if response else "unknown"
                    raise AgentBrowserFetchError(
                        url=url, reason=f"gagal memuat halaman (HTTP {status})"
                    )
                await page.screenshot(path=output_path, full_page=True)
                return output_path
            except PlaywrightTimeoutError:
                raise AgentBrowserFetchError(
                    url=url,
                    reason=f"timeout saat mengambil screenshot setelah {REQUEST_TIMEOUT_SECONDS} detik",
                )
        except AgentBrowserFetchError:
            raise
        except Exception as exc:
            raise AgentBrowserFetchError(url=url, reason=str(exc)) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def set_cookies(self, domain: str, cookies: dict) -> None:
        """Simpan cookies untuk domain tertentu.

        Cookies disimpan dalam memori dan diterapkan secara otomatis
        sebelum setiap navigasi ke domain yang sama (Requirement 4.6).

        Args:
            domain: Domain target (contoh: ``"example.com"``).
            cookies: Mapping ``{nama_cookie: nilai}`` yang akan disimpan.
        """
        cookie_list: list[dict] = []
        for name, value in cookies.items():
            cookie_entry: dict = {
                "name": str(name),
                "value": str(value),
                "domain": domain if domain.startswith(".") else f".{domain}",
                "path": "/",
            }
            cookie_list.append(cookie_entry)
        self._cookies[domain] = cookie_list

    # ------------------------------------------------------------------ #
    # ToolInterface: run() dispatcher
    # ------------------------------------------------------------------ #

    async def run(self, params: dict) -> ToolResult:
        """Dispatcher utama untuk semua operasi BrowserTool.

        Memilih operasi berdasarkan ``params["operation"]`` dan
        mendelegasikan ke method yang sesuai.

        Args:
            params: Parameter operasi. Wajib mengandung key ``"operation"``.
                Setiap operasi memiliki parameter tambahan masing-masing:
                - ``fetch_html``: ``url``
                - ``extract_content``: ``html``
                - ``fill_form``: ``url``, ``selectors``
                - ``click_element``: ``url``, ``selector``
                - ``screenshot``: ``url``, ``output_path``
                - ``set_cookies``: ``domain``, ``cookies``

        Returns:
            `ToolResult` dengan ``success=True`` dan ``data`` berisi
            hasil operasi, atau ``ToolResult(success=False, error=...)``
            jika terjadi kesalahan.
        """
        operation = params.get("operation")

        try:
            if operation == "fetch_html":
                url = params["url"]
                html = await self.fetch_html(url)
                return ToolResult(success=True, data=html, tool_name=self.name)

            elif operation == "extract_content":
                html = params["html"]
                content = await self.extract_content(html)
                return ToolResult(
                    success=True,
                    data={
                        "text": content.text,
                        "links": content.links,
                        "structured_data": content.structured_data,
                    },
                    tool_name=self.name,
                )

            elif operation == "fill_form":
                url = params["url"]
                selectors: dict[str, str] = params.get("selectors", {})
                await self.fill_form(url, selectors)
                return ToolResult(
                    success=True,
                    data={"message": f"Formulir pada '{url}' berhasil diisi"},
                    tool_name=self.name,
                )

            elif operation == "click_element":
                url = params["url"]
                selector: str = params["selector"]
                await self.click_element(url, selector)
                return ToolResult(
                    success=True,
                    data={"message": f"Elemen '{selector}' pada '{url}' berhasil diklik"},
                    tool_name=self.name,
                )

            elif operation == "screenshot":
                url = params["url"]
                output_path: str = params["output_path"]
                saved_path = await self.screenshot(url, output_path)
                return ToolResult(
                    success=True,
                    data={"path": saved_path},
                    tool_name=self.name,
                )

            elif operation == "set_cookies":
                domain: str = params["domain"]
                cookies_dict: dict = params.get("cookies", {})
                await self.set_cookies(domain, cookies_dict)
                return ToolResult(
                    success=True,
                    data={"message": f"Cookies untuk domain '{domain}' berhasil disimpan"},
                    tool_name=self.name,
                )

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=(
                        f"Operasi tidak dikenal: '{operation}'. "
                        "Operasi yang valid: fetch_html, extract_content, fill_form, "
                        "click_element, screenshot, set_cookies."
                    ),
                    tool_name=self.name,
                )

        except AgentBrowserFetchError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except ImportError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=str(exc),
                tool_name=self.name,
            )
        except KeyError as exc:
            return ToolResult(
                success=False,
                data=None,
                error=f"Parameter wajib tidak ada: {exc}",
                tool_name=self.name,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                data=None,
                error=f"Error tidak terduga pada BrowserTool: {exc}",
                tool_name=self.name,
            )


__all__ = ["BrowserTool", "REQUEST_TIMEOUT_SECONDS"]
