"""Unit tests for web search and extraction tools in zeus/tools/web.py."""

from unittest.mock import MagicMock, patch

from zeus.tools.web import web_extract, web_scrape_links, web_search


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
    mock_resp.is_redirect = False

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
    mock_resp.is_redirect = False

    with patch("requests.get", return_value=mock_resp):
        res = web_scrape_links("https://example.com")
        assert res["status"] == "success"
        assert len(res["links"]) == 2
        assert res["links"][0]["url"] == "https://example.com/page1"
        assert res["links"][1]["url"] == "https://example.com/page2"


def test_web_extract_blocks_private_url():
    res = web_extract("http://127.0.0.1:9876/secrets")
    assert "error" in res
    assert "blocked" in res["error"].lower()


def test_web_scrape_links_blocks_private_url():
    res = web_scrape_links("http://localhost/admin")
    assert "error" in res
    assert "blocked" in res["error"].lower()


def test_web_extract_blocks_redirect_to_private_url():
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.is_redirect = True
    mock_resp.headers = {"Location": "http://127.0.0.1:9876/internal"}

    with patch("requests.get", return_value=mock_resp):
        res = web_extract("https://example.com/article")
    assert "error" in res
    assert "Redirect blocked" in res["error"]


def test_web_scrape_links_blocks_redirect_to_private_url():
    mock_resp = MagicMock()
    mock_resp.status_code = 301
    mock_resp.is_redirect = True
    mock_resp.headers = {"Location": "http://localhost/admin"}

    with patch("requests.get", return_value=mock_resp):
        res = web_scrape_links("https://example.com")
    assert "error" in res
    assert "Redirect blocked" in res["error"]
