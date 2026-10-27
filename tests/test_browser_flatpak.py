from types import SimpleNamespace
from unittest.mock import patch

from zeus.tools.browser import _find_chrome, _start_chrome


def test_find_chrome_discovers_flatpak_google_chrome(tmp_path):
    def which(command):
        return "/usr/bin/flatpak" if command == "flatpak" else None

    with patch("zeus.tools.browser.shutil.which", side_effect=which):
        with patch(
            "zeus.tools.browser.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="com.google.Chrome\n", stderr=""),
        ):
            assert _find_chrome(tmp_path) == [
                "/usr/bin/flatpak",
                "run",
                f"--filesystem={tmp_path.resolve()}",
                "com.google.Chrome",
            ]


def test_start_chrome_expands_flatpak_command_prefix(tmp_path):
    prefix = [
        "/usr/bin/flatpak",
        "run",
        f"--filesystem={tmp_path.resolve()}",
        "com.google.Chrome",
    ]
    with patch("zeus.tools.browser._find_chrome", return_value=prefix) as find_chrome:
        with patch("zeus.tools.browser.subprocess.Popen") as popen:
            _start_chrome(tmp_path, port=19222)
    find_chrome.assert_called_once_with(tmp_path)
    command = popen.call_args.args[0]
    assert command[:4] == prefix
    assert "--headless=new" in command
    assert f"--user-data-dir={tmp_path}" in command
