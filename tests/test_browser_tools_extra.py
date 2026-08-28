"""Additional unit tests for zeus/tools/browser.py error paths."""

import json
import subprocess
from unittest import mock

import pytest

from zeus.tools.browser import (
    CDPClient,
    _find_chrome,
    _get_ws_url,
    _kill_chrome_tree,
    _start_chrome,
    _with_browser,
    browser_click,
    browser_evaluate,
    browser_extract,
    browser_navigate,
)


class TestFindChrome:
    def test_find_chrome_not_found(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            assert _find_chrome() is None

    def test_find_chrome_exception_returns_none(self):
        with mock.patch("subprocess.run", side_effect=OSError("nope")):
            assert _find_chrome() is None


class TestStartChrome:
    def test_start_chrome_raises_when_not_found(self, tmp_path):
        with mock.patch("zeus.tools.browser._find_chrome", return_value=None):
            with pytest.raises(RuntimeError, match="Chrome/Chromium not found"):
                _start_chrome(tmp_path)

    def test_start_chrome_launches_process(self, tmp_path):
        fake_binary = "/usr/bin/google-chrome"
        fake_proc = mock.Mock(spec=subprocess.Popen)
        with mock.patch("zeus.tools.browser._find_chrome", return_value=fake_binary):
            with mock.patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
                result = _start_chrome(tmp_path, port=9222)
        assert result is fake_proc
        args = mock_popen.call_args[0][0]
        assert fake_binary in args
        assert "--headless=new" in args
        assert f"--user-data-dir={tmp_path}" in args


class TestGetWsUrl:
    def test_get_ws_url_success(self):
        mock_response = mock.Mock()
        mock_response.read.return_value = json.dumps({"webSocketDebuggerUrl": "ws://test"}).encode()
        mock_cm = mock.Mock()
        mock_cm.__enter__ = mock.Mock(return_value=mock_response)
        mock_cm.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_cm):
            assert _get_ws_url(port=9222, timeout=1) == "ws://test"

    def test_get_ws_url_timeout(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("refused")):
            with pytest.raises(RuntimeError, match="Could not connect to Chrome CDP"):
                _get_ws_url(port=9222, timeout=1)


class TestCDPClient:
    def test_cdp_client_command_error(self):
        fake_ws = mock.Mock()
        fake_ws.recv.return_value = json.dumps({"id": 1, "error": {"message": "boom"}})
        with mock.patch("websocket.create_connection", return_value=fake_ws):
            client = object.__new__(CDPClient)
            client.ws = fake_ws
            client._id = 0
            client._session_id = None
            with pytest.raises(RuntimeError, match="CDP error"):
                client.command("Page.enable")

    def test_cdp_client_evaluate_exception(self):
        fake_ws = mock.Mock()
        fake_ws.recv.return_value = json.dumps({
            "id": 1,
            "result": {"exceptionDetails": {"text": "SyntaxError"}}
        })
        with mock.patch("websocket.create_connection", return_value=fake_ws):
            client = object.__new__(CDPClient)
            client.ws = fake_ws
            client._id = 0
            client._session_id = None
            with pytest.raises(RuntimeError, match="SyntaxError"):
                client.evaluate("bad js")

    def test_cdp_client_click_element_not_found(self):
        fake_ws = mock.Mock()
        responses = [
            {"id": 1, "result": {"root": {"nodeId": 1}}},
            {"id": 2, "result": {"nodeId": 0}},
        ]
        fake_ws.recv.side_effect = [json.dumps(r) for r in responses]
        with mock.patch("websocket.create_connection", return_value=fake_ws):
            client = object.__new__(CDPClient)
            client.ws = fake_ws
            client._id = 0
            client._session_id = None
            result = client.click("#missing")
            assert "error" in result
            assert "not found" in result["error"]

    def test_cdp_client_close_swallows_errors(self):
        fake_ws = mock.Mock()
        fake_ws.close.side_effect = RuntimeError("nope")
        with mock.patch("websocket.create_connection", return_value=fake_ws):
            client = object.__new__(CDPClient)
            client.ws = fake_ws
            client._id = 0
            client._session_id = None
            client.close()


class TestKillChromeTree:
    def test_kill_chrome_tree_normal(self):
        fake_proc = mock.Mock(spec=subprocess.Popen)
        fake_proc.pid = 1234
        with mock.patch("os.getpgid", return_value=1234):
            with mock.patch("os.killpg") as mock_killpg:
                with mock.patch("signal.SIGTERM", 15):
                    _kill_chrome_tree(fake_proc)
        mock_killpg.assert_called_once_with(1234, 15)

    def test_kill_chrome_tree_fallback_to_kill(self):
        fake_proc = mock.Mock(spec=subprocess.Popen)
        fake_proc.pid = 1234
        fake_proc.wait.side_effect = [Exception("timeout"), None]
        with mock.patch("os.getpgid", side_effect=[1234, Exception("dead")]):
            with mock.patch("os.killpg"):
                with mock.patch("signal.SIGTERM", 15):
                    with mock.patch("signal.SIGKILL", 9):
                        _kill_chrome_tree(fake_proc)
        fake_proc.kill.assert_called_once()


class TestWithBrowser:
    def test_with_browser_returns_error_on_failure(self):
        with mock.patch("zeus.tools.browser._start_chrome", side_effect=RuntimeError("no chrome")):
            result = _with_browser(lambda c: {"ok": True})
        assert "error" in result
        assert "no chrome" in result["error"]

    def test_with_browser_runs_action(self):
        fake_client = mock.Mock()
        fake_client.close = mock.Mock()
        fake_proc = mock.Mock(spec=subprocess.Popen)
        fake_proc.pid = 1234
        with mock.patch("zeus.tools.browser._start_chrome", return_value=fake_proc):
            with mock.patch("zeus.tools.browser._get_ws_url", return_value="ws://test"):
                with mock.patch("zeus.tools.browser.CDPClient", return_value=fake_client):
                    with mock.patch("zeus.tools.browser._kill_chrome_tree") as mock_kill:
                        result = _with_browser(lambda c, x: {"result": x}, "value")
        assert result == {"result": "value"}
        fake_client.close.assert_called_once()
        mock_kill.assert_called_once_with(fake_proc)


class TestToolErrorPaths:
    def test_browser_navigate_error(self):
        with mock.patch("zeus.tools.browser._start_chrome", side_effect=RuntimeError("boom")):
            result = browser_navigate("http://example.com")
        assert "error" in result

    def test_browser_extract_error(self):
        with mock.patch("zeus.tools.browser._start_chrome", side_effect=RuntimeError("boom")):
            result = browser_extract("http://example.com")
        assert "error" in result

    def test_browser_click_error(self):
        with mock.patch("zeus.tools.browser._start_chrome", side_effect=RuntimeError("boom")):
            result = browser_click("http://example.com", "#btn")
        assert "error" in result

    def test_browser_evaluate_error(self):
        with mock.patch("zeus.tools.browser._start_chrome", side_effect=RuntimeError("boom")):
            result = browser_evaluate("http://example.com", "1+1")
        assert "error" in result
