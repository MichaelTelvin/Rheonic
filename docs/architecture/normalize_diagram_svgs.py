#!/usr/bin/env python3
"""Normalize generated diagram SVGs for browser-friendly sizing."""

from __future__ import annotations

import re
from pathlib import Path

SVG_PATHS = (
    Path("frontend/public/docs/architecture/incident_flow.svg"),
    Path("frontend/public/docs/architecture/protect_decision_flow.svg"),
)


def _normalize_svg(text: str) -> str:
    # Patch first (outer) and second (inner d2) <svg ...> tags.
    matches = list(re.finditer(r"<svg\b[^>]*>", text))
    if len(matches) < 2:
        return text

    def viewbox_width(tag: str) -> str:
        m = re.search(r'viewBox="[^"]*\s([0-9]+(?:\.[0-9]+)?)\s[0-9]+(?:\.[0-9]+)?"', tag)
        if not m:
            return "1200"
        w = m.group(1)
        return w[:-2] if w.endswith(".0") else w

    def repl(tag: str, *, outer: bool) -> str:
        tag = re.sub(r'\swidth="[^"]*"', "", tag)
        tag = re.sub(r'\sheight="[^"]*"', "", tag)
        tag = re.sub(r'\spreserveAspectRatio="[^"]*"', "", tag)
        tag = re.sub(r'\sstyle="[^"]*"', "", tag)
        max_w = viewbox_width(tag)
        if outer:
            insert = (
                ' width="100%" preserveAspectRatio="xMidYMin meet"'
                f' style="display:block;margin:0 auto;width:100%;max-width:{max_w}px;height:auto;background:#f4f6fb;"'
            )
        else:
            insert = (
                ' width="100%" preserveAspectRatio="xMidYMin meet"'
                f' style="display:block;width:100%;max-width:{max_w}px;height:auto;"'
            )
        return tag[:-1] + insert + ">"

    first = matches[0]
    second = matches[1]

    text = text[: first.start()] + repl(first.group(0), outer=True) + text[first.end() :]

    # Re-find second after first replacement changed offsets.
    matches = list(re.finditer(r"<svg\b[^>]*>", text))
    second = matches[1]
    text = text[: second.start()] + repl(second.group(0), outer=False) + text[second.end() :]

    # Strip embedded D2 font blobs so charts render faster in the browser using system fonts.
    text = re.sub(r"@font-face\s*{.*?}", "", text, flags=re.DOTALL)
    text = re.sub(
        r'font-family:\s*"d2-[^"]+-font-bold";',
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;font-weight:700;',
        text,
    )
    text = re.sub(
        r'font-family:\s*"d2-[^"]+-font-italic";',
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;font-style:italic;',
        text,
    )
    return text


def main() -> None:
    for path in SVG_PATHS:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        normalized = _normalize_svg(content)
        path.write_text(normalized, encoding="utf-8")


if __name__ == "__main__":
    main()
