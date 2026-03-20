from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json


def format_timestamp(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")


def humanize_incident_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "-"
    mapping = {
        "cap_breach": "Cap breach",
        "near_cap": "Near cap",
        "retry_storm": "Retry storm",
        "loop_suspect": "Loop suspect",
        "token_explosion": "Token explosion",
    }
    return mapping.get(normalized, normalized.replace("_", " ").replace("-", " ").title())


def format_evidence(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    preferred_order = [
        "reason",
        "count",
        "failure_count",
        "threshold_count",
        "window_seconds",
        "requests_60s",
        "tokens_60s",
        "estimated_next_tokens",
        "req_cap",
        "tok_cap",
        "provider",
        "model",
        "environment",
        "last_seen_at",
    ]
    seen: set[str] = set()
    lines: list[str] = []
    for key in preferred_order + sorted(str(item) for item in value.keys()):
        if key in seen or key not in value:
            continue
        seen.add(key)
        raw = value.get(key)
        if raw is None:
            continue
        label = key.replace("_", " ").title()
        if key.endswith("_at"):
            rendered = format_timestamp(raw)
        elif isinstance(raw, bool):
            rendered = "Yes" if raw else "No"
        elif isinstance(raw, (dict, list)):
            rendered = json.dumps(raw, sort_keys=True)
        else:
            rendered = str(raw)
        lines.append(f"{label}: {rendered}")
    return "\n".join(lines) if lines else "-"


def format_page_location(value: object) -> str:
    raw = str(value or "").strip()
    if not raw or raw == "-":
        return "-"
    path = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return raw
    if path.startswith("/app/"):
        section = path[len("/app/") :].strip("/")
        if not section:
            return "Dashboard"
        return "Dashboard / " + " / ".join(_humanize_segment(part) for part in section.split("/") if part)
    if path == "/app":
        return "Dashboard"
    if path.startswith("/"):
        return " / ".join(_humanize_segment(part) for part in path.strip("/").split("/") if part) or raw
    return raw


def render_base_email(
    *,
    eyebrow: str | None,
    title: str,
    subtitle: str,
    fields: list[tuple[str, str]],
    footer: str | None = None,
) -> dict[str, str]:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    safe_eyebrow = escape(str(eyebrow or "").strip())
    normalized_fields = [(_humanize_field_label(str(label)), str(value)) for label, value in fields]
    footer_copy = (footer or "").strip()

    rows_html = "".join(
        "<tr>"
        f"<td style=\"padding:10px 14px;vertical-align:top;font:600 12px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#667085;text-transform:uppercase;letter-spacing:0.04em;border-top:1px solid #eaecf0;white-space:nowrap;\">{escape(label)}</td>"
        f"<td style=\"padding:10px 14px;vertical-align:top;font:400 14px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#101828;border-top:1px solid #eaecf0;white-space:pre-wrap;\">{escape(value).replace(chr(10), '<br/>')}</td>"
        "</tr>"
        for label, value in normalized_fields
    )
    eyebrow_html = (
        f"<div style=\"margin-top:10px;font:600 12px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;letter-spacing:0.06em;text-transform:uppercase;color:#f59e0b;\">{safe_eyebrow}</div>"
        if safe_eyebrow
        else ""
    )
    footer_html = (
        "<p style=\"margin:20px 0 0;font:400 13px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#667085;\">"
        f"{escape(footer_copy)}"
        "</p>"
        if footer_copy
        else ""
    )
    html = (
        "<!doctype html>"
        "<html><body style=\"margin:0;padding:0;background:#f4f4f5;\">"
        "<div style=\"margin:0;padding:32px 16px;\">"
        "<div style=\"max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e4e7ec;border-radius:18px;overflow:hidden;box-shadow:0 8px 30px rgba(16,24,40,0.08);\">"
        "<div style=\"padding:24px 28px 18px;background:linear-gradient(135deg,#101828 0%,#1d2939 100%);\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"border-collapse:collapse;\">"
        "<tr>"
        "<td style=\"width:28px;height:28px;border:2px solid #7a7dff;border-radius:6px;\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"width:100%;height:100%;border-collapse:collapse;\">"
        "<tr>"
        "<td colspan=\"5\" style=\"height:9px;font-size:0;line-height:0;\">&nbsp;</td>"
        "</tr>"
        "<tr>"
        "<td style=\"width:4px;font-size:0;line-height:0;\">&nbsp;</td>"
        "<td style=\"width:6px;height:2px;background:#a78bfa;font-size:0;line-height:0;\">&nbsp;</td>"
        "<td style=\"width:6px;height:6px;border-radius:999px;background:#7a7dff;font-size:0;line-height:0;\">&nbsp;</td>"
        "<td style=\"width:6px;height:2px;background:#7cc1ff;font-size:0;line-height:0;\">&nbsp;</td>"
        "<td style=\"width:4px;font-size:0;line-height:0;\">&nbsp;</td>"
        "</tr>"
        "<tr>"
        "<td colspan=\"5\" style=\"height:9px;font-size:0;line-height:0;\">&nbsp;</td>"
        "</tr>"
        "</table>"
        "</td>"
        "<td style=\"width:10px;font-size:0;line-height:0;\">&nbsp;</td>"
        "<td style=\"font:700 12px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;letter-spacing:0.08em;text-transform:uppercase;color:#7a7dff;\">RHEONIC</td>"
        "</tr>"
        "</table>"
        f"{eyebrow_html}"
        f"<h1 style=\"margin:10px 0 0;font:700 28px/1.15 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#ffffff;\">{safe_title}</h1>"
        f"<p style=\"margin:14px 0 0;font:400 15px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#d0d5dd;\">{safe_subtitle}</p>"
        "</div>"
        "<div style=\"padding:20px 28px 28px;\">"
        "<table style=\"width:100%;border-collapse:collapse;border-spacing:0;background:#fcfcfd;border:1px solid #eaecf0;border-radius:14px;overflow:hidden;\">"
        f"{rows_html}"
        "</table>"
        f"{footer_html}"
        "</div>"
        "</div>"
        "</div>"
        "</body></html>"
    )

    text_lines = ["Rheonic", title, subtitle, ""]
    if safe_eyebrow:
        text_lines.insert(1, str(eyebrow))
    text_lines.extend(f"{label}: {value}" for label, value in normalized_fields)
    if footer_copy:
        text_lines.extend(["", footer_copy])
    text = "\n".join(text_lines)
    return {"html": html, "text": text}


def _humanize_field_label(label: str) -> str:
    normalized = label.strip()
    if not normalized:
        return "-"
    replacements = {
        "id": "ID",
        "ids": "IDs",
        "url": "URL",
        "urls": "URLs",
        "api": "API",
        "sdk": "SDK",
    }
    if "_" not in normalized and normalized.replace(" ", "").isalpha():
        words = normalized.split()
        return " ".join(replacements.get(word.lower(), word if word.isupper() else word.capitalize()) for word in words)
    words = normalized.replace("/", " / ").replace("_", " ").split()
    humanized: list[str] = []
    for word in words:
        lowered = word.lower()
        humanized.append(replacements.get(lowered, word.capitalize()))
    return " ".join(humanized).replace(" / ", " / ")


def _humanize_segment(value: str) -> str:
    return _humanize_field_label(value.replace("-", " "))
