"""Unit tests for web search and extraction tools in zeus/tools/web.py."""

from unittest.mock import MagicMock, patch
import pytest

from zeus.tools.web import web_search, web_extract, web_scrape_links


def test_web_search_duckduckgo_fallback():
    mock_ddg_output = [
        {"title": "Test Title 1", "href": "https://example.com/1", "body": "Snippet 1"},
        {"title": "Test Title 2", "href": "https://example.com/2", "body": "Snippet 2"},
    ]

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.return_value = mock_ddg_output
        mock_ddgs.return_value.__enter__.return_value = instance

        res = web_search("python ai agent", limit=2)
        assert res["provider"] == "duckduckgo"
        assert len(res["results"]) == 2
        assert res["results"][0]["title"] == "Test Title 1"


def test_web_extract_markdown():
    sample_html = """
    <html>
        <head><title>Test Page Title</title></head>
        <body>
            <nav><a href="/home">Home</a></nav>
            <h1>Main Heading</h1>
            <p>This is a paragraph with <b>bold text</b> and <a href="https://example.com">a link</a>.</p>
            <script>console.log('ignore me');</script>
        </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.encoding = "utf-8"
    mock_resp.content = sample_html.encode("utf-8")
    mock_resp.text = sample_html

    with patch("requests.get", return_value=mock_resp):
        res = web_extract("https://example.com/article")
        assert res["status"] == "success"
        assert res["title"] == "Test Page Title"
        assert "Main Heading" in res["content"]
        assert "bold text" in res["content"]


def test_web_scrape_links():
    sample_html = """
    <html>
        <body>
            <a href="https://example.com/page1">Page 1</a>
            <a href="/page2">Page 2 Relative</a>
        </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html

    with patch("requests.get", return_value=mock_resp):
        res = web_scrape_links("https://example.com")
        assert res["status"] == "success"
        assert len(res["links"]) == 2
        assert res["links"][0]["url"] == "https://example.com/page1"
        assert res["links"][1]["url"] == "https://example.com/page2"
