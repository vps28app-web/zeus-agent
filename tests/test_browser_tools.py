"""Integration tests for zeus/tools/browser.py using headless Chrome."""

import http.server
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

from zeus.tools.browser import (
    CDPClient,
    _find_chrome,
    _get_ws_url,
    _start_chrome,
    browser_click,
    browser_evaluate,
    browser_extract,
    browser_navigate,
)

# Ports are allocated per-test to avoid collisions when previous Chrome processes linger.
_PORT_LOCK = threading.Lock()
_NEXT_PORT = 19222


def _allocate_port() -> int:
    global _NEXT_PORT
    with _PORT_LOCK:
        port = _NEXT_PORT
        _NEXT_PORT += 1
        return port


def _kill_chrome(process: subprocess.Popen) -> None:
    """Forcefully terminate a Chrome process tree started by _start_chrome."""
    import os
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


@pytest.fixture(scope="module")
def chrome_binary():
    binary = _find_chrome()
    if not binary:
        pytest.skip("Chrome/Chromium not found")
    return binary


@pytest.fixture(scope="module")
def http_server():
    """Serve files from a temporary directory on 127.0.0.1 using a free port."""
    server_dir = Path(tempfile.mkdtemp(prefix="zeus_browser_test_"))

    class _ReuseTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(
            *args, directory=str(server_dir), **kwargs
        )

    httpd = _ReuseTCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    yield server_dir, port

    httpd.shutdown()
    httpd.server_close()
    shutil.rmtree(server_dir, ignore_errors=True)


@pytest.fixture
def cdp_client(chrome_binary, tmp_path):
    user_data_dir = tmp_path / "chrome_profile"
    port = _allocate_port()
    process = _start_chrome(user_data_dir, port=port)
    client = None
    try:
        ws_url = _get_ws_url(port=port, timeout=10)
        client = CDPClient(ws_url)
        yield client
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
        _kill_chrome(process)
        time.sleep(0.2)
        shutil.rmtree(user_data_dir, ignore_errors=True)


def _write_and_url(http_server, filename: str, content: str) -> str:
    server_dir, port = http_server
    path = server_dir / filename
    path.write_text(content, encoding="utf-8")
    return f"http://127.0.0.1:{port}/{filename}"


def test_find_chrome_returns_path(chrome_binary):
    assert chrome_binary and "chrome" in chrome_binary.lower()


def test_cdp_client_navigates_and_evaluates(cdp_client, http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><head><title>Zeus Test</title></head><body><h1>Hello</h1></body></html>",
    )

    result = cdp_client.navigate(url, wait_seconds=1.0)
    assert result.get("frameId") is not None

    title = cdp_client.evaluate("document.title")
    assert title == "Zeus Test"

    text = cdp_client.evaluate("document.body.innerText")
    assert "Hello" in text


def test_cdp_client_get_content(cdp_client, http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><p id='msg'>world</p></body></html>",
    )

    cdp_client.navigate(url, wait_seconds=1.0)
    content = cdp_client.get_content()
    assert "world" in content


def test_cdp_client_find_elements(cdp_client, http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><div class='item'>A</div><div class='item'>B</div></body></html>",
    )

    cdp_client.navigate(url, wait_seconds=1.0)
    elements = cdp_client.find_elements(".item")
    assert len(elements) == 2


def test_cdp_client_click_button(cdp_client, http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><button id='btn' onclick=\"document.getElementById('out').innerText='clicked'\">Click</button>"
        "<p id='out'>not clicked</p></body></html>",
    )

    cdp_client.navigate(url, wait_seconds=1.0)
    result = cdp_client.click("#btn")
    assert result.get("clicked") is True

    text = cdp_client.evaluate("document.getElementById('out').innerText")
    assert text == "clicked"


def test_cdp_client_screenshot(cdp_client, http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><h1>Capture</h1></body></html>",
    )

    cdp_client.navigate(url, wait_seconds=1.0)
    shot_path = http_server[0] / "shot.png"
    b64 = cdp_client.screenshot(path=str(shot_path))
    assert b64
    assert shot_path.exists()
    assert shot_path.stat().st_size > 0


def test_browser_navigate_tool(http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><head><title>Tool Test</title></head><body><h1>Hi</h1></body></html>",
    )

    result = browser_navigate(url, wait_seconds=1.0)
    assert "error" not in result
    assert result["title"] == "Tool Test"
    assert "Hi" in result["text"]


def test_browser_extract_tool(http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><main><p>content</p></main></body></html>",
    )

    result = browser_extract(url, wait_seconds=1.0)
    assert "error" not in result
    assert "content" in result["html"]


def test_browser_extract_with_selector_tool(http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><main><p>inside main</p></main><footer>outside</footer></body></html>",
    )

    result = browser_extract(url, selector="main p", wait_seconds=1.0)
    assert "error" not in result
    assert result["selector"] == "main p"
    assert len(result["elements"]) == 1


def test_browser_evaluate_tool(http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><div id='x'>1</div></body></html>",
    )

    result = browser_evaluate(url, expression="document.getElementById('x').innerText", wait_seconds=1.0)
    assert "error" not in result
    assert result["result"] == "1"


def test_browser_click_tool(http_server):
    url = _write_and_url(
        http_server,
        "page.html",
        "<html><body><button id='btn' onclick=\"document.getElementById('out').innerText='done'\">Go</button>"
        "<p id='out'>waiting</p></body></html>",
    )

    result = browser_click(url, selector="#btn", wait_seconds=1.0)
    assert "error" not in result
    assert result["clicked"] is True
    assert "done" in result["page_text"]


def test_browser_navigate_blocks_file_url():
    result = browser_navigate("file:///etc/passwd", wait_seconds=0.1)
    assert "error" in result
    assert "blocked" in result["error"].lower()


def test_browser_extract_blocks_javascript_url():
    result = browser_extract("javascript:alert(1)", wait_seconds=0.1)
    assert "error" in result
    assert "blocked" in result["error"].lower()
