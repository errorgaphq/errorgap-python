from __future__ import annotations

from types import SimpleNamespace

import errorgap
from errorgap.sign_ins import build_sign_in


def test_flask_like_request_fields():
    req = SimpleNamespace(
        remote_addr="198.51.100.71", headers={"User-Agent": "Safari 18"}, method="POST", path="/login"
    )
    e = build_sign_in("success", user="mara@oxcoffee.com", request=req)
    assert e["user"] == "mara@oxcoffee.com"
    assert (e["ip"], e["user_agent"], e["path"]) == ("198.51.100.71", "Safari 18", "POST /login")
    assert e["occurred_at"].endswith("Z")


def test_starlette_like_request_fields():
    req = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.9"),
        url=SimpleNamespace(path="/token"),
        headers={"user-agent": "curl/8"},
        method="POST",
    )
    e = build_sign_in("mfa_failure", request=req)
    assert (e["ip"], e["path"], "user" in e) == ("203.0.113.9", "POST /token", False)


def test_unknown_outcome_is_dropped():
    assert build_sign_in("teleported") is None


def test_sign_in_posts_once_opted_in(ingestor, reset_errorgap):
    errorgap.init(endpoint=ingestor.endpoint, project_slug="ox-coffee", api_key="k1",
                  environment="production", async_=False, capture_globals=False)
    assert errorgap.sign_in("success", user="x").status == 204
    assert ingestor.requests == []

    errorgap.init(endpoint=ingestor.endpoint, project_slug="ox-coffee", api_key="k1",
                  environment="production", async_=False, capture_globals=False,
                  auth_events=True, app_name="oxcoffee-web")
    errorgap.sign_in("locked", user="admin", ip="203.0.113.9")
    req = ingestor.requests[0]
    assert req.path == "/api/projects/ox-coffee/logins/web"
    assert req.headers["x-errorgap-project-key"] == "k1"
    assert req.body["app"] == "oxcoffee-web"
    assert req.body["environment"] == "production"
    assert req.body["sdk"].startswith("errorgap-python ")
    assert req.body["events"][0]["outcome"] == "locked"
