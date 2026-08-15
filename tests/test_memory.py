"""Unit tests for the memory system."""

from pathlib import Path
import tempfile
from zeus.memory.store import MemoryStore
from zeus.tools.memory_tools import remember, recall, search_memory, list_memories, forget_memory


def test_memory_store_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = Path(tmpdir) / "test_memory.json"
        store = MemoryStore(path=json_file)
        store.use_sqlite = False

        store.append("user_profile", "Usuário prefere código em Python")
        store.append("user_preferences", "Usar modo escuro no terminal")
        store.append("general", "Projeto Zeus iniciado")

        # Test search
        results = store.search("Python")
        assert len(results) == 1
        assert results[0]["key"] == "user_profile"

        # Test summary context
        summary = store.get_summary_context()
        assert "user_profile" in summary
        assert "Python" in summary

        # Test keys
        keys = store.keys()
        assert "user_profile" in keys
        assert "user_preferences" in keys

        # Test clear
        store.clear("general")
        assert store.get("general") == []


def test_memory_tools_integration():
    remember("Test note for unit testing", key="unit_test_key")
    res_recall = recall("unit_test_key")
    assert "Test note for unit testing" in res_recall["notes"]

    res_search = search_memory("unit testing")
    assert res_search["count"] >= 1

    res_list = list_memories()
    assert "unit_test_key" in res_list["keys"]

    res_forget = forget_memory("unit_test_key")
    assert res_forget["deleted"] is True
    assert recall("unit_test_key")["notes"] == []
