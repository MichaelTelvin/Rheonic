# API tests for feedback endpoint.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_current_user, get_feedback_mailer, get_settings
from app.domain.models.user import User
from app.main import app


class FakeFeedbackMailer:
    # Test double for feedback email sender.

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, *, subject: str, body: str) -> None:
        self.sent.append((subject, body))


def test_feedback_endpoint_sends_email_payload() -> None:
    # Valid payload should be accepted and forwarded to mailer.
    fake_mailer = FakeFeedbackMailer()
    app.dependency_overrides[get_feedback_mailer] = lambda: fake_mailer
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

    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    assert len(fake_mailer.sent) == 1
    subject, body = fake_mailer.sent[0]
    assert subject == "Rheonic beta feedback"
    assert "project_id: p1" in body
    assert "mode: protect" in body
    assert "The alerts setup was confusing." in body

    app.dependency_overrides.clear()


def test_feedback_endpoint_rejects_empty_message() -> None:
    # Empty message should return validation error.
    fake_mailer = FakeFeedbackMailer()
    app.dependency_overrides[get_feedback_mailer] = lambda: fake_mailer
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
    assert len(fake_mailer.sent) == 0
    app.dependency_overrides.clear()


def test_public_config_returns_public_contact_email() -> None:
    # Public config endpoint should expose configured contact email.
    app.dependency_overrides[get_settings] = lambda: Settings(public_contact_email="hello@rheonic.ai")
    client = TestClient(app)
    response = client.get("/api/v1/public-config")
    assert response.status_code == 200
    assert response.json() == {"public_contact_email": "hello@rheonic.ai"}
    app.dependency_overrides.clear()
