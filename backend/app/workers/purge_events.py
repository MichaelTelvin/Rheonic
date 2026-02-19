# Manual entrypoint for raw-event retention purge.
from app.infrastructure.jobs.purge_events_job import purge_old_events


def main() -> None:
    purge_old_events()


if __name__ == "__main__":
    main()
