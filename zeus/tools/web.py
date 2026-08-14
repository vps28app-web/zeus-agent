"""Web search and content extraction tools."""

import os
from typing import Any, Dict, List

from zeus.core.registry import register_tool


def web_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """Simple web search using configured search backend."""
    # Placeholder: real implementation would use serper, brave, or similar
    return {
        "query": query,
        "results": [],
        "note": "Web search requires a search API key (SERPER_API_KEY or BRAVE_API_KEY).",
    }


def web_extract(url: str, char_limit: int = 15000) -> Dict[str, Any]:
    """Extract content from a URL."""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "ZeusAgent/0.1.0"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return {"url": url, "title": soup.title.string if soup.title else None, "content": text[:char_limit]}
    except Exception as e:
        return {"url": url, "error": str(e)}


register_tool(
    name="web_search",
    description="Search the web for a query.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    handler=web_search,
    required_env=["SERPER_API_KEY"],
)

register_tool(
    name="web_extract",
    description="Extract readable content from a URL.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "char_limit": {"type": "integer", "default": 15000},
        },
        "required": ["url"],
    },
    handler=web_extract,
)
