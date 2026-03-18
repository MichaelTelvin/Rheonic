# Database base configuration scaffolding.
from collections.abc import Generator
from time import perf_counter

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, app_config
from app.logger import build_log_extra, get_logger

logger = get_logger(__name__)


class DatabaseSessionFactory:
    # Factory abstraction for creating database sessions.

    def __init__(self, database_url: str | None = None) -> None:
        # Create a session factory for the configured database URL.
        try:
            self._database_url = database_url or Settings().database_url
            if not self._database_url:
                raise ValueError("DATABASE_URL is not set")
            self._engine: Engine = create_engine(self._database_url, future=True)
            _register_engine_logging(self._engine)
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                class_=Session,
            )
        except Exception:
            logger.exception("Failed to initialize DatabaseSessionFactory")
            raise

    @property
    def engine(self) -> Engine:
        # Return the SQLAlchemy engine.
        return self._engine

    def create_session(self) -> Session:
        # Create and return a new database session object.
        try:
            return self._session_factory()
        except Exception:
            logger.exception("Failed to create database session")
            raise

    def session_scope(self) -> Generator[Session, None, None]:
        # Provide a managed session scope for repository operations.
        session = self.create_session()
        try:
            yield session
            session.commit()
        except Exception:
            logger.exception("Database session scope failed")
            session.rollback()
            raise
        finally:
            session.close()


def _register_engine_logging(engine: Engine) -> None:
    if getattr(engine, "_rheonic_db_logging_registered", False):
        return
    setattr(engine, "_rheonic_db_logging_registered", True)

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        _ = cursor, parameters, executemany
        conn.info.setdefault("rheonic_query_start_times", []).append(perf_counter())
        context._rheonic_statement_operation = _extract_sql_operation(statement)

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        _ = cursor, statement, parameters, executemany
        starts = conn.info.get("rheonic_query_start_times", [])
        if not starts:
            return
        started = starts.pop(-1)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        if duration_ms < app_config.db_slow_query_threshold_ms:
            return
        logger.warning(
            "Slow database query",
            extra=build_log_extra(
                event="db_query_slow",
                metadata={
                    "operation": getattr(context, "_rheonic_statement_operation", "unknown"),
                    "duration_ms": duration_ms,
                },
            ),
        )

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context):  # type: ignore[no-untyped-def]
        logger.exception(
            "Database query failed",
            extra=build_log_extra(
                event="db_query_error",
                metadata={
                    "operation": _extract_sql_operation(getattr(exception_context, "statement", None)),
                    "is_disconnect": bool(getattr(exception_context, "is_disconnect", False)),
                },
            ),
        )


def _extract_sql_operation(statement: str | None) -> str:
    if not statement:
        return "unknown"
    token = statement.strip().split(None, 1)[0].lower()
    return token or "unknown"
