from __future__ import annotations

from pathlib import Path


def test_staging_compose_contains_core_services_and_readiness_checks() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "docker-compose.staging.yml"
    content = compose_path.read_text(encoding="utf-8")

    assert "backend:" in content
    assert "worker:" in content
    assert "scheduler:" in content
    assert "db_init:" in content
    assert "frontend:" in content
    assert "/ready" in content
    assert "rq worker" in content
    assert "scheduler_bootstrap" in content
