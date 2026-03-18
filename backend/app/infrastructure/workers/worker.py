import traceback

from redis import Redis
from rq import Worker, Queue

from app.config import Settings
from app.logger import bind_trace_context, build_log_extra, configure_logging, generate_trace_id, get_logger, reset_trace_context

logger = get_logger(__name__)


def _job_exception_handler(job, exc_type, exc_value, tb) -> bool:
    # Log failed jobs with contextual information and traceback.
    project_id = None
    trace_id = None
    kwargs = getattr(job, "kwargs", {}) or {}
    if isinstance(kwargs, dict):
        project_id = kwargs.get("project_id")
        trace_id = kwargs.get("trace_id")
    tokens = bind_trace_context(trace_id=trace_id)
    logger.error(
        "RQ job failed",
        extra=build_log_extra(
            event="job_failed",
            metadata={
                "job_id": getattr(job, "id", None),
                "job_name": getattr(job, "func_name", None),
                "project_id": project_id,
                "error_type": getattr(exc_type, "__name__", str(exc_type)),
                "error_message": str(exc_value),
                "stack_trace": "".join(traceback.format_exception(exc_type, exc_value, tb)),
            },
            trace_id=trace_id,
        ),
    )
    reset_trace_context(tokens)
    return True


def main() -> None:
    settings = Settings()
    configure_logging(service_name="worker", level=settings.log_level)
    redis_url = Settings().redis_url
    if not redis_url:
        raise ValueError("REDIS_URL is not set")
    conn = Redis.from_url(redis_url)

    with conn:
        worker = Worker(
            queues=["rheonic"],
            connection=conn,
            exception_handlers=[_job_exception_handler],
        )
        logger.info(
            "RQ worker started",
            extra=build_log_extra(
                event="worker_started",
                metadata={"queues": ["rheonic"]},
                trace_id=generate_trace_id(),
            ),
        )
        worker.work()


if __name__ == "__main__":
    main()
