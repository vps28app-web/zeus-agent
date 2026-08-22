"""Additional unit tests for zeus/memory/user_profile.py."""

import os
from unittest.mock import patch

import pytest

from zeus.db.connection import init_db
from zeus.memory.user_profile import UserProfileStore, extract_profile_signals_with_llm


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def store(db_path):
    from zeus.db.repository import UserProfileRepository

    return UserProfileStore(repo=UserProfileRepository(db_path))


def test_extract_with_llm_returns_empty_on_exception():
    with patch("zeus.core.router.chat", side_effect=Exception("no model")):
        result = extract_profile_signals_with_llm("Eu gosto de Python")
    assert result == {"name": None, "preferences": [], "habits": []}


def test_extract_with_llm_parses_markdown_fenced_json():
    response = {
        "choices": [{
            "message": {
                "content": "```json\n{\"name\": \"Zeus\", \"preferences\": [\"Python\"], \"habits\": []}\n```"
            }
        }]
    }

    with patch("zeus.core.router.chat", return_value=response):
        result = extract_profile_signals_with_llm("Meu nome é Zeus")

    assert result["name"] == "Zeus"
    assert "Python" in result["preferences"]


def test_extract_with_llm_enabled_env(store):
    with patch.dict(os.environ, {"ZEUS_PROFILE_USE_LLM": "true"}, clear=False):
        with patch("zeus.memory.user_profile.extract_profile_signals_with_llm", return_value={
            "name": "LLMName", "preferences": [], "habits": []
        }):
            result = store.learn_from_message("u1", None, "mensagem sem sinais claros")

    assert result["updated"] is True
    assert result["signals"]["name"] == "LLMName"


def test_format_context_empty(store):
    assert store.format_context("no-user") == ""


def test_list_profiles(store):
    store.learn_from_message("u1", None, "Meu nome é Ana")
    store.learn_from_message("u2", None, "Meu nome é Bob")
    profiles = store.list_profiles()
    assert len(profiles) >= 2


def test_learn_no_signals(store):
    result = store.learn_from_message("u1", None, "ok")
    assert result["updated"] is False


def test_user_profile_repository_merge(tmp_path, db_path):
    from zeus.db.repository import UserProfileRepository

    repo = UserProfileRepository(db_path)
    repo.upsert("u1", name="Old", preferences=["a"])
    repo.upsert("u1", name="New", preferences=["b"])

    profile = repo.get("u1")
    assert profile is not None
    assert profile["name"] == "New"
    assert "a" in profile["preferences"]
    assert "b" in profile["preferences"]
