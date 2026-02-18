import os
import traceback

from redis import Redis
from rq import Worker, Queue

from app.logger import get_logger

logger = get_logger(__name__)


def _job_exception_handler(job, exc_type, exc_value, tb) -> bool:
    # Log failed jobs with contextual information and traceback.
    project_id = None
    kwargs = getattr(job, "kwargs", {}) or {}
    if isinstance(kwargs, dict):
        project_id = kwargs.get("project_id")
    logger.error(
        "RQ job failed",
        extra={
            "job_id": getattr(job, "id", None),
            "job_name": getattr(job, "func_name", None),
            "project_id": project_id,
            "error_type": getattr(exc_type, "__name__", str(exc_type)),
            "error": str(exc_value),
            "traceback": "".join(traceback.format_exception(exc_type, exc_value, tb)),
        },
    )
    return True


def main() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL is not set")
    conn = Redis.from_url(redis_url)

    with conn:
        worker = Worker(
            queues=["llmtbg"],
            connection=conn,
            exception_handlers=[_job_exception_handler],
        )
        logger.info("RQ worker started", extra={"queues": ["llmtbg"]})
        worker.work()


if __name__ == "__main__":
    main()
