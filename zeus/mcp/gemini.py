"""Gemini MCP Integration & Built-in Gemini Tools for Zeus."""

import os
from typing import Any, Dict, Optional

import requests

from zeus.core.registry import register_tool


def gemini_search_grounding(query: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Perform Google Web Search grounding using Gemini Generative Language API."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY or GOOGLE_API_KEY not set"}

    active_model = model or os.getenv("ZEUS_MODEL", "gemini-3.6-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": query}]}],
        "tools": [{"googleSearch": {}}],
    }


    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {"error": "No response from Gemini Grounding API"}

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if "text" in p)

        grounding_metadata = candidates[0].get("groundingMetadata", {})
        web_search_queries = grounding_metadata.get("webSearchQueries", [])
        sources = []
        for chunk in grounding_metadata.get("groundingChunks", []):
            web = chunk.get("web", {})
            if web.get("uri"):
                sources.append({"title": web.get("title", ""), "url": web.get("uri")})

        return {
            "status": "success",
            "query": query,
            "answer": text,
            "search_queries": web_search_queries,
            "sources": sources,
        }
    except Exception as e:
        return {"error": f"Gemini search grounding error: {e}"}


def gemini_code_execution(code: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Execute Python code in Google Gemini Serverless Code Execution Sandbox."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY or GOOGLE_API_KEY not set"}

    active_model = model or os.getenv("ZEUS_MODEL", "gemini-3.6-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={api_key}"
    prompt = f"Execute the following Python code:\n```python\n{code}\n```"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"codeExecution": {}}],
    }

    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {"error": "No response from Gemini Code Execution API"}

        parts = candidates[0].get("content", {}).get("parts", [])
        output_parts = []
        for p in parts:
            if "text" in p:
                output_parts.append(p["text"])
            elif "executableCode" in p:
                output_parts.append(f"Code:\n{p['executableCode'].get('code')}")
            elif "codeExecutionResult" in p:
                res = p["codeExecutionResult"]
                output_parts.append(f"Outcome ({res.get('outcome')}):\n{res.get('output')}")

        return {
            "status": "success",
            "result": "\n\n".join(output_parts),
        }
    except Exception as e:
        return {"error": f"Gemini code execution error: {e}"}


def register_gemini_mcp_tools() -> None:
    """Register Gemini MCP tools into Zeus REGISTRY."""
    try:
        register_tool(
            name="gemini_search_grounding",
            description="Perform real-time Google Web Search grounding using Gemini 2.0.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or question requiring live web information"},
                },
                "required": ["query"],
            },
            handler=gemini_search_grounding,
            required_env=["GEMINI_API_KEY"],
            tags=["mcp", "gemini", "search", "web"],
        )
    except Exception:
        pass

    try:
        register_tool(
            name="gemini_code_execution",
            description="Execute Python code inside Google Gemini serverless code execution environment.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code snippet to execute"},
                },
                "required": ["code"],
            },
            handler=gemini_code_execution,
            required_env=["GEMINI_API_KEY"],
            tags=["mcp", "gemini", "code", "sandbox"],
        )
    except Exception:
        pass
