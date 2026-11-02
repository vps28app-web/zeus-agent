"""Google Gemini model provider implementation."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from zeus.providers.base import check_response_status, with_retries


def sanitize_gemini_schema(schema: Any) -> Any:
    """Sanitize JSON Schema for Google Gemini API functionDeclarations.

    Gemini API strict schema validator rejects 'additionalProperties', '$ref', '$schema', 'title', 'default', 'examples', etc.
    It also strictly requires 'items' for array types and 'properties' for object types.
    """
    if not isinstance(schema, dict):
        return schema

    allowed_keys = {"type", "properties", "required", "description", "enum", "items", "format"}
    cleaned = {}

    for k, v in schema.items():
        if k not in allowed_keys:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {prop_k: sanitize_gemini_schema(prop_v) for prop_k, prop_v in v.items()}
        elif k == "items":
            if isinstance(v, dict):
                cleaned[k] = sanitize_gemini_schema(v)
            elif isinstance(v, list) and v:
                cleaned[k] = sanitize_gemini_schema(v[0])
            else:
                cleaned[k] = {"type": "string"}
        else:
            cleaned[k] = v

    if "type" not in cleaned:
        if "properties" in cleaned:
            cleaned["type"] = "object"
        elif "items" in cleaned:
            cleaned["type"] = "array"
        else:
            cleaned["type"] = "string"

    if cleaned.get("type") == "array" and "items" not in cleaned:
        cleaned["items"] = {"type": "string"}

    if cleaned.get("type") == "object" and "properties" not in cleaned:
        cleaned["properties"] = {}

    return cleaned


def build_gemini_payload(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the Gemini generateContent request payload."""
    contents = []
    system_parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append({"text": content})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
        else:
            contents.append({"role": "user", "parts": [{"text": content}]})

    payload: Dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    if tools:
        fn_decls = []
        for t in tools:
            fn = t.get("function", {})
            fn_decl = {
                "name": fn.get("name", ""),
                "description": fn.get("description", "") or "No description provided.",
            }
            params = fn.get("parameters")
            if params:
                fn_decl["parameters"] = sanitize_gemini_schema(params)
            fn_decls.append(fn_decl)
        payload["tools"] = [{"functionDeclarations": fn_decls}]
    return payload


def send_gemini_request(
    model: str,
    payload: Dict[str, Any],
    api_key: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a request to the Gemini Generative Language API."""
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    url = f"{base_url}/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    elif api_key:
        headers["x-goog-api-key"] = api_key
    else:
        raise RuntimeError("No API key or OAuth authorization available for Google Gemini.")

    def _call() -> Any:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        check_response_status(response, "Google Gemini")
        return response

    response = with_retries(_call)
    return response.json()


def google_api_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Google Gemini via API key (GOOGLE_API_KEY or GEMINI_API_KEY)."""
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    env_paths = [zeus_home / ".env", Path.cwd() / ".env"]
    install_dir = os.getenv("ZEUS_INSTALL_DIR")
    if install_dir:
        env_paths.append(Path(install_dir) / ".env")
    for path in env_paths:
        if path.exists():
            load_dotenv(path, override=False)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ou GOOGLE_API_KEY nao configurada. "
            "Use o provider 'google_auth' para autenticacao via navegador."
        )

    payload = build_gemini_payload(messages, tools)
    return send_gemini_request(model, payload, api_key=api_key)


def google_auth_chat(
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    model: str,
    stream: bool = False,
) -> Any:
    """Google Gemini via OAuth 2.0 browser authentication."""
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    env_paths = [zeus_home / ".env", Path.cwd() / ".env"]
    install_dir = os.getenv("ZEUS_INSTALL_DIR")
    if install_dir:
        env_paths.append(Path(install_dir) / ".env")
    for path in env_paths:
        if path.exists():
            load_dotenv(path, override=False)

    try:
        from zeus.core.google_oauth_desktop import get_access_token
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Falha ao carregar modulo OAuth: {exc}") from exc

    access_token = get_access_token()
    if not access_token:
        raise RuntimeError(
            "Token OAuth do Google nao disponivel. Execute '/auth google' no CLI."
        )

    payload = build_gemini_payload(messages, tools)
    try:
        return send_gemini_request(model, payload, auth_header=f"Bearer {access_token}")
    except RuntimeError as exc:
        err_msg = str(exc)
        if "401" in err_msg:
            access_token = get_access_token(force_new=True)
            return send_gemini_request(model, payload, auth_header=f"Bearer {access_token}")
        raise
