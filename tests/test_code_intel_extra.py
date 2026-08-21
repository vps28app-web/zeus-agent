"""Additional tests for zeus/tools/code_intel.py."""

import pytest

from zeus.tools.code_intel import (
    _permissions,
    codebase_symbol_map,
    find_symbol,
    parse_code_structure,
)


@pytest.fixture(autouse=True)
def setup_permissions(tmp_path):
    _permissions.file_level = "unrestricted"
    _permissions.project_dir = tmp_path
    return tmp_path


def test_parse_code_structure_non_python(tmp_path):
    f = tmp_path / "app.js"
    f.write_text("function greet(name) {\n  return `Hello ${name}`;\n}\nclass User {\n  constructor(name) {\n    this.name = name;\n  }\n}\n", encoding="utf-8")

    res = parse_code_structure(str(f))
    assert "error" not in res
    assert any(symbol["name"] == "greet" for symbol in res["functions"])
    assert any(symbol["name"] == "User" for symbol in res["classes"])


def test_parse_code_structure_permission_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(_permissions, "can_read_file", lambda _path: False)
    f = tmp_path / "secret.py"
    f.write_text("x = 1\n", encoding="utf-8")

    res = parse_code_structure(str(f))
    assert "error" in res
    assert "not allowed" in res["error"]


def test_find_symbol_case_insensitive(tmp_path):
    (tmp_path / "module.py").write_text(
        "def MyFunction():\n    pass\nclass MyClass:\n    def MyMethod(self):\n        pass\n",
        encoding="utf-8",
    )

    res = find_symbol("myfunction", path=str(tmp_path))
    assert res["total_matches"] == 1
    assert res["matches"][0]["name"] == "MyFunction"


def test_find_symbol_no_matches(tmp_path):
    (tmp_path / "empty.py").write_text("x = 1\n", encoding="utf-8")
    res = find_symbol("nonexistent", path=str(tmp_path))
    assert res["total_matches"] == 0
    assert res["matches"] == []


def test_codebase_symbol_map_honors_max_files(tmp_path):
    for i in range(5):
        (tmp_path / f"file{i}.py").write_text(f"def fn{i}():\n    pass\n", encoding="utf-8")

    res = codebase_symbol_map(str(tmp_path), max_files=2)
    assert res["files_scanned"] == 2


def test_codebase_symbol_map_ignores_non_code_files(tmp_path):
    (tmp_path / "readme.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "script.py").write_text("def run():\n    pass\n", encoding="utf-8")

    res = codebase_symbol_map(str(tmp_path))
    paths = [item["path"] for item in res["symbol_map"]]
    assert "script.py" in paths
    assert "readme.md" not in paths
