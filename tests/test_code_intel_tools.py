"""Unit tests for Code Intelligence tools in zeus/tools/code_intel.py."""

import pytest
from pathlib import Path
from zeus.tools.code_intel import (
    parse_code_structure,
    codebase_symbol_map,
    find_symbol,
    _permissions,
)


@pytest.fixture(autouse=True)
def setup_permissions(tmp_path):
    _permissions.file_level = "unrestricted"
    _permissions.project_dir = tmp_path
    return tmp_path


def test_parse_code_structure_python(tmp_path):
    sample_code = '''"""Sample module docstring."""

class PokerPlayer:
    """Represents a poker player."""
    def __init__(self, name: str, chips: int):
        self.name = name
        self.chips = chips

    def place_bet(self, amount: int) -> int:
        """Place a bet."""
        return amount

def calculate_pot_size(bets: list) -> int:
    """Calculate pot size."""
    return sum(bets)
'''
    f = tmp_path / "poker.py"
    f.write_text(sample_code, encoding="utf-8")

    res = parse_code_structure(str(f))
    assert "error" not in res
    assert len(res["classes"]) == 1
    assert res["classes"][0]["name"] == "PokerPlayer"
    assert len(res["classes"][0]["methods"]) == 2
    assert len(res["functions"]) == 1
    assert res["functions"][0]["name"] == "calculate_pot_size"


def test_codebase_symbol_map(tmp_path):
    (tmp_path / "game.py").write_text("class Game:\n    pass\ndef start_game():\n    pass\n", encoding="utf-8")
    (tmp_path / "utils.py").write_text("def helper_fn():\n    pass\n", encoding="utf-8")

    res = codebase_symbol_map(str(tmp_path))
    assert res["status"] == "success"
    assert res["files_scanned"] >= 2
    paths = [item["path"] for item in res["symbol_map"]]
    assert "game.py" in paths
    assert "utils.py" in paths


def test_find_symbol(tmp_path):
    code = "class Table:\n    def deal_cards(self):\n        pass\n\ndef evaluate_hand():\n    pass\n"
    (tmp_path / "poker_engine.py").write_text(code, encoding="utf-8")

    res_fn = find_symbol("evaluate_hand", path=str(tmp_path))
    assert res_fn["status"] == "success"
    assert res_fn["total_matches"] == 1
    assert res_fn["matches"][0]["name"] == "evaluate_hand"

    res_method = find_symbol("deal_cards", path=str(tmp_path))
    assert res_method["status"] == "success"
    assert res_method["total_matches"] == 1
    assert res_method["matches"][0]["name"] == "Table.deal_cards"
