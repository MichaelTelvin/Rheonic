import re

_MODEL_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def normalized_model_name(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    return _MODEL_DATE_SUFFIX_RE.sub("", normalized)
