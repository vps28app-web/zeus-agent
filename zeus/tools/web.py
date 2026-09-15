"""Web search and LLM-friendly content extraction tools."""

import os
import re
import urllib.parse
from typing import Any, Dict, List

from zeus.core.registry import register_tool


# Block URLs that target internal/private infrastructure (SSRF protection).
BLOCKED_HOST_PATTERNS = [
    re.compile(r"^localhost$", re.IGNORECASE),
    re.compile(r"^127\.\d+\.\d+\.\d+$"),
    re.compile(r"^10\.\d+\.\d+\.\d+$"),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+$"),
    re.compile(r"^192\.168\.\d+\.\d+$"),
    re.compile(r"^169\.254\.\d+\.\d+$"),
    re.compile(r"^0\."),
    re.compile(r"^::1$"),
    re.compile(r"^fc00:", re.IGNORECASE),
    re.compile(r"^fe80:", re.IGNORECASE),
    re.compile(r"\.local$", re.IGNORECASE),
]


def _is_url_allowed(url: str) -> bool:
    """Return False for private/internal URLs to mitigate SSRF."""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname or ""
        for pattern in BLOCKED_HOST_PATTERNS:
            if pattern.match(hostname):
                return False
        # Block file:// and other non-http schemes
        if parsed.scheme not in ("http", "https"):
            return False
        return True
    except Exception:
        return False


def web_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search the web using DuckDuckGo or configured search APIs (Tavily, Serper, Brave)."""
    # 1. Check Tavily API
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = [
                    {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("content")}
                    for item in data.get("results", [])
                ]
                return {"query": query, "provider": "tavily", "results": results}
        except Exception:
            pass

    # 2. Check Serper API
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        try:
            import requests
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                json={"q": query, "num": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = [
                    {"title": item.get("title"), "url": item.get("link"), "snippet": item.get("snippet")}
                    for item in data.get("organic", [])
                ]
                return {"query": query, "provider": "serper", "results": results}
        except Exception:
            pass

    # 3. Free Fallback: DuckDuckGo (DDGS)
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            ddg_results = ddgs.text(query, max_results=limit)
            if ddg_results:
                for item in ddg_results:
                    results.append({
                        "title": item.get("title"),
                        "url": item.get("href"),
                        "snippet": item.get("body"),
                    })
        return {"query": query, "provider": "duckduckgo", "results": results}
    except Exception as e:
        return {
            "query": query,
            "provider": "error",
            "results": [],
            "error": f"Search failed: {e}",
        }


def web_extract(url: str, char_limit: int = 15000) -> Dict[str, Any]:
    """Extract readable LLM-friendly Markdown content from a URL."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (private/internal address)."}
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ZeusAgent/1.0"
            )
        }
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()

        encoding = response.encoding or "utf-8"
        soup = BeautifulSoup(response.content.decode(encoding, errors="ignore"), "html.parser")

        # Decompose noise tags
        for tag in soup(["script", "style", "nav", "footer", "iframe", "svg", "noscript", "form", "aside"]):
            tag.decompose()

        page_title = soup.title.string.strip() if soup.title and soup.title.string else None

        # Convert to Markdown using html2text if available
        markdown_text = ""
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = False
            h.body_width = 0
            markdown_text = h.handle(str(soup))
        except Exception:
            markdown_text = soup.get_text(separator="\n", strip=True)

        cleaned_text = markdown_text.strip()
        truncated = len(cleaned_text) > char_limit
        final_content = cleaned_text[:char_limit]

        return {
            "status": "success",
            "url": url,
            "title": page_title,
            "char_count": len(final_content),
            "truncated": truncated,
            "content": final_content,
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


def web_scrape_links(url: str, limit: int = 30) -> Dict[str, Any]:
    """Extract hyperlinked URLs and anchor text from a webpage."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (private/internal address)."}
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ZeusAgent/1.0"
            )
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        links: List[Dict[str, str]] = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = urllib.parse.urljoin(url, href)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                links.append({"text": text or full_url, "url": full_url})
                if len(links) >= limit:
                    break

        return {
            "status": "success",
            "url": url,
            "total_links": len(links),
            "links": links,
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


register_tool(
    name="web_search",
    description="Search the web for real-time information (supports DuckDuckGo, Tavily, Serper).",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query text."},
            "limit": {"type": "integer", "description": "Max results count.", "default": 5},
        },
        "required": ["query"],
    },
    handler=web_search,
    tags=["web", "research"],
)

register_tool(
    name="web_extract",
    description="Extract readable content from a URL converted into clean LLM-friendly Markdown.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Target webpage URL."},
            "char_limit": {"type": "integer", "description": "Max characters of content to return.", "default": 15000},
        },
        "required": ["url"],
    },
    handler=web_extract,
    tags=["web", "research"],
)

register_tool(
    name="web_scrape_links",
    description="Extract all hyperlinks and anchor texts from a webpage URL.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Target webpage URL."},
            "limit": {"type": "integer", "description": "Max links to return.", "default": 30},
        },
        "required": ["url"],
    },
    handler=web_scrape_links,
    tags=["web", "research"],
)
