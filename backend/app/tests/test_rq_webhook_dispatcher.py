from datetime import datetime, timezone

from app.infrastructure.alerts import rq_webhook_dispatcher
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, TransportOutboxRecord


def test_webhook_dispatcher_enqueues_outbox_row_and_dispatch_job(tmp_path, monkeypatch) -> None:
    db_url = f"sqlite:///{tmp_path}/rq_webhook_dispatcher_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    monkeypatch.setattr(rq_webhook_dispatcher, "DatabaseSessionFactory", lambda: DatabaseSessionFactory(database_url=db_url))
    captured_outbox_ids: list[str] = []
    monkeypatch.setattr(rq_webhook_dispatcher, "enqueue_outbox_delivery", lambda outbox_id: captured_outbox_ids.append(outbox_id))

    dispatcher = rq_webhook_dispatcher.RQWebhookDispatcher(redis_url="redis://localhost:6379/15")
    dispatcher.enqueue(
        project_id="p1",
        payload={"event": "webhook.test", "sent_at": datetime.now(timezone.utc).isoformat()},
        event_type="webhook.test",
        override_url="https://example.test/hook",
        override_payload_template_json="{\"text\":\"{{event}}\"}",
        force_send=True,
    )

    with session_factory.create_session() as session:
        rows = session.query(TransportOutboxRecord).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.project_id == "p1"
        assert row.kind == "webhook"
        assert row.event_type == "webhook.test"
        assert row.destination == "https://example.test/hook"
        assert row.payload["__transport_meta"]["override_payload_template_json"] == "{\"text\":\"{{event}}\"}"

    assert len(captured_outbox_ids) == 1
    assert captured_outbox_ids[0] == rows[0].id
