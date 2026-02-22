# Manual entrypoint for stale-incident auto-close.
from app.infrastructure.jobs.auto_close_incidents_job import auto_close_incidents


def main() -> None:
    auto_close_incidents()


if __name__ == "__main__":
    main()
