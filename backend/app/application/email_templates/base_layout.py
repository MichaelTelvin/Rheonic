from __future__ import annotations

from html import escape


def render_base_email(*, title: str, subtitle: str, fields: list[tuple[str, str]]) -> dict[str, str]:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    normalized_fields = [(str(label), str(value)) for label, value in fields]

    rows_html = "".join(
        f"<tr><td><strong>{escape(label)}</strong></td><td>{escape(value)}</td></tr>"
        for label, value in normalized_fields
    )
    html = (
        "<!doctype html>"
        "<html><body>"
        f"<h2>{safe_title}</h2>"
        f"<p>{safe_subtitle}</p>"
        f"<table>{rows_html}</table>"
        "</body></html>"
    )

    text_lines = [title, subtitle, ""]
    text_lines.extend(f"{label}: {value}" for label, value in normalized_fields)
    text = "\n".join(text_lines)
    return {"html": html, "text": text}

