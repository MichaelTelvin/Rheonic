# API tests for feedback endpoint.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.transport_service import TransportService
from app.config import Settings
from app.dependencies import get_current_user, get_settings, get_transport_service
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, TransportOutboxRecord
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.main import app


def _make_transport_service(db_url: str) -> TransportService:
    session_factory = DatabaseSessionFactory(database_url=db_url)
    return TransportService(
        outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
        enqueue_job=lambda outbox_id: None,
    )


def test_feedback_endpoint_enqueues_outbox_email_and_returns_202(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/feedback_api_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    app.dependency_overrides[get_transport_service] = lambda: _make_transport_service(db_url)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1",
        email="user@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/feedback",
        json={
            "message": "The alerts setup was confusing.",
            "email": "feedback@example.com",
            "project_id": "p1",
            "page": "/app/settings",
            "mode": "protect",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app_version": "1.0.0",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "queued"}

    with session_factory.create_session() as session:
        rows = session.query(TransportOutboxRecord).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "email"
        assert row.event_type == "feedback.submitted"
        assert row.template == "feedback_submitted"
        assert row.status == "pending"
        assert row.payload["message"] == "The alerts setup was confusing."
        assert row.payload["user_email"] == "user@example.com"

    app.dependency_overrides.clear()


def test_feedback_endpoint_rejects_empty_message(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/feedback_api_empty_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    app.dependency_overrides[get_transport_service] = lambda: _make_transport_service(db_url)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1",
        email="user@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/feedback",
        json={"message": "   "},
    )

    assert response.status_code == 400
    with session_factory.create_session() as session:
        assert session.query(TransportOutboxRecord).count() == 0
    app.dependency_overrides.clear()


def test_public_config_returns_public_contact_email() -> None:
    # Public config endpoint should expose configured contact email.
    app.dependency_overrides[get_settings] = lambda: Settings(public_contact_email="hello@rheonic.dev")
    client = TestClient(app)
    response = client.get("/api/v1/public-config")
    assert response.status_code == 200
    assert response.json() == {"public_contact_email": "hello@rheonic.dev"}
    app.dependency_overrides.clear()
