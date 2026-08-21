"""Unit tests for zeus/mcp/gemini.py."""

from unittest.mock import MagicMock, patch

from zeus.mcp.gemini import (
    gemini_code_execution,
    gemini_search_grounding,
    register_gemini_mcp_tools,
)


def test_gemini_search_grounding_missing_key():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
        result = gemini_search_grounding("news today")
    assert "error" in result
    assert "not set" in result["error"]


@patch("requests.post")
def test_gemini_search_grounding_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Result text"}]},
            "groundingMetadata": {
                "webSearchQueries": ["query1"],
                "groundingChunks": [{"web": {"title": "Source", "uri": "http://example.com"}}],
            },
        }]
    }
    mock_post.return_value.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}, clear=False):
        result = gemini_search_grounding("test")

    assert result["status"] == "success"
    assert result["answer"] == "Result text"
    assert result["search_queries"] == ["query1"]
    assert result["sources"][0]["url"] == "http://example.com"


@patch("requests.post")
def test_gemini_search_grounding_no_candidates(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"candidates": []}
    mock_post.return_value.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}, clear=False):
        result = gemini_search_grounding("test")

    assert "error" in result


@patch("requests.post")
def test_gemini_code_execution_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "Output"},
                    {"executableCode": {"code": "print(1)"}},
                    {"codeExecutionResult": {"outcome": "OK", "output": "1"}},
                ]
            }
        }]
    }
    mock_post.return_value.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}, clear=False):
        result = gemini_code_execution("print(1)")

    assert result["status"] == "success"
    assert "Output" in result["result"]
    assert "OK" in result["result"]


def test_register_gemini_mcp_tools_does_not_crash():
    register_gemini_mcp_tools()
