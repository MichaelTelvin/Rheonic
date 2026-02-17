# Concrete user repository implementation.
from app.application.interfaces.user_repository import UserRepository
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import UserRecord
from app.logger import get_logger

logger = get_logger(__name__)


class UserRepositoryImpl(UserRepository):
    # Database-backed implementation for users.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory

    def get_by_id(self, user_id: str) -> User | None:
        # Return user by id.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(UserRecord).filter(UserRecord.id == user_id).first()
            return _to_domain(record) if record is not None else None
        except Exception:
            logger.exception("Failed fetching user by id", extra={"user_id": user_id})
            raise

    def get_by_email(self, email: str) -> User | None:
        # Return user by email.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(UserRecord).filter(UserRecord.email == email).first()
            return _to_domain(record) if record is not None else None
        except Exception:
            logger.exception("Failed fetching user by email")
            raise

    def create_user(self, user: User) -> User:
        # Persist new user.
        try:
            with self._session_factory.create_session() as session:
                session.add(
                    UserRecord(
                        id=user.id,
                        email=user.email,
                        password_hash=user.password_hash,
                        created_at=user.created_at,
                    )
                )
                session.commit()
            return user
        except Exception:
            logger.exception("Failed creating user")
            raise


def _to_domain(record: UserRecord) -> User:
    # Convert SQLAlchemy user record to domain model.
    return User(
        id=record.id,
        email=record.email,
        password_hash=record.password_hash,
        created_at=record.created_at,
    )
