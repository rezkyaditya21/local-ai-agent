"""
agent/tools/web_search.py

Web Search Tool — melakukan pencarian informasi di internet.

Komponen utama:
- `WebSearchTool`: Implementasi `ToolInterface` untuk pencarian web.

Fitur:
- Mendukung kata kunci pencarian arbitrer.
- Menggunakan Bing Search dan DuckDuckGo untuk mengekstrak hasil pencarian web teraktual.
- Mengabaikan pengalihan internal dan mengodekan ulang URL tujuan asli.
- Mengembalikan daftar hasil berupa title, snippet, dan URL.
"""

from __future__ import annotations

import base64
import logging
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from agent.models.schemas import ToolResult

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

DEFAULT_MAX_RESULTS: int = 5
MAX_SEARCH_RESULTS: int = 10
REQUEST_TIMEOUT_SECONDS: int = 15

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# HTML Parsers
# ---------------------------------------------------------------------------


class _BingHTMLParser(HTMLParser):
    """Parser HTML untuk halaman pencarian Bing Search (www.bing.com/search)."""

    def __init__(self, max_results: int = DEFAULT_MAX_RESULTS) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str]] = []

        self._in_b_algo = False
        self._in_h2 = False
        self._in_a = False
        self._in_caption = False

        self._current_title: list[str] = []
        self._current_url: str = ""
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        classes = attr_dict.get("class", "").split()

        if tag == "li" and "b_algo" in classes:
            self._in_b_algo = True
            self._current_title = []
            self._current_url = ""
            self._current_snippet = []
        elif self._in_b_algo and tag == "h2":
            self._in_h2 = True
        elif self._in_h2 and tag == "a":
            self._in_a = True
            raw_href = attr_dict.get("href", "")
            self._current_url = self._decode_bing_url(raw_href)
        elif self._in_b_algo and (tag == "p" or "b_caption" in classes or tag == "div"):
            if not self._current_snippet:
                self._in_caption = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_a:
            self._in_a = False
        elif tag == "h2" and self._in_h2:
            self._in_h2 = False
        elif tag == "p" and self._in_caption:
            self._in_caption = False
        elif tag == "li" and self._in_b_algo:
            self._in_b_algo = False
            title = unescape("".join(self._current_title)).strip()
            snippet = unescape("".join(self._current_snippet)).strip()
            if title and self._current_url and not self._current_url.startswith("javascript"):
                self.results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": self._current_url,
                })
                self._current_title = []
                self._current_snippet = []
                self._current_url = ""

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._current_title.append(data)
        elif self._in_caption:
            self._current_snippet.append(data)

    @staticmethod
    def _decode_bing_url(raw_url: str) -> str:
        """Dekode URL dari link tracking Bing (/ck/a?...&u=a1...)."""
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        if "bing.com" in parsed.netloc and "/ck/a" in parsed.path:
            qs = parse_qs(parsed.query)
            if "u" in qs:
                u_val = qs["u"][0]
                if u_val.startswith("a1"):
                    b64 = u_val[2:]
                    b64 += "=" * (-len(b64) % 4)
                    try:
                        decoded = base64.b64decode(b64).decode("utf-8")
                        return decoded
                    except Exception:
                        pass
        return raw_url


class _DDGHTMLParser(HTMLParser):
    """Parser HTML untuk halaman pencarian DuckDuckGo HTML (html.duckduckgo.com)."""

    def __init__(self, max_results: int = DEFAULT_MAX_RESULTS) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str]] = []

        self._in_title_a = False
        self._in_snippet_td = False

        self._current_title: list[str] = []
        self._current_url: str = ""
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        classes = attr_dict.get("class", "").split()

        if tag == "a" and "result__a" in classes:
            self._in_title_a = True
            self._current_title = []
            raw_href = attr_dict.get("href", "")
            self._current_url = self._clean_ddg_url(raw_href)

        elif tag == "td" and "result__snippet" in classes:
            self._in_snippet_td = True
            self._current_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title_a:
            self._in_title_a = False
        elif tag == "td" and self._in_snippet_td:
            self._in_snippet_td = False
            title = unescape("".join(self._current_title)).strip()
            snippet = unescape("".join(self._current_snippet)).strip()
            if self._current_url and title:
                self.results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": self._current_url,
                })
                self._current_title = []
                self._current_snippet = []
                self._current_url = ""

    def handle_data(self, data: str) -> None:
        if self._in_title_a:
            self._current_title.append(data)
        elif self._in_snippet_td:
            self._current_snippet.append(data)

    @staticmethod
    def _clean_ddg_url(raw_url: str) -> str:
        if not raw_url:
            return ""
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        parsed = urlparse(raw_url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        return raw_url


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------


class WebSearchTool:
    """Tool untuk melakukan pencarian di internet.

    Mengimplementasikan `ToolInterface`.
    """

    name: str = "web_search"
    description: str = (
        "Lakukan pencarian web/internet untuk menemukan informasi, berita, artikel, "
        "atau jawaban atas kata kunci tertentu."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Kata kunci atau frasa pencarian di internet",
            },
            "max_results": {
                "type": "integer",
                "description": "Jumlah hasil maksimum yang dikembalikan (1-10, default 5)",
            },
        },
        "required": ["query"],
    }
    output_schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "snippet": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
            },
        },
    }

    async def run(self, params: dict) -> ToolResult:
        """Eksekusi pencarian web dengan query yang diberikan.

        Args:
            params: Dict berisi key "query" dan opsional "max_results".

        Returns:
            ToolResult dengan data hasil pencarian.
        """
        query = str(params.get("query", "")).strip()
        if not query:
            return ToolResult(
                success=False,
                data=None,
                error="Parameter 'query' tidak boleh kosong.",
                tool_name=self.name,
            )

        raw_max = params.get("max_results", DEFAULT_MAX_RESULTS)
        try:
            max_results = int(raw_max)
            max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
        except (ValueError, TypeError):
            max_results = DEFAULT_MAX_RESULTS

        try:
            results = await self._search_web(query, max_results)
            return ToolResult(
                success=True,
                data={"query": query, "results": results},
                tool_name=self.name,
            )
        except Exception as exc:
            _logger.error("Error pada WebSearchTool.run: %s", exc)
            return ToolResult(
                success=False,
                data=None,
                error=f"Pencarian web gagal: {exc}",
                tool_name=self.name,
            )

    async def _search_web(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Lakukan pencarian web via Bing atau DuckDuckGo."""
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        }
        timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            # 1. Coba Bing Search terlebih dahulu
            try:
                bing_url = f"https://www.bing.com/search?q={httpx.QueryParams({'q': query})['q']}"
                response = await client.get(bing_url)
                response.raise_for_status()
                parser = _BingHTMLParser(max_results=max_results)
                parser.feed(response.text)
                results = parser.results[:max_results]
                if results:
                    return results
            except Exception as exc:
                _logger.warning("Bing search gagal: %s. Mencoba DuckDuckGo...", exc)

            # 2. Coba DuckDuckGo HTML
            try:
                ddg_url = "https://html.duckduckgo.com/html/"
                response = await client.post(ddg_url, data={"q": query, "b": ""})
                response.raise_for_status()
                parser = _DDGHTMLParser(max_results=max_results)
                parser.feed(response.text)
                results = parser.results[:max_results]
                if results:
                    return results
            except Exception as exc:
                _logger.warning("DuckDuckGo HTML search gagal: %s. Mencoba Instant Answer API...", exc)

            # 3. Fallback DuckDuckGo API
            api_url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
            resp = await client.get(api_url, params=params)
            resp.raise_for_status()
            json_data = resp.json()

            results = []
            abstract = json_data.get("AbstractText", "")
            abstract_url = json_data.get("AbstractURL", "")
            heading = json_data.get("Heading", query)
            if abstract and abstract_url:
                results.append({"title": heading, "snippet": abstract, "url": abstract_url})

            for topic in json_data.get("RelatedTopics", []):
                if len(results) >= max_results:
                    break
                text = topic.get("Text")
                url = topic.get("FirstURL")
                if text and url:
                    results.append({
                        "title": text.split(" - ")[0] if " - " in text else text[:50],
                        "snippet": text,
                        "url": url,
                    })

            return results


__all__ = ["WebSearchTool"]
