"""Additional unit tests for zeus/tools/web.py."""

from unittest.mock import MagicMock, patch

from zeus.tools.web import web_extract, web_scrape_links, web_search


@patch("requests.post")
def test_web_search_tavily(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "T", "url": "http://x.com", "content": "snippet"}]
    }

    with patch.dict("os.environ", {"TAVILY_API_KEY": "fake"}, clear=False):
        result = web_search("query", limit=1)

    assert result["provider"] == "tavily"
    assert len(result["results"]) == 1


@patch("requests.post")
def test_web_search_serper(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "organic": [{"title": "S", "link": "http://s.com", "snippet": "ss"}]
    }

    with patch.dict("os.environ", {"SERPER_API_KEY": "fake"}, clear=False):
        result = web_search("query", limit=1)

    assert result["provider"] == "serper"


@patch("requests.post")
@patch("ddgs.DDGS")
def test_web_search_duckduckgo_fallback(mock_ddgs, mock_post):
    mock_post.return_value.status_code = 500

    mock_instance = MagicMock()
    mock_instance.text.return_value = iter([{"title": "D", "href": "http://d.com", "body": "body"}])
    mock_ddgs.return_value.__enter__.return_value = mock_instance

    with patch.dict("os.environ", {"TAVILY_API_KEY": "", "SERPER_API_KEY": ""}, clear=False):
        result = web_search("query", limit=1)

    assert result["provider"] == "duckduckgo"
    assert len(result["results"]) == 1


@patch("requests.get")
def test_web_extract_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.encoding = "utf-8"
    mock_get.return_value.content = b"<html><head><title>T</title></head><body><p>hello</p></body></html>"
    mock_get.return_value.raise_for_status = MagicMock()

    result = web_extract("http://example.com", char_limit=100)
    assert result["status"] == "success"
    assert result["title"] == "T"
    assert "hello" in result["content"]


@patch("requests.get")
def test_web_extract_error(mock_get):
    import requests

    mock_get.side_effect = requests.RequestException("down")
    result = web_extract("http://example.com")
    assert "error" in result


@patch("requests.get")
def test_web_scrape_links_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = '<a href="/page">link</a><a href="#x">skip</a><a href="mailto:a@b">skip2</a>'
    mock_get.return_value.raise_for_status = MagicMock()

    result = web_scrape_links("http://example.com", limit=10)
    assert result["status"] == "success"
    assert result["total_links"] == 1
    assert result["links"][0]["url"] == "http://example.com/page"


@patch("requests.get")
def test_web_scrape_links_error(mock_get):
    import requests

    mock_get.side_effect = requests.RequestException("down")
    result = web_scrape_links("http://example.com")
    assert "error" in result
