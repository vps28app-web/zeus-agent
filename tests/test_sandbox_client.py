"""Tests for the sandbox client helpers."""

import os

from zeus.tools.sandbox_client import safe_environment


def test_safe_environment_filters_secrets():
    os.environ["OPENAI_API_KEY"] = "secret-key"
    os.environ["PATH"] = "/usr/bin"
    env = safe_environment()
    assert "OPENAI_API_KEY" not in env
    assert env.get("PATH") == "/usr/bin"
    del os.environ["OPENAI_API_KEY"]


def test_safe_environment_rejects_extra_secrets():
    env = safe_environment(extra={"MY_TOKEN": "x", "SAFE_VAR": "ok"})
    assert "MY_TOKEN" not in env
    assert env.get("SAFE_VAR") == "ok"
