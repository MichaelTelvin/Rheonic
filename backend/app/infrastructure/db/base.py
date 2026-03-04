# Database base configuration scaffolding.
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.logger import get_logger

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
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                class_=Session,
            )
            logger.info("DatabaseSessionFactory initialized")
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
