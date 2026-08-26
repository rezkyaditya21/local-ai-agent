"""
tests/unit/test_web_search_tool.py

Unit test untuk WebSearchTool.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.tools.web_search import WebSearchTool, _BingHTMLParser, _DDGHTMLParser
from agent.tools.registry import ToolRegistry
from agent.models.schemas import ToolResult


@pytest.fixture
def web_search_tool() -> WebSearchTool:
    return WebSearchTool()


def test_tool_interface_compliance(web_search_tool: WebSearchTool) -> None:
    """Pastikan WebSearchTool memenuhi atribut ToolInterface."""
    assert web_search_tool.name == "web_search"
    assert isinstance(web_search_tool.description, str)
    assert isinstance(web_search_tool.input_schema, dict)
    assert isinstance(web_search_tool.output_schema, dict)
    assert callable(web_search_tool.run)

    registry = ToolRegistry()
    missing = registry.validate_plugin_schema(web_search_tool)
    assert missing == []


@pytest.mark.asyncio
async def test_run_empty_query(web_search_tool: WebSearchTool) -> None:
    """Test penanganan query kosong."""
    result = await web_search_tool.run({"query": "   "})
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "tidak boleh kosong" in result.error
    assert result.tool_name == "web_search"


@pytest.mark.asyncio
async def test_run_success_bing_mock(web_search_tool: WebSearchTool) -> None:
    """Test pencarian sukses dengan mock Bing response."""
    mock_bing_html = """
    <html>
      <body>
        <li class="b_algo">
          <h2><a href="https://www.bing.com/ck/a?!&&p=1&u=a1aHR0cHM6Ly9weXRob24ub3JnLw">Python Programming</a></h2>
          <p>Python language documentation.</p>
        </li>
      </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_bing_html
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await web_search_tool.run({"query": "python language", "max_results": 2})

        assert result.success is True
        assert result.data["query"] == "python language"
        assert len(result.data["results"]) == 1
        assert result.data["results"][0]["title"] == "Python Programming"
        assert result.data["results"][0]["url"] == "https://python.org/"
        assert result.data["results"][0]["snippet"] == "Python language documentation."


@pytest.mark.asyncio
async def test_run_ddg_fallback_mock(web_search_tool: WebSearchTool) -> None:
    """Test fallback ke DuckDuckGo jika Bing gagal."""
    mock_ddg_html = """
    <html>
      <body>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org">Python Programming</a>
        <td class="result__snippet">Python is a programming language.</td>
      </body>
    </html>
    """
    mock_ddg_resp = MagicMock()
    mock_ddg_resp.status_code = 200
    mock_ddg_resp.text = mock_ddg_html
    mock_ddg_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.side_effect = Exception("Bing Error")
        mock_post.return_value = mock_ddg_resp

        result = await web_search_tool.run({"query": "python"})

        assert result.success is True
        assert len(result.data["results"]) == 1
        assert result.data["results"][0]["title"] == "Python Programming"
        assert result.data["results"][0]["url"] == "https://python.org"


def test_bing_url_decoding() -> None:
    """Test dekoding base64 URL Bing."""
    raw = "https://www.bing.com/ck/a?!&&p=123&u=a1aHR0cHM6Ly93d3cucHl0aG9uLm9yZy8"
    decoded = _BingHTMLParser._decode_bing_url(raw)
    assert decoded == "https://www.python.org/"
