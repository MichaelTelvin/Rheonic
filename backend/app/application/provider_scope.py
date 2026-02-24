# Provider scoping helpers for project-bound counters/caches.


def scoped_project_provider_id(project_id: str, provider: str | None) -> str:
    # Build a stable composite id used by Redis stores keyed by project scope.
    normalized_provider = (provider or "").strip() or "unknown"
    return f"{project_id}:{normalized_provider}"
