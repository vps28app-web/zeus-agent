"""Additional unit tests for zeus/tools/code_intel.py edge cases."""

import pytest

from zeus.tools.code_intel import _permissions, find_symbol, parse_code_structure


@pytest.fixture(autouse=True)
def setup_permissions(tmp_path):
    _permissions.file_level = "unrestricted"
    _permissions.project_dir = tmp_path
    return tmp_path


def test_parse_code_structure_parse_error(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def foo(\n", encoding="utf-8")
    res = parse_code_structure(str(f))
    assert "error" in res


def test_parse_code_structure_async_methods(tmp_path):
    code = """
class Service:
    async def fetch(self):
        pass

async def main():
    pass
"""
    f = tmp_path / "async.py"
    f.write_text(code, encoding="utf-8")
    res = parse_code_structure(str(f))
    assert len(res["classes"][0]["methods"]) == 1
    assert res["classes"][0]["methods"][0]["name"] == "fetch"
    assert res["functions"][0]["name"] == "main"


def test_parse_code_structure_imports(tmp_path):
    code = "import os\nfrom pathlib import Path\n"
    f = tmp_path / "imports.py"
    f.write_text(code, encoding="utf-8")
    res = parse_code_structure(str(f))
    assert "os" in res["imports"]
    assert "pathlib.Path" in res["imports"]


def test_find_symbol_method_in_class(tmp_path):
    code = "class A:\n    def method_x(self):\n        pass\n"
    (tmp_path / "mod.py").write_text(code, encoding="utf-8")
    res = find_symbol("method_x", path=str(tmp_path))
    assert res["total_matches"] == 1
    assert res["matches"][0]["name"] == "A.method_x"


def test_find_symbol_class(tmp_path):
    code = "class Alpha:\n    pass\n"
    (tmp_path / "mod.py").write_text(code, encoding="utf-8")
    res = find_symbol("alpha", path=str(tmp_path))
    assert res["total_matches"] == 1
    assert res["matches"][0]["name"] == "Alpha"
