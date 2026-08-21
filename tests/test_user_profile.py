"""Unit tests for zeus/memory/user_profile.py and zeus/tools/user_profile_tools.py."""


import pytest

from zeus.db.connection import init_db
from zeus.memory.user_profile import UserProfileStore, extract_profile_signals
from zeus.tools import user_profile_tools


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture
def store(db_path):
    from zeus.db.repository import UserProfileRepository

    return UserProfileStore(repo=UserProfileRepository(db_path))


def test_extract_profile_signals_name():
    text = "Meu nome é Valdeir"
    signals = extract_profile_signals(text)
    assert signals["name"] == "Valdeir"


def test_extract_profile_signals_preferences_and_habits():
    text = "Eu gosto de Python. Costumo acordar cedo."
    signals = extract_profile_signals(text)
    assert any("Python" in p for p in signals["preferences"])
    assert any("acordar cedo" in h for h in signals["habits"])


def test_extract_profile_signals_no_match():
    signals = extract_profile_signals("apenas uma mensagem qualquer")
    assert signals["name"] is None
    assert signals["preferences"] == []
    assert signals["habits"] == []


def test_user_profile_store_learn_from_message(store):
    result = store.learn_from_message("u1", "telegram", "Meu nome é Zeus e eu gosto de café")
    assert result["updated"] is True
    assert result["signals"]["name"] == "Zeus"

    profile = store.get_profile("u1")
    assert profile is not None
    assert profile["name"] == "Zeus"
    assert any("café" in p for p in profile["preferences"])


def test_user_profile_store_ignores_assistant_messages(store):
    result = store.learn_from_message("u1", "telegram", "Meu nome é Zeus", role="assistant")
    assert result["updated"] is False


def test_user_profile_store_format_context(store):
    store.learn_from_message("u2", None, "Meu nome é Hera. Eu gosto de chá.")
    context = store.format_context("u2")
    assert "Hera" in context
    assert "chá" in context


def test_user_profile_store_forget_user(store):
    store.learn_from_message("u3", None, "Meu nome é Atena")
    store.forget_user("u3")
    assert store.get_profile("u3") is None


def test_remember_user_tool_uses_repo(db_path, monkeypatch):
    from zeus.db.repository import UserProfileRepository
    from zeus.tools.user_profile_tools import _store

    _store._repo = UserProfileRepository(db_path)

    res = user_profile_tools.remember_user("Valdeir", user_id="u4", category="name")
    assert res["stored"] is True
    profile = _store.get_profile("u4")
    assert profile is not None
    assert profile["name"] == "Valdeir"


def test_remember_user_tool_invalid_category():
    res = user_profile_tools.remember_user("x", category="invalid")
    assert "error" in res


def test_recall_user_tool_found(db_path, monkeypatch):
    from zeus.db.repository import UserProfileRepository
    from zeus.tools.user_profile_tools import _store

    _store._repo = UserProfileRepository(db_path)
    _store._repo.upsert("u5", name="Poseidon")

    res = user_profile_tools.recall_user("u5")
    assert res["found"] is True
    assert res["profile"]["name"] == "Poseidon"


def test_recall_user_tool_not_found(db_path, monkeypatch):
    from zeus.db.repository import UserProfileRepository
    from zeus.tools.user_profile_tools import _store

    _store._repo = UserProfileRepository(db_path)
    res = user_profile_tools.recall_user("unknown-user")
    assert res["found"] is False
