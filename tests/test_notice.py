from __future__ import annotations

from errorgap.configuration import Configuration
from errorgap.notice import build_notice
from errorgap.version import VERSION


def _raise(message: str) -> Exception:
    try:
        raise TypeError(message)
    except Exception as exc:
        return exc


def test_captures_type_and_message():
    config = Configuration(project_slug="demo")
    notice = build_notice(_raise("boom"), config)
    assert notice["errors"][0]["type"] == "TypeError"
    assert notice["errors"][0]["message"] == "boom"


def test_includes_notifier_identification():
    config = Configuration(project_slug="demo", environment="test")
    notice = build_notice(_raise("x"), config)
    assert notice["context"]["notifier"] == "errorgap-python"
    assert notice["context"]["notifier_version"] == VERSION
    assert notice["context"]["environment"] == "test"


def test_merges_custom_context_over_defaults():
    config = Configuration(project_slug="demo")
    notice = build_notice(_raise("x"), config, context={"component": "billing"})
    assert notice["context"]["component"] == "billing"
    assert notice["context"]["notifier"] == "errorgap-python"


def test_filters_sensitive_params():
    config = Configuration(project_slug="demo")
    notice = build_notice(
        _raise("x"),
        config,
        params={
            "username": "alice",
            "password": "hunter2",
            "nested": {"auth_token": "abc", "safe": "ok"},
        },
    )
    assert notice["params"]["username"] == "alice"
    assert notice["params"]["password"] == "[FILTERED]"
    assert notice["params"]["nested"]["auth_token"] == "[FILTERED]"
    assert notice["params"]["nested"]["safe"] == "ok"


def test_includes_project_id():
    config = Configuration(project_slug="demo", project_id="p_1")
    notice = build_notice(_raise("x"), config)
    assert notice["project_id"] == "p_1"


def test_received_at_ends_with_z():
    config = Configuration(project_slug="demo")
    notice = build_notice(_raise("x"), config)
    assert notice["received_at"].endswith("Z")
