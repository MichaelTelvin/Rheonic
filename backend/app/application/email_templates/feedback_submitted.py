from __future__ import annotations


def render_feedback_submitted(payload: dict[str, object]) -> dict[str, str]:
    message = str(payload.get("message") or "").strip()
    email = str(payload.get("email") or "").strip() or "-"
    user_id = str(payload.get("user_id") or "").strip() or "-"
    user_email = str(payload.get("user_email") or "").strip() or "-"
    project_id = str(payload.get("project_id") or "").strip() or "-"
    page = str(payload.get("page") or "").strip() or "-"
    mode = str(payload.get("mode") or "").strip() or "-"
    timestamp = str(payload.get("timestamp") or "").strip() or "-"
    app_version = str(payload.get("app_version") or "").strip() or "-"

    subject = "Rheonic beta feedback"
    text = "\n".join(
        [
            "Rheonic beta feedback",
            "",
            f"message: {message}",
            f"email: {email}",
            f"user_id: {user_id}",
            f"user_email: {user_email}",
            f"project_id: {project_id}",
            f"page: {page}",
            f"mode: {mode}",
            f"timestamp: {timestamp}",
            f"app_version: {app_version}",
        ]
    )
    html = (
        "<h3>Rheonic beta feedback</h3>"
        f"<p><strong>message:</strong> {message}</p>"
        f"<p><strong>email:</strong> {email}</p>"
        f"<p><strong>user_id:</strong> {user_id}</p>"
        f"<p><strong>user_email:</strong> {user_email}</p>"
        f"<p><strong>project_id:</strong> {project_id}</p>"
        f"<p><strong>page:</strong> {page}</p>"
        f"<p><strong>mode:</strong> {mode}</p>"
        f"<p><strong>timestamp:</strong> {timestamp}</p>"
        f"<p><strong>app_version:</strong> {app_version}</p>"
    )
    return {"subject": subject, "html": html, "text": text}
