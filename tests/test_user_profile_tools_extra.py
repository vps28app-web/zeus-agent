"""Additional unit tests for zeus/tools/user_profile_tools.py."""


import pytest

from zeus.db.connection import init_db
from zeus.tools import user_profile_tools


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


@pytest.fixture(autouse=True)
def reset_store(db_path, monkeypatch):
    from zeus.db.repository import UserProfileRepository

    user_profile_tools._store._repo = UserProfileRepository(db_path)


def test_remember_user_habit(db_path):
    res = user_profile_tools.remember_user("Acordar cedo", user_id="u1", category="habits")
    assert res["stored"] is True
    profile = user_profile_tools._store.get_profile("u1")
    assert profile is not None
    assert any("Acordar" in h for h in profile["habits"])


def test_remember_user_preference(db_path):
    res = user_profile_tools.remember_user("Python", user_id="u2", category="preferences")
    assert res["stored"] is True
    profile = user_profile_tools._store.get_profile("u2")
    assert profile is not None
    assert "Python" in profile["preferences"]


def test_recall_user_found(db_path):
    user_profile_tools._store._repo.upsert("u3", name="Zeus")
    res = user_profile_tools.recall_user("u3")
    assert res["found"] is True
    assert res["profile"]["name"] == "Zeus"
