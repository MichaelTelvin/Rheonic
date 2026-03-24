from __future__ import annotations

from fastapi.testclient import TestClient

import app.health_checks as health_checks_module
import app.main as main_module


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb

    def execute(self, statement):
        _ = statement
        return None


class _FakeDbFactory:
    def create_session(self):
        return _FakeSession()


class _FakeRedisOk:
    def ping(self) -> bool:
        return True


class _FakeRedisFail:
    def ping(self) -> bool:
        return False


def test_health_and_ready_ok(monkeypatch) -> None:
    monkeypatch.setattr(health_checks_module, "get_db_session_factory", lambda: _FakeDbFactory())
    monkeypatch.setattr(health_checks_module, "get_redis_client", lambda: _FakeRedisOk())

    with TestClient(main_module.app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        api_health = client.get("/api/v1/health")
        version = client.get("/api/v1/version")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Trace-ID"]
    assert health.headers["X-Span-ID"]
    assert health.headers["X-App-Version"]
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.headers["X-Trace-ID"]
    assert ready.headers["X-Span-ID"]
    assert api_health.status_code == 200
    assert api_health.json()["status"] == "ok"
    assert version.status_code == 200
    assert version.json()["version"]
    assert version.json()["environment"]


def test_ready_returns_503_when_dependency_fails(monkeypatch) -> None:
    monkeypatch.setattr(health_checks_module, "get_db_session_factory", lambda: _FakeDbFactory())
    monkeypatch.setattr(health_checks_module, "get_redis_client", lambda: _FakeRedisFail())

    with TestClient(main_module.app) as client:
        ready = client.get("/ready")
        api_health = client.get("/api/v1/health")
    assert ready.status_code == 503
    assert api_health.status_code == 503
