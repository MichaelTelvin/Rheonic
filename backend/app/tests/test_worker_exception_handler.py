import traceback
from types import SimpleNamespace

from app.infrastructure.workers import worker as worker_module


def test_job_exception_handler_accepts_stack_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_error(message: str, *, extra=None) -> None:
        captured["message"] = message
        captured["extra"] = extra

    monkeypatch.setattr(worker_module.logger, "error", fake_error)
    monkeypatch.setattr(worker_module, "bind_trace_context", lambda trace_id=None: None)
    monkeypatch.setattr(worker_module, "reset_trace_context", lambda tokens: None)

    job = SimpleNamespace(
        id="job-1",
        func_name="demo.task",
        kwargs={"project_id": "p-1", "trace_id": "trace-1"},
    )
    stack_summary = traceback.StackSummary.from_list(
        [("worker.py", 31, "_job_exception_handler", "stack_trace = ...")]
    )

    result = worker_module._job_exception_handler(job, RuntimeError, RuntimeError("boom"), stack_summary)

    assert result is True
    assert captured["message"] == "RQ job failed"
    metadata = captured["extra"]["metadata"]
    assert metadata["job_id"] == "job-1"
    assert metadata["project_id"] == "p-1"
    assert metadata["error_type"] == "RuntimeError"
    assert metadata["error_message"] == "boom"
    assert "worker.py" in metadata["stack_trace"]
