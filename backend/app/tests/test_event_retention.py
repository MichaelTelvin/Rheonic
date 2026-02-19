from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.services.event_retention_service import EventRetentionService
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, EventRecord
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl


def test_purge_old_events_removes_only_rows_older_than_retention_cutoff(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/event_retention.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    now = datetime.now(timezone.utc)
    old_ts = now - timedelta(days=40)
    recent_ts = now - timedelta(days=2)

    with session_factory.create_session() as session:
        session.add(
            EventRecord(
                id=str(uuid4()),
                ts=old_ts,
                project_id="p-retention",
                provider="openai",
                model="gpt-4o-mini",
                environment="dev",
                input_tokens=1,
                output_tokens=1,
                total_tokens=2,
                created_at=old_ts,
            )
        )
        session.add(
            EventRecord(
                id=str(uuid4()),
                ts=recent_ts,
                project_id="p-retention",
                provider="openai",
                model="gpt-4o-mini",
                environment="dev",
                input_tokens=1,
                output_tokens=1,
                total_tokens=2,
                created_at=recent_ts,
            )
        )
        session.commit()

    service = EventRetentionService(
        event_repository=EventRepositoryImpl(session_factory=session_factory),
        retention_days=30,
    )

    deleted_count = service.purge_old_events(now=now)
    assert deleted_count == 1

    with session_factory.create_session() as session:
        remaining = session.query(EventRecord).all()
        assert len(remaining) == 1
        assert remaining[0].ts.replace(tzinfo=timezone.utc) == recent_ts
