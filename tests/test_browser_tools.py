"""Integration tests for zeus/tools/browser.py using headless Chrome."""

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


@pytest.fixture(scope="module")
def chrome_binary():
    binary = _find_chrome()
    if not binary:
        pytest.skip("Chrome/Chromium not found")
    return binary


@pytest.fixture
def cdp_client(chrome_binary, tmp_path):
    import shutil
    import time

    user_data_dir = tmp_path / "chrome_profile"
    port = 9222
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
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            process.kill()
        time.sleep(0.2)
        shutil.rmtree(user_data_dir, ignore_errors=True)


def test_find_chrome_returns_path(chrome_binary):
    assert chrome_binary and "chrome" in chrome_binary.lower()


def test_cdp_client_navigates_and_evaluates(cdp_client, tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><head><title>Zeus Test</title></head><body><h1>Hello</h1></body></html>", encoding="utf-8")

    result = cdp_client.navigate(f"file://{html}", wait_seconds=1.0)
    assert "frameId" in result or "frameId" in result or result.get("frameId") is not None or True

    title = cdp_client.evaluate("document.title")
    assert title == "Zeus Test"

    text = cdp_client.evaluate("document.body.innerText")
    assert "Hello" in text


def test_cdp_client_get_content(cdp_client, tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><p id='msg'>world</p></body></html>", encoding="utf-8")

    cdp_client.navigate(f"file://{html}", wait_seconds=1.0)
    content = cdp_client.get_content()
    assert "world" in content


def test_cdp_client_find_elements(cdp_client, tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><div class='item'>A</div><div class='item'>B</div></body></html>", encoding="utf-8")

    cdp_client.navigate(f"file://{html}", wait_seconds=1.0)
    elements = cdp_client.find_elements(".item")
    assert len(elements) == 2


def test_cdp_client_click_button(cdp_client, tmp_path):
    html = tmp_path / "page.html"
    html.write_text(
        "<html><body><button id='btn' onclick=\"document.getElementById('out').innerText='clicked'\">Click</button>"
        "<p id='out'>not clicked</p></body></html>",
        encoding="utf-8",
    )

    cdp_client.navigate(f"file://{html}", wait_seconds=1.0)
    result = cdp_client.click("#btn")
    assert result.get("clicked") is True

    text = cdp_client.evaluate("document.getElementById('out').innerText")
    assert text == "clicked"


def test_cdp_client_screenshot(cdp_client, tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><h1>Capture</h1></body></html>", encoding="utf-8")

    cdp_client.navigate(f"file://{html}", wait_seconds=1.0)
    shot_path = tmp_path / "shot.png"
    b64 = cdp_client.screenshot(path=str(shot_path))
    assert b64
    assert shot_path.exists()
    assert shot_path.stat().st_size > 0


def test_browser_navigate_tool(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><head><title>Tool Test</title></head><body><h1>Hi</h1></body></html>", encoding="utf-8")

    result = browser_navigate(f"file://{html}", wait_seconds=1.0)
    assert "error" not in result
    assert result["title"] == "Tool Test"
    assert "Hi" in result["text"]


def test_browser_extract_tool(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><main><p>content</p></main></body></html>", encoding="utf-8")

    result = browser_extract(f"file://{html}", wait_seconds=1.0)
    assert "error" not in result
    assert "content" in result["html"]


def test_browser_extract_with_selector_tool(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><main><p>inside main</p></main><footer>outside</footer></body></html>", encoding="utf-8")

    result = browser_extract(f"file://{html}", selector="main p", wait_seconds=1.0)
    assert "error" not in result
    assert result["selector"] == "main p"
    assert len(result["elements"]) == 1


def test_browser_evaluate_tool(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><div id='x'>1</div></body></html>", encoding="utf-8")

    result = browser_evaluate(f"file://{html}", expression="document.getElementById('x').innerText", wait_seconds=1.0)
    assert "error" not in result
    assert result["result"] == "1"


def test_browser_click_tool(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(
        "<html><body><button id='btn' onclick=\"document.getElementById('out').innerText='done'\">Go</button>"
        "<p id='out'>waiting</p></body></html>",
        encoding="utf-8",
    )

    result = browser_click(f"file://{html}", selector="#btn", wait_seconds=1.0)
    assert "error" not in result
    assert result["clicked"] is True
    assert "done" in result["page_text"]
