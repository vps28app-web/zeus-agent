"""Configuration loader and defaults."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG = {
    "provider": "openrouter",
    "model": "openrouter/auto",
    "max_turns": 20,
    "memory": {
        "enabled": True,
        "path": "~/.zeus/memory.json",
    },
}


def config_path() -> Path:
    return Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))) / "config.yaml"


def load_config() -> Dict[str, Any]:
    path = config_path()
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    with path.open("r", encoding="utf-8") as f:
        return {**DEFAULT_CONFIG, **yaml.safe_load(f)}


def save_config(config: Dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False)
