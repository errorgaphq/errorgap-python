from __future__ import annotations

import pytest

from errorgap.configuration import Configuration

ENV_KEYS = [
    "ERRORGAP_ENDPOINT",
    "ERRORGAP_PROJECT_SLUG",
    "ERRORGAP_PROJECT_ID",
    "ERRORGAP_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_defaults_when_nothing_provided():
    config = Configuration()
    assert config.endpoint == "http://127.0.0.1:3030"
    assert config.async_ is True
    assert "password" in config.filter_keys
    assert "authorization" in config.filter_keys


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("ERRORGAP_ENDPOINT", "https://errorgap.example.com")
    monkeypatch.setenv("ERRORGAP_PROJECT_SLUG", "demo")
    monkeypatch.setenv("ERRORGAP_PROJECT_ID", "p_123")
    monkeypatch.setenv("ERRORGAP_API_KEY", "flk_test")
    config = Configuration()
    assert config.endpoint == "https://errorgap.example.com"
    assert config.project_slug == "demo"
    assert config.project_id == "p_123"
    assert config.api_key == "flk_test"


def test_explicit_kwargs_override_env(monkeypatch):
    monkeypatch.setenv("ERRORGAP_PROJECT_SLUG", "from-env")
    config = Configuration(project_slug="from-arg")
    assert config.project_slug == "from-arg"


def test_validate_raises_when_project_slug_missing():
    config = Configuration()
    with pytest.raises(ValueError, match="project_slug"):
        config.validate()


def test_validate_passes_when_project_slug_present():
    config = Configuration(project_slug="demo")
    config.validate()  # does not raise
