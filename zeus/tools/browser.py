"""Browser automation tool using Chrome DevTools Protocol (CDP).

Spins up a headless Chrome instance, connects via CDP, and exposes
common automation primitives without requiring selenium.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from zeus.core.registry import register_tool


def _is_url_allowed(url: str) -> bool:
    """Allow only http/https URLs; block file://, javascript:, data:, etc."""
    try:
        scheme = urlparse(url).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False


def _find_chrome(user_data_dir: Optional[Path] = None) -> Optional[Union[str, List[str]]]:
    """Locate a Chrome/Chromium executable or a narrowly scoped Flatpak prefix."""
    candidates = ["google-chrome", "chromium", "chromium-browser", "chrome"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    flatpak = shutil.which("flatpak")
    if not flatpak:
        return None
    try:
        result = subprocess.run(
            [flatpak, "list", "--app", "--columns=application"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        installed = set(result.stdout.splitlines())
        for app_id in ("com.google.Chrome", "org.chromium.Chromium"):
            if app_id in installed:
                args = [flatpak, "run"]
                if user_data_dir is not None:
                    # Grant access only to this browser's profile, never all of /tmp.
                    args.append(f"--filesystem={user_data_dir.resolve()}")
                return [*args, app_id]
    except Exception:
        return None
    return None


def _start_chrome(user_data_dir: Path, port: int = 9222) -> subprocess.Popen:
    """Launch headless Chrome with remote debugging enabled."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    binary = _find_chrome(user_data_dir)
    if not binary:
        raise RuntimeError("Chrome/Chromium not found in PATH or Flatpak")

    args = [binary] if isinstance(binary, str) else list(binary)
    args.extend([
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ])
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _get_ws_url(port: int = 9222, timeout: int = 10) -> str:
    """Fetch the WebSocket debugger URL from Chrome."""
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(  # nosec B310
                f"http://127.0.0.1:{port}/json/version", timeout=2
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["webSocketDebuggerUrl"]
        except Exception as e:
            last_error = str(e)
            time.sleep(0.3)
    raise RuntimeError(f"Could not connect to Chrome CDP: {last_error}")


class CDPClient:
    """Minimal blocking CDP client using a WebSocket connection."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._id = 0
        self._session_id: Optional[str] = None
        # Lazy import so Zeus works even without websocket-client installed
        import websocket

        self.ws = websocket.create_connection(ws_url)
        self._targets = self._command("Target.getTargets")
        # Attach to the first page target
        if self._targets and self._targets.get("targetInfos"):
            page_targets = [t for t in self._targets["targetInfos"] if t["type"] == "page"]
            if page_targets:
                attach = self._command(
                    "Target.attachToTarget",
                    targetId=page_targets[0]["targetId"],
                    flatten=True,
                )
                self._session_id = attach.get("sessionId")

    def _command(self, method: str, **params) -> Any:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params}
        payload = json.dumps(msg)
        self.ws.send(payload)

        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result")
            # ignore events

    def command(self, method: str, **params) -> Any:
        """Send a CDP command within the attached target session."""
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params}
        if self._session_id:
            msg["sessionId"] = self._session_id
        self.ws.send(json.dumps(msg))

        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"CDP error: {data['error']}")
                return data.get("result")
            # ignore events

    def navigate(self, url: str, wait_seconds: float = 2.0) -> Dict[str, Any]:
        """Navigate to a URL and wait briefly for the load."""
        self.command("Page.enable")
        result = self.command("Page.navigate", url=url)
        time.sleep(wait_seconds)
        return result

    def get_content(self) -> str:
        """Return the current page HTML."""
        doc = self.command("DOM.getDocument", depth=0)
        root_node_id = doc["root"]["nodeId"]
        html = self.command("DOM.querySelector", nodeId=root_node_id, selector="html")
        outer = self.command("DOM.getOuterHTML", nodeId=html["nodeId"])
        return outer.get("outerHTML", "")

    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in the page context."""
        result = self.command("Runtime.evaluate", expression=expression, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("text", "JS exception"))
        return result.get("result", {}).get("value")

    def find_elements(self, selector: str) -> List[Dict[str, Any]]:
        """Find elements matching a CSS selector and return basic info."""
        doc = self.command("DOM.getDocument", depth=0)
        root_node_id = doc["root"]["nodeId"]
        node_list = self.command("DOM.querySelectorAll", nodeId=root_node_id, selector=selector)
        elements = []
        for node_id in node_list.get("nodeIds", []):
            try:
                attrs = self.command("DOM.getAttributes", nodeId=node_id)
                attr_pairs = attrs.get("attributes", [])
                attr_dict = {attr_pairs[i]: attr_pairs[i + 1] for i in range(0, len(attr_pairs), 2)}
                elements.append({
                    "node_id": node_id,
                    "tag": attr_dict.get("class", ""),
                    "text": attr_dict.get("innerText", ""),
                    "attributes": attr_dict,
                })
            except Exception:
                continue
        return elements

    def click(self, selector: str) -> Dict[str, Any]:
        """Click the first element matching a CSS selector."""
        doc = self.command("DOM.getDocument", depth=0)
        root_node_id = doc["root"]["nodeId"]
        result = self.command("DOM.querySelector", nodeId=root_node_id, selector=selector)
        node_id = result.get("nodeId")
        if not node_id:
            return {"error": f"Element not found: {selector}"}
        # Scroll into view and click via JS
        self.command(
            "DOM.scrollIntoViewIfNeeded",
            nodeId=node_id,
        )
        box = self.command("DOM.getBoxModel", nodeId=node_id)
        quad = box.get("model", {}).get("content")
        if quad and len(quad) >= 8:
            x = (quad[0] + quad[4]) / 2
            y = (quad[1] + quad[5]) / 2
            self.command("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
            self.command("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
            return {"clicked": True, "selector": selector, "x": x, "y": y}
        return {"error": "Could not compute click coordinates"}

    def screenshot(self, path: Optional[str] = None) -> str:
        """Capture a base64 screenshot; optionally save to path."""
        result = self.command("Page.captureScreenshot", format="png")
        b64 = result.get("data", "")
        if path:
            Path(path).expanduser().resolve().write_bytes(base64.b64decode(b64))
        return b64

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def _with_browser(func, *args, **kwargs) -> Dict[str, Any]:
    """Helper to manage a temporary Chrome process and CDP session."""
    port = 9222
    user_data_dir = Path(tempfile.gettempdir()) / f"zeus_browser_{os.getpid()}_{int(time.time())}"
    process = None
    client = None
    try:
        process = _start_chrome(user_data_dir, port=port)
        ws_url = _get_ws_url(port=port)
        client = CDPClient(ws_url)
        return func(client, *args, **kwargs)
    except Exception as e:
        return {"error": str(e)}
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
        if process:
            _kill_chrome_tree(process)
        # Cleanup temp profile
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass


def _kill_chrome_tree(process: subprocess.Popen) -> None:
    """Terminate the whole Chrome process tree started via start_new_session."""
    import signal

    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=3)
    except Exception:
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:
                pass


def browser_navigate(url: str, wait_seconds: float = 2.0) -> Dict[str, Any]:
    """Navigate to a URL and return page title and simplified text."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (only http/https allowed)."}

    def action(client: CDPClient, url: str, wait_seconds: float):
        nav = client.navigate(url, wait_seconds=wait_seconds)
        title = client.evaluate("document.title")
        text = client.evaluate("document.body.innerText")
        return {
            "url": url,
            "title": title,
            "text": text[:4000] if isinstance(text, str) else "",
            "frame_id": nav.get("frameId"),
        }
    return _with_browser(action, url, wait_seconds)


def browser_extract(url: str, selector: Optional[str] = None, wait_seconds: float = 2.0) -> Dict[str, Any]:
    """Extract HTML or text from a page, optionally scoped by CSS selector."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (only http/https allowed)."}

    def action(client: CDPClient, url: str, selector: Optional[str], wait_seconds: float):
        client.navigate(url, wait_seconds=wait_seconds)
        if selector:
            elements = client.find_elements(selector)
            return {"url": url, "selector": selector, "elements": elements[:20]}
        html = client.get_content()
        return {"url": url, "html": html[:8000]}
    return _with_browser(action, url, selector, wait_seconds)


def browser_click(url: str, selector: str, wait_seconds: float = 2.0) -> Dict[str, Any]:
    """Click an element on a page and return simplified page text afterwards."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (only http/https allowed)."}

    def action(client: CDPClient, url: str, selector: str, wait_seconds: float):
        client.navigate(url, wait_seconds=wait_seconds)
        click_result = client.click(selector)
        if "error" in click_result:
            return click_result
        time.sleep(0.5)
        text = client.evaluate("document.body.innerText")
        return {"clicked": True, "url": url, "selector": selector, "page_text": text[:4000] if isinstance(text, str) else ""}
    return _with_browser(action, url, selector, wait_seconds)


def browser_evaluate(url: str, expression: str, wait_seconds: float = 2.0) -> Dict[str, Any]:
    """Navigate to a URL and evaluate a JavaScript expression."""
    if not _is_url_allowed(url):
        return {"url": url, "error": "URL blocked for security reasons (only http/https allowed)."}

    def action(client: CDPClient, url: str, expression: str, wait_seconds: float):
        client.navigate(url, wait_seconds=wait_seconds)
        value = client.evaluate(expression)
        return {"url": url, "expression": expression, "result": value}
    return _with_browser(action, url, expression, wait_seconds)


register_tool(
    name="browser_navigate",
    description="Navigate to a URL using headless Chrome and return title + visible text.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "wait_seconds": {"type": "number", "default": 2.0},
        },
        "required": ["url"],
    },
    handler=browser_navigate,
    tags=["browser", "web"],
)

register_tool(
    name="browser_extract",
    description="Extract HTML or selected elements from a page using headless Chrome.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string", "description": "Optional CSS selector to scope extraction."},
            "wait_seconds": {"type": "number", "default": 2.0},
        },
        "required": ["url"],
    },
    handler=browser_extract,
    tags=["browser", "web"],
)

register_tool(
    name="browser_click",
    description="Click an element on a page using headless Chrome and return page text after click.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string", "description": "CSS selector of the element to click."},
            "wait_seconds": {"type": "number", "default": 2.0},
        },
        "required": ["url", "selector"],
    },
    handler=browser_click,
    tags=["browser", "web"],
)

register_tool(
    name="browser_evaluate",
    description="Evaluate JavaScript on a page using headless Chrome.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "expression": {"type": "string", "description": "JavaScript expression to evaluate."},
            "wait_seconds": {"type": "number", "default": 2.0},
        },
        "required": ["url", "expression"],
    },
    handler=browser_evaluate,
    tags=["browser", "web"],
)
