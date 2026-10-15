"""Tests for the terminal first-run onboarding wizard."""

from zeus.cli import onboarding


def test_setup_wizard_configures_model_then_selected_channels(monkeypatch):
    calls = []
    monkeypatch.setattr(onboarding, "setup_model", lambda: calls.append("model") or True)
    monkeypatch.setattr(onboarding, "_get_input", lambda prompt: "whatsapp, instagram")
    monkeypatch.setitem(onboarding._CHANNEL_SETUP, "whatsapp", lambda: calls.append("whatsapp") or True)
    monkeypatch.setitem(onboarding._CHANNEL_SETUP, "instagram", lambda: calls.append("instagram") or True)

    assert onboarding.run_setup_wizard() is True
    assert calls == ["model", "whatsapp", "instagram"]


def test_setup_wizard_stops_if_model_setup_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(onboarding, "setup_model", lambda: False)
    monkeypatch.setattr(onboarding, "_get_input", lambda prompt: calls.append(prompt) or "whatsapp")

    assert onboarding.run_setup_wizard() is False
    assert calls == []
