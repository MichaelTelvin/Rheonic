# Manual entrypoint for sending one project webhook payload.
from __future__ import annotations

import json
import sys

from app.infrastructure.jobs.webhook_job import send_project_webhook


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit("Usage: python -m app.workers.send_webhook_job <project_id> <event_type> <payload_json>")
    project_id = sys.argv[1]
    event_type = sys.argv[2]
    payload = json.loads(sys.argv[3])
    if not isinstance(payload, dict):
        raise SystemExit("payload_json must decode to an object")
    send_project_webhook(project_id=project_id, payload=payload, event_type=event_type)


if __name__ == "__main__":
    main()
