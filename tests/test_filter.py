from __future__ import annotations

from errorgap.filter import filter_params

DEFAULTS = ("password", "token", "secret", "api_key", "authorization", "cookie")


def test_masks_filtered_keys():
    out = filter_params(
        {"username": "alice", "password": "hunter2", "access_token": "x"},
        DEFAULTS,
    )
    assert out["username"] == "alice"
    assert out["password"] == "[FILTERED]"
    assert out["access_token"] == "[FILTERED]"


def test_recurses_into_nested_dicts():
    out = filter_params({"user": {"name": "alice", "api_key": "x"}}, DEFAULTS)
    assert out["user"]["name"] == "alice"
    assert out["user"]["api_key"] == "[FILTERED]"


def test_case_insensitive_match():
    out = filter_params({"Authorization": "Bearer xyz"}, DEFAULTS)
    assert out["Authorization"] == "[FILTERED]"


def test_arrays_untouched():
    out = filter_params({"items": [1, 2, 3]}, DEFAULTS)
    assert out["items"] == [1, 2, 3]
