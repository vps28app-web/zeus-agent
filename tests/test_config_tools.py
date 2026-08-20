"""Tests for Zeus configuration management tools."""

import os
from zeus.tools.config_tools import (
    get_zeus_config,
    update_zeus_config,
    list_available_models,
)


def test_get_zeus_config():
    config = get_zeus_config()
    assert "zeus_provider" in config
    assert "zeus_model" in config
    assert "api_keys_status" in config


def test_update_zeus_config():
    res = update_zeus_config("TEST_KEY_VAR", "secret_value_1234")
    assert res["status"] == "success"
    assert os.getenv("TEST_KEY_VAR") == "secret_value_1234"


def test_list_available_models():
    models = list_available_models("google")
    assert models["provider"] == "google"
    assert len(models["models"]) > 0
